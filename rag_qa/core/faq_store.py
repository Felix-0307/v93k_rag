"""独立 FAQ 问答库：JSON 持久化问答对，本地向量匹配标准问题。"""
import json
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from base.config import config
from base.logger import logger
from rag_qa.core.embedding import get_embedding_model


class FAQEntry(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    source: str = Field(default="faq", min_length=1)
    enabled: bool = True


@dataclass(frozen=True)
class FAQMatch:
    entry: FAQEntry
    similarity: float


class FAQStore:
    def __init__(self, data_path=None, similarity_threshold=None, enabled=None):
        self.data_path = Path(data_path if data_path is not None else config.FAQ_DATA_PATH)
        self.similarity_threshold = (
            config.FAQ_SIMILARITY_THRESHOLD
            if similarity_threshold is None else similarity_threshold
        )
        self.enabled = config.FAQ_ENABLED if enabled is None else enabled
        if not 0 <= self.similarity_threshold <= 1:
            raise ValueError("FAQ similarity_threshold 必须在 0 到 1 之间")
        self._reload_lock = threading.Lock()
        # 问答和向量作为一个快照整体替换，匹配请求不会读到半更新的数据。
        self._snapshot = ((), np.empty((0, 0), dtype=np.float64))
        if self.enabled:
            if self.data_path.exists():
                self.reload()
            else:
                logger.warning(f"FAQ 文件不存在，暂时跳过 FAQ 检测: {self.data_path}")

    def reload(self) -> int:
        """重读 JSON 并重建问题向量；失败时保留上一次有效快照。"""
        with self._reload_lock:
            if not self.enabled:
                self._snapshot = ((), np.empty((0, 0), dtype=np.float64))
                return 0
            raw = json.loads(self.data_path.read_text(encoding="utf-8-sig"))
            if not isinstance(raw, list):
                raise ValueError("FAQ 文件顶层必须是问答对数组")
            entries = [FAQEntry.model_validate(item) for item in raw]
            if len({entry.id for entry in entries}) != len(entries):
                raise ValueError("FAQ id 不能重复")
            entries = tuple(entry for entry in entries if entry.enabled)
            if entries:
                vectors = np.asarray(
                    get_embedding_model().encode_dense([entry.question for entry in entries]),
                    dtype=np.float64,
                )
                if vectors.ndim != 2 or vectors.shape[0] != len(entries):
                    raise ValueError("FAQ 问题向量数量或维度错误")
                norms = np.linalg.norm(vectors, axis=1, keepdims=True)
                if not np.isfinite(vectors).all() or np.any(norms == 0):
                    raise ValueError("FAQ 问题向量必须有限且非零")
                vectors = vectors / norms
            else:
                vectors = np.empty((0, 0), dtype=np.float64)
            self._snapshot = (entries, vectors)
            logger.info(f"FAQ 已加载: {len(entries)} 条, path={self.data_path}")
            return len(entries)

    def match(self, question: str, source_filter: str | None = None) -> FAQMatch | None:
        if not self.enabled or not question.strip():
            return None
        entries, vectors = self._snapshot
        candidates = [
            i for i, entry in enumerate(entries)
            if not source_filter or entry.source == source_filter
        ]
        if not candidates:
            return None
        query = np.asarray(get_embedding_model().encode_dense(question), dtype=np.float64)
        norm = np.linalg.norm(query)
        if query.ndim != 1 or not np.isfinite(query).all() or norm == 0:
            return None
        scores = np.clip(vectors[candidates] @ (query / norm), -1.0, 1.0)
        best = int(np.argmax(scores))
        similarity = float(scores[best])
        if similarity < self.similarity_threshold:
            return None
        return FAQMatch(entries[candidates[best]], similarity)


_faq_store = None
_faq_store_lock = threading.Lock()


def get_faq_store() -> FAQStore:
    global _faq_store
    with _faq_store_lock:
        if _faq_store is None:
            _faq_store = FAQStore()
    return _faq_store
