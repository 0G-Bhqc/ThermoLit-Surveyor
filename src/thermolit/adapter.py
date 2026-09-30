"""
sciverse_adapter.py — Sciverse API 适配层。

改进点(相对 v0.1):
  - 惰性创建客户端:导入本模块不再需要 token / sciverse 包就绪,便于测试
  - 命中结果归一化:同时兼容 dict 与对象属性两种返回风格
  - 带指数退避的重试;超时/失败向上传播,而不是静默返回空列表
  - 论文去重(按 DOI 优先、标题兜底)
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from thermolit.config import SCIVERSE_TOKEN, is_configured
from thermolit.json_utils import with_retries

try:  # sciverse 为运行时依赖;延迟导入让单元测试可以在未安装时仍然可用
    from sciverse import AgentToolsClient
except ImportError:  # pragma: no cover
    AgentToolsClient = None  # type: ignore[assignment]


class SciverseNotConfiguredError(RuntimeError):
    pass


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """兼容 dict / 对象属性两种命中风格。"""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def dedup_papers(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按 DOI(规范化)去重;无 DOI 时按小写标题去重。保持首次出现顺序。"""
    seen_doi, seen_title, out = set(), set(), []
    for p in papers:
        doi = str(p.get("doi", "N/A")).strip().lower().removeprefix("https://doi.org/")
        title = str(p.get("title", "")).strip().lower()
        if doi not in ("n/a", "", "none") and doi not in seen_doi:
            seen_doi.add(doi)
            out.append(p)
        elif doi in ("n/a", "", "none"):
            if title and title in seen_title:
                continue
            if title:
                seen_title.add(title)
            out.append(p)
    return out


class SciverseAdapter:
    """Sciverse API MCP/Skill Adapter:语义检索 + 全文段落证据。"""

    def __init__(self, token: str = SCIVERSE_TOKEN):
        self.token = token
        self._client: Optional[Any] = None

    @property
    def client(self) -> Any:
        if self._client is None:
            if AgentToolsClient is None:
                raise SciverseNotConfiguredError(
                    "sciverse 包未安装:请先 `pip install sciverse==0.13.1`")
            if not is_configured(self.token):
                raise SciverseNotConfiguredError(
                    "SCIVERSE_TOKEN 未配置:请在 .env 或环境变量中设置")
            self._client = AgentToolsClient(token=self.token)
        return self._client

    async def semantic_search_async(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """对 25M+ 全文段落块做语义检索,返回标准化论文段落列表。失败时抛异常由调用方决定降级策略。

        启用 THERMOLIT_CACHE 时按 (query, top_k) 缓存命中列表,重复调研零 API 消耗。
        """
        from thermolit.cache import get_global_cache

        cache = get_global_cache()
        cache_payload = {"query": query, "top_k": top_k}
        if cache is not None:
            cached = cache.get("search", cache_payload)
            if cached is not None:
                return cached

        def _call():
            return self.client.semantic_search(query=query, top_k=top_k)

        res = await asyncio.to_thread(with_retries, _call, 3, 2.0,
                                      (Exception,), f"Sciverse search '{query[:40]}'")

        hits = _get(res, "hits", None)
        if hits is None and isinstance(res, dict):
            hits = res.get("hits", [])

        papers: List[Dict[str, Any]] = []
        for hit in hits or []:
            chunk = str(_get(hit, "chunk", "") or "")
            abstract = str(_get(hit, "abstract", "") or "")
            text = f"Chunk: {chunk}\nAbstract: {abstract}".strip()
            if not text:
                continue
            papers.append({
                "title": str(_get(hit, "title", "Sciverse Hit") or "Sciverse Hit"),
                "text": text,
                "doi": str(_get(hit, "doi", "N/A") or "N/A"),
                "query_source": query,
            })
        if cache is not None:
            cache.set("search", cache_payload, papers)
        return papers

    def search_sync(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        return asyncio.run(self.semantic_search_async(query, top_k=top_k))
