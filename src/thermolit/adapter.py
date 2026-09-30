"""
sciverse_adapter.py — Sciverse API 适配层。

改进点(相对 v0.1,经真实 API 校准):
  - 惰性创建客户端:导入本模块不再需要 token / sciverse 包就绪,便于测试
  - 兼容同步/异步 client(真实 sciverse 0.13.x 的 semantic_search 为 async)
  - 真实命中无 DOI 字段:通过 Crossref 标题→DOI 解析补齐证据锚点
    (difflib 相似度阈值防错配;失败保留 N/A,不阻塞检索主流程)
  - 命中结果归一化:dict/对象属性两种风格;保留 venue/year 元数据
  - 指数退避重试;失败向上传播而不是静默返回空列表
  - 论文去重(按 DOI 优先、标题兜底)
"""
from __future__ import annotations

import asyncio
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from thermolit.config import SCIVERSE_TOKEN, is_configured

try:  # sciverse 为运行时依赖;延迟导入让单元测试可以在未安装时仍然可用
    from sciverse import AgentToolsClient
except ImportError:  # pragma: no cover
    AgentToolsClient = None  # type: ignore[assignment]

_CROSSREF_API = "https://api.crossref.org/works"
_TITLE_SIM_THRESHOLD = 0.60


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", str(title).lower()).strip()


def resolve_doi_by_title(title: str, timeout: float = 15.0) -> Optional[str]:
    """
    Crossref 标题→DOI 解析(免费,无需 key)。
    用 query.title 取 3 个候选,取相似度最高且达到阈值的——
    防止 bibliographic 搜索返回错配论文;网络失败/无匹配返回 None(不阻塞流程)。
    """
    import requests

    if not title or not title.strip():
        return None
    try:
        resp = requests.get(
            _CROSSREF_API,
            params={"query.title": title, "rows": 3,
                    "select": "DOI,title", "mailto": "thermolit-surveyor"},
            timeout=timeout)
        if resp.status_code != 200:
            return None
        items = (resp.json().get("message") or {}).get("items") or []
        norm_query = _norm_title(title)
        best_doi, best_sim = None, 0.0
        for item in items:
            doi = str(item.get("DOI", "") or "").strip()
            crossref_title = " ".join(item.get("title") or [])
            sim = SequenceMatcher(None, norm_query, _norm_title(crossref_title)).ratio()
            if doi and sim > best_sim:
                best_doi, best_sim = doi, sim
        if best_doi and best_sim >= _TITLE_SIM_THRESHOLD:
            return best_doi.lower()
        return None
    except Exception:  # noqa: BLE001 — 解析失败不阻塞检索主流程
        return None


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

        兼容同步/异步两种 client(真实 sciverse 客户端为 async);
        启用 THERMOLIT_CACHE 时按 (query, top_k) 缓存命中列表,重复调研零 API 消耗。
        """
        from thermolit.cache import get_global_cache

        cache = get_global_cache()
        cache_payload = {"query": query, "top_k": top_k}
        if cache is not None:
            cached = cache.get("search", cache_payload)
            if cached is not None:
                return cached

        # 指数退避重试(async 版):单次失败不放弃
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                result = self.client.semantic_search(query=query, top_k=top_k)
                if asyncio.iscoroutine(result):
                    result = await result  # async client(真实 sciverse 0.13.x)
                last_exc = None
                break
            except Exception as e:  # noqa: BLE001
                last_exc = e
                if attempt < 2:
                    await asyncio.sleep(2.0 * (2 ** attempt))
        if last_exc is not None:
            raise last_exc
        res = result

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
            title = str(_get(hit, "title", "Sciverse Hit") or "Sciverse Hit")
            doi = str(_get(hit, "doi", "N/A") or "N/A")
            if doi in ("N/A", "", "none", "None"):
                # 真实命中无 DOI 字段:Crossref 标题解析补齐证据锚点(失败保留 N/A)
                resolved = resolve_doi_by_title(title)
                doi = resolved or "N/A"
            papers.append({
                "title": title,
                "text": text,
                "doi": doi,
                "venue": str(_get(hit, "publication_venue_name_unified", "") or ""),
                "year": _get(hit, "publication_published_year", ""),
                "query_source": query,
            })
        if cache is not None:
            cache.set("search", cache_payload, papers)
        return papers

    def search_sync(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        return asyncio.run(self.semantic_search_async(query, top_k=top_k))
