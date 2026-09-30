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


class TestCrossrefResolution(unittest.TestCase):
    """Crossref 标题→DOI 解析(真实命中无 DOI 字段的锚点修复)。"""

    def _mock(self, status=200, doi="10.1000/real", title="Key Properties of Inorganic Thermoelectric Materials"):
        m = MagicMock()
        m.status_code = status
        m.json.return_value = {"message": {"items": [{"DOI": doi, "title": [title]}]}}
        return m

    @patch("requests.get")
    def test_similar_title_resolved(self, mock_get):
        from thermolit.adapter import resolve_doi_by_title
        mock_get.return_value = self._mock()
        out = resolve_doi_by_title("key properties of inorganic thermoelectric materials tables")
        self.assertEqual(out, "10.1000/real")

    @patch("requests.get")
    def test_dissimilar_title_rejected(self, mock_get):
        from thermolit.adapter import resolve_doi_by_title
        mock_get.return_value = self._mock(title="Completely Unrelated Paper About Biology")
        self.assertIsNone(resolve_doi_by_title("PbTe thermoelectric transport"))

    @patch("requests.get")
    def test_http_error_returns_none(self, mock_get):
        from thermolit.adapter import resolve_doi_by_title
        mock_get.return_value = self._mock(status=500)
        self.assertIsNone(resolve_doi_by_title("some title"))

    @patch("requests.get", side_effect=doi_mod.requests.ConnectionError())
    def test_network_error_returns_none(self, mock_get):
        from thermolit.adapter import resolve_doi_by_title
        self.assertIsNone(resolve_doi_by_title("some title"))

    def test_empty_title_short_circuit(self):
        from thermolit.adapter import resolve_doi_by_title
        self.assertIsNone(resolve_doi_by_title(""))

    def test_sanitize_title_strips_mathml(self):
        # 真实校准发现:APS/Sciverse 标题含 MathML,污染 Crossref 搜索与展示
        from thermolit.adapter import sanitize_title
        dirty = ("valence-band structure of highly efficient<mml:math xmlns:mml="
                 '"http://www.w3.org/1998/Math/MathML"><mml:mrow>p-type</mml:mrow'
                 "></mml:math> thermoelectric pbte")
        clean = sanitize_title(dirty)
        self.assertNotIn("<", clean)
        self.assertIn("p-type thermoelectric pbte", clean)

    def test_sanitize_title_unescapes_entities(self):
        from thermolit.adapter import sanitize_title
        self.assertEqual(sanitize_title("p-type (bi&lt;sub&gt;2&lt;/sub&gt;te&lt;sub&gt;3"),
                         "p-type (bi2te3")


if __name__ == "__main__":
    unittest.main()
