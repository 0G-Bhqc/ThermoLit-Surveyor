"""
graph.py — 2-Pass 缺口驱动物理约束研究闭环工作流(领域无关编排)。

编排与领域知识解耦:所有领域特异逻辑(抽取 schema、记录审计、数值基准表、
缺口提示、假说/实验指令、合成指令)来自 DomainProfile(见 profiles/),
本模块只负责 LangGraph 状态图编排。10 节点覆盖"调研 → 假说 → 实验设计":

    pass1_search → pass1_extract → pass1_audit → query_refine
                 → pass2_search → pass2_extract → pass2_audit
                 → hypothesize → design_experiments → synthesize

(实验执行在实验室完成;结果回验走 thermolit.verify / hypothesis.evaluate_hypotheses,
缺失变量回流为下一轮调研缺口——完整闭环。)

可靠性设施(v0.4.0):
  * 抽取输出经 Pydantic 契约校验(schemas),失败把错误回喂 LLM 重试一次;
  * DOI 批量比对 doi.org 注册库(doi),假 DOI 在 JSON 输出中被点名;
  * token 用量计量(UsageTracker 代理)写入 metrics;
  * 可选 SqliteSaver 断点续跑(checkpoint_path)。

核心设计不变式:
  * 报告数值必须来自程序计算的《Physics Audit Table》,LLM 不得改写;
  * 参数缺口由"单位解析失败/字段缺失"数据驱动判定,驱动 Pass 2 定向检索;
  * 假说判据与实验测量目标必须是规范变量+数值阈值,由代码归一校验、由代码回验;
  * 领域 profile 可插拔,新增领域零改动本文件。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, TypedDict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from thermolit import doi as doi_mod
from thermolit.adapter import SciverseAdapter, dedup_papers
from thermolit.cache import _CachedLLM, get_global_cache
from thermolit.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MAX_CONCURRENCY,
    LLM_MODEL,
    LLM_REQUEST_RETRIES,
    LLM_TEMPERATURE,
    MAX_EXCERPT_CHARS,
    NUM_FOLLOWUP_QUERIES,
    SCIVERSE_TOKEN,
    SEARCH_TOP_K,
)
from thermolit.hypothesis import normalize_experiment_plan, normalize_hypotheses
from thermolit.json_utils import extract_json, with_retries
from thermolit.profiles.base import DomainProfile
from thermolit.profiles.thermoelectric import THERMOELECTRIC_PROFILE
from thermolit.schemas import check_evidence, validate_extraction

logger = logging.getLogger("thermolit")

# ---------------------------------------------------------------- 状态定义
class AgentState(TypedDict):
    initial_query: str
    material_system: str
    search_top_k: int
    num_followup: int

    pass1_papers: List[dict]
    pass1_records: List[dict]
    pass1_audit: List[dict]
    followup_queries: List[str]
    pass2_papers: List[dict]
    pass2_records: List[dict]
    pass2_audit: List[dict]

    all_papers: List[dict]
    all_records: List[dict]
    error_records: List[dict]
    audit_table_md: str
    knowledge_graph: dict

    hypotheses: List[dict]
    hypothesis_warnings: List[str]
    experiment_plan: dict
    experiment_warnings: List[str]
    doi_check: dict
    doi_warnings: List[str]
    deep_gap_report: str
    metrics: dict


_adapter: SciverseAdapter | None = None

# ---------------------------------------------------------------- LLM 与计量
class UsageTracker:
    """跨节点累计 LLM token 用量(挂在我们自己的调用代理上,不依赖回调机制)。"""

    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.requests = 0

    def observe(self, message: Any) -> None:
        usage = getattr(message, "usage_metadata", None) or {}
        self.input_tokens += int(usage.get("input_tokens") or 0)
        self.output_tokens += int(usage.get("output_tokens") or 0)
        self.requests += 1

    def as_dict(self) -> dict:
        return {"input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.input_tokens + self.output_tokens,
                "requests": self.requests}


class _TrackingLLM:
    """invoke 代理:记录每次响应的 usage_metadata 后透传。"""

    def __init__(self, inner: Any, tracker: UsageTracker):
        self._inner = inner
        self._tracker = tracker

    def invoke(self, messages, **kwargs):
        res = self._inner.invoke(messages, **kwargs)
        self._tracker.observe(res)
        return res


_active_tracker: UsageTracker | None = None
_cache_stats: Dict[str, int] = {"llm_cache_hits": 0, "llm_cache_misses": 0}


def get_adapter() -> SciverseAdapter:
    """惰性单例:导入/编译本模块不需要真实 token(测试友好)。"""
    global _adapter
    if _adapter is None:
        _adapter = SciverseAdapter(token=SCIVERSE_TOKEN)
    return _adapter


def _make_llm() -> Any:
    base = ChatOpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
    )
    llm: Any = base
    if _active_tracker is not None:
        llm = _TrackingLLM(base, _active_tracker)
    cache = get_global_cache()
    if cache is not None:
        llm = _CachedLLM(llm, cache, LLM_MODEL, _cache_stats)
    return llm


# ---------------------------------------------------------------- 抽取(领域无关)
def _extract_one(llm: Any, paper: Dict[str, Any], profile: DomainProfile) -> Dict[str, Any]:
    prompt = profile.build_extraction_prompt(paper["text"], MAX_EXCERPT_CHARS)
    res = with_retries(lambda: llm.invoke([HumanMessage(content=prompt)]),
                       attempts=LLM_REQUEST_RETRIES,
                       description=f"extract '{paper['title'][:40]}'")
    data = extract_json(res.content)
    normalized, err = validate_extraction(data)
    if err:
        # Pydantic 契约校验失败:把错误回喂 LLM 重试一次(结构化输出的本地闸门)
        feedback = (prompt + f"\n\nYour previous output was invalid: {err}\n"
                    "Return ONLY the corrected valid JSON object now.")
        res2 = with_retries(lambda: llm.invoke([HumanMessage(content=feedback)]),
                            attempts=2, description=f"re-extract '{paper['title'][:40]}'")
        normalized, err = validate_extraction(extract_json(res2.content))
        if err:
            raise ValueError(f"extraction schema validation failed after retry: {err}")
    data = normalized
    # P0-2:证据句包含校验——摘录必须真实存在于原文,否则标记为未核实
    data["evidence_check"] = check_evidence(data, paper["text"])
    data["title"] = paper.get("title", "")
    data["doi"] = paper.get("doi", "N/A")
    data["query_source"] = paper.get("query_source", "")
    data["source_pass"] = paper.get("source_pass", 1)
    return data


def _try_job(fn, paper):
    try:
        return fn(paper)
    except Exception as e:  # 单条失败不影响整批
        return {"error": str(e)}


def _batch_extract(papers: List[Dict[str, Any]], pass_num: int,
                   profile: DomainProfile) -> tuple[List[dict], List[dict]]:
    """并行抽取;失败条目进入独立 error_records,不混入正常记录污染下游。"""
    if not papers:
        return [], []
    llm = _make_llm()
    records: List[dict] = []
    errors: List[dict] = []

    def _job(p: Dict[str, Any]) -> Dict[str, Any]:
        p = {**p, "source_pass": p.get("source_pass", pass_num)}
        return _extract_one(llm, p, profile)

    with ThreadPoolExecutor(max_workers=LLM_MAX_CONCURRENCY) as pool:
        results = list(pool.map(lambda p: _try_job(_job, p), papers))

    for p, r in zip(papers, results):
        if r.get("error"):
            errors.append({"title": p.get("title", ""), "doi": p.get("doi", "N/A"),
                           "pass": pass_num, "error": r["error"]})
        else:
            records.append(r)
    return records, errors


def _update_material_system(state: Dict[str, Any], records: List[dict]) -> str:
    """从抽取记录投票选出最常见材料体系;无候选则回退初始查询词。"""
    from collections import Counter
    candidates = [str(r.get("material_system")).strip()
                  for r in records if r.get("material_system")]
    if candidates:
        top, _ = Counter(candidates).most_common(1)[0]
        return top
    return state.get("material_system") or state["initial_query"]


def build_evidence_table_md(papers: List[Dict[str, Any]]) -> str:
    header = ("| # | Title | DOI | 年份 | 期刊 | Pass | 来源查询 |\n"
              "|---|---|---|---|---|---|---|")
    rows = [f"| {i} | {p['title'][:55]} | {p.get('doi', 'N/A')} "
            f"| {p.get('year', '') or '—'} | {str(p.get('venue', ''))[:28] or '—'} "
            f"| {p.get('source_pass', '?')} | {str(p.get('query_source', ''))[:40]} |"
            for i, p in enumerate(papers, 1)]
    return "\n".join([header] + rows) if rows else header + "\n|(无)|"


# ---------------------------------------------------------------- 图工厂
_apps: Dict[tuple, Any] = {}


def _make_checkpointer(path: str | None):
    """可选 SqliteSaver 断点续跑;依赖缺失时优雅降级并告警。"""
    if not path:
        return None
    try:
        import sqlite3

        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        logger.warning(
            "langgraph-checkpoint-sqlite 未安装,断点续跑不可用:"
            "pip install 'thermolit-surveyor[checkpoint]'")
        return None
    logger.info("[checkpoint] SqliteSaver 已启用: %s", path)
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))


def build_survey_app(profile: DomainProfile | None = None,
                     checkpoint_path: str | None = None):
    """按 profile(+checkpoint 路径)编译并缓存 LangGraph 应用。"""
    profile = profile or THERMOELECTRIC_PROFILE
    cache_key = (profile.name, checkpoint_path)
    cached = _apps.get(cache_key)
    if cached is not None:
        return cached

    def pass1_search_node(state: AgentState) -> dict:
        start = time.time()
        q = state["initial_query"]
        top_k = state.get("search_top_k") or SEARCH_TOP_K
        logger.info("[Pass 1] Sciverse 广域检索: %s (top_k=%s)", q, top_k)
        papers = get_adapter().search_sync(q, top_k=top_k)
        for p in papers:
            p["source_pass"] = 1
        metrics = dict(state.get("metrics", {}))
        metrics.update(pass1_search_time=time.time() - start, pass1_papers_count=len(papers))
        return {"pass1_papers": papers, "metrics": metrics,
                "material_system": state.get("material_system") or q}

    def pass1_extract_node(state: AgentState) -> dict:
        start = time.time()
        papers = state.get("pass1_papers", [])
        logger.info("[Pass 1] 结构化抽取 %s 篇...", len(papers))
        records, errors = _batch_extract(papers, pass_num=1, profile=profile)
        material = _update_material_system(dict(state), records)
        metrics = dict(state.get("metrics", {}))
        metrics.update(pass1_extract_time=time.time() - start, pass1_records_count=len(records))
        return {"pass1_records": records, "error_records": errors,
                "material_system": material, "metrics": metrics}

    def pass1_audit_node(state: AgentState) -> dict:
        start = time.time()
        audits = profile.audit_records(state.get("pass1_records", []))
        gaps = profile.aggregate_missing(audits)
        n_flagged = sum(1 for a in audits if a.get("flags"))
        logger.info("[Pass 1] 物理审计[%s]: %s 条,参数缺口 %s,标记异常 %s 条",
                    profile.name, len(audits), gaps, n_flagged)
        metrics = dict(state.get("metrics", {}))
        metrics.update(pass1_audit_time=time.time() - start, pass1_gaps=gaps)
        return {"pass1_audit": audits, "metrics": metrics}

    def query_refine_node(state: AgentState) -> dict:
        """缺口驱动的 Pass 2 查询生成:数据驱动缺口摘要 + LLM 拟查;LLM 失败时退化为模板查询。"""
        start = time.time()
        audits = state.get("pass1_audit", [])
        material = state.get("material_system") or state["initial_query"]
        n = state.get("num_followup") or NUM_FOLLOWUP_QUERIES

        gaps = profile.aggregate_missing(audits)
        gap_lines = [f"- {param} missing in {count} record(s) "
                     f"(hint: {profile.gap_query_hints.get(param, param)})"
                     for param, count in gaps.items()] or \
                    ["- no numeric domain parameter parsed yet"]
        flags_summary = [f"{a['title'][:50]}: {'; '.join(a['flags'])}"
                         for a in audits if a.get("flags")]

        llm = _make_llm()
        prompt = f"""You are refining a literature search for the material system: {material}
(domain profile: {profile.name} — {profile.description})

Physics audit of Pass 1 found these evidence gaps:
{chr(10).join(gap_lines)}

Physics consistency flags:
{chr(10).join(flags_summary) or "(none)"}

Generate exactly {n} targeted academic search queries in English to fill the most critical gaps.
Each query MUST mention the material system AND a specific parameter AND a measurement keyword,
targeting papers that REPORT NUMBERS (reviews and application papers are useless as evidence).
- good: "PbTe Seebeck coefficient electrical conductivity measured 773 K"
- good: "Bi2Te3 lattice thermal conductivity Wiedemann-Franz decoupling value"
- bad: "PbTe thermoelectric review applications" (review, no numbers)
Return ONLY a valid JSON array of {n} strings."""

        queries = None
        try:
            res = llm.invoke([HumanMessage(content=prompt)])
            parsed = extract_json(res.content)
            if isinstance(parsed, list) and parsed and all(isinstance(s, str) for s in parsed):
                queries = parsed[:n]
        except Exception as e:
            logger.warning("查询生成失败,退化为模板查询: %s", e)

        if not queries:
            queries = profile.fallback_queries(material, list(gaps.keys()), n)

        metrics = dict(state.get("metrics", {}))
        metrics.update(refine_time=time.time() - start)
        logger.info("[Gap→Query] %s", queries)
        return {"followup_queries": queries, "metrics": metrics}

    def pass2_search_node(state: AgentState) -> dict:
        start = time.time()
        queries = state.get("followup_queries", [])
        top_k = state.get("search_top_k") or SEARCH_TOP_K
        logger.info("[Pass 2] 定向下钻: %s", queries)

        async def _run_all():
            tasks = [get_adapter().semantic_search_async(q, top_k=top_k) for q in queries]
            return [r for sub in await asyncio.gather(*tasks, return_exceptions=True)
                    if isinstance(sub, list) for r in sub]

        pass2_papers = asyncio.run(_run_all())
        for p in pass2_papers:
            p["source_pass"] = 2
        # 与 Pass 1 合并后按 DOI/标题去重,避免同一篇文献重复计入证据链
        all_papers = dedup_papers(state.get("pass1_papers", []) + pass2_papers)
        metrics = dict(state.get("metrics", {}))
        metrics.update(pass2_search_time=time.time() - start,
                       pass2_papers_count=len(pass2_papers),
                       deduped_total_papers=len(all_papers))
        return {"pass2_papers": pass2_papers, "all_papers": all_papers, "metrics": metrics}

    def pass2_extract_node(state: AgentState) -> dict:
        start = time.time()
        seen_keys = {(str(r.get("doi", "N/A")).lower(), str(r.get("title", "")).lower())
                     for r in state.get("pass1_records", [])}
        fresh = [p for p in state.get("pass2_papers", [])
                 if (str(p.get("doi", "N/A")).lower(), str(p.get("title", "")).lower())
                 not in seen_keys]
        logger.info("[Pass 2] 抽取 %s 篇(跳过 %s 篇 Pass 1 已抽取)",
                    len(fresh), len(state.get("pass2_papers", [])) - len(fresh))
        records, errors = _batch_extract(fresh, pass_num=2, profile=profile)
        # 真实校准发现:不同查询常命中同一文献的不同段落,记录层必须与检索层同规则去重
        all_records = dedup_papers(state.get("pass1_records", []) + records)
        skipped = (len(state.get("pass1_records", [])) + len(records)) - len(all_records)
        metrics = dict(state.get("metrics", {}))
        metrics.update(pass2_extract_time=time.time() - start,
                       duplicate_records_skipped=skipped)
        return {"pass2_records": records, "all_records": all_records,
                "error_records": state.get("error_records", []) + errors,
                "metrics": metrics}

    def pass2_audit_node(state: AgentState) -> dict:
        start = time.time()
        audits = profile.audit_records(state.get("all_records", []))
        table = profile.build_table_md(audits)
        metrics = dict(state.get("metrics", {}))
        metrics.update(pass2_audit_time=time.time() - start,
                       total_papers_analyzed=len(state.get("all_papers", [])),
                       total_records_audited=len(audits))
        return {"pass2_audit": audits, "audit_table_md": table, "metrics": metrics}

    def hypothesize_node(state: AgentState) -> dict:
        """审计表 → 结构化可证伪假说(LLM 拟稿,代码归一校验判据与引用)。"""
        start = time.time()
        if not profile.supports_research_loop:
            warn = f"profile '{profile.name}' 未提供假说钩子,跳过研究闭环环节"
            logger.warning(warn)
            return {"hypotheses": [], "hypothesis_warnings": [warn],
                    "experiment_plan": {}, "experiment_warnings": [],
                    "metrics": dict(state.get("metrics", {}))}

        material = state.get("material_system") or state["initial_query"]
        audits = state.get("pass2_audit", [])
        audit_table = state.get("audit_table_md") or profile.build_table_md(audits)
        gaps = profile.aggregate_missing(audits)
        prompt = profile.build_hypothesis_prompt(material, audit_table, gaps)

        hypotheses: List[dict] = []
        warnings: List[str] = []
        try:
            llm = _make_llm()
            res = with_retries(lambda: llm.invoke([HumanMessage(content=prompt)]),
                               attempts=LLM_REQUEST_RETRIES,
                               description="generate hypotheses")
            parsed = extract_json(res.content)
            known_dois = {str(a.get("doi")) for a in audits if a.get("doi")}
            hypotheses, warnings = normalize_hypotheses(parsed, known_dois)
        except Exception as e:
            warnings.append(f"假说生成失败: {e}")

        metrics = dict(state.get("metrics", {}))
        metrics.update(hypothesize_time=time.time() - start,
                       hypotheses_count=len(hypotheses))
        logger.info("[Hypothesize] %s 条结构化假说,%s 条警告",
                    len(hypotheses), len(warnings))
        return {"hypotheses": hypotheses, "hypothesis_warnings": warnings,
                "metrics": metrics}

    def design_experiments_node(state: AgentState) -> dict:
        """结构化假说 → 实验方案(LLM 拟稿,代码校验测量目标与假说引用)。"""
        start = time.time()
        hypotheses = state.get("hypotheses", [])
        if not profile.supports_research_loop or not hypotheses:
            warn = "无可用假说或 profile 不支持,跳过实验设计"
            logger.warning(warn)
            return {"experiment_plan": {}, "experiment_warnings": [warn],
                    "metrics": dict(state.get("metrics", {}))}

        material = state.get("material_system") or state["initial_query"]
        plan: Dict[str, Any] = {}
        warnings: List[str] = []
        try:
            llm = _make_llm()
            prompt = profile.build_experiment_prompt(material, hypotheses)
            res = with_retries(lambda: llm.invoke([HumanMessage(content=prompt)]),
                               attempts=LLM_REQUEST_RETRIES,
                               description="design experiments")
            plan, warnings = normalize_experiment_plan(extract_json(res.content),
                                                       hypotheses)
        except Exception as e:
            warnings.append(f"实验方案生成失败: {e}")

        metrics = dict(state.get("metrics", {}))
        metrics.update(design_time=time.time() - start,
                       planned_measurements=len(plan.get("measurements", [])))
        logger.info("[Design] 实验方案:%s 次测量,覆盖假说 %s",
                    len(plan.get("measurements", [])), plan.get("hypothesis_refs"))
        return {"experiment_plan": plan, "experiment_warnings": warnings,
                "metrics": metrics}

    def synthesize_node(state: AgentState) -> dict:
        start = time.time()
        material = state.get("material_system") or state["initial_query"]
        audits = state.get("pass2_audit", [])
        audit_table = state.get("audit_table_md") or profile.build_table_md(audits)
        evidence_table = build_evidence_table_md(state.get("all_papers", []))
        gaps = profile.aggregate_missing(audits)
        prompt = profile.build_synthesis_prompt(
            material, audit_table, evidence_table, gaps,
            hypotheses=state.get("hypotheses") or None,
            experiment_plan=state.get("experiment_plan") or None)

        llm = _make_llm()
        res = with_retries(lambda: llm.invoke([HumanMessage(content=prompt)]),
                           attempts=LLM_REQUEST_RETRIES, description="synthesize report")
        report = res.content

        loop_note = ("假说与实验方案为结构化对象,实验完成后可用 "
                     "`thermolit --verify` 程序化回验。\n" if state.get("hypotheses") else "")
        header = (f"# {material} 领域调研报告({profile.name} profile)\n\n"
                  f"> 本报告由 2-Pass 物理约束研究闭环智能体生成;"
                  f"数值以《Physics Audit Table》为准(程序计算,非 LLM 生成)。{loop_note}\n")
        full_report = header + report

        metrics = dict(state.get("metrics", {}))
        metrics.update(synthesis_time=time.time() - start)
        logger.info("[Synthesize] 报告生成完成(%s 字符)", len(full_report))
        return {"deep_gap_report": full_report, "metrics": metrics}

    workflow = StateGraph(AgentState)
    workflow.add_node("pass1_search", pass1_search_node)
    workflow.add_node("pass1_extract", pass1_extract_node)
    workflow.add_node("pass1_audit", pass1_audit_node)
    workflow.add_node("query_refine", query_refine_node)
    workflow.add_node("pass2_search", pass2_search_node)
    workflow.add_node("pass2_extract", pass2_extract_node)
    workflow.add_node("pass2_audit", pass2_audit_node)
    workflow.add_node("hypothesize", hypothesize_node)
    workflow.add_node("design_experiments", design_experiments_node)
    workflow.add_node("synthesize", synthesize_node)

    workflow.set_entry_point("pass1_search")
    workflow.add_edge("pass1_search", "pass1_extract")
    workflow.add_edge("pass1_extract", "pass1_audit")
    workflow.add_edge("pass1_audit", "query_refine")
    workflow.add_edge("query_refine", "pass2_search")
    workflow.add_edge("pass2_search", "pass2_extract")
    workflow.add_edge("pass2_extract", "pass2_audit")
    workflow.add_edge("pass2_audit", "hypothesize")
    workflow.add_edge("hypothesize", "design_experiments")
    workflow.add_edge("design_experiments", "synthesize")
    workflow.add_edge("synthesize", END)

    checkpointer = _make_checkpointer(checkpoint_path)
    app = workflow.compile(checkpointer=checkpointer) if checkpointer \
        else workflow.compile()
    _apps[cache_key] = app
    return app


def run_agent(query: str = "Bi2Te3 thermoelectric figure of merit zT Seebeck conductivity",
              profile: DomainProfile | None = None,
              top_k: int | None = None, num_followup: int | None = None,
              check_dois: bool = True, checkpoint_path: str | None = None) -> dict:
    """
    运行一次完整研究闭环调研。

    check_dois:     调研结束后把全部 DOI 比对 doi.org 注册库(免费),假 DOI 点名;
    checkpoint_path: 提供 Sqlite 路径则启用断点续跑(thread_id 由 query+profile 派生)。
    """
    global _active_tracker
    profile = profile or THERMOELECTRIC_PROFILE
    _cache_stats.update(llm_cache_hits=0, llm_cache_misses=0)
    initial_state = {
        "initial_query": query,
        "material_system": query,
        "search_top_k": top_k or SEARCH_TOP_K,
        "num_followup": num_followup or NUM_FOLLOWUP_QUERIES,
        "metrics": {},
    }
    app = build_survey_app(profile, checkpoint_path=checkpoint_path)
    tracker = UsageTracker()
    _active_tracker = tracker
    start_total = time.time()
    try:
        if checkpoint_path:
            thread_id = hashlib.sha1(
                f"{profile.name}|{query}".encode()).hexdigest()[:16]
            final_state = app.invoke(
                initial_state, config={"configurable": {"thread_id": thread_id}})
        else:
            final_state = app.invoke(initial_state)
    finally:
        _active_tracker = None
    final_state["metrics"]["total_pipeline_duration"] = time.time() - start_total
    final_state["metrics"]["profile"] = profile.name
    final_state["metrics"]["llm_usage"] = tracker.as_dict()
    final_state["metrics"]["llm_cache"] = dict(_cache_stats)

    # DOI 注册库核验(证据链最后一道闸;免费 API,无需 key)
    start = time.time()
    dois = doi_mod.extract_dois(final_state.get("all_records", []),
                                final_state.get("hypotheses", []))
    if check_dois and dois:
        summary = doi_mod.summarize(doi_mod.check_dois(dois))
        final_state["doi_check"] = summary
        final_state["doi_warnings"] = (
            [f"DOI 在注册库中不存在: {d}" for d in summary["missing"]]
            + [f"DOI 无法核验(网络/限流): {d}" for d in summary["unknown"]])
        logger.info("[DOI] ok=%s missing=%s unknown=%s",
                    len(summary["ok"]), len(summary["missing"]), len(summary["unknown"]))
    else:
        final_state["doi_check"] = {"ok": [], "missing": [], "unknown": [],
                                    "skipped": True}
        final_state["doi_warnings"] = []
    final_state["metrics"]["doi_check_time"] = time.time() - start
    return final_state
