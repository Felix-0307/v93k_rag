# scripts/build_index.py
# 离线建索引：加载 data/ 下全部文档 → 父子块切分 → 写入 Chroma + 稀疏索引。
# 用法（在 my_pro 根目录）:
#   D:\Anaconda\envs\edu_rag\python.exe scripts\build_index.py
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from base.config import config
from base.logger import logger
from rag_qa.core.document_processor import process_documents
from rag_qa.core.vector_store import get_vector_store


def main():
    logger.info(f"数据目录: {config.DATA_DIR}")
    children, parents = process_documents(config.DATA_DIR)
    if not children:
        logger.warning("未加载到任何文档，请检查 data/ 目录")
        return

    store = get_vector_store()
    store.clear()  # 全量重建
    store.add_documents(children, parents=parents)
    logger.info(f"索引构建完成: {store.children_col.count()} 子块, {store.parents_col.count()} 父块")


if __name__ == "__main__":
    main()
