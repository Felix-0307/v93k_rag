# rag_qa/splitters/chinese_recursive_splitter.py
# 中文递归切分器（功能对齐 EduRag 同名实现，写法独立）：
# 按「段落 → 行 → 句末标点 → 分号 → 逗号」的优先级递归切分，
# 保证每个块是完整的句子/段落，且不超 chunk_size。
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

# 分隔符优先级：从粗粒度到细粒度，命中即切
_CHINESE_SEPARATORS = [
    "\n\n",                # 空行分段
    "\n",                  # 换行
    r"(?<=[。！？])",       # 中文句末标点后
    r"(?<=[.!?])\s+",       # 英文句末标点 + 空格
    r"(?<=[；;])",          # 分号后
    r"(?<=[，,])",          # 逗号后
]


class ChineseRecursiveTextSplitter(RecursiveCharacterTextSplitter):
    """面向中文的分层递归切分器，块边界落在标点之后，保留分隔符本身。"""

    def __init__(self, chunk_size: int, chunk_overlap: int = 0):
        super().__init__(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=_CHINESE_SEPARATORS,
            keep_separator=True,        # 保留标点：每个块是完整句子
            is_separator_regex=True,    # 分隔符按正则处理
            length_function=len,
        )
