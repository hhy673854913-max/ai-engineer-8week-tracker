# Day 31 · 评估方法论与评估集构建

> W7 · 周一 ｜ 5h ｜ 产出 `code/week07/eval/eval_set.jsonl` + 评分细则 ｜ [Day 30](../week-06/day-30.md)

**今日目标**
- 建立"评估先于优化"的纪律：没有评估集的改进都是玄学
- 亲手构建 50 组 M2 评估集（含 15 组"应该拒答"的负样本）
- 设计一份可执行的评分细则，让不同人打出接近的分数

**验收**：`eval_set.jsonl` 50 条，字段完整；评分细则能让另一个人独立复现你的打分。

---

## 上午 09:00–11:30 · 理论

### 1. 为什么评估是分水岭

| 阶段 | 关注点 | 典型问题 |
| --- | --- | --- |
| Demo | 能跑 | "看起来还行" |
| 系统 | 可信 | "错误率多少？错在哪类？" |

企业敢把系统交给业务，前提是**能回答第二个问题**。所以评估能力直接决定你是"会调 API"还是"能交付"。

### 2. 评估的三个层次

| 层次 | 评什么 | 方法 | 成本 |
| --- | --- | --- | --- |
| 检索层 | 找到的块对不对 | hit-rate@k / MRR / Recall | 低（只需标注） |
| 生成层 | 答案对不对、有没有依据 | 人工 / LLM-as-judge / RAGAS | 中 |
| 端到端 | 用户任务完成没 | 任务成功率、人工评分 | 高 |

**顺序**：先检索层（便宜、可自动化）→ 再生成层 → 最后端到端。

### 3. 评估集怎么建（最容易被跳过的一步）

| 来源 | 数量 | 注意 |
| --- | --- | --- |
| 真实用户问题 | 20 | 最宝贵，句式和用词真实 |
| 业务 FAQ | 10 | 覆盖常见问题 |
| 边界/刁钻问题 | 10 | 多意图、含糊指代、错别字 |
| 应该拒答的问题 | 10–15 | 库里确实没有，考"不编造" |

每条样本的字段：

```json
{
  "id": "q01",
  "question": "春节活动奖励什么时候发",
  "type": "direct | colloquial | multi_hop | entity | negative",
  "gold_doc_ids": ["activity_2026_spring"],
  "gold_keywords": ["7 个工作日", "活动结束后"],
  "reference_answer": "活动结束后 7 个工作日内发放。",
  "should_refuse": false,
  "notes": "旧版本是 3 个工作日，注意别答错版本"
}
```

**`gold_keywords` 比 `reference_answer` 更实用**：判断"答案是否包含关键事实"比逐字比对更稳。

### 4. 人工评估的规范

三件事让打分可复现：
1. **维度分开**：正确性 / 完整性 / 引用有效性 / 简洁性，各 1–3 分
2. **判定规则**：什么算"正确"（关键事实全对且无错误信息）
3. **双人复核**：至少 20% 样本由第二个人独立打分，算一致性（Cohen's kappa）

评分卡示例：

| 维度 | 3 分 | 2 分 | 1 分 |
| --- | --- | --- | --- |
| 正确性 | 关键事实全对 | 主要事实对，有次要错误 | 关键事实错/编造 |
| 完整性 | 覆盖问题所有子项 | 覆盖主要子项 | 漏关键信息 |
| 引用 | 引用有效且对应 | 引用有效但不对应 | 引用错/无引用 |
| 简洁 | 无冗余 | 略有冗余 | 大量无关内容 |

### 5. LLM-as-judge 的边界

能用：批量粗筛、对比两版输出、回归测试。
不能全信：细微事实错误、领域黑话、需要外部知识的判断。

三个降低偏差的手段：
1. 给评分细则（和人工同一份）
2. 要求先写理由再打分（顺序影响结果）
3. 定期用人工标注集校准（算与人工的一致率）

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 建 50 条评估集（120 min）

```python
# code/week07/eval/build_eval_set.py
CASES = [
    {"id": "q01", "question": "春节活动奖励什么时候发", "type": "direct",
     "gold_doc_ids": ["activity_2026_spring"], "gold_keywords": ["7 个工作日"],
     "reference_answer": "活动结束后 7 个工作日内发放。", "should_refuse": False},
    # ... 49 条
]
```

要求：
- 至少 12 条 `negative`（应该拒答）
- 至少 8 条 `colloquial`（口语化）
- 至少 5 条 `multi_hop`（需要两块以上信息）
- 每条都有 `gold_doc_ids` 与 `gold_keywords`

### 任务 2 · 检索层评测脚本（50 min）

```python
def evaluate_retrieval(service, cases: list[dict], k: int = 5) -> dict:
    hits_ok = 0
    mrr_sum = 0.0
    detail = []
    for c in cases:
        if c["should_refuse"]:
            continue
        docs = service.retrieve(c["question"], k=k)
        ids = [d.id for d in docs]
        rank = next((i + 1 for i, d in enumerate(ids) if d in c["gold_doc_ids"]), None)
        hits_ok += 1 if rank else 0
        mrr_sum += 1.0 / rank if rank else 0.0
        detail.append({"id": c["id"], "rank": rank, "ids": ids[:k]})
    n = max(len(cases) - sum(1 for c in cases if c["should_refuse"]), 1)
    return {"hit_rate": hits_ok / n, "mrr": mrr_sum / n, "detail": detail}
```

### 任务 3 · 评分细则落地（40 min）

写 `docs/week-07/rubric.md`：四个维度、三档描述、判定示例（含一个"2 分"的边界案例）。
**边界案例最重要**——它决定了不同人打分的一致性。

### 任务 4 · 负样本检查（30 min）

跑 12 条 `should_refuse`，统计误答率（本该拒答却回答了）。
**这是最容易暴露幻觉的一组**，也是面试时最有说服力的数据。

---

## 代码思考（写进 `logs/day-31.md`）

1. 为什么 `gold_keywords` 比 `reference_answer` 更适合自动判断？
2. 负样本应该占多少比例？太少会怎样？
3. 人工评分时，"正确性"和"完整性"经常冲突（答对了但没答全），你怎么处理？
4. LLM-as-judge 与人工的一致率只有 65%，你还敢用它做回归测试吗？怎么改进？
5. 如果 hit-rate@5 是 0.82，但用户满意度很低，可能是什么原因？（提示：排序、答案组织）

## 复盘清单

- [ ] 50 条评估集，字段完整
- [ ] 检索层评测能跑，输出 hit-rate / MRR
- [ ] 评分细则有边界案例
- [ ] 负样本误答率有数字
- [ ] commit：`day31: 50 条评估集 + 检索评测 + 评分细则`
