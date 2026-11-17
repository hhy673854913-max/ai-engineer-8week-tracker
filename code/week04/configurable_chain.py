"""Day 17 · 可配置检索链：参数外置 + 四种策略对比。

设计要点：
1. 配置三层覆盖：默认值 → config.yaml → 环境变量（RAG_*）
2. 同一套代码，换 config 即切换检索策略（分块 / top-k / 重排 / 改写）
3. run_id + 配置 + 结果一起落盘，实验可复现

用法：
    python -m code.week04.configurable_chain "问题"
    python -m code.week04.configurable_chain --sweep
    python -m code.week04.configurable_chain --sweep --kb data/kb_sample --out output/day17_sweep.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import BaseModel

from code.week03.mini_rag.chunking import Chunk, chunk_fixed, chunk_recursive, chunk_by_heading
from code.week03.mini_rag.embeddings import HashingEmbedder, get_embed_fn, EmbedConfigError
from code.week03.mini_rag.store import NumpyVectorStore, SearchHit
from code.week03.mini_rag.bm25 import BM25
from code.week03.mini_rag.hybrid import rrf as _rrf
from code.shared.llm_client import get_client, ChatResult

PROMPT = """你是严谨的知识库问答助手。请只依据下面的资料回答问题。

规则：
1. 只使用资料中的信息，资料没有的内容明确说"资料未提及"；
2. 每个结论后用 [资料 n] 标注来源，n 是资料编号；
3. 如果资料与问题无关，直接回答"当前知识库没有找到相关内容"；
4. 回答控制在 200 字以内，不使用感叹号。

资料：
{context}

问题：{question}
"""

REWRITE_PROMPT = """请将用户问题改写成适合检索知识库的查询，保留关键实体名。
原问题：{question}
改写后："""


# ---------------------------------------------------------------------------
# 配置模型（Pydantic）
# ---------------------------------------------------------------------------


class RetrievalConfig(BaseModel):
    """检索策略参数。所有调参都在这里，不动代码。"""

    chunk_size: int = 500
    chunk_overlap: int = 80
    splitter: Literal["recursive", "fixed", "heading"] = "recursive"
    top_k: int = 5
    rerank: Literal["none", "rule", "model"] = "rule"
    rewrite: Literal["none", "llm"] = "none"
    min_score: float = 0.62

    def model_post_init(self, __context: Any) -> None:
        if not 0 <= self.min_score <= 1:
            raise ValueError(f"min_score 必须在 [0,1] 区间，当前: {self.min_score}")
        if self.chunk_size <= 0:
            raise ValueError("chunk_size 必须为正整数")
        if self.top_k <= 0:
            raise ValueError("top_k 必须为正整数")


class AppConfig(BaseModel):
    retrieval: RetrievalConfig = RetrievalConfig()
    model: str = "deepseek-chat"
    temperature: float = 0.2

    def model_post_init(self, __context: Any) -> None:
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature 必须在 [0,2] 区间")


def load_config(path: Path = Path("config.yaml")) -> AppConfig:
    """三层覆盖：默认值 → config.yaml → 环境变量（优先级最高）。"""
    data: dict[str, Any] = {}
    if path.exists():
        try:
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except ImportError:
            # 没有 yaml 时用最小 JSON 解析（config.yaml 也可能是 JSON 兼容格式）
            data = json.loads(path.read_text(encoding="utf-8"))

    # 环境变量覆盖：RAG_TOP_K / RAG_CHUNK_SIZE / RAG_MIN_SCORE / RAG_RERANK / RAG_REWRITE
    env_map = {
        "RAG_TOP_K": ("retrieval", "top_k", int),
        "RAG_CHUNK_SIZE": ("retrieval", "chunk_size", int),
        "RAG_CHUNK_OVERLAP": ("retrieval", "chunk_overlap", int),
        "RAG_MIN_SCORE": ("retrieval", "min_score", float),
        "RAG_RERANK": ("retrieval", "rerank", str),
        "RAG_REWRITE": ("retrieval", "rewrite", str),
        "RAG_SPLITTER": ("retrieval", "splitter", str),
        "RAG_MODEL": (None, "model", str),
        "RAG_TEMPERATURE": (None, "temperature", float),
    }
    for env_key, (section, field_name, caster) in env_map.items():
        raw = os.getenv(env_key)
        if raw is None:
            continue
        if section:
            data.setdefault(section, {})[field_name] = caster(raw)
        else:
            data[field_name] = caster(raw)

    return AppConfig.model_validate(data)


# ---------------------------------------------------------------------------
# 分块 + 入库
# ---------------------------------------------------------------------------


def load_documents(kb_dir: Path) -> list[Chunk]:
    """读取 markdown → 按配置分块 → 带元数据。"""
    docs = sorted(kb_dir.rglob("*.md"))
    if not docs:
        raise FileNotFoundError(f"{kb_dir} 下没有 .md 文件")
    chunks: list[Chunk] = []
    for path in docs:
        text = path.read_text(encoding="utf-8")
        meta = {"source": path.name, "path": str(path.relative_to(kb_dir))}
        chunks.extend(_do_split(text, meta))
    return chunks


def _do_split(text: str, meta: dict[str, str]) -> list[Chunk]:
    """根据当前全局配置分块（由 build_index 先设置 _CURRENT_CFG）。"""
    cfg = _CURRENT_CFG
    if cfg.splitter == "fixed":
        out = chunk_fixed(text, size=cfg.chunk_size, overlap=cfg.chunk_overlap)
    elif cfg.splitter == "recursive":
        out = chunk_recursive(text, size=cfg.chunk_size, overlap=cfg.chunk_overlap)
    else:  # heading
        out = chunk_by_heading(text, max_size=cfg.chunk_size)
    for c in out:
        c.metadata.update(meta)
        c.metadata.setdefault("title", meta["source"].rsplit(".", 1)[0])
    return out


# 模块级当前配置（分块函数需要读它；多线程不安全但教学可接受）
_CURRENT_CFG: RetrievalConfig = RetrievalConfig()


def build_index(kb_dir: Path, cfg: RetrievalConfig) -> NumpyVectorStore:
    """分块 + 嵌入 + 入库，返回可查询的向量库。"""
    global _CURRENT_CFG
    _CURRENT_CFG = cfg
    chunks = load_documents(kb_dir)

    # 优先真实嵌入；失败时回退哈希嵌入（保证可跑）
    try:
        embed_fn = get_embed_fn()
    except EmbedConfigError:
        embed_fn = HashingEmbedder()

    vectors = embed_fn([c.text for c in chunks])
    store = NumpyVectorStore()
    store.upsert(chunks, vectors)
    return store


# ---------------------------------------------------------------------------
# 检索组件
# ---------------------------------------------------------------------------


@dataclass
class RetrievedDoc:
    """多路召回后的统一文档表示。"""

    chunk: Chunk
    score: float
    rank_vector: int = 0  # 向量路排名
    rank_bm25: int = 0  # BM25 路排名


def merge_docs(doc_lists: list[list[RetrievedDoc]]) -> list[RetrievedDoc]:
    """多 query 召回后：按 chunk.id 去重，保留最优排名，按 RRF 分数排序。"""
    best: dict[str, RetrievedDoc] = {}
    for docs in doc_lists:
        for rank, d in enumerate(docs, 1):
            key = d.chunk.id
            d.rank_vector = rank  # 记录在该 query 下的名次
            if key not in best or d.score > best[key].score:
                best[key] = d
    # 用 RRF 融合多 query 的名次（单 query 时退化为按 score 排序）
    return sorted(best.values(), key=lambda d: d.score, reverse=True)


def hybrid_retrieve(store: NumpyVectorStore, query: str, embed_fn, k: int = 20) -> list[RetrievedDoc]:
    """向量 top-k + BM25 top-k → RRF 融合 → 返回 RetrievedDoc 列表。"""
    chunks = store.chunks
    if not chunks:
        return []

    q_vec = embed_fn([query])[0]
    vector_hits: list[SearchHit] = store.query(q_vec, k=k)
    bm25 = BM25().add([c.text for c in chunks])
    bm25_hits = bm25.search(query, k=k)

    id_to_chunk = {c.id: c for c in chunks}
    vector_ranking = [h.chunk.id for h in vector_hits]
    bm25_ranking = [chunks[i].id for i, _ in bm25_hits]

    fused = _rrf([vector_ranking, bm25_ranking])
    out: list[RetrievedDoc] = []
    for cid, score in fused[:k]:
        chunk = id_to_chunk.get(cid)
        if chunk:
            # 用向量分数作为粗分，RRF 分作为排序键存入 score
            out.append(RetrievedDoc(chunk=chunk, score=score))
    return out


def rule_rerank_docs(docs: list[RetrievedDoc], query: str) -> list[RetrievedDoc]:
    """把 week03 的 rule_rerank 适配到 RetrievedDoc（时间 + 标题命中加权）。"""
    now = datetime.now()
    terms = [t for t in query.split() if t] or [query]
    for d in docs:
        title = str(d.chunk.metadata.get("title") or "")
        title_bonus = 1.0 if any(t in title for t in terms) else 0.0
        published = d.chunk.metadata.get("published_at") or d.chunk.metadata.get("effective_from")
        fresh = 0.5
        if published:
            try:
                ts = datetime.fromisoformat(str(published))
                hours = max(0.0, (now - ts).total_seconds() / 3600)
                fresh = max(0.0, 1 - hours / (24 * 30))
            except ValueError:
                pass
        d.score = round(0.6 * d.score + 0.15 * fresh + 0.25 * title_bonus, 4)
    return sorted(docs, key=lambda d: d.score, reverse=True)


# ---------------------------------------------------------------------------
# RagPipeline
# ---------------------------------------------------------------------------


@dataclass
class PipelineResult:
    answer: str
    docs: list[RetrievedDoc]
    queries: list[str]
    latency_ms: int
    tokens: int
    cost_cny: float
    run_id: str


class RagPipeline:
    """可配置 RAG 链：rewrite → hybrid retrieve → rerank → threshold → llm。"""

    def __init__(self, cfg: AppConfig, kb_dir: Path):
        self.cfg = cfg
        self.store = build_index(kb_dir, cfg.retrieval)
        # 重新获取 embed_fn 给检索用（build_index 内部的局部变量不外泄）
        try:
            self.embed_fn = get_embed_fn()
        except EmbedConfigError:
            self.embed_fn = HashingEmbedder()
        self.llm = get_client()
        self.run_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    # -- 改写 -----------------------------------------------------------
    def rewrite(self, question: str, history: list[dict] | None = None) -> list[str]:
        if self.cfg.retrieval.rewrite != "llm":
            return [question]
        prompt = REWRITE_PROMPT.format(question=question)
        result: ChatResult = self.llm.chat(
            [{"role": "user", "content": prompt}], temperature=0.0, max_tokens=100
        )
        rewritten = result.content.strip() or question
        return [rewritten, question]  # 改写 + 原问双路召回

    # -- 检索 -----------------------------------------------------------
    def retrieve(self, queries: list[str]) -> list[RetrievedDoc]:
        per_query = [hybrid_retrieve(self.store, q, self.embed_fn, k=20) for q in queries]
        docs = merge_docs(per_query)
        if self.cfg.retrieval.rerank == "rule":
            docs = rule_rerank_docs(docs, queries[0])
        docs = docs[: self.cfg.retrieval.top_k]
        # 阈值过滤：RRF 分数过低说明两路检索都不认可，倾向拒答
        return [d for d in docs if d.score >= 0.005]

    # -- 上下文 ---------------------------------------------------------
    @staticmethod
    def build_context(docs: list[RetrievedDoc]) -> str:
        blocks = []
        for i, d in enumerate(docs, 1):
            source = d.chunk.metadata.get("source", "未知")
            blocks.append(f"【资料 {i}｜{source}】\n{d.chunk.text.strip()}")
        return "\n\n".join(blocks)

    # -- 主入口 ---------------------------------------------------------
    def run(self, question: str, history: list[dict] | None = None) -> PipelineResult:
        t0 = time.perf_counter()
        queries = self.rewrite(question, history)
        docs = self.retrieve(queries)

        if not docs:
            return PipelineResult(
                answer="当前知识库没有找到相关内容。",
                docs=[], queries=queries,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                tokens=0, cost_cny=0.0, run_id=self.run_id,
            )

        prompt = PROMPT.format(context=self.build_context(docs), question=question)
        result: ChatResult = self.llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=self.cfg.temperature,
            max_tokens=600,
        )
        return PipelineResult(
            answer=result.content,
            docs=docs, queries=queries,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            tokens=result.usage.total_tokens,
            cost_cny=result.cost_cny,
            run_id=self.run_id,
        )


# ---------------------------------------------------------------------------
# 四种策略对比（--sweep）
# ---------------------------------------------------------------------------


@dataclass
class StrategyResult:
    name: str
    hit_rate: float
    mrr: float
    avg_latency_ms: float
    avg_tokens: float
    avg_cost_cny: float
    cfg: dict[str, Any]


def make_strategies() -> list[tuple[str, RetrievalConfig]]:
    """预定义的四种策略。"""
    base = RetrievalConfig()
    return [
        ("baseline（无重排无改写）", RetrievalConfig(rerank="none", rewrite="none")),
        ("+ rule rerank", RetrievalConfig(rerank="rule", rewrite="none")),
        ("+ llm rewrite", RetrievalConfig(rerank="none", rewrite="llm")),
        ("+ 两者都开", RetrievalConfig(rerank="rule", rewrite="llm")),
    ]


# 内置评估问题（示例，可根据实际知识库扩充）
EVAL_QUESTIONS: list[dict[str, Any]] = [
    {"q": "退款多久到账", "gold_source": "refund-faq.md"},
    {"q": "春节活动奖励什么时候发", "gold_source": "spring-activity.md"},
    {"q": "补偿标准是什么", "gold_source": "compensation.md"},
    {"q": "活动参与条件有哪些", "gold_source": "spring-activity.md"},
    {"q": "如何申请退款", "gold_source": "refund-faq.md"},
]


def _hit_and_mrr(docs: list[RetrievedDoc], gold_source: str) -> tuple[int, float]:
    """计算单条 query 的 hit@k 与 MRR（按 gold_source 文件名匹配）。"""
    for rank, d in enumerate(docs, 1):
        src = str(d.chunk.metadata.get("source", ""))
        if gold_source in src or src in gold_source:
            return 1, 1.0 / rank
    return 0, 0.0


def sweep(kb_dir: Path, out_path: Path | None = None) -> list[StrategyResult]:
    """跑四种策略，输出对比表。"""
    app_cfg = AppConfig()
    results: list[StrategyResult] = []

    print(f"{'策略':<20} {'hit@5':>8} {'MRR':>8} {'平均延迟ms':>12} {'平均token':>12} {'平均成本¥':>12}")
    print("-" * 76)

    for name, ret_cfg in make_strategies():
        cfg = AppConfig(retrieval=ret_cfg, model=app_cfg.model, temperature=app_cfg.temperature)
        pipeline = RagPipeline(cfg, kb_dir)

        hits, mrrs, latencies, tokens, costs = [], [], [], [], []
        for case in EVAL_QUESTIONS:
            res = pipeline.run(case["q"])
            hit, m = _hit_and_mrr(res.docs, case["gold_source"])
            hits.append(hit)
            mrrs.append(m)
            latencies.append(res.latency_ms)
            tokens.append(res.tokens)
            costs.append(res.cost_cny)

        sr = StrategyResult(
            name=name,
            hit_rate=round(sum(hits) / len(hits), 3),
            mrr=round(sum(mrrs) / len(mrrs), 3),
            avg_latency_ms=round(sum(latencies) / len(latencies), 1),
            avg_tokens=round(sum(tokens) / len(tokens), 1),
            avg_cost_cny=round(sum(costs) / len(costs), 6),
            cfg=ret_cfg.model_dump(),
        )
        results.append(sr)
        print(f"{name:<20} {sr.hit_rate:>8.3f} {sr.mrr:>8.3f} {sr.avg_latency_ms:>12.1f} {sr.avg_tokens:>12.1f} {sr.avg_cost_cny:>12.6f}")

    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
            "kb_dir": str(kb_dir),
            "eval_questions": len(EVAL_QUESTIONS),
            "results": [r.__dict__ for r in results],
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n对比结果已写入: {out_path}")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="可配置 RAG 链")
    parser.add_argument("question", nargs="?", default=None, help="提问（省略时跑 --sweep）")
    parser.add_argument("--kb", default=str(ROOT / "data" / "kb_sample"), help="知识库目录")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--sweep", action="store_true", help="跑四种策略对比")
    parser.add_argument("--out", default=None, help="sweep 结果输出 JSON 路径")
    args = parser.parse_args()

    kb_dir = Path(args.kb)

    if args.sweep or not args.question:
        sweep(kb_dir, out_path=args.out or ROOT / "output" / "day17_sweep.json")
        return 0

    cfg = load_config(Path(args.config))
    pipeline = RagPipeline(cfg, kb_dir)
    res = pipeline.run(args.question)
    print(f"\n[run_id] {res.run_id}")
    print(f"[queries] {res.queries}")
    print(f"[latency] {res.latency_ms} ms  [tokens] {res.tokens}  [cost] ¥{res.cost_cny:.6f}")
    print(f"\n{res.answer}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
