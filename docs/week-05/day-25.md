# Day 25 · 记忆系统：短期上下文与长期偏好

> W5 · 周五 ｜ 5h ｜ 产出 `code/week05/memory.py` ｜ [Day 24](day-24.md) ｜ **本周里程碑**

**今日目标**
- 分清短期记忆（对话上下文）与长期记忆（跨会话事实/偏好）的工程差异
- 实现"滑动窗口 + 摘要 + 向量召回"三层记忆
- 给 Agent 加上"跨会话记住用户偏好"的能力，并处理隐私与遗忘

**验收**：`python -m week05.memory` 演示：第一次会话说"我偏好简短回答"，新会话中 Agent 自动遵守。

---

## 上午 09:00–11:30 · 理论

### 1. 三种记忆

| 类型 | 内容 | 存储 | 生命周期 |
| --- | --- | --- | --- |
| 短期（工作记忆） | 最近 N 轮对话 | 内存 / Redis | 会话内 |
| 长期-语义 | 用户偏好、事实（"我是运营"、"讨厌长回复"） | 向量库 / KV | 跨会话 |
| 长期-情节 | 历史事件（"上周问过退款"） | 带时间的向量库 | 跨会话，可衰减 |

大多数产品只做前两层。第三层（情节记忆）是 Agent 产品化的分水岭，但成本和隐私问题也最大。

### 2. 短期记忆的三种压缩策略

| 策略 | 做法 | 优点 | 缺点 |
| --- | --- | --- | --- |
| 滑窗 | 只保留最近 K 轮 | 简单、可预测 | 丢失早期关键信息 |
| 摘要 | 把早期对话压成一段 | 省 token、保留要点 | 摘要本身可能丢细节/失真 |
| 混合 | 最近 K 轮原文 + 更早的摘要 | 平衡 | 实现复杂 |

```python
def build_messages(history: list[dict], recent: int = 8, summary: str | None = None) -> list[dict]:
    msgs = []
    if summary:
        msgs.append({"role": "system", "content": f"早前对话摘要：{summary}"})
    msgs.extend(history[-recent:])
    return msgs
```

**触发摘要的时机**：token 超过预算的 60%，而不是固定轮数——按 token 算更准。

### 3. 长期记忆的写入与召回

写入不是"每句话都存"，要有取舍：

```python
class MemoryItem(BaseModel):
    id: str
    user_id: str
    kind: Literal["preference", "fact", "event"]
    content: str            # "用户偏好回答简短，不超过 3 句"
    confidence: float       # 抽取置信度
    created_at: datetime
    last_used_at: datetime | None
    source_turn: int
```

召回：用当前问题做 embedding，检索该用户的记忆，top-3 拼进 system。

**关键设计：记忆要"带置信度 + 可失效"**。
模型从一句话里推断出"用户讨厌长回复"，这是推断不是事实；置信度低时不该长期保留。

### 4. 记忆的三个陷阱

| 陷阱 | 表现 | 对策 |
| --- | --- | --- |
| 记忆污染 | 把模型的猜测当成用户事实 | 只存用户明确说过的；抽取时要求引用原句 |
| 无限增长 | 记忆库越来越大，召回噪声变多 | 容量上限 + LRU 淘汰 + 定期合并 |
| 隐私越界 | 跨用户串数据 / 存了不该存的 | 按 `user_id` 强隔离；敏感字段白名单；提供"清除我的记忆" |

**"清除我的记忆"不是可选项**，是合规要求（个人信息保护法）。设计时就要有 `delete_by_user`。

### 5. 记忆 vs RAG：别混为一谈

| | RAG | 长期记忆 |
| --- | --- | --- |
| 数据来源 | 公共知识库 | 该用户的历史交互 |
| 更新频率 | 低（文档变更时） | 高（每次对话可能更新） |
| 检索范围 | 全库 | 当前用户 |
| 失败后果 | 答错 | 答错 + 隐私事故 |

**一个系统里两者可以共存**，但索引、权限、生命周期必须分开管理。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 短期记忆（50 min）

实现 `ConversationBuffer`：
- `add(role, content)`
- `to_messages(max_tokens)`：超预算时先摘要再裁剪
- 摘要用 LLM（廉价模型即可），并保留"最近 2 轮原文"

### 任务 2 · 长期记忆（80 min）

```python
class LongTermMemory:
    def __init__(self, store, embed_fn, user_id: str): ...

    def extract(self, user_text: str) -> list[MemoryItem]:
        """用 LLM 抽取偏好/事实，要求引用原句，低置信度丢弃。"""

    def save(self, items: list[MemoryItem]) -> None: ...
    def recall(self, query: str, k: int = 3) -> list[MemoryItem]: ...
    def forget(self, memory_id: str) -> None: ...
    def forget_user(self) -> int: ...
```

抽取 prompt 要点：

```text
从用户这句话里抽取"值得长期记住"的信息，只包括：
- 明确的偏好（"我喜欢简短回答"）
- 稳定的事实（"我是做游戏运营的"）
不要抽：临时状态（"我现在很忙"）、模型推测。
每条必须给出原文引用 quote。没有就返回空数组。
输出 JSON：{"items": [{"kind": "preference|fact", "content": "...", "quote": "...", "confidence": 0.0-1.0}]}
```

### 任务 3 · 组装（40 min）

```python
def build_system_prompt(user_id: str, question: str) -> str:
    mems = memory.recall(question, k=3)
    mem_block = "\n".join(f"- {m.content}" for m in mems) or "（无）"
    return BASE_SYSTEM + f"\n\n已知用户信息：\n{mem_block}"
```

演示：会话 1 说"回答尽量简短"，会话 2 问技术问题，观察是否遵守。
**如果没遵守，先查抽取是否成功，再查召回是否命中，最后才怀疑 prompt。**

### 任务 4 · 遗忘与隐私（30 min）

实现 `forget_user()`，并跑一次"清除后不再被召回"的验证。写进 `logs/day-25.md`：
如果用户要求删除全部记忆，你的系统需要删哪些地方？（向量库 / 缓存 / 日志 / 备份）

---

## 代码思考（写进 `logs/day-25.md`）

1. 为什么记忆要带 `confidence`？置信度 0.4 的记忆该存还是该丢？
2. 摘要式压缩会失真，怎么检测"摘要丢了关键信息"？
3. 记忆召回用 `question` 做 query，如果用户这次问的是完全无关的话题，会召回噪声吗？怎么缓解？
4. `delete_by_user` 要覆盖哪些存储？漏掉日志会有什么后果？
5. 如果两个用户共享一个设备（比如公司平板），记忆隔离怎么做？

## 复盘清单（本周里程碑自检）

- [ ] 短期记忆有摘要 + 滑窗
- [ ] 长期记忆能抽取、召回、遗忘
- [ ] 跨会话演示成功
- [ ] 有 `forget_user` 且验证过
- [ ] commit：`day25: 三层记忆系统 + 跨会话偏好`
