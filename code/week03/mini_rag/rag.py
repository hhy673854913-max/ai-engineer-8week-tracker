"""Day 14 · 完整 RAG 链路：检索 → 组装上下文 → 生成 → 引用校验。

三个关键设计：
1. 相似度阈值 + 拒答，控制幻觉
2. 上下文带编号与来源，便于引用
3. 生成后校验引用编号，发现无效引用就降级
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from .store import NumpyVectorStore, SearchHit

CITE = re.compile(r"\[资料\s*(\d+)\]|\[(\d+)\]")

CONTEXT_PROMPT = """你是严谨的知识库问答助手。请只依据下面的资料回答问题。

规则：
1. 只使用资料中的信息，资料没有的内容明确说"资料未提及"；
2. 每个结论后用 [资料 n] 标注来源，n 是资料编号；
3. 如果资料与问题无关，直接回答"当前知识库没有找到相关内容"；
4. 回答控制在 200 字以内，不使用感叹号。

资料：
{context}

问题：{question}
"""


@dataclass
class Answer:
    question: str
    answer: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    hits: list[SearchHit] = field(default_factory=list)
    refused: bool = False


class MiniRAG:
    def __init__(
        self,
        store: NumpyVectorStore,
        embed_fn: Callable[[Sequence[str]], list[list[float]]],
        chat_fn: Callable[..., Any] | None = None,
        *,
        top_k: int = 5,
        min_score: float = 0.55,
    ):
        self.store = store
        self.embed_fn = embed_fn
        self.chat_fn = chat_fn
        self.top_k = top_k
        self.min_score = min_score

    # -- 检索 -----------------------------------------------------------
    def retrieve(self, question: str, k: int | None = None) -> list[SearchHit]:
        vector = self.embed_fn([question])[0]
        hits = self.store.query(vector, k=k or self.top_k)
        return [h for h in hits if h.score >= self.min_score]

    # -- 上下文 ---------------------------------------------------------
    @staticmethod
    def build_context(hits: list[SearchHit]) -> str:
        blocks = []
        for i, h in enumerate(hits, 1):
            meta = h.chunk.metadata
            source = meta.get("source") or meta.get("doc_id") or "未知来源"
            section = meta.get("section") or ""
            suffix = f" § {section}" if section else ""
            blocks.append(f"【资料 {i}｜来源：{source}{suffix}】\n{h.chunk.text.strip()}")
        return "\n\n".join(blocks)

    # -- 生成 -----------------------------------------------------------
    def answer(self, question: str) -> Answer:
        hits = self.retrieve(question)
        if not hits:
            return Answer(question=question, answer="当前知识库没有找到相关内容。", refused=True)
        if self.chat_fn is None:
            raise RuntimeError("未提供 chat_fn，只能做检索演示")

        result = self.chat_fn(
            [{"role": "user", "content": CONTEXT_PROMPT.format(context=self.build_context(hits), question=question)}],
            temperature=0.2,
            max_tokens=600,
        )
        text = getattr(result, "content", result)
        return Answer(question=question, answer=text, citations=self.parse_citations(text, hits), hits=hits)

    @staticmethod
    def parse_citations(text: str, hits: list[SearchHit]) -> list[dict[str, Any]]:
        """强引用：只保留真实存在的编号，并把编号映射回原文。"""
        seen: set[int] = set()
        out: list[dict[str, Any]] = []
        for match in CITE.finditer(text):
            n = int(match.group(1) or match.group(2))
            if not 1 <= n <= len(hits) or n in seen:
                continue
            seen.add(n)
            hit = hits[n - 1]
            out.append(
                {
                    "n": n,
                    "source": hit.chunk.metadata.get("source") or hit.chunk.metadata.get("doc_id"),
                    "score": round(hit.score, 3),
                    "text": hit.chunk.text[:160],
                }
            )
        return out


def check_citations(answer: str, hits: list[SearchHit]) -> list[int]:
    """返回引用了但不存在于上下文中的编号（用于降级提示）。"""
    invalid = []
    for match in CITE.finditer(answer):
        n = int(match.group(1) or match.group(2))
        if not 1 <= n <= len(hits):
            invalid.append(n)
    return sorted(set(invalid))
