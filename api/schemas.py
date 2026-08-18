# api/schemas.py
# FastAPI 请求/响应模型
from typing import Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="用户提问")
    source_filter: Optional[str] = Field(None, description="知识库过滤（文件 stem）")
    session_id: Optional[str] = Field(
        None,
        description="会话 ID（s_<uuid8>）；为空则后端自动生成并在响应里返回",
    )
    stream: bool = Field(
        False,
        description="是否 SSE 流式响应（默认 false，向后兼容）",
    )


class AskResponse(BaseModel):
    answer: str = Field(..., description="最终回答；FAQ 命中时为知识库原文片段")
    domain: str = Field(..., description="knowledge | chitchat | faq")
    strategy: str = Field(..., description="direct | hyde | subquery | backtracking")
    sources: list[str] = Field(default_factory=list, description="命中的知识库来源")
    elapsed_ms: float = Field(..., description="端到端耗时 ms")
    session_id: str = Field(..., description="会话 ID（前端存 localStorage 用于续会话）")


class RebuildResponse(BaseModel):
    indexed_docs: int
    child_chunks: int


class HealthResponse(BaseModel):
    status: str
    llm_model: str
    collection: str
    chunk_count: int
