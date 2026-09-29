# rag_qa/core/rag_system.py
# RAG 门面：先匹配独立 FAQ，未命中才进入 query_router → retriever → generator。
# 接入会话历史：knowledge/chitchat 路径拼摘要+最近3轮给 LLM；FAQ 不调 LLM。
# 摘要重建放后台线程，不阻塞主响应。
import threading
import time

from base.logger import logger
from rag_qa.chat_history import get_chat_history
from rag_qa.core.faq_store import get_faq_store
from rag_qa.core.generator import Generator
from rag_qa.core.query_router import QueryRouter
from rag_qa.core.retriever import Retriever


def _build_summary_async(session_id: str, history: "ChatHistory", generator: Generator) -> None:
    """后台线程：调 LLM 重建摘要并 upsert。失败不阻塞（daemon 线程）。"""
    try:
        old_turns = history.get_old_turns(session_id, n=3)
        if not old_turns:
            return
        old_summary = history.get_summary(session_id) or ""
        new_summary = generator.summarize(old_summary, old_turns)
        history.update_summary(
            session_id=session_id,
            summary=new_summary,
            turn_count=3 + len(old_turns),
        )
        logger.info(
            f"[bg] summaries 表更新: session={session_id}, covered={3 + len(old_turns)} turns"
        )
    except Exception as e:
        logger.error(f"[bg] 摘要重建失败: {e}")


class RAGSystem:
    """对外统一问答入口：ask(question, session_id) -> dict"""

    def __init__(self):
        self.faq_store = get_faq_store()
        self.query_router = QueryRouter()
        self.retriever = Retriever()
        self.generator = Generator()
        self.history = get_chat_history()  # 懒加载 + 自动建库

    def _resolve_route(self, question: str, source_filter: str | None):
        """FAQ 命中时直接确定路径，不调用意图识别 LLM。"""
        try:
            match = self.faq_store.match(question, source_filter=source_filter)
        except Exception as e:
            logger.warning(f"FAQ 检测失败，继续常规问答: {e}")
            match = None
        if match is not None:
            logger.info(f"FAQ hit: id={match.entry.id}, similarity={match.similarity:.4f}")
            return {"domain": "faq", "strategy": "direct"}, match
        return self.query_router.analyze(question), None

    def ask(
        self,
        question: str,
        source_filter: str | None = None,
        session_id: str | None = None,
    ) -> dict:
        start = time.time()
        route, faq_match = self._resolve_route(question, source_filter)
        domain, strategy = route["domain"], route["strategy"]

        sources: list[str] = []
        if faq_match is not None:
            answer = faq_match.entry.answer
            sources = [faq_match.entry.source]
        elif domain == "chitchat":
            # 闲聊也走历史路径（用户可能在续对话）
            ctx = self.history.get_context(session_id, n=3) if session_id else None
            if ctx and ctx["has_history"]:
                answer = self._chitchat_with_history(question, ctx)
            else:
                answer = self.generator.generate_chitchat(question)
        else:  # knowledge
            sources, answer = self._knowledge_path(
                question, strategy=strategy, source_filter=source_filter,
                session_id=session_id, area_filter=route.get("area"),
            )

        elapsed_ms = round((time.time() - start) * 1000, 1)

        # 落库 + 摘要重建（异常不阻塞主流程）
        if session_id:
            self._persist_and_summarize(
                session_id, question, answer, domain, strategy, sources, elapsed_ms
            )

        return {
            "answer": answer,
            "domain": domain,
            "strategy": strategy,
            "sources": sources,
            "elapsed_ms": elapsed_ms,
        }

    def ask_stream(
        self,
        question: str,
        source_filter: str | None = None,
        session_id: str | None = None,
    ):
        """流式版 ask()：yield 字典事件序列，前端用 SSE 消费。

        事件类型：
          {"type": "meta", "domain": ..., "strategy": ...}
          {"type": "chunk", "text": "..."}    # 多次
          {"type": "done", "sources": [...], "elapsed_ms": ..., "domain": ..., "strategy": ...}
        """
        start = time.time()
        route, faq_match = self._resolve_route(question, source_filter)
        domain, strategy = route["domain"], route["strategy"]

        # 路由信息先发（前端可即时更新标签）
        yield {"type": "meta", "domain": domain, "strategy": strategy}

        sources: list[str] = []
        answer_chunks: list[str] = []

        def _record(delta: str):
            answer_chunks.append(delta)

        if faq_match is not None:
            answer = faq_match.entry.answer
            sources = [faq_match.entry.source]
            _record(answer)
            yield {"type": "chunk", "text": answer}
        elif domain == "chitchat":
            ctx = self.history.get_context(session_id, n=3) if session_id else None
            if ctx and ctx["has_history"]:
                history_lines = []
                if ctx["summary"]:
                    history_lines.append(f"[历史摘要] {ctx['summary']}")
                for i, t in enumerate(ctx["recent"], 1):
                    history_lines.append(f"[轮 {i}] 用户: {t['question']}")
                    history_lines.append(f"[轮 {i}] 助手: {t['answer'][:200]}")
                history_text = "\n".join(history_lines) + "\n"
                combined = history_text + f"用户最新问题: {question}"
                for delta in self.generator.generate_chitchat_stream(combined):
                    _record(delta)
                    yield {"type": "chunk", "text": delta}
            else:
                for delta in self.generator.generate_chitchat_stream(question):
                    _record(delta)
                    yield {"type": "chunk", "text": delta}
        else:  # knowledge
            for delta, srcs in self._knowledge_stream(
                question, strategy=strategy, source_filter=source_filter,
                session_id=session_id, area_filter=route.get("area"),
            ):
                if srcs is not None:
                    sources = srcs
                else:
                    _record(delta)
                    yield {"type": "chunk", "text": delta}

        elapsed_ms = round((time.time() - start) * 1000, 1)
        full_answer = "".join(answer_chunks)

        # 落库 + 摘要重建（异常不阻塞主流程）
        if session_id:
            try:
                self._persist_and_summarize(
                    session_id, question, full_answer, domain, strategy, sources, elapsed_ms,
                )
            except Exception as e:
                logger.error(f"落库失败（已忽略）: {e}")

        yield {
            "type": "done",
            "domain": domain,
            "strategy": strategy,
            "sources": sources,
            "elapsed_ms": elapsed_ms,
        }

    def _knowledge_stream(
        self,
        question: str,
        strategy: str,
        source_filter: str | None,
        session_id: str | None,
        area_filter: str | None = None,
    ):
        """Knowledge 路径流式生成器：yield (delta_text | None, sources | None)。

        约定：
          - (delta, None)            → 流式文本 chunk
          - ("", sources_list)       → 末尾一次性返回 sources（用于最终 done）
        """
        parent_docs = self.retriever.retrieve(
            question, strategy=strategy, source_filter=source_filter,
            area_filter=None if source_filter else area_filter,
        )
        sources = [d.metadata.get("source", "") for d in parent_docs]
        context = "\n\n---\n\n".join(
            f"[资料来源: {d.metadata.get('source', '未知')}]\n{d.page_content}"
            for d in parent_docs
        )
        if not context:
            msg = (
                "抱歉，当前知识库中没有与该问题相关的内容，"
                "无法提供准确答案。请尝试换一种问法，或确认问题是否在已发布范围内。"
            )
            yield msg, None
            yield "", sources
            return

        if session_id:
            ctx = self.history.get_context(session_id, n=3)
            if ctx["has_history"]:
                gen = self.generator.generate_with_history_stream(
                    summary=ctx["summary"],
                    recent_turns=ctx["recent"],
                    context=context,
                    question=question,
                )
            else:
                gen = self.generator.generate_stream(context, question)
        else:
            gen = self.generator.generate_stream(context, question)

        for delta in gen:
            yield delta, None
        yield "", sources

    # ---------- 路径辅助 ----------
    def _knowledge_path(
        self,
        question: str,
        strategy: str,
        source_filter: str | None,
        session_id: str | None,
        area_filter: str | None = None,
    ) -> tuple[list[str], str]:
        """Knowledge 路径：检索 + 拼上下文 + 调 LLM（含会话历史）。"""
        parent_docs = self.retriever.retrieve(
            question, strategy=strategy, source_filter=source_filter,
            area_filter=None if source_filter else area_filter,
        )
        sources = [d.metadata.get("source", "") for d in parent_docs]
        context = "\n\n---\n\n".join(
            f"[资料来源: {d.metadata.get('source', '未知')}]\n{d.page_content}"
            for d in parent_docs
        )
        if not context:
            return sources, (
                "抱歉，当前知识库中没有与该问题相关的内容，"
                "无法提供准确答案。请尝试换一种问法，或确认问题是否在已发布范围内。"
            )

        # 拼会话上下文
        if session_id:
            ctx = self.history.get_context(session_id, n=3)
            if ctx["has_history"]:
                answer = self.generator.generate_with_history(
                    summary=ctx["summary"],
                    recent_turns=ctx["recent"],
                    context=context,
                    question=question,
                )
            else:
                answer = self.generator.generate(context, question)
        else:
            answer = self.generator.generate(context, question)
        return sources, answer

    def _chitchat_with_history(self, question: str, ctx: dict) -> str:
        """闲聊 + 历史：把历史嵌进 user prompt 调 LLM。"""
        # 简化：把 history 当作"用户上文" 拼到问题前
        history_lines = []
        if ctx["summary"]:
            history_lines.append(f"[历史摘要] {ctx['summary']}")
        for i, t in enumerate(ctx["recent"], 1):
            history_lines.append(f"[轮 {i}] 用户: {t['question']}")
            history_lines.append(f"[轮 {i}] 助手: {t['answer'][:200]}")
        history_text = "\n".join(history_lines) + "\n"
        combined = history_text + f"用户最新问题: {question}"
        return self.generator.generate_chitchat(combined)

    def _persist_and_summarize(
        self, session_id, question, answer, domain, strategy, sources, elapsed_ms
    ):
        """存本轮问答（同步）+ 摘要重建（后台线程，不阻塞响应）。"""
        # 同步：写 sessions 表（~10ms，必须在响应前完成，保证后续读得到）
        try:
            self.history.save_turn(
                session_id=session_id,
                question=question,
                answer=answer,
                domain=domain,
                strategy=strategy,
                sources=sources,
                elapsed_ms=elapsed_ms,
            )
            logger.info(f"sessions 表写入: session={session_id}")
        except Exception as e:
            logger.error(f"sessions 写入失败: {e}")
            return  # 写库失败就别起后台线程了

        # FAQ 快速路径只保存问答，不发起任何 LLM 调用。
        # 后续非 FAQ 对话更新摘要时，会自然纳入这些已保存的旧轮次。
        if domain == "faq":
            return

        # 后台：摘要重建（~10s，不阻塞响应）
        # daemon=True：主进程退出时自动结束；不阻塞 shutdown
        # 注意：不是 thread-safe per session（快速连发可能丢更新），但单用户感知不到
        t = threading.Thread(
            target=_build_summary_async,
            args=(session_id, self.history, self.generator),
            daemon=True,
        )
        t.start()


# 全局单例（懒加载）
_rag_system = None


def get_rag_system() -> RAGSystem:
    global _rag_system
    if _rag_system is None:
        _rag_system = RAGSystem()
    return _rag_system
