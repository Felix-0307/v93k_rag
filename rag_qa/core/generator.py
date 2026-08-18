# rag_qa/core/generator.py
# 答案生成：基于检索上下文 + 问题，调用 LLM 生成最终回答。
from base.config import config
from base.logger import logger
from rag_qa.core.llm_client import get_llm_client
from rag_qa.core.prompts import RAGPrompts


class Generator:
    def __init__(self):
        self.llm = get_llm_client()
        self.prompt = RAGPrompts.rag_prompt()

    def generate(self, context: str, question: str) -> str:
        """带检索上下文生成答案。"""
        prompt_text = self.prompt.format(context=context, question=question)
        try:
            answer = self.llm.chat(prompt_text, temperature=config.LLM_TEMPERATURE)
            return answer.strip()
        except Exception as e:
            logger.error(f"答案生成失败: {e}")
            return "抱歉，生成答案时出现错误，请稍后重试。"

    def generate_stream(self, context: str, question: str):
        """流式版 generate：逐 chunk yield delta 文本。"""
        prompt_text = self.prompt.format(context=context, question=question)
        try:
            for delta in self.llm.chat_stream(prompt_text, temperature=config.LLM_TEMPERATURE):
                yield delta
        except Exception as e:
            logger.error(f"答案生成失败: {e}")
            yield "抱歉，生成答案时出现错误，请稍后重试。"

    def generate_with_history(
        self,
        summary: str | None,
        recent_turns: list[dict],
        context: str,
        question: str,
    ) -> str:
        """带会话历史生成答案：摘要 + 最近 3 轮 + 检索上下文 + 当前问题。"""
        # 把 recent 拼成可读文本
        if recent_turns:
            history_lines = []
            for i, t in enumerate(recent_turns, 1):
                history_lines.append(f"轮 {i}")
                history_lines.append(f"用户: {t['question']}")
                history_lines.append(f"助手: {t['answer'][:300]}{'...' if len(t['answer']) > 300 else ''}")
                history_lines.append("")
            history = "\n".join(history_lines)
        else:
            history = "（无）"

        prompt_text = RAGPrompts.with_history_prompt().format(
            summary=summary or "（无）",
            history=history,
            context=context,
            question=question,
        )
        try:
            answer = self.llm.chat(prompt_text, temperature=config.LLM_TEMPERATURE)
            return answer.strip()
        except Exception as e:
            logger.error(f"带历史的答案生成失败: {e}")
            return "抱歉，生成答案时出现错误，请稍后重试。"

    def generate_with_history_stream(
        self,
        summary: str | None,
        recent_turns: list[dict],
        context: str,
        question: str,
    ):
        """流式版 generate_with_history。"""
        if recent_turns:
            history_lines = []
            for i, t in enumerate(recent_turns, 1):
                history_lines.append(f"轮 {i}")
                history_lines.append(f"用户: {t['question']}")
                history_lines.append(f"助手: {t['answer'][:300]}{'...' if len(t['answer']) > 300 else ''}")
                history_lines.append("")
            history = "\n".join(history_lines)
        else:
            history = "（无）"
        prompt_text = RAGPrompts.with_history_prompt().format(
            summary=summary or "（无）",
            history=history,
            context=context,
            question=question,
        )
        try:
            for delta in self.llm.chat_stream(prompt_text, temperature=config.LLM_TEMPERATURE):
                yield delta
        except Exception as e:
            logger.error(f"带历史的答案生成失败: {e}")
            yield "抱歉，生成答案时出现错误，请稍后重试。"

    def summarize(self, existing_summary: str | None, new_turns: list[dict]) -> str:
        """压缩"旧摘要 + 新增轮"成新摘要。"""
        if not new_turns:
            return existing_summary or ""
        lines = []
        for t in new_turns:
            lines.append(f"用户: {t['question']}")
            lines.append(f"助手: {t['answer'][:200]}")
            lines.append("")
        new_turns_text = "\n".join(lines)
        prompt_text = RAGPrompts.summary_prompt().format(
            existing_summary=existing_summary or "（无）",
            new_turns=new_turns_text,
        )
        try:
            summary = self.llm.chat(prompt_text, temperature=config.LLM_TEMPERATURE)
            return summary.strip()
        except Exception as e:
            logger.error(f"摘要生成失败: {e}")
            # 降级：把 new_turns 简单拼接
            return (existing_summary or "") + "\n" + new_turns_text

    def generate_chitchat(self, question: str) -> str:
        """闲聊/无关问题：不检索，直接 LLM 回答。"""
        prompt_text = (
            f"你是 V93000（V93K）半导体测试机的知识库助手，也可以回答日常问题。\n"
            f"用户: {question}\n回答（中文，简洁友好）："
        )
        try:
            answer = self.llm.chat(prompt_text, temperature=config.LLM_TEMPERATURE)
            return answer.strip()
        except Exception as e:
            logger.error(f"闲聊生成失败: {e}")
            return "抱歉，服务暂时不可用，请稍后重试。"

    def generate_chitchat_stream(self, question: str):
        """流式版 generate_chitchat。"""
        prompt_text = (
            f"你是 V93000（V93K）半导体测试机的知识库助手，也可以回答日常问题。\n"
            f"用户: {question}\n回答（中文，简洁友好）："
        )
        try:
            for delta in self.llm.chat_stream(prompt_text, temperature=config.LLM_TEMPERATURE):
                yield delta
        except Exception as e:
            logger.error(f"闲聊生成失败: {e}")
            yield "抱歉，服务暂时不可用，请稍后重试。"
