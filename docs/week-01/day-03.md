# Day 03 · 第一个大模型 API 调用

> W1 · 周三 ｜ 5h ｜ 产出 `code/shared/llm_client.py` ｜ [Day 02](day-02.md) · [Day 04](day-04.md)

**今日目标**
- 讲清 Chat Completions 的 `messages` 结构与 token 计费方式
- 理解"OpenAI 兼容层"为什么能让你随时换供应商
- 写出第一版生产级封装：超时、重试、限流、日志、成本统计

**验收**：`python -m shared.llm_client "用一句话解释 RAG"` 能返回答案，并在日志里打印 token 与预估成本。

---

## 上午 09:00–11:30 · 理论输入

### 1. 一次调用到底发生了什么

```
你的 messages 数组 → 服务端拼成一段特殊格式的 token 序列 → 模型逐 token 预测
                   ← 返回 choices[0].message.content + usage(prompt_tokens, completion_tokens)
```

`messages` 是**有角色的对话数组**，不是一段字符串：

```python
messages = [
    {"role": "system", "content": "你是严谨的中文技术编辑，只回答事实。"},
    {"role": "user", "content": "RAG 是什么？"},
    {"role": "assistant", "content": "RAG 指检索增强生成……"},   # 历史回复
    {"role": "user", "content": "那它和微调的区别？"},             # 本轮问题
]
```

三个必须记住的点：

1. **模型无状态**。服务端不记得上一轮，所谓"多轮对话"是你每次把历史全量回传。所以上下文越长越贵、越慢。
2. **system 是最高优先级的约束**，但它是"软约束"，不是安全边界（提示词注入在 Day 06 讲）。
3. **计费按 token**，输入 + 输出分别计价，中文大约 1 个汉字 ≈ 0.6–1 token（不同分词器有差异，别手算，看 `usage`）。

### 2. OpenAI 兼容层：一次封装，随时换厂商

DeepSeek、通义千问、智谱、月之暗面、以及各类中转网关，都实现了 `/v1/chat/completions` 协议。
所以只需换三样东西：`base_url`、`api_key`、`model`。

| 供应商 | base_url | 常用模型 |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` / `deepseek-reasoner` |
| 阿里百炼 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` / `qwen-vl-max` |
| 智谱 | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-air` |

> 模型名与价格会变，**以各家控制台为准**；代码里不要把模型名写死到业务逻辑中。

这就是为什么 `.env` 里只放 `LLM_PROVIDER`，由工厂函数决定实际配置——**你的资产是封装，不是某家 API**。

### 3. 错误模型：哪些能重试，哪些不能

| 状态 | 含义 | 能重试？ | 处理 |
| --- | --- | --- | --- |
| 401 / 403 | Key 错误 / 无权限 | 否 | 立刻失败并提示检查 `.env` |
| 400 | 参数或上下文超长 | 否 | 修参数，通常是 messages 太长 |
| 429 | 限流 / 配额 | 是 | 指数退避 + 抖动 |
| 500 / 502 / 503 | 服务端抖动 | 是 | 退避重试，最多 3–5 次 |
| 超时 / 连接重置 | 网络 | 是 | 重试，但要防重复计费 |
| 内容审查拒绝 | 安全策略 | 否 | 换措辞或降级 |

**关键工程判断**：重试必须有上限 + 退避 + 抖动，否则限流时会把服务打挂（惊群）。

```python
# 
# `base * 2 ** attempt` 指数退避 ：基础延迟 × 2的尝试次数（1s, 2s, 4s, 8s...） 
# `min(..., cap)` 封顶 ：延迟不超过上限（如最多 30 秒），避免无限增长 
# `+ random.uniform(0, jitter)` 抖动 ：添加随机偏移（0~jitter 秒），打散重试时间
delay = min(base * 2 ** attempt, cap) + random.uniform(0, jitter)
```

### 4. 生产级封装的六个要素

| 要素 | 不做的后果 |
| --- | --- |
| 配置集中（env → 一个对象） | Key 散落在代码里，换供应商要改十处 |
| 超时（connect/read 分开） | 一个卡死请求拖垮整个进程 |
| 重试（仅可重试错误） | 4xx 也重试，浪费钱还更慢 |
| 限流（并发信号量 / QPS） | 批量任务瞬间打满配额 |
| 日志（请求 id、耗时、token） | 出问题无法定位 |
| 成本统计（按 usage 累加） | 月底账单爆炸 |

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 先裸调一次，看清返回结构（30 min）

```python
from openai import OpenAI
import os

client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url=os.environ["DEEPSEEK_BASE_URL"])
resp = client.chat.completions.create(
    model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
    messages=[{"role": "user", "content": "用一句话解释 RAG"}],
    temperature=0.3,
)
print(resp.choices[0].message.content)
print(resp.usage)          # prompt_tokens / completion_tokens / total_tokens
print(resp.model, resp.id) # 线上排障要记录的字段
```

补充说明，`.env` 文件没有被自动加载 ，Python 的`os.environ` 只能读取 系统环境变量 ，不会自动读取项目根目录的`.env` 文件。
安装 python-dotenv
`pip install python-dotenv`
修改代码开头：
`from dotenv import load_dotenv
import os

load_dotenv()  # 自动加载 .env 到环境变量

client = OpenAI(api_key=os.environ["DASHSCOPE_API_KEY"], ...)`

### 任务 2 · 封装配置与客户端（40 min）

完整实现见 [`code/shared/llm_client.py`](../../code/shared/llm_client.py)，骨架：

```python
@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout: float = 60.0
    max_retries: int = 3
    price_in: float = 1.0   # 元 / 百万输入 token
    price_out: float = 2.0  # 元 / 百万输出 token

def load_config(provider: str | None = None) -> LLMConfig:
    ...  # 从 .env 读取，缺 Key 抛 ConfigError
```

### 任务 3 · 重试：先手写，再用库（50 min）

手写版（理解原理）：

```python
def _should_retry(exc: Exception) -> bool:
    # 1. 如果是超时或连接错误 → 可重试（网络问题，稍后可能恢复），直接超时
    #`isinstance` 是 Python 的 类型检查函数 ，判断对象是否是指定类型（或其子类）。
    # 这里的写法的等价于 `isinstance(exc, APITimeoutError) or isinstance(exc, APIConnectionError)
    if isinstance(exc, (APITimeoutError, APIConnectionError)):
        return True
    status = getattr(exc, "status_code", None)
    #| 429 | 限流 / 配额 | 是 | 指数退避 + 抖动 |
    #| 500 / 502 / 503 | 服务端抖动 | 是 | 退避重试，最多 3–5 次 |
    return status is not None and (status == 429 or status >= 500)

for attempt in range(max_retries):
    try:
        return call()
    except Exception as e:
        if attempt == max_retries - 1 or not _should_retry(e):
            raise
        time.sleep(min(2 ** attempt, 8) + random.uniform(0, 0.3))
```

再用 `tenacity` 重写一遍，对比可读性。**先手写理解，再用库提效**——这是整个八周的方法论。

day03_first_call_tenacity.py


### 任务 4 · 成本统计与日志（30 min）

```python
@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def cost(self) -> float: ...
```

在每次调用的日志里输出：`model / 耗时 / prompt_tokens / completion_tokens / 累计成本`。
这个字段在第 7 周做评估报告时会被直接复用。

### 任务 5 · 异步版本（20 min）

```python
from openai import AsyncOpenAI

async def achat(self, messages, **kw) -> str:
    resp = await self._client.chat.completions.create(...)
```

异步是为第 2 周的多信源采集、第 3 周的批量嵌入准备的——这些场景是"1 万个请求"，同步会等到天荒地老。

---

## 代码思考（写进 `logs/day-03.md`）

1. 为什么"多轮对话"本质是客户端重放历史？这会带来哪两个成本问题？怎么缓解（滑窗 / 摘要 / 缓存）？
2. 429 重试时为什么要加随机抖动？不加会发生什么（想想 100 个并发同时重试）？
3. 超时后重试可能导致同一请求被计费两次，怎么接受/规避这个风险？
4. `price_in / price_out` 为什么要单独配置，而不是写死一个"每次调用 0.01 元"？
5. 如果供应商返回 200 但 `choices` 为空，你的封装应该抛什么异常？为什么这类"协议层异常"要单独分类？

## 复盘清单

- [ ] 能画出"messages → token → 响应 → usage"的链路
- [ ] 能背出"可重试 / 不可重试"的状态码分组 可重试【500 502 503 425】
- [ ] `llm_client.py` 通过冒烟测试（无 Key 时应给出明确的 ConfigError）
- [ ] commit：`day03: 生产级 llm_client（超时/重试/日志/成本）`
