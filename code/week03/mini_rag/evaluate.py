"""Day 15 · 检索评测：hit-rate@k、MRR、Recall。

先建评估集再优化——否则你不知道改动是好是坏。
"""

from __future__ import annotations

from typing import Any, Callable


def hit_at_k(retrieved_ids: list[str], gold_ids: set[str], k: int = 5) -> float:
    return 1.0 if any(doc in gold_ids for doc in retrieved_ids[:k]) else 0.0


def mrr(retrieved_ids: list[str], gold_ids: set[str]) -> float:
    for rank, doc in enumerate(retrieved_ids, start=1):
        if doc in gold_ids:
            return 1.0 / rank
    return 0.0


def recall_at_k(retrieved_ids: list[str], gold_ids: set[str], k: int = 5) -> float:
    if not gold_ids:
        return 1.0
    return len(set(retrieved_ids[:k]) & gold_ids) / len(gold_ids)


def evaluate(
    cases: list[dict[str, Any]],
    retrieve: Callable[[str, int], list[str]],
    k: int = 5,
) -> dict[str, Any]:
    """cases: [{"question": str, "gold_ids"/"gold_doc_ids": [str], "should_refuse": bool}]"""
    rows = []
    for case in cases:
        if case.get("should_refuse"):
            continue
        ids = retrieve(case["question"], k)
        gold = set(case.get("gold_ids") or case.get("gold_doc_ids") or [])
        rows.append(
            {
                "question": case["question"],
                "hit": hit_at_k(ids, gold, k),
                "mrr": mrr(ids, gold),
                "recall": recall_at_k(ids, gold, k),
                "retrieved": ids[:k],
            }
        )
    n = max(len(rows), 1)
    return {
        "n": len(rows),
        "hit_rate": round(sum(r["hit"] for r in rows) / n, 4),
        "mrr": round(sum(r["mrr"] for r in rows) / n, 4),
        "recall": round(sum(r["recall"] for r in rows) / n, 4),
        "rows": rows,
    }
