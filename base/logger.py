# base/logger.py
# 统一日志：控制台 + 文件双输出，避免重复注册 handler
import logging
import os

from .config import config


def setup_logging():
    logger = logging.getLogger("V93KRAG")
    logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))

    if not logger.handlers:
        os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)

        fmt = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(fmt)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(fmt)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger


logger = setup_logging()
