# Day 17 · LCEL 进阶与可配置检索链

> W4 · 周二 ｜ 5h ｜ 产出 `code/week04/configurable_chain.py` ｜ [Day 16](day-16.md) · [Day 18](day-18.md)

**今日目标**
- 把"写死的检索链"改造成**参数可配置**的链：分块策略、top-k、是否重排、是否改写
- 掌握 `RunnableParallel` / `RunnableBranch` / `RunnableLambda` 的组合
- 学会用配置做 A/B，而不是改代码

**验收**：同一份代码，换一份 `config.yaml` 就能跑出 4 种检索策略，并输出对比结果。

---

## 上午 09:00–11:30 · 理论输入

### 1. 为什么"可配置"是工程化的分水岭

三周前你写的是"能跑"；现在要写"能试"。RAG 的参数空间很大：

```text
chunk_size ∈ {300, 500, 800}
top_k ∈ {3, 5, 8}
rerank ∈ {none, rule, model}
rewrite ∈ {none, llm}
→ 3 × 3 × 3 × 2 = 54 种组合
```

如果每种组合都要改代码、重跑、记录，你会疯。所以：**参数外置 + 结果可复现**。

### 2. 配置模型（Pydantic）

```python
class RetrievalConfig(BaseModel):
    chunk_size: int = 500
    chunk_overlap: int = 80
    splitter: Literal["recursive", "fixed", "heading"] = "recursive"
    top_k: int = 5
    rerank: Literal["none", "rule", "model"] = "rule"
    rewrite: Literal["none", "llm"] = "none"
    min_score: float = 0.62

class AppConfig(BaseModel):
    retrieval: RetrievalConfig = RetrievalConfig()
    model: str = "deepseek-chat"
    temperature: float = 0.2
```

**配置也要校验**：`min_score` 超过 1 就应该报错，而不是静默失败。

### 3. LCEL 的四个组合件

| 组件 | 用途 | 例子 |
| --- | --- | --- |
| `RunnableLambda` | 把普通函数塞进链 | `RunnableLambda(rewrite_query)` |
| `RunnableParallel` | 并行分支 | `{"context": retriever, "question": passthrough}` |
| `RunnableBranch` | 条件路由 | 有历史 → 改写；无历史 → 原样 |
| `RunnablePassthrough.assign` | 透传并追加字段 | 在输入里加 `retrieved_docs` |

### 4. 可配置链的结构

```text
question
  ├─ [rewrite] → queries
  ├─ retriever(queries) → docs
  ├─ [rerank] → docs'
  ├─ build_context(docs') → context
  └─ prompt | llm | parser → answer
```

用 `RunnableLambda` 把每步包起来，配置决定"插不插这一步"：

```python
def build_chain(cfg: RetrievalConfig):
    steps = []
    if cfg.rewrite != "none":
        steps.append(RunnableLambda(make_rewriter(cfg)))
    steps.append(...)
    return compose(steps)
```

**不要为了用 LCEL 而用 LCEL**：如果链里全是 `RunnableLambda`，说明你其实在写普通函数。
判断标准：**LCEL 适合"线性 + 并行"的组合，复杂分支用普通 Python 更清楚。**

### 5. 可复现：把配置和结果一起存

```json
{
  "run_id": "20261130-142233",
  "config": {"chunk_size": 500, "top_k": 5, "rerank": "rule"},
  "metrics": {"hit_rate@5": 0.8, "mrr": 0.66, "avg_latency_ms": 850},
  "cases": [{"q": "...", "hit": true, "answer": "..."}]
}
```

没有 `run_id` 的实验等于没做——你三天后无法复现"那次 0.82 是怎么跑出来的"。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 配置加载（40 min）

```python
def load_config(path: Path = Path("config.yaml")) -> AppConfig:
    if path.exists():
        import yaml
        return AppConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    return AppConfig()
```

支持三层覆盖：默认值 → `config.yaml` → 环境变量（`RAG_TOP_K=8`）。环境变量优先级最高，方便部署。

### 任务 2 · 组装可配置链（90 min）

```python
class RagPipeline:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.retriever = build_retriever(cfg)   # 分块 + 入库 + top_k
        self.reranker = build_reranker(cfg)     # none/rule/model
        self.rewriter = build_rewriter(cfg)     # none/llm

    def run(self, question: str, history: list[dict] | None = None) -> dict:
        queries = self.rewriter(question, history) if self.rewriter else [question]
        docs = merge_docs([self.retriever(q) for q in queries])
        docs = self.reranker(question, docs) if self.reranker else docs
        if not docs:
            return {"answer": "当前知识库没有找到相关内容。", "docs": [], "queries": queries}
        ctx = build_context(docs)
        answer = self.llm(PROMPT.format(context=ctx, question=question))
        return {"answer": answer, "docs": docs, "queries": queries}
```

注意 `merge_docs`：多 query 召回后要**按 id 去重并按最优排名排序**，否则同一块出现多次。

### 任务 3 · 四种策略对比（60 min）

写 `python -m week04.configurable_chain --sweep`，跑：

| 策略 | hit-rate@5 | MRR | 平均延迟 | 平均 token |
| --- | --- | --- | --- | --- |
| baseline（无重排无改写） | | | | |
| + rule rerank | | | | |
| + llm rewrite | | | | |
| + 两者都开 | | | | |

**注意**：LLM 改写会让每次查询多一次调用，延迟与成本都会涨。表格里必须体现，否则"优化"是自欺欺人。

### 任务 4 · 失败归因（30 min）

把没命中的 case 逐条归类：分块问题 / 改写跑偏 / 重排把正确块排后 / 知识库确实没有。
写进 `logs/day-17.md`。

---

## 代码思考（写进 `logs/day-17.md`）

1. 多 query 召回后直接拼接会带来什么问题？去重与排序应该按什么规则？
2. `RunnableBranch` 和普通 `if` 相比，优势在哪？什么情况下反而更糟？
3. 配置里 `min_score` 与 `top_k` 有耦合吗？调小 `top_k` 时阈值该不该跟着调？
4. 实验记录里如果不存 `config`，三天后会发生什么？你打算怎么保证可复现？
5. 四种策略里，如果"+llm rewrite"只提升了 2 个点却让延迟翻倍，你会保留吗？向谁汇报这个决策？

## 复盘清单

- [ ] 一份 `config.yaml` 能切换 4 种策略
- [ ] `run_id` + 结果落盘可复现
- [ ] 对比表有延迟与 token 成本
- [ ] commit：`day17: 可配置 RAG 链 + 四种策略对比`
