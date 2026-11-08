"""Day 32 · 检索层评估（离线可跑）+ RAGAS 接入示例。

默认只算检索指标（hit-rate / MRR / recall），不需要 API Key：
    python -m code.week07.eval.run_eval

接上真实嵌入与生成后，再开 --ragas 跑忠实度等指标：
    python -m code.week07.eval.run_eval --ragas --limit 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.week03.mini_rag.chunking import load_markdown_dir  # noqa: E402
from code.week03.mini_rag.embeddings import HashingEmbedder, get_embed_fn  # noqa: E402
from code.week03.mini_rag.evaluate import evaluate  # noqa: E402
from code.week03.mini_rag.store import NumpyVectorStore  # noqa: E402

EVAL_SET = Path(__file__).resolve().parent / "eval_set.jsonl"
KB_DIR = ROOT / "data" / "kb_sample"


def build_store(offline: bool = True):
    embed = HashingEmbedder() if offline else get_embed_fn()
    chunks = load_markdown_dir(KB_DIR)
    store = NumpyVectorStore()
    store.upsert(chunks, embed([c.text for c in chunks]))
    return store, embed


def retrieval_eval(store, embed, cases: list[dict], k: int = 4) -> dict:
    """混合检索（向量 + BM25 → RRF）后再算指标，与 M2 的设计一致。"""
    from code.week03.mini_rag.hybrid import bm25_search, rrf

    chunks = store.chunks
    id_to_index = {c.id: i for i, c in enumerate(chunks)}

    def retrieve(question: str, top_k: int) -> list[str]:
        query_vector = embed([question])[0]
        vector_rank = [id_to_index[h.chunk.id] for h in store.query(query_vector, k=12) if h.chunk.id in id_to_index]
        bm25_rank = [i for i, _ in bm25_search(chunks, question, k=12)]
        fused = rrf([vector_rank, bm25_rank])[:top_k]
        return [chunks[i].metadata.get("doc_id", "") for i, _ in fused]

    result = evaluate(cases, retrieve, k=k)
    # 负样本单独看：误召回率
    negative = [c for c in cases if c.get("should_refuse")]
    false_positive = 0
    for case in negative:
        hits = store.query(embed([case["question"]])[0], k=k)
        if hits and hits[0].score > 0.35:
            false_positive += 1
    result["negative_cases"] = len(negative)
    result["negative_false_positive"] = false_positive
    result["negative_fp_rate"] = round(false_positive / max(len(negative), 1), 3)
    return result


def ragas_eval(cases: list[dict], store, embed, limit: int) -> dict:
    """RAGAS 需要 judge 模型；没有依赖或 Key 时给出明确提示。"""
    try:
        from datasets import Dataset
        from ragas import evaluate as ragas_evaluate
        from ragas.metrics import answer_relevancy, context_precision, faithfulness
    except ImportError as exc:
        return {"skipped": f"未安装 ragas/datasets：{exc}"}

    try:
        from code.shared.llm_client import get_client

        client = get_client()
    except Exception as exc:  # noqa: BLE001
        return {"skipped": f"没有可用的 LLM 配置：{exc}"}

    rows = []
    for case in [c for c in cases if not c.get("should_refuse")][:limit]:
        hits = store.query(embed([case["question"]])[0], k=4)
        answer = client.chat(
            [{"role": "user", "content": f"只依据资料回答：{case['question']}\n资料：" + "\n".join(h.text for h in hits)}],
            temperature=0,
        ).content
        rows.append(
            {
                "question": case["question"],
                "answer": answer,
                "contexts": [h.chunk.text for h in hits],
                "ground_truth": case["reference_answer"],
            }
        )

    ds = Dataset.from_list(rows)
    result = ragas_evaluate(ds, metrics=[faithfulness, answer_relevancy, context_precision], raise_exceptions=False)
    return {"ragas": {k: round(float(v), 4) for k, v in result.items() if isinstance(v, (int, float))}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", default=True, help="使用离线哈希嵌入器")
    parser.add_argument("--ragas", action="store_true", help="额外跑 RAGAS（需要 API Key 与依赖）")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--out", type=Path, default=ROOT / "output" / "eval_report.json")
    args = parser.parse_args()

    cases = [json.loads(line) for line in EVAL_SET.read_text(encoding="utf-8").splitlines() if line.strip()]
    store, embed = build_store(offline=True)
    report: dict = {"retrieval": retrieval_eval(store, embed, cases)}

    if args.ragas:
        report.update(ragas_eval(cases, store, embed, args.limit))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "retrieval"}, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report["retrieval"].items() if k != "rows"}, ensure_ascii=False, indent=2))
    print(f"\n报告已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
