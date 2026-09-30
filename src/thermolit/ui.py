"""
ui.py — Gradio 演示界面(可选依赖 ui:pip install 'thermolit-surveyor[ui]')。

启动:python -m thermolit.ui
输入材料查询 → 展示调研报告、《Physics Audit Table》、结构化假说 JSON。

`format_state` 是纯函数(离线单测覆盖);gradio 编排仅在 build_app 中惰性导入。
"""
from __future__ import annotations

import json
from typing import Any, Dict, Tuple


def format_state(state: Dict[str, Any]) -> Tuple[str, str, str, str]:
    """把 run_agent 产物格式化为界面四个面板(纯函数,离线测试覆盖)。"""
    report = state.get("deep_gap_report", "(无报告)")
    audit = state.get("audit_table_md", "(无审计表)")
    hyps = state.get("hypotheses", [])
    hyp_md = json.dumps(hyps, ensure_ascii=False, indent=2) if hyps else "(无假说)"
    metrics = state.get("metrics", {})
    usage = metrics.get("llm_usage", {})
    cache = metrics.get("llm_cache", {})
    meta = (f"材料: {state.get('material_system', '?')} | 记录: "
            f"{metrics.get('total_records_audited', '?')} | tokens: "
            f"{usage.get('total_tokens', 0)} | 缓存命中: {cache.get('llm_cache_hits', 0)}")
    return meta, report, audit, hyp_md


def build_app():
    import gradio as gr

    from thermolit.graph import run_agent
    from thermolit.profiles.thermoelectric import THERMOELECTRIC_PROFILE

    def run(query: str, top_k: int, followup: int):
        state = run_agent(query, profile=THERMOELECTRIC_PROFILE,
                          top_k=int(top_k), num_followup=int(followup),
                          check_dois=False)
        return format_state(state)

    with gr.Blocks(title="ThermoLit-Surveyor") as app:
        gr.Markdown("# ThermoLit-Surveyor — 物理约束研究闭环演示\n"
                    "调研 → 审计 → 假说 → 实验方案;数值全部由程序计算。")
        with gr.Row():
            query = gr.Textbox(
                label="查询", scale=4,
                value="Bi2Te3 thermoelectric figure of merit zT Seebeck conductivity")
            top_k = gr.Number(label="每轮检索条数", value=3, precision=0)
            followup = gr.Number(label="Pass 2 查询数", value=2, precision=0)
        btn = gr.Button("开始调研", variant="primary")
        meta = gr.Markdown()
        with gr.Tabs():
            with gr.Tab("调研报告"):
                report = gr.Markdown()
            with gr.Tab("Physics Audit Table"):
                audit = gr.Markdown()
            with gr.Tab("结构化假说"):
                hyp = gr.Code(language="json")
        btn.click(run, inputs=[query, top_k, followup],
                  outputs=[meta, report, audit, hyp])
    return app


if __name__ == "__main__":
    build_app().launch()
