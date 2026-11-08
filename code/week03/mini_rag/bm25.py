"""Day 15 · 手写 BM25（中文分词优先 jieba，缺依赖时退化为字符二元组）。

BM25 的强项是专有名词与精确词命中，正好补向量检索的短板。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Sequence

_TOKEN = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    """优先用 jieba；没装则用"汉字二元组 + 英文单词"，效果略差但零依赖。"""
    try:
        import jieba  # type: ignore[import-not-found]

        return [t for t in jieba.lcut(text) if t.strip()]
    except ImportError:
        chars = [c for c in _TOKEN.findall(text)]
        tokens = list(chars)
        for i in range(len(chars) - 1):
            if "\u4e00" <= chars[i] <= "\u9fff" and "\u4e00" <= chars[i + 1] <= "\u9fff":
                tokens.append(chars[i] + chars[i + 1])
        return tokens


class BM25:
    """标准 BM25 实现。k1 控制词频饱和，b 控制文档长度归一化。"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs: list[list[str]] = []
        self.df: Counter[str] = Counter()
        self.avgdl: float = 0.0

    def add(self, texts: Sequence[str]) -> "BM25":
        for text in texts:
            tokens = tokenize(text)
            self.docs.append(tokens)
            self.df.update(set(tokens))
        total = sum(len(d) for d in self.docs)
        self.avgdl = total / len(self.docs) if self.docs else 0.0
        return self

    def score(self, query: str) -> list[float]:
        q_tokens = tokenize(query)
        n = len(self.docs)
        scores = [0.0] * n
        for i, doc in enumerate(self.docs):
            tf = Counter(doc)
            dl = len(doc) or 1
            for token in q_tokens:
                if token not in tf:
                    continue
                idf = math.log(1 + (n - self.df[token] + 0.5) / (self.df[token] + 0.5))
                denom = tf[token] + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                scores[i] += idf * tf[token] * (self.k1 + 1) / denom
        return scores

    def search(self, query: str, k: int = 10) -> list[tuple[int, float]]:
        scores = self.score(query)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [(i, s) for i, s in ranked[:k] if s > 0]
