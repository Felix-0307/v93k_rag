# rag_qa/loaders/__init__.py
# Loader 集合：纯文本 + OCR（含扫描版 PDF/DOCX/PPT/图片）
from langchain_core.document_loaders import BaseLoader

from .ocr_docx import OCRDOCLoader
from .ocr_image import OCRIMGLoader
from .ocr_pdf import OCRPDFLoader
from .ocr_pptx import OCRPPTLoader
from .md_loader import MarkdownTextLoader
from .pdf_loader import PDFTextLoader  # 仅文本层（无 OCR），保留供可选切换

__all__ = [
    "BaseLoader",
    "PDFTextLoader",
    "MarkdownTextLoader",
    "OCRPDFLoader",
    "OCRDOCLoader",
    "OCRPPTLoader",
    "OCRIMGLoader",
]