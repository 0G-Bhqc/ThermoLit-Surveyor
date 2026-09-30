#!/usr/bin/env python
"""
evaluate.py — 金标评测脚本:对每条金标记录运行真实抽取(或确定性解析),
与人工核对的 SI 真值比对,产出字段召回率 / 数值相对误差 / 编造率。

  python eval/evaluate.py --gold eval/golden/thermoelectric_sample.jsonl --validate  # 仅校验格式
  python eval/evaluate.py --gold eval/golden/thermoelectric_sample.jsonl            # 完整评测(需 API key)
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_KEYS = {"id", "profile", "excerpt", "expected"}
EXPECTED_VALUE_KEYS = {"seebeck_coefficient", "electrical_conductivity",
                       "thermal_conductivity", "zT_value"}


def load_gold(path: Path) -> list[dict]:
    entries = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"[gold] 第 {i} 行不是合法 JSON: {exc}")
        missing = REQUIRED_KEYS - set(e)
        if missing:
            raise SystemExit(f"[gold] 第 {i} 行缺少键: {missing}")
        for k in e["expected"].get("values", {}):
            if k not in EXPECTED_VALUE_KEYS:
                raise SystemExit(f"[gold] 第 {i} 行出现未知参数 {k},"
                                 f"合法键: {sorted(EXPECTED_VALUE_KEYS)}")
        entries.append(e)
    return entries


def run_extraction(excerpt: str) -> dict:
    """对单条 excerpt 运行真实抽取 + 确定性解析(需要 DEEPSEEK_API_KEY)。"""
    from thermolit import graph as proto
    from thermolit.profiles.thermoelectric import THERMOELECTRIC_PROFILE

    llm = proto._make_llm()
    paper = {"title": "gold", "doi": "gold", "text": excerpt, "source_pass": 0}
    record = proto._extract_one(llm, paper, THERMOELECTRIC_PROFILE)
    return THERMOELECTRIC_PROFILE.audit_record(record)


def evaluate(entries: list[dict]) -> dict:
    # SI 字段名 → audit_record 返回的键
    AUDIT_KEY = {"seebeck_coefficient": "S_si_V_per_K",
                 "electrical_conductivity": "sigma_si_S_per_m",
                 "thermal_conductivity": "kappa_si_W_per_mK",
                 "zT_value": "zT_reported"}
    total_fields, recalled, fabricated = 0, 0, 0
    rel_errors: list[float] = []

    for e in entries:
        audit = run_extraction(e["excerpt"])
        for param, truth in e["expected"]["values"].items():
            total_fields += 1
            got = audit.get(AUDIT_KEY[param])
            if got is None:
                continue  # 漏抽(计入召回率分母,不计入编造)
            if abs(got - truth["si"]) <= max(1e-12, 0.02 * abs(truth["si"])):
                recalled += 1
                rel_errors.append(abs(got - truth["si"]) / abs(truth["si"]))
            else:
                rel_errors.append(abs(got - truth["si"]) / abs(truth["si"]))

    # 编造率:expected 中不存在的字段,LLM 却给出非空文本且能解析出数值
    for e in entries:
        audit = run_extraction(e["excerpt"])
        absent = set(EXPECTED_VALUE_KEYS) - set(e["expected"]["values"])
        for param in absent:
            fabricated += 1 if audit.get(AUDIT_KEY[param]) is not None else 0

    n_fabs = sum(1 for e in entries
                 for _ in set(EXPECTED_VALUE_KEYS) - set(e["expected"]["values"]))
    return {
        "fields_total": total_fields,
        "field_recall": round(recalled / total_fields, 4) if total_fields else None,
        "median_rel_error": round(statistics.median(rel_errors), 4) if rel_errors else None,
        "fabrication_rate": round(fabricated / n_fabs, 4) if n_fabs else None,
        "n_entries": len(entries),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="ThermoLit-Surveyor 金标评测")
    ap.add_argument("--gold", type=Path, required=True, help="金标 JSONL 路径")
    ap.add_argument("--validate", action="store_true", help="仅校验格式,不调用 LLM")
    ap.add_argument("--out", type=Path, default=None, help="结果 JSON 输出路径")
    args = ap.parse_args()

    entries = load_gold(args.gold)
    print(f"[gold] 载入 {len(entries)} 条金标记录")

    if args.validate:
        print("[gold] 格式校验通过(--validate)")
        return 0

    results = evaluate(entries)
    print(json.dumps(results, ensure_ascii=False, indent=2))

    out = args.out or Path("eval/results") / f"{datetime.now(timezone.utc):%Y%m%d_%H%M}_{args.gold.stem}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[eval] 结果写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
