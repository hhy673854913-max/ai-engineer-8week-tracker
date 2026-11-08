"""信源采集：mock（离线）+ RSS（可选依赖 feedparser）。

先让链路通，再换数据源——所以 mock 是正式功能，不是临时补丁。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .models import RawItem

MOCK_PATH = Path(__file__).resolve().parents[3] / "data" / "mock_news.json"


def load_mock(path: Path | None = None) -> list[RawItem]:
    """离线数据，CI 与演示都用它，保证结果可复现。"""
    p = path or MOCK_PATH
    if not p.exists():
        raise FileNotFoundError(f"找不到 mock 数据: {p}")
    rows = json.loads(p.read_text(encoding="utf-8"))
    return [RawItem.model_validate(r) for r in rows]


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def fetch_rss(url: str, limit: int = 20) -> list[RawItem]:
    """抓取 RSS。feedparser 是可选依赖，缺了会给出明确提示。"""
    try:
        import feedparser  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - 取决于环境
        raise RuntimeError("需要先安装 feedparser：uv pip install feedparser") from exc

    feed = feedparser.parse(url)
    items: list[RawItem] = []
    for entry in feed.entries[:limit]:
        items.append(
            RawItem(
                source=feed.feed.get("title", url),
                url=entry.get("link", ""),
                title=entry.get("title", ""),
                content=entry.get("summary", ""),
                published_at=parse_time(entry.get("published")),
            )
        )
    return items
