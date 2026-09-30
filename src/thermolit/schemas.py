"""
schemas.py — 抽取结果的 Pydantic 契约。

结构化输出分两层:
  1. 提示词层约束 LLM 输出 JSON(profile.extraction_schema_prompt);
  2. 本模块用 Pydantic 做确定性校验,校验失败把错误信息回喂给 LLM 重试一次。
     (不依赖端点的 response_format/json_schema——各家兼容程度不一,校验永远在本地)

evidence_sentences 是句子级证据引用:每个非 null 参数,LLM 必须同时给出
摘录原文的完整句子,使每个数值可回溯到原文(可审计性的最后一公里)。
"""
from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

EXTRACTION_VALUE_FIELDS = (
    "material_system", "zT_value", "seebeck_coefficient",
    "thermal_conductivity", "electrical_conductivity",
    "carrier_concentration", "mobility", "key_claim",
)


class ExtractionRecord(BaseModel):
    """单篇文献段落的结构化抽取结果。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    material_system: Optional[str] = None
    zT_value: Optional[str] = None
    seebeck_coefficient: Optional[str] = None
    thermal_conductivity: Optional[str] = None
    electrical_conductivity: Optional[str] = None
    carrier_concentration: Optional[str] = None
    mobility: Optional[str] = None
    temperature_k: Optional[float] = None
    key_claim: Optional[str] = None
    evidence_sentences: Dict[str, str] = Field(default_factory=dict)


def validate_extraction(data: object) -> tuple[Optional[dict], Optional[str]]:
    """
    校验 LLM 抽取输出。
    返回 (规范化 dict, None) 或 (None, 错误说明)——错误说明用于回喂重试。
    """
    if not isinstance(data, dict):
        return None, f"输出必须是 JSON 对象,得到 {type(data).__name__}"
    try:
        record = ExtractionRecord.model_validate(data)
    except ValidationError as e:
        details = "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
                            for err in e.errors()[:5])
        return None, f"schema 校验失败({len(e.errors())} 处): {details}"
    return record.model_dump(), None
