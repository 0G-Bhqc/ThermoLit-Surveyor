"""物理引擎测试:单位解析、Wiedemann-Franz 解耦、zT 一致性、审计表。"""
import unittest

from thermolit import physics


# ---------------------------------------------------------------- 单位解析
class TestUnitParsing(unittest.TestCase):
    def test_seebeck_uV(self):
        self.assertAlmostEqual(physics.parse_seebeck("-180 µV/K"), -1.8e-4)
        self.assertAlmostEqual(physics.parse_seebeck("S = 200 μV/K @ 300K"), 2.0e-4)

    def test_seebeck_mV_and_unicode_minus(self):
        self.assertAlmostEqual(physics.parse_seebeck("−0.25 mV/K"), -2.5e-4)

    def test_seebeck_no_unit_assumes_uV(self):
        self.assertAlmostEqual(physics.parse_seebeck("180"), 1.8e-4)

    def test_sigma_S_per_cm(self):
        self.assertAlmostEqual(physics.parse_sigma("1200 S/cm"), 1.2e5)

    def test_sigma_resistivity_mOhm_cm(self):
        # 1.5 mOhm·cm = 1.5e-5 Ohm·m → sigma ≈ 6.67e4 S/m
        self.assertAlmostEqual(physics.parse_sigma("1.5 mΩ·cm"), 1.0 / 1.5e-5, places=0)

    def test_kappa_variants(self):
        self.assertAlmostEqual(physics.parse_kappa("1.3 W/mK"), 1.3)
        self.assertAlmostEqual(physics.parse_kappa("2.1 W m−1 K−1"), 2.1)
        self.assertAlmostEqual(physics.parse_kappa("12 mW/cmK"), 1.2)
        self.assertAlmostEqual(physics.parse_kappa("0.45 W/cmK"), 45.0)

    def test_sigma_no_unit_is_none(self):
        self.assertIsNone(physics.parse_sigma("значение 1200"))  # 无单位不可猜测

    def test_scientific_notation_unicode(self):
        # 1.2×10⁵ S/m → 1.2e5 S/m(解析不改变 S/m 单位)
        self.assertAlmostEqual(physics.parse_sigma("1.2×10⁵ S/m"), 1.2e5)

    def test_parse_temperature(self):
        self.assertEqual(physics.parse_temperature({"zT_value": "0.9 @ 350 K"}), 350.0)
        self.assertEqual(physics.parse_temperature({"temperature_k": 320}), 320.0)
        self.assertIsNone(physics.parse_temperature({"zT_value": "0.9"}))


# ---------------------------------------------------------------- 物理引擎
class TestPhysicsEngine(unittest.TestCase):
    def test_wiedemann_franz_split_degenerate(self):
        # 简并极限:S→0 时 L = 2.44e-8;sigma=1e5 S/m, T=300K → kappa_e = 0.732 W/mK
        self.assertAlmostEqual(physics.lorenz_from_seebeck(0.0), 2.44e-8, places=11)
        self.assertAlmostEqual(physics.lorenz_from_seebeck(None), 2.44e-8, places=11)
        # |S|=10µV/K 时接近简并极限(插值连续)
        self.assertAlmostEqual(physics.lorenz_from_seebeck(10e-6), 2.44e-8, delta=0.05e-8)
        kappa_e = 2.44e-8 * 1e5 * 300
        self.assertAlmostEqual(kappa_e, 0.732, places=3)

    def test_lorenz_decreases_with_seebeck(self):
        lo = physics.lorenz_from_seebeck(10e-6)
        mid = physics.lorenz_from_seebeck(150e-6)
        hi = physics.lorenz_from_seebeck(400e-6)
        self.assertGreater(lo, mid)
        self.assertGreaterEqual(mid, hi)
        self.assertAlmostEqual(hi, 1.55e-8, places=11)

    def test_zT_consistency_clean_numbers(self):
        # S=200e-6, sigma=1e5, T=300, kappa=1.5 → zT_calc = 0.8
        zt = physics.zT_from_components(200e-6, 1e5, 300.0, 1.5)
        self.assertAlmostEqual(zt, 0.8, places=6)

    def test_audit_flags_zT_mismatch(self):
        rec = {"title": "t", "doi": "10.1/x", "material_system": "Bi2Te3",
               "seebeck_coefficient": "200 uV/K", "electrical_conductivity": "1e5 S/m",
               "thermal_conductivity": "1.5 W/mK", "zT_value": "2.5"}
        a = physics.audit_record(rec)
        self.assertAlmostEqual(a["zT_calc"], 0.8, places=5)
        self.assertTrue(any("zT不一致" in f for f in a["flags"]))
        self.assertEqual(a["missing"], [])

    def test_audit_flags_kappa_l_negative(self):
        # 高电导 + 高 Lorenz → kappa_e 超过 kappa_tot
        rec = {"seebeck_coefficient": "10 uV/K", "electrical_conductivity": "5e6 S/m",
               "thermal_conductivity": "0.5 W/mK", "zT_value": "0.3",
               "material_system": "BiSb", "doi": "d", "title": "t"}
        a = physics.audit_record(rec)
        self.assertTrue(any("kappa_l" in f for f in a["flags"]))

    def test_audit_collects_missing(self):
        rec = {"seebeck_coefficient": None, "electrical_conductivity": "1200 S/cm",
               "thermal_conductivity": None, "zT_value": "0.8",
               "material_system": "PbTe", "doi": "d", "title": "t"}
        a = physics.audit_record(rec)
        self.assertIn("seebeck_coefficient", a["missing"])
        self.assertIn("thermal_conductivity", a["missing"])
        self.assertNotIn("electrical_conductivity", a["missing"])

    def test_audit_table_renders(self):
        audits = physics.audit_records([
            {"seebeck_coefficient": "-180 uV/K", "electrical_conductivity": "1000 S/cm",
             "thermal_conductivity": "1.3 W/mK", "zT_value": "0.9 @ 350 K",
             "material_system": "Bi2Te3", "doi": "10.1/a", "title": "A"},
            {"title": "B", "doi": "10.1/b", "error": "boom"},
        ])
        table = physics.build_audit_table_md(audits)
        self.assertIn("Bi2Te3", table)
        self.assertIn("10.1/a", table)
        self.assertIn("抽取失败", table)

    def test_aggregate_missing_sorted(self):
        audits = [{"missing": ["seebeck_coefficient"]},
                  {"missing": ["seebeck_coefficient", "zT_value"]}]
        gaps = physics.aggregate_missing(audits)
        self.assertEqual(list(gaps.items())[0], ("seebeck_coefficient", 2))


if __name__ == "__main__":
    unittest.main()
