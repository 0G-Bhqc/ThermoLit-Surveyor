"""负样本回归防线:单位写法长尾、跨字段温度、极值与证据校验的陷阱用例。

来源:深度评测 P0-1(跨字段温度错配)/ P0-2(证据句无校验)修复的回归防线;
新单位写法解析规则必须先在这里加用例。
"""
import unittest

from thermolit import physics
from thermolit.schemas import check_evidence


class TestFieldTemperature(unittest.TestCase):
    def test_at_and_suffix_forms(self):
        self.assertEqual(physics.parse_field_temperature("S = 200 uV/K @ 350 K"), 350.0)
        self.assertEqual(physics.parse_field_temperature("sigma measured at 400 K"), 400.0)
        self.assertEqual(physics.parse_field_temperature("0.09 S/cm at room temperature"),
                         300.0)
        self.assertEqual(physics.parse_field_temperature("mobility (RT value)"), 300.0)
        self.assertIsNone(physics.parse_field_temperature("850 S/cm"))

    def test_out_of_range_rejected(self):
        self.assertIsNone(physics.parse_field_temperature("zT = 2.6 @ 99999 K"))

    def test_per_field_temperature_in_audit(self):
        # 评测报告 P0-1 的原始案例:S@300K 但 zT@923K,旧实现把 T=923 套到全部字段
        rec = {"seebeck_coefficient": "+450 uV/K @ 300 K",
               "electrical_conductivity": "0.09 S/cm at room temperature",
               "zT_value": "2.6 @ 923 K", "temperature_k": 923,
               "doi": "d", "title": "t"}
        a = physics.audit_record(rec)
        self.assertEqual(a["T_S"], 300.0)
        self.assertEqual(a["T_sigma"], 300.0)
        self.assertEqual(a["T_zT"], 923.0)
        self.assertEqual(a["T_K"], 300.0)  # 输运值温度,不再是 923
        self.assertTrue(any("923" in f and "不同" in f for f in a["flags"]))

    def test_mixed_transport_temps_reject_derivation(self):
        rec = {"seebeck_coefficient": "200 uV/K @ 300 K",
               "electrical_conductivity": "1200 S/cm @ 400 K",
               "thermal_conductivity": "1.6 W/mK @ 300 K",
               "zT_value": "1.4", "doi": "d", "title": "t"}
        a = physics.audit_record(rec)
        self.assertTrue(any("温度混计" in f for f in a["flags"]))
        self.assertIsNone(a["zT_calc"])   # 跨温派生被拒绝
        self.assertIsNone(a["kappa_l"])

    def test_same_temp_still_computes(self):
        rec = {"seebeck_coefficient": "200 uV/K @ 300 K",
               "electrical_conductivity": "1200 S/cm @ 300 K",
               "thermal_conductivity": "1.6 W/mK @ 300 K",
               "zT_value": "1.4", "doi": "d", "title": "t"}
        a = physics.audit_record(rec)
        # (2e-4)^2 * 1.2e5 * 300 / 1.6 = 0.9
        self.assertAlmostEqual(a["zT_calc"], 0.9, places=2)
        self.assertFalse(any("温度混计" in f for f in a["flags"]))


class TestUnitLongTail(unittest.TestCase):
    def test_kappa_parenthesized(self):
        self.assertAlmostEqual(physics.parse_kappa("1.3 W/(m·K)"), 1.3)

    def test_resistivity_space_form(self):
        self.assertAlmostEqual(physics.parse_sigma("2.5 mΩ cm"), 1.0 / 2.5e-5, places=0)

    def test_resistivity_micro(self):
        # 10 µΩ·cm = 10 × 1e-8 Ω·m = 1e-7 Ω·m → σ = 1e7 S/m(金属量级)
        self.assertAlmostEqual(physics.parse_sigma("10 µΩ·cm"), 1e7)

    def test_sigma_scientific(self):
        self.assertAlmostEqual(physics.parse_sigma("3×10⁶ S/m"), 3e6)

    def test_seebeck_mV_with_space(self):
        self.assertAlmostEqual(physics.parse_seebeck("0.25 mV/K"), 2.5e-4)

    def test_unparseable_sigma_flagged(self):
        a = physics.audit_record({"electrical_conductivity": "good sample",
                                  "doi": "d", "title": "t"})
        self.assertTrue(any("electrical_conductivity字段存在但无法解析" in f
                            for f in a["flags"]))


class TestEvidenceContainment(unittest.TestCase):
    EXCERPT = ("The sample shows zT = 0.9 @ 350 K with an unusually low\n"
               "lattice thermal conductivity of 0.6 W/mK.")

    def test_exact_and_whitespace_collapsed_match(self):
        out = check_evidence(
            {"evidence_sentences": {"zT_value": "The sample shows zT = 0.9 @ 350 K"}},
            self.EXCERPT)
        self.assertEqual(out["verified"], ["zT_value"])

        out = check_evidence(
            {"evidence_sentences": {"thermal_conductivity":
                                    "lattice thermal  conductivity of 0.6 W/mK."}},
            self.EXCERPT)
        self.assertEqual(out["verified"], ["thermal_conductivity"])  # 换行/多空格归一

    def test_fabricated_quote_flagged(self):
        out = check_evidence(
            {"evidence_sentences": {"zT_value": "zT reached an unprecedented 3.5 at 300 K"}},
            self.EXCERPT)
        self.assertEqual(out["unverified"], ["zT_value"])

    def test_unverified_propagates_to_audit_flags(self):
        rec = {"seebeck_coefficient": "-180 uV/K", "electrical_conductivity": "1200 S/cm",
               "thermal_conductivity": "1.3 W/mK", "zT_value": "0.9 @ 350 K",
               "temperature_k": 350, "doi": "d", "title": "t",
               "evidence_check": {"verified": [], "unverified": ["zT_value"]}}
        a = physics.audit_record(rec)
        self.assertTrue(any("证据句未核实" in f for f in a["flags"]))


if __name__ == "__main__":
    unittest.main()
