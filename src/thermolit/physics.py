"""
physics.py — 物理约束引擎(可计算、可审计)

这里实现 README 宣称的"物理约束驱动参数解耦":
  1. Wiedemann-Franz 解耦:   kappa_e = L * sigma * T,  kappa_l = kappa_tot - kappa_e
  2. 自适应 Lorenz 数:       L 随 |S| 增大而从简并极限 2.44e-8 下降(单抛物带模型趋势的启发式插值)
  3. zT 一致性校验:          zT_calc = S^2 * sigma * T / kappa,与文献报道值比对
  4. 非晶极限筛查:           kappa_l 低于典型非晶下限时标记可疑(Cahill 模型量级的粗筛常数)

所有解析均为"尽力而为 + 显式标注":解析失败的字段不猜测,而是进入 missing 列表,
由上游缺口检索(Pass 2)补齐。单位缺失时仅在量纲有把握的场景(Seebeck 默认 uV/K)
做假设,并在 flags 中注明。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------- 常量 (SI 单位)
# Lorenz 数 (W·Ohm·K^-2):简并极限 (pi^2/3)(kB/e)^2 = 2.44e-8
LORENZ_DEGENERATE = 2.44e-8
# 锚点插值: (|S| in V/K, L in W·Ohm·K^-2),趋势依据单抛物带模型(Snyder & Toberer 2008)
_LORENZ_ANCHORS: List[Tuple[float, float]] = [
    (0.0, 2.44e-8),
    (150e-6, 1.80e-8),
    (300e-6, 1.55e-8),
]
# 典型非晶/最小热导率下限 (W·m^-1·K^-1),用于粗筛不合理 kappa_l(Cahill 模型量级)
AMORPHOUS_KAPPA_FLOOR = 0.25
# zT 一致性判定:计算值与报道值相对偏差超过该阈值即标记(抽取误差也可能致偏,故为"待核"而非"造假")
ZT_MISMATCH_TOLERANCE = 0.30
ROOM_TEMPERATURE_K = 300.0

# ---------------------------------------------------------------- 数值/单位解析
_SUPERSCRIPT_MAP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")
_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _normalize(text: str) -> str:
    """统一 unicode 上标、负号与科学计数写法,便于后续正则。"""
    if not isinstance(text, str):
        text = str(text)
    t = text.translate(_SUPERSCRIPT_MAP)
    t = t.replace("−", "-").replace("–", "-").replace("—", "-")
    # 1.2 ×10^5 / 1.2 x 10 5 / 1.2*10^-4 -> 1.2e5 形式
    t = re.sub(r"(\d)\s*[×xX*]\s*10\s*\^?\s*", r"\1e", t)
    # 裸 10^5 -> 1e5
    t = re.sub(r"(?<![\d.eE])10\s*\^", "1e", t)
    return t


def _first_number(text: str) -> Optional[float]:
    m = _NUMBER_RE.search(_normalize(text))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def parse_seebeck(raw: Any) -> Optional[float]:
    """解析 Seebeck 系数,返回 SI 单位 V/K。无单位时按热电文献惯例假设 uV/K。"""
    if raw is None:
        return None
    t = _normalize(raw)
    v = _first_number(t)
    if v is None:
        return None
    low = t.lower()
    if re.search(r"(µ|μ|u)\s*v\s*[·./]?\s*k", low):
        factor = 1e-6
    elif re.search(r"(?<![a-z])m\s*v\s*[·./]?\s*k", low):
        factor = 1e-3
    elif re.search(r"v\s*[·./]?\s*k", low):
        factor = 1.0
    else:
        factor = 1e-6  # 热电文献惯例:不带单位几乎总是 uV/K
    return v * factor


def parse_sigma(raw: Any) -> Optional[float]:
    """解析电导率或电阻率,返回 SI 单位 S/m。电阻率取倒数。"""
    if raw is None:
        return None
    t = _normalize(raw)
    v = _first_number(t)
    if v is None:
        return None
    if v == 0:
        return None
    low = t.lower()
    # 电阻率 (Ohm·cm 家族)
    if re.search(r"(µ|μ|u)\s*(ω|ohm)", low) and re.search(r"c\s*m", low):
        rho = v * 1e-8  # uOhm·cm -> Ohm·m
        return 1.0 / rho
    if re.search(r"(?<![a-z])m\s*(ω|ohm)", low) and re.search(r"c\s*m", low):
        rho = v * 1e-5  # mOhm·cm -> Ohm·m
        return 1.0 / rho
    if re.search(r"(ω|ohm)", low) and re.search(r"c\s*m", low):
        rho = v * 1e-2  # Ohm·cm -> Ohm·m
        return 1.0 / rho
    # 电导率
    if re.search(r"s\s*[·./]?\s*c\s*m", low):
        return v * 100.0  # S/cm -> S/m
    if re.search(r"s\s*[·./]?\s*m\b", low) or "s/m" in low:
        return v  # S/m
    return None  # 电导率无单位不可猜测


def parse_kappa(raw: Any) -> Optional[float]:
    """解析热导率,返回 SI 单位 W·m^-1·K^-1。"""
    if raw is None:
        return None
    t = _normalize(raw)
    v = _first_number(t)
    if v is None:
        return None
    low = t.lower()
    if re.search(r"(?<![a-z])m\s*w[\s·./()]*c[\s·./()]*m", low):
        return v * 0.1  # mW/cmK -> W/mK
    if re.search(r"w[\s·./()]*c[\s·./()]*m", low):
        return v * 100.0  # W/cmK -> W/mK
    if re.search(r"w[\s·./()]*m", low):
        return v  # W/mK(含 W/(m·K) 括号写法)
    return None


def parse_zt(raw: Any) -> Optional[float]:
    """解析无量纲 zT(取字段中第一个数)。"""
    if raw is None:
        return None
    return _first_number(_normalize(raw))


def parse_temperature(record: Dict[str, Any]) -> Optional[float]:
    """从记录字段中找测量温度(K)。优先显式 temperature_k 字段,其次 '@ 350 K' 句式。"""
    tk = record.get("temperature_k")
    if isinstance(tk, (int, float)) and 2 <= tk <= 2000:
        return float(tk)
    for field in ("zT_value", "seebeck_coefficient", "thermal_conductivity",
                  "electrical_conductivity"):
        raw = record.get(field)
        if not raw:
            continue
        m = re.search(r"@\s*(\d{2,4})\s*k\b", _normalize(raw), re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None


def parse_field_temperature(raw: Any) -> Optional[float]:
    """
    单字段自己的温度:识别 "@ 350 K"、"at 350 K"、"room temperature/RT"。
    这是 P0 修复的核心:不同字段可能在不同温度下测得(如 S@300K、zT@923K),
    统一用一个 T 参与派生计算会造成跨字段温度错配。
    """
    if raw is None:
        return None
    t = _normalize(str(raw))
    m = re.search(r"(?:@|\bat)\s*(\d{2,4})\s*k\b", t, re.IGNORECASE)
    if m:
        v = float(m.group(1))
        if 2 <= v <= 2000:
            return v
    if re.search(r"room\s*temp|(^|\W)rt(\W|$)", t, re.IGNORECASE):
        return ROOM_TEMPERATURE_K
    return None


# ---------------------------------------------------------------- 物理计算
def lorenz_from_seebeck(seebeck_si: Optional[float]) -> float:
    """自适应 Lorenz 数:|S| 越大越非简并,L 越小(锚点线性插值,两端截断)。"""
    if seebeck_si is None:
        return LORENZ_DEGENERATE
    s_abs = abs(seebeck_si)
    anchors = _LORENZ_ANCHORS
    if s_abs <= anchors[0][0]:
        return anchors[0][1]
    if s_abs >= anchors[-1][0]:
        return anchors[-1][1]
    for (s0, l0), (s1, l1) in zip(anchors, anchors[1:]):
        if s0 <= s_abs <= s1:
            frac = (s_abs - s0) / (s1 - s0)
            return l0 + frac * (l1 - l0)
    return LORENZ_DEGENERATE


def zT_from_components(seebeck_si: float, sigma_si: float, t_k: float,
                       kappa_tot_si: float) -> Optional[float]:
    """zT = S^2 * sigma * T / kappa_total。"""
    if not all(isinstance(x, (int, float)) and x > 0 for x in (sigma_si, t_k, kappa_tot_si)):
        return None
    if seebeck_si is None:
        return None
    return seebeck_si ** 2 * sigma_si * t_k / kappa_tot_si


def fmt(value: Optional[float], digits: int = 3) -> str:
    """表格展示格式化。"""
    if value is None:
        return "—"
    if value == 0:
        return "0"
    if abs(value) >= 1e4 or abs(value) < 1e-3:
        return f"{value:.2e}"
    return f"{round(value, digits):g}"


# ---------------------------------------------------------------- 单条记录物理审计
def audit_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    对单条抽取记录执行物理解耦与一致性校验(逐字段温度感知)。

    返回字段:
      S_si / sigma_si / kappa_si / T_K / zT_reported:解析后的 SI 值(缺失为 None)
      T_S / T_sigma / T_kappa / T_zT:各字段自己的温度(P0 修复:跨字段可能不同)
      lorenz_used / kappa_e / kappa_l / zT_calc:派生物理量(缺失为 None;
        zT_calc 仅在 S/σ/κ 同温时计算,κ_l 仅在 σ/κ 同温时计算)
      flags:物理解析/一致性/温度混计/证据未核实标记
      missing:未能解析的规范参数名(驱动 Pass 2 缺口检索)
    """
    s_si = parse_seebeck(record.get("seebeck_coefficient"))
    sigma_si = parse_sigma(record.get("electrical_conductivity"))
    kappa_si = parse_kappa(record.get("thermal_conductivity"))
    zt_rep = parse_zt(record.get("zT_value"))

    base_t = record.get("temperature_k")
    base_t = float(base_t) if isinstance(base_t, (int, float)) and 2 <= base_t <= 2000 else None
    t_s = parse_field_temperature(record.get("seebeck_coefficient")) or base_t
    t_sigma = parse_field_temperature(record.get("electrical_conductivity")) or base_t
    t_kappa = parse_field_temperature(record.get("thermal_conductivity")) or base_t
    t_zt = parse_field_temperature(record.get("zT_value")) or base_t

    flags: List[str] = []
    missing: List[str] = []

    if s_si is None:
        missing.append("seebeck_coefficient")
    if sigma_si is None:
        missing.append("electrical_conductivity")
    if kappa_si is None:
        missing.append("thermal_conductivity")
    if zt_rep is None:
        missing.append("zT_value")

    # 派生计算仅在输运值同温时进行;跨字段混温 → 标记并拒绝计算(P0-1)
    known_temps = [t for t in (t_s, t_sigma, t_kappa) if t is not None]
    mixed = len(set(known_temps)) > 1
    calc_t = known_temps[0] if known_temps else (base_t or ROOM_TEMPERATURE_K)

    lorenz = lorenz_from_seebeck(s_si)
    eff_sigma_t = t_sigma or calc_t
    kappa_e = lorenz * sigma_si * eff_sigma_t if sigma_si is not None else None
    kappa_l = (kappa_si - kappa_e) \
        if (kappa_si is not None and kappa_e is not None
            and (t_kappa or eff_sigma_t) == (t_sigma or eff_sigma_t)) else None
    zt_calc = None
    if all(v is not None for v in (s_si, sigma_si, kappa_si)) and not mixed:
        zt_calc = zT_from_components(s_si, sigma_si, calc_t, kappa_si)
    if mixed:
        detail = "/".join(f"{t:.0f}K" for t in known_temps)
        flags.append(f"字段温度混计({detail}),跨温派生量已拒绝计算")

    if kappa_l is not None and kappa_l <= 0:
        flags.append("kappa_l_negative(Lorenz过高或抽取单位有误)")
    elif kappa_l is not None and kappa_l < AMORPHOUS_KAPPA_FLOOR:
        flags.append("kappa_l低于非晶下限(粗筛,待核)")

    if zt_calc is not None and zt_rep is not None and zt_rep > 0:
        if t_zt is not None and t_zt != calc_t:
            flags.append(f"zT报道温度({t_zt:.0f}K)与计算温度({calc_t:.0f}K)不一致,未做偏差判定")
        else:
            rel = abs(zt_calc - zt_rep) / zt_rep
            if rel > ZT_MISMATCH_TOLERANCE:
                flags.append(f"zT不一致(计算{zt_calc:.2f} vs 报道{zt_rep:.2f},偏差{rel:.0%})")
    elif zt_rep is not None and t_zt is not None and known_temps \
            and t_zt != calc_t:
        flags.append(f"zT报道@{t_zt:.0f}K(与输运值温度{calc_t:.0f}K不同)")

    # 字段有文本但解析失败 → 单位/写法问题,标记出来供人工复核
    _FIELD_OF = {"seebeck": ("seebeck_coefficient", s_si),
                 "sigma": ("electrical_conductivity", sigma_si),
                 "kappa": ("thermal_conductivity", kappa_si)}
    for _label, (record_field, parsed) in _FIELD_OF.items():
        if record.get(record_field) and parsed is None:
            flags.append(f"{record_field}字段存在但无法解析(单位/写法)")

    # 证据句包含校验结果透传为标记(P0-2,由 schemas.check_evidence 在抽取时判定)
    ev = record.get("evidence_check") or {}
    if ev.get("unverified"):
        flags.append(f"证据句未核实({len(ev['unverified'])}条): {', '.join(ev['unverified'])}")

    t_k_out = known_temps[0] if known_temps else (t_zt or base_t or ROOM_TEMPERATURE_K)
    return {
        "title": record.get("title", ""),
        "doi": record.get("doi", "N/A"),
        "material_system": record.get("material_system"),
        "S_si_V_per_K": s_si,
        "sigma_si_S_per_m": sigma_si,
        "kappa_si_W_per_mK": kappa_si,
        "T_K": t_k_out,
        "T_S": t_s,
        "T_sigma": t_sigma,
        "T_kappa": t_kappa,
        "T_zT": t_zt,
        "zT_reported": zt_rep,
        "zT_calc": zt_calc,
        "lorenz_used": lorenz if sigma_si is not None else None,
        "kappa_e": kappa_e,
        "kappa_l": kappa_l,
        "flags": flags,
        "missing": missing,
    }


def audit_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """批量审计;保留输入顺序,错误记录(含 error 键)直接透传标记。"""
    out = []
    for rec in records:
        if "error" in rec:
            out.append({**rec, "flags": ["extraction_failed"], "missing": []})
            continue
        out.append(audit_record(rec))
    return out


def aggregate_missing(audits: List[Dict[str, Any]]) -> Dict[str, int]:
    """统计各规范参数的缺失次数,用于缺口检索排序。"""
    counts: Dict[str, int] = {}
    for a in audits:
        for m in a.get("missing", []):
            counts[m] = counts.get(m, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def build_audit_table_md(audits: List[Dict[str, Any]]) -> str:
    """生成 Markdown 物理审计表(报告的数值以此表为准,而非 LLM 自由生成)。"""
    header = (
        "| # | 材料 (DOI) | S (µV/K) | σ (S/cm) | κ_tot (W/mK) | T (K) "
        "| zT报道 | zT计算 | κ_e (W/mK) | κ_l (W/mK) | 标记 |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|"
    )
    rows = []
    for i, a in enumerate(audits, 1):
        if "error" in a or "extraction_failed" in a.get("flags", []):
            rows.append(f"| {i} | {a.get('title', '')[:40]} (DOI: {a.get('doi', 'N/A')}) "
                        f"| — | — | — | — | — | — | — | — | 抽取失败 |")
            continue
        s_uv = a["S_si_V_per_K"] * 1e6 if a["S_si_V_per_K"] is not None else None
        sigma_scm = a["sigma_si_S_per_m"] / 100.0 if a["sigma_si_S_per_m"] is not None else None
        mat = a.get("material_system") or "—"
        rows.append(
            f"| {i} | {mat[:24]} ({a['doi']}) "
            f"| {fmt(s_uv)} | {fmt(sigma_scm)} | {fmt(a['kappa_si_W_per_mK'])} "
            f"| {fmt(a['T_K'], 0)} | {fmt(a['zT_reported'], 2)} | {fmt(a['zT_calc'], 2)} "
            f"| {fmt(a['kappa_e'])} | {fmt(a['kappa_l'])} "
            f"| {'; '.join(a['flags']) or '✓'} |"
        )
    return "\n".join([header] + rows) if rows else header + "\n|(无可用记录)|"
