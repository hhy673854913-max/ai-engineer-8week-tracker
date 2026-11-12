# Day 05 · 结构化输出与运营文案生成器

> W1 · 周五 ｜ 5h ｜ 产出 `code/week01/day05_event_copy.py` + `code/shared/structured.py` ｜ [Day 04](day-04.md)

**今日目标**
- 说清"让模型输出 JSON"的三种做法与各自适用边界
- 掌握 **校验 → 失败 → 带错误重试** 的修复闭环
- 用你最熟的运营场景，做一个真正能进生产流程的文案生成器

**验收**：输入活动主题，稳定输出通过 Pydantic 校验的 JSON；批量 10 条，失败率 ≤ 1 次重试内 100%。

---

## 上午 09:00–11:30 · 理论输入

### 1. 为什么"结构化"是分水岭

Demo 到生产的差距，往往就是这一句话：

> Demo 把模型输出 `print` 出来给人看；生产要把模型输出**喂给下一段代码**。

下游代码要解析、要入库、要校验、要展示，所以输出必须是**契约**。而 LLM 的输出天然是"字符串"，
于是所有结构化方案的本质都是：**用约束把字符串收敛到契约**。

在 Agent 里，结构化输出的头号用途不是文案而是工具调用：`tool_calls[0].function.arguments` 就是一段必须过 schema 的 JSON，参数不合法工具就直接执行失败——Day 22 注册工具时，工具的入参模型就是你今天写的这个 Pydantic 类。把 `CopyVariant` 换成下周 M1 简报的 `BriefItem`（title/summary/category/credibility），这套"校验→回传错误→重试"可以原样跑 100 条资讯抽取。

### 2. 三种做法

| 方案 | 做法 | 优点 | 缺点 | 适用 |
| --- | --- | --- | --- | --- |
| 提示词约束 | 明确要求"只输出 JSON，字段如下" | 通用、零依赖 | 不保证，可能带解释/代码块 | 快速原型 |
| JSON mode | `response_format={"type":"json_object"}` | 保证是合法 JSON | 不保证字段/类型/必填 | 大多数业务 |
| JSON Schema | `response_format={"type":"json_schema","json_schema":{...}}` | 结构强约束 | 各家支持度不一；流式下不友好 | 关键链路 |

**选择顺序**：先 JSON mode + Pydantic 校验；校验频繁失败再升 schema 约束；schema 不支持就退回"提示词 + 修复循环"。

### 3. 修复闭环（本课核心）

```
生成 → 解析 → Pydantic 校验 ──成功──→ 返回
                    │失败
                    ↓
        把"错误信息 + 原始输出"回传给模型，要求只修这一个问题
                    ↓
               最多重试 2 次 → 仍失败则降级（返回默认值 / 抛异常 / 人工介入）
```

```python
def generate_with_retry(prompt: str, model: type[BaseModel], max_repair: int = 2):
    messages = [{"role": "user", "content": prompt}]
    last_err = None
    for _ in range(max_repair + 1):
        raw = chat(messages, json_mode=True, temperature=0)
        try:
            return model.model_validate_json(extract_json(raw))
        except ValidationError as e:
            last_err = e
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"上面的输出不符合要求：{e.errors()[:3]}。只输出修正后的 JSON，不要解释。"},
            ]
    raise StructuredOutputError(str(last_err))
```

三个工程细节：
1. **把错误原文回传**比"重新生成一次"有效得多，模型能定位到具体字段。
2. **限制错误条数**（`e.errors()[:3]`），否则长错误信息反而干扰。
3. **上限 2 次**，超过就降级——无限重试会把成本和延迟顶穿。

### 4. 六种常见失败模式与对策

| 失败模式 | 表现 | 对策 |
| --- | --- | --- |
| Markdown 包裹 | ` ```json ... ``` ` | 提取首个 `{` 到末个 `}` |
| 前后有解释 | "好的，以下是 JSON：{...}" | 同上 + 提示词"只输出 JSON" |
| 截断 | 末尾 `}` 缺失 | 提高 `max_tokens`；检测可修复则补括号 |
| 类型错 | `"3"` 而不是 `3` | Pydantic 转换；或 `strict=True` 暴露问题 |
| 字段缺失 | 少了 `tags` | 给默认值 or 校验失败重试 |
| 幻觉值 | 编造不存在的活动 ID | 约束枚举 / 提供候选列表 / 后置校验 |

### 5. 提示词模板（可直接抄）

```text
你是资深游戏运营文案。请为下面的活动生成 3 套文案方案。

只输出 JSON，不要 markdown 代码块，不要任何解释。
JSON 结构：
{
  "theme": "string，活动主题，不超过 12 字",
  "slogan": "string，一句话主标语，不超过 20 字",
  "bullets": ["string，3-4 条卖点，每条不超过 15 字"],
  "channels": ["string，从 [站内Banner, 推送, 社群, 短视频] 中选"],
  "risk": "low | mid | high"
}

活动信息：
- 主题：{theme}
- 目标人群：{audience}
- 玩法：{mechanic}
- 合规限制：{constraints}
```

注意最后那块"活动信息"——**把变量放在末尾**，前面是固定指令。这样模板可缓存（部分厂商支持 prompt caching），
也更容易做版本管理。

这条理由值得说清楚：prompt caching 指把固定前缀的 token 计算结果缓存住，命中后不再重复计算、通常也不再重复计费，所以"固定指令在前、变量在后"不是排版偏好，而是让每次请求的前缀完全一致以打中缓存。Agent 的 system prompt + 工具定义动辄几千 token、每次请求都重发，这一条能同时压低首字延迟和输入成本。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · `shared/structured.py`：解析与修复（60 min）

```python
import json, re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)

def extract_json(text: str) -> str:
    """从可能带解释/代码块的输出里抠出 JSON 文本。"""
    m = _FENCE.search(text)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("找不到 JSON 对象")
    return text[start : end + 1]

def loads_lenient(text: str) -> dict[str, Any]:
    """容忍尾逗号、单引号等小毛病；失败才抛错。"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        fixed = re.sub(r",\s*([}\]])", r"\1", text)     # 去尾逗号
        return json.loads(fixed)
```

### 任务 2 · 定义业务模型（40 min）类 CopyVariant

```python
from pydantic import BaseModel, Field, field_validator
from typing import Literal

class CopyVariant(BaseModel):
    theme: str = Field(min_length=2, max_length=12)
    slogan: str = Field(min_length=4, max_length=20)
    bullets: list[str] = Field(min_length=3, max_length=4)
    channels: list[Literal["站内Banner", "推送", "社群", "短视频"]]
    risk: Literal["low", "mid", "high"] = "low"

    @field_validator("slogan")
    @classmethod
    def no_exclamation(cls, v: str) -> str:
        if "!!" in v:
            raise ValueError("标语不允许连续感叹号")
        return v
```

`field_validator` 是**业务规则落地点**：合规词、长度、禁用标点都可以在这里拦。

### 任务 3 · 生成器主程序（60 min）

```python
def generate(theme: str, audience: str, mechanic: str, constraints: str, n: int = 3) -> list[CopyVariant]:
    prompt = TEMPLATE.format(theme=theme, audience=audience, mechanic=mechanic, constraints=constraints)
    raw = chat(prompt, json_mode=True, temperature=0.8, max_tokens=900)
    data = loads_lenient(extract_json(raw))
    return [CopyVariant.model_validate(v) for v in data["variants"]]
```

批量跑 10 个主题，记录：一次通过率、平均重试次数、平均耗时、平均 token 成本——这四个数字写进 `logs/day-05.md`。

### 任务 4 · 降级策略（20 min）

想清楚三个问题并写进代码注释：
- 重试 2 次仍失败，返回什么？（空列表 + 调用方提示 / 人工兜底）
- 部分字段合法、部分不合法，是整条丢弃还是保留可用字段？
- 线上要不要把失败样本落盘？落盘要不要脱敏？

---

## 代码思考（写进 `logs/day-05.md`）

1. 为什么"提示词约束"永远无法达到 100% 可靠？从模型生成机制（逐 token 采样）角度解释。
2. `response_format=json_object` 只保证"是 JSON"，不保证"是你想要的 JSON"——那它到底省了什么？
3. 修复循环里把 `assistant` 的坏输出也塞回上下文，为什么比只发"请重新生成"更有效？
4. 如果模型返回的 `risk` 是 `"中等"` 而不是 `"mid"`，用 `Literal` 会报错——你会选严格失败还是映射容错？理由？
5. 批量生成时，10 个请求串行 vs 并发，成本和失败率有区别吗？（提示：429 概率、重试风暴）

## 复盘清单

- [ ] 能画出"生成 → 解析 → 校验 → 修复"的闭环
- [ ] 六种失败模式能各说一个对策
- [ ] 有 10 条批量数据的一手指标
- [ ] commit：`day05: 结构化输出修复闭环 + 活动文案生成器`
- [ ] 第 1 周收尾：确认 `llm_client.py` 已可用于后续所有项目
