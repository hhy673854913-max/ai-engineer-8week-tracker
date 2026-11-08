# Day 34 · FastAPI 服务化：路由、SSE 与错误处理

> W7 · 周四 ｜ 5h ｜ 产出 `code/week07/api/main.py` ｜ [Day 33](day-33.md) · [Day 35](day-35.md)

**今日目标**
- 把 M2 从"本地脚本"变成"HTTP 服务"：路由、依赖注入、流式、CORS、错误码
- 处理 FastAPI 里最容易踩的三个坑：阻塞事件循环、SSE 缓冲、异常泄露
- 用 OpenAPI 文档让前端能自助联调

**验收**：`uvicorn week07.api.main:app --reload` 后，`/docs` 可调试，`POST /api/query` 流式返回。

---

## 上午 09:00–11:30 · 理论

### 1. 接口设计

```http
GET  /healthz                    → {"ok": true, "version": "1.0.0"}
GET  /api/config                 → 当前检索配置（只读，便于排障）
POST /api/query                  → SSE 流式回答
POST /api/query/sync             → 非流式（给脚本/测试用）
GET  /api/docs/{doc_id}          → 读取原文（引用点击）
```

三条设计原则：
1. **健康检查必须有**（部署平台靠它判断存活）
2. **流式与非流式都要有**（前端用流式，测试用同步）
3. **配置可读**（线上"为什么答得不一样"第一件事就是看配置）

### 2. 依赖注入：把重资源放 lifespan

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.service = QAService.load(settings)
    yield
    app.state.service.close()

app = FastAPI(lifespan=lifespan)

def get_service(request: Request) -> QAService:
    return request.app.state.service
```

**不要在路由里 `QAService()`**：每次请求都重新加载索引，1 秒起步，还会打爆内存。

### 3. 三个必踩的坑

**坑 1：阻塞事件循环**

```python
# ❌ 同步检索直接在 async 路由里跑，会阻塞所有并发请求
@app.post("/api/query")
async def query(req: QueryReq):
    hits = service.retrieve(req.question)   # 同步阻塞！

# ✅ 丢到线程池
hits = await asyncio.to_thread(service.retrieve, req.question)
```

**坑 2：SSE 被中间件缓冲**

- Nginx 要关 `proxy_buffering`
- 响应头加 `X-Accel-Buffering: no`
- 每个事件后 `yield` 要 flush

```python
def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
```

**坑 3：异常泄露**

```python
@app.exception_handler(Exception)
async def on_error(request: Request, exc: Exception):
    trace_id = getattr(request.state, "trace_id", "-")
    log.exception("unhandled error trace=%s", trace_id)
    return JSONResponse(status_code=500, content={"error": "internal_error", "trace_id": trace_id})
```

**返回 trace_id 不返回堆栈**：用户能报障，你不泄露内部结构。

### 4. 请求模型与校验

```python
class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    session_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=10)
```

Pydantic 自动返回 422 与字段级错误，前端能直接展示。**别自己手写 if 校验**。

### 5. 流式的正确收尾

```python
async def stream():
    try:
        yield sse({"type": "start", "trace_id": trace_id})
        async for piece in service.stream_answer(...):
            yield sse({"type": "delta", "text": piece})
        yield sse({"type": "done", "citations": [...]})
    except asyncio.CancelledError:
        log.info("client disconnected trace=%s", trace_id)
        raise
    except Exception as e:
        yield sse({"type": "error", "message": "生成失败，请重试", "trace_id": trace_id})
```

**客户端断开是常态**（用户切页），`CancelledError` 要单独处理，别当成错误上报。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 搭骨架（60 min）

```python
# code/week07/api/main.py
app = FastAPI(title="M2 KB QA", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["*"], allow_headers=["*"])

@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "version": app.version}

@app.post("/api/query")
async def query(req: QueryRequest, service: QAService = Depends(get_service)):
    ...
```

### 任务 2 · 流式接口（70 min）

```python
@app.post("/api/query")
async def query(req: QueryRequest, request: Request, service=Depends(get_service)):
    trace_id = request.headers.get("x-trace-id") or new_id()
    request.state.trace_id = trace_id

    async def gen():
        yield sse({"type": "start", "trace_id": trace_id})
        hits = await asyncio.to_thread(service.retrieve, req.question, req.top_k or 5)
        yield sse({"type": "hits", "hits": [h.to_dict() for h in hits]})
        async for piece in service.stream(req.question, hits):
            yield sse({"type": "delta", "text": piece})
        yield sse({"type": "done"})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})
```

### 任务 3 · 错误与限流（40 min）

- 全局异常处理器（返回 trace_id）
- 简单限流：`slowapi` 或内存计数器（每 IP 每分钟 20 次）
- 请求体大小限制（防超大 prompt 打爆）

### 任务 4 · 用 `/docs` 自测 + 写 API README（30 min）

打开 `http://127.0.0.1:8000/docs`，逐个接口点一遍。
README 里写清：启动命令、环境变量、接口示例（curl）、错误码表。

---

## 代码思考（写进 `logs/day-34.md`）

1. 为什么同步检索必须 `to_thread`？如果 QPS 是 1，还有必要吗？（提示：并发请求）
2. SSE 被 Nginx 缓冲的表现是什么？怎么在不改 Nginx 的情况下从应用层缓解？
3. 客户端断开时，后端还在生成，token 还在烧——你怎么尽早止损？
4. 限流按 IP 还是按用户？如果用户都在同一个公司出口 IP 后面会怎样？
5. 健康检查只返回 `{"ok": true}` 有什么问题？更好的健康检查应该查什么？

## 复盘清单

- [ ] `/docs` 可调试，三个接口都通
- [ ] 流式接口在浏览器 `EventSource` 或 curl 里能看到逐条 data
- [ ] 异常返回 trace_id 不泄露堆栈
- [ ] API README 写完
- [ ] commit：`day34: FastAPI 服务化（SSE + 异常 + 限流）`
