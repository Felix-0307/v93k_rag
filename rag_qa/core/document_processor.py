# rag_qa/core/document_processor.py
# 文档加载 + 父子块切分：
#   父块（大上下文）→ 子块（检索粒度），子块只携带 parent_id；
#   父块原文由 caller 汇总成 {parent_id: content} 交给 vector_store 单独入库。
import os
from datetime import datetime

from langchain_core.documents import Document

from base.config import config
from base.logger import logger
from rag_qa.loaders import (
    OCRDOCLoader,
    OCRIMGLoader,
    OCRPDFLoader,
    OCRPPTLoader,
    MarkdownTextLoader,
)
from rag_qa.splitters import ChineseRecursiveTextSplitter

# 扩展名 → 加载器类（OCR 加载器覆盖了文本 + 扫描版场景）
_LOADERS = {
    ".pdf": OCRPDFLoader,        # 文本层 + 大图 OCR fallback
    ".docx": OCRDOCLoader,
    ".ppt": OCRPPTLoader,
    ".pptx": OCRPPTLoader,
    ".jpg": OCRIMGLoader,
    ".jpeg": OCRIMGLoader,
    ".png": OCRIMGLoader,
    ".md": MarkdownTextLoader,
    ".txt": MarkdownTextLoader,
}


def _source_of(file_path: str) -> str:
    """从文件名推导文档类别，如 common_errors.md -> common_errors"""
    return os.path.splitext(os.path.basename(file_path))[0]


def _load_file(file_path: str) -> Document:
    ext = os.path.splitext(file_path)[1].lower()
    loader_cls = _LOADERS[ext]
    docs = loader_cls(file_path).load()
    doc = docs[0]
    # loader 只设 source（path）和 page_content；这里补 file_path 和时间戳
    doc.metadata["file_path"] = file_path
    doc.metadata["source"] = _source_of(file_path)
    # 五类资料按目录标注，供领域路由过滤；其他目录保持兼容。
    area = os.path.basename(os.path.dirname(file_path))
    if area in {"process", "equipment", "yield", "cleanroom", "quality"}:
        doc.metadata["area"] = area
    doc.metadata["timestamp"] = datetime.now().isoformat()
    return doc


def load_documents(data_dir: str) -> list[Document]:
    """递归遍历数据目录，加载所有支持格式的文档。

    同目录下同名不同格式只保留 md/txt，
    避免同一份内容重复入库。
    """
    # 先收集全部候选文件，md/txt 排在 pdf 之前，保证同名去重时 md/txt 优先
    candidates = []
    for root, _, files in os.walk(data_dir):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext in _LOADERS:
                candidates.append(os.path.join(root, name))
    candidates.sort(key=lambda p: os.path.splitext(p)[1].lower() != ".pdf")

    documents = []
    loaded_stems = set()
    for path in candidates:
        name = os.path.basename(path)
        stem = (os.path.dirname(path), os.path.splitext(name)[0])
        if stem in loaded_stems:
            logger.warning(f"跳过同名文档: {path}（已加载 {stem}）")
            continue
        try:
            doc = _load_file(path)
        except Exception as e:
            logger.error(f"加载失败 {path}: {e}")
            continue
        loaded_stems.add(stem)
        documents.append(doc)
        logger.info(f"加载文档: {path}")
    return documents


def _build_child_chunks(doc: Document, doc_index: int) -> tuple[list[Document], dict[str, str]]:
    """单篇文档：父块切分 → 子块切分。

    返回:
        children: 子块列表（metadata 含 parent_id、source、file_path，不再带 parent_content）
        parents: {parent_id: parent_content}
    """
    parent_splitter = ChineseRecursiveTextSplitter(
        chunk_size=config.PARENT_CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP
    )
    child_splitter = ChineseRecursiveTextSplitter(
        chunk_size=config.CHILD_CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP
    )

    children = []
    parents: dict[str, str] = {}
    for j, parent in enumerate(parent_splitter.split_documents([doc])):
        parent_id = f"doc_{doc_index}_parent_{j}"
        parents[parent_id] = parent.page_content
        subs = child_splitter.split_text(parent.page_content)
        for k, sub_text in enumerate(subs):
            children.append(Document(
                page_content=sub_text,
                metadata={
                    "id": f"{parent_id}_child_{k}",
                    "parent_id": parent_id,
                    **{key: value for key, value in doc.metadata.items()},
                },
            ))
    return children, parents


def process_documents(data_dir: str) -> tuple[list[Document], dict[str, str]]:
    """加载目录全部文档并切分，返回 (children, parents)。

    parents: {parent_id: parent_content}，交给 vector_store 入独立 collection。
    """
    docs = load_documents(data_dir)
    logger.info(f"加载文档数: {len(docs)}")

    all_children: list[Document] = []
    all_parents: dict[str, str] = {}
    for i, doc in enumerate(docs):
        children, parents = _build_child_chunks(doc, i)
        all_children.extend(children)
        all_parents.update(parents)
        logger.info(f"文档[{i}] {doc.metadata.get('source')}: {len(children)} 子块, {len(parents)} 父块")

    logger.info(f"子块总数: {len(all_children)}，父块总数: {len(all_parents)}")
    return all_children, all_parents
