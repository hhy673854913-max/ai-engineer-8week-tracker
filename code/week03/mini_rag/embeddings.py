"""嵌入：真实 API + 离线哈希嵌入器。

离线嵌入器不是"假的"：它把字符 n-gram 哈希到固定维度，能让整条链路在
没有 API Key 的情况下跑通与做单元测试。真实效果当然要用真模型。
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Callable, Sequence

EmbedFn = Callable[[Sequence[str]], list[list[float]]]


def get_embed_fn(model: str | None = None, batch_size: int = 16) -> EmbedFn:
    """返回一个"批量文本 → 向量"的函数（OpenAI 兼容接口）。"""
    from code.shared.llm_client import get_client

    client = get_client()
    cfg = client.config
    model = model or os.getenv("EMBED_MODEL", "text-embedding-v3")

    def embed(texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = list(texts[i : i + batch_size])
            resp = client._client.embeddings.create(model=model, input=batch)  # noqa: SLF001
            vectors.extend([d.embedding for d in resp.data])
        return vectors

    return embed


class HashingEmbedder:
    """零依赖的确定性嵌入器：字符 n-gram → 哈希桶 → 归一化。

    只用于离线演示与测试；语义能力远弱于真实模型。
    """

    def __init__(self, dim: int = 256, ngram: int = 2):
        self.dim, self.ngram = dim, ngram

    def _tokens(self, text: str) -> list[str]:
        text = re.sub(r"\s+", "", text.lower())
        padded = f"<{text}>"
        return [padded[i : i + self.ngram] for i in range(len(padded) - self.ngram + 1)]

    def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for token in self._tokens(text):
                bucket = int.from_bytes(hashlib.md5(token.encode("utf-8")).digest()[:4], "big") % self.dim
                vec[bucket] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out
