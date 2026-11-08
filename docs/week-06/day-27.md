# Day 27 · 开发第一个 MCP Server：把 M1 简报封装成工具

> W6 · 周二 ｜ 5h ｜ 产出 `code/week06/mcp_server_news.py` ｜ [Day 26](day-26.md) · [Day 28](day-28.md)

**今日目标**
- 把 M1 的资讯能力封装成 MCP 工具，让任意 MCP 客户端都能用
- 处理参数校验、错误返回、超时、日志（stdio 模式下日志不能写 stdout！）
- 设计"工具粒度"：一个万能工具还是多个小工具？

**验收**：Inspector 中调用 `query_news(keyword, limit)` 返回结构化结果；错误参数返回清晰的错误消息。

---

## 上午 09:00–11:30 · 工程细节

### 1. 工具粒度：这是设计问题，不是实现问题

| 设计 | 例子 | 优点 | 缺点 |
| --- | --- | --- | --- |
| 万能工具 | `execute(action, params)` | 工具数量少 | 模型难用，参数复杂 |
| 单一职责 | `query_news` / `get_news_detail` / `list_sources` | 模型容易选对 | 工具数量多，占上下文 |
| 按场景组合 | `daily_brief(date)` | 贴近用户意图 | 灵活性差 |

**建议**：3–7 个工具，每个做一件事，描述写清"什么时候用"。
工具超过 20 个时，考虑加"工具分组"或"按需发现"。

### 2. stdio 模式的头号坑：日志

MCP 走 stdio 时，**stdout 是协议通道**。你 `print()` 一行，客户端就解析失败。

```python
import logging, sys

logging.basicConfig(
    stream=sys.stderr,          # 必须 stderr
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger("mcp.news")
```

这条规则同样适用于任何"被当作子进程启动"的程序。踩过这个坑的人面试时会心一笑。

### 3. 参数校验与错误返回

FastMCP 会用类型注解 + Pydantic 做基础校验。但业务校验要自己写：

```python
@mcp.tool()
def query_news(keyword: str, limit: int = 5, days: int = 7) -> list[dict]:
    """按关键词查询最近资讯。

    Args:
        keyword: 关键词，2-20 字
        limit: 返回条数，1-20
        days: 最近几天，1-30

    返回字段：title / summary / source / url / published_at / credibility
    """
    if not 2 <= len(keyword) <= 20:
        raise ValueError("keyword 长度需在 2-20 字之间")
    if not 1 <= limit <= 20:
        raise ValueError("limit 需在 1-20 之间")
    ...
```

**错误要"可行动"**：`"limit 需在 1-20 之间"` 比 `"invalid parameter"` 有用得多。
FastMCP 会把异常转成 `isError: true` 的结果，模型能读到消息并自行修正。

### 4. 超时与外部依赖

MCP 工具调用没有内置超时（取决于客户端）。所以工具内部要自己控制：

```python
async def fetch_with_timeout(url: str, timeout: float = 10.0) -> str:
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.text
```

**永远不要让工具无限等待**：客户端可能等 30 秒然后认为 Server 挂了。

### 5. 无状态 vs 有状态

MCP Server 可以是长驻进程（有状态），但**工具应尽量无状态**：
- 缓存放进程内（dict + TTL）可以，但重启就丢
- 不要在工具间传递隐式状态（"先调 A 再调 B"），模型不保证顺序

如果确实需要状态，用显式参数（`session_id`）或外部存储。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 封装 query_news（80 min）

```python
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

mcp = FastMCP("news-brief")

class NewsItem(BaseModel):
    title: str
    summary: str
    source: str
    url: str
    published_at: str | None = None
    credibility: int = 0

@mcp.tool()
async def query_news(keyword: str, limit: int = 5, days: int = 7) -> list[dict]:
    """按关键词查询最近资讯（来自本地缓存的 M1 简报数据）。"""
    items = load_brief_cache()                    # 读 M1 产出的 output/brief_*.json
    hits = [i for i in items if keyword in (i["title"] + i["summary"])]
    hits = [i for i in hits if within_days(i, days)]
    hits.sort(key=lambda i: (i["credibility"], i.get("published_at") or ""), reverse=True)
    return [NewsItem(**i).model_dump() for i in hits[:limit]]

@mcp.tool()
def list_sources() -> list[str]:
    """列出当前简报数据覆盖的信源。"""
    return load_sources()

@mcp.tool()
def get_brief(date: str | None = None) -> str:
    """获取某天的完整简报（Markdown）。date 格式 YYYY-MM-DD，默认今天。"""
    ...
```

### 任务 2 · 资源与提示（40 min）

```python
@mcp.resource("brief://daily/{date}")
def daily_brief(date: str) -> str:
    """按日期读取简报全文（只读资源）。"""
    return read_brief_file(date)

@mcp.prompt()
def news_digest(topic: str) -> str:
    """生成"围绕某主题做 3 条摘要"的提示。"""
    return f"请从简报中挑出与「{topic}」相关的 3 条，每条 50 字以内，并标注来源。"
```

### 任务 3 · 调试与测试（50 min）

三件事：
1. Inspector 里逐个调用，看返回结构
2. 故意传错参数（`limit=999`），确认错误消息清晰
3. 用 Day 26 的客户端脚本调用，确认非 Inspector 环境也正常

### 任务 4 · 接进自己的 Agent（40 min）

把 MCP Server 的工具列表转成 Function Calling schema，接进 Day 24 的 LangGraph Agent：

```python
async def load_mcp_tools(session) -> list[dict]:
    tools = await session.list_tools()
    return [{"type": "function", "function": {
        "name": t.name, "description": t.description or "", "parameters": t.inputSchema}} for t in tools.tools]
```

跑通"问一句资讯 → Agent 调 MCP 工具 → 回答"，这就是 M3 的雏形。

---

## 代码思考（写进 `logs/day-27.md`）

1. stdio 模式下 `print()` 会怎样？为什么日志必须写 stderr？还有哪些输出会污染协议通道？
2. 工具抛 `ValueError` 与返回 `{"error": ...}`，对模型的行为有什么不同影响？
3. 工具设计成 3 个小工具还是 1 个万能工具，取决于什么？
4. `query_news` 依赖 M1 的缓存文件，如果缓存不存在应该返回什么？（提示：空数组 vs 报错）
5. 工具执行 10 秒还没返回，客户端会怎样？你会在工具内部加超时还是交给客户端？

## 复盘清单

- [ ] `query_news` / `list_sources` / `get_brief` 三个工具可用
- [ ] 资源与提示模板各一个
- [ ] 错误参数返回可行动的消息
- [ ] 接进自己的 Agent 跑通一次
- [ ] commit：`day27: MCP Server（资讯三工具 + 资源 + 提示）`
