"""Day 13 · 向量库：numpy 版（含持久化与元数据过滤）。

理解了这一百行，"向量库"就没有神秘感了：
它不过是"矩阵 + 元数据 + 排序 + 落盘"。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .chunking import Chunk


@dataclass
class SearchHit:
    chunk: Chunk
    score: float

    def __getattr__(self, item: str) -> Any:  # 方便 hit.text / hit.id 直接取
        if item in {"text", "id", "metadata"}:
            return getattr(self.chunk, item)
        raise AttributeError(item)


class NumpyVectorStore:
    """最小可用向量库：内存矩阵 + JSONL 元数据。"""

    def __init__(self, dim: int | None = None):
        self.dim = dim
        self._vectors: np.ndarray | None = None
        self._chunks: list[Chunk] = []

    # -- 写 -------------------------------------------------------------
    def upsert(self, chunks: list[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks 与 vectors 数量不一致")
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim != 2:
            raise ValueError("vectors 应该是二维数组")
        if self._vectors is None:
            self._vectors = arr
            self._chunks = list(chunks)
        else:
            self._vectors = np.vstack([self._vectors, arr])
            self._chunks.extend(chunks)
        self.dim = self._vectors.shape[1]

    def delete(self, ids: Sequence[str] | None = None, where: dict[str, Any] | None = None) -> int:
        keep = []
        removed = 0
        for i, chunk in enumerate(self._chunks):
            match_id = ids is not None and chunk.id in ids
            match_where = where is not None and all(chunk.metadata.get(k) == v for k, v in where.items())
            if match_id or match_where:
                removed += 1
            else:
                keep.append(i)
        if self._vectors is not None:
            self._vectors = self._vectors[keep] if keep else None
        self._chunks = [self._chunks[i] for i in keep]
        return removed

    # -- 读 -------------------------------------------------------------
    def query(self, vector: Sequence[float], k: int = 5, where: dict[str, Any] | None = None) -> list[SearchHit]:
        if self._vectors is None or not len(self._chunks):
            return []
        q = np.asarray(vector, dtype=np.float32)
        q = q / (np.linalg.norm(q) or 1.0)
        mat = self._vectors
        mat = mat / np.clip(np.linalg.norm(mat, axis=1, keepdims=True), 1e-9, None)
        scores = mat @ q

        indices = range(len(self._chunks))
        if where:
            indices = [i for i in indices if all(self._chunks[i].metadata.get(k) == v for k, v in where.items())]
        ranked = sorted(indices, key=lambda i: float(scores[i]), reverse=True)[:k]
        return [SearchHit(self._chunks[i], float(scores[i])) for i in ranked]

    def __len__(self) -> int:
        return len(self._chunks)

    @property
    def chunks(self) -> list[Chunk]:
        """返回全部块（BM25 等需要遍历原文的组件会用到）。"""
        return list(self._chunks)

    # -- 持久化 ----------------------------------------------------------
    def save(self, directory: Path) -> None:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        if self._vectors is not None:
            np.save(directory / "vectors.npy", self._vectors)
        (directory / "chunks.jsonl").write_text(
            "\n".join(
                json.dumps({"id": c.id, "text": c.text, "metadata": c.metadata}, ensure_ascii=False)
                for c in self._chunks
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, directory: Path) -> "NumpyVectorStore":
        directory = Path(directory)
        store = cls()
        path = directory / "vectors.npy"
        if path.exists():
            store._vectors = np.load(path)
            store.dim = store._vectors.shape[1]
        lines = (directory / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
        store._chunks = [Chunk(**json.loads(line)) for line in lines if line.strip()]
        return store


class ChromaStore:
    """Chroma 适配层：接口与 NumpyVectorStore 对齐，方便切换。

    需要 `pip install chromadb`。这里用组合而不是继承，避免把 Chroma 的抽象泄露到业务层。
    """

    def __init__(self, path: str = "./chroma_db", collection: str = "kb", dim: int | None = None):
        import chromadb

        self.client = chromadb.PersistentClient(path=path)
        self.col = self.client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}
        )
        self.dim = dim

    def upsert(self, chunks: list[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        self.col.upsert(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=[list(v) for v in vectors],
            metadatas=[c.metadata for c in chunks],
        )

    def query(self, vector: Sequence[float], k: int = 5, where: dict[str, Any] | None = None) -> list[SearchHit]:
        res = self.col.query(
            query_embeddings=[list(vector)],
            n_results=k,
            where=where or None,
            include=["documents", "metadatas", "distances"],
        )
        hits: list[SearchHit] = []
        for cid, text, meta, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            hits.append(SearchHit(Chunk(id=cid, text=text, metadata=meta or {}), score=1 - float(dist)))
        return hits
