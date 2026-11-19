"""信源采集：mock（离线）+ RSS 自动采集（基于可信源列表）。

设计原则：
- 可信源列表是数据采集的唯一入口，采集前必须加载并校验。
- 自动模式只保留“前一日”发布的 AI 相关资讯。
- 手动 `--rss` 仅作为调试/覆盖手段，不改变默认行为。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from .models import RawItem, TrustedSource

MOCK_PATH = Path(__file__).resolve().parents[3] / "data" / "mock_news.json"
TRUSTED_SOURCES_PATH = Path(__file__).resolve().parents[3] / "data" / "trusted_sources.json"


def load_mock(path: Path | None = None) -> list[RawItem]:
    """离线数据，CI 与演示都用它，保证结果可复现。"""
    p = path or MOCK_PATH
    if not p.exists():
        raise FileNotFoundError(f"找不到 mock 数据: {p}")
    rows = json.loads(p.read_text(encoding="utf-8"))
    return [RawItem.model_validate(r) for r in rows]


def load_trusted_sources(path: Path | None = None) -> list[TrustedSource]:
    """加载可信源列表。缺失或非法时快速失败，避免静默降级。"""
    p = path or TRUSTED_SOURCES_PATH
    if not p.exists():
        raise FileNotFoundError(f"找不到可信源列表: {p}，请先创建该文件")
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
        sources = [TrustedSource.model_validate(r) for r in rows]
    except Exception as exc:
        raise ValueError(f"可信源列表格式非法: {p} ({exc})") from exc
    enabled = [s for s in sources if s.enabled]
    if not enabled:
        raise ValueError(f"可信源列表中没有启用项: {p}")
    return enabled


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
    ):
        try:
            parsed = datetime.strptime(value, fmt)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed
        except ValueError:
            continue
    return None


def entry_published_at(entry: object) -> datetime | None:
    """从 feedparser entry 中提取发布时间，兼容 published/updated 及解析后的时间结构。"""
    published_parsed = getattr(entry, "get", lambda *_: None)("published_parsed")
    if published_parsed:
        try:
            return datetime(*published_parsed[:6])
        except Exception:
            pass

    updated_parsed = getattr(entry, "get", lambda *_: None)("updated_parsed")
    if updated_parsed:
        try:
            return datetime(*updated_parsed[:6])
        except Exception:
            pass

    published = getattr(entry, "get", lambda *_: None)("published")
    if published:
        parsed = parse_time(str(published))
        if parsed:
            return parsed

    updated = getattr(entry, "get", lambda *_: None)("updated")
    if updated:
        return parse_time(str(updated))

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
                published_at=entry_published_at(entry),
            )
        )
    return items


def fetch_all_trusted_sources(sources: list[TrustedSource], limit: int = 20) -> list[RawItem]:
    """按可信源列表逐个抓取 RSS，并聚合结果。"""
    # feedparser 缺失属于环境配置错误，不应被当成单源失败吞掉
    try:
        import feedparser  # type: ignore[import-not-found]  # noqa: F401
    except ImportError as exc:  # pragma: no cover - 取决于环境
        raise RuntimeError("自动采集需要 feedparser：uv pip install feedparser") from exc

    items: list[RawItem] = []
    for source in sources:
        try:
            items.extend(fetch_rss(source.rss, limit=limit))
        except Exception:
            # 单源失败不应阻断整体采集；这里选择跳过，保持流水线可用
            continue
    return items


def fetch_article_text(url: str, timeout_s: int = 10, max_chars: int = 3000) -> str:
    """抓取正文页并做极简清洗，供 LLM 抽取使用。

    说明：这是保底实现，优先用 BeautifulSoup；缺失时回退到正则去标签。
    """
    import re
    from urllib.request import Request, urlopen

    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout_s) as resp:  # nosec B310
        html = resp.read().decode("utf-8", errors="ignore")

    soup_text = ""
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-not-found]

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
            tag.decompose()
        soup_text = soup.get_text("\n", strip=True)
    except ImportError:
        soup_text = re.sub(r"<[^>]+>", " ", html)

    soup_text = re.sub(r"\s+", " ", soup_text).strip()
    return soup_text[:max_chars]


def enrich_empty_content(items: list[RawItem], *, timeout_s: int = 10) -> tuple[list[RawItem], int, int]:
    """对正文为空的条目抓原文补正文，返回 (更新后的列表, 成功补全数, 失败数)。"""
    updated: list[RawItem] = []
    filled = 0
    failed = 0
    for item in items:
        if item.content.strip():
            updated.append(item)
            continue
        try:
            text = fetch_article_text(item.url, timeout_s=timeout_s)
        except Exception:
            failed += 1
            updated.append(item)
            continue
        if text:
            item.content = text
            filled += 1
        else:
            failed += 1
        updated.append(item)
    return updated, filled, failed


def filter_previous_day(items: list[RawItem], now: datetime) -> list[RawItem]:
    """仅保留前一日 00:00–23:59:59 发布的条目。"""
    start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(hour=23, minute=59, second=59)
    kept: list[RawItem] = []
    for item in items:
        published = item.published_at
        if published is None:
            continue
        if published.tzinfo is not None:
            published = published.astimezone().replace(tzinfo=None)
        if start <= published <= end:
            kept.append(item)
    return kept


def _looks_clickbait(title: str) -> bool:
    """粗略识别标题党/低信息标题。"""
    t = title.strip()
    if not t:
        return True
    if len(t) <= 4:
        return True
    for kw in ("!", "！", "？？", "??", "震惊", "刚刚", "突发", "炸裂", "绝了", "笑死", "氖人寻味"):
        if kw in t:
            return True
    return False


def _content_is_too_thin(content: str, title: str) -> bool:
    """判断正文是否几乎没信息量。"""
    text = (content or "").strip()
    if len(text) < 80:
        return True
    # 全是重复字符/太短句，基本不可抽取
    if len(set(text)) < 20:
        return True
    # 标题和正文高度重合时，通常说明只抓到了标题片段
    if title and title.strip() and title.strip() in text and len(text) < 180:
        return True
    return False


def filter_low_quality(items: list[RawItem]) -> tuple[list[RawItem], int, int]:
    """过滤低质条目：过短正文、标题党、低信息量内容。

    返回 (保留列表, 低质移除数, 空正文移除数)
    """
    kept: list[RawItem] = []
    low_quality = 0
    empty = 0
    for item in items:
        title = item.title.strip()
        content = item.content.strip()
        if not content:
            if _looks_clickbait(title):
                low_quality += 1
            else:
                empty += 1
            continue
        if _looks_clickbait(title) or _content_is_too_thin(content, title):
            low_quality += 1
            continue
        kept.append(item)
    return kept, low_quality, empty


AI_KEYWORDS = (
    "AI",
    "人工智能",
    "大模型",
    "模型",
    "机器学习",
    "深度学习",
    "GPT",
    "LLM",
    "Agent",
    "RAG",
    "神经网络",
    "推理",
    "训练",
    "开源模型",
    "多模态",
)


def is_ai_related(text: str) -> bool:
    return any(k.lower() in text.lower() for k in AI_KEYWORDS)


def filter_ai_related(items: list[RawItem]) -> tuple[list[RawItem], int]:
    """过滤出 AI 相关条目，返回 (保留列表, 被过滤数量)。"""
    kept: list[RawItem] = []
    removed = 0
    for item in items:
        text = f"{item.title}\n{item.content}"
        if is_ai_related(text):
            kept.append(item)
        else:
            removed += 1
    return kept, removed
