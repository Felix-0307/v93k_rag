# rag_qa/loaders/ocr_image.py
# OCRIMGLoader：纯 OCR 的图片加载器（PNG / JPG）。
from typing import Iterator

import numpy as np
from langchain_core.documents import Document
from langchain_core.document_loaders import BaseLoader
from PIL import Image

from rag_qa.loaders.ocr import run_ocr


class OCRIMGLoader(BaseLoader):
    """图片加载器：整个文件作为一张图跑 OCR。"""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def lazy_load(self) -> Iterator[Document]:
        img = Image.open(self.file_path)
        text = run_ocr(np.array(img))
        yield Document(page_content=text, metadata={})