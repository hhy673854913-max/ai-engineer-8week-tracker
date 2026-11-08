# Day 28 · MCP 进阶：资源、提示模板与调试体系

> W6 · 周三 ｜ 5h ｜ 产出 `code/week06/mcp_server_kb.py` ｜ [Day 27](day-27.md) · [Day 29](day-29.md)

**今日目标**
- 把"领域知识库检索"封装成 MCP 工具，让任意客户端复用 M2 的能力
- 掌握 Resources 的正确用法（只读数据 + URI 设计）
- 建立 MCP 的调试体系：日志分级、Inspector、错误复现

**验收**：`mcp_server_kb.py` 暴露 `search_kb` / `get_doc` 两个工具和 `kb://doc/{id}` 资源，Inspector 全部可用。

---

## 上午 09:00–11:30 · 进阶要点

### 1. Resource 的 URI 设计

Resource 用 URI 标识，客户端可以"列出来再读"：

```text
kb://docs                     → 列出所有文档
kb://doc/{doc_id}             → 读取单篇
kb://doc/{doc_id}/chunk/{n}   → 读取某一块
brief://daily/2026-11-20      → 某日简报
```

URI 设计三条：
1. **层级清晰**：`scheme://collection/item/sub`
2. **不要放敏感信息**：URI 会被记录在日志和客户端历史里
3. **稳定**：URI 变了，客户端的书签就失效了

```python
@mcp.resource("kb://doc/{doc_id}")
def get_doc(doc_id: str) -> str:
    """按 id 读取知识库文档全文（Markdown）。"""
    doc = load_doc(doc_id)
    if not doc:
        raise ValueError(f"文档不存在: {doc_id}")
    return doc.content
```

### 2. Tool 与 Resource 的分工

| 场景 | 用哪个 | 理由 |
| --- | --- | --- |
| 模型需要"查一下" | Tool | 模型主动发起，可带参数 |
| 应用要"把上下文塞给模型" | Resource | 应用控制，不进模型决策 |
| 用户点"/摘要" | Prompt | 用户显式选择 |
| 大段只读文档 | Resource | 避免模型反复调工具 |

**一个常见错误**：把大文档做成 Tool 返回。正确做法是 Resource 提供 URI，模型按需读取其中片段。

### 3. 错误处理的分层

| 层 | 错误 | 处理 |
| --- | --- | --- |
| 协议层 | 方法不存在、参数格式错 | 返回 JSON-RPC error |
| 参数层 | 业务校验失败 | 抛 `ValueError`，转成 `isError: true` |
| 依赖层 | 数据库连不上、API 超时 | 捕获后返回可读消息 + `retryable` 提示 |
| 内部层 | 代码 bug | 记录完整堆栈到 stderr，返回通用消息（不泄露内部细节） |

**不要把所有异常都 `except Exception: return "出错了"`**，那样模型无法自救。

### 4. 调试体系

三件套：

```python
# 1) 分级日志（stderr）
log.debug("tool=%s args=%s", name, args)
log.info("tool=%s elapsed=%.0fms ok=%s", name, ms, ok)

# 2) Inspector：交互式调用
#    uv run mcp dev code/week06/mcp_server_kb.py

# 3) 回放：把一次调用的 args/result 存成 json，离线复现
```

**MCP 的调试难点在于"客户端看不见服务端内部"**，所以日志 + 回放是唯一可靠手段。

### 5. 性能与并发

- 工具是 `async def` 时，FastMCP 会并发处理多个调用（同一连接内仍可能串行，取决于客户端）
- 重活（embedding、检索）用 `asyncio.to_thread` 避免阻塞
- 高频工具加进程内缓存（TTL 60s）

```python
@lru_cache(maxsize=256)
def load_doc_cached(doc_id: str) -> str: ...
```

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 知识库 MCP Server（100 min）

```python
mcp = FastMCP("kb")

@mcp.tool()
async def search_kb(query: str, top_k: int = 5) -> list[dict]:
    """在领域知识库中语义检索，返回最相关的片段。

    Args:
        query: 自然语言问题或关键词
        top_k: 返回条数，1-10

    返回：id / title / score / snippet / source
    """
    if not query.strip():
        raise ValueError("query 不能为空")
    hits = await asyncio.to_thread(kb.search, query, min(max(top_k, 1), 10))
    return [{"id": h.id, "title": h.title, "score": round(h.score, 3),
             "snippet": h.text[:200], "source": h.source} for h in hits]

@mcp.tool()
async def get_doc(doc_id: str) -> dict:
    """按 id 读取知识库文档全文。"""
    ...

@mcp.resource("kb://doc/{doc_id}")
def doc_resource(doc_id: str) -> str:
    ...
```

复用 M2 的 `QAService`，**不要重写检索逻辑**——这是"能力复用"的体现。

### 任务 2 · 把两个 Server 一起接进 Agent（50 min）

M3 需要同时用"资讯"和"知识库"两个 Server：

```python
async def connect_all(servers: dict[str, StdioServerParameters]):
    async with AsyncExitStack() as stack:
        sessions = {}
        for name, params in servers.items():
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            sessions[name] = session
        yield sessions
```

注意**工具名冲突**：两个 Server 都叫 `search` 时，要加前缀（`news_search` / `kb_search`）。

### 任务 3 · 故障演练（30 min）

- Server 启动失败（路径错）：客户端报什么？你怎么定位？
- 工具抛异常：客户端收到什么结构？模型能看到消息吗？
- Server 卡住 30 秒：客户端超时行为？

把三种情况的日志贴进 `logs/day-28.md`。

### 任务 4 · 写 MCP README（20 min）

包含：能力列表、启动命令、配置示例（Claude Desktop / Cursor）、已知限制。
**这个 README 会直接被面试官看到，按"给别人用"的标准写。**

---

## 代码思考（写进 `logs/day-28.md`）

1. 为什么大文档更适合做成 Resource 而不是 Tool 的返回值？
2. 工具名冲突时，加前缀和加命名空间（`news.search`）哪个更好？
3. 内部异常要不要把堆栈返回给客户端？泄露堆栈有什么风险？
4. 多 Server 同时连接时，某个 Server 挂掉会影响其他 Server 吗？为什么？
5. 如果要把 M2 的知识库开放给公司其他团队，MCP 与 REST API 各适合什么场景？

## 复盘清单

- [ ] 知识库 MCP Server 可用（工具 + 资源）
- [ ] 两个 Server 同时接进 Agent，无命名冲突
- [ ] 三种故障场景有日志记录
- [ ] MCP README 写完
- [ ] commit：`day28: 知识库 MCP Server + 多 Server 接入`
