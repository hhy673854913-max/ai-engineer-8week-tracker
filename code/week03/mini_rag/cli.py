"""mini-RAG 命令行入口。

用法（仓库根目录）：
    python -m code.week03.mini_rag.cli index --docs data/kb_sample
    python -m code.week03.mini_rag.cli query "退款多久到账" --offline
    python -m code.week03.mini_rag.cli query "退款多久到账"          # 需要 API Key

离线模式下向量相似度很弱（哈希嵌入器），所以检索采用
"向量 + BM25 → RRF 融合"，这也是 Day 15 的正式做法。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.week03.mini_rag.chunking import load_markdown_dir, stats  # noqa: E402
from code.week03.mini_rag.embeddings import HashingEmbedder, get_embed_fn  # noqa: E402
from code.week03.mini_rag.hybrid import bm25_search, rrf  # noqa: E402
from code.week03.mini_rag.rag import MiniRAG  # noqa: E402
from code.week03.mini_rag.store import NumpyVectorStore, SearchHit  # noqa: E402


def cmd_index(args: argparse.Namespace) -> int:
    docs = Path(args.docs)
    chunks = load_markdown_dir(docs)
    if not chunks:
        print(f"没有在 {docs} 找到 Markdown 文档", file=sys.stderr)
        return 1
    embed_fn = HashingEmbedder() if args.offline else get_embed_fn()
    vectors = embed_fn([c.text for c in chunks])
    store = NumpyVectorStore()
    store.upsert(chunks, vectors)
    store.save(Path(args.index))

    print(json.dumps(stats(chunks), ensure_ascii=False, indent=2))
    print(f"已写入 {args.index}（{len(store)} 块，维度 {store.dim}，模式={'offline' if args.offline else 'api'}）")
    return 0


def hybrid_hits(store: NumpyVectorStore, query_vector, question: str, k: int, pool: int = 12) -> list[SearchHit]:
    chunks = store.chunks
    id_to_index = {c.id: i for i, c in enumerate(chunks)}
    vector_rank = [id_to_index[h.chunk.id] for h in store.query(query_vector, k=pool) if h.chunk.id in id_to_index]
    bm25_rank = [i for i, _ in bm25_search(chunks, question, k=pool)]
    fused = rrf([vector_rank, bm25_rank])[:k]
    return [SearchHit(chunks[i], score) for i, score in fused]


def cmd_query(args: argparse.Namespace) -> int:
    store = NumpyVectorStore.load(Path(args.index))
    embed_fn = HashingEmbedder() if args.offline else get_embed_fn()
    query_vector = embed_fn([args.question])[0]
    hits = hybrid_hits(store, query_vector, args.question, args.top_k)

    if not hits:
        print("未检索到相关片段（可尝试重建索引）")
        return 0

    for i, h in enumerate(hits, 1):
        meta = h.chunk.metadata
        print(f"[{i}] rrf={h.score:.4f}  {meta.get('source', '')} § {meta.get('section', '')}")
        print("    " + h.chunk.text.strip().replace("\n", " ")[:120])

    if args.offline:
        print("\n(offline 模式只做检索演示；接上 API Key 后同一条命令会输出带引用的答案)")
        return 0

    from code.shared.llm_client import get_client

    rag = MiniRAG(store, embed_fn, chat_fn=get_client().chat, top_k=args.top_k)
    result = rag.answer(args.question)
    print("\n答案：\n" + result.answer)
    if result.citations:
        print("\n引用：")
        for c in result.citations:
            print(f"  [资料 {c['n']}] {c['source']}  score={c['score']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="mini-RAG（手写版）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    idx = sub.add_parser("index", help="切分并建立索引")
    idx.add_argument("--docs", default=str(ROOT / "data" / "kb_sample"))
    idx.add_argument("--index", default=str(ROOT / ".mini_rag_index"))
    idx.add_argument("--offline", action="store_true", help="使用离线哈希嵌入器")
    idx.set_defaults(func=cmd_index)

    q = sub.add_parser("query", help="检索或问答")
    q.add_argument("question")
    q.add_argument("--index", default=str(ROOT / ".mini_rag_index"))
    q.add_argument("--top-k", type=int, default=5)
    q.add_argument("--offline", action="store_true")
    q.set_defaults(func=cmd_query)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
