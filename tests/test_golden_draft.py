"""金标草稿生成器测试。"""
import unittest

from eval.golden_draft import build_draft


class TestGoldenDraft(unittest.TestCase):
    def test_build_draft(self):
        survey = {
            "papers": [{"title": "A Paper", "doi": "10.1000/a",
                        "text": "The sample shows zT = 0.9 @ 350 K with S = -180 uV/K."}],
            "physics_audit": [
                {"title": "A Paper", "doi": "10.1000/a", "material_system": "Bi2Te3",
                 "S_si_V_per_K": -1.8e-4, "sigma_si_S_per_m": 1.2e5,
                 "kappa_si_W_per_mK": 1.3, "zT_reported": 0.9,
                 "flags": [], "missing": []},
                {"title": "Broken", "doi": "10.1000/b", "error": "boom"},
            ],
        }
        drafts = build_draft(survey)
        self.assertEqual(len(drafts), 1)              # 错误记录跳过
        d = drafts[0]
        self.assertTrue(d["source"]["needs_human_review"])
        self.assertIn("zT = 0.9", d["excerpt"])       # excerpt 来自检索段落
        vals = d["expected"]["values"]
        self.assertAlmostEqual(vals["seebeck_coefficient"]["si"], -1.8e-4)
        self.assertEqual(vals["seebeck_coefficient"]["text"], "-180 uV/K")
        self.assertAlmostEqual(vals["electrical_conductivity"]["si"], 1.2e5)
        self.assertEqual(d["expected"]["material_system"], "Bi2Te3")

    def test_missing_excerpt_tolerated(self):
        survey = {"papers": [], "physics_audit": [
            {"title": "X", "doi": "10.1000/x", "material_system": "PbTe",
             "zT_reported": 1.4, "flags": [], "missing": []}]}
        drafts = build_draft(survey)
        self.assertIn("未找到对应检索段落", drafts[0]["excerpt"])
        self.assertIn("zT_value", drafts[0]["expected"]["values"])


if __name__ == "__main__":
    unittest.main()
