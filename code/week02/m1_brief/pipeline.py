"""M1 智能资讯简报 v2 主流程。

用法（在仓库根目录执行）：
    python code/week02/m1_brief/pipeline.py --mock
    python code/week02/m1_brief/pipeline.py --mock --limit 10 --out output

设计要点：
- mock 模式完全离线，CI 与演示都能跑
- 每一步都落盘（原始数据 / 简报 / 报表），可回放
- 单条失败降级为规则抽取，不中断整批
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.week02.m1_brief.dedup import dedup  # noqa: E402
from code.week02.m1_brief.extract import extract_batch  # noqa: E402
from code.week02.m1_brief.models import BriefItem, PipelineReport, RawItem  # noqa: E402
from code.week02.m1_brief.sources import load_mock  # noqa: E402


def freshness_score(item: BriefItem, now: datetime) -> float:
    """48 小时线性衰减：越新分越高。"""
    if item.published_at is None:
        return 0.3
    published = item.published_at
    if published.tzinfo is not None:
        published = published.astimezone().replace(tzinfo=None)
    hours = max(0.0, (now - published).total_seconds() / 3600)
    return max(0.0, 1 - hours / 48)


def rank(items: list[BriefItem], now: datetime) -> list[BriefItem]:
    for item in items:
        item.score = round(item.credibility * 0.7 + freshness_score(item, now) * 100 * 0.3, 2)
    return sorted(items, key=lambda i: i.score, reverse=True)


def render_markdown(items: list[BriefItem], report: PipelineReport) -> str:
    lines = [
        f"# 智能资讯简报 · {report.date}",
        "",
        f"> 采集 {report.fetched} 条 → 去重后 {report.after_dedup} 条 → 成功抽取 {report.extracted_ok} 条"
        f"（失败 {report.failed}）｜平均可信度 {report.avg_credibility:.1f}",
        "",
    ]
    by_category: dict[str, list[BriefItem]] = {}
    for item in items:
        by_category.setdefault(item.category, []).append(item)

    for category, group in by_category.items():
        lines.append(f"## {category}")
        for i, item in enumerate(group, 1):
            when = f" · {item.published_at:%m-%d}" if item.published_at else ""
            lines.append(f"### {i}. {item.title}")
            lines.append(f"`{item.source}`{when} · 可信度 **{item.credibility}** · 综合分 {item.score}")
            lines.append("")
            lines.append(item.summary)
            if item.entities:
                lines.append("")
                lines.append("标签：" + " ".join(f"`{e}`" for e in item.entities))
            lines.append("")
            lines.append(f"[原文]({item.url})")
            lines.append("")
    return "\n".join(lines)


async def run(mock: bool, limit: int, out_dir: Path, rss: list[str]) -> int:
    t0 = time.perf_counter()
    now = datetime.now()
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_items: list[RawItem] = []
    if mock or not rss:
        raw_items += load_mock()
    for url in rss:
        from code.week02.m1_brief.sources import fetch_rss

        raw_items += fetch_rss(url, limit=limit)
    raw_items = raw_items[:limit] if limit else raw_items

    payload = [{"url": r.url, "title": r.title, "content": r.content} for r in raw_items]
    kept, removed = dedup(payload)
    kept_urls = {k["url"] for k in kept}
    deduped = [r for r in raw_items if r.url in kept_urls]

    client = None
    use_llm = not mock
    if use_llm:
        try:
            from code.shared.llm_client import get_client

            client = get_client()
        except Exception as exc:  # noqa: BLE001 - 配置缺失时自动降级为 mock
            print(f"[warn] 无法初始化 LLM 客户端（{exc}），自动降级为离线模式", file=sys.stderr)
            use_llm = False

    brief_items, failed = await extract_batch(deduped, client, use_llm=use_llm)
    ranked = rank(brief_items, now)

    report = PipelineReport(
        date=now.strftime("%Y-%m-%d"),
        sources=len({r.source for r in raw_items}),
        fetched=len(raw_items),
        after_dedup=len(deduped),
        extracted_ok=len(brief_items) - len(failed),
        failed=len(failed),
        avg_credibility=round(sum(i.credibility for i in brief_items) / max(len(brief_items), 1), 1),
        duration_s=round(time.perf_counter() - t0, 2),
        failed_items=failed,
    )

    markdown = render_markdown(ranked, report)
    (out_dir / f"brief_{now:%Y%m%d}.md").write_text(markdown, encoding="utf-8")
    (out_dir / f"report_{now:%Y%m%d}.json").write_text(
        json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / f"raw_{now:%Y%m%d}.jsonl").write_text(
        "\n".join(json.dumps(r.model_dump(mode="json"), ensure_ascii=False) for r in raw_items),
        encoding="utf-8",
    )

    print(markdown)
    print("-" * 60)
    print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    print(f"去重移除 {removed} 条；产物目录：{out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M1 智能资讯简报 v2")
    parser.add_argument("--mock", action="store_true", help="离线模式（不调用模型）")
    parser.add_argument("--rss", action="append", default=[], help="RSS 地址，可重复")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out", type=Path, default=ROOT / "output")
    args = parser.parse_args(argv)
    return asyncio.run(run(args.mock, args.limit, args.out, args.rss))


if __name__ == "__main__":
    raise SystemExit(main())
