# base/config.py
# 配置单例：读取 config.ini，支持环境变量覆盖敏感项
import configparser
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _path(p):
    """相对项目根的路径 → 规范化绝对路径"""
    abs_p = p if os.path.isabs(p) else os.path.join(PROJECT_ROOT, p)
    return os.path.normpath(abs_p)


class Config:
    def __init__(self, config_file=None):
        self.PROJECT_ROOT = PROJECT_ROOT
        if config_file is None:
            config_file = os.path.join(PROJECT_ROOT, "config.ini")

        self.config = configparser.ConfigParser(
            interpolation=configparser.ExtendedInterpolation()
        )
        self.config.read(config_file, encoding="utf-8")

        # ---------- LLM（DashScope OpenAI 兼容接口）----------
        self.LLM_MODEL = self.config.get("llm", "model", fallback="qwen-plus")
        self.DASHSCOPE_API_KEY = os.getenv(
            "DASHSCOPE_API_KEY",
            self.config.get("llm", "dashscope_api_key", fallback=""),
        )
        self.DASHSCOPE_BASE_URL = self.config.get(
            "llm", "dashscope_base_url",
            fallback="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.LLM_TEMPERATURE = self.config.getfloat("llm", "temperature", fallback=0.3)
        self.STRATEGY_TEMPERATURE = self.config.getfloat(
            "llm", "strategy_temperature", fallback=0.1
        )

        # ---------- Embedding（bge-m3，本地 FlagEmbedding）----------
        self.EMBEDDING_MODEL_DIR = _path(
            self.config.get("embedding", "model_dir", fallback="./models/bge-m3")
        )
        self.EMBEDDING_DEVICE = self.config.get("embedding", "device", fallback="cpu")
        self.EMBEDDING_USE_FP16 = self.config.getboolean("embedding", "use_fp16", fallback=False)
        self.EMBEDDING_MAX_LENGTH = self.config.getint("embedding", "max_length", fallback=512)

        # ---------- Chroma ----------
        self.CHROMA_PERSIST_DIR = _path(
            self.config.get("chroma", "persist_dir", fallback="./chroma_data")
        )
        self.CHROMA_COLLECTION_NAME = self.config.get(
            "chroma", "collection_name", fallback="v93k_kb"
        )
        self.CHROMA_PARENTS_COLLECTION_NAME = self.config.get(
            "chroma", "parents_collection_name", fallback="v93k_kb_parents"
        )
        self.CHROMA_DISTANCE_METRIC = self.config.get(
            "chroma", "distance_metric", fallback="cosine"
        )

        # ---------- 检索参数 ----------
        self.PARENT_CHUNK_SIZE = self.config.getint(
            "retrieval", "parent_chunk_size", fallback=1200
        )
        self.CHILD_CHUNK_SIZE = self.config.getint(
            "retrieval", "child_chunk_size", fallback=300
        )
        self.CHUNK_OVERLAP = self.config.getint(
            "retrieval", "chunk_overlap", fallback=50
        )
        self.RETRIEVAL_K = self.config.getint("retrieval", "retrieval_k", fallback=5)
        self.CANDIDATE_M = self.config.getint("retrieval", "candidate_m", fallback=3)
        self.FAQ_SIMILARITY_THRESHOLD = self.config.getfloat(
            "retrieval", "faq_similarity_threshold", fallback=0.35
        )

        # ---------- Rerank（BGE-Reranker-Large，引用 EduRag 本地权重）----------
        self.RERANK_ENABLED = self.config.getboolean("rerank", "enabled", fallback=False)
        self.RERANK_MODEL_PATH = self.config.get(
            "rerank", "model_path",
            fallback="D:/workspace/python/RAG_project/learning/EduRag/rag_qa/models/bge-reranker-large",
        )
        self.RERANK_DEVICE = self.config.get("rerank", "device", fallback="cpu")
        self.RERANK_USE_FP16 = self.config.getboolean("rerank", "use_fp16", fallback=False)

        # ---------- OCR ----------
        self.OCR_USE_CUDA = self.config.getboolean("ocr", "use_cuda", fallback=False)
        self.OCR_PDF_IMAGE_THRESHOLD = self.config.getfloat(
            "ocr", "pdf_image_threshold", fallback=0.6
        )

        # ---------- 应用 ----------
        self.APP_HOST = self.config.get("app", "host", fallback="0.0.0.0")
        self.APP_PORT = self.config.getint("app", "port", fallback=8000)
        self.DATA_DIR = _path(self.config.get("app", "data_dir", fallback="./data"))

        # ---------- LLM 超时 ----------
        self.LLM_TIMEOUT = self.config.getfloat("llm", "timeout", fallback=30.0)

        # ---------- 日志 ----------
        self.LOG_FILE = _path(self.config.get("logger", "log_file", fallback="logs/app.log"))
        self.LOG_LEVEL = self.config.get("logger", "log_level", fallback="INFO")

        # ---------- MySQL（会话历史持久化）----------
        # 敏感字段支持环境变量覆盖
        self.MYSQL_HOST = os.getenv("MYSQL_HOST", self.config.get("mysql", "host", fallback="localhost"))
        self.MYSQL_PORT = int(os.getenv("MYSQL_PORT", self.config.get("mysql", "port", fallback="3306")))
        self.MYSQL_USER = os.getenv("MYSQL_USER", self.config.get("mysql", "user", fallback="root"))
        self.MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", self.config.get("mysql", "password", fallback=""))
        self.MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", self.config.get("mysql", "database", fallback="v93k_rag"))


config = Config()
