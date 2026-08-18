# rag_qa/core/prompts.py
# 全部 prompt 模板（V93K 语境）
from langchain_core.prompts import PromptTemplate


class RAGPrompts:
    """集中管理 RAG 链路的提示词。"""

    @staticmethod
    def rag_prompt() -> PromptTemplate:
        """最终生成答案：严格基于检索上下文。"""
        return PromptTemplate(
            template="""你是 V93000（V93K）半导体测试机的知识库助手。
请严格基于下面提供的【上下文】回答，若上下文不足以回答，
如实说明"根据当前知识库，信息不足"，不要编造。

【上下文】
{context}

【问题】
{question}

回答（中文，专业、准确、分点清晰）：""",
            input_variables=["context", "question"],
        )

    @staticmethod
    def strategy_prompt() -> PromptTemplate:
        """一次调用完成领域分类 + 检索策略选择，只输出 JSON。"""
        return PromptTemplate(
            template="""你是 V93000 半导体测试机知识库的路由器。对用户输入判断，只返回 JSON，不要多余文字：
{{"domain": "<knowledge|chitchat|faq>", "strategy": "<direct|hyde|subquery|backtracking>"}}

- domain:
  * faq: 高频简短的事实性问题，期望知识库里有对应原文片段能直接命中（如"STIL 是什么？"、"DPS 板卡的作用？"、"什么是 testmethod？"）。命中后跳过 LLM 生成，直接返回知识库原文。
  * knowledge: 复杂、需要多步推理或没有固定答案的问题，需要检索 + LLM 整合（如"如何优化测试流程？"、"良率突然下降怎么排查？"）。
  * chitchat: 问候、闲聊、与半导体测试无关。
- strategy（仅 domain=knowledge 时需要选，其它场景固定 direct）:
  * direct: 问题明确具体，直接查库即可（如"DPS 板卡的作用？"）
  * hyde: 问题抽象、字面难以命中（如"如何提升量产测试效率？"）
  * subquery: 涉及多个实体或比较（如"比较 FunctionalTest 和 DC_Test 的适用场景"）
  * backtracking: 问题复杂需先简化（如"100 条引脚都要做接触测试，怎么批量设置？"）

用户输入: {query}
JSON:""",
            input_variables=["query"],
        )

    @staticmethod
    def hyde_prompt() -> PromptTemplate:
        """生成假设答案用于检索。"""
        return PromptTemplate(
            template="""你是 V93000 半导体测试机专家。请针对下面的问题，用专业知识写一段可能的答案（不需要完全准确，作为检索线索即可，100-200 字）：

问题: {query}
假设答案:""",
            input_variables=["query"],
        )

    @staticmethod
    def subquery_prompt() -> PromptTemplate:
        """拆分子查询。"""
        return PromptTemplate(
            template="""把下面的 V93K 领域问题拆分成多个独立的子问题，每行一个，子问题之间信息互不重叠，以便分别检索：

问题: {query}
子问题:""",
            input_variables=["query"],
        )

    @staticmethod
    def backtracking_prompt() -> PromptTemplate:
        """回溯简化问题。"""
        return PromptTemplate(
            template="""下面的 V93K 领域问题过于复杂。请把它改写成一个更简单、更聚焦基础概念的问题，保留核心技术词：

原问题: {query}
简化问题:""",
            input_variables=["query"],
        )

    @staticmethod
    def with_history_prompt() -> PromptTemplate:
        """带会话历史的问答 prompt：摘要 + 最近 3 轮 + 当前问题。"""
        return PromptTemplate(
            template="""你是 V93000（V93K）半导体测试机的知识库助手。
请严格基于下面【上下文】回答，并参考【对话历史】理解当前问题。如果上下文不足以回答，
如实说明"根据当前知识库，信息不足"，不要编造。

【对话摘要（更早的对话）】
{summary}

【最近对话】
{history}

【上下文】
{context}

【当前问题】
{question}

回答（中文，专业、准确、分点清晰）：""",
            input_variables=["summary", "history", "context", "question"],
        )

    @staticmethod
    def summary_prompt() -> PromptTemplate:
        """把"旧摘要 + 新增轮"压缩成新摘要。"""
        return PromptTemplate(
            template="""你是会话摘要助手。已有摘要和新增对话轮，请合并生成新的简洁摘要（不超过 200 字）。
摘要应保留关键概念、数字、专有名词、上下文线索，便于后续对话引用。

【旧摘要】
{existing_summary}

【新增对话轮】
{new_turns}

【新摘要】""",
            input_variables=["existing_summary", "new_turns"],
        )
