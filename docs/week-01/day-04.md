# Day 04 · 流式输出与采样参数

> W1 · 周四 ｜ 5h ｜ 产出 `code/week01/day04_stream_chat.py` ｜ [Day 03](day-03.md) · [Day 05](day-05.md)

**今日目标**
- 理解 SSE 协议与 `stream=True` 的数据形态
- 讲清 `temperature / top_p / max_tokens / stop` 的实际影响，而不是背参数表
- 写出一个终端流式聊天程序，并量化 **TTFT（首字延迟）** 与 **tokens/s**

**验收**：终端里逐字输出，退出时打印本次 TTFT、总耗时、输出 token 数与速度。

---

## 上午 09:00–11:30 · 理论输入

### 1. 为什么流式是"体验"而不只是"性能"

| 模式 | 用户感知 | 总耗时 |
| --- | --- | --- |
| 阻塞 | 白屏 8 秒 → 整段答案 | 8 秒 |
| 流式 | 0.8 秒开始出字 | 8 秒 |

总耗时一样，但**感知等待**从 8 秒降到 0.8 秒。AI 产品的"快"几乎都由首字延迟决定。
所以面试问"流式怎么实现"时，好的回答会补一句：**TTFT 才是核心指标，不是总时长**。

对 Agent 工程师还有两个更硬的理由：一是长输出的总耗时经常超过网关/负载均衡 60s 的空闲超时，流式让连接一直有数据、不被掐断；二是"正在检索/正在调工具/正在重写"这些中间状态只能靠流式事件推给前端，否则用户看到的是几十秒无反馈的白屏。

### 2. SSE 长什么样

SSE（Server-Sent Events）是浏览器原生支持的服务端单向推送协议：一条 HTTP 长连接上服务端持续写 `data:` 行，客户端用 `EventSource` 或 `fetch` + `ReadableStream` 逐条读；它解决的是普通 HTTP「一问一答」里服务端没法边算边推的问题，单向推送用它就够，不必付 WebSocket 的双向与心跳成本。这半边你其实已经会——前端那侧的消费代码就是你现成的资产。

服务端返回 `Content-Type: text/event-stream`，每个事件是若干行 `data:`，空行分隔：

```
data: {"id":"...","choices":[{"delta":{"content":"RAG"}}]}

data: {"id":"...","choices":[{"delta":{"content":" 是"}}]}

data: [DONE]
```

用 `openai` SDK 时你看到的是已经解析好的 chunk：

```python
for chunk in stream:
    delta = chunk.choices[0].delta
    if delta.content:
        print(delta.content, end="", flush=True)
```

三个细节：
- `delta.content` 可能为 `None`（比如工具调用块、角色块），必须判空
- 最后一个 chunk 可能带 `finish_reason`，但不一定带内容
- 网络中断时迭代会抛异常，要能优雅收尾（保留已输出内容 + 提示重试）

### 3. 采样参数：只讲会影响你决策的部分

| 参数 | 范围 | 作用 | 什么时候动 |
| --- | --- | --- | --- |
| `temperature` | 0–2 | 随机性。0 附近更确定 | 抽取/分类用 0–0.3；创意文案 0.7–1.0 |
| `top_p` | 0–1 | 核采样，截断长尾 | 一般不动；要更保守就调小 |
| `max_tokens` | — | 输出上限 | 必须设！防止跑飞烧钱 |
| `stop` | 字符串/数组 | 遇到即停 | 结构化输出收尾、防止模型自问自答 |
| `presence_penalty` | -2–2 | 惩罚已出现词，鼓励新话题 | 长文避免重复 |
| `frequency_penalty` | -2–2 | 按出现次数惩罚 | 同上，更强烈 |
| `seed` | 整数 | 尽力可复现 | 评估集回归时用（不保证跨模型稳定） |

**经验法则**：`temperature` 和 `top_p` 不要同时调，改一个就够。做抽取/结构化输出时，`temperature=0` + `max_tokens` 收紧 + `stop` 兜底。

### 4. 流式和结构化输出是天然冲突的

这一点很多人踩坑：`response_format={"type": "json_object"}` 在流式下会返回**半截 JSON**，前端拿到无法解析。
解决思路（Day 05 展开）：
- 要么先流式给"人看的文本"，再单独调一次结构化
- 要么边收边缓冲，用增量 JSON 解析器
- 要么用 JSON Lines / 特殊分隔符，让每一行都是独立可解析单元

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 最小流式（30 min）

```python
stream = client.chat.completions.create(
    model=cfg.model,
    messages=messages,
    stream=True,
    temperature=0.7,
    max_tokens=800,
)
for chunk in stream:
    piece = chunk.choices[0].delta.content or ""
    if piece:
        print(piece, end="", flush=True)
```

`flush=True` 必须加，否则 Python 的输出缓冲会让"流式"变成"最后一次性出现"。

### 任务 2 · 终端聊天程序（60 min）

要求：
- 多轮：维护 `messages` 列表，每轮把 assistant 回复追加进去
- 命令：`/exit` 退出、`/clear` 清空上下文、`/temp 0.2` 调温度
- 统计：每轮打印 `TTFT / 总耗时 / completion_tokens / tokens/s`
- 中断：`Ctrl+C` 不崩，保留已输出内容

```python
import time

t0 = time.perf_counter()
first = None
n_chars = 0
for chunk in stream:
    piece = chunk.choices[0].delta.content or ""
    if not piece:
        continue
    if first is None:
        first = time.perf_counter() - t0
    n_chars += len(piece)
    print(piece, end="", flush=True)
total = time.perf_counter() - t0
print(f"\n\n[TTFT {first:.2f}s | 总 {total:.2f}s | {n_chars} 字 | {n_chars/total:.1f} 字/s]")
```

注意：这里用**字符数**代替 token 数做粗估，精确值要看最后一个 chunk 的 `usage`（部分厂商流式默认不返回 usage，需要显式开启）。

### 任务 3 · 对比实验：阻塞 vs 流式（20 min）

同一句 prompt 各跑一次，记录用户"看到第一个字"的时间。把两组数字写进 `logs/day-04.md`——
这就是你面试讲"为什么做流式"时的一手数据。

### 任务 4 · 参数实验（30 min）

固定 prompt，跑四组：`temperature=0` / `0.7` / `1.2` / `1.8`，各 3 次，观察输出差异。
结论写成一句话，比如："0 时三次输出几乎一致；1.8 时开始出现事实漂移与重复。"

---

## 代码思考（写进 `logs/day-04.md`）

1. 为什么 `flush=True` 决定流式是"真流式"还是"假流式"？Windows 终端还有哪些坑（`chcp 65001`）？
2. 流式输出到一半网络断了，前端应该显示什么？后端应该记录什么？重试时如何避免重复输出？
3. `max_tokens` 设太小会怎样？为什么它和"截断的 JSON"是同一个问题的两面？
4. 如果要给流式输出加"打字机 + 逐句高亮"，前端需要在哪个边界做缓冲？为什么不能在服务端切句？
5. 为什么 `temperature=0` 也不保证完全可复现？（并行计算、浮点非确定性、模型更新）

## 复盘清单

- [ ] 能画出 SSE 报文形态并解释 `[DONE]`
- [ ] 能说出 TTFT 与总耗时的区别，以及为什么前者更重要
- [ ] 参数表能讲出"什么时候动、动哪个"
- [ ] commit：`day04: 流式聊天 + TTFT 统计`
