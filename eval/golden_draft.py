#!/usr/bin/env python
"""
golden_draft.py — 金标草稿生成器:把真实调研输出转成"待人工核对"的金标 JSONL 草稿。

把标注成本从"查原文 + 手工填写 SI 真值"降为"核对草稿值是否与原文一致":
每条草稿已带 excerpt(检索段落)、程序解析的 SI 值(expected.values.*.si)与
审计标记,人工只需逐条 ✓/✗/改数。

用法:
  python eval/golden_draft.py --survey deepresearch_all_records.json \
      --out eval/golden/my_draft.jsonl
产物中每条 "needs_human_review": true —— 核对完成后请改为 false。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

# audit SI 键 → 金标 values 键
_AUDIT_TO_FIELD = {
    "S_si_V_per_K": "seebeck_coefficient",
    "sigma_si_S_per_m": "electrical_conductivity",
    "kappa_si_W_per_mK": "thermal_conductivity",
    "zT_reported": "zT_value",
}
# 展示文本还原(SI → 常见文献单位),供人工快速核对
_DISPLAY = {
    "seebeck_coefficient": lambda v: f"{v * 1e6:g} uV/K",
    "electrical_conductivity": lambda v: f"{v / 100:g} S/cm",
    "thermal_conductivity": lambda v: f"{v:g} W/mK",
    "zT_value": lambda v: f"{v:g}",
}


def build_draft(survey: dict) -> list[dict]:
    """从调研输出 JSON 生成金标草稿条目列表。"""
    papers = {(str(p.get("doi", "")).lower(), str(p.get("title", "")).lower()): p
              for p in survey.get("papers", [])}
    audits = survey.get("physics_audit") or survey.get("all_records") or []
    drafts = []
    for audit in audits:
        if "error" in audit or audit.get("flags") == ["extraction_failed"]:
            continue
        key = (str(audit.get("doi", "")).lower(), str(audit.get("title", "")).lower())
        paper = papers.get(key) or {}
        excerpt = str(paper.get("text", "")).strip()
        values = {}
        for akey, field in _AUDIT_TO_FIELD.items():
            si = audit.get(akey)
            if si is not None:
                values[field] = {"text": _DISPLAY[field](float(si)), "si": float(si)}
        # 审计里的缺失字段也要进 expected(表示"原文没有",用于考核编造率)吗?
        # 不——草稿只填程序解析出的值,缺失与否由人工对照 excerpt 决定。
        drafts.append({
            "id": f"draft-{len(drafts) + 1:03d}-{str(audit.get('doi', 'NA'))[:20]}",
            "profile": "thermoelectric",
            "excerpt": excerpt or "(未找到对应检索段落,请人工补充)",
            "source": {"title": audit.get("title", ""),
                       "doi": audit.get("doi", "N/A"),
                       "needs_human_review": True},
            "expected": {"material_system": audit.get("material_system"),
                         "values": values},
            "audit_flags_at_draft_time": audit.get("flags", []),
        })
    return drafts


def main() -> int:
    ap = argparse.ArgumentParser(description="金标草稿生成器")
    ap.add_argument("--survey", type=Path, required=True, help="调研输出 JSON")
    ap.add_argument("--out", type=Path, required=True, help="草稿 JSONL 输出路径")
    args = ap.parse_args()

    survey = json.loads(args.survey.read_text(encoding="utf-8"))
    if not survey.get("papers"):
        print("[draft] 调研输出缺少 papers 字段——请用 v0.6.1+ 的 thermolit 重新调研,"
              "或把检索段落合并进 JSON(papers 键)", file=sys.stderr)
        return 1
    drafts = build_draft(survey)
    with_values = sum(1 for d in drafts if d["expected"]["values"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for d in drafts:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"[draft] 生成 {len(drafts)} 条草稿(其中 {with_values} 条含程序解析的数值待核对)"
          f" → {args.out}")
    print("[draft] 核对流程:逐条对照 excerpt 与 expected.values,正确则把 "
          "needs_human_review 改为 false;excerpt 无该数值时删除对应 values 条目")
    return 0


if __name__ == "__main__":
    sys.exit(main())
