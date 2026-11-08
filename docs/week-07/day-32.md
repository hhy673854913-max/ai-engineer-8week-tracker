# Day 32 · RAGAS 自动化评估

> W7 · 周二 ｜ 5h ｜ 产出 `code/week07/eval/run_ragas.py` + 第一份量化报告 ｜ [Day 31](day-31.md) · [Day 33](day-33.md)

**今日目标**
- 用 RAGAS 跑通自动化评估，产出**四个核心指标**：忠实度、答案相关性、上下文精度、上下文召回
- 理解每个指标的**计算方式与失效场景**，不把分数当真理
- 产出一份能放进 README 的评估报告

**验收**：`python -m week07.eval.run_ragas` 输出 JSON + Markdown 报告，含指标、样本数、配置、badcase 列表。

---

## 上午 09:00–11:30 · 理论

### 1. RAGAS 的四个核心指标

| 指标 | 问的问题 | 怎么算（直觉） |
| --- | --- | --- |
| **Faithfulness**（忠实度） | 答案里的每个论断，上下文支持吗？ | 把答案拆成论断，逐条判断能否从上下文推出 |
| **Answer Relevancy**（答案相关性） | 答案真的回答了问题吗？ | 用答案反推问题，与原始问题比相似度 |
| **Context Precision**（上下文精度） | 检索到的块里，有用的排前面吗？ | 逐个判断块是否相关，算加权精度 |
| **Context Recall**（上下文召回） | 回答问题所需的信息，检索到了吗？ | 用参考答案的论断反查上下文覆盖度 |

四个指标合起来回答两个问题：**检索对不对**（precision/recall）、**生成老不老实**（faithfulness/relevancy）。

### 2. 指标背后的 LLM 调用

RAGAS 不是"公式计算"，它内部大量调用 LLM 做判断。所以：

- 成本 ≈ 样本数 × 4 个指标 × 若干次调用
- 结果受 judge 模型影响很大（换模型分数会变）
- 慢：50 条样本可能要 5–10 分钟

**实践**：先用 10 条样本试跑，确认流程与成本，再全量跑。

### 3. RAGAS 的基本用法

```python
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper

ds = Dataset.from_dict({
    "question": [...],
    "answer": [...],
    "contexts": [[...], ...],       # 每个问题对应的检索块列表
    "ground_truth": [...],          # 参考答案（Context Recall 需要）
})

result = evaluate(
    ds,
    metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
    llm=LangchainLLMWrapper(judge_llm),
    embeddings=LangchainEmbeddingsWrapper(judge_emb),
)
print(result)
```

**版本差异很大**：RAGAS 0.1 → 0.2 的 API 变过（`evaluate` 参数、`Dataset` 构造方式）。
以你安装版本的文档为准，别照抄博客。

### 4. 怎么读分数（比怎么算更重要）

| 现象 | 可能原因 |
| --- | --- |
| Faithfulness 低 | 模型在编；上下文里有冲突信息；prompt 没要求"仅依据资料" |
| Answer Relevancy 低 | 答非所问；答案太长跑题；问题本身含糊 |
| Context Precision 低 | 检索排序差；块太大导致相关句被稀释 |
| Context Recall 低 | 分块切断了信息；top-k 太小；知识库确实缺 |

**关键**：指标是"诊断线索"，不是"考试分数"。看到低分要回到 badcase 看具体样本。

### 5. 评估的成本控制

- 用便宜模型当 judge（但要固定版本，否则不可比）
- 缓存 judge 结果（同一 question+context+answer 不重复评）
- 抽样评估（50 条里抽 20 条做全指标，其余只算检索指标）
- 只对"改动涉及的子集"跑回归

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 生成评估数据（60 min）

```python
def collect(service, cases: list[dict]) -> list[dict]:
    rows = []
    for c in cases:
        hits = service.retrieve(c["question"], k=5)
        ans = service.answer_with(c["question"], hits)
        rows.append({
            "question": c["question"],
            "answer": ans["answer"],
            "contexts": [h.text for h in hits],
            "ground_truth": c["reference_answer"],
            "gold_doc_ids": c["gold_doc_ids"],
        })
    return rows
```

**先落盘再评估**：`eval_runs/{run_id}/samples.jsonl`。这样评估失败不用重新生成（省钱）。

### 任务 2 · 跑 RAGAS（70 min）

```python
def run(samples_path: Path, out_dir: Path) -> dict:
    rows = [json.loads(l) for l in samples_path.read_text(encoding="utf-8").splitlines()]
    ds = Dataset.from_list([{k: r[k] for k in ("question", "answer", "contexts", "ground_truth")} for r in rows])
    result = evaluate(ds, metrics=METRICS, llm=judge_llm, embeddings=judge_emb, raise_exceptions=False)
    df = result.to_pandas()
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "ragas_scores.csv", index=False)
    return summarize(df)
```

`raise_exceptions=False` 很重要：单条失败不应让整批崩掉。

### 任务 3 · 定位 badcase（50 min）

按 Faithfulness 升序取 5 条，逐条看：
- 答案里哪句是编的？
- 上下文里有没有支持它的句子？
- 是检索没给到，还是模型没用？

把结论写进 `docs/week-07/eval-report.md` 的"Badcase 分析"一节。

### 任务 4 · 产出报告（30 min）

```markdown
# M2 评估报告 · 2026-12-22

- 评估集：50 条（35 正样本 / 15 负样本）
- 配置：chunk 500/80，top_k 5，rule rerank，temperature 0.2
- judge：deepseek-chat（固定版本）

| 指标 | 分数 |
| --- | --- |
| Faithfulness | 0.86 |
| Answer Relevancy | 0.81 |
| Context Precision | 0.74 |
| Context Recall | 0.79 |
| 拒答准确率 | 0.87 |
| P95 延迟 | 2.1s |
| 单次成本 | ¥0.0032 |

## 结论
1. ...
## Badcase
...
```

**这份报告是 M2 README 的核心素材**，也是简历上"量化评估"的直接证据。

---

## 代码思考（写进 `logs/day-32.md`）

1. Faithfulness 需要"把答案拆成论断"，拆分的粒度会怎样影响分数？
2. Context Recall 依赖 `ground_truth`，如果参考答案本身不完整，指标会怎样失真？
3. 同一份数据换 judge 模型，分数可能差 10 个点。那你如何做跨版本对比？
4. 评估花了 8 分钟、2 块钱，跑 50 条。如果每天要跑 10 次，你怎么降本？
5. 四个指标里，哪个最适合作为"上线门禁"？为什么？

## 复盘清单

- [ ] RAGAS 跑通，产出 CSV
- [ ] 有 5 条 badcase 的人工分析
- [ ] 报告含配置、指标、结论、局限
- [ ] commit：`day32: RAGAS 评估 + 首份量化报告`
