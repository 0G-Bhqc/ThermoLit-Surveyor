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


if __name__ == "__main__":
    unittest.main()
