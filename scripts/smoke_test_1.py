# -*- coding: utf-8 -*-
# 冒烟测试 1：加载 + 切分（不涉及模型与 LLM）
import sys, os
sys.path.insert(0, r"D:\workspace\python\RAG_project\my_pro")

from base.config import config
from rag_qa.core.document_processor import load_documents, process_documents

print("DATA_DIR:", config.DATA_DIR)
docs = load_documents(config.DATA_DIR)
print("加载文档数:", len(docs))
for d in docs:
    print(" -", d.metadata.get("source"), "| 长度:", len(d.page_content))

children = process_documents(config.DATA_DIR)
print("子块总数:", len(children))
if children:
    c = children[0]
    print("样例子块元数据键:", sorted(c.metadata.keys()))
    print("样例 parent_id:", c.metadata.get("parent_id"))
    print("样例 parent_content 长度:", len(c.metadata.get("parent_content", "")))
    print("样例文本前 80 字:", c.page_content[:80])
