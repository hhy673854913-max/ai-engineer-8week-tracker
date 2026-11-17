"""Day 19 · M2 问答链路：索引构建 + QAService + Badcase 记录。

核心设计：
1. 单一入口：QAService.ask(question) -> Answer，CLI / API / 测试都走它
2. 依赖注入：embedder / llm / retriever 从外部传入，方便 mock 与替换
3. 可观测：trace_id / latency / tokens / cost 全记录

用法：
    python -m code.week04.m2_kb.qa_chain "春节奖励什么时候发"
    python -m code.week04.m2_kb.qa_chain --rebuild  # 重建索引
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, Sequence

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import BaseModel, Field

from code.week03.mini_rag.chunking import Chunk, chunk_by_heading
from code.week03.mini_rag.embeddings import HashingEmbedder, get_embed_fn, EmbedConfigError
from code.week03.mini_rag.store import NumpyVectorStore, SearchHit
from code.week03.mini_rag.bm25 import BM25
from code.week03.mini_rag.hybrid import rrf as _rrf
from code.shared.llm_client import get_client, ChatResult

log = logging.getLogger("m2_kb")

# 默认路径
DEFAULT_KB_PATH = ROOT / "data" / "kb" / "docs.jsonl"
DEFAULT_INDEX_DIR = ROOT / "output" / "m2_kb_index"
DEFAULT_EVAL_OUT = ROOT / "output" / "m2_eval.csv"


def get_embed_fn_or_fallback():
    """优先真实嵌入；未配置时回退哈希嵌入（保证可跑）。"""
    try:
        return get_embed_fn()
    except EmbedConfigError:
        log.warning("未配置 EMBED_*，回退到 HashingEmbedder（仅用于离线演示）")
        return HashingEmbedder()

PROMPT = """你是严谨的游戏运营知识库助手。请只依据下面的资料回答问题。

规则：
1. 只使用资料中的信息，资料没有的内容明确说"资料未提及"；
2. 每个结论后用 [资料 n] 标注来源，n 是资料编号；
3. 如果资料与问题无关，直接回答"当前知识库没有找到相关内容"；
4. 回答控制在 200 字以内，不使用感叹号。

资料：
{context}

问题：{question}
"""

REWRITE_PROMPT = """请将用户问题改写成适合检索知识库的查询，保留关键实体名（活动名、奖励名等）。
原问题：{question}
改写后："""


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


class KBDoc(BaseModel):
    """知识库文档 schema（Day 18 定义）。"""

    doc_id: str
    title: str
    category: Literal["活动规则", "玩法说明", "FAQ", "公告", "补偿标准"]
    version: str = "v1.0"
    effective_from: date
    effective_to: date | None = None
    source: str = ""
    content: str

    def is_effective(self, today: date | None = None) -> bool:
        """是否仍在有效期内。"""
        today = today or date.today()
        if self.effective_from > today:
            return False
        if self.effective_to and self.effective_to < today:
            return False
        return True

    def contextualized_text(self) -> str:
        """嵌入用的文本：标题 + 分类 + 正文（比裸正文语义更完整）。"""
        return f"{self.title}\n{self.category}\n{self.content}"


@dataclass
class Hit:
    """检索命中（带排名信息）。"""

    chunk: Chunk
    score: float
    rank_vector: int = 0
    rank_bm25: int = 0

    @property
    def source(self) -> str:
        return str(self.chunk.metadata.get("source") or self.chunk.metadata.get("doc_id") or "未知")

    @property
    def title(self) -> str:
        return str(self.chunk.metadata.get("title") or "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": 0,  # 由调用方填入最终编号
            "score": round(self.score, 4),
            "source": self.source,
            "title": self.title,
            "snippet": self.chunk.text[:200],
        }


@dataclass
class Citation:
    """答案中的引用（编号 + 溯源）。"""

    n: int
    source: str
    score: float
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"n": self.n, "source": self.source, "score": self.score, "text": self.text}


@dataclass
class Answer:
    """QAService.ask 的完整返回。"""

    question: str
    answer: str
    citations: list[Citation] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
    latency_ms: int = 0
    tokens: int = 0
    cost_cny: float = 0.0
    trace_id: str = ""
    refused: bool = False


# ---------------------------------------------------------------------------
# 索引构建
# ---------------------------------------------------------------------------


def load_kb_docs(path: Path) -> list[KBDoc]:
    """读取 JSONL → 校验 schema → 过滤空文档。"""
    if not path.exists():
        raise FileNotFoundError(
            f"知识库文件不存在: {path}\n"
            "请先准备 data/kb/docs.jsonl，或运行 Day 18 的数据转换脚本。"
        )
    docs = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            docs.append(KBDoc.model_validate_json(line))
        except Exception as exc:
            log.warning("第 %d 行 schema 校验失败，已跳过: %s", i, exc)
    return [d for d in docs if d.content.strip()]


def filter_effective(docs: list[KBDoc], today: date | None = None) -> list[KBDoc]:
    """过滤过期文档（先过滤再嵌入，不浪费 token）。"""
    kept = [d for d in docs if d.is_effective(today)]
    removed = len(docs) - len(kept)
    if removed:
        log.info("过滤掉 %d 条过期/未生效文档", removed)
    return kept


async def embed_batched(
    texts: Sequence[str],
    embed_fn,
    *,
    batch_size: int = 16,
    concurrency: int = 5,
) -> list[list[float]]:
    """批量嵌入：用 asyncio.Semaphore 控制并发，避免 429。"""
    sem = asyncio.Semaphore(concurrency)
    vectors: list[list[float]] = []

    async def _embed_batch(batch: list[str]) -> list[list[float]]:
        async with sem:
            # embed_fn 是同步的，丢到线程池防止阻塞事件循环
            return await asyncio.to_thread(embed_fn, batch)

    tasks = []
    for i in range(0, len(texts), batch_size):
        batch = list(texts[i : i + batch_size])
        tasks.append(_embed_batch(batch))

    results = await asyncio.gather(*tasks)
    for r in results:
        vectors.extend(r)
    return vectors


async def build_index(
    docs_path: Path = DEFAULT_KB_PATH,
    out_dir: Path = DEFAULT_INDEX_DIR,
) -> dict[str, Any]:
    """建索引：读取 → 校验 → 过滤 → 分块 → 上下文化 → 批量嵌入 → 落盘。"""
    docs = load_kb_docs(docs_path)
    docs = filter_effective(docs)
    log.info("有效文档: %d 条", len(docs))

    chunks: list[Chunk] = []
    for d in docs:
        for c in chunk_by_heading(d.content, max_size=500, docs=d.doc_id):
            c.metadata.update({
                "doc_id": d.doc_id,
                "title": d.title,
                "category": d.category,
                "effective_from": str(d.effective_from),
                "source": d.source or d.doc_id,
            })
            chunks.append(c)
    log.info("分块完成: %d 个", len(chunks))

    # 嵌入文本用上下文化版本，但存进库里的是正文
    embed_texts = [f"{c.metadata['title']}\n{c.text}" for c in chunks]

    embed_fn = get_embed_fn_or_fallback()
    vectors = await embed_batched(embed_texts, embed_fn, concurrency=5)

    store = NumpyVectorStore()
    store.upsert(chunks, vectors)
    store.save(out_dir)

    # BM25 索引也落盘（检索时重建太耗时）
    bm25_dir = out_dir / "bm25"
    bm25_dir.mkdir(parents=True, exist_ok=True)
    (bm25_dir / "chunks.jsonl").write_text(
        "\n".join(json.dumps({"id": c.id, "text": c.text}, ensure_ascii=False) for c in chunks),
        encoding="utf-8",
    )

    stats = {"docs": len(docs), "chunks": len(chunks), "index_dir": str(out_dir)}
    log.info("索引构建完成: %s", stats)
    return stats


def load_index(index_dir: Path = DEFAULT_INDEX_DIR) -> NumpyVectorStore:
    """加载已构建的索引。"""
    return NumpyVectorStore.load(index_dir)


# ---------------------------------------------------------------------------
# QAService
# ---------------------------------------------------------------------------


class QAService:
    """知识库问答服务：单一入口，依赖注入，全链路可观测。"""

    def __init__(
        self,
        index_dir: Path = DEFAULT_INDEX_DIR,
        llm=None,
        embed_fn=None,
        *,
        top_k: int = 5,
        min_score: float = 0.55,
        rewrite: bool = False,
        temperature: float = 0.2,
    ):
        self.store = load_index(index_dir)
        self.llm = llm or get_client()
        self.embed_fn = embed_fn or get_embed_fn_or_fallback()
        self.top_k = top_k
        self.min_score = min_score
        self.rewrite = rewrite
        self.temperature = temperature

    # -- 查询改写 -------------------------------------------------------
    def _rewrite(self, question: str, history: list[dict] | None = None) -> list[str]:
        if not self.rewrite:
            return [question]
        result: ChatResult = self.llm.chat(
            [{"role": "user", "content": REWRITE_PROMPT.format(question=question)}],
            temperature=0.0, max_tokens=100,
        )
        rewritten = result.content.strip() or question
        return [rewritten, question]

    # -- 混合检索 -------------------------------------------------------
    def _hybrid_search(self, queries: list[str]) -> list[Hit]:
        """向量 top-20 + BM25 top-20 → RRF → 规则重排 → 余弦阈值 → top_k。"""
        chunks = self.store.chunks
        if not chunks:
            return []

        id_to_chunk = {c.id: c for c in chunks}
        all_hits: dict[str, Hit] = {}
        for q in queries:
            q_vec = self.embed_fn([q])[0]
            vector_hits: list[SearchHit] = self.store.query(q_vec, k=20)
            bm25 = BM25().add([c.text for c in chunks])
            bm25_hits = bm25.search(q, k=20)

            vector_ranking = [h.chunk.id for h in vector_hits]
            bm25_ranking = [chunks[i].id for i, _ in bm25_hits]

            fused = _rrf([vector_ranking, bm25_ranking])
            # 余弦分数映射（用于阈值过滤）
            cos_map = {h.chunk.id: h.score for h in vector_hits}
            for rank, (cid, rrf_score) in enumerate(fused[:20], 1):
                chunk = id_to_chunk.get(cid)
                if not chunk:
                    continue
                hit = Hit(chunk=chunk, score=rrf_score, rank_vector=rank)
                hit.chunk.metadata["_cosine"] = cos_map.get(cid, 0.0)
                if cid not in all_hits or rrf_score > all_hits[cid].score:
                    all_hits[cid] = hit

        hits = sorted(all_hits.values(), key=lambda h: h.score, reverse=True)
        hits = self._rule_rerank(hits, queries[0])
        # 阈值过滤：用余弦相似度（min_score 语义），RRF 分仅用于排序
        hits = [h for h in hits if h.chunk.metadata.get("_cosine", 0.0) >= self.min_score]
        return hits[: self.top_k]

    def _rule_rerank(self, hits: list[Hit], query: str) -> list[Hit]:
        """零成本重排：标题命中 + 时间新鲜度加权。"""
        now = datetime.now()
        terms = [t for t in query.split() if t] or [query]
        for h in hits:
            title = h.title
            title_bonus = 1.0 if any(t in title for t in terms) else 0.0
            published = h.chunk.metadata.get("effective_from") or h.chunk.metadata.get("published_at")
            fresh = 0.5
            if published:
                try:
                    ts = datetime.fromisoformat(str(published))
                    hours = max(0.0, (now - ts).total_seconds() / 3600)
                    fresh = max(0.0, 1 - hours / (24 * 30))
                except ValueError:
                    pass
            h.score = round(0.6 * h.score + 0.15 * fresh + 0.25 * title_bonus, 4)
            # 保留余弦分供阈值过滤（_hybrid_search 用）
            h.chunk.metadata["_cosine"] = h.chunk.metadata.get("_cosine", 0.0)
        return sorted(hits, key=lambda h: h.score, reverse=True)

    # -- 上下文 ---------------------------------------------------------
    @staticmethod
    def _build_context(hits: list[Hit]) -> str:
        blocks = []
        for i, h in enumerate(hits, 1):
            source = h.source
            section = h.chunk.metadata.get("section") or ""
            suffix = f" § {section}" if section else ""
            blocks.append(f"【资料 {i}｜来源：{source}{suffix}】\n{h.chunk.text.strip()}")
        return "\n\n".join(blocks)

    # -- 引用解析 -------------------------------------------------------
    @staticmethod
    def _parse_citations(text: str, hits: list[Hit]) -> list[Citation]:
        import re

        CITE = re.compile(r"\[资料\s*(\d+)\]|\[(\d+)\]")
        seen: set[int] = set()
        out: list[Citation] = []
        for m in CITE.finditer(text):
            n = int(m.group(1) or m.group(2))
            if not 1 <= n <= len(hits) or n in seen:
                continue
            seen.add(n)
            hit = hits[n - 1]
            out.append(Citation(n=n, source=hit.source, score=round(hit.score, 3), text=hit.chunk.text[:160]))
        return out

    # -- 主入口 ---------------------------------------------------------
    def ask(self, question: str, history: list[dict] | None = None) -> Answer:
        trace_id = uuid.uuid4().hex[:12]
        t0 = time.perf_counter()

        queries = self._rewrite(question, history)
        hits = self._hybrid_search(queries)

        if not hits:
            return Answer(
                question=question,
                answer="当前知识库没有找到相关内容。",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                trace_id=trace_id,
                refused=True,
            )

        prompt = PROMPT.format(context=self._build_context(hits), question=question)
        result: ChatResult = self.llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=self.temperature,
            max_tokens=600,
        )
        answer_text = result.content
        citations = self._parse_citations(answer_text, hits)

        return Answer(
            question=question,
            answer=answer_text,
            citations=citations,
            hits=hits,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            tokens=result.usage.total_tokens,
            cost_cny=result.cost_cny,
            trace_id=trace_id,
        )

    async def ask_stream(self, question: str, history: list[dict] | None = None):
        """异步流式问答（Day 20 SSE 用）。"""
        trace_id = uuid.uuid4().hex[:12]
        t0 = time.perf_counter()

        queries = self._rewrite(question, history)
        hits = self._hybrid_search(queries)

        if not hits:
            yield {"type": "refuse", "trace_id": trace_id}
            return

        prompt = PROMPT.format(context=self._build_context(hits), question=question)
        full_text = ""
        async for piece in self.llm.astream(
            [{"role": "user", "content": prompt}],
            temperature=self.temperature,
            max_tokens=600,
        ):
            full_text += piece
            yield {"type": "delta", "text": piece, "trace_id": trace_id}

        citations = self._parse_citations(full_text, hits)
        yield {
            "type": "done",
            "trace_id": trace_id,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "citations": [c.to_dict() for c in citations],
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="M2 知识库问答")
    parser.add_argument("question", nargs="?", default=None, help="提问")
    parser.add_argument("--rebuild", action="store_true", help="重建索引")
    parser.add_argument("--kb", default=str(DEFAULT_KB_PATH), help="知识库 JSONL 路径")
    parser.add_argument("--index-dir", default=str(DEFAULT_INDEX_DIR), help="索引目录")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-score", type=float, default=0.55)
    parser.add_argument("--rewrite", action="store_true", help="开启 LLM 查询改写")
    parser.add_argument("--eval-out", default=str(DEFAULT_EVAL_OUT), help="评估结果 CSV 输出路径")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    index_dir = Path(args.index_dir)

    if args.rebuild:
        stats = asyncio.run(build_index(Path(args.kb), index_dir))
        print(f"索引重建完成: {stats}")
        return 0

    if not args.question:
        parser.print_help()
        return 1

    service = QAService(
        index_dir=index_dir,
        top_k=args.top_k,
        min_score=args.min_score,
        rewrite=args.rewrite,
    )
    ans = service.ask(args.question)
    print(f"\n[trace_id] {ans.trace_id}")
    print(f"[latency] {ans.latency_ms} ms  [tokens] {ans.tokens}  [cost] ¥{ans.cost_cny:.6f}")
    print(f"\n{ans.answer}")
    if ans.citations:
        print("\n--- 引用 ---")
        for c in ans.citations:
            print(f"  [{c.n}] {c.source} (score={c.score})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
