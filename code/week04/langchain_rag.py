"""Day 16 · 用 LangChain 复刻 mini-RAG（可选依赖）。

对比手写版：代码短了，但抽象层变厚。运行前先装依赖：
    uv pip install -r requirements/rag.txt

用法：
    python -m code.week04.langchain_rag "退款多久到账"
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROMPT = """只依据下面的资料回答问题，并用 [资料 n] 标注来源。
资料没有的信息请回答"资料未提及"。

资料：
{context}

问题：{question}"""


def build_chain(kb_dir: Path, persist_dir: Path):
    try:
        from langchain_chroma import Chroma
        from langchain_core.documents import Document
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "缺少依赖，请先执行：uv pip install -r requirements/rag.txt\n"
            f"原始错误：{exc}"
        ) from exc

    from code.shared.llm_client import get_client

    cfg = get_client().config
    docs = [
        Document(page_content=p.read_text(encoding="utf-8"), metadata={"source": p.name})
        for p in sorted(kb_dir.rglob("*.md"))
    ]
    splits = RecursiveCharacterTextSplitter(
        chunk_size=400, chunk_overlap=60, separators=["\n\n", "\n", "。", "，", " "]
    ).split_documents(docs)

    embeddings = OpenAIEmbeddings(api_key=cfg.api_key, base_url=cfg.base_url)
    vectorstore = Chroma.from_documents(
        splits, embeddings, collection_name="kb", persist_directory=str(persist_dir)
    )
    retriever = vectorstore.as_retriever(search_kwargs={"k": 4})
    llm = ChatOpenAI(model=cfg.model, api_key=cfg.api_key, base_url=cfg.base_url, temperature=0.2)
    prompt = ChatPromptTemplate.from_template(PROMPT)

    def format_docs(ds) -> str:
        return "\n\n".join(f"【资料 {i}｜{d.metadata.get('source', '')}】\n{d.page_content}" for i, d in enumerate(ds, 1))

    return {"context": retriever | format_docs, "question": lambda x: x} | prompt | llm | StrOutputParser()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="?", default="退款多久到账")
    parser.add_argument("--kb", default=str(ROOT / "data" / "kb_sample"))
    parser.add_argument("--persist", default=str(ROOT / ".chroma_kb"))
    args = parser.parse_args()

    chain = build_chain(Path(args.kb), Path(args.persist))
    print(chain.invoke(args.question))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
