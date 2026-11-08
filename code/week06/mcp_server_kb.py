"""Day 28 · MCP Server：把领域知识库检索封装成工具 + 资源。

复用 mini_rag 的检索能力，不重写逻辑。索引不存在时自动用离线嵌入器建一个临时索引。

调试：
    uv run mcp dev code/week06/mcp_server_kb.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[2]
KB_DIR = ROOT / "data" / "kb_sample"
INDEX_DIR = ROOT / ".mini_rag_index"

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
log = logging.getLogger("mcp.kb")

mcp = FastMCP("kb")

_store = None
_embed = None


def _get_store():
    global _store, _embed
    if _store is not None:
        return _store
    sys.path.insert(0, str(ROOT))
    from code.week03.mini_rag.chunking import load_markdown_dir
    from code.week03.mini_rag.embeddings import HashingEmbedder
    from code.week03.mini_rag.store import NumpyVectorStore

    if (INDEX_DIR / "vectors.npy").exists():
        _store = NumpyVectorStore.load(INDEX_DIR)
        _embed = HashingEmbedder()
        log.info("loaded index from %s (%d chunks)", INDEX_DIR, len(_store))
    else:
        chunks = load_markdown_dir(KB_DIR)
        _embed = HashingEmbedder()
        _store = NumpyVectorStore()
        _store.upsert(chunks, _embed([c.text for c in chunks]))
        log.info("built in-memory index (%d chunks)", len(_store))
    return _store


@mcp.tool()
def search_kb(query: str, top_k: int = 3) -> list[dict]:
    """在领域知识库中语义检索，返回最相关的片段。

    Args:
        query: 自然语言问题或关键词
        top_k: 返回条数，1-10
    """
    if not query.strip():
        raise ValueError("query 不能为空")
    store = _get_store()
    vector = _embed([query])[0]  # type: ignore[index]
    hits = store.query(vector, k=min(max(top_k, 1), 10))
    return [
        {
            "id": h.chunk.id,
            "section": h.chunk.metadata.get("section"),
            "source": h.chunk.metadata.get("source"),
            "score": round(h.score, 3),
            "snippet": h.chunk.text[:200],
        }
        for h in hits
    ]


@mcp.tool()
def get_doc(doc_id: str) -> str:
    """按文档名读取知识库全文（不含扩展名）。"""
    path = KB_DIR / f"{doc_id}.md"
    if not path.exists():
        available = ", ".join(p.stem for p in KB_DIR.glob("*.md"))
        raise ValueError(f"文档不存在: {doc_id}，可选：{available}")
    return path.read_text(encoding="utf-8")


@mcp.resource("kb://doc/{doc_id}")
def doc_resource(doc_id: str) -> str:
    """按 URI 读取文档全文（只读资源，供客户端主动加载）。"""
    return get_doc(doc_id)


if __name__ == "__main__":
    mcp.run()
