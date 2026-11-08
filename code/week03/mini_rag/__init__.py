"""mini-RAG：一个 400 行以内、无框架依赖的 RAG 实现。

模块划分对应第 3 周的五天课程：
    similarity  Day 11  余弦相似度与 top-k
    chunking    Day 12  三种分块器
    store       Day 13  向量库（numpy 版 + Chroma 适配）
    rag         Day 14  完整链路与引用溯源
    hybrid      Day 15  BM25 + RRF + 重排
    evaluate    Day 15  评测指标
"""

from .chunking import Chunk, chunk_by_heading, chunk_fixed, chunk_recursive
from .hybrid import bm25_search, rrf, rule_rerank
from .similarity import cosine, similarity_matrix, top_k
from .store import NumpyVectorStore, SearchHit

__all__ = [
    "Chunk",
    "NumpyVectorStore",
    "SearchHit",
    "bm25_search",
    "chunk_by_heading",
    "chunk_fixed",
    "chunk_recursive",
    "cosine",
    "rrf",
    "rule_rerank",
    "similarity_matrix",
    "top_k",
]
