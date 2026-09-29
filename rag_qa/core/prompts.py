# rag_qa/core/prompts.py
# 半导体工艺场景提示词
from langchain_core.prompts import PromptTemplate


class RAGPrompts:
    """集中管理 RAG 链路的提示词。"""

    @staticmethod
    def rag_prompt() -> PromptTemplate:
        """最终生成答案：严格基于检索上下文。"""
        return PromptTemplate(
            template="""你是半导体工艺智能问答助手。只能依据检索上下文回答。
请严格基于下面提供的【上下文】回答，若上下文不足以回答，
如实说明"根据当前知识库，信息不足"，不要编造工艺参数、设备规格、控制限或文档版本。
回答中引用上下文已有的资料标题和文档编号；涉及停机、放行、参数修改或 PM 时，提示用户核对厂内最新受控文件并履行审批。

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
            template="""你是半导体工艺知识库的路由器。对用户输入判断，只返回 JSON，不要多余文字：
{{"domain": "<knowledge|chitchat>", "area": "<process|equipment|yield|cleanroom|quality>", "strategy": "<direct|hyde|subquery|backtracking>"}}

用户问题已经过独立 FAQ 库检测且未命中。这里只判断知识问答或闲聊。

- domain:
  * knowledge: 与晶圆制造工艺、设备、良率、洁净室或制程质量有关的问题。
  * chitchat: 问候、闲聊、与半导体工艺无关。
- area: process=工艺整合；equipment=设备维护与PM；yield=良率与WAT；cleanroom=洁净室与EHS；quality=SPC、OOC、OOS与量测。
- strategy（仅 domain=knowledge 时需要选，其它场景固定 direct）:
  * direct: 明确事实问题（如"SPC OOC 的定义是什么？"）
  * hyde: 宽泛研究问题（如"如何改善金属层良率？"）
  * subquery: 多因素排查（如"刻蚀腔体 particle 超标怎么排查？"）
  * backtracking: 依赖上文的追问（如"那过刻蚀量呢？"）

用户输入: {query}
JSON:""",
            input_variables=["query"],
        )

    @staticmethod
    def hyde_prompt() -> PromptTemplate:
        """生成假设答案用于检索。"""
        return PromptTemplate(
            template="""你是半导体工艺知识检索助手。请针对下面的问题写一段假设答案作为检索线索，不要编造具体产线参数（100-200 字）：

问题: {query}
假设答案:""",
            input_variables=["query"],
        )

    @staticmethod
    def subquery_prompt() -> PromptTemplate:
        """拆分子查询。"""
        return PromptTemplate(
            template="""把下面的半导体工艺问题拆分成多个独立的子问题，每行一个，覆盖排查流程、设备、工艺和受控规范，以便分别检索：

问题: {query}
子问题:""",
            input_variables=["query"],
        )

    @staticmethod
    def backtracking_prompt() -> PromptTemplate:
        """回溯简化问题。"""
        return PromptTemplate(
            template="""将下面的半导体工艺追问改写为独立可检索的问题，保留已经出现的核心技术词，不补造设备或参数：

原问题: {query}
简化问题:""",
            input_variables=["query"],
        )

    @staticmethod
    def with_history_prompt() -> PromptTemplate:
        """带会话历史的问答 prompt：摘要 + 最近 3 轮 + 当前问题。"""
        return PromptTemplate(
            template="""你是半导体工艺智能问答助手。只能依据检索上下文回答。
请严格基于下面【上下文】回答，并参考【对话历史】理解当前问题。如果上下文不足以回答，
如实说明"根据当前知识库，信息不足"，不要编造工艺参数、设备规格、控制限或文档版本。
回答中引用上下文已有的资料标题和文档编号；涉及停机、放行、参数修改或 PM 时，提示用户核对厂内最新受控文件并履行审批。

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
