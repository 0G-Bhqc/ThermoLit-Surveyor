import asyncio
from typing import List, Dict, Any
from sciverse import AgentToolsClient
from config import SCIVERSE_TOKEN

class SciverseAdapter:
    """
    Sciverse API MCP/Skill Adapter
    Provides semantic search and passage retrieval with evidence auditing.
    """
    def __init__(self, token: str = SCIVERSE_TOKEN):
        self.token = token
        self.client = AgentToolsClient(token=self.token)

    async def semantic_search_async(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Executes semantic search over 25M+ full-text passage chunks in Sciverse DB.
        """
        try:
            res = await self.client.semantic_search(query=query, top_k=top_k)
            hits = getattr(res, 'hits', None)
            if hits is None and isinstance(res, dict):
                hits = res.get('hits', [])
            
            papers = []
            if hits:
                for hit in hits:
                    chunk = hit.get('chunk', '')
                    abstract = hit.get('abstract', '')
                    text = f"Chunk: {chunk}\nAbstract: {abstract}"
                    title = hit.get('title', 'Sciverse Hit')
                    doi = hit.get('doi', 'N/A')
                    papers.append({
                        'title': str(title),
                        'text': str(text),
                        'doi': str(doi),
                        'query_source': query
                    })
            return papers
        except Exception as e:
            print(f"[Sciverse API Error] Search failed for query '{query}': {e}")
            return []

    def search_sync(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        return asyncio.run(self.semantic_search_async(query, top_k=top_k))
