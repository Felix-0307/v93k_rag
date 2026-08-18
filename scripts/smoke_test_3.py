# -*- coding: utf-8 -*-
# 冒烟测试 3：多文档检索验证（不调 LLM，只验证检索结果来源）
import sys, os
sys.path.insert(0, r"D:\workspace\python\RAG_project\my_pro")

from rag_qa.core.vector_store import get_vector_store

store = get_vector_store()
print(f"Chroma 子块数: {store.collection.count()}")

test_queries = [
    ("DPS 板卡的作用是什么？", "V93K基础知识"),
    ("Contact Fail 怎么排查？", "common_errors"),
    ("STIL 中 WaveformTable 怎么写？", "stil_syntax"),
    ("FunctionalTest API 的 pinList 怎么用？", "test_method_api"),
    ("Pattern Mismatch 的常见原因？", "common_errors"),
    ("STIL 的 Signals 块怎么定义引脚？", "stil_syntax"),
    ("DC_Test 怎么测漏电流？", "test_method_api"),
    ("什么是 Per-Pin 架构？", "V93K基础知识"),
]

correct = 0
for q, expected_source in test_queries:
    hits = store.search_children(q, top_k=5)
    parents = store.restore_parent_docs(hits)
    sources = [p.metadata.get("source", "") for p in parents]
    # 检查期望的 source 是否在命中结果中
    matched = expected_source in sources
    correct += int(matched)
    status = "OK" if matched else "MISS"
    print(f"[{status}] Q: {q[:30]}... -> sources: {sources}")

print(f"\n命中率: {correct}/{len(test_queries)}")
