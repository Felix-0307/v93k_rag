# rag_qa/eval/__init__.py
# 评估模块导出
from rag_qa.eval.dataset import EvalDataset, EvalSample, load_dataset
from rag_qa.eval.report import build_report, print_table, save_report
from rag_qa.eval.runner import SampleResult, run_eval

__all__ = [
    "EvalSample",
    "EvalDataset",
    "load_dataset",
    "SampleResult",
    "run_eval",
    "build_report",
    "save_report",
    "print_table",
]