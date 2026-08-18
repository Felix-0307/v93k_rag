# rag_qa/core/reranker.py
# 懒加载式 BGE-Reranker 封装：用于检索后对 top-K 重排，按相关性分数取 top-M。
import os
from typing import TYPE_CHECKING

from base.config import config
from base.logger import logger

if TYPE_CHECKING:
    from langchain_core.documents import Document
    from sentence_transformers import CrossEncoder


class CrossEncoderReranker:
    """BGE-Reranker 懒加载封装。

    重 (~3GB 内存 + 数秒加载) ，所以首调 rerank() 时才实例化 CrossEncoder。
    FAQ 路径不调 rerank（retrieve_top_match 不走这里）。
    """

    def __init__(self):
        self._model: "CrossEncoder | None" = None

    def _ensure_loaded(self) -> "CrossEncoder":
        if self._model is not None:
            return self._model
        if not os.path.isdir(config.RERANK_MODEL_PATH):
            raise FileNotFoundError(
                f"Rerank 模型路径不存在: {config.RERANK_MODEL_PATH}，"
                f"请检查 config.ini [rerank] model_path 或下载 bge-reranker-large"
            )
        from sentence_transformers import CrossEncoder

        logger.info(f"加载 rerank 模型: {config.RERANK_MODEL_PATH} (device={config.RERANK_DEVICE})")
        self._model = CrossEncoder(
            config.RERANK_MODEL_PATH,
            device=config.RERANK_DEVICE,
        )
        return self._model

    def rerank(self, query: str, docs: list["Document"], top_m: int) -> list["Document"]:
        """对 docs 按与 query 的相关性重排，取 top_m。

        - docs ≤ top_m：直接返回（rerank 没意义）
        - docs 为空：返回空
        """
        if not docs or len(docs) <= top_m:
            return docs[:top_m]

        model = self._ensure_loaded()
        pairs = [[query, d.page_content] for d in docs]
        scores = model.predict(pairs, show_progress_bar=False)

        # 按 score 降序排列文档（稳定排序）
        ranked = [doc for _, doc in sorted(zip(scores, docs), key=lambda x: -x[0])]
        logger.info(
            f"rerank: {len(docs)} → top {top_m}, top_score={max(scores):.3f}"
        )
        return ranked[:top_m]


# 全局单例（懒加载：首调时实例化）
_reranker: "CrossEncoderReranker | None" = None


def get_reranker() -> CrossEncoderReranker:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoderReranker()
    return _reranker