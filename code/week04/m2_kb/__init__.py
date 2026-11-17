"""M2 知识库问答：文档 → 块 → 向量 → 可溯源回答。

Day 19 产出：索引构建 + QAService + Badcase 工作流
Day 20 产出：FastAPI SSE 后端 + 前端

用法：
    python -m code.week04.m2_kb.qa_chain "问题"
    python -m code.week04.m2_kb.eval_manual
    uvicorn code.week04.m2_kb.web.app:app --reload
"""
