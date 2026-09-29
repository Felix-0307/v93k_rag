# rag_qa/eval/report.py
# 输出：JSON 报告 + 控制台表格
import json
from datetime import datetime
from pathlib import Path

from rag_qa.eval.runner import EVALUATION_METRICS, SampleResult


def build_report(
    results: list[SampleResult],
    metrics: dict,
    dataset_version: str = "v1",
    ragas_version: str | None = None,
) -> dict:
    """组装完整 JSON 报告。"""
    per_question = [
        {
            "id": r.id,
            "question": r.question,
            "answer": r.answer,
            "contexts": r.contexts,
            "ground_truth": r.ground_truth,
            "source_file": r.source_file,
            "elapsed_ms": r.elapsed_ms,
        }
        for r in results
    ]

    return {
        "metadata": {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "dataset_version": dataset_version,
            "ragas_version": ragas_version,
            "model": "glm-4.5-air",  # 复用现有 LLM
            "n_questions": len(results),
            "strategy": "direct",
            "metrics": list(EVALUATION_METRICS),
            "score_definition": "mean(context_precision, context_recall)",
        },
        "aggregate": {name: metrics.get(name) for name in (*EVALUATION_METRICS, "ragas_score")},
        "per_question": per_question,
    }


def save_report(report: dict, path: str | Path) -> Path:
    """写 JSON 报告到磁盘。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return path


def print_table(metrics: dict, results: list[SampleResult] | None = None) -> None:
    """控制台打印聚合指标（可选：每题耗时统计）。"""
    import math

    print("\n" + "=" * 56)
    print("        RAGAS 评估报告 — SemiconRAG")
    print("=" * 56)

    metric_order = [
        ("ragas_score", "检索综合（两项均值）"),
        ("context_precision", "Context Precision (检索-信噪比)"),
        ("context_recall", "Context Recall (检索-覆盖率)"),
    ]

    def _fmt(v):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return "  N/A (无有效评分)"
        return f"{v:.4f}"

    def _bar(v):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return " " * 20 + " (skip)"
        n = int(v * 20)
        return "█" * n + "·" * (20 - n)

    for key, label in metric_order:
        v = metrics.get(key)
        print(f"  {label:<28} {_fmt(v)}  {_bar(v)}")

    print("-" * 56)

    if results:
        total_ms = sum(r.elapsed_ms for r in results)
        avg_ms = total_ms / len(results) if results else 0
        print(f"  题目数: {len(results)}    平均耗时: {avg_ms:.0f}ms    总耗时: {total_ms/1000:.1f}s")
    print("=" * 56 + "\n")
