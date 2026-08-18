# rag_qa/loaders/ocr_docx.py
# OCRDOCLoader：python-docx 段落 + 表格 + 嵌入图片 OCR。
from typing import Iterator

from docx import Document as DocxDocument
from langchain_core.documents import Document
from langchain_core.document_loaders import BaseLoader

from rag_qa.loaders.ocr import run_ocr


class OCRDOCLoader(BaseLoader):
    """Word 加载器：原生段落/表格 + 嵌入图片 OCR。"""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def lazy_load(self) -> Iterator[Document]:
        text = self._extract_text()
        yield Document(page_content=text, metadata={})

    def _extract_text(self) -> str:
        doc = DocxDocument(self.file_path)
        parts: list[str] = []

        # 段落 + 表格（按文档顺序遍历）
        for block in doc.element.body.iter():
            tag = block.tag.split("}")[-1] if "}" in block.tag else block.tag
            if tag == "p":
                text = "".join(t.text or "" for t in block.iter() if t.tag.endswith("}t"))
                if text.strip():
                    parts.append(text)
            elif tag == "tbl":
                cells = [
                    "".join(t.text or "" for t in cell.iter() if t.tag.endswith("}t"))
                    for cell in block.iter() if cell.tag.endswith("}tc")
                ]
                parts.append(" | ".join(cells))

        # 嵌入图片 OCR（python-docx ImagePart）
        try:
            for rel in doc.part.rels.values():
                if "image" in rel.target_ref:
                    img_part = rel.target_part
                    if hasattr(img_part, "blob"):
                        from io import BytesIO

                        from PIL import Image

                        img = Image.open(BytesIO(img_part.blob))
                        import numpy as np

                        ocr_text = run_ocr(np.array(img))
                        if ocr_text.strip():
                            parts.append(f"\n[图片OCR] {ocr_text}")
        except Exception:
            pass

        return "\n".join(parts)