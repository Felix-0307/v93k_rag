# rag_qa/core/embedding.py
# bge-m3 嵌入封装（FlagEmbedding 加载）：同时输出 1024 维稠密向量
# + 稀疏词项权重（lexical_weights），供 Chroma 稠密检索与内存稀疏检索混合使用。
#
# 兼容补丁：transformers 4.50+ 移除了 `dtype=` kwargs 给 model.__init__，
# 但 FlagEmbedding 1.x 的 finetune 路径仍在传 `dtype=...`，会触发
# `XLMRobertaModel.__init__() got an unexpected keyword argument 'dtype'`。
# 我们把 `dtype` 改名为 `torch_dtype` 后再喂给 AutoModel.from_pretrained。
import numpy as np
from FlagEmbedding import BGEM3FlagModel
from transformers import AutoModel as _AutoModel

_orig_from_pretrained = _AutoModel.from_pretrained


def _patched_from_pretrained(*args, **kwargs):
    if "dtype" in kwargs and "torch_dtype" not in kwargs:
        kwargs["torch_dtype"] = kwargs.pop("dtype")
    return _orig_from_pretrained(*args, **kwargs)


_AutoModel.from_pretrained = staticmethod(_patched_from_pretrained)

from base.config import config
from base.logger import logger


class BGE_M3_Embedding:
    """bge-m3 嵌入封装：encode_dense 和 encode_sparse 上下文一致。"""

    # 批大小：bge-m3 显存敏感；CPU 下 12 比较稳；GPU 可调高
    _BATCH_SIZE = 12

    def __init__(self):
        logger.info(f"加载 bge-m3: {config.EMBEDDING_MODEL_DIR}")
        self.model = BGEM3FlagModel(
            config.EMBEDDING_MODEL_DIR,
            use_fp16=config.EMBEDDING_USE_FP16,
            device=config.EMBEDDING_DEVICE,
        )

    def encode_dense(self, texts) -> np.ndarray:
        """稠密向量（bge-m3 内置 L2 归一化）。单文本返回 1 维，否则 2 维。"""
        single = isinstance(texts, str)
        if single:
            texts = [texts]
        out = self.model.encode(
            texts,
            batch_size=self._BATCH_SIZE,
            max_length=config.EMBEDDING_MAX_LENGTH,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        dense = np.asarray(out["dense_vecs"], dtype=np.float32)
        return dense[0] if single else dense

    def encode_sparse(self, texts) -> list[dict] | dict:
        """稀疏词项权重 {token: weight}，来自 bge-m3 的 lexical_weights。

        单文本直接返回 dict；多文本返回 list[dict]。
        """
        single = isinstance(texts, str)
        if single:
            texts = [texts]
        out = self.model.encode(
            texts,
            batch_size=self._BATCH_SIZE,
            max_length=config.EMBEDDING_MAX_LENGTH,
            return_dense=False,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        weights = out["lexical_weights"]
        return weights[0] if single else weights


# 全局单例（懒加载：首次调用时才加载模型，避免 import 即加载 2.2GB 权重）
_embedding_model = None


def get_embedding_model() -> BGE_M3_Embedding:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = BGE_M3_Embedding()
    return _embedding_model
