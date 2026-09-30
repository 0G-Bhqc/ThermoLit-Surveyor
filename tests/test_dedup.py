"""去重与 profile 通用行为测试。"""
import unittest

from thermolit.adapter import dedup_papers
from thermolit.profiles.thermoelectric import THERMOELECTRIC_PROFILE


class TestDedup(unittest.TestCase):
    def test_doi_dedup_case_insensitive(self):
        papers = [{"title": "A", "doi": "10.1/x", "text": "1"},
                  {"title": "A again", "doi": "https://doi.org/10.1/X", "text": "2"},
                  {"title": "B", "doi": "10.1/y", "text": "3"}]
        out = dedup_papers(papers)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["doi"], "10.1/x")

    def test_title_dedup_without_doi(self):
        papers = [{"title": "Same Title", "doi": "N/A", "text": "1"},
                  {"title": "same title", "doi": "N/A", "text": "2"}]
        self.assertEqual(len(dedup_papers(papers)), 1)


class TestProfileDefaults(unittest.TestCase):
    def test_audit_records_marks_extraction_failure(self):
        audits = THERMOELECTRIC_PROFILE.audit_records([{"title": "B", "error": "boom"}])
        self.assertEqual(audits[0]["flags"], ["extraction_failed"])

    def test_fallback_queries_driven_by_real_gaps(self):
        qs = THERMOELECTRIC_PROFILE.fallback_queries("PbTe",
                                                     ["seebeck_coefficient"], 2)
        self.assertEqual(qs[0], "PbTe Seebeck coefficient measurement")
        self.assertEqual(len(qs), 2)

    def test_extraction_prompt_is_concatenated_not_formatted(self):
        # 回归:模板含 JSON 大括号,绝不能经过 str.format
        prompt = THERMOELECTRIC_PROFILE.build_extraction_prompt("S = -180 uV/K", 3500)
        self.assertIn('"material_system"', prompt)
        self.assertIn("S = -180 uV/K", prompt)


class TestNumericDensityRank(unittest.TestCase):
    """检索预筛:数值密集段优先(fetch-and-rank)。"""

    DENSE = ("The sample shows zT = 0.9 @ 350 K with S = -180 uV/K, "
             "sigma = 1200 S/cm and kappa = 1.3 W/mK measured at 300 K.")
    REVIEW = ("Thermoelectric materials have attracted attention for energy "
              "harvesting applications in recent decades.")

    def test_density_scores(self):
        from thermolit.adapter import numeric_density_score
        self.assertGreater(numeric_density_score(self.DENSE), 3)
        self.assertEqual(numeric_density_score(self.REVIEW), 0)
        self.assertEqual(numeric_density_score(""), 0)

    def test_fetch_and_rank_prefers_numeric(self):
        from unittest.mock import MagicMock

        from thermolit.adapter import SciverseAdapter

        ad = SciverseAdapter(token="dummy")
        ad._client = MagicMock()
        hits = [{"title": "Review paper", "chunk": self.REVIEW, "doi": "10.1000/r",
                 "abstract": "", "score": 0.99},          # API 分最高但无数值
                {"title": "Data paper", "chunk": self.DENSE, "doi": "10.1000/d",
                 "abstract": "", "score": 0.90}]          # 数值密集
        ad._client.semantic_search.return_value = {"hits": hits}
        out = ad.search_sync("Bi2Te3 zT values", top_k=1)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["doi"], "10.1000/d")     # 数值密集段胜出
        self.assertNotIn("_density", out[0])             # 内部字段不外泄


if __name__ == "__main__":
    unittest.main()
