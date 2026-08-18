# rag_qa/loaders/ocr.py
# OCR 工厂：rapidocr_onnxruntime 单例（CPU），首次调用时实例化。
from typing import TYPE_CHECKING

from base.config import config
from base.logger import logger

if TYPE_CHECKING:
    from rapidocr_onnxruntime import RapidOCR

_ocr: "RapidOCR | None" = None


def get_ocr() -> "RapidOCR":
    """获取 RapidOCR 单例。默认 CPU（rapidocr-onnxruntime），按 config 决定是否启用 CUDA。"""
    global _ocr
    if _ocr is not None:
        return _ocr

    from rapidocr_onnxruntime import RapidOCR

    use_cuda = config.OCR_USE_CUDA
    logger.info(f"初始化 RapidOCR（use_cuda={use_cuda}）...")
    _ocr = RapidOCR(det_use_cuda=use_cuda, cls_use_cuda=use_cuda, rec_use_cuda=use_cuda)
    return _ocr


def run_ocr(image_array) -> str:
    """对 numpy 图像数组跑 OCR，返回识别文本（多行用换行拼接）。"""
    ocr = get_ocr()
    result, _ = ocr(image_array)
    if not result:
        return ""
    return "\n".join(line[1] for line in result)