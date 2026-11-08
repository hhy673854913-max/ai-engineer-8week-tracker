"""两层去重：URL 精确去重 + SimHash 近似去重。

分层的意义：先用便宜的方法（字符串/哈希）过滤掉大部分，再对剩下的做昂贵计算。
同样的思路可以推广到 RAG 的"粗排 + 精排"。
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "spm", "from"}
_TOKEN = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]{2}")


def normalize_url(url: str) -> str:
    """去掉追踪参数与锚点，让同一篇文章只有一种写法。"""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in _TRACKING_PARAMS]
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, urlencode(query), ""))


def simhash(text: str, bits: int = 64) -> int:
    """64 位 SimHash：语义相近的文本，汉明距离小。"""
    weights = [0] * bits
    for token in _TOKEN.findall(text):
        digest = int.from_bytes(hashlib.md5(token.encode("utf-8")).digest()[:8], "big")
        for i in range(bits):
            weights[i] += 1 if (digest >> i) & 1 else -1
    fingerprint = 0
    for i, w in enumerate(weights):
        if w > 0:
            fingerprint |= 1 << i
    return fingerprint


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def dedup(items: list[dict], max_distance: int = 3) -> tuple[list[dict], int]:
    """输入 [{url, content, ...}]，返回 (去重后列表, 去掉的条数)。

    同一条新闻被十家媒体转载时，内容不同但语义相同，SimHash 能抓出来。
    """
    seen_urls: set[str] = set()
    fingerprints: list[int] = []
    kept: list[dict] = []

    for item in items:
        url = normalize_url(item.get("url", ""))
        if url and url in seen_urls:
            continue
        fp = simhash(item.get("title", "") + item.get("content", ""))
        if any(hamming(fp, other) <= max_distance for other in fingerprints):
            continue
        seen_urls.add(url)
        fingerprints.append(fp)
        kept.append(item)

    return kept, len(items) - len(kept)
