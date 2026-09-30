import argparse
import json
import logging
import sys
from pathlib import Path

from thermolit.config import LOG_LEVEL, NUM_FOLLOWUP_QUERIES, SEARCH_TOP_K
from thermolit.graph import run_agent
from thermolit.hypothesis import evaluate_hypotheses, missing_to_gap_queries
from thermolit.profiles.thermoelectric import THERMOELECTRIC_PROFILE

PROFILES = {"thermoelectric": THERMOELECTRIC_PROFILE}


def _run_verify(args) -> int:
    """回验模式:实验测量值(SI)+ 假说 → 程序化判定,缺失变量回流为调研缺口。"""
    with open(args.verify, encoding="utf-8") as f:
        results = json.load(f)
    measurements = results.get("measurements", results)

    hyp_path = args.hypotheses or args.output_json
    with open(hyp_path, encoding="utf-8") as f:
        hyp_data = json.load(f)
    hypotheses = hyp_data.get("hypotheses", hyp_data) if isinstance(hyp_data, dict) else hyp_data
    if not isinstance(hypotheses, list) or not hypotheses:
        print(f"[verify] {hyp_path} 中没有结构化假说,请先运行一次调研", file=sys.stderr)
        return 2

    evaluations = evaluate_hypotheses(hypotheses, measurements)
    print(f"[verify] 对 {len(hypotheses)} 条假说回验完成(变量由代码判定):")
    for ev in evaluations:
        crit = "; ".join(f"{r['var']}={r['measured']:.4g} {r['op']} {r['threshold']}"
                         f"→{'✓' if r['pass'] else '✗'}" for r in ev["criteria_results"])
        print(f"  {ev['id']} [{ev['status']}] {ev['statement'][:60]}")
        if crit:
            print(f"        判据: {crit}")
        if ev["missing"]:
            print(f"        缺失: {ev['missing']}")

    gaps = missing_to_gap_queries(evaluations, PROFILES[args.profile].gap_query_hints)
    if gaps:
        print(f"\n[verify] 缺失变量回流为下一轮调研缺口,建议查询: {gaps}")

    # 回验报告独立落盘,避免覆盖调研输出(假说来源文件)
    out_path = f"{Path(args.verify).stem}_verification.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"evaluations": evaluations,
                   "next_gap_queries": gaps,
                   "measurements": measurements}, f, ensure_ascii=False, indent=2)
    print(f"[verify] 回验报告已写入 {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="thermolit",
        description="ThermoLit-Surveyor: 2-Pass 缺口驱动、物理约束的文献调研与研究闭环智能体框架")
    parser.add_argument("--query", type=str,
                        default="Bi2Te3 thermoelectric figure of merit zT Seebeck conductivity",
                        help="初始检索查询(决定调研的对象/材料体系)")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="thermoelectric",
                        help="领域 profile(决定抽取 schema 与物理审计引擎)")
    parser.add_argument("--output_report", type=str, default="deepresearch_multihop_report.md",
                        help="Markdown 调研报告输出路径")
    parser.add_argument("--output_json", type=str, default="deepresearch_all_records.json",
                        help="结构化 JSON(抽取记录+物理审计+假说+实验方案+指标)输出路径")
    parser.add_argument("--top_k", type=int, default=SEARCH_TOP_K,
                        help="每轮检索返回的段落数")
    parser.add_argument("--followup", type=int, default=NUM_FOLLOWUP_QUERIES,
                        help="Pass 2 生成的新查询数")
    parser.add_argument("--verify", type=str, default=None, metavar="RESULTS.json",
                        help="回验模式:传入实验测量值 JSON {\"measurements\": {...SI 值...}},"
                             "对已有假说做程序化判定(不执行调研)")
    parser.add_argument("--hypotheses", type=str, default=None, metavar="HYP.json",
                        help="回验模式使用的假说文件(默认取 --output_json,即调研输出)")
    parser.add_argument("--no-doi-check", action="store_true",
                        help="跳过 DOI 注册库核验(默认开启,访问 doi.org)")
    parser.add_argument("--checkpoint", type=str, default=None, metavar="PATH.db",
                        help="启用 SqliteSaver 断点续跑(需 pip install '.[checkpoint]')")
    parser.add_argument("--export_docx", type=str, default=None, metavar="OUT.docx",
                        help="同时导出 docx 版报告(需 pip install '.[export]')")
    parser.add_argument("--log_level", type=str, default=LOG_LEVEL)
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(message)s")

    if args.verify:
        return _run_verify(args)

    print(f"[ThermoLit-Surveyor] 开始调研: '{args.query}' "
          f"(profile={args.profile}, top_k={args.top_k}, followup={args.followup}, "
          f"doi_check={not args.no_doi_check})")
    state = run_agent(args.query, profile=PROFILES[args.profile],
                      top_k=args.top_k, num_followup=args.followup,
                      check_dois=not args.no_doi_check,
                      checkpoint_path=args.checkpoint)

    metrics = state.get("metrics", {})
    duration = metrics.get("total_pipeline_duration", 0)
    papers = metrics.get("total_papers_analyzed", len(state.get("all_papers", [])))
    records = metrics.get("total_records_audited", len(state.get("all_records", [])))
    print(f"\n[ThermoLit-Surveyor] 流水线完成,耗时 {duration:.2f} 秒")
    print(f"[ThermoLit-Surveyor] 证据文献 {papers} 篇,结构化+审计记录 {records} 条")

    if not state.get("all_records"):
        print("[ThermoLit-Surveyor] 警告: 未获得任何结构化记录,请检查 SCIVERSE_TOKEN 与网络。",
              file=sys.stderr)
        return 1

    with open(args.output_report, "w", encoding="utf-8") as f:
        f.write(state.get("deep_gap_report", ""))
    print(f"[Output] Markdown 报告: {args.output_report}")

    if args.export_docx:
        from thermolit.export import report_to_docx
        path = report_to_docx(state.get("deep_gap_report", ""), args.export_docx,
                              title=f"{state.get('material_system', '')} 调研报告")
        print(f"[Output] docx 报告: {path}")

    doi_check = state.get("doi_check", {})
    if doi_check.get("missing"):
        print(f"[DOI] 警告:{len(doi_check['missing'])} 个 DOI 在注册库中不存在,"
              "详见输出 JSON 的 doi_check 字段", file=sys.stderr)

    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump({
            "profile": args.profile,
            "material_system": state.get("material_system"),
            "all_records": state.get("all_records", []),
            "physics_audit": state.get("pass2_audit", []),
            "audit_table_md": state.get("audit_table_md", ""),
            "followup_queries": state.get("followup_queries", []),
            "hypotheses": state.get("hypotheses", []),
            "hypothesis_warnings": state.get("hypothesis_warnings", []),
            "experiment_plan": state.get("experiment_plan", {}),
            "experiment_warnings": state.get("experiment_warnings", []),
            "doi_check": doi_check,
            "doi_warnings": state.get("doi_warnings", []),
            "error_records": state.get("error_records", []),
            "metrics": metrics,
        }, f, ensure_ascii=False, indent=2)
    print(f"[Output] 结构化 JSON(含物理审计): {args.output_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
