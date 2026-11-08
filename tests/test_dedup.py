from code.week02.m1_brief.dedup import dedup, hamming, normalize_url, simhash


def test_normalize_url_strips_tracking_and_fragment():
    url = "https://Example.com/a?utm_source=rss&id=1#section"
    assert normalize_url(url) == "https://example.com/a?id=1"


def test_simhash_similar_texts_are_close():
    a = simhash("2026 春节活动将于 2 月 1 日开启，持续 14 天")
    b = simhash("2026 春节活动将于 2 月 1 日开启，持续 14 天。")
    c = simhash("服务器故障按影响时长补偿钻石")
    assert hamming(a, b) < hamming(a, c)


def test_dedup_exact_url():
    items = [
        {"url": "https://a.com/x?utm_source=rss", "title": "t", "content": "c"},
        {"url": "https://a.com/x", "title": "t", "content": "c"},
    ]
    kept, removed = dedup(items)
    assert len(kept) == 1
    assert removed == 1


def test_dedup_near_duplicate_content():
    body = "官方今日宣布春节活动将于二月一日开启持续十四天采用双人组队玩法"
    items = [
        {"url": "https://a.com/1", "title": "春节活动", "content": body},
        {"url": "https://a.com/2", "title": "春节活动", "content": body + "。"},
        {"url": "https://a.com/3", "title": "无关新闻", "content": "服务器故障补偿标准调整"},
    ]
    kept, removed = dedup(items, max_distance=3)
    assert removed >= 1
    assert any("无关" in i["title"] for i in kept)
