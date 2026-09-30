"""
profiles.base — DomainProfile:把"领域知识"从"智能体编排"中解耦出来的插件接口。

设计动机(项目的核心创新点之一):通用 DeepResearch 工具只做"检索 + 写作",
对检索到的数值不做任何确定性校验;ThermoLit-Surveyor 在检索与合成之间插入一个
**确定性领域审计层**。这一层对领域是完全可插拔的:

    一个 DomainProfile = 抽取 schema + 记录级审计函数 + 数值基准表渲染 + 缺口检索提示 + 合成指令

新领域(超导、锂电、催化…)只需提供一个 profile,LangGraph 编排、缺口驱动的
2-Pass 检索、审计表注入、证据链等全部复用。

注意:extraction_schema_prompt 内含 JSON 大括号示例,拼接时不要用 str.format。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

AuditRecordFn = Callable[[Dict[str, Any]], Dict[str, Any]]
BuildTableFn = Callable[[List[Dict[str, Any]]], str]
SynthesisPromptFn = Callable[..., str]


@dataclass(frozen=True)
class DomainProfile:
    name: str
    """profile 标识,如 "thermoelectric"(用于日志、缓存键、CLI 选择)。"""

    description: str
    """一句话说明本 profile 审计什么物理量。"""

    extraction_schema_prompt: str
    """抽取阶段 JSON schema 指令(纯文本,含大括号示例,勿用 str.format)。"""

    audit_record: AuditRecordFn
    """单条抽取记录 → {解析值, 派生量, flags: [...], missing: [...]},全部为确定性问题代码。"""

    build_table_md: BuildTableFn
    """审计记录列表 → Markdown《Physics Audit Table》(报告的数值基准)。"""

    gap_query_hints: Dict[str, str] = field(default_factory=dict)
    """规范参数名 → 定向检索提示语(驱动 Pass 2 缺口查询)。"""

    build_synthesis_prompt: SynthesisPromptFn = None  # type: ignore[assignment]
    """(material, audit_table, evidence_table, gaps, hypotheses, plan) → 完整合成提示词。"""

    build_hypothesis_prompt: Callable[..., str] | None = None
    """(material, audit_table, gaps) → 假说生成提示词;为 None 表示该 profile 不支持研究闭环。"""

    build_experiment_prompt: Callable[..., str] | None = None
    """(material, hypotheses) → 实验方案设计提示词;与 build_hypothesis_prompt 成对提供。"""

    # ------------------------------------------------------------ 通用默认实现
    @property
    def supports_research_loop(self) -> bool:
        """是否具备研究闭环能力(结构化假说 + 实验方案设计)。"""
        return (self.build_hypothesis_prompt is not None
                and self.build_experiment_prompt is not None)

    def audit_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量审计;抽取失败的记录直接透传标记,不进入领域审计。"""
        out: List[Dict[str, Any]] = []
        for rec in records:
            if "error" in rec:
                out.append({**rec, "flags": ["extraction_failed"], "missing": []})
            else:
                out.append(self.audit_record(rec))
        return out

    def aggregate_missing(self, audits: List[Dict[str, Any]]) -> Dict[str, int]:
        """按规范参数名统计缺失次数(降序),用于缺口检索排序。"""
        counts: Dict[str, int] = {}
        for a in audits:
            for m in a.get("missing", []):
                counts[m] = counts.get(m, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    def build_extraction_prompt(self, excerpt: str, max_chars: int) -> str:
        """抽取提示词 = schema + 截断后的摘要。必须用拼接,不能用 str.format。"""
        excerpt = excerpt[:max_chars]
        return (f"{self.extraction_schema_prompt}\n\n"
                f"Excerpt (may be truncated to {max_chars} chars):\n{excerpt}")

    def fallback_queries(self, material: str, missing_params: List[str],
                         n: int) -> List[str]:
        """LLM 查询生成失败时的模板兜底(由真实缺口驱动,而非硬编码材料)。"""
        queries = []
        for p in missing_params:
            hint = self.gap_query_hints.get(p, p)
            queries.append(f"{material} {hint}")
        if not queries:
            queries = [f"{material} {h}" for h in self.gap_query_hints.values()]
        queries.append(f"{material} key transport properties measurement")
        # 去重并截断到 n 条
        seen, out = set(), []
        for q in queries:
            if q not in seen:
                seen.add(q)
                out.append(q)
        return out[:n]
