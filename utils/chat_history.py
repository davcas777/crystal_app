"""SQLite-backed chat history store, scoped per user.

Each Databricks App pod gets its own ephemeral disk; SQLite at /tmp survives
restarts inside a pod and is sufficient for chat-style usage where conversations
are short-lived and per-user.  For permanent multi-pod history, point
`CHAT_HISTORY_DB_PATH` at a mounted volume or swap the store for a Delta table.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id           TEXT PRIMARY KEY,
    user_email   TEXT NOT NULL,
    endpoint     TEXT,
    title        TEXT,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_email, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    attachments     TEXT,
    created_at      REAL NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, created_at);
"""


class ChatHistoryStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            with self._lock:
                yield conn
                conn.commit()
        finally:
            conn.close()

    # -- conversations --------------------------------------------------
    def create_conversation(self, user_email: str, endpoint: str) -> str:
        cid = uuid.uuid4().hex
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversations (id, user_email, endpoint, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (cid, user_email, endpoint, None, now, now),
            )
        return cid

    def set_title(self, conversation_id: str, title: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, time.time(), conversation_id),
            )

    def list_conversations(self, user_email: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, endpoint, created_at, updated_at "
                "FROM conversations WHERE user_email = ? ORDER BY updated_at DESC",
                (user_email,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_conversation(self, conversation_id: str, user_email: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM messages WHERE conversation_id IN "
                "(SELECT id FROM conversations WHERE id = ? AND user_email = ?)",
                (conversation_id, user_email),
            )
            conn.execute(
                "DELETE FROM conversations WHERE id = ? AND user_email = ?",
                (conversation_id, user_email),
            )

    # -- messages -------------------------------------------------------
    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        attachments: list[str] | None = None,
    ) -> str:
        mid = uuid.uuid4().hex
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, attachments, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (mid, conversation_id, role, content, json.dumps(attachments or []), now),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
        return mid

    def list_messages(self, conversation_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, role, content, attachments, created_at FROM messages "
                "WHERE conversation_id = ? ORDER BY created_at ASC",
                (conversation_id,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["attachments"] = json.loads(d.get("attachments") or "[]")
            except json.JSONDecodeError:
                d["attachments"] = []
            result.append(d)
        return result

    def last_message_id(self, conversation_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM messages WHERE conversation_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
        return row["id"] if row else None
