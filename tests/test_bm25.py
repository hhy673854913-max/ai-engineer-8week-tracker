from code.week03.mini_rag.bm25 import BM25, tokenize


DOCS = [
    "退款一般 1-3 个工作日到账，银行卡渠道可能延长至 5 个工作日。",
    "春节活动奖励将在活动结束后 7 个工作日内发放。",
    "服务器故障按影响时长补偿钻石。",
]


def test_tokenize_nonempty():
    tokens = tokenize("退款多久到账")
    assert tokens


def test_bm25_ranks_relevant_doc_first():
    index = BM25().add(DOCS)
    results = index.search("退款到账要多久", k=3)
    assert results
    assert results[0][0] == 0


def test_bm25_no_match_returns_empty():
    index = BM25().add(DOCS)
    assert index.search("完全无关的查询词zzz", k=3) == []


def test_bm25_idf_prefers_rare_term():
    index = BM25().add(DOCS)
    # "服务器" 只出现在第 3 篇，IDF 高
    results = index.search("服务器故障", k=3)
    assert results[0][0] == 2
