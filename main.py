# main.py
# FastAPI 入口：uvicorn 启动，lifespan 内完成模型/向量库初始化。
# 启动:  D:\Anaconda\envs\edu_rag\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.routes import router
from base.config import config
from base.logger import logger
from rag_qa.core.embedding import get_embedding_model
from rag_qa.core.reranker import get_reranker
from rag_qa.core.vector_store import get_vector_store
from rag_qa.core.rag_system import get_rag_system
from rag_qa.chat_history import get_chat_history


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SemiconRAG 服务启动中...")
    logger.info(f"加载 embedding 模型: {config.EMBEDDING_MODEL_DIR}")
    get_embedding_model()          # 预热 bge-m3
    # 预热 rerank 模型（避免首次 /api/ask 时 10s 加载阻塞响应）
    if config.RERANK_ENABLED:
        try:
            get_reranker()._ensure_loaded()
            logger.info("rerank 模型预热完成")
        except Exception as e:
            logger.warning(f"rerank 预热失败（首次 /api/ask 时会重试）: {e}")
    store = get_vector_store()     # 连接 Chroma + 恢复稀疏索引
    logger.info(
        f"服务就绪: llm={config.LLM_MODEL}, collection={config.CHROMA_COLLECTION_NAME}, "
        f"子块数={store.children_col.count()}, 父块数={store.parents_col.count()}"
    )
    # 预热 RAG（含独立 FAQ 问题向量）与会话历史，消除首个请求的补初始化延迟
    try:
        get_rag_system()
        get_chat_history()
        logger.info("RAG 链路、FAQ 问答库与会话历史预热完成")
    except Exception as e:
        logger.warning(f"RAG 链路/会话历史预热失败（首个请求时会重试）: {e}")
    yield
    logger.info("SemiconRAG 服务已关闭")


app = FastAPI(title="SemiconRAG 半导体工艺智能问答", lifespan=lifespan)
app.include_router(router, prefix="/api")

# CORS：允许任意来源（本地开发场景；生产环境应改为白名单）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 托管前端静态文件
WEB_DIR = Path(__file__).parent / "web_ui" / "dist"
if WEB_DIR.exists():
    @app.get("/")
    async def serve_index():
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    logger.info(f"前端静态文件托管: {WEB_DIR}")
