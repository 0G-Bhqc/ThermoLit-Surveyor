"""
profiles.thermoelectric — 首个领域 profile:热电材料输运性质。

把 v0.1~v0.3 中沉淀的热电领域知识装配为 DomainProfile:
  - 抽取:S/σ/κ/zT/载流子浓度/迁移率 + 测量温度
  - 审计:Wiedemann-Franz 解耦 + zT 一致性 + 非晶下限筛查(见 thermolit.physics)
  - 研究闭环:结构化可证伪假说 → 实验方案设计 → 实验结果确定性回验
  - 缺口提示与合成指令
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from thermolit import physics
from thermolit.hypothesis import CANONICAL_VARS
from thermolit.profiles.base import DomainProfile

EXTRACTION_SCHEMA_PROMPT = """Extract thermoelectric transport parameters from the excerpt below into JSON with EXACTLY these keys:
{
  "material_system": "material formula, e.g. Bi2Te3 / PbTe",
  "zT_value": "dimensionless zT exactly as printed (e.g. \\"0.9 @ 350 K\\"), else null",
  "seebeck_coefficient": "Seebeck coefficient with units as printed (e.g. \\"-180 uV/K\\"), else null",
  "thermal_conductivity": "total thermal conductivity with units as printed (e.g. \\"1.3 W/mK\\"), else null",
  "electrical_conductivity": "electrical conductivity OR resistivity with units as printed, else null",
  "carrier_concentration": "carrier concentration with units, else null",
  "mobility": "carrier mobility with units, else null",
  "temperature_k": "numeric measurement temperature in Kelvin if explicitly stated, else null",
  "key_claim": "one-sentence summary of the main transport claim",
  "evidence_sentences": {
    "<parameter_key>": "the VERBATIM sentence from the excerpt containing that parameter's value"
  }
}
Rules:
- Copy values verbatim from the excerpt WITH their original units. Never convert, never infer.
- If a parameter is not explicitly stated in the excerpt, use null. Do NOT guess.
- For EVERY non-null parameter, evidence_sentences must contain its verbatim supporting sentence
  (quote exactly, do not paraphrase). Never fabricate a sentence that is not in the excerpt.
- Return ONLY valid JSON, no prose, no code fences."""

GAP_QUERY_HINTS = {
    "seebeck_coefficient": "Seebeck coefficient measurement",
    "electrical_conductivity": "electrical conductivity resistivity measurement",
    "thermal_conductivity": "total thermal conductivity measurement",
    "zT_value": "thermoelectric figure of merit zT",
    "carrier_concentration": "Hall carrier concentration",
    "mobility": "carrier mobility",
}


def build_synthesis_prompt(material: str, audit_table: str, evidence_table: str,
                           gaps: Dict[str, int],
                           hypotheses: List[Dict[str, Any]] | None = None,
                           experiment_plan: Dict[str, Any] | None = None) -> str:
    extra_sections = ""
    if hypotheses:
        extra_sections += (
            "\n## Structured falsifiable hypotheses (already generated, cite by id)\n"
            + f"{json.dumps(hypotheses, ensure_ascii=False, indent=2)}\n")
    if experiment_plan:
        extra_sections += (
            "\n## Proposed experiment plan (already generated, cite by id)\n"
            + f"{json.dumps(experiment_plan, ensure_ascii=False, indent=2)}\n")

    return f"""You are a leading thermoelectricity specialist writing a rigorous literature survey on "{material}".

You have completed a 2-Pass iterative deep-research workflow. The numbers below were computed
by a deterministic physics engine from the extracted literature values (Wiedemann-Franz:
kappa_e = L*sigma*T with adaptive Lorenz number; kappa_l = kappa_tot - kappa_e;
zT_calc = S^2*sigma*T/kappa). Treat this table as the single source of numeric truth:
DO NOT invent, alter, or recompute any value; cite them by row DOI.

## Physics Audit Table (deterministically computed)
{audit_table}

## Aggregate evidence gaps
{gaps}

## Sciverse Evidence Chain
{evidence_table}
{extra_sections}
Write an authoritative Chinese academic markdown survey report with these sections:
1. **多尺度输运参数矩阵**:基于上方 Physics Audit Table 整理解耦参数,保留全部 DOI 引用。
2. **物理输运解耦分析**:解释 Wiedemann-Franz 关系 kappa_e = L0*sigma*T(含自适应 Lorenz 数的
   简并/非简并判据)与 Debye-Callaway 声子散射(边界/点缺陷/Umklapp)对 kappa_l 的作用;
   结合表中 zT报道 与 zT计算 的偏差与标记列,指出哪些文献值需要复核。
3. **两轮迭代检索发现**:说明 Pass 2 的定向查询如何补齐 Pass 1 的参数缺口(引用具体 DOI)。
4. **可证伪科学假说 H1~H5**:逐条展开上方结构化假说(沿用其 id、判据阈值与证据 DOI,
   不得改动数值),每条附验证协议(MEMS/TEM/Debye-Callaway),并标注证据等级:
   [F]=文献事实(带 DOI),[I]=跨文献推理(列出参与的 DOI),[H]=假设。
5. **实验方案**:基于上方实验计划,说明每组样品、每次测量的目标变量(SI 单位)、
   温度区间与该测量能证伪哪条假说。
6. **证据链与局限**:汇总上表证据来源,并说明未能解析/缺失的参数对结论的影响。

Report:"""


def _fill(template: str, **tokens: Any) -> str:
    """用 token 替换填充模板。含 JSON 大括号的提示词模板禁用 str.format(会解析大括号)。"""
    out = template
    for key, value in tokens.items():
        out = out.replace("{" + key + "}", str(value))
    return out


HYPOTHESIS_PROMPT_TEMPLATE = """You are a thermoelectricity specialist proposing falsifiable hypotheses for "{material}", grounded ONLY in the Physics Audit Table below.

## Physics Audit Table (deterministically computed)
{audit_table}

## Aggregate evidence gaps
{gaps}

Generate exactly 5 falsifiable hypotheses (H1-H5) about the transport decoupling of {material}.
Each hypothesis MUST be output as a JSON object with EXACTLY these keys:
{
  "statement": "one-sentence quantitative claim",
  "criteria": [
    {"var": "<canonical variable>", "op": "<|<=|>|>=", "value": <number>, "T_K": <number or null>}
  ],
  "evidence_dois": ["DOIs from the audit table supporting this hypothesis"],
  "rationale": "physics reasoning in one sentence"
}
Canonical variables (SI units) you may use in criteria: {variables}.
Rules:
- Every criterion threshold must be a NUMBER derived from or contrasted with the audit table.
- Each hypothesis must have at least one criterion; a hypothesis without numeric criteria is rejected.
- Cite only DOIs present in the audit table.
- Return ONLY a valid JSON array of 5 objects, no prose, no code fences."""


def build_hypothesis_prompt(material: str, audit_table: str,
                            gaps: Dict[str, int]) -> str:
    variables = "; ".join(f"{k} ({v})" for k, v in CANONICAL_VARS.items())
    return _fill(HYPOTHESIS_PROMPT_TEMPLATE,
                 material=material, audit_table=audit_table, gaps=gaps,
                 variables=variables)


EXPERIMENT_PROMPT_TEMPLATE = """You are designing the experiment plan to test the following falsifiable hypotheses about "{material}":

{hypotheses_json}

Design the experiment plan as a JSON object with EXACTLY these keys:
{
  "summary": "one-paragraph strategy",
  "samples": ["sample descriptions: composition, doping series, processing route"],
  "measurements": [
    {"target_var": "<canonical variable>", "technique": "<instrument/method>", "T_range_K": [<low>, <high>]}
  ],
  "hypothesis_refs": ["H1", "H2", ...]
}
Canonical variables (SI units): {variables}.
Rules:
- Every measurement target must be a canonical variable, so results can be verified programmatically.
- The sample matrix and temperature ranges must be sufficient to evaluate EVERY hypothesis cited.
- Techniques must be real, standard methods (e.g. Seebeck/4-probe conductivity, laser flash, Hall effect).
- Return ONLY valid JSON, no prose, no code fences."""


def build_experiment_prompt(material: str, hypotheses: List[Dict[str, Any]]) -> str:
    variables = "; ".join(f"{k} ({v})" for k, v in CANONICAL_VARS.items())
    return _fill(EXPERIMENT_PROMPT_TEMPLATE,
                 material=material,
                 hypotheses_json=json.dumps(hypotheses, ensure_ascii=False, indent=2),
                 variables=variables)


THERMOELECTRIC_PROFILE = DomainProfile(
    name="thermoelectric",
    description="热电材料输运性质(S/σ/κ/zT)的 Wiedemann-Franz 解耦审计与 zT 一致性校验",
    extraction_schema_prompt=EXTRACTION_SCHEMA_PROMPT,
    audit_record=physics.audit_record,
    build_table_md=physics.build_audit_table_md,
    gap_query_hints=GAP_QUERY_HINTS,
    build_synthesis_prompt=build_synthesis_prompt,
    build_hypothesis_prompt=build_hypothesis_prompt,
    build_experiment_prompt=build_experiment_prompt,
)
