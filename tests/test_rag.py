from code.week03.mini_rag.chunking import Chunk
from code.week03.mini_rag.evaluate import evaluate, hit_at_k, mrr
from code.week03.mini_rag.hybrid import rrf
from code.week03.mini_rag.rag import MiniRAG, check_citations
from code.week03.mini_rag.store import NumpyVectorStore, SearchHit


def make_store():
    chunks = [
        Chunk.make("退款一般 1-3 个工作日到账。", "faq", 0, source="refund.md"),
        Chunk.make("奖励将在活动结束后 7 个工作日内发放。", "activity", 0, source="spring.md"),
    ]
    vectors = [[1.0, 0.0], [0.0, 1.0]]
    store = NumpyVectorStore()
    store.upsert(chunks, vectors)
    return store


def test_store_query_and_delete():
    store = make_store()
    hits = store.query([1.0, 0.0], k=1)
    assert hits[0].chunk.id.startswith("faq")
    assert store.delete(where={"source": "spring.md"}) == 1
    assert len(store) == 1


def test_store_where_filter():
    store = make_store()
    hits = store.query([1.0, 0.0], k=5, where={"source": "spring.md"})
    assert len(hits) == 1
    assert hits[0].chunk.metadata["source"] == "spring.md"


def test_rrf_prefers_consensus():
    fused = rrf([[1, 2, 3], [2, 3, 1]])
    assert fused[0][0] in {1, 2}


def test_citation_parse_and_invalid_check():
    hits = [SearchHit(Chunk.make("A", "d", 0, source="a.md"), 0.9),
            SearchHit(Chunk.make("B", "d", 1, source="b.md"), 0.8)]
    parsed = MiniRAG.parse_citations("结论一 [资料 1]，结论二 [2]，错误 [5]", hits)
    assert [c["n"] for c in parsed] == [1, 2]
    assert check_citations("看 [5]", hits) == [5]


def test_refuse_when_below_threshold():
    store = make_store()
    # 查询向量与两个块都不完全同向（余弦约 0.707），低于 0.99 阈值 → 应拒答
    rag = MiniRAG(store, lambda texts: [[0.7, 0.7] for _ in texts], chat_fn=None, min_score=0.99)
    result = rag.answer("退款")
    assert result.refused is True


def test_evaluate_metrics():
    cases = [
        {"question": "q1", "gold_ids": ["a"], "should_refuse": False},
        {"question": "q2", "gold_ids": ["b"], "should_refuse": False},
        {"question": "q3", "gold_ids": [], "should_refuse": True},
    ]

    def retrieve(q, k):
        return ["a", "x"] if q == "q1" else ["x", "b"]

    result = evaluate(cases, retrieve, k=2)
    assert result["n"] == 2
    assert result["hit_rate"] == 1.0
    assert 0 < result["mrr"] <= 1.0
    assert hit_at_k(["x", "a"], {"a"}, k=2) == 1.0
    assert mrr(["x", "a"], {"a"}) == 0.5
