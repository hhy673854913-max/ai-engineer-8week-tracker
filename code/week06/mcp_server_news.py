"""Day 27 · MCP Server：把 M1 简报能力封装成工具。

关键工程细节：
- 日志写 stderr（stdout 是协议通道，print 会直接破坏连接）
- 错误消息要"可行动"，模型才能自我修正

调试：
    uv run mcp dev code/week06/mcp_server_news.py
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[2]
MOCK_PATH = ROOT / "data" / "mock_news.json"

logging.basicConfig(
    stream=sys.stderr,  # 必须 stderr
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger("mcp.news")

mcp = FastMCP("news-brief")


def _load_news() -> list[dict]:
    if not MOCK_PATH.exists():
        raise FileNotFoundError(f"缺少数据文件: {MOCK_PATH}")
    return json.loads(MOCK_PATH.read_text(encoding="utf-8"))


@mcp.tool()
def query_news(keyword: str, limit: int = 5, days: int = 30) -> list[dict]:
    """按关键词查询最近资讯。

    Args:
        keyword: 关键词，2-20 字
        limit: 返回条数，1-20
        days: 最近几天，1-365

    Returns:
        每条包含 title / summary / source / url / published_at
    """
    if not 2 <= len(keyword) <= 20:
        raise ValueError("keyword 长度需在 2-20 字之间")
    if not 1 <= limit <= 20:
        raise ValueError("limit 需在 1-20 之间")
    if not 1 <= days <= 365:
        raise ValueError("days 需在 1-365 之间")

    now = datetime.now()
    hits = []
    for item in _load_news():
        text = item["title"] + item["content"]
        if keyword not in text:
            continue
        published = item.get("published_at")
        if published:
            try:
                if (now - datetime.fromisoformat(published)).days > days:
                    continue
            except ValueError:
                pass
        hits.append(
            {
                "title": item["title"],
                "summary": item["content"][:120],
                "source": item["source"],
                "url": item["url"],
                "published_at": published,
            }
        )
    log.info("query_news keyword=%s hits=%d", keyword, len(hits))
    return hits[:limit]


@mcp.tool()
def list_sources() -> list[str]:
    """列出当前简报数据覆盖的信源。"""
    return sorted({item["source"] for item in _load_news()})


@mcp.tool()
def get_brief(date: str = "") -> str:
    """获取某天的完整简报（Markdown）。date 格式 YYYY-MM-DD，默认最新一份。"""
    candidates = sorted((ROOT / "output").glob("brief_*.md"))
    if not candidates:
        raise ValueError("还没有生成过简报，请先运行 M1 pipeline")
    path = candidates[-1]
    if date:
        target = ROOT / "output" / f"brief_{date.replace('-', '')}.md"
        if not target.exists():
            raise ValueError(f"没有 {date} 的简报，可选：{', '.join(p.stem for p in candidates[-5:])}")
        path = target
    return path.read_text(encoding="utf-8")


if __name__ == "__main__":
    mcp.run()
