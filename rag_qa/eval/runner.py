# rag_qa/eval/runner.py
# 评估运行器：对每个 EvalSample 跑 RAG → 收集 (question, answer, contexts, gt, gt_contexts)
# → 喂 ragas.evaluate 计算上下文精确度与召回率。
import math
import os
import time
from dataclasses import dataclass

from datasets import Dataset

from base.config import config
from base.logger import logger
from rag_qa.core.generator import Generator
from rag_qa.core.retriever import Retriever
from rag_qa.eval.dataset import EvalDataset, EvalSample

# 抑制 ragas / langchain 的 telemetry
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")

EVALUATION_METRICS = ("context_precision", "context_recall")


@dataclass
class SampleResult:
    """单条评估结果（不进入 ragas，只用于报告）。"""

    id: str
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str
    ground_truth_contexts: list[str]
    source_file: str
    elapsed_ms: float
    rag_domain: str = ""          # RAG 路由结果
    rag_strategy: str = ""


def _run_rag_for_sample(sample: EvalSample, retriever: Retriever, generator: Generator) -> SampleResult:
    """对单条样本跑 RAG：direct 策略检索 → LLM 生成答案。"""
    start = time.time()
    parent_docs = retriever.retrieve(sample.question, strategy="direct")
    contexts = [d.page_content for d in parent_docs]
    context_str = "\n\n---\n\n".join(contexts)
    if context_str:
        answer = generator.generate(context_str, sample.question)
    else:
        answer = "抱歉，当前知识库中没有与该问题相关的内容。"
    elapsed_ms = round((time.time() - start) * 1000, 1)

    return SampleResult(
        id=sample.id,
        question=sample.question,
        answer=answer,
        contexts=contexts,
        ground_truth=sample.ground_truth,
        ground_truth_contexts=sample.ground_truth_contexts,
        source_file=sample.source_file,
        elapsed_ms=elapsed_ms,
    )


def _to_ragas_dataset(results: list[SampleResult]) -> Dataset:
    """把 SampleResult 转成 ragas 的 Dataset。ragas 0.2.x 用 HuggingFace datasets。"""
    return Dataset.from_list([
        {
            "question": r.question,
            "answer": r.answer,
            "contexts": r.contexts,
            "ground_truth": r.ground_truth,
            "ground_truth_contexts": r.ground_truth_contexts,
        }
        for r in results
    ])


def _build_ragas_llm():
    """包装现有 LLM 配置为 langchain ChatOpenAI，供 ragas 使用。"""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        base_url=config.DASHSCOPE_BASE_URL,
        api_key=config.DASHSCOPE_API_KEY,
        model=config.LLM_MODEL,
        timeout=config.LLM_TIMEOUT,
        temperature=0.0,  # 评估要确定性
    )


class _RetryLLM:
    """包装 ChatOpenAI，给 invoke 方法加 tenacity retry。

    ragas 0.2.x 内部用 llm.invoke(prompt) 调用 LLM，所以我们包一层。
    Pydantic 2 禁止给 ChatOpenAI 实例直接设属性，所以用 wrapper。
    """

    def __init__(self, inner, max_attempts: int = 3):
        self._inner = inner
        import openai
        from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

        self._retry = retry(
            retry=retry_if_exception_type((
                openai.RateLimitError,
                openai.APITimeoutError,
                openai.APIConnectionError,
            )),
            wait=wait_exponential(multiplier=2, min=4, max=30),
            stop=stop_after_attempt(max_attempts),
            reraise=True,
        )(inner.invoke)

    def invoke(self, *args, **kwargs):
        return self._retry(*args, **kwargs)

    def __getattr__(self, name):
        # 透传其他属性（ragas 可能还会读 .model_name 等）
        return getattr(self._inner, name)


def _build_ragas_llm_with_retry():
    """包装为 ragas 的 LangchainLLMWrapper，规避 zhipu 限速/超时。"""
    from langchain_openai import ChatOpenAI
    from ragas.llms import LangchainLLMWrapper

    inner = ChatOpenAI(
        base_url=config.DASHSCOPE_BASE_URL,
        api_key=config.DASHSCOPE_API_KEY,
        model=config.LLM_MODEL,
        timeout=config.LLM_TIMEOUT,
        temperature=0.0,
    )

    # 给 langchain 的 invoke 加 retry（ragas 用 LangchainLLMWrapper.invoke 间接调到这里）
    import openai
    from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

    retry_decorator = retry(
        retry=retry_if_exception_type((
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.APIConnectionError,
        )),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )

    # 关键：ChatOpenAI 是 BaseChatModel 子类，用 monkey-patch 类的 _generate 方法不可行，
    # 但可以用子类方式覆盖 invoke。简单点：直接在 LangchainLLMWrapper 的 invoke 路径上加 retry。
    # 这里采用 Pydantic v2 兼容方案：扩展 ChatOpenAI 子类覆盖 invoke
    class _RetryingChatOpenAI(ChatOpenAI):
        def invoke(self, input, *args, **kwargs):
            return retry_decorator(super().invoke)(input, *args, **kwargs)

    # 上面 `ChatOpenAI(base_url=..., ...)` 已实例化一次；改成重建子类的实例
    retrying_inner = _RetryingChatOpenAI(
        base_url=inner.openai_api_base,
        api_key=inner.openai_api_key.model_dump()["api_key"] if hasattr(inner.openai_api_key, "model_dump") else inner.openai_api_key.get_secret_value() if hasattr(inner.openai_api_key, "get_secret_value") else str(inner.openai_api_key),
        model=inner.model_name,
        temperature=0.0,
        timeout=config.LLM_TIMEOUT,
    )

    return LangchainLLMWrapper(retrying_inner)


def run_eval(
    dataset: EvalDataset,
    limit: int | None = None,
    progress: bool = True,
) -> tuple[list[SampleResult], dict]:
    """跑评估。

    Returns:
        (per_sample_results, metrics_dict)
        metrics_dict 形如:
            {
                "context_precision": 0.74,
                "context_recall": 0.72,
                "ragas_score": 0.73,    # 两项检索指标的算术平均；缺项时为 None
            }
    """
    from ragas import evaluate
    from ragas.metrics import context_precision, context_recall

    samples = dataset.samples
    if limit is not None and limit > 0:
        samples = samples[:limit]

    logger.info(f"开始评估：{len(samples)} 道题")

    # 阶段 1：跑 RAG 收集样本
    retriever = Retriever()
    generator = Generator()

    results: list[SampleResult] = []
    for i, s in enumerate(samples, 1):
        try:
            r = _run_rag_for_sample(s, retriever, generator)
            results.append(r)
            if progress:
                logger.info(f"[{i:02d}/{len(samples)}] {s.id} ({s.source_file}) - {r.elapsed_ms}ms")
        except Exception as e:
            logger.error(f"[{i:02d}] {s.id} 失败: {e}")
            # 即便失败也占位，避免错位
            results.append(SampleResult(
                id=s.id,
                question=s.question,
                answer=f"[评估出错: {e}]",
                contexts=[],
                ground_truth=s.ground_truth,
                ground_truth_contexts=s.ground_truth_contexts,
                source_file=s.source_file,
                elapsed_ms=0.0,
            ))

    # 阶段 2：ragas 评分
    ragas_ds = _to_ragas_dataset(results)
    llm = _build_ragas_llm_with_retry()

    metrics_list = [context_precision, context_recall]
    logger.info("调用 ragas.evaluate ...")
    eval_result = evaluate(
        dataset=ragas_ds,
        metrics=metrics_list,
        llm=llm,
        raise_exceptions=False,  # 部分失败不中断，让能算的指标先出
    )

    # ragas 0.2.x 返回 EvaluationResult，含聚合分数 _repr_dict。
    # 无效指标保存为 JSON null，只有两项都有有效分数时才计算综合分。
    aggregate = getattr(eval_result, "_repr_dict", {})
    metrics_dict: dict[str, float | None] = {}
    for name in EVALUATION_METRICS:
        value = aggregate.get(name)
        score = float(value) if value is not None else None
        metrics_dict[name] = score if score is not None and math.isfinite(score) else None
    scores = [metrics_dict[name] for name in EVALUATION_METRICS]
    metrics_dict["ragas_score"] = (
        round(sum(scores) / len(scores), 4)
        if all(score is not None for score in scores) else None
    )

    logger.info(f"评估完成: {metrics_dict}")
    return results, metrics_dict
