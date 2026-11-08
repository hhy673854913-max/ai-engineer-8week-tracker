"""Day 11 · 余弦相似度与 top-k。

纯标准库实现（便于理解），另附 numpy 版本（便于生产）。
"""

from __future__ import annotations

import math
from typing import Sequence


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def norm(a: Sequence[float]) -> float:
    return math.sqrt(sum(x * x for x in a))


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """余弦相似度，范围 [-1, 1]。零向量返回 0，避免除零。"""
    if len(a) != len(b):
        raise ValueError(f"维度不一致: {len(a)} vs {len(b)}")
    na, nb = norm(a), norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return dot(a, b) / (na * nb)


def similarity_matrix(vectors: Sequence[Sequence[float]]) -> list[list[float]]:
    n = len(vectors)
    matrix = [[1.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            score = cosine(vectors[i], vectors[j])
            matrix[i][j] = matrix[j][i] = score
    return matrix


def top_k(query: Sequence[float], matrix: Sequence[Sequence[float]], k: int = 3) -> list[tuple[int, float]]:
    """返回 [(下标, 相似度)]，按相似度降序。"""
    scored = [(i, cosine(query, row)) for i, row in enumerate(matrix)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]


def normalize_numpy(vectors):
    """归一化后，余弦相似度 = 点积，一次矩阵乘法即可算完所有 pair。"""
    import numpy as np

    arr = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms
