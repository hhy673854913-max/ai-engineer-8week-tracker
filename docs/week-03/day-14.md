# Day 14 · 完整 RAG 链路与引用溯源

> W3 · 周四 ｜ 5h ｜ 产出 `code/week03/mini_rag/rag.py` ｜ [Day 13](day-13.md) · [Day 15](day-15.md)

**今日目标**
- 把"检索 + 生成"串成完整链路，并加上**引用溯源**
- 学会用"阈值 + 拒答"控制幻觉，而不是祈祷模型不乱说
- 写出第一版可复用的 RAG 类，为 M2 打底

**验收**：提问后输出「答案 + 引用片段（来源文件 / 段落位置）」，检索不到时明确拒答。

---

## 上午 09:00–11:30 · 理论输入

### 1. RAG 完整链路（七步）

```mermaid
flowchart LR
    Q[问题] --> RW[查询改写]
    RW --> E[查询嵌入]
    E --> R[向量检索 top-k]
    R --> F[阈值过滤]
    F --> M[相邻块合并/去重]
    M --> C[上下文组装<br/>编号 + 元数据]
    C --> G[LLM 生成<br/>要求引用]
    G --> P[解析引用 + 校验]
    P --> A[答案 + 出处]
```

大多数教程只讲"检索 + 拼 prompt + 生成"，但真正决定体验的是 **RW（改写）、F（阈值）、M（合并）、P（引用校验）** 这四步。

### 2. 上下文组装：不是简单拼接

```text
【资料 1｜来源：kb/activity/spring.md § 奖励发放】
奖励将在活动结束后 7 个工作日内发放……

【资料 2｜来源：kb/faq/pay.md § 退款】
退款一般 1-3 个工作日到账……

请仅依据以上资料回答。每个结论后用 [1] [2] 标注来源。
资料不足时，回答"当前知识库没有相关信息"，并说明缺什么。
```

四个要点：
1. **编号**：让模型能引用，也让你能反查
2. **带来源与 section**：模型更容易判断"这段是否回答问题"
3. **总量控制**：top-k × 块长 ≤ 模型上下文的安全水位（留出输出空间）
4. **去重与合并**：相邻块（同 doc 且 index 连续）合并，否则同一段话重复占 token

### 3. 阈值与拒答

```python
hits = [h for h in hits if h.score >= 0.65]   # 阈值要实测，不同模型差别大
if not hits:
    return "当前知识库没有找到相关内容。"
```

没有阈值的 RAG 会**永远给出答案**，哪怕检索到的全是垃圾——这是幻觉最大的来源。
阈值怎么定：拿 50 个"库里有答案"的问题 + 20 个"库里没有"的问题，画出相似度分布，
取两峰之间的谷底。

### 4. 引用溯源的两个层次

| 层次 | 做法 | 可信度 |
| --- | --- | --- |
| 弱引用 | 让模型自己写 `[1]`，不校验 | 低（会编造编号） |
| 强引用 | 生成后正则提取 `[n]`，校验 n 是否在上下文范围内，再把 n 映射回原文片段 | 高 |
| 精确引用 | 要求模型输出"原文摘录"，程序做子串匹配 | 最高，但对模型要求高 |

**工程建议**：至少做到强引用，M2 演示时才敢说"每个结论都可点回原文"。

### 5. 失败模式清单

| 现象 | 根因 | 对策 |
| --- | --- | --- |
| 答得对但没引用 | 模型偷懒 | few-shot 示例里带上引用格式 |
| 引用编号错位 | 上下文编号与模型理解不一致 | 用 `[资料 1]` 而不是 `[1]`；或要求引用原文 |
| 答非所问 | 检索错 | 阈值 + 重排 + 查询改写 |
| 编造细节 | 上下文没有但模型补全 | 明确"资料未提及则写未提及" |
| 多块冲突 | 知识库有过期文档 | 元数据 `updated_at` 加权 + 冲突时提示 |

---

## 下午 14:00–16:30 · 实战

### 任务 1 · RAG 类（90 min）

```python
@dataclass
class Hit:
    chunk: Chunk
    score: float

class MiniRAG:
    def __init__(self, store, embed_fn, chat_fn, top_k: int = 5, min_score: float = 0.62):
        ...

    def retrieve(self, question: str) -> list[Hit]:
        qv = self.embed_fn([question])[0]
        return [Hit(c, s) for c, s in self.store.query(qv, k=self.top_k) if s >= self.min_score]

    def build_context(self, hits: list[Hit]) -> str:
        blocks = []
        for i, h in enumerate(hits, 1):
            meta = h.chunk.metadata
            blocks.append(f"【资料 {i}｜来源：{meta.get('source','')} § {meta.get('section','')}】\n{h.chunk.text}")
        return "\n\n".join(blocks)

    def answer(self, question: str) -> dict:
        hits = self.retrieve(question)
        if not hits:
            return {"answer": "当前知识库没有找到相关内容。", "citations": []}
        raw = self.chat_fn(PROMPT.format(context=self.build_context(hits), question=question))
        return {"answer": raw, "citations": self.parse_citations(raw, hits)}
```

### 任务 2 · 引用解析与校验（40 min）

```python
CITE = re.compile(r"\[资料\s*(\d+)\]|\[(\d+)\]")

def parse_citations(self, text: str, hits: list[Hit]) -> list[dict]:
    seen, out = set(), []
    for m in CITE.finditer(text):
        n = int(m.group(1) or m.group(2))
        if 1 <= n <= len(hits) and n not in seen:
            seen.add(n)
            h = hits[n - 1]
            out.append({"n": n, "source": h.chunk.metadata.get("source"), "text": h.chunk.text[:120], "score": h.score})
    return out
```

**校验的价值**：模型写出 `[9]` 但只有 5 条资料时，你能立刻发现并降级（比如去掉不存在的引用并标注"引用异常"）。

### 任务 3 · 阈值标定实验（40 min）

准备 20 个"有答案"问题 + 10 个"无答案"问题，跑检索，记录两组 top-1 相似度分布。
选一个阈值，使得：无答案组误召回 ≤ 2/10，有答案组召回 ≥ 16/20。把分布图画进 `logs/day-14.md`。

### 任务 4 · 20 组人工评测（30 min）

对 20 个真实问题，逐条记录：检索是否正确、答案是否正确、引用是否有效、耗时。
这张表就是 Day 31 评估集的种子数据。

---

## 代码思考（写进 `logs/day-14.md`）

1. 为什么"没有阈值的 RAG 一定会有幻觉"？从生成机制解释。
2. 相邻块合并有什么副作用？合并后超过上下文预算怎么办？
3. 用 `[资料 1]` 替代 `[1]` 为什么能降低引用错位？还有哪些编号方案？
4. 如果知识库里有两条互相矛盾的规则（新旧版本），RAG 应该怎么处理？在产品上怎么提示用户？
5. 23 个问题里 6 个答错，其中 4 个是检索没召回——你会先改分块还是先加重排？依据是什么？

## 复盘清单

- [ ] `MiniRAG` 可复用，接口清晰（retrieve / build_context / answer）
- [ ] 引用能解析、能校验、能反查原文
- [ ] 阈值有标定数据支撑
- [ ] 20 组评测表已落盘
- [ ] commit：`day14: 完整 RAG + 引用溯源 + 阈值标定`
