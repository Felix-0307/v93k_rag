# rag_qa/core/retriever.py
# 检索编排：按 query_router 选择的策略生成检索 query，
# 混合检索子块 → 还原父块 → 截取前 candidate_m 个。
from langchain_core.documents import Document

from base.config import config
from base.logger import logger
from rag_qa.core.llm_client import get_llm_client
from rag_qa.core.prompts import RAGPrompts
from rag_qa.core.vector_store import get_vector_store


class Retriever:
    def __init__(self):
        self.llm = get_llm_client()
        self.vector_store = get_vector_store()

    def retrieve(self, query: str, strategy: str = "direct",
                 source_filter: str | None = None,
                 area_filter: str | None = None) -> list[Document]:
        """按策略检索，返回最终父块列表（最多 candidate_m 个）。"""
        k = config.RETRIEVAL_K

        if strategy == "hyde":
            search_queries = [self._generate_hyde_query(query)]
        elif strategy == "subquery":
            search_queries = self._generate_subqueries(query)
        elif strategy == "backtracking":
            search_queries = [self._generate_backtracking_query(query)]
        else:  # direct
            search_queries = [query]

        # 逐 query 检索子块并合并（按 id 去重）
        merged_children = {}
        for sq in search_queries:
            hits = self.vector_store.search_children(
                sq, top_k=k, source_filter=source_filter, area_filter=area_filter
            )
            for child in hits:
                merged_children.setdefault(child.metadata["id"], child)
            logger.info(f"检索 query[{sq[:40]}...] 命中 {len(hits)} 个子块")

        # 还原父块 + rerank（rerank 关闭时退化为截取 top_m）
        parent_docs = self.vector_store.restore_and_rerank_parents(
            list(merged_children.values()), query=query
        )
        logger.info(f"还原 {len(parent_docs)} 个父块（已 rerank 或截取）")
        return parent_docs

    def retrieve_top_match(self, query: str,
                           source_filter: str | None = None
                           ) -> tuple[Document | None, float]:
        """取知识库最匹配父块及距离；兼容旧调用，独立 FAQ 不再使用此方法。"""
        hits = self.vector_store.search_children(
            query, top_k=1, source_filter=source_filter
        )
        if not hits:
            return None, float("inf")
        distance = hits[0].metadata.get("_distance", float("inf"))
        parent_docs = self.vector_store.restore_parent_docs(hits)
        if not parent_docs:
            return None, float("inf")
        return parent_docs[0], float(distance)

    # ---------- 策略辅助：LLM 改写检索 query ----------

    def _generate_hyde_query(self, query: str) -> str:
        try:
            return self.llm.chat(
                RAGPrompts.hyde_prompt().format(query=query),
                temperature=config.STRATEGY_TEMPERATURE,
            )
        except Exception as e:
            logger.error(f"HyDE 生成失败，退回原 query: {e}")
            return query

    def _generate_subqueries(self, query: str) -> list[str]:
        try:
            raw = self.llm.chat(
                RAGPrompts.subquery_prompt().format(query=query),
                temperature=config.STRATEGY_TEMPERATURE,
            )
            # 清洗：去数字编号、中英文 bullet 前缀（- * •）、首尾空白
            import re
            subs = []
            for line in raw.splitlines():
                s = line.strip()
                if not s:
                    continue
                # 去前缀：可选空白 + 数字 + 点/顿号 + 可选 bullet 字符
                s = re.sub(r"^\s*(?:[\-\*•·]|\d+[.、\)）])\s*", "", s).strip()
                if s:
                    subs.append(s)
            return subs[:4] if subs else [query]
        except Exception as e:
            logger.error(f"子查询拆分失败，退回原 query: {e}")
            return [query]

    def _generate_backtracking_query(self, query: str) -> str:
        try:
            return self.llm.chat(
                RAGPrompts.backtracking_prompt().format(query=query),
                temperature=config.STRATEGY_TEMPERATURE,
            )
        except Exception as e:
            logger.error(f"回溯简化失败，退回原 query: {e}")
            return query
