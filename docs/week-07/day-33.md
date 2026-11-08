# Day 33 · 可观测性：链路追踪与提示词版本管理

> W7 · 周三 ｜ 5h ｜ 产出 `code/week07/observability.py` ｜ [Day 32](day-32.md) · [Day 34](day-34.md)

**今日目标**
- 给 M2 接入链路追踪，能看清"一次提问里每一步花了多少时间、多少 token、多少钱"
- 用 trace 定位一个真实性能问题
- 建立提示词版本管理习惯：改了哪版、效果如何、能否回滚

**验收**：一次提问在追踪面板里能看到 retrieve / rerank / generate 三个 span，含延迟与 token 成本。

---

## 上午 09:00–11:30 · 理论

### 1. 为什么需要可观测

线上问题通常长这样：

> "用户说有时候很慢。"
> "有时候答得不对，但复现不了。"

没有追踪，你只能猜。有了追踪，你能回答：

- 慢在检索还是生成？（P95 分解）
- 贵在哪个环节？（token 归属）
- 答错的那次，检索到了什么？（输入快照）
- 是不是改了 prompt 之后变差的？（版本对比）

### 2. Trace / Span / Run 三层模型

```text
Trace: 一次用户提问（trace_id = req-123）
 ├─ Span: retrieve            (120ms, 0 token)
 ├─ Span: rerank              (35ms, 0 token)
 ├─ Span: generate            (1.8s, 1200 in / 260 out, ¥0.0021)
 └─ Span: postprocess         (2ms)

Run: 一个评估批次的聚合（run_id = eval-20261222-1）
```

**Span 要带输入输出**：只记耗时没用，出问题时要能看到"当时检索到了什么"。

### 3. Langfuse / LangSmith 怎么选

| | Langfuse | LangSmith |
| --- | --- | --- |
| 部署 | 开源自托管 / 云 | 云为主 |
| 价格 | 免费自托管 | 有免费额度 |
| 强项 | 自托管、数据可控 | 与 LangChain 深度集成 |
| 接入 | SDK 装饰器 | 环境变量 + 自动埋点 |

国内团队常选自托管 Langfuse（数据不出内网）。**没有条件就先用日志自己实现**——
今天先用"结构化日志 + trace_id"手写一版，再决定要不要上平台。

### 4. 提示词版本管理

```python
PROMPT_REGISTRY = {
    "qa_answer": {
        "v1": {"template": "...", "created": "2026-11-26", "note": "初版"},
        "v2": {"template": "...", "created": "2026-12-10", "note": "加引用格式约束"},
    }
}
```

三个要求：
1. **模板与代码分离**（文件或配置中心），改 prompt 不用发版
2. **每版有 note + 效果数据**（Faithfulness 变化）
3. **能回滚**（`PROMPT_VERSION=v1` 环境变量）

**没有版本管理的 prompt 迭代 = 无法复现的实验。**

### 5. 关键指标看板

| 指标 | 采样 | 告警阈值 |
| --- | --- | --- |
| P50 / P95 延迟 | 全量 | P95 > 4s |
| 错误率 | 全量 | > 1% |
| 单次成本 | 全量 | 日均 > 预算 |
| 拒答率 | 全量 | 突增 2 倍（可能检索挂了） |
| 引用有效率 | 抽样 10% | < 95% |
| 用户点踩率 | 有反馈渠道时 | 突增 |

**拒答率突增是最好的"检索故障"报警器**，比错误率更灵敏。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 手写 trace（80 min）

```python
@dataclass
class Span:
    name: str
    start: float
    end: float | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    meta: dict = field(default_factory=dict)

    @property
    def ms(self) -> int:
        return int(((self.end or time.perf_counter()) - self.start) * 1000)

class Trace:
    def __init__(self, trace_id: str, question: str):
        self.trace_id, self.question, self.spans = trace_id, question, []

    @contextmanager
    def span(self, name: str, **meta):
        s = Span(name=name, start=time.perf_counter(), meta=meta)
        self.spans.append(s)
        try:
            yield s
        finally:
            s.end = time.perf_counter()

    def to_dict(self) -> dict: ...
```

用起来：

```python
trace = Trace(new_id(), question)
with trace.span("retrieve") as s:
    hits = service.retrieve(question)
    s.meta["hit_ids"] = [h.id for h in hits]
with trace.span("generate") as s:
    ans = service.generate(question, hits)
    s.tokens_in, s.tokens_out = usage_in, usage_out
log.info(json.dumps(trace.to_dict(), ensure_ascii=False))
```

### 任务 2 · 接 Langfuse（可选，50 min）

```powershell
uv pip install langfuse
```

```python
from langfuse.decorators import observe, langfuse_context

@observe()
def retrieve(question: str): ...

@observe()
def generate(question: str, hits: list): ...
```

配好 `LANGFUSE_PUBLIC_KEY` / `SECRET_KEY` 即可在面板看到。**没有账号就跳过，手写版足够。**

### 任务 3 · 用 trace 定位一个真实问题（50 min）

跑 20 次提问，统计每步 P50/P95。找出：
- 最慢的一步是哪步？（通常是 generate）
- 最贵的一步？（通常也是 generate）
- 有没有"检索 10ms 但生成 4s"的极端样本？

把结论写进 `logs/day-33.md`，并给出一个优化假设。

### 任务 4 · 提示词版本化（30 min）

把 M2 的 prompt 抽到 `prompts/qa_answer_v2.md`，代码里用 `load_prompt(name, version)` 读取。
跑一次 A/B：v1 vs v2 的 Faithfulness 对比，写进评估报告。

---

## 代码思考（写进 `logs/day-33.md`）

1. 为什么 Span 要记录输入输出，而不只是耗时？记录输入有什么隐私风险，怎么处理？
2. `trace_id` 应该在哪个环节生成？如果前端也生成一个，怎么和后台对齐？
3. 拒答率突增为什么是好的故障信号？还有哪些"业务指标"能当报警器？
4. 提示词版本化后，线上出现"昨天还好今天变差"，你的排查顺序是什么？
5. 自托管 Langfuse 与"自己写日志 + ELK"相比，多解决了什么？

## 复盘清单

- [ ] 一次提问有三个 span 的完整记录
- [ ] 有 20 次调用的耗时分布
- [ ] prompt 已抽出版本文件
- [ ] commit：`day33: 手写 trace + 提示词版本化`
