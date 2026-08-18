# rag_qa/loaders/ocr_pptx.py
# OCRPPTLoader：python-pptx 文本 + 表格 + 图片 shape OCR。
from typing import Iterator

from pptx import Presentation
from langchain_core.documents import Document
from langchain_core.document_loaders import BaseLoader

from rag_qa.loaders.ocr import run_ocr


class OCRPPTLoader(BaseLoader):
    """PPT/PTTX 加载器：每页提取 text frame + 表格 + 图片 OCR。"""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def lazy_load(self) -> Iterator[Document]:
        text = self._extract_text()
        yield Document(page_content=text, metadata={})

    def _extract_text(self) -> str:
        prs = Presentation(self.file_path)
        parts: list[str] = []

        for slide_idx, slide in enumerate(prs.slides, 1):
            slide_text_parts: list[str] = [f"[Slide {slide_idx}]"]

            for shape in slide.shapes:
                # MSO_SHAPE_TYPE.PICTURE == 13
                if shape.shape_type == 13:
                    try:
                        img_bytes = shape.image.blob
                        from io import BytesIO

                        from PIL import Image

                        img = Image.open(BytesIO(img_bytes))
                        import numpy as np

                        ocr_text = run_ocr(np.array(img))
                        if ocr_text.strip():
                            slide_text_parts.append(f"[图片OCR] {ocr_text}")
                    except Exception:
                        pass
                    continue

                # GROUP（6）递归
                if shape.shape_type == 6 and shape.shapes:
                    for sub in shape.shapes:
                        if sub.has_text_frame and sub.text_frame.text.strip():
                            slide_text_parts.append(sub.text_frame.text)
                    continue

                if shape.has_text_frame and shape.text_frame.text.strip():
                    slide_text_parts.append(shape.text_frame.text)

                # 表格
                if shape.has_table:
                    for row in shape.table.rows:
                        slide_text_parts.append(
                            " | ".join(cell.text.strip() for cell in row.cells)
                        )

            parts.append("\n".join(slide_text_parts))

        return "\n".join(parts)