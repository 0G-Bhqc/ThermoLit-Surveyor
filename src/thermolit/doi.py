"""
doi.py — DOI 有效性校验(doi.org handle API,免费无需 key)。

调研报告中 DOI 是证据链的锚点;LLM 编造 DOI 是最常见的幻觉之一。
本模块把报告中出现的所有 DOI(文献记录 + 假说证据)批量比对 DOI 官方注册库:

  ok       → handle 存在
  missing  → 注册库确认不存在(404)→ 报告中标记
  unknown  → 网络失败,无法判定(不冤枉)

这是"可审计性"的最后一道闸:任何假 DOI 都会在 JSON 输出中被点名。
"""
from __future__ import annotations

import re
from typing import Dict, List

import requests

_HANDLE_API = "https://doi.org/api/handles/{doi}"
_TIMEOUT_S = 10
# DOI 语法:10.<registrant>/<suffix>(Crossref 建议 2<=registrant<=5 位,放宽以兼容实验性前缀)
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
# 这些占位不算 DOI(抽取失败/未提供的标记)
_PLACEHOLDERS = {"n/a", "none", "", "unknown", "null"}


def normalize_doi(doi: str) -> str:
    return (doi or "").strip().lower().removeprefix("https://doi.org/").removeprefix("http://dx.doi.org/")


def extract_dois(records: List[dict], hypotheses: List[dict] | None = None) -> List[str]:
    """从审计记录与假说证据里收集全部合法格式的 DOI(去重保序)。"""
    seen, out = set(), []
    candidates: List[str] = []
    for rec in records or []:
        candidates.append(str(rec.get("doi", "")))
    for hyp in hypotheses or []:
        for d in hyp.get("evidence_dois", []) or []:
            candidates.append(str(d))
    for raw in candidates:
        doi = normalize_doi(raw)
        if doi in _PLACEHOLDERS or not _DOI_RE.match(doi):
            continue
        if doi not in seen:
            seen.add(doi)
            out.append(doi)
    return out


def check_dois(dois: List[str], max_check: int = 50) -> Dict[str, Dict[str, int]]:
    """
    批量校验 DOI。返回 {doi: {"status": ok|missing|unknown, "http": code}}。
    单个失败不影响整批;超过 max_check 截断(防止大报告打爆 API)。
    """
    results: Dict[str, Dict[str, int]] = {}
    for doi in dois[:max_check]:
        status, code = "unknown", 0
        try:
            resp = requests.get(_HANDLE_API.format(doi=doi), timeout=_TIMEOUT_S,
                                headers={"Accept": "application/json"})
            code = resp.status_code
            if resp.status_code == 200:
                payload = resp.json() if resp.content else {}
                # handle API: responseCode==1 表示存在
                status = "ok" if payload.get("responseCode") == 1 else "missing"
            elif resp.status_code == 404:
                status = "missing"
            elif resp.status_code == 429:
                status = "unknown"  # 限流,不冤枉
                break
        except requests.RequestException:
            status, code = "unknown", 0
        results[doi] = {"status": status, "http": code}
    return results


def summarize(results: Dict[str, Dict[str, int]]) -> Dict[str, List[str]]:
    """按状态归类,供 JSON 输出与警告使用。"""
    summary: Dict[str, List[str]] = {"ok": [], "missing": [], "unknown": []}
    for doi, info in results.items():
        summary[info["status"]].append(doi)
    return summary
