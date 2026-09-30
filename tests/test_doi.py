"""DOI 注册库校验测试(mock HTTP,离线可跑)。"""
import unittest
from unittest.mock import MagicMock, patch

from thermolit import doi as doi_mod


class TestExtractDois(unittest.TestCase):
    def test_filters_placeholders_and_invalid(self):
        records = [{"doi": "10.1000/a"}, {"doi": "N/A"}, {"doi": ""},
                   {"doi": "https://doi.org/10.2000/B"}, {"doi": "not-a-doi"}]
        self.assertEqual(doi_mod.extract_dois(records),
                         ["10.1000/a", "10.2000/b"])

    def test_collects_hypothesis_evidence(self):
        hyps = [{"evidence_dois": ["10.1000/a", "bogus"]}]
        self.assertEqual(doi_mod.extract_dois([], hyps), ["10.1000/a"])

    def test_dedup_preserves_order(self):
        records = [{"doi": "10.1000/a"}, {"doi": "10.1000/A"},
                   {"doi": "10.1000/b"}]
        self.assertEqual(doi_mod.extract_dois(records),
                         ["10.1000/a", "10.1000/b"])


class TestCheckDois(unittest.TestCase):
    def _resp(self, status, payload=None):
        m = MagicMock()
        m.status_code = status
        m.content = b"{}" if payload is not None else b""
        if payload is not None:
            m.json.return_value = payload
        return m

    @patch("thermolit.doi.requests.get")
    def test_ok_when_handle_exists(self, mock_get):
        mock_get.return_value = self._resp(200, {"responseCode": 1})
        out = doi_mod.check_dois(["10.1000/real"])
        self.assertEqual(out["10.1000/real"]["status"], "ok")

    @patch("thermolit.doi.requests.get")
    def test_missing_on_404(self, mock_get):
        mock_get.return_value = self._resp(404)
        self.assertEqual(
            doi_mod.check_dois(["10.1000/fake"])["10.1000/fake"]["status"],
            "missing")

    @patch("thermolit.doi.requests.get")
    def test_missing_on_response_code_100(self, mock_get):
        mock_get.return_value = self._resp(200, {"responseCode": 100})
        self.assertEqual(
            doi_mod.check_dois(["10.1000/fake"])["10.1000/fake"]["status"],
            "missing")

    @patch("thermolit.doi.requests.get", side_effect=doi_mod.requests.Timeout())
    def test_network_error_unknown(self, mock_get):
        self.assertEqual(
            doi_mod.check_dois(["10.1000/x"])["10.1000/x"]["status"], "unknown")

    @patch("thermolit.doi.requests.get")
    def test_max_check_truncates(self, mock_get):
        mock_get.return_value = self._resp(200, {"responseCode": 1})
        out = doi_mod.check_dois(["10.1000/a", "10.1000/b", "10.1000/c"],
                                 max_check=2)
        self.assertEqual(len(out), 2)

    def test_summarize_groups(self):
        summary = doi_mod.summarize({"10.1/a": {"status": "ok"},
                                     "10.1/b": {"status": "missing"}})
        self.assertEqual(summary["ok"], ["10.1/a"])
        self.assertEqual(summary["missing"], ["10.1/b"])
        self.assertEqual(summary["unknown"], [])


if __name__ == "__main__":
    unittest.main()
