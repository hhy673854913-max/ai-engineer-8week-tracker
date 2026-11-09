# Day 15 · 混合检索、查询改写与重排序

> W3 · 周五 ｜ 5h ｜ 产出 `code/week03/mini_rag/hybrid.py` + `evaluate.py` ｜ [Day 14](day-14.md) ｜ **本周里程碑**

**今日目标**
- 手写 BM25，理解"为什么关键词检索在专有名词上更强"
- 用 RRF 融合向量与 BM25，再用重排做精排
- 用 hit-rate@k / MRR 量化"优化前后到底好了多少"

**验收**：20 个问题上，混合检索 + 重排的 hit-rate@5 比纯向量检索有明确提升（并记录数字）。

---

## 上午 09:00–11:30 · 理论输入

### 1. 为什么需要混合检索

| 检索方式 | 强项 | 弱项 |
| --- | --- | --- |
| 向量（dense） | 同义改写、口语化提问 | 专有名词、编号、罕见词 |
| BM25（sparse） | 精确词命中、专名、长尾词 | 不理解同义、对措辞敏感 |

真实问题里两种都有：

- "春节活动怎么领奖" → 口语化，向量强
- "SPRING2026 兑换码在哪输入" → 专名，BM25 强

**混合检索不是"更高级"，而是"覆盖面更全"**。代价是要维护两套索引。

### 2. BM25 公式（理解即可，不背）

```text
score(q, d) = Σ_t IDF(t) × (tf × (k1 + 1)) / (tf + k1 × (1 - b + b × |d| / avgdl))
```

- `tf`：词 t 在文档 d 中的频次
- `IDF`：词越罕见权重越高——这就是专名强的原因
- `k1`（1.2–2.0）：词频饱和速度
- `b`（0.75）：文档长度归一化强度

中文要先分词：`jieba.lcut`。**分词质量直接决定 BM25 上限**，专名建议加进 `jieba.add_word()`。

BM25 是搜索引擎用了二十多年的关键词相关度打分函数，Elasticsearch / Lucene 的默认排序就是它（名字里的 25 是作者当年的编号）。手写一遍的理由很实际：调混合检索时你得凭手感判断 k1/b 往哪调，面试也常问"BM25 和向量检索各强在哪"；生产里你多半直接调 ES 或向量库自带的 sparse 检索，公式不用背，但 IDF 在压什么、长度归一化在补什么必须能讲出来。

### 3. 融合：RRF 比加权分数更稳

两路检索的分数**不可比**（余弦 0–1，BM25 无上界），直接加权是错的。RRF 只用排名：

```text
RRF(d) = Σ_i 1 / (k + rank_i(d))     # k 常取 60
```

优点：无需归一化、对异常分数鲁棒、实现 10 行。缺点：丢掉了分数的"置信度"信息。

### 4. 重排（Rerank）：用贵的模型看少数候选

```text
召回 50 条（便宜、快） → 重排 top 20 → 取 top 5 给 LLM
```

三种重排器：

| 类型 | 代表 | 成本 | 效果 |
| --- | --- | --- | --- |
| 交叉编码器 | BGE-Reranker | 中（本地 GPU 或 API） | 好 |
| LLM 重排 | 让模型给相关性打 0–10 分 | 高 | 很好，但慢 |
| 规则重排 | 时间衰减、来源权重、标题命中 | 极低 | 兜底 |

**工程顺序**：先上规则重排（几乎零成本），有效果再上交叉编码器，最后才考虑 LLM 重排。

原理上：召回用的 embedding 是双塔——query 和文档各自独立编码，文档向量能提前建索引；交叉编码器把 query 和文档拼成一对送进模型打分，能看见两者的交互，所以更准，但每条候选都要现算一次前向。这就是"召回 50 条、重排 20 条、给 LLM 5 条"的由来，也是面试问"为什么需要 rerank、延迟怎么控"时你要答的东西。

### 5. 查询改写（Query Rewriting）

用户的问法常常不适合检索：

| 原问题 | 改写 |
| --- | --- |
| "奖励啥时候到" | "奖励发放时间 到账时间" |
| "这个能退吗" | "退款条件 退款政策"（需结合对话历史） |
| "春节活动" | "2026 春节活动 规则 奖励" |

三种做法：
1. **规则**：补全指代词（"这个"→上一轮主题）
2. **LLM 改写**：让模型输出 3 个检索 query（多 query 召回后合并）
3. **HyDE**：让模型先"编"一个假答案，用假答案去检索（对模糊问题有效）

代价都是额外一次 LLM 调用。**先用规则，再考虑 LLM**。

落到代码上：在 `MiniRAG.answer()` 第一行加 `queries = self.rewrite(question)`（规则版：把"这个/它"替换成上一轮对话里的实体），各自 `retrieve` 后用今天 §3 的 RRF 合并去重，再进 `build_context`——这才是"这个能退吗"能召回退款规定的地方。做完把改写前后的 hit-rate@5 记一笔，你就有数据回答面试官"查询改写值不值一次额外 LLM 调用"。

### 6. 评测指标

| 指标 | 定义 | 说明 |
| --- | --- | --- |
| hit-rate@k | top-k 里是否包含正确块 | 最直观，先看这个 |
| MRR | 正确块排名的倒数均值 | 衡量"排得靠不靠前" |
| Recall@k | 所有正确块被召回的比例 | 多块答案时用 |
| nDCG@k | 考虑排序位置的相关性 | 有分级相关性时用 |

**先建 20–50 条评测集再优化**，否则你不知道改动是好是坏。这条纪律从今天开始，一直用到 Day 32。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 手写 BM25（70 min）

```python
class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs: list[list[str]] = []
        self.df: Counter[str] = Counter()
        self.avgdl: float = 0.0

    def add(self, texts: list[str]) -> None:
        for t in texts:
            toks = jieba.lcut(t)
            self.docs.append(toks)
            self.df.update(set(toks))
        self.avgdl = sum(len(d) for d in self.docs) / max(len(self.docs), 1)

    def search(self, query: str, k: int = 10) -> list[tuple[int, float]]:
        q = jieba.lcut(query)
        N = len(self.docs)
        scores = []
        for i, d in enumerate(self.docs):
            tf = Counter(d)
            s = 0.0
            for t in q:
                if t not in tf:
                    continue
                idf = math.log(1 + (N - self.df[t] + 0.5) / (self.df[t] + 0.5))
                denom = tf[t] + self.k1 * (1 - self.b + self.b * len(d) / self.avgdl)
                s += idf * tf[t] * (self.k1 + 1) / denom
            scores.append((i, s))
        return sorted(scores, key=lambda x: x[1], reverse=True)[:k]
```

写完用 3 个查询验证：专名查询应该 BM25 明显强于向量。

### 任务 2 · RRF 融合（40 min）

```python
def rrf(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    scores: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

### 任务 3 · 重排（40 min）

**规则重排先上**（零成本）：

```python
def rule_rerank(hits, now, w_time=0.15, w_title=0.25):
    for h in hits:
        h.score = (1 - w_time - w_title) * h.score \
                + w_time * freshness(h, now) \
                + w_title * (1.0 if query_terms_in(h.chunk.metadata["title"]) else 0.0)
    return sorted(hits, key=lambda h: h.score, reverse=True)
```

有条件再用 BGE-Reranker（本地 `sentence-transformers` 或 API），对比 hit-rate 差异。

### 任务 4 · 评测脚本（40 min）

```python
CASES = [{"q": "退款多久到账", "gold_ids": ["faq_pay#2"], "gold_kw": ["1-3 个工作日"]}, ...]

def hit_rate(hits, gold_ids) -> float:
    return 1.0 if any(h.chunk.id in gold_ids for h in hits) else 0.0

def mrr(hits, gold_ids) -> float:
    for i, h in enumerate(hits, 1):
        if h.chunk.id in gold_ids:
            return 1.0 / i
    return 0.0
```

跑四组对比：纯向量 / 纯 BM25 / RRF / RRF + 重排。把四个 hit-rate@5 写进 `logs/day-15.md`。

---

## 代码思考（写进 `logs/day-15.md`）

1. 为什么两路检索的分数不能直接加权？举一个"加权后效果变差"的具体数值例子。
2. RRF 的 `k=60` 从哪来？调大调小分别有什么效果？
3. BM25 对中文分词的依赖体现在哪？专名没被正确切分会怎样？
4. 规则重排的时间权重设 0.15 是基于什么假设？如果知识库是"经典文档、很少更新"，这个权重该怎么改？
5. hit-rate@5 从 0.65 提升到 0.80，但延迟从 80ms 涨到 350ms——这个交换值得吗？判断依据是什么？

## 复盘清单（本周里程碑自检）

- [ ] `mini_rag/` 总代码 ≤ 400 行，无框架依赖（除 httpx/openai）
- [ ] 四组对比的 hit-rate 有数字
- [ ] 写一份"我在每个环节的取舍"（分块/嵌入/检索/重排/阈值），≥ 500 字
- [ ] 录一段 60 秒演示：提问 → 答案 + 引用
- [ ] commit：`day15: BM25 + RRF + 重排 + 评测（hit-rate 提升 x）`
