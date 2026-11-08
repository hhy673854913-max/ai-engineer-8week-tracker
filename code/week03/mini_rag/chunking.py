"""Day 12 · 三种分块器：固定长度、递归字符、按 Markdown 标题。

分块是 RAG 效果的第一杠杆：块太大稀释相似度，块太小语义不完整。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

DEFAULT_SEPS: tuple[str, ...] = ("\n\n", "\n", "。", "！", "？", "；", "，", " ")


@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(cls, text: str, doc_id: str = "", index: int = 0, **metadata: Any) -> "Chunk":
        digest = hashlib.sha1(f"{doc_id}:{index}:{text}".encode("utf-8")).hexdigest()[:12]
        return cls(id=f"{doc_id or 'doc'}#{index}-{digest}", text=text, metadata={"doc_id": doc_id, "chunk_index": index, **metadata})


def _sliding(text: str, size: int, overlap: int) -> list[str]:
    if size <= 0:
        raise ValueError("size 必须为正数")
    if overlap >= size:
        raise ValueError("overlap 必须小于 size，否则会死循环")
    if len(text) <= size:
        return [text]
    step = size - overlap
    return [text[i : i + size] for i in range(0, len(text), step) if text[i : i + size].strip()]


def chunk_fixed(text: str, size: int = 400, overlap: int = 60, doc_id: str = "") -> list[Chunk]:
    """固定长度 + 重叠。简单、可预测，但会切断句子。"""
    return [Chunk.make(t, doc_id, i) for i, t in enumerate(_sliding(text, size, overlap))]


def _split_recursive(text: str, seps: tuple[str, ...], size: int) -> list[str]:
    if len(text) <= size:
        return [text]
    if not seps:
        # 没有可用分隔符时硬切，避免产出超长块
        return [text[i : i + size] for i in range(0, len(text), size)]
    sep, rest = seps[0], seps[1:]
    parts = text.split(sep)
    if len(parts) == 1:
        return _split_recursive(text, rest, size)

    out: list[str] = []
    buf = ""
    for part in parts:
        piece = part + sep
        if len(piece) > size:
            if buf:
                out.append(buf)
                buf = ""
            out.extend(_split_recursive(piece, rest, size))
            continue
        if len(buf) + len(piece) <= size:
            buf += piece
        else:
            if buf:
                out.append(buf)
            buf = piece
    if buf:
        out.append(buf)
    return [o for o in out if o.strip()]


def chunk_recursive(
    text: str,
    size: int = 400,
    overlap: int = 60,
    seps: tuple[str, ...] = DEFAULT_SEPS,
    doc_id: str = "",
) -> list[Chunk]:
    """递归字符分块：优先在段落、句号处切，实在不行才按字符切。"""
    pieces = _split_recursive(text, seps, size)
    # 补 overlap：把上一块尾部拼到下一块头部，防止边界信息丢失
    if overlap > 0 and len(pieces) > 1:
        merged = []
        for i, piece in enumerate(pieces):
            if i == 0:
                merged.append(piece)
            else:
                tail = pieces[i - 1][-overlap:]
                merged.append(tail + piece)
        pieces = merged
    return [Chunk.make(p, doc_id, i) for i, p in enumerate(pieces) if p.strip()]


_HEADING = re.compile(r"^(#{1,3})\s+(.+)$", re.M)


def chunk_by_heading(markdown: str, max_size: int = 600, docs: str = "") -> list[Chunk]:
    """按 Markdown 标题切 section；section 过长再递归切。中文文档最实用。"""
    matches = list(_HEADING.finditer(markdown))
    sections: list[tuple[str, str]] = []
    if not matches:
        sections.append(("", markdown))
    else:
        if matches[0].start() > 0:
            sections.append(("", markdown[: matches[0].start()]))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
            sections.append((m.group(2).strip(), markdown[m.start() : end]))

    chunks: list[Chunk] = []
    for title, body in sections:
        if not body.strip():
            continue
        if len(body) <= max_size:
            chunks.append(Chunk.make(body.strip(), docs, len(chunks), section=title))
        else:
            for sub in chunk_recursive(body.strip(), size=max_size, doc_id=docs):
                sub.metadata["section"] = title
                chunks.append(sub)
    return chunks


def load_markdown_dir(root: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(root.rglob("*.md")):
        doc_id = path.stem
        text = path.read_text(encoding="utf-8")
        for c in chunk_by_heading(text, docs=doc_id):
            c.metadata.setdefault("source", str(path.relative_to(root)))
            chunks.append(c)
    return chunks


def stats(chunks: Iterable[Chunk]) -> dict[str, float]:
    sizes = [len(c.text) for c in chunks]
    if not sizes:
        return {"count": 0}
    return {
        "count": len(sizes),
        "avg": round(sum(sizes) / len(sizes), 1),
        "max": max(sizes),
        "min": min(sizes),
        "empty": sum(1 for s in sizes if s == 0),
        "oversize": sum(1 for s in sizes if s > 800),
    }
