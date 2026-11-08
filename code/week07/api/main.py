"""Day 34 · FastAPI 服务化：健康检查、配置、流式问答、错误处理。

启动（仓库根目录）：
    uvicorn code.week07.api.main:app --reload --port 8000
然后打开 http://127.0.0.1:8000/docs

注意：SSE 要关掉 Nginx 缓冲（X-Accel-Buffering: no），生产环境记得配。
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.week03.mini_rag.chunking import load_markdown_dir  # noqa: E402
from code.week03.mini_rag.embeddings import HashingEmbedder  # noqa: E402
from code.week03.mini_rag.rag import CONTEXT_PROMPT, MiniRAG  # noqa: E402
from code.week03.mini_rag.store import NumpyVectorStore  # noqa: E402

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
log = logging.getLogger("api")

KB_DIR = ROOT / "data" / "kb_sample"
INDEX_DIR = ROOT / ".mini_rag_index"


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    top_k: int | None = Field(default=4, ge=1, le=10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """重资源只加载一次：索引、嵌入器、客户端。"""
    embed = HashingEmbedder()
    if (INDEX_DIR / "vectors.npy").exists():
        store = NumpyVectorStore.load(INDEX_DIR)
        log.info("loaded index: %d chunks", len(store))
    else:
        chunks = load_markdown_dir(KB_DIR)
        store = NumpyVectorStore()
        store.upsert(chunks, embed([c.text for c in chunks]))
        log.info("built in-memory index: %d chunks", len(store))

    app.state.rag = MiniRAG(store, embed, chat_fn=None, top_k=4, min_score=0.05)
    app.state.embed = embed
    try:
        from code.shared.llm_client import get_client

        app.state.client = get_client()
    except Exception as exc:  # noqa: BLE001 - 没有 Key 也要能启动，方便看 /docs
        app.state.client = None
        log.warning("LLM 客户端未初始化（%s），/api/query 将返回检索结果", exc)
    yield


app = FastAPI(title="M2 知识库问答 API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    trace_id = getattr(request.state, "trace_id", "-")
    log.exception("unhandled trace=%s", trace_id)
    return JSONResponse(status_code=500, content={"error": "internal_error", "trace_id": trace_id})


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"ok": True, "version": app.version}


@app.get("/api/config")
async def config() -> dict[str, Any]:
    rag: MiniRAG = app.state.rag
    return {
        "top_k": rag.top_k,
        "min_score": rag.min_score,
        "chunks": len(rag.store),
        "llm": getattr(app.state.client, "config", None) and app.state.client.config.model,
    }


@app.post("/api/query/sync")
async def query_sync(req: QueryRequest, request: Request) -> dict[str, Any]:
    trace_id = request.headers.get("x-trace-id", f"req-{int(time.time() * 1000)}")
    request.state.trace_id = trace_id
    rag: MiniRAG = app.state.rag
    t0 = time.perf_counter()

    hits = await asyncio.to_thread(rag.retrieve, req.question, req.top_k or 4)
    if not hits:
        return {"trace_id": trace_id, "answer": "当前知识库没有找到相关内容。", "citations": [], "refused": True}

    if app.state.client is None:
        return {
            "trace_id": trace_id,
            "answer": "（未配置 API Key，仅返回检索结果）",
            "hits": [{"source": h.chunk.metadata.get("source"), "score": h.score, "text": h.chunk.text[:160]} for h in hits],
            "refused": False,
        }

    context = rag.build_context(hits)
    answer = await app.state.client.achat(
        [{"role": "user", "content": CONTEXT_PROMPT.format(context=context, question=req.question)}],
        temperature=0.2,
        max_tokens=600,
    )
    citations = MiniRAG.parse_citations(answer.content, hits)
    return {
        "trace_id": trace_id,
        "answer": answer.content,
        "citations": citations,
        "latency_ms": int((time.perf_counter() - t0) * 1000),
        "cost_cny": answer.cost_cny,
    }


@app.post("/api/query")
async def query(req: QueryRequest, request: Request):
    trace_id = request.headers.get("x-trace-id", f"req-{int(time.time() * 1000)}")
    request.state.trace_id = trace_id
    rag: MiniRAG = app.state.rag

    async def gen():
        try:
            yield sse({"type": "start", "trace_id": trace_id})
            hits = await asyncio.to_thread(rag.retrieve, req.question, req.top_k or 4)
            yield sse(
                {
                    "type": "hits",
                    "hits": [
                        {"source": h.chunk.metadata.get("source"), "section": h.chunk.metadata.get("section"),
                         "score": round(h.score, 3), "text": h.chunk.text[:120]}
                        for h in hits
                    ],
                }
            )
            if not hits:
                yield sse({"type": "delta", "text": "当前知识库没有找到相关内容。"})
                yield sse({"type": "done", "citations": []})
                return
            if app.state.client is None:
                yield sse({"type": "delta", "text": "（未配置 API Key，仅返回检索结果）"})
                yield sse({"type": "done", "citations": []})
                return

            context = rag.build_context(hits)
            async for piece in app.state.client.astream(
                [{"role": "user", "content": CONTEXT_PROMPT.format(context=context, question=req.question)}],
                temperature=0.2,
                max_tokens=600,
            ):
                yield sse({"type": "delta", "text": piece})
            yield sse({"type": "done", "citations": []})
        except asyncio.CancelledError:
            log.info("client disconnected trace=%s", trace_id)
            raise
        except Exception as exc:  # noqa: BLE001 - 流已开始，只能以事件形式报错
            log.exception("stream error trace=%s", trace_id)
            yield sse({"type": "error", "message": "生成失败，请重试", "trace_id": trace_id})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.get("/api/docs/{doc_id}")
async def read_doc(doc_id: str) -> dict[str, str]:
    path = KB_DIR / f"{doc_id}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"文档不存在: {doc_id}")
    return {"doc_id": doc_id, "content": path.read_text(encoding="utf-8")}
