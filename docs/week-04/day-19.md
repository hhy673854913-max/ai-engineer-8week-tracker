# Day 19 · M2 开发（一）：问答链路与 Badcase 记录

> W4 · 周四 ｜ 5h ｜ 产出 `code/week04/m2_kb/qa_chain.py` ｜ [Day 18](day-18.md) · [Day 20](day-20.md)

**今日目标**
- 把第 3 周的 mini-RAG 接到真实的 100 条知识库上，跑通"文档 → 块 → 向量 → 问答"
- 建立**Badcase 工作流**：每条错例都有 id、现象、归因、修复动作、验证结果
- 用 20 组真实问题做首轮人工测试，产出第一版指标

**验收**：`python -m week04.m2_kb.qa_chain "问题"` 返回答案 + 引用；`badcases.md` 有 ≥ 10 条记录。

---

## 上午 09:00–11:30 · 工程要点

### 1. 从"能跑"到"能维护"

昨天的数据是 100 条结构化文档，今天要做三件事让链路可维护：

1. **单一入口**：`QAService.ask(question) -> Answer`，所有调用方（CLI / API / 测试）都走它
2. **可注入依赖**：embedder、llm、retriever 都从外部传入，方便 mock 与替换
3. **可观测**：每次调用记录 `question / queries / hits / latency / tokens / cost`

```python
@dataclass
class Answer:
    question: str
    answer: str
    citations: list[Citation]
    hits: list[Hit]
    latency_ms: int
    tokens: int
    cost_cny: float
    trace_id: str
```

**`trace_id` 从第一天就加**：出问题时你能凭它找回完整调用链（Day 33 的 Langfuse 就是干这个的）。

### 2. 建索引的顺序很关键

```
读取 docs.jsonl → 校验 schema → 过滤过期/空文档 → 分块 → 上下文化 → 批量嵌入 → 写向量库 + BM25 索引
```

三个容易忽略的点：

- **先过滤再嵌入**：过期文档不要浪费 token
- **上下文化**：嵌入的文本用 `标题 + 分类 + 正文`，但**存进库里的是正文**（展示时不要标题重复）
- **批量嵌入**：每条文档一次 API 调用是灾难，一次 10–20 条

### 3. 并发与限流

100 条 → 约 300 个块 → 15 批。用 `asyncio.Semaphore(5)` 控制并发。
不要 `asyncio.gather(*all)` 一次发 300 个请求，429 会让你重试风暴。

### 4. Badcase 的分类框架

| 类别 | 判据 | 典型修法 |
| --- | --- | --- |
| A 检索未召回 | gold 块不在 top-k | 改分块 / 加 BM25 / 改嵌入文本 |
| B 召回但排序差 | gold 块在 6–20 名 | 重排 / 加关键词权重 |
| C 上下文不足 | 召回块缺关键句 | 增大 chunk / 加相邻块 |
| D 生成答错 | 上下文有答案但答错 | 改 prompt / 降温度 / 换模型 |
| E 引用错误 | 编号错/不存在 | 修引用格式 / 加校验 |
| F 拒答误判 | 有答案却拒答 | 调阈值 |
| G 知识库缺失 | 确实没有 | 补数据 |

**七类不是学术分类，而是"下一步该改哪里"的决策树。** 没有分类的 badcase 列表等于没记录。

### 5. 20 组测试的纪律

- 问题从**真实用户会怎么问**出发，不要自己造"完美的检索式问题"
- 逐条记录，不要只记"错了 5 个"
- 同一条 badcase 修完要**回归验证**（改 A 问题别把 B 问题弄坏）

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 建索引（50 min）

```python
async def build_index(docs_path: Path, out_dir: Path) -> dict:
    docs = [KBDoc.model_validate_json(l) for l in docs_path.read_text(encoding="utf-8").splitlines()]
    docs = [d for d in docs if d.content.strip() and is_effective(d)]
    chunks = []
    for d in docs:
        for c in chunk_by_heading(d.content, max_size=500):
            c.metadata.update({"doc_id": d.doc_id, "title": d.title, "category": d.category,
                               "effective_from": str(d.effective_from), "source": d.source})
            chunks.append(c)
    vectors = await embed_batched([f"{c.metadata['title']}\n{c.text}" for c in chunks], concurrency=5)
    save_index(out_dir, chunks, vectors)
    return {"docs": len(docs), "chunks": len(chunks)}
```

### 任务 2 · QAService（80 min）

```python
class QAService:
    def __init__(self, index_dir: Path, llm, cfg: AppConfig):
        self.store = load_index(index_dir)
        self.llm, self.cfg = llm, cfg

    def ask(self, question: str, history: list[dict] | None = None) -> Answer:
        t0 = time.perf_counter()
        queries = rewrite(question, history) if self.cfg.retrieval.rewrite == "llm" else [question]
        hits = self._hybrid_search(queries)
        if not hits:
            return self._refuse(question, t0)
        ctx = build_context(hits)
        raw = self.llm.chat(PROMPT.format(context=ctx, question=question), temperature=self.cfg.temperature)
        return self._finish(question, raw, hits, t0)
```

`_hybrid_search` 内部：向量 top-20 + BM25 top-20 → RRF → 规则重排 → 阈值过滤 → top-5。

### 任务 3 · 20 组人工测试（60 min）

写 `code/week04/m2_kb/eval_manual.py`，输出 CSV：

```csv
id,question,hit,answer_ok,citation_ok,latency_ms,tokens,note
1,奖励什么时候发,1,1,1,1200,830,
2,奖励咋还没到,0,0,0,980,810,检索到了别的活动
```

### 任务 4 · Badcase 归档（30 min）

在 `docs/week-04/badcases.md` 建表：`ID / 问题 / 现象 / 类别(A-G) / 根因 / 修复动作 / 状态`。
**先归档再修**，别边修边忘。

---

## 代码思考（写进 `logs/day-19.md`）

1. 为什么要把 embedder / llm 作为参数注入，而不是在类里直接 new？（提示：测试、切换供应商、评估）
2. 上下文化嵌入（标题 + 正文）与"存正文"分开，能避免什么问题？
3. 20 个问题里 7 个错，其中 5 个是 C 类（上下文不足），你会调 chunk_size 还是加"相邻块扩展"？为什么？
4. `trace_id` 用一个自增整数和用 `uuid4` 有什么区别？线上排查时哪个更好？
5. 修完一个 A 类 badcase，怎么确认没有把 B 类弄坏？（提示：回归集）

## 复盘清单

- [ ] 索引构建脚本可重复执行（幂等）
- [ ] `QAService.ask` 有完整返回结构（含延迟/成本/trace）
- [ ] 20 组测试 CSV 已落盘
- [ ] `badcases.md` ≥ 10 条，每条有类别与动作
- [ ] commit：`M2: 索引构建 + QAService + 20 组测试 + badcase 归档`
