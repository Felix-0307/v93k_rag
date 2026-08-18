# rag_qa/chat_history.py
# 会话历史 + 摘要：MySQL 持久化，s_<uuid8> 作为 session_id。
#
# 表结构（启动时自动建库建表）：
#   sessions:  每次一问一答 = 1 行
#   summaries: 每个 session 一条最新摘要
import json
import uuid
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from base.config import config
from base.logger import logger

_RECENT_N = 3  # 传给 LLM 的最近轮数


def new_session_id() -> str:
    """生成 s_<uuid8> 形式的 session id（用户首次访问时由后端生成）。"""
    return "s_" + uuid.uuid4().hex[:8]


class ChatHistory:
    """MySQL 会话历史管理器（单例懒加载）。"""

    def __init__(self):
        self._conn_params = {
            "host": config.MYSQL_HOST,
            "port": config.MYSQL_PORT,
            "user": config.MYSQL_USER,
            "password": config.MYSQL_PASSWORD,
            "charset": "utf8mb4",
            "autocommit": False,
            "cursorclass": DictCursor,
        }
        self._database = config.MYSQL_DATABASE
        try:
            self._init_db()  # 建库 + 建表（MySQL 未起时仅 warning，不阻塞启动）
        except Exception as e:
            logger.warning(
                f"MySQL 不可用，会话历史功能将不可用（不影响 RAG 启动）: {type(e).__name__}: {e}"
            )

    # ---------- 连接管理 ----------
    def _connect(self, with_db: bool = True):
        params = dict(self._conn_params)
        if with_db:
            params["database"] = self._database
        # 防止 MySQL 不可用时连接无限阻塞（首次请求会卡在 TCP 超时）
        params.setdefault("connect_timeout", 3)
        params.setdefault("read_timeout", 10)
        params.setdefault("write_timeout", 10)
        return pymysql.connect(**params)

    def _init_db(self):
        """启动时确保数据库 + 表存在（首次自动建）。"""
        # 1) 建数据库（无 database 也能连）
        conn = self._connect(with_db=False)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{self._database}` "
                    f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            conn.commit()
        finally:
            conn.close()

        # 2) 建表（在目标库内）
        conn = self._connect(with_db=True)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        id          BIGINT AUTO_INCREMENT PRIMARY KEY,
                        session_id  VARCHAR(64) NOT NULL,
                        question    TEXT NOT NULL,
                        answer      TEXT NOT NULL,
                        domain      VARCHAR(32),
                        strategy    VARCHAR(32),
                        sources     JSON,
                        elapsed_ms  FLOAT,
                        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_session_created (session_id, created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS summaries (
                        session_id  VARCHAR(64) PRIMARY KEY,
                        summary     TEXT NOT NULL,
                        turn_count  INT NOT NULL,
                        updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
            conn.commit()
        finally:
            conn.close()
        logger.info(f"MySQL 就绪: {config.MYSQL_HOST}:{config.MYSQL_PORT}/{self._database}")

    # ---------- 写 ----------
    def save_turn(
        self,
        session_id: str,
        question: str,
        answer: str,
        domain: str | None = None,
        strategy: str | None = None,
        sources: list[str] | None = None,
        elapsed_ms: float | None = None,
    ) -> None:
        """存一次问答到 sessions 表。"""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO sessions
                       (session_id, question, answer, domain, strategy, sources, elapsed_ms)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (
                        session_id, question, answer, domain, strategy,
                        json.dumps(sources or [], ensure_ascii=False),
                        elapsed_ms,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def update_summary(self, session_id: str, summary: str, turn_count: int) -> None:
        """upsert summaries 表（覆盖式）。"""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO summaries (session_id, summary, turn_count)
                       VALUES (%s, %s, %s)
                       ON DUPLICATE KEY UPDATE summary=VALUES(summary), turn_count=VALUES(turn_count)""",
                    (session_id, summary, turn_count),
                )
            conn.commit()
        finally:
            conn.close()

    # ---------- 读 ----------
    def get_recent_turns(self, session_id: str, n: int = _RECENT_N) -> list[dict]:
        """取最近 n 条 Q&A（按时间倒序，转成正序返回）。"""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT question, answer, created_at
                       FROM sessions WHERE session_id = %s
                       ORDER BY created_at DESC, id DESC LIMIT %s""",
                    (session_id, n),
                )
                rows = list(reversed(cur.fetchall()))
            return rows
        finally:
            conn.close()

    def get_summary(self, session_id: str) -> str | None:
        """取该 session 的最新摘要；没有则 None。"""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT summary FROM summaries WHERE session_id = %s",
                    (session_id,),
                )
                row = cur.fetchone()
            return row["summary"] if row else None
        finally:
            conn.close()

    def get_old_turns(self, session_id: str, n: int = _RECENT_N) -> list[dict]:
        """取**老于最近 n 条**的 Q&A（按时间正序），用于摘要重建。"""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT question, answer
                       FROM (
                         SELECT question, answer, created_at, id,
                                ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY created_at DESC, id DESC) AS rn
                         FROM sessions WHERE session_id = %s
                       ) t WHERE rn > %s ORDER BY created_at, id""",
                    (session_id, n),
                )
                return cur.fetchall()
        finally:
            conn.close()

    # ---------- 拼装 ----------
    def get_context(self, session_id: str, n: int = _RECENT_N) -> dict[str, Any]:
        """拼 LLM 上下文：摘要 + 最近 n 轮。

        返回：
            {
                "summary": str | None,    # 老于最近 n 条的对话摘要
                "recent": [                # 最近 n 条 Q&A（按时间正序）
                    {"question": ..., "answer": ..., "created_at": ...},
                    ...
                ],
                "has_history": bool,        # 是否有任何历史（用于路由决策）
            }
        """
        summary = self.get_summary(session_id)
        recent = self.get_recent_turns(session_id, n=n)
        return {
            "summary": summary,
            "recent": recent,
            "has_history": bool(summary or recent),
        }


# ---------- 单例 ----------
_history: ChatHistory | None = None


def get_chat_history() -> ChatHistory:
    global _history
    if _history is None:
        _history = ChatHistory()
    return _history