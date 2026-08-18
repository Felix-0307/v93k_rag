# rag_qa/loaders/md_loader.py
# Markdown/纯文本加载器：按多编码顺序尝试读取（utf-8-sig → utf-8 → gbk → gb18030 → latin-1），
# 覆盖 Windows GBK 习惯保存的 .txt 文件。
from typing import Iterator

from langchain_core.documents import Document
from langchain_core.document_loaders import BaseLoader

# 编码尝试顺序：先 utf-8 系（带 BOM），再 GBK 系（中文 Windows 常见），最后 latin-1（兜底）
_ENCODING_CANDIDATES = ("utf-8-sig", "utf-8", "gbk", "gb18030", "latin-1")


class MarkdownTextLoader(BaseLoader):
    """按 utf-8-sig → utf-8 → gbk → gb18030 → latin-1 顺序读取 md/txt 文件。"""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def lazy_load(self) -> Iterator[Document]:
        text = self._read_text()
        yield Document(page_content=text, metadata={})

    def _read_text(self) -> str:
        with open(self.file_path, "rb") as f:
            raw = f.read()
        for enc in _ENCODING_CANDIDATES:
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        # 兜底：latin-1 不会失败，但内容可能乱码
        return raw.decode("latin-1")
