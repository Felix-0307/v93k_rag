# -*- coding: utf-8 -*-
# 冒烟测试 2：建索引 + 检索（验证完整链路，不调 LLM）
import sys, os
sys.path.insert(0, r"D:\workspace\python\RAG_project\my_pro")

from base.config import config
from base.logger import logger
from rag_qa.core.document_processor import process_documents
from rag_qa.core.vector_store import get_vector_store

# 1. 切分
children = process_documents(config.DATA_DIR)
print(f"子块数: {len(children)}")

# 2. 建索引
store = get_vector_store()
store.clear()
store.add_documents(children)
print(f"Chroma 子块数: {store.collection.count()}")
print(f"稀疏索引条目: {len(store.sparse.ids)}")

# 3. 稠密+稀疏混合检索测试
test_queries = [
    "DPS 板卡的作用是什么？",
    "如何执行功能测试？",
    "测试向量的数据格式有哪些？",
    "什么是 Per-Pin 架构？",
]
for q in test_queries:
    hits = store.search_children(q, top_k=3)
    parents = store.restore_parent_docs(hits)
    print(f"\nQ: {q}")
    print(f"  命中子块: {len(hits)}, 还原父块: {len(parents)}")
    if parents:
        print(f"  父块来源: {parents[0].metadata.get('source')}")
        print(f"  父块前 100 字: {parents[0].page_content[:100]}")
