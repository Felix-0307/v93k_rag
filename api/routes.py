# api/routes.py
# FastAPI 路由：/api/ask /api/rebuild_index /api/health
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.schemas import AskRequest, AskResponse, HealthResponse, RebuildResponse
from base.config import config
from base.logger import logger
from rag_qa.chat_history import new_session_id
from rag_qa.core.document_processor import load_documents, process_documents
from rag_qa.core.rag_system import get_rag_system
from rag_qa.core.vector_store import get_vector_store

router = APIRouter()


def _sse_format(event: dict) -> str:
    """SSE 单事件格式化：`data: <json>\\n\\n`。"""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    sid = req.session_id or new_session_id()

    # 流式分支：直接返回 StreamingResponse（FastAPI 对 Response 子类跳过 response_model 校验）
    if req.stream:
        system = get_rag_system()

        def event_stream():
            try:
                # 首事件携带 session_id（前端首次访问时持久化）
                yield _sse_format({"type": "meta", "domain": "_init", "strategy": "_init", "session_id": sid})
                for event in system.ask_stream(
                    req.question, source_filter=req.source_filter, session_id=sid,
                ):
                    yield _sse_format(event)
            except Exception as e:
                logger.exception("SSE /api/ask 失败: %s", e)
                yield _sse_format({"type": "error", "message": str(e)})

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用 nginx 等反向代理缓冲
            },
        )

    # 非流式分支（保持原行为，向后兼容）
    try:
        system = get_rag_system()
        result = system.ask(
            req.question,
            source_filter=req.source_filter,
            session_id=sid,
        )
        result["session_id"] = sid
        return AskResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("/api/ask failed: %s", e)
        raise HTTPException(status_code=500, detail=f"问答服务异常：{type(e).__name__}")


@router.post("/rebuild_index", response_model=RebuildResponse)
def rebuild_index():
    try:
        children, parents = process_documents(config.DATA_DIR)
        store = get_vector_store()
        store.clear()
        store.add_documents(children, parents=parents)
        docs = load_documents(config.DATA_DIR)
        logger.info(f"索引重建完成: {len(docs)} 文档, {len(children)} 子块, {len(parents)} 父块")
        return RebuildResponse(indexed_docs=len(docs), child_chunks=len(children))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("/api/rebuild_index failed: %s", e)
        raise HTTPException(status_code=500, detail=f"索引重建异常：{type(e).__name__}")


@router.get("/health", response_model=HealthResponse)
def health():
    store = get_vector_store()
    return HealthResponse(
        status="ok",
        llm_model=config.LLM_MODEL,
        collection=config.CHROMA_COLLECTION_NAME,
        chunk_count=store.children_col.count(),
    )
