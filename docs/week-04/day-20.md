# Day 20 · M2 开发（二）：引用溯源界面与演示

> W4 · 周五 ｜ 5h ｜ 产出 `code/week04/m2_kb/web/` ｜ [Day 19](day-19.md) ｜ **本周里程碑**

**今日目标**
- 用你最熟的前端能力做一个"能给人看"的问答界面，把引用做成可点击的高亮
- 接流式输出，体验到"首字 1 秒"的产品感
- 录一段 60 秒演示，写清 M2 的 README（这是简历上的第一个 RAG 作品）

**验收**：界面上提问 → 流式出字 → 点引用高亮原文片段 → 移动端也能用。

---

## 上午 09:00–11:30 · 设计

### 1. 界面要解决的三个问题

| 问题 | 设计动作 |
| --- | --- |
| 用户不知道答案可不可信 | 每个结论后带 `[1]` 角标，点击展开原文片段 |
| 用户不知道检索到了什么 | 侧栏显示 top-k 命中块与相似度（"检索透明"） |
| 用户不知道系统什么时候在思考 | 流式光标 + 首字延迟提示 + 检索阶段骨架屏 |

**不要做聊天框 + 气泡就完事**。RAG 产品的差异化在"可验证"：让用户能一眼看到答案从哪来。

### 2. 技术选型

| 方案 | 适合 | 说明 |
| --- | --- | --- |
| Streamlit | 2 小时出原型 | 适合内部演示，样式受限 |
| Vue / React | 你的主场 | 可控、可部署、可写进简历 |
| 纯 HTML + fetch | 最轻 | 够用，但状态管理麻烦 |

本文以 **Vue 3 + Vite** 为例（你也可以用 React，结构一样）：

```
m2_kb/web/
├─ index.html
├─ src/main.ts
├─ src/App.vue
├─ src/api.ts        # SSE 客户端
└─ src/components/Citation.vue
```

### 3. 流式接口的契约（先定，前后端各自开发）

```http
POST /api/query
Content-Type: application/json

{"question": "春节奖励什么时候发", "session_id": "abc"}

→ 200 text/event-stream
data: {"type":"hits","hits":[{"n":1,"score":0.82,"title":"2026春节活动规则","snippet":"..."}]}
data: {"type":"delta","text":"奖励将在"}
data: {"type":"delta","text":"活动结束后"}
data: {"type":"done","citations":[{"n":1,"doc_id":"activity_2026_spring"}]}
```

**先定契约再写代码**：前端可以用 mock 流先做 UI，后端按契约返回，联调成本最低。

### 4. 引用高亮怎么做

最简单的实现：

```vue
<template>
  <p class="answer" v-html="withCitations(answer)" />
</template>

<script setup>
function withCitations(text: string) {
  return text.replace(/\[(\d+)\]/g, (_, n) =>
    `<sup class="cite" data-n="${n}">[${n}]</sup>`
  )
}
</script>
```

点击 `.cite` 时，从 `hits[n-1]` 取原文片段，在侧栏高亮对应段落。

**注意 XSS**：`v-html` 前必须对模型输出做转义（只允许 `[n]` 替换，其余 HTML 转义）。
这是 AI 应用里真实存在的攻击面——模型输出可以被提示词注入操控。

### 5. 演示视频怎么录

60 秒脚本：
1. `0-10s`：一句话说清"这是什么、解决什么问题"
2. `10-35s`：提一个真实问题，展示流式 + 引用点击
3. `35-50s`：提一个"库里没有"的问题，展示拒答（证明不编造）
4. `50-60s`：一行架构图 + 指标（hit-rate / 延迟）

**拒答演示比答对演示更有说服力**——它证明你懂"可信"。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 后端接口（80 min）

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/api/query")
async def query(req: QueryReq):
    async def gen():
        hits = await asyncio.to_thread(service.retrieve, req.question)
        yield sse({"type": "hits", "hits": [h.to_dict() for h in hits]})
        async for piece in service.stream_answer(req.question, hits):
            yield sse({"type": "delta", "text": piece})
        yield sse({"type": "done", "citations": [c.to_dict() for c in service.citations]})
    return StreamingResponse(gen(), media_type="text/event-stream")
```

`asyncio.to_thread` 把同步检索丢到线程池，避免阻塞事件循环——这是 FastAPI 里最容易犯的错。

### 任务 2 · 前端（90 min）

```ts
export async function ask(question: string, onEvent: (e: any) => void) {
  const res = await fetch("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: getSessionId() }),
  })
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buf = ""
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const parts = buf.split("\n\n")
    buf = parts.pop() ?? ""
    for (const p of parts) {
      const line = p.split("\n").find((l) => l.startsWith("data:"))
      if (line) onEvent(JSON.parse(line.slice(5)))
    }
  }
}
```

**SSE 解析的三个坑**：跨 chunk 的半截消息（用 buffer）、`TextDecoder({stream:true})`、`\n\n` 分隔。

### 任务 3 · 联调与体验打磨（50 min）

- 首字延迟：显示"检索中…"骨架，检索完成立刻出现 hits
- 流式光标：末尾加 `▍` 闪烁
- 引用侧栏：hover 高亮、点击滚动到原文
- 错误态：网络断开显示"重试"按钮，别白屏

### 任务 4 · 录屏 + README（40 min）

M2 的 README 必须包含：一句话定位、架构图、技术选型理由、指标数据、快速启动、已知局限。
**这是你第一次把"作品"而不是"作业"放到 GitHub 上。**

---

## 代码思考（写进 `logs/day-20.md`）

1. 为什么 `asyncio.to_thread` 是必需的？直接调用同步检索会怎样（并发 10 个请求时）？
2. `v-html` 渲染模型输出有什么安全风险？除了转义还有哪些防御手段？
3. SSE 的 buffer 如果不在 `\n\n` 处切，会遇到什么诡异 bug？
4. 引用侧栏显示相似度分数，对用户有帮助还是干扰？什么用户会看它？
5. 如果演示视频只能保留一个镜头，你选"答对"还是"拒答"？为什么？

## 复盘清单（本周里程碑自检）

- [ ] 界面能流式输出、引用可点击
- [ ] 拒答场景正常
- [ ] 60 秒演示录好，README 写完
- [ ] 指标数据（hit-rate / P95 延迟 / 单次成本）写进 README
- [ ] commit：`M2: 引用溯源问答界面 + 演示`
- [ ] 周末：把 M2 的 README 发给自己，问"面试官会追问什么"
