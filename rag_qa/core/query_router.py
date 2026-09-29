# rag_qa/core/query_router.py
# 查询路由：一次 LLM 调用完成「领域分类 + 检索策略选择」，返回结构化 JSON。
from base.config import config
from base.logger import logger
from rag_qa.core.llm_client import get_llm_client
from rag_qa.core.prompts import RAGPrompts

# 合法取值（防 LLM 输出越界）
_VALID_DOMAINS = {"knowledge", "chitchat"}
_VALID_STRATEGIES = {"direct", "hyde", "subquery", "backtracking"}
_VALID_AREAS = {"process", "equipment", "yield", "cleanroom", "quality"}
_FALLBACK = {"domain": "knowledge", "area": "process", "strategy": "direct"}


class QueryRouter:
    """FAQ 未命中后，判断是否需要检索知识库，并选择检索策略。"""

    def __init__(self):
        self.llm = get_llm_client()
        self.prompt = RAGPrompts.strategy_prompt()

    def analyze(self, query: str) -> dict:
        """返回 {domain, strategy}，异常时兜底 direct 保证链路不中断。"""
        try:
            result = self.llm.chat_json(
                self.prompt.format(query=query),
                temperature=config.STRATEGY_TEMPERATURE,
                fallback=_FALLBACK,
            )
        except Exception as e:
            logger.error(f"QueryRouter 调用失败: {e}")
            return dict(_FALLBACK)

        domain = result.get("domain", "knowledge")
        strategy = result.get("strategy", "direct")
        area = result.get("area", "process")
        if domain not in _VALID_DOMAINS:
            domain = "knowledge"
        if strategy not in _VALID_STRATEGIES:
            strategy = "direct"
        if area not in _VALID_AREAS:
            area = "process"
        # 闲聊不走复杂检索策略，FAQ 已在路由前完成。
        if domain == "chitchat":
            strategy = "direct"

        logger.info(f"路由结果: domain={domain}, area={area}, strategy={strategy}")
        return {"domain": domain, "area": area, "strategy": strategy}
