"""
cache.py — 结果缓存:LLM 调用与检索结果的 SQLite 缓存。

目的:同一 (prompt, model) 或同一 (query, top_k) 的重复调研零 API 消耗——
评测迭代、金标扩充、演示复跑时不再重复计费。

启用方式(默认关闭):设置环境变量 THERMOLIT_CACHE 为 sqlite 文件路径。
  THERMOLIT_CACHE=eval/cache/runs.db

设计:
  * key = sha1(kind + 规范化 payload),kind 区分 "llm" / "search";
  * LLM 缓存只存响应文本(temperature=0 幂等);命中不计入 token 计量;
  * 检索缓存存整段命中列表;
  * 全局单例按路径惰性创建,线程安全(SQLite check_same_thread=False + 写锁)。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from typing import Any, Dict, Optional


class ResultCache:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
        self.conn.commit()

    @staticmethod
    def make_key(kind: str, payload: Any) -> str:
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return f"{kind}:{hashlib.sha1(blob.encode('utf-8')).hexdigest()}"

    def get(self, kind: str, payload: Any) -> Optional[Any]:
        with self._lock:
            row = self.conn.execute(
                "SELECT v FROM cache WHERE k=?", (self.make_key(kind, payload),)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def set(self, kind: str, payload: Any, value: Any) -> None:
        blob = json.dumps(value, ensure_ascii=False)
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO cache (k, v) VALUES (?, ?)",
                (self.make_key(kind, payload), blob))
            self.conn.commit()

    def clear(self) -> int:
        with self._lock:
            n = self.conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            self.conn.execute("DELETE FROM cache")
            self.conn.commit()
        return n


_global_cache: Optional[ResultCache] = None
_global_cache_path: Optional[str] = None


def get_global_cache() -> Optional[ResultCache]:
    """按 THERMOLIT_CACHE 环境变量惰性创建全局缓存;未设置返回 None。"""
    global _global_cache, _global_cache_path
    from thermolit.config import THERMOLIT_CACHE

    if not THERMOLIT_CACHE:
        return None
    if _global_cache is None or _global_cache_path != THERMOLIT_CACHE:
        from pathlib import Path

        parent = Path(THERMOLIT_CACHE).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        _global_cache = ResultCache(THERMOLIT_CACHE)
        _global_cache_path = THERMOLIT_CACHE
    return _global_cache


class _CachedLLM:
    """invoke 代理:命中缓存直接返回,未命中调用内层并回填(只缓存文本)。"""

    def __init__(self, inner: Any, cache: ResultCache, model: str,
                 stats: Optional[Dict[str, int]] = None):
        self._inner = inner
        self._cache = cache
        self._model = model
        self._stats = stats if stats is not None else {"llm_cache_hits": 0,
                                                       "llm_cache_misses": 0}

    def invoke(self, messages, **kwargs):
        payload = {"model": self._model, "prompt": messages[0].content}
        hit = self._cache.get("llm", payload)
        if hit is not None:
            self._stats["llm_cache_hits"] += 1

            class _Cached:  # 最小消息 duck-type:节点只用 .content
                content = hit

            return _Cached()
        self._stats["llm_cache_misses"] += 1
        res = self._inner.invoke(messages, **kwargs)
        self._cache.set("llm", payload, res.content)
        return res
