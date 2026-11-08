# Day 11 · 嵌入向量与语义相似度

> W3 · 周一 ｜ 5h ｜ 产出 `code/week03/mini_rag/similarity.py` ｜ [Day 10](../week-02/day-10.md)

**今日目标**
- 说清 embedding 是什么、为什么能表达"语义"
- 手写余弦相似度与 top-k 检索，不依赖任何库
- 用真实句子做实验，建立"相似度数值 = 什么感觉"的直觉

**验收**：`python -m week03.mini_rag.similarity` 打印 8 个句子的相似度矩阵与 top-3 近邻。

---

## 上午 09:00–11:30 · 理论输入

### 1. embedding 到底是什么

把一段文本映射成一个固定长度的浮点向量：

```text
"如何退款"        → [0.021, -0.113, 0.884, ...]   # 1024 维
"退款怎么操作"    → [0.019, -0.108, 0.879, ...]   # 与上面很近
"今天天气不错"    → [-0.442, 0.301, 0.077, ...]   # 很远
```

模型是在海量语料上训练的，**语义相近的文本在向量空间里距离近**。
所以"检索"就变成了"找最近的向量"——这是 RAG 的全部数学基础，没有比这更复杂的东西。

### 2. 余弦相似度

```text
cos(a, b) = (a · b) / (|a| × |b|)
```

范围 [-1, 1]，越接近 1 越相似。**如果向量已归一化（|a| = 1），余弦相似度就等于点积**，快一个数量级。

```python
def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
```

用 numpy 时：`a @ b / (np.linalg.norm(a) * np.linalg.norm(b))`，或者先 `normalize` 再直接 `a @ b`。

### 3. 走 API 还是本地模型

| 方案 | 优点 | 缺点 | 适用 |
| --- | --- | --- | --- |
| API（百炼 text-embedding-v3 / OpenAI） | 零运维，效果好 | 按量计费、有网络依赖 | 快速验证、文档量中等 |
| 本地（BGE-M3 / bge-large-zh） | 免费、可离线、数据不出内网 | 要 GPU/CPU 算力，首次加载慢 | 数据敏感、量大 |
| 中转/自建 | 可控 | 运维成本 | 有基础设施的团队 |

**维度不是越高越好**：1024 维已经足够，1536/3072 提升有限但存储和计算翻倍。
关键是**同一个索引里的向量必须来自同一个模型**——换模型 = 重建索引，这是 RAG 最常见的翻车点之一。

### 4. 相似度的"感觉"（必须亲手建立）

| 分值 | 含义 | 例子 |
| --- | --- | --- |
| > 0.90 | 几乎同义 | "怎么退款" vs "如何申请退款" |
| 0.80–0.90 | 强相关 | "退款流程" vs "退款需要多久" |
| 0.70–0.80 | 同主题 | "退款政策" vs "发票怎么开" |
| < 0.60 | 基本无关 | "退款" vs "天气" |

**这个表格必须你自己实测填一遍**，不同模型的分值分布差异很大，照抄别人的阈值一定翻车。

### 5. 一个反直觉的事实

embedding 捕捉的是**语义相似**，不是**答案相关**。
"退款需要多久"和"退款政策"可能很像，但前者需要的是"时效"这个具体答案。
所以 RAG 的召回只是第一步，**重排与生成阶段才是精度来源**（Day 15、Day 14）。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 纯手写相似度（40 min）

```python
# code/week03/mini_rag/similarity.py
def cosine(a: Sequence[float], b: Sequence[float]) -> float: ...
def top_k(query: Sequence[float], matrix: Sequence[Sequence[float]], k: int = 3) -> list[tuple[int, float]]: ...
def similarity_matrix(vecs: Sequence[Sequence[float]]) -> list[list[float]]: ...
```

要求：不 import numpy 也能跑通（用于理解），再写一个 numpy 版本对比性能（10 万 × 1024 的差距有多大）。

### 任务 2 · 调用真实 embedding API（50 min）

OpenAI 兼容写法（百炼 / OpenAI / 硅基流动都适用）：

```python
from openai import OpenAI

client = OpenAI(api_key=os.environ["DASHSCOPE_API_KEY"],
                base_url=os.environ["DASHSCOPE_BASE_URL"])

def embed(texts: list[str], model: str = "text-embedding-v3") -> list[list[float]]:
    resp = client.embeddings.create(model=model, input=texts, dimensions=1024)
    return [d.embedding for d in resp.data]
```

注意：`dimensions` 参数不是所有厂商都支持，不支持就删掉。批量接口一次最多 10–25 条，要看文档。

> 仓库里的 `code/week03/mini_rag/embeddings.py` 读的是独立的 `EMBED_*` 变量，所以"Kimi 聊天 + 百炼嵌入"
> 这种混搭可以直接用；聊天厂商不支持 embedding 时它会给明确提示，而不是抛一个 404。

### 任务 3 · 相似度实验（60 min）

准备 8 个句子（3 组近似 + 2 个离群），做三件事：
1. 打印 8×8 相似度矩阵（保留 3 位小数）
2. 对每个句子找 top-3 近邻，人工判断"是否符合直觉"
3. 记录 3 个"不符合直觉"的案例，分析原因（一词多义？领域词？长度差异？）

### 任务 4 · 归一化与点积（20 min）

```python
import numpy as np

def normalize(m: np.ndarray) -> np.ndarray:
    return m / np.linalg.norm(m, axis=1, keepdims=True)

# 归一化后，余弦相似度 = 点积，一次矩阵乘法算完所有 pair
sims = normalize(A) @ normalize(B).T
```

用 `time.perf_counter()` 对比"循环算余弦"与"矩阵乘法"在 1000 条上的耗时差。

---

## 代码思考（写进 `logs/day-11.md`）

1. 为什么"换了 embedding 模型就必须重建索引"？混用两个模型的向量会怎样？
2. 余弦相似度只看方向不看长度，这在文本检索里为什么是优点？什么场景下反而需要看长度？
3. 你的实验里相似度 0.78 的一对句子其实不相关，可能是什么原因导致的？（提示：长度、停用词、领域专名）
4. 1024 维向量存 10 万条要多少内存？用 `float32` 和 `float16` 分别是多少？这对选型有什么影响？
5. 为什么"检索到的文档相似度高"不等于"能回答问题"？举一个你数据里的例子。

## 复盘清单

- [ ] 手写版与 numpy 版都能跑，性能差有记录
- [ ] 相似度"感觉表"用自己数据填过
- [ ] 有 3 个反直觉案例的分析
- [ ] commit：`day11: 手写余弦相似度 + embedding 实验`
