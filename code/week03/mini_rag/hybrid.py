"""Day 15 · 混合检索：BM25 + 向量 + RRF + 规则重排。

两路检索的分数不可比（余弦 0-1，BM25 无上界），所以融合只用排名（RRF）。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Sequence

from .bm25 import BM25
from .store import SearchHit


def rrf(rankings: Sequence[Sequence[int]], k: int = 60) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion：只用名次，无需归一化。"""
    scores: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def bm25_search(chunks: list[Any], query: str, k: int = 20) -> list[tuple[int, float]]:
    index = BM25().add([c.text for c in chunks])
    return index.search(query, k=k)


def hybrid_search(
    chunks: list[Any],
    query: str,
    query_vector: Sequence[float],
    vector_query,
    k: int = 20,
) -> list[int]:
    """返回融合后的块下标列表。

    vector_query(vector, k) -> list[SearchHit]（SearchHit 需要能反查下标）
    """
    id_to_index = {c.id: i for i, c in enumerate(chunks)}
    vector_hits = vector_query(query_vector, k)
    vector_ranking = [id_to_index[h.chunk.id] for h in vector_hits if h.chunk.id in id_to_index]
    bm25_ranking = [i for i, _ in bm25_search(chunks, query, k)]
    fused = rrf([vector_ranking, bm25_ranking])
    return [i for i, _ in fused]


def rule_rerank(
    hits: list[SearchHit],
    query: str,
    *,
    now: datetime | None = None,
    w_time: float = 0.15,
    w_title: float = 0.25,
) -> list[SearchHit]:
    """零成本重排：时间新鲜度 + 标题命中加权。

    比"直接上交叉编码器"更值得先试——它几乎不增加延迟。
    """
    now = now or datetime.now()
    terms = [t for t in query.split() if t] or [query]
    for hit in hits:
        title = str(hit.chunk.metadata.get("title") or hit.chunk.metadata.get("section") or "")
        title_bonus = 1.0 if any(t in title for t in terms) else 0.0

        published = hit.chunk.metadata.get("published_at")
        if published:
            try:
                ts = datetime.fromisoformat(str(published))
                hours = max(0.0, (now - ts).total_seconds() / 3600)
                fresh = max(0.0, 1 - hours / (24 * 30))
            except ValueError:
                fresh = 0.5
        else:
            fresh = 0.5

        hit.score = round(
            (1 - w_time - w_title) * hit.score + w_time * fresh + w_title * title_bonus, 4
        )
    return sorted(hits, key=lambda h: h.score, reverse=True)
