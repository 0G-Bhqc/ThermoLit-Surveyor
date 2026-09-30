#!/usr/bin/env python
"""
real_model_smoke.py — 真实模型端到端烟雾测试(无需 Sciverse token)。

用固定热电语料(fixture adapter)替代检索端,完整跑通 10 节点图,
验证提示词模板 → LLM → JSON 解析 → 物理审计 → 假说归一 → 实验方案 → 报告合成全链路。

两种模式:
  --live                用 .env 里的真实 LLM 端点(需要可用余额;检索端仍为 fixture)
  --replay DIR(默认)  回放 eval/replay_fixtures/ 中预置的模型级输出(离线可跑,
                        同时是一份"金标准示例":展示每一步 LLM 应当输出什么)

用法:
  python eval/real_model_smoke.py                 # 回放模式
  python eval/real_model_smoke.py --live          # 真实 LLM
产物写入 eval/results/real_model_smoke/。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

FIXTURES = [
    {"query_hint": None, "paper": {
        "title": "Nanostructured Bi0.3Sb1.7Te3 by spark plasma sintering [SMOKE FIXTURE]",
        "doi": "10.0000/smoke.001",
        "text": "Spark-plasma-sintered nanostructured Bi0.3Sb1.7Te3 alloys exhibit a peak "
                "zT of 1.2 @ 350 K, with a Seebeck coefficient of -240 uV/K, an electrical "
                "conductivity of 850 S/cm, and a total thermal conductivity of 1.05 W/mK "
                "at 350 K. Hall measurements give a carrier concentration of 3.2e19 cm-3.",
    }},
    {"query_hint": None, "paper": {
        "title": "Na-doped PbTe single crystals: p-type transport [SMOKE FIXTURE]",
        "doi": "10.0000/smoke.002",
        "text": "Na-doped PbTe single crystals show p-type transport with a Seebeck "
                "coefficient of +180 uV/K and electrical conductivity of 1200 S/cm at "
                "300 K, a total thermal conductivity of 1.6 W/mK; zT reaches 1.4 @ 750 K "
                "with a carrier concentration of 2.5e19 cm-3.",
    }},
    {"query_hint": None, "paper": {
        "title": "Ultralow kappa_l in layered SnSe along the b axis [SMOKE FIXTURE]",
        "doi": "10.0000/smoke.003",
        "text": "Layered SnSe single crystals along the b axis show an intrinsically "
                "ultralow lattice thermal conductivity of 0.23 W/mK at 973 K arising from "
                "anharmonic phonon scattering; a hole mobility of 120 cm2/Vs is measured "
                "at 300 K.",
    }},
    {"query_hint": "SnSe", "paper": {
        "title": "High-temperature transport of SnSe along the b axis [SMOKE FIXTURE]",
        "doi": "10.0000/smoke.004",
        "text": "High-temperature thermoelectric properties of SnSe crystals along the b "
                "axis: the Seebeck coefficient is +450 uV/K @ 300 K, while the electrical "
                "conductivity remains as low as 0.09 S/cm at room temperature; a zT of "
                "2.6 @ 923 K is obtained.",
    }},
    {"query_hint": "melt-spun", "paper": {
        "title": "Melt-spun Bi2Te3 ribbons annealed at 753 K [SMOKE FIXTURE]",
        "doi": "10.0000/smoke.005",
        "text": "Melt-spun Bi2Te3 ribbons annealed at 753 K show zT = 0.95 @ 350 K with "
                "S = -190 uV/K, sigma = 1100 S/cm and kappa = 1.2 W/mK.",
    }},
]

INITIAL_QUERY = "Bi2Te3-based thermoelectric transport decoupling zT Seebeck kappa"


class FixtureAdapter:
    """检索替身:Pass 1 返回前三篇,Pass 2 按查询关键词匹配。"""

    def search_sync(self, query, top_k=3):
        return [self._tag(p["paper"], 1) for p in FIXTURES if p["query_hint"] is None]

    async def semantic_search_async(self, query, top_k=3):
        hits = [self._tag(p["paper"], 2) for p in FIXTURES
                if p["query_hint"] and p["query_hint"].lower() in query.lower()]
        return hits or [self._tag(FIXTURES[4]["paper"], 2)]

    @staticmethod
    def _tag(paper, source_pass):
        return {**paper, "query_source": "fixture", "source_pass": source_pass}


class ReplayLLM:
    """按 eval/replay_fixtures/ 中的文件回放模型输出(与图内调用顺序一一对应)。"""

    def __init__(self, replay_dir: Path):
        self.extractions = [p for p in sorted(replay_dir.glob("extract_*.json"))]
        self.dir = replay_dir
        self._extract_i = 0

    def invoke(self, messages):
        prompt = messages[0].content
        if "Extract thermoelectric transport parameters" in prompt:
            path = self.extractions[self._extract_i]
            self._extract_i += 1
            return _msg(path.read_text(encoding="utf-8"))
        if "Design the experiment plan" in prompt:
            return _msg((self.dir / "plan.json").read_text(encoding="utf-8"))
        if "Generate exactly 5 falsifiable hypotheses" in prompt:
            return _msg((self.dir / "hypotheses.json").read_text(encoding="utf-8"))
        if "targeted academic search queries" in prompt:
            return _msg((self.dir / "refine.json").read_text(encoding="utf-8"))
        return _msg((self.dir / "report.md").read_text(encoding="utf-8"))


def _msg(content: str):
    class _M:
        pass
    m = _M()
    m.content = content
    return m


def main() -> int:
    ap = argparse.ArgumentParser(description="real-model smoke test")
    ap.add_argument("--live", action="store_true", help="用 .env 的真实 LLM(需可用余额)")
    ap.add_argument("--replay_dir", type=Path,
                    default=REPO / "eval" / "replay_fixtures")
    ap.add_argument("--out", type=Path,
                    default=REPO / "eval" / "results" / "real_model_smoke")
    args = ap.parse_args()

    from thermolit import graph as proto
    from thermolit.profiles.thermoelectric import THERMOELECTRIC_PROFILE

    out: dict = {}
    if args.live:
        # LIVE:不 patch _make_llm——让 tracker/cache 包装链真实生效(token 计量可用)
        print(f"[smoke] LIVE 模式:{LLM_MODEL_NAME()} @ {LLM_BASE_NAME()}")
        with _patch(proto, "get_adapter", lambda: FixtureAdapter()):
            state = proto.run_agent(INITIAL_QUERY, profile=THERMOELECTRIC_PROFILE,
                                    top_k=3, num_followup=2, check_dois=False)
    else:
        llm = ReplayLLM(args.replay_dir)
        print(f"[smoke] REPLAY 模式:{len(llm.extractions)} 份抽取回放 @ {args.replay_dir}")
        with _patch(proto, "_make_llm", lambda: llm), \
             _patch(proto, "get_adapter", lambda: FixtureAdapter()):
            state = proto.run_agent(INITIAL_QUERY, profile=THERMOELECTRIC_PROFILE,
                                    top_k=3, num_followup=2, check_dois=False)

    out["material_system"] = state["material_system"]
    out["all_records"] = state["all_records"]
    out["physics_audit"] = state["pass2_audit"]
    out["audit_table_md"] = state["audit_table_md"]
    out["followup_queries"] = state["followup_queries"]
    out["hypotheses"] = state["hypotheses"]
    out["hypothesis_warnings"] = state["hypothesis_warnings"]
    out["experiment_plan"] = state["experiment_plan"]
    out["experiment_warnings"] = state["experiment_warnings"]
    out["doi_check"] = state.get("doi_check", {})
    out["error_records"] = state["error_records"]
    out["metrics"] = state["metrics"]

    args.out.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now(timezone.utc):%Y%m%d_%H%M%S}"
    (args.out / f"smoke_{stamp}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "report.md").write_text(state["deep_gap_report"], encoding="utf-8")
    (args.out / "audit_table.md").write_text(state["audit_table_md"], encoding="utf-8")

    print(f"\n[smoke] 材料: {out['material_system']}")
    print(f"[smoke] 记录: {len(out['all_records'])} 条 | 审计标记 "
          f"{sum(1 for a in out['physics_audit'] if a.get('flags'))} 条 | "
          f"缺口 {state['metrics'].get('pass1_gaps')}")
    print(f"[smoke] 假说: {len(out['hypotheses'])} 条 "
          f"(警告 {len(out['hypothesis_warnings'])})")
    print(f"[smoke] 实验方案: {len(out['experiment_plan'].get('measurements', []))} 次测量 "
          f"(警告 {len(out['experiment_warnings'])})")
    print(f"[smoke] 产物: {args.out}/(smoke_{stamp}.json, report.md, audit_table.md)")

    # 基本断言:任何一步结构性失败都应在这里暴露
    assert out["all_records"], "无结构化记录"
    assert out["hypotheses"], "无有效假说"
    assert out["experiment_plan"].get("measurements"), "实验方案无有效测量"
    assert len(state["deep_gap_report"]) > 500, "报告过短"
    print("[smoke] PASS")
    return 0


class _patch:
    def __init__(self, obj, name, value):
        self.obj, self.name, self.value = obj, name, value

    def __enter__(self):
        self.old = getattr(self.obj, self.name)
        setattr(self.obj, self.name, self.value)

    def __exit__(self, *exc):
        setattr(self.obj, self.name, self.old)


def LLM_MODEL_NAME():
    from thermolit.config import LLM_MODEL
    return LLM_MODEL


def LLM_BASE_NAME():
    from thermolit.config import LLM_BASE_URL
    return LLM_BASE_URL


if __name__ == "__main__":
    sys.exit(main())
