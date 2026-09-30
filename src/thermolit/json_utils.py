"""
json_utils.py — LLM 输出的健壮 JSON 提取与通用重试。

替代旧的 `.strip("```json")` 写法(那是逐字符剥离,会破坏 JSON 内容)。
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Iterable, Optional, Tuple, Type

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Optional[Any]:
    """
    从 LLM 输出中提取第一个合法 JSON 值(对象或数组)。
    处理:代码围栏、前后解释性文字、尾随逗号容错。失败返回 None。

    顶层结构按首个非空白字符判定([ 开头优先按数组截取,否则按对象):
    否则 `[{"a": 1}]` 会被先按大括号截成单个对象,丢失数组语义。
    """
    if text is None:
        return None
    candidates: Iterable[str] = []
    m = _FENCE_RE.search(text)
    if m:
        candidates = (m.group(1), text)
    else:
        candidates = (text,)

    for cand in candidates:
        # 先整体尝试(最常见:输出本身就是纯 JSON)
        stripped = cand.strip()
        try:
            return json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            pass
        # 截取:按两种括号首次出现的先后决定优先级(兼容 prose 前缀)
        first_obj, first_arr = cand.find("{"), cand.find("[")
        if first_arr != -1 and (first_obj == -1 or first_arr < first_obj):
            pairs = (("[", "]"), ("{", "}"))
        else:
            pairs = (("{", "}"), ("[", "]"))
        for start_ch, end_ch in pairs:
            start = cand.find(start_ch)
            end = cand.rfind(end_ch)
            if start != -1 and end > start:
                snippet = cand[start:end + 1]
                for attempt in (snippet, re.sub(r",\s*([}\]])", r"\1", snippet)):
                    try:
                        return json.loads(attempt)
                    except (json.JSONDecodeError, ValueError):
                        continue
    return None


def with_retries(fn: Callable[[], Any], attempts: int = 3, base_delay: float = 2.0,
                 exceptions: Tuple[Type[BaseException], ...] = (Exception,),
                 description: str = "operation") -> Any:
    """简单指数退避重试(避免引入额外依赖)。全部失败时抛出最后一次异常。"""
    last_exc: Optional[BaseException] = None
    for i in range(attempts):
        try:
            return fn()
        except exceptions as e:  # noqa: PERF203
            last_exc = e
            if i < attempts - 1:
                delay = base_delay * (2 ** i)
                print(f"[retry] {description} failed ({e}); retry {i + 2}/{attempts} in {delay:.1f}s")
                time.sleep(delay)
    assert last_exc is not None
    raise last_exc
