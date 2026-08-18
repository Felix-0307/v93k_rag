# rag_qa/loaders/pdf_loader.py
# PDF 文本层加载器：用 fitz 逐页提取文本（不 OCR，适合带文本层的电子版 PDF）
from typing import Iterator

import fitz
from langchain_core.documents import Document
from langchain_core.document_loaders import BaseLoader


class PDFTextLoader(BaseLoader):
    """用 PyMuPDF 提取 PDF 文本层，每页文本以换行拼接为一个 Document。"""

    def __init__(self, file_path: str, page_delimiter: str = "\n"):
        self.file_path = file_path
        self.page_delimiter = page_delimiter

    def lazy_load(self) -> Iterator[Document]:
        text = self._pdf2text()
        yield Document(page_content=text, metadata={})

    def _pdf2text(self) -> str:
        pages = []
        with fitz.open(self.file_path) as doc:
            for page in doc:
                pages.append(page.get_text("text"))
        return self.page_delimiter.join(pages)
