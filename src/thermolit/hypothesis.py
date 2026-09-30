"""
hypothesis.py — 可证伪假说的结构化对象与确定性回验引擎。

延续本项目的不变式:**假说是否被支持/驳倒,由代码判定,不由 LLM 判定**。

研究闭环的四个环节:
  1. 调研审计(已有):文献数值 → 《Physics Audit Table》
  2. 假说生成(hypothesize 节点):LLM 依审计表提出假说,但判据必须是
     *规范变量 + 数值阈值* 的结构化对象,由 `normalize_hypotheses` 确定性校验
  3. 实验设计(design_experiments 节点):LLM 拟方案,`normalize_experiment_plan`
     确定性校验(测量目标必须是规范变量、假说引用必须存在)
  4. 回验(本模块 `evaluate_hypotheses`):实验测得值(SI)→ 逐判据比较 →
     supported / refuted / inconclusive;inconclusive 的缺失变量
     直接回流为下一轮调研缺口(闭环)

规范变量集合(CANONICAL_VARS)是文献抽取与实验测量共用的"数值语言"。
"""
from __future__ import annotations

import operator
from typing import Any, Dict, List, Optional, Tuple

OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}

CANONICAL_VARS: Dict[str, str] = {
    "S": "Seebeck coefficient (V/K)",
    "sigma": "electrical conductivity (S/m)",
    "kappa": "total thermal conductivity (W/mK)",
    "kappa_e": "electronic thermal conductivity (W/mK)",
    "kappa_l": "lattice thermal conductivity (W/mK)",
    "zT": "dimensionless figure of merit",
    "PF": "power factor S^2*sigma (W/mK^2)",
    "n": "carrier concentration (m^-3)",
    "mu": "carrier mobility (m^2/Vs)",
    "T_K": "temperature (K)",
}

# 温度条件判定允许的测量温度偏差(K)
_T_TOLERANCE_K = 10.0


# ---------------------------------------------------------------- 派生变量
def derive_variables(measurements: Dict[str, Any]) -> Dict[str, Any]:
    """
    从测量值派生可计算的规范变量,缺输入则保持缺失:
      PF = S²σ;  zT = S²σT/κ;
      κ_e = L(S)·σ·T(Wiedemann-Franz,与审计引擎同源自适应 Lorenz 数);
      κ_l = κ_tot − κ_e(或 κ_e = κ_tot − κ_l 反推)。
    """
    from thermolit.physics import lorenz_from_seebeck

    m = {k: v for k, v in measurements.items() if k in CANONICAL_VARS}
    s, sigma, t, kappa = m.get("S"), m.get("sigma"), m.get("T_K"), m.get("kappa")
    if m.get("PF") is None and s is not None and sigma:
        m["PF"] = s ** 2 * sigma
    if m.get("zT") is None and None not in (s, sigma, t, kappa) and kappa:
        m["zT"] = s ** 2 * sigma * t / kappa
    if m.get("kappa_e") is None and None not in (s, sigma, t):
        m["kappa_e"] = lorenz_from_seebeck(s) * sigma * t
    if m.get("kappa_l") is None and None not in (m.get("kappa_e"), kappa):
        m["kappa_l"] = kappa - m["kappa_e"]
    if m.get("kappa_e") is None and None not in (m.get("kappa_l"), kappa):
        m["kappa_e"] = kappa - m["kappa_l"]
    return m


# ---------------------------------------------------------------- 回验
def _check_criterion(c: Dict[str, Any], m: Dict[str, Any]) -> Tuple[Optional[bool], Optional[str]]:
    """单判据判定:返回 (pass/fail/None, 说明)。None 表示不可判定。"""
    var, op = c["var"], c["op"]
    measured = m.get(var)
    if measured is None:
        return None, f"missing:{var}"
    t_req = c.get("T_K")
    if t_req is not None:
        t_meas = m.get("T_K")
        if t_meas is None:
            return None, f"missing:T_K(判据要求 {t_req} K)"
        if abs(t_meas - t_req) > _T_TOLERANCE_K:
            return None, f"温度不符(判据要求 {t_req} K,测量 {t_meas} K)"
    return OPS[op](measured, c["value"]), None


def evaluate_hypotheses(hypotheses: List[Dict[str, Any]],
                        measurements: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    确定性回验:对每个假说逐判据比较,给出状态与缺失变量。

    状态规则:
      - 任一已判定判据 fail           → refuted(假说被驳倒)
      - 全部已判定且无缺失            → supported
      - 其余(有判据无法判定)        → inconclusive,缺失变量回流为调研缺口
    """
    m = derive_variables(measurements)
    out: List[Dict[str, Any]] = []
    for h in hypotheses:
        criterion_results: List[Dict[str, Any]] = []
        missing: List[str] = []
        for c in h.get("criteria", []):
            ok, note = _check_criterion(c, m)
            if ok is None:
                missing.append(note or c["var"])
            else:
                criterion_results.append({
                    "var": c["var"], "op": c["op"], "threshold": c["value"],
                    "T_K": c.get("T_K"),
                    "measured": m[c["var"]],
                    "pass": bool(ok),
                })
        evaluated = criterion_results
        any_fail = any(not r["pass"] for r in evaluated)
        if evaluated and not missing and not any_fail:
            status = "supported"
        elif any_fail:
            status = "refuted"
        else:
            status = "inconclusive"
        out.append({
            "id": h.get("id", "?"),
            "statement": h.get("statement", ""),
            "status": status,
            "criteria_results": criterion_results,
            "missing": missing,
        })
    return out


# 测量规范变量 → 文献抽取字段名(回流缺口时桥接到 profile.gap_query_hints)
MEASUREMENT_TO_FIELD = {
    "S": "seebeck_coefficient",
    "sigma": "electrical_conductivity",
    "kappa": "thermal_conductivity",
    "kappa_e": "thermal_conductivity",
    "kappa_l": "thermal_conductivity",
    "zT": "zT_value",
    "PF": "seebeck_coefficient",
    "n": "carrier_concentration",
    "mu": "mobility",
}


def missing_to_gap_queries(evaluations: List[Dict[str, Any]],
                           gap_query_hints: Dict[str, str]) -> List[str]:
    """把回验中缺失的规范变量转成下一轮调研的定向查询(闭环出口)。"""
    fields_needed: List[str] = []
    for ev in evaluations:
        for note in ev.get("missing", []):
            var = note.replace("missing:", "").split("(")[0].strip()
            field = MEASUREMENT_TO_FIELD.get(var)
            if field and field not in fields_needed:
                fields_needed.append(field)
    queries = []
    for field in fields_needed:
        hint = gap_query_hints.get(field, field)
        queries.append(hint if hint != field else f"{field} measurement")
    return queries


# ---------------------------------------------------------------- LLM 输出的确定性归一化
def normalize_hypotheses(raw: Any, known_dois: Optional[set] = None,
                         max_n: int = 5) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    把 LLM 生成的假说 JSON 归一化为结构化对象,并做确定性校验:
      - 判据变量必须在 CANONICAL_VARS 中(防止幻觉变量)
      - 阈值必须可转为 float
      - 无有效判据的假说整体剔除(不可证伪 = 不可收)
      - 引用了审计表之外 DOI 的假说打 unverified_dois 标记
    返回 (假说列表, 警告列表)。
    """
    known_dois = known_dois or set()
    hypotheses: List[Dict[str, Any]] = []
    warnings: List[str] = []
    if not isinstance(raw, list):
        return [], ["假说生成输出不是 JSON 数组,已丢弃"]
    for i, item in enumerate(raw[:max_n], 1):
        hid = f"H{i}"
        if not isinstance(item, dict):
            warnings.append(f"{hid}: 非 JSON 对象,已跳过")
            continue
        statement = str(item.get("statement", "")).strip()
        if not statement:
            warnings.append(f"{hid}: 缺少 statement,已跳过")
            continue
        criteria: List[Dict[str, Any]] = []
        for c in item.get("criteria", []) or []:
            if not isinstance(c, dict):
                continue
            var, op, value = c.get("var"), c.get("op"), c.get("value")
            if var not in CANONICAL_VARS:
                warnings.append(f"{hid}: 未知变量 '{var}',判据已剔除")
                continue
            if op not in OPS:
                warnings.append(f"{hid}: 非法比较符 '{op}',判据已剔除")
                continue
            try:
                value = float(value)
            except (TypeError, ValueError):
                warnings.append(f"{hid}: 阈值 '{value}' 不是数值,判据已剔除")
                continue
            entry: Dict[str, Any] = {"var": var, "op": op, "value": value}
            if c.get("T_K") is not None:
                try:
                    entry["T_K"] = float(c["T_K"])
                except (TypeError, ValueError):
                    warnings.append(f"{hid}: T_K '{c.get('T_K')}' 非数值,忽略温度条件")
            criteria.append(entry)
        if not criteria:
            warnings.append(f"{hid}: 无有效判据(不可证伪),已剔除")
            continue
        hyp: Dict[str, Any] = {
            "id": hid,
            "statement": statement,
            "criteria": criteria,
            "evidence_dois": [d for d in (item.get("evidence_dois") or [])
                              if isinstance(d, str)],
            "rationale": str(item.get("rationale", "")).strip(),
        }
        unverified = [d for d in hyp["evidence_dois"] if known_dois and d not in known_dois]
        if unverified:
            hyp["unverified_dois"] = unverified
            warnings.append(f"{hid}: 引用了审计表之外的 DOI {unverified},已标记")
        hypotheses.append(hyp)
    return hypotheses, warnings


def normalize_experiment_plan(raw: Any, hypotheses: List[Dict[str, Any]]
                              ) -> Tuple[Dict[str, Any], List[str]]:
    """
    把 LLM 生成的实验方案 JSON 归一化并确定性校验:
      - 引用的假说 id 必须存在
      - 测量目标 target_var 必须是规范变量(保证回验可自动判定)
    返回 (方案, 警告)。
    """
    warnings: List[str] = []
    if not isinstance(raw, dict):
        return {}, ["实验方案输出不是 JSON 对象,已丢弃"]
    valid_ids = {h["id"] for h in hypotheses}

    measurements: List[Dict[str, Any]] = []
    for meas in raw.get("measurements", []) or []:
        if not isinstance(meas, dict):
            continue
        target = meas.get("target_var")
        if target not in CANONICAL_VARS:
            warnings.append(f"测量目标 '{target}' 不是规范变量,已剔除")
            continue
        entry: Dict[str, Any] = {
            "target_var": target,
            "technique": str(meas.get("technique", "")),
        }
        trange = meas.get("T_range_K")
        if isinstance(trange, list) and len(trange) == 2:
            try:
                entry["T_range_K"] = [float(trange[0]), float(trange[1])]
            except (TypeError, ValueError):
                warnings.append(f"测量 {target}: T_range_K 非法,已忽略")
        measurements.append(entry)

    refs = [r for r in (raw.get("hypothesis_refs") or []) if isinstance(r, str)]
    unknown = [r for r in refs if r not in valid_ids]
    if unknown:
        warnings.append(f"方案引用了不存在的假说: {unknown},已剔除")
    return {
        "summary": str(raw.get("summary", "")),
        "samples": [str(s) for s in (raw.get("samples") or []) if isinstance(s, (str, dict))],
        "measurements": measurements,
        "hypothesis_refs": [r for r in refs if r in valid_ids],
    }, warnings
