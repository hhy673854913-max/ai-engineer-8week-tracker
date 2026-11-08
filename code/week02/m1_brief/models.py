"""M1 的数据契约。

流水线思维的第一课：把"随手拼的 dict"换成有类型的模型。
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["融资", "产品", "政策", "技术", "其他"]


class RawItem(BaseModel):
    """采集到的原始条目。"""

    source: str
    url: str
    title: str
    content: str
    published_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=datetime.now)

    @property
    def id(self) -> str:
        """稳定 id：同一 URL 永远得到同一个 id，保证幂等。"""
        return hashlib.sha1(self.url.encode("utf-8")).hexdigest()[:16]


class BriefItem(BaseModel):
    """抽取后的简报条目。"""

    id: str
    title: str
    summary: str
    category: Category = "其他"
    entities: list[str] = Field(default_factory=list)
    credibility: int = Field(default=50, ge=0, le=100)
    score: float = 0.0
    source: str = ""
    url: str = ""
    published_at: datetime | None = None

    @classmethod
    def from_raw(cls, raw: RawItem, **fields: object) -> "BriefItem":
        return cls(id=raw.id, source=raw.source, url=raw.url, published_at=raw.published_at, **fields)  # type: ignore[arg-type]


class PipelineReport(BaseModel):
    """每次运行的成本与质量报表——这是"能进简历"的证据。"""

    date: str
    sources: int = 0
    fetched: int = 0
    after_dedup: int = 0
    extracted_ok: int = 0
    failed: int = 0
    avg_credibility: float = 0.0
    duration_s: float = 0.0
    failed_items: list[dict] = Field(default_factory=list)
