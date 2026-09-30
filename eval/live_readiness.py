#!/usr/bin/env python
"""
live_readiness.py — 第二档(真实世界校准)就绪自检。

逐项检查真实全链路(--live)的前置条件,给出明确的"缺什么":
  1. LLM 凭证(DEEPSEEK_API_KEY / BASE_URL)——可选 --ping 发一次真实补全
  2. sciverse 包与 SCIVERSE_TOKEN
  3. doi.org 可达性(DOI 核验功能)

用法:python eval/live_readiness.py [--ping]
退出码:0 = 就绪;1 = 有缺失项。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

CHECKS: list[tuple[str, bool, str]] = []


def main() -> int:
    ap = argparse.ArgumentParser(description="live 全链路就绪自检")
    ap.add_argument("--ping", action="store_true", help="额外发一次真实 LLM 补全(消耗少量额度)")
    args = ap.parse_args()

    from thermolit import config

    # 1. LLM 凭证
    llm_ok = bool(config.LLM_API_KEY) and not config.LLM_API_KEY.startswith("your_")
    CHECKS.append(("LLM 凭证 DEEPSEEK_API_KEY", llm_ok,
                   f"endpoint={config.LLM_BASE_URL} model={config.LLM_MODEL}"))

    # 2. Sciverse
    try:
        import sciverse  # noqa: F401

        pkg_ok = True
    except ImportError:
        pkg_ok = False
    CHECKS.append(("sciverse 包", pkg_ok, "pip install sciverse==0.13.1"))
    CHECKS.append(("SCIVERSE_TOKEN", bool(config.SCIVERSE_TOKEN),
                   "sciverse.opendatalab.com 注册获取"))

    # 3. doi.org 可达性(DOI 核验,免费)
    doi_ok, doi_note = False, "未检测"
    try:
        import requests

        r = requests.get("https://doi.org/api/handles/10.1000/1", timeout=10)
        doi_ok = r.status_code in (200, 404)
        doi_note = f"HTTP {r.status_code}"
    except Exception as e:  # noqa: BLE001
        doi_note = f"不可达: {e}"
    CHECKS.append(("doi.org 可达(DOI 核验)", doi_ok, doi_note))

    # 4. 可选:真实 LLM ping
    if args.ping and llm_ok:
        try:
            from langchain_core.messages import HumanMessage

            from thermolit.graph import _make_llm
            res = _make_llm().invoke([HumanMessage(content="Reply: OK")])
            CHECKS.append(("LLM 真实补全", res.content.strip() != "",
                           str(res.content)[:40]))
        except Exception as e:  # noqa: BLE001
            CHECKS.append(("LLM 真实补全", False, str(e)[:120]))

    print("=== live 全链路就绪自检 ===")
    all_ok = True
    for name, ok, note in CHECKS:
        mark = "✓" if ok else "✗"
        all_ok &= ok
        print(f"  {mark} {name}: {note}")
    print("\n结论:", "就绪,可运行 python eval/real_model_smoke.py --live 与 thermolit 真实调研"
          if all_ok else "存在缺失项——补齐上方 ✗ 项后重跑本自检")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
