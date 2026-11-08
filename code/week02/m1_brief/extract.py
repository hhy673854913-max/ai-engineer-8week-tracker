"""结构化抽取：LLM 版 + 离线启发式版。

离线版不是"凑数"：它让 --mock 模式能在没有 API Key 的 CI 里跑完整链路，
也给了你一个 baseline——LLM 版比规则版好多少，是可以量化的。
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from .models import BriefItem, Category, RawItem
from .prompts import EXTRACT_PROMPT

log = logging.getLogger("m1.extract")

# 信源等级 → 权威性得分（可信度评分的第一个维度）
SOURCE_TIER = {
    "官方公告": 40,
    "36氪": 30,
    "机器之心": 30,
    "量子位": 30,
    "GameLook": 20,
    "自媒体": 10,
}

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "融资": ("融资", "估值", "轮", "投资", "IPO"),
    "产品": ("发布", "上线", "更新", "版本", "功能"),
    "政策": ("政策", "监管", "备案", "法规", "标准"),
    "技术": ("模型", "开源", "论文", "算法", "架构", "Agent", "RAG"),
}


def guess_category(text: str) -> Category:
    best, best_hits = "其他", 0
    for cat, words in CATEGORY_KEYWORDS.items():
        hits = sum(text.count(w) for w in words)
        if hits > best_hits:
            best, best_hits = cat, hits
    return best  # type: ignore[return-value]


def first_sentence(text: str, limit: int = 80) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:limit]


def heuristic_extract(raw: RawItem) -> BriefItem:
    """没有模型时的兜底：规则版抽取。"""
    text = f"{raw.title}\n{raw.content}"
    authority = next((v for k, v in SOURCE_TIER.items() if k in raw.source), 20)
    specific = min(30, 10 + 10 * sum(bool(re.search(p, text)) for p in (r"\d+%?", r"\d+亿", r"\d{4}年")))
    verifiable = 20 if re.search(r"\d", text) else 10
    return BriefItem.from_raw(
        raw,
        title=raw.title[:30],
        summary=first_sentence(raw.content),
        category=guess_category(text),
        entities=re.findall(r"[A-Z][A-Za-z]{2,}", text)[:5],
        credibility=min(100, authority + verifiable + specific),
    )


def llm_extract(client: Any, raw: RawItem, *, max_tokens: int = 500) -> BriefItem:
    """LLM 抽取；失败时抛出，由批量层决定降级策略。"""
    prompt = EXTRACT_PROMPT.format(text=raw.content[:2000])
    result = client.chat(
        [{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    parsed = client_parse(result.content)
    return BriefItem.from_raw(
        raw,
        title=str(parsed.get("title") or raw.title)[:30],
        summary=str(parsed.get("summary") or "")[:120],
        category=parsed.get("category") if parsed.get("category") in CATEGORY_KEYWORDS else "其他",
        entities=[str(x) for x in (parsed.get("entities") or [])][:8],
        credibility=int(parsed.get("credibility") or 50),
    )


def client_parse(raw: str) -> dict[str, Any]:
    from code.shared.structured import loads_lenient, extract_json

    return loads_lenient(extract_json(raw))


async def extract_batch(
    items: list[RawItem],
    client: Any | None,
    *,
    concurrency: int = 5,
    use_llm: bool = True,
) -> tuple[list[BriefItem], list[dict]]:
    """并发抽取；单条失败不中断整批，并记录失败原因。"""
    sem = asyncio.Semaphore(concurrency)
    ok: list[BriefItem] = []
    failed: list[dict] = []

    async def one(raw: RawItem) -> None:
        async with sem:
            if not use_llm or client is None:
                ok.append(heuristic_extract(raw))
                return
            try:
                ok.append(await asyncio.to_thread(llm_extract, client, raw))
            except Exception as exc:  # noqa: BLE001 - 单条失败要隔离
                log.warning("抽取失败 %s: %s", raw.url, exc)
                failed.append({"id": raw.id, "url": raw.url, "error": f"{type(exc).__name__}: {exc}"})
                ok.append(heuristic_extract(raw))  # 降级而不是丢弃

    await asyncio.gather(*(one(i) for i in items))
    return ok, failed
