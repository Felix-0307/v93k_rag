#!/usr/bin/env python3
"""scripts/run_eval.py — SemiconRAG 评估入口。

用法:
  D:/Anaconda/envs/DL_Pytorch_CUDA/python.exe scripts/run_eval.py
  D:/Anaconda/envs/DL_Pytorch_CUDA/python.exe scripts/run_eval.py --limit 2
  D:/Anaconda/envs/DL_Pytorch_CUDA/python.exe scripts/run_eval.py --dataset data/eval/other.json
"""
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# 让脚本能 import 项目根目录的包
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 抑制 langchain / ragas telemetry
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")

from rag_qa.eval import (
    build_report,
    load_dataset,
    print_table,
    run_eval,
    save_report,
)


def main():
    parser = argparse.ArgumentParser(description="RAGAS 评估 SemiconRAG")
    parser.add_argument(
        "--dataset",
        type=str,
        default=str(PROJECT_ROOT / "data" / "eval" / "semicon_qa_v1.json"),
        help="评估集 JSON 路径",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="只跑前 N 道（用于冒烟测试）",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="报告输出路径（默认 data/eval/report_<timestamp>.json）",
    )
    args = parser.parse_args()

    print(f"加载评估集: {args.dataset}")
    dataset = load_dataset(args.dataset)
    print(f"  共 {len(dataset.samples)} 道题，version={dataset.version}")

    results, metrics = run_eval(dataset, limit=args.limit)

    # 写报告
    if args.out:
        out_path = Path(args.out)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = PROJECT_ROOT / "data" / "eval" / f"report_{ts}.json"

    report = build_report(
        results=results,
        metrics=metrics,
        dataset_version=dataset.version,
    )
    saved = save_report(report, out_path)
    print(f"报告已保存: {saved}")

    # 控制台汇总
    print_table(metrics, results)


if __name__ == "__main__":
    main()
