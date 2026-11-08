# Day 12 · 文档加载与分块策略

> W3 · 周二 ｜ 5h ｜ 产出 `code/week03/mini_rag/chunking.py` ｜ [Day 11](day-11.md) · [Day 13](day-13.md)

**今日目标**
- 说清"分块"为什么是 RAG 里最影响效果的一步
- 手写三种分块器：固定长度、递归字符、按语义边界
- 用你熟悉的文档做对比实验，用数据选参数

**验收**：三种分块器在 20–50 篇文档上产出的块数、平均长度、边界质量有对比表。

---

## 上午 09:00–11:30 · 理论输入

### 1. 分块决定了两件事

| 决定 | 说明 |
| --- | --- |
| **检索精度** | 块太大 → 噪声多，相似度被稀释；块太小 → 语义不完整，答非所问 |
| **上下文质量** | 块边界切断句子，模型看到半句话，生成质量必然差 |

所以分块不是"预处理细节"，它是 RAG 效果的第一杠杆。

### 2. 三种策略

**A. 固定长度（fixed size）**

```python
chunks = [text[i : i + size] for i in range(0, len(text), size - overlap)]
```

优点：简单、块长可控、成本可预测。缺点：无脑切断句子。

**B. 递归字符分块（recursive）**

按优先级尝试分隔符：`\n\n` → `\n` → `。` → `，` → 空格 → 字符。
先用大分隔符切，超长再降级。这是 LangChain `RecursiveCharacterTextSplitter` 的思路。

**C. 语义分块（semantic）**

按句子算相邻 embedding 的相似度，在"相似度骤降"处切分（话题转换点）。
效果最好但成本最高（要先算 embedding），一般只用于高质量知识库。

### 3. 参数怎么定

| 参数 | 经验值 | 说明 |
| --- | --- | --- |
| chunk_size | 300–600 token（中文约 300–600 字） | 问答类偏小，综述类偏大 |
| overlap | size 的 10%–20% | 防止边界信息丢失，但会增加冗余与成本 |
| 最小块长 | ≥ 50 字 | 太短的块几乎没有检索价值 |

**中文的特殊性**：按字符数近似 token 数（中文 1 字 ≈ 1 token，部分分词器更少）。
英文按 `len(text) / 4` 估算 token。

### 4. 比参数更重要的事：元数据

检索质量的一半来自元数据：

```python
Chunk(
    id="doc12#3",
    text="...",
    metadata={
        "doc_id": "doc12",
        "title": "2026 春节活动规则",
        "section": "奖励发放",
        "chunk_index": 3,
        "source": "kb/activities/2026-spring.md",
        "updated_at": "2026-10-01",
    },
)
```

有了 `section` 和 `title`，检索时可以拼"标题 + section + 正文"一起嵌入（**上下文化**），
命中率通常能提升 5–15 个百分点。这一步很多教程没讲，但它是实战里最划算的优化。

### 5. 从文档到块：加载器

| 格式 | 工具 | 注意 |
| --- | --- | --- |
| Markdown | 直接读，按 `##` 切 section | 保留标题层级最有用 |
| PDF | `pypdf` / `pdfplumber` | 表格与双栏会乱，扫描件要 OCR |
| Word | `python-docx` | 样式信息可帮助分节 |
| 网页 | `trafilatura` / `readability` | 先去掉导航与广告 |
| Excel | `openpyxl` / `pandas` | 一行一条更合理，别按字符切 |

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 写三种分块器（80 min）

```python
@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict[str, Any]

def chunk_fixed(text: str, size: int = 400, overlap: int = 60) -> list[Chunk]: ...
def chunk_recursive(text: str, size: int = 400, overlap: int = 60,
                    seps: tuple[str, ...] = ("\n\n", "\n", "。", "！", "？", "；", "，", " ")) -> list[Chunk]: ...
def chunk_by_heading(md: str, max_size: int = 600) -> list[Chunk]:
    """Markdown 专用：按 ## 切 section，section 过长再递归切。"""
```

递归实现的核心：

```python
def _split(text: str, seps: tuple[str, ...], size: int) -> list[str]:
    if len(text) <= size or not seps:
        return [text]
    sep, rest = seps[0], seps[1:]
    parts = text.split(sep)
    out, buf = [], ""
    for p in parts:
        piece = p + sep
        if len(buf) + len(piece) <= size:
            buf += piece
        else:
            if buf:
                out.append(buf)
            buf = piece if len(piece) <= size else ""
            if len(piece) > size:
                out.extend(_split(piece, rest, size))
    if buf:
        out.append(buf)
    return out
```

这段代码不长，但边界条件很多（空串、超长片段、分隔符在结尾）。**写完后一定要用 20 篇真实文档跑，看有没有空块、超长块。**

### 任务 2 · 切你的真实文档（50 min）

选 20–50 篇你熟的文档（前端技术文档、活动规则、FAQ），三种分块各跑一遍，统计：

| 分块器 | 块数 | 平均长度 | 最长块 | 空块/超长块 | 边界切断句子的比例（抽 20 块人工看） |
| --- | --- | --- | --- | --- | --- |

### 任务 3 · 上下文化实验（30 min）

同一批文档，A 组只嵌正文，B 组嵌 `标题 + section + 正文`。用 Day 11 的相似度方法，
对 10 个问题看 top-5 命中率差异。**这是最便宜的一次效果提升，务必做。**

### 任务 4 · 决策记录（20 min）

写一段 300 字的"我为什么选 X 分块、size/overlap 为什么是这两个数"，放进 `code/week03/mini_rag/README.md`。
面试被问"分块怎么选"时，这段就是答案。

---

## 代码思考（写进 `logs/day-12.md`）

1. overlap 设 0 和设 50%，分别会带来什么问题？为什么 10–20% 是常见区间？
2. 递归分词时，分隔符顺序为什么不能随便排？把 `，` 放在 `。` 前面会怎样？
3. 表格类内容按字符切会出什么灾难？应该怎么处理？
4. 上下文化（标题 + section + 正文）会带来什么副作用？（提示：向量被标题主导、块间相似度升高）
5. 如果一份文档只有 40 字，你还切吗？小于最小块长的块应该丢弃还是合并？

## 复盘清单

- [ ] 三种分块器都有，且没有空块/超长块
- [ ] 有对比表与"边界质量"抽查
- [ ] 上下文化实验有数字
- [ ] commit：`day12: 三种分块器 + 上下文化实验`
