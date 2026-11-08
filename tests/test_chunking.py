from code.week03.mini_rag.chunking import (
    chunk_by_heading,
    chunk_fixed,
    chunk_recursive,
    stats,
)

TEXT = "第一段内容。" * 30 + "\n\n" + "第二段内容，包含一些细节。" * 30


def test_fixed_no_empty_and_overlap():
    chunks = chunk_fixed(TEXT, size=100, overlap=20, doc_id="doc")
    assert chunks
    assert all(c.text.strip() for c in chunks)
    assert all(c.id.startswith("doc#") for c in chunks)


def test_fixed_rejects_bad_overlap():
    import pytest

    with pytest.raises(ValueError):
        chunk_fixed(TEXT, size=100, overlap=100)


def test_recursive_no_oversize_when_no_separators():
    text = "字" * 1000
    chunks = chunk_recursive(text, size=100, overlap=0, seps=(), doc_id="d")
    assert all(len(c.text) <= 100 for c in chunks)


def test_heading_split_keeps_section():
    md = "# 标题\n\n## 奖励发放\n奖励 7 天内发放。\n\n## 参与条件\n等级 20 级。"
    chunks = chunk_by_heading(md, max_size=200, docs="promo")
    sections = [c.metadata.get("section") for c in chunks]
    assert "奖励发放" in sections
    assert "参与条件" in sections
    assert chunks[0].metadata["doc_id"] == "promo"


def test_stats_shape():
    chunks = chunk_fixed(TEXT, size=200, overlap=0)
    s = stats(chunks)
    assert s["count"] == len(chunks)
    assert s["empty"] == 0
