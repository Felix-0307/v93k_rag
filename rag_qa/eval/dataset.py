# rag_qa/eval/dataset.py
# 评估集 schema + loader
import json
from pathlib import Path

from pydantic import BaseModel, Field


class EvalSample(BaseModel):
    """单条评估样本。"""

    id: str = Field(..., description="样本 ID，如 q001")
    question: str
    ground_truth: str = Field("", description="标准答案（用于上下文精确度与召回率评分）")
    ground_truth_contexts: list[str] = Field(
        default_factory=list,
        description="参考上下文片段（保留用于人工核查，当前指标不直接使用）",
    )
    source_file: str = Field("", description="题目对应的 KB 来源文件名（仅用于统计）")


class EvalDataset(BaseModel):
    """完整评估集。"""

    version: str = "v1"
    source: str = "manual"
    description: str = ""
    samples: list[EvalSample]


def load_dataset(path: str | Path) -> EvalDataset:
    """从 JSON 文件加载评估集。"""
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return EvalDataset(**raw)


def save_dataset(dataset: EvalDataset, path: str | Path) -> None:
    """保存评估集到 JSON 文件。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dataset.model_dump(), f, ensure_ascii=False, indent=2)
