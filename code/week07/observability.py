"""Day 33 · 手写链路追踪：Trace / Span / 成本归属。

没有 Langfuse 账号也能用；有账号时把 export() 换成 SDK 上报即可。

用法：
    python -m code.week07.observability
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


@dataclass
class Span:
    name: str
    start: float = field(default_factory=time.perf_counter)
    end: float | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def ms(self) -> int:
        return int(((self.end or time.perf_counter()) - self.start) * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ms": self.ms,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "meta": self.meta,
        }


class Trace:
    def __init__(self, trace_id: str, question: str):
        self.trace_id = trace_id
        self.question = question
        self.spans: list[Span] = []
        self.created_at = datetime.now().isoformat(timespec="seconds")

    @contextmanager
    def span(self, name: str, **meta: Any) -> Iterator[Span]:
        span = Span(name=name, meta=meta)
        self.spans.append(span)
        try:
            yield span
        finally:
            span.end = time.perf_counter()

    @property
    def total_ms(self) -> int:
        return sum(s.ms for s in self.spans)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "question": self.question,
            "created_at": self.created_at,
            "total_ms": self.total_ms,
            "spans": [s.to_dict() for s in self.spans],
        }


def demo() -> None:
    trace = Trace("req-demo-001", "退款多久到账")
    with trace.span("retrieve", top_k=4) as s:
        time.sleep(0.12)
        s.meta["hit_ids"] = ["refund-faq#0", "refund-faq#1"]
    with trace.span("rerank", method="rule") as s:
        time.sleep(0.03)
    with trace.span("generate", model="deepseek-chat") as s:
        time.sleep(0.8)
        s.tokens_in, s.tokens_out = 1200, 260

    payload = trace.to_dict()
    out = Path("output") / "trace_demo.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    slowest = max(trace.spans, key=lambda x: x.ms)
    print(f"\n最慢的一步：{slowest.name} ({slowest.ms} ms) —— 优化从这里开始")
    print(f"轨迹已写入 {out}")


if __name__ == "__main__":
    demo()
