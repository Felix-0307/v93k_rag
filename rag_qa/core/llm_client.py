# rag_qa/core/llm_client.py
# GLM-4.5-Air（OpenAI 兼容协议）LLM 客户端封装。
# API Key 解析顺序：环境变量 GLM_API_KEY > config.ini
import os

# 修复 SSL 证书路径：系统 SSL_CERT_FILE 指向不存在的 conda 环境时，用 certifi 的证书
if "SSL_CERT_FILE" in os.environ and not os.path.isfile(os.environ["SSL_CERT_FILE"]):
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
    except ImportError:
        del os.environ["SSL_CERT_FILE"]

from openai import OpenAI

from base.config import config
from base.logger import logger


def _resolve_api_key() -> str:
    """API Key 解析顺序：环境变量 > config.ini"""
    if config.DASHSCOPE_API_KEY:
        return config.DASHSCOPE_API_KEY


class LLMClient:
    """统一 LLM 调用入口：chat 补全 + JSON 解析。"""

    def __init__(self):
        api_key = _resolve_api_key()
        if not api_key:
            logger.warning("未找到 DashScope API Key，LLM 调用将失败")
        self.client = OpenAI(
            api_key=api_key,
            base_url=config.DASHSCOPE_BASE_URL,
            timeout=config.LLM_TIMEOUT,
        )

    def chat(self, prompt: str, temperature: float | None = None,
             system: str = "你是半导体工艺知识库助手。回答需依据提供的资料，不编造产线参数。") -> str:
        """单轮对话，失败时抛异常由上层兜底。"""
        completion = self.client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=config.LLM_TEMPERATURE if temperature is None else temperature,
            timeout=config.LLM_TIMEOUT,
        )
        return completion.choices[0].message.content or ""

    def chat_stream(self, prompt: str, temperature: float | None = None,
                    system: str = "你是半导体工艺知识库助手。回答需依据提供的资料，不编造产线参数。"):
        """流式对话：逐 chunk 产出 delta 文本（generator）。"""
        stream = self.client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=config.LLM_TEMPERATURE if temperature is None else temperature,
            timeout=config.LLM_TIMEOUT,
            stream=True,
        )
        for chunk in stream:
            try:
                delta = chunk.choices[0].delta.content
            except (AttributeError, IndexError):
                delta = None
            if delta:
                yield delta

    def chat_json(self, prompt: str, temperature: float | None = None,
                  fallback: dict | None = None) -> dict:
        """调用并解析 JSON 响应，解析失败返回 fallback。"""
        try:
            raw = self.chat(prompt, temperature=temperature)
            return _parse_json(raw) or fallback or {}
        except Exception as e:
            logger.error(f"LLM JSON 调用失败: {e}")
            return fallback or {}


def _parse_json(raw: str) -> dict | None:
    """容错 JSON 解析：用正则匹配最外层 {...}，避免嵌套场景下 find/rfind 错位。"""
    import json
    import re
    raw = raw.strip()
    # 1) 直接尝试
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 2) 截取最外层大括号（非贪婪：第一个 { 到配对的最后一个 }）
    m = re.search(r"\{(?:[^{}]|\{[^{}]*\})*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None


# 全局单例（懒加载）
_llm_client = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
