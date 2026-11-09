# Day 13 · 向量库：存储、检索与增量更新

> W3 · 周三 ｜ 5h ｜ 产出 `code/week03/mini_rag/store.py` + `ingest.py` ｜ [Day 12](day-12.md) · [Day 14](day-14.md)

**今日目标**
- 说清向量库比"numpy 数组 + 循环"多解决了什么
- 用 Chroma 完成增删改查、元数据过滤、持久化
- 手写一个 numpy 版向量库作为"没有依赖时的兜底"，理解 HNSW 的动机

**验收**：`python -m week03.mini_rag.ingest --docs data/kb` 把文档入库，`python -m week03.mini_rag.store --query "退款多久到账"` 返回 top-5。

---

## 上午 09:00–11:30 · 理论输入

### 1. 向量库解决的不是"存储"

暴力检索就是"算 N 次余弦再排序"。10 万条 × 1024 维，一次查询约 1 亿次乘加——CPU 上几十毫秒，其实能接受。
向量库的价值在别处：

| 能力 | 裸 numpy | 向量库 |
| --- | --- | --- |
| 元数据过滤（按品类/时间/来源） | 自己写 | 内置 `where` |
| 持久化与增量更新 | 自己序列化 | `upsert` / `delete` |
| 近似最近邻（ANN） | 无 | HNSW / IVF |
| 多租户与集合隔离 | 自己设计 | collection |
| 并发与服务化 | 自己扛 | 内置 |

**结论**：几千条以内，numpy 足够；上万条或要过滤/更新，上向量库。

### 2. HNSW 的直觉（不需要会实现）

想象一个多层"高速公路网"：
- 最上层节点少，边很长 → 快速跳到大区域
- 往下层节点变密，边变短 → 逐步逼近
- 查询时从顶层贪心走到最近点，再逐层下降到最底层

两个关键参数：
- `M`（每层连接数）：越大越准、越占内存
- `ef_construction` / `ef_search`：候选队列大小，越大越准越慢

**这就是"近似"的来源**：为了快，放弃遍历全部点，所以 recall < 100%。工程上用 95% 召回 + 10 倍速度，通常划算。

### 3. 距离度量要对齐

| 度量 | 适用 | 注意 |
| --- | --- | --- |
| cosine | 文本 embedding 默认 | 需向量归一化 |
| l2（欧氏） | 图像、未归一化向量 | 与 cosine 会给出不同排序 |
| ip（内积） | 归一化后等价 cosine | 快 |

**入库前必须确认**：集合的 `hnsw:space` 与你的 embedding 是否匹配。用 cosine 建库、用 l2 查询，结果会莫名其妙地差。

### 4. Chroma 的基本用法

```python
import chromadb

client = chromadb.PersistentClient(path="./chroma_db")
col = client.get_or_create_collection(
    name="kb_activity",
    metadata={"hnsw:space": "cosine"},
)

col.upsert(
    ids=[c.id for c in chunks],
    documents=[c.text for c in chunks],
    embeddings=[e for e in vectors],
    metadatas=[c.metadata for c in chunks],
)

res = col.query(
    query_embeddings=[q_vec],
    n_results=5,
    where={"category": "活动规则"},          # 元数据过滤
    include=["documents", "metadatas", "distances"],
)
```

三个坑：
1. `distances` 在 cosine 下是 `1 - cos`，**越小越相似**，别当相似度用。
2. `where` 只支持有限的运算符（`$eq/$in/$gt/$and`），复杂过滤要拆成多次查询。
3. **同 id 覆盖**用 `upsert`，用 `add` 会因主键冲突报错。

Chroma 是一个 pip 装完就在进程内跑的嵌入式向量库：不用起服务、不用 docker，`PersistentClient(path="./chroma_db")` 把数据落在本地目录（这个目录就是你的数据库，删了就得重新入库），适合原型和单机演示；生产上团队更常见的是 pgvector（已有 Postgres 加个扩展就行）、Qdrant、Milvus，面试问"向量库怎么选"时你要能说出这三者的差别。今天用 Chroma 只是让你把注意力放在检索逻辑上，M2 之后换实现只改 `store.py` 这一层。

### 5. 增量更新与"重建"的抉择

文档会改。三种策略：

| 策略 | 做法 | 适合 |
| --- | --- | --- |
| 全量重建 | 清库 → 重新切分嵌入 | 小库、变更频繁 |
| 按文档替换 | `delete(where={"doc_id": x})` + 重新 upsert | 中库，推荐 |
| 块级 diff | 比 hash，只更新变了的块 | 大库，工程量大 |

注意：**改了分块参数就必须全量重建**，因为块 id 与边界都变了。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 手写 numpy 向量库（60 min）

```python
class NumpyVectorStore:
    def __init__(self, dim: int, path: Path | None = None): ...
    def upsert(self, ids, vectors, texts, metadatas) -> None: ...
    def query(self, vector, k=5, where: dict | None = None) -> list[SearchHit]: ...
    def delete(self, ids: list[str] | None = None, where: dict | None = None) -> int: ...
    def save(self) -> None: ...   # npz + jsonl
    def load(self) -> None: ...
```

要求：
- 向量存 `np.float32` 矩阵，元数据存 list[dict]
- 查询：先按 `where` 过滤行索引，再矩阵乘排序
- 持久化：`.npz` 存向量 + `.jsonl` 存 id/text/metadata

这个类 100 行以内，写完之后你对"向量库"就没有神秘感了。

### 任务 2 · Chroma 入库（50 min）

```python
def ingest(docs_dir: Path, col, embed_fn) -> dict:
    stats = {"docs": 0, "chunks": 0, "skipped": 0}
    for p in docs_dir.rglob("*.md"):
        chunks = chunk_by_heading(p.read_text(encoding="utf-8"))
        chunks = [c for c in chunks if len(c.text.strip()) >= 50]
        vectors = embed_fn([c.text for c in chunks])
        col.upsert(ids=[c.id for c in chunks], documents=[c.text for c in chunks],
                   embeddings=vectors, metadatas=[c.metadata for c in chunks])
        stats["docs"] += 1
        stats["chunks"] += len(chunks)
    return stats
```

注意：**embed 要批量**，一次 10–25 条，别一条一条调。

### 任务 3 · 对照实验：语义 vs 关键词（40 min）

同一批文档，同一批问题：
- A 组：向量检索（本日成果）
- B 组：关键词匹配（`text.lower().count(query)` 或简单 BM25）

记录两种方式各答对几个。**你会发现问题里的专有名词（活动名、道具名）关键词更准，而口语化问题向量更准**——
这个观察直接引出 Day 15 的混合检索。

今天的关键词基线就用最笨的 `text.lower().count()`：它只要跑出对照组数字、证明"向量在口语化问题上更强"就够了。BM25 明天手写，等你在 Day 15 看到它在 `SPRING2026` 这类专名上比 count 强一个档，就明白混合检索为什么值得维护两套索引。

### 任务 4 · 元数据过滤（30 min）

给块加 `category`（活动规则 / 玩法说明 / FAQ）与 `updated_at`，实现：
- 只搜"活动规则"类
- 只搜最近 90 天更新的
- 过滤 + top-k 的耗时对比（过滤能显著减少候选集）

---

## 代码思考（写进 `logs/day-13.md`）

1. 为什么 `distances` 越小越相似？如果直接把 distance 当相似度展示给用户会出什么问题？
2. 集合用 l2 建、查询用 cosine，结果为什么会变差？给出一个具体的反例。
3. `upsert` 与"先 delete 再 add"在并发下有什么区别？
4. 10 万块、1024 维、float32，内存占用多少？如果换成 3072 维还撑得住吗？
5. 元数据过滤放在"检索前"和"检索后"有什么本质区别？（提示：top-k 被过滤掉）

## 复盘清单

- [ ] numpy 版向量库能存能查能落盘
- [ ] Chroma 入库成功，`--query` 能返回结果
- [ ] 向量 vs 关键词的对照数据已记录
- [ ] commit：`day13: numpy 向量库 + Chroma 入库`
