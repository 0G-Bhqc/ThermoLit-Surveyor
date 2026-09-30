"""离线端到端图测试:monkeypatch LLM 与检索适配器,验证 LangGraph 全流程连通。

不需要任何 API key;需要 langgraph/langchain-openai(核心依赖)。
在线真实 API 集成测试见本文件末尾(仅在配置 SCIVERSE_TOKEN 时运行)。
"""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from thermolit import physics
from thermolit.hypothesis import evaluate_hypotheses


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    """按提示词特征返回预置内容的假 LLM。"""

    def __init__(self, extraction_outputs):
        self.extraction_outputs = list(extraction_outputs)
        self.calls = []

    def invoke(self, messages):
        prompt = messages[0].content
        self.calls.append(prompt[:60])
        if "Extract thermoelectric transport parameters" in prompt:
            return FakeMessage(self.extraction_outputs.pop(0))
        if "Design the experiment plan" in prompt:
            return FakeMessage(json.dumps({
                "summary": "doping series + full transport characterization",
                "samples": ["Bi2Te3 x=0.01", "Bi2Te3 x=0.03"],
                "measurements": [
                    {"target_var": "zT", "technique": "Seebeck/4-probe + laser flash",
                     "T_range_K": [300, 500]},
                    {"target_var": "dream_var", "technique": "bogus"}],
                "hypothesis_refs": ["H1", "H9"],
            }))
        if "Generate exactly 5 falsifiable hypotheses" in prompt:
            return FakeMessage(json.dumps([{
                "statement": "zT >= 1.0 at 350 K via nanostructure-induced kappa_l reduction",
                "criteria": [{"var": "zT", "op": ">=", "value": 1.0, "T_K": 350},
                             {"var": "magic_var", "op": "<", "value": 1}],
                "evidence_dois": ["10.99/fake11", "10.9999/bogus"],
                "rationale": "boundary scattering reduces kappa_l",
            }]))
        if "targeted academic search queries" in prompt:
            return FakeMessage('["Bi2Te3 Seebeck coefficient Hall measurement",'
                               '"Bi2Te3 lattice thermal conductivity boundary scattering"]')
        return FakeMessage("# 合成报告\n正文(由离线测试生成)。")


class FakeAdapter:
    def __init__(self):
        self.queries = []

    def search_sync(self, query, top_k=3):
        self.queries.append(("sync", query))
        return self._hits(query, 1)

    async def semantic_search_async(self, query, top_k=3):
        self.queries.append(("async", query))
        return self._hits(query, 2)

    def _hits(self, query, pass_num):
        return [{
            "title": f"Paper {pass_num}-{len(self.queries)}",
            "doi": f"10.99/fake{pass_num}{len(self.queries)}",
            "text": "The sample shows zT = 0.9 @ 350 K with S = -180 uV/K, "
                    "sigma = 1200 S/cm, kappa = 1.3 W/mK.",
            "query_source": query,
            "source_pass": pass_num,
        }]


class TestGraphOffline(unittest.TestCase):
    """不需要任何 API key 的全流程连通性测试。"""

    def _run(self):
        from thermolit import graph as proto

        fake_llm = FakeLLM([
            json.dumps({"material_system": "Bi2Te3", "zT_value": "0.9 @ 350 K",
                        "seebeck_coefficient": "-180 uV/K",
                        "electrical_conductivity": "1200 S/cm",
                        "thermal_conductivity": "1.3 W/mK",
                        "carrier_concentration": None, "mobility": None,
                        "temperature_k": 350, "key_claim": "decoupled transport"}),
            json.dumps({"material_system": "Bi2Te3", "zT_value": "1.1 @ 400 K",
                        "seebeck_coefficient": "-210 uV/K",
                        "electrical_conductivity": "900 S/cm",
                        "thermal_conductivity": "1.1 W/mK",
                        "carrier_concentration": "3e19 cm-3", "mobility": None,
                        "temperature_k": 400, "key_claim": "reduced kappa_l"}),
            json.dumps({"material_system": "Bi2Te3", "zT_value": "0.95 @ 350 K",
                        "seebeck_coefficient": "-190 uV/K",
                        "electrical_conductivity": "1100 S/cm",
                        "thermal_conductivity": "1.2 W/mK",
                        "carrier_concentration": None, "mobility": "350 cm2/Vs",
                        "temperature_k": 350, "key_claim": "nanostructured"}),
        ])
        fake_adapter = FakeAdapter()
        with patch.object(proto, "_make_llm", return_value=fake_llm), \
             patch.object(proto, "get_adapter", return_value=fake_adapter):
            return proto.run_agent("Bi2Te3 thermoelectric zT decoupling",
                                   top_k=1, num_followup=2, check_dois=False)

    def test_end_to_end(self):
        try:
            from thermolit import graph as proto  # noqa: F401
        except Exception as e:  # langgraph 等不可用时跳过
            self.skipTest(f"graph deps unavailable: {e}")
        state = self._run()
        # 全流程产物齐备
        self.assertGreaterEqual(len(state["all_records"]), 2)
        self.assertGreaterEqual(len(state["all_papers"]), 2)
        self.assertEqual(len(state["followup_queries"]), 2)
        self.assertIn("Physics Audit Table", state["deep_gap_report"])
        # 物理审计真实发生(数值来自 fake 文献:S=-180uV/K, sigma=1200 S/cm, kappa=1.3, T=350)
        first = state["pass2_audit"][0]
        # 手算:zT_calc = (1.8e-4)^2 * 1.2e5 * 350 / 1.3 ≈ 1.047
        self.assertAlmostEqual(first["zT_calc"], 1.0468, places=3)
        # kappa_e/kappa_l 用引擎自身的 Lorenz 插值验证流水线衔接
        expected_ke = physics.lorenz_from_seebeck(-1.8e-4) * 1.2e5 * 350
        self.assertAlmostEqual(first["kappa_e"], expected_ke, places=6)
        self.assertAlmostEqual(first["kappa_l"], 1.3 - expected_ke, places=6)
        # 材料体系来自抽取结果而非硬编码
        self.assertEqual(state["material_system"], "Bi2Te3")
        # Pass 2 查询包含材料体系(来自抽取投票,而非硬编码)
        self.assertTrue(all("Bi2Te3" in q for q in state["followup_queries"]))
        # ---- 研究闭环:结构化假说(代码归一校验)----
        hyps = state["hypotheses"]
        self.assertEqual(len(hyps), 1)
        self.assertEqual(hyps[0]["id"], "H1")
        # 未知变量判据被确定性剔除,只留合法判据
        self.assertEqual(len(hyps[0]["criteria"]), 1)
        self.assertEqual(hyps[0]["criteria"][0]["var"], "zT")
        self.assertTrue(any("magic_var" in w for w in state["hypothesis_warnings"]))
        # 引用审计表之外 DOI 被标记
        self.assertEqual(hyps[0]["unverified_dois"], ["10.9999/bogus"])
        # ---- 研究闭环:实验方案(代码校验引用与测量目标)----
        plan = state["experiment_plan"]
        self.assertEqual([m["target_var"] for m in plan["measurements"]], ["zT"])
        self.assertEqual(plan["hypothesis_refs"], ["H1"])
        self.assertTrue(any("H9" in w for w in state["experiment_warnings"]))
        # 报告头部提示可用 --verify 回验
        self.assertIn("thermolit --verify", state["deep_gap_report"])
        # ---- v0.4.0 可靠性设施 ----
        # token 计量:metrics 含 llm_usage 四键(FakeLLM 无 usage_metadata,请求数仍计数
        # 与否取决于代理是否在位——此处只验证结构)
        usage = state["metrics"]["llm_usage"]
        for key in ("input_tokens", "output_tokens", "total_tokens", "requests"):
            self.assertIn(key, usage)
        # Pydantic 契约:记录带证据引用字段(即使为空)
        self.assertIn("evidence_sentences", state["all_records"][0])
        # DOI 校验被显式跳过
        self.assertTrue(state["doi_check"].get("skipped"))
        # ---- 闭环出口:实验值回验(SI 测量值 → 代码判定 supported)----
        evals = evaluate_hypotheses(hyps, {"S": -1.8e-4, "sigma": 1.2e5,
                                           "kappa": 1.3, "T_K": 350})
        self.assertEqual(evals[0]["status"], "supported")  # zT_calc=1.047 >= 1.0 @350K


# ---------------------------------------------------------------- 在线集成测试(可选)
@unittest.skipUnless(
    os.getenv("SCIVERSE_TOKEN") and not os.getenv("SCIVERSE_TOKEN", "").startswith("YOUR_"),
    "SCIVERSE_TOKEN 未配置,跳过真实 API 集成测试")
class TestSciverseIntegration(unittest.TestCase):
    def test_real_search(self):
        from thermolit.adapter import SciverseAdapter
        results = SciverseAdapter().search_sync("Bi2Te3 thermoelectric", top_k=2)
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0, "真实 API 应返回命中")
        self.assertIn("title", results[0])
        self.assertIn("doi", results[0])


if __name__ == "__main__":
    unittest.main()
