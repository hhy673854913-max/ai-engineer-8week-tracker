# Day 16 · LangChain 快速上手与复刻 mini-RAG

> W4 · 周一 ｜ 5h ｜ 产出 `code/week04/langchain_rag.py` ｜ [Day 15](../week-03/day-15.md) · [Day 17](day-17.md)

**今日目标**
- 用 LangChain 重写第 3 周的 mini-RAG，**体会框架到底替你做了什么、代价是什么**
- 掌握 LCEL 的基本组合方式（`|`、`RunnableParallel`、`RunnablePassthrough`）
- 形成自己的判断：什么时候该用框架，什么时候不该

**验收**：`python -m week04.langchain_rag "退款多久到账"` 输出答案 + 引用，代码 ≤ 80 行。

---

## 上午 09:00–11:30 · 理论输入

### 1. 框架的定位：不是"更简单"，是"更标准化"

第 3 周你手写的 mini-RAG 大约 400 行，LangChain 版大约 60 行。少的 340 行去哪了？
——变成了 `Document` / `TextSplitter` / `VectorStore` / `Retriever` 这些**标准接口**。

标准接口带来两个好处：
1. 组件可替换（换向量库、换模型不改业务代码）
2. 生态可复用（别人的 Loader / Retriever 你能直接用）

代价：
1. 抽象层多，出问题难定位（错误栈很深）
2. 版本迭代快，API 常变（教程三个月就过期）
3. 隐藏了关键细节（比如它到底怎么切块、怎么拼 context）

**结论**：先手写（第 3 周），再用框架（本周）。这样你既能享受效率，又能在出问题时钻进去。

### 2. LangChain 的四个核心抽象

| 抽象 | 作用 | 对应你手写的 |
| --- | --- | --- |
| `Document` | 文本 + metadata | `Chunk` |
| `TextSplitter` | 分块 | `chunk_recursive` |
| `VectorStore` | 向量存储与检索 | `NumpyVectorStore` / Chroma |
| `Retriever` | 检索接口（`invoke(query) -> list[Document]`） | `MiniRAG.retrieve` |

模型层：`ChatOpenAI`（兼容任何 OpenAI 协议端点）。
输出层：`StrOutputParser`、`JsonOutputParser`、`PydanticOutputParser`。

### 3. LCEL：用管道符组合

```python
chain = prompt | llm | StrOutputParser()
result = chain.invoke({"question": "退款多久到账"})
```

`|` 的本质是 `__or__` 重载，把前一个 Runnable 的输出喂给下一个。所以：

- 前面输出 `dict` → 后面要能接收 `dict`（通常是 `ChatPromptTemplate`）
- 中间要透传输入 → `RunnablePassthrough`
- 要并行分支 → `RunnableParallel`

### 4. RAG 链的两种写法

**写法 A：手写编排（推荐先学这个）**

```python
def rag(question: str) -> str:
    docs = retriever.invoke(question)
    context = "\n\n".join(f"[{i}] {d.page_content}" for i, d in enumerate(docs, 1))
    return (prompt | llm | StrOutputParser()).invoke({"context": context, "question": question})
```

**写法 B：全链式**

```python
chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt | llm | StrOutputParser()
)
```

写法 B 更"LangChain"，但调试时你看不到中间检索结果。**生产中建议在检索后打日志**，所以 A 更实用。

### 5. 版本与依赖的坑

```powershell
uv pip install langchain langchain-openai langchain-community
```

- `langchain` 是元包，核心在 `langchain-core`
- 模型接入在 `langchain-openai`（新版拆包了，老教程里的 `from langchain.chat_models import ChatOpenAI` 已废弃）
- 向量库接入在 `langchain-chroma` / `langchain-community`

**遇到 ImportError 先查版本，再查文档，不要照抄三年前的博客。**

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 冒烟测试（30 min）

```python
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

llm = ChatOpenAI(model=MODEL, api_key=KEY, base_url=BASE, temperature=0)
chain = ChatPromptTemplate.from_template("用一句话解释 {topic}") | llm | StrOutputParser()
print(chain.invoke({"topic": "RAG"}))
```

能跑通再往下，跑不通先解决 Key / base_url / 模型名。

### 任务 2 · 复刻 mini-RAG（90 min）

```python
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

docs = [Document(page_content=p.read_text(encoding="utf-8"), metadata={"source": str(p)}) for p in KB.rglob("*.md")]
splits = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=80,
                                        separators=["\n\n", "\n", "。", "，", " "]).split_documents(docs)
vs = Chroma.from_documents(splits, OpenAIEmbeddings(model=EMBED_MODEL, base_url=BASE, api_key=KEY),
                           collection_name="kb", persist_directory="./chroma_db")
retriever = vs.as_retriever(search_kwargs={"k": 5})
```

注意 `OpenAIEmbeddings` 的 `base_url` 参数名与 `ChatOpenAI` 可能不同（有的版本是 `openai_api_base`），
**以你安装的版本文档为准**，这也是框架的代价之一。

### 任务 3 · 对比实验（50 min）

同一批 20 个问题，对比手写版与 LangChain 版：

| 维度 | 手写 | LangChain |
| --- | --- | --- |
| 代码行数 | | |
| hit-rate@5 | | |
| 单次延迟 | | |
| 依赖数量 | | |
| 定位问题的难度（1-5） | | |

**如果 hit-rate 明显不同，先怀疑分块参数不一致**（框架默认值与你的不同），这是最常见的"框架玄学"来源。

### 任务 4 · 写"框架取舍"笔记（20 min）

300 字，说清三件事：什么场景用框架、什么场景坚持手写、如果框架升级破坏兼容你怎么办。

---

## 代码思考（写进 `logs/day-16.md`）

1. `RecursiveCharacterTextSplitter` 的 `chunk_size` 是按字符还是按 token 算？中文场景有什么坑？
2. 为什么 `RunnablePassthrough` 在 RAG 链里是必需的？去掉它会怎样？
3. 框架把检索结果封装成 `Document`，你丢失了哪些手写版里有的信息？（提示：score、距离）
4. 两版 hit-rate 不一致时，你的排查顺序是什么？
5. 如果团队里有人说"用 LangChain 吧，省事"，你会怎么回应（结合今天的对比数据）？

## 复盘清单

- [ ] LangChain 版能跑，代码 ≤ 80 行
- [ ] 对比表填完
- [ ] 框架取舍笔记已写
- [ ] commit：`day16: LangChain 复刻 mini-RAG + 对比`
