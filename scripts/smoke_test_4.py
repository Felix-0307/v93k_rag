# -*- coding: utf-8 -*-
# 本地测试 RAGSystem.ask（直接调用，绕过 FastAPI）
import sys, os
sys.path.insert(0, r"D:\workspace\python\RAG_project\my_pro")

import traceback
try:
    from rag_qa.core.rag_system import get_rag_system
    system = get_rag_system()
    result = system.ask("DPS 板卡的作用是什么？")
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
except Exception as e:
    traceback.print_exc()
