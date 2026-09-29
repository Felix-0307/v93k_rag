# rag_qa/core/vector_store.py
# 向量存储：两个 Chroma collection：
#   - children（v93k_kb）：存子块稠密向量 + 引用 parent_id
#   - parents（v93k_kb_parents）：存父块原文，文档还原时按 id 批量取
# 稀疏检索：bge-m3 的 lexical_weights 在内存中维护，按 dot product 打分。
# 两路结果用 RRF（Reciprocal Rank Fusion）融合。
from collections import defaultdict

import chromadb
from langchain_core.documents import Document

from base.config import config
from base.logger import logger
from rag_qa.core.embedding import get_embedding_model
from rag_qa.core.reranker import get_reranker

# RRF 常数：rank 得分 = 1 / (k + rank)，rank 从 1 开始
_RRF_K = 60


class SparseIndex:
    """内存稀疏索引：基于 bge-m3 lexical_weights 的 dot product 检索。"""

    def __init__(self):
        self.ids = []                # 与 doc_weights 同序的 Chroma id
        self.doc_weights = []        # [{token: weight}, ...] 来自 bge-m3
        self.doc_freq = defaultdict(int)  # token -> 出现该词的文档数
        self.sources = []            # 每篇文档的 source（用于过滤）
        self.areas = []              # 五类半导体工艺知识领域

    def add_documents(self, children: list[Document], ids: list[str],
                      sparse_weights: list[dict] | None = None) -> None:
        """children 与 ids 等长，sparse_weights 与 children 等长。

        ids 独立传入而不依赖 metadata，避免外部修改 metadata 时破坏索引。
        """
        if sparse_weights is None or len(sparse_weights) != len(children):
            raise ValueError(
                f"sparse_weights 长度({len(sparse_weights) if sparse_weights else 0}) "
                f"必须等于 children 长度({len(children)})"
            )
        if len(ids) != len(children):
            raise ValueError(f"ids 长度({len(ids)}) 必须等于 children 长度({len(children)})")
        for child, doc_id, weights in zip(children, ids, sparse_weights):
            self.ids.append(doc_id)
            self.doc_weights.append(weights)
            for token in weights:
                self.doc_freq[token] += 1
            self.sources.append(child.metadata.get("source", ""))
            self.areas.append(child.metadata.get("area", ""))
        logger.info(f"稀疏索引新增 {len(children)} 条（总 {len(self.doc_weights)}）")

    def search(self, query_weights: dict, top_k: int,
               source_filter: str | None = None,
               area_filter: str | None = None) -> list[tuple[str, float]]:
        """按 bge-m3 的 query/doc 词项权重做 dot product，返回 [(chroma_id, 分数)] 降序。"""
        if not self.doc_weights or not query_weights:
            return []
        scores = {}
        for token, q_weight in query_weights.items():
            for idx, doc_weights in enumerate(self.doc_weights):
                if token not in doc_weights:
                    continue
                if source_filter and self.sources[idx] != source_filter:
                    continue
                if area_filter and self.areas[idx] != area_filter:
                    continue
                scores[idx] = scores.get(idx, 0.0) + q_weight * doc_weights[token]
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [(self.ids[idx], score) for idx, score in ranked[:top_k]]


class VectorStore:
    """Chroma 双 collection 封装：children + parents + 内存稀疏索引。"""

    def __init__(self):
        self.client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
        self.children_col = self.client.get_or_create_collection(
            name=config.CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": config.CHROMA_DISTANCE_METRIC},
        )
        self.parents_col = self.client.get_or_create_collection(
            name=config.CHROMA_PARENTS_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self.sparse = SparseIndex()
        # reranker：按 config.RERANK_ENABLED 懒加载（首调 rerank 才实例化 CrossEncoder）
        self.reranker = get_reranker() if config.RERANK_ENABLED else None
        self._rebuild_sparse_from_chroma()
        logger.info(
            f"VectorStore 就绪: children={self.children_col.count()}, "
            f"parents={self.parents_col.count()}, rerank={'on' if self.reranker else 'off'}"
        )

    def _rebuild_sparse_from_chroma(self) -> None:
        """服务重启后从 Chroma 恢复稀疏索引（不恢复稠密向量，由 Chroma 持久化）。"""
        if self.children_col.count() == 0:
            return
        data = self.children_col.get(include=["documents", "metadatas"])
        children = [
            Document(page_content=text, metadata=meta or {})
            for text, meta in zip(data["documents"], data["metadatas"])
        ]
        # 重算稀疏权重（Chroma 不存 lexical_weights）
        embedder = get_embedding_model()
        sparse_weights = embedder.encode_sparse([c.page_content for c in children])
        self.sparse.add_documents(children, list(data["ids"]), sparse_weights)

    def add_documents(self, children: list[Document],
                      parents: dict[str, str] | None = None,
                      sparse_weights: list[dict] | None = None) -> None:
        """写入子块到 children collection + 父块到 parents collection + 更新稀疏索引。

        parents: {parent_id: parent_content}（由 caller 合并去重）
        sparse_weights: 与 children 等长的 lexical_weights 列表
        """
        if not children:
            return
        embedder = get_embedding_model()
        texts = [c.page_content for c in children]
        ids = [c.metadata["id"] for c in children]
        # 注意：children 元数据里**不再放 parent_content**，避免 4× 重复
        # 但保留 `id`，供 retriever 跨子查询去重（id 短，不占空间）
        child_metadatas = [
            {
                "id": doc_id,
                "parent_id": c.metadata["parent_id"],
                "source": c.metadata.get("source", ""),
                "area": c.metadata.get("area", ""),
                "file_path": c.metadata.get("file_path", ""),
            }
            for c, doc_id in zip(children, ids)
        ]
        dense = embedder.encode_dense(texts)

        self.children_col.add(
            ids=ids, documents=texts, embeddings=dense.tolist(),
            metadatas=child_metadatas,
        )

        if parents:
            self.parents_col.upsert(
                ids=list(parents.keys()),
                documents=list(parents.values()),
                # 父块仅按 ID 还原，不参与向量检索。显式给占位向量，避免
                # Chroma 自动调用默认 embedding 模型并下载额外权重。
                embeddings=[[1.0] for _ in parents],
                metadatas=[
                    {"source": self._guess_parent_source(parent_id, children)}
                    for parent_id in parents
                ],
            )

        if sparse_weights is None:
            sparse_weights = embedder.encode_sparse(texts)
        self.sparse.add_documents(children, ids, sparse_weights)
        logger.info(f"写入 {len(children)} 子块，{len(parents) if parents else 0} 父块")

    @staticmethod
    def _guess_parent_source(parent_id: str, children: list[Document]) -> str:
        """从 parent_id 反查对应的 source（同一父块下的子块共享 source）。"""
        for c in children:
            if c.metadata.get("parent_id") == parent_id:
                return c.metadata.get("source", "")
        return ""

    def clear(self) -> None:
        """清空 children + parents collection 与稀疏索引（重建索引前调用）。"""
        self.client.delete_collection(config.CHROMA_COLLECTION_NAME)
        self.client.delete_collection(config.CHROMA_PARENTS_COLLECTION_NAME)
        self.children_col = self.client.get_or_create_collection(
            name=config.CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": config.CHROMA_DISTANCE_METRIC},
        )
        self.parents_col = self.client.get_or_create_collection(
            name=config.CHROMA_PARENTS_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self.sparse = SparseIndex()

    # ---------- 检索 ----------

    def search_children(self, query: str, top_k: int,
                        source_filter: str | None = None,
                        area_filter: str | None = None) -> list[Document]:
        """稠密 + 稀疏混合检索子块，返回按 RRF 融合排序的 child Documents。"""
        embedder = get_embedding_model()
        query_dense = embedder.encode_dense(query)
        query_weights = embedder.encode_sparse(query)

        # 稠密路：Chroma 子块
        where = {"source": source_filter} if source_filter else ({"area": area_filter} if area_filter else None)
        dense_hits = self.children_col.query(
            query_embeddings=[query_dense.tolist()],
            n_results=max(top_k, 1),
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        # 稀疏路：内存索引
        sparse_hits = self.sparse.search(query_weights, top_k, source_filter, None if source_filter else area_filter)

        # RRF 融合
        rrf_scores: dict[str, float] = {}
        children_by_id: dict[str, Document] = {}

        dense_ids = dense_hits["ids"][0] if dense_hits["ids"] else []
        for rank, (child_id, text, meta, dist) in enumerate(zip(
                dense_ids, dense_hits["documents"][0], dense_hits["metadatas"][0],
                dense_hits["distances"][0]), start=1):
            rrf_scores[child_id] = rrf_scores.get(child_id, 0) + 1 / (_RRF_K + rank)
            # 把稠密距离挂到 metadata._distance，供 FAQ 阈值判断使用
            children_by_id[child_id] = Document(
                page_content=text,
                metadata={**meta, "_distance": float(dist)},
            )

        # 按完整稀疏列表的原始排名计分；共同命中的子块也要累加贡献。
        # 仅文档内容去重，不能先去重再重新编号，否则会抬高稀疏独有结果。
        sparse_only_ids = []
        for rank, (cid, _score) in enumerate(sparse_hits, start=1):
            rrf_scores[cid] = rrf_scores.get(cid, 0) + 1 / (_RRF_K + rank)
            if cid not in children_by_id:
                sparse_only_ids.append(cid)

        if sparse_only_ids:
            fetched = self.children_col.get(
                ids=sparse_only_ids, include=["documents", "metadatas"]
            )
            # get() 只补全文档内容，返回顺序不参与评分；按 ID 建立映射。
            for cid, text, meta in zip(
                    fetched["ids"], fetched["documents"], fetched["metadatas"]):
                # 稀疏命中没有原生 distance，近似用 1.0（保守不触发 FAQ）
                children_by_id[cid] = Document(
                    page_content=text,
                    metadata={**meta, "_distance": 1.0},
                )

        ranked_ids = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        # 稀疏索引中的记录可能已被删除，只返回成功取回的文档。
        return [children_by_id[cid] for cid, _ in ranked_ids if cid in children_by_id][:top_k]

    def restore_parent_docs(self, child_hits: list[Document]) -> list[Document]:
        """按 parent_id 去重，从 parents collection 批量取父块原文。"""
        parent_ids = []
        seen = set()
        for child in child_hits:
            pid = child.metadata.get("parent_id")
            if pid and pid not in seen:
                parent_ids.append(pid)
                seen.add(pid)
        if not parent_ids:
            return []

        fetched = self.parents_col.get(
            ids=parent_ids, include=["documents", "metadatas"]
        )
        # 按 parent_ids 顺序还原（保持子块命中顺序）
        id_to_doc = {
            pid: {"content": doc, "meta": meta}
            for pid, doc, meta in zip(
                fetched["ids"], fetched["documents"], fetched["metadatas"]
            )
        }
        return [
            Document(
                page_content=id_to_doc[pid]["content"],
                metadata={
                    "parent_id": pid,
                    "source": id_to_doc[pid]["meta"].get("source", ""),
                    "file_path": id_to_doc[pid]["meta"].get("file_path", ""),
                },
            )
            for pid in parent_ids if pid in id_to_doc
        ]

    def restore_and_rerank_parents(
        self,
        child_hits: list[Document],
        query: str,
        top_m: int | None = None,
    ) -> list[Document]:
        """restore_parent_docs + 可选 rerank（如果 rerank 启用且父块 > 1）。

        Args:
            child_hits: search_children 返回的子块
            query: 用于 rerank 比对的查询
            top_m: 取多少个父块（默认 config.CANDIDATE_M）
        """
        if top_m is None:
            top_m = config.CANDIDATE_M

        parents = self.restore_parent_docs(child_hits)
        if self.reranker and len(parents) > 1:
            parents = self.reranker.rerank(query, parents, top_m=top_m)
        else:
            parents = parents[:top_m]
        return parents


# 全局单例（懒加载）
_vector_store = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
