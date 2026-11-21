"""Day 11 · 余弦相似度与 top-k。

纯标准库实现（便于理解 + 面试白板复现），另附 numpy 版本（便于生产 + 性能对比）。

核心知识链：
    1. embedding 把文本变成固定维度向量（原料）
    2. 余弦相似度 = 点积 / (|a|×|b|)，只看方向不看长度（尺子）
    3. L2 归一化后 |a|=|b|=1，余弦 = 点积，可用矩阵乘法批量算
    4. top-k 检索 = 排序取前 k 个，是 RAG 召回的全部数学基础
"""

from __future__ import annotations

import math
from typing import Sequence


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    """向量点积：对应分量相乘后求和。

    数学定义：a·b = Σ a_i × b_i
    几何意义：衡量两个向量在方向上的"投影重叠程度"。
    """
    return sum(x * y for x, y in zip(a, b))


def norm(a: Sequence[float]) -> float:
    """L2 范数（欧几里得长度）：|a| = √(Σ a_i²)。"""
    return math.sqrt(sum(x * x for x in a))


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """余弦相似度，范围 [-1, 1]，越接近 1 越相似。

    公式：cos(a, b) = (a·b) / (|a| × |b|)

    为什么用余弦而不是欧氏距离？
    - 文本向量长度受词数、停用词影响，方向才反映语义主题
    - 余弦把长度归一化，"退款" 和 "请问怎么申请退款呢" 才能拿到高分

    零向量返回 0.0，避免除零崩溃（实际 embedding 不会出现零向量，防御性编程）。
    """
    if len(a) != len(b):
        raise ValueError(f"维度不一致: {len(a)} vs {len(b)}")
    na, nb = norm(a), norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return dot(a, b) / (na * nb)


def similarity_matrix(vectors: Sequence[Sequence[float]]) -> list[list[float]]:
    """计算所有向量两两之间的余弦相似度，返回 n×n 对称矩阵。

    对角线初始化为 1.0（自己和自己的相似度），
    利用对称性只算上三角，然后镜像到下三角，节省一半计算。
    """
    n = len(vectors)
    matrix = [[1.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            score = cosine(vectors[i], vectors[j])
            matrix[i][j] = matrix[j][i] = score
    return matrix


def top_k(query: Sequence[float], matrix: Sequence[Sequence[float]], k: int = 3) -> list[tuple[int, float]]:
    """对 query 和 matrix 中每一行计算余弦相似度，返回前 k 个最相似的结果。

    返回 [(下标, 相似度)]，按相似度降序排列。这是 RAG 检索的标准流程：
    query 向量 × 文档向量库 → 打分 → 取 top-k → 喂给 LLM 生成答案。
    """
    scored = [(i, cosine(query, row)) for i, row in enumerate(matrix)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]


def normalize_numpy(vectors):
    """L2 归一化：让每个向量的长度变成 1。

    归一化后余弦相似度 = 点积，推导：
        cos(â, b̂) = (â·b̂) / (|â|×|b̂|) = (â·b̂) / (1×1) = â·b̂

    好处：
    - 省掉重复算范数：10 万文档从 O(N²) 次开平方降到 O(N) 次
    - 允许矩阵化：sims = normalize(A) @ normalize(B).T 一次算完所有 pair
    """
    import numpy as np

    arr = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # 防止除零（实际 embedding 不会出现，防御性编程）
    return arr / norms
