"""Day 20 · M2 FastAPI SSE 后端：流式问答 + 引用溯源。

SSE 契约：
    POST /api/query
    → data: {"type":"hits","hits":[{"n":1,"score":0.82,"title":"...","snippet":"..."}]}
    → data: {"type":"delta","text":"..."}
    → data: {"type":"done","citations":[{"n":1,"source":"...","score":0.82,"text":"..."}]}

用法：
    uvicorn code.week04.m2_kb.web.app:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from code.week04.m2_kb.qa_chain import QAService, DEFAULT_INDEX_DIR

log = logging.getLogger("m2_web")

app = FastAPI(title="M2 知识库问答", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_service: QAService | None = None


def get_service() -> QAService:
    global _service
    if _service is None:
        _service = QAService(index_dir=DEFAULT_INDEX_DIR)
    return _service


class QueryReq(BaseModel):
    question: str
    session_id: str | None = None


def _sse(obj: dict) -> str:
    """把 dict 转成 SSE 格式字符串。"""
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@app.post("/api/query")
async def query(req: QueryReq):
    """流式问答接口：先返回 hits，再逐字流式输出，最后返回 citations。"""
    service = get_service()

    async def gen():
        # 1. 检索（同步，丢线程池防阻塞）
        hits = await asyncio.to_thread(service._hybrid_search, [req.question])
        hits_payload = []
        for i, h in enumerate(hits, 1):
            d = h.to_dict()
            d["n"] = i
            hits_payload.append(d)
        yield _sse({"type": "hits", "hits": hits_payload})

        if not hits:
            yield _sse({"type": "refuse", "message": "当前知识库没有找到相关内容。"})
            return

        # 2. 流式生成
        from code.week04.m2_kb.qa_chain import PROMPT

        prompt = PROMPT.format(context=service._build_context(hits), question=req.question)
        full_text = ""
        async for piece in service.llm.astream(
            [{"role": "user", "content": prompt}],
            temperature=service.temperature,
            max_tokens=600,
        ):
            full_text += piece
            yield _sse({"type": "delta", "text": piece})

        # 3. 引用
        citations = service._parse_citations(full_text, hits)
        yield _sse({"type": "done", "citations": [c.to_dict() for c in citations]})

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "m2_kb"}
