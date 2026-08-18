# rag_qa/loaders/ocr_pdf.py
# OCRPDFLoader：PyMuPDF 文本层 + 超过尺寸阈值的图片走 OCR。
from typing import Iterator

import fitz
import numpy as np
from langchain_core.documents import Document
from langchain_core.document_loaders import BaseLoader

from base.config import config
from rag_qa.loaders.ocr import run_ocr


class OCRPDFLoader(BaseLoader):
    """带 OCR fallback 的 PDF 加载器。

    对每页先取文本层（PyMuPDF），再对 bbox 占比 ≥ 阈值（默认 0.6）
    的嵌入图片跑 RapidOCR，识别结果追加到该页文本后。
    """

    def __init__(self, file_path: str, page_delimiter: str = "\n"):
        self.file_path = file_path
        self.page_delimiter = page_delimiter
        self.threshold = config.OCR_PDF_IMAGE_THRESHOLD

    def lazy_load(self) -> Iterator[Document]:
        text = self._pdf2text()
        yield Document(page_content=text, metadata={})

    def _pdf2text(self) -> str:
        threshold_w, threshold_h = self.threshold, self.threshold
        pages = []
        with fitz.open(self.file_path) as doc:
            for page in doc:
                parts = [page.get_text("text")]

                # 大图才 OCR（避免水印、logo 等小图）
                for img_info in page.get_image_info(xrefs=True):
                    bbox = img_info["bbox"]
                    w_ratio = (bbox[2] - bbox[0]) / page.rect.width
                    h_ratio = (bbox[3] - bbox[1]) / page.rect.height
                    if w_ratio < threshold_w or h_ratio < threshold_h:
                        continue

                    xref = img_info["xref"]
                    try:
                        img = doc.extract_image(xref)
                    except Exception:
                        continue
                    arr = np.frombuffer(img["image"], dtype=np.uint8).reshape(
                        img["height"], img["width"], -1
                    )
                    ocr_text = run_ocr(arr)
                    if ocr_text.strip():
                        parts.append(f"\n[图片OCR] {ocr_text}")

                pages.append("\n".join(parts))
        return self.page_delimiter.join(pages)