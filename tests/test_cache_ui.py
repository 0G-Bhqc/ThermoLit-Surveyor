"""结果缓存与 Gradio 界面格式化的离线测试。"""
import unittest
from unittest.mock import MagicMock, patch

from thermolit.cache import ResultCache, _CachedLLM, get_global_cache
from thermolit.ui import format_state


class TestResultCache(unittest.TestCase):
    def test_roundtrip_and_miss(self):
        c = ResultCache("eval/results/test_cache.db")
        self.assertIsNone(c.get("llm", {"p": 1}))
        c.set("llm", {"p": 1}, {"content": "hello"})
        self.assertEqual(c.get("llm", {"p": 1}), {"content": "hello"})
        self.assertEqual(c.clear(), 1)
        self.assertIsNone(c.get("llm", {"p": 1}))

    def test_key_is_payload_normalized(self):
        # json.dumps(sort_keys=True):键序不影响命中
        self.assertEqual(ResultCache.make_key("llm", {"a": 1, "b": 2}),
                         ResultCache.make_key("llm", {"b": 2, "a": 1}))


class _Msg:
    def __init__(self, content):
        self.content = content


class _Inner:
    def __init__(self):
        self.calls = 0

    def invoke(self, messages, **kwargs):
        self.calls += 1
        return _Msg(f"resp-{self.calls}")


class TestCachedLLM(unittest.TestCase):
    def test_miss_then_hit(self):
        cache = ResultCache("eval/results/test_cachedllm.db")
        cache.clear()
        inner = _Inner()
        stats = {"llm_cache_hits": 0, "llm_cache_misses": 0}
        llm = _CachedLLM(inner, cache, "test-model", stats)

        first = llm.invoke([_Msg("same prompt")])
        second = llm.invoke([_Msg("same prompt")])
        self.assertEqual(inner.calls, 1)          # 第二次命中缓存,不再调用
        self.assertEqual(first.content, second.content)
        self.assertEqual(stats, {"llm_cache_hits": 1, "llm_cache_misses": 1})

    def test_different_prompt_misses(self):
        cache = ResultCache("eval/results/test_cachedllm.db")
        cache.clear()
        inner = _Inner()
        llm = _CachedLLM(inner, cache, "test-model")
        llm.invoke([_Msg("prompt A")])
        llm.invoke([_Msg("prompt B")])
        self.assertEqual(inner.calls, 2)


class TestGlobalCache(unittest.TestCase):
    def setUp(self):
        import thermolit.cache as cm

        cm._global_cache = None
        cm._global_cache_path = None

    def test_enabled_by_env(self):
        with patch("thermolit.config.THERMOLIT_CACHE",
                   "eval/results/test_global_cache.db"):
            c1 = get_global_cache()
            c2 = get_global_cache()
            self.assertIs(c1, c2)                 # 同路径单例
            self.assertIsInstance(c1, ResultCache)

    def test_disabled_without_env(self):
        with patch("thermolit.config.THERMOLIT_CACHE", ""):
            self.assertIsNone(get_global_cache())


class TestAdapterSearchCache(unittest.TestCase):
    def test_second_search_hits_cache(self):
        from thermolit.adapter import SciverseAdapter

        ad = SciverseAdapter(token="dummy")
        ad._client = MagicMock()
        ad._client.semantic_search.return_value = {
            "hits": [{"title": "T", "chunk": "c", "doi": "10.1000/x",
                      "abstract": "a"}]}
        cache = ResultCache("eval/results/test_adapter_cache.db")
        cache.clear()
        with patch("thermolit.config.THERMOLIT_CACHE",
                   "eval/results/test_adapter_cache.db"), \
             patch("thermolit.cache._global_cache", cache), \
             patch("thermolit.cache._global_cache_path", None):
            first = ad.search_sync("Bi2Te3 zT", top_k=2)
            second = ad.search_sync("Bi2Te3 zT", top_k=2)
        self.assertEqual(ad._client.semantic_search.call_count, 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(first[0]["doi"], "10.1000/x")


class TestFormatState(unittest.TestCase):
    def test_formats_four_panels(self):
        meta, report, audit, hyp = format_state({
            "material_system": "Bi2Te3",
            "deep_gap_report": "# 报告",
            "audit_table_md": "| 表 |",
            "hypotheses": [{"id": "H1"}],
            "metrics": {"total_records_audited": 5,
                        "llm_usage": {"total_tokens": 42},
                        "llm_cache": {"llm_cache_hits": 3}},
        })
        self.assertIn("Bi2Te3", meta)
        self.assertIn("42", meta)
        self.assertEqual(report, "# 报告")
        self.assertEqual(audit, "| 表 |")
        self.assertIn("H1", hyp)

    def test_empty_state_tolerated(self):
        meta, report, audit, hyp = format_state({})
        self.assertIn("?", meta)
        self.assertIn("无报告", report)
        self.assertIn("无假说", hyp)


if __name__ == "__main__":
    unittest.main()
