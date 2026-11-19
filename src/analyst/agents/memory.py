"""Conversation memory in SQLite: pending clarification, prior plan and result, recent turns."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

HISTORY_TURNS = 5  # turns kept per conversation (intent v8; three in v7)
ANSWER_CHARS = 400  # each kept answer is cut to this length


class ConversationMemory:
    """Small local SQLite conversation store; no credentials or network identifiers are stored."""

    def __init__(self, path: str | Path = "outputs/runs/memory.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS memory (
                conversation_id TEXT PRIMARY KEY,
                pending_clarification TEXT,
                prior_plan TEXT,
                prior_sql TEXT,
                prior_result_ref TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""")
            columns = {row[1] for row in db.execute("PRAGMA table_info(memory)")}
            if "history" not in columns:  # databases from before the history column
                db.execute("ALTER TABLE memory ADD COLUMN history TEXT")

    def _connect(self) -> sqlite3.Connection:
        """Open a connection to the memory database."""
        return sqlite3.connect(self.path)

    def get(self, conversation_id: str) -> dict[str, Any]:
        """Return the stored state of a conversation, or empty values for a new one."""
        with self._connect() as db:
            row = db.execute(
                "SELECT pending_clarification, prior_plan, prior_sql, prior_result_ref, history "
                "FROM memory WHERE conversation_id=?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return {}
        return {
            "pending_clarification": json.loads(row[0]) if row[0] else None,
            "prior_plan": json.loads(row[1]) if row[1] else None,
            "prior_sql": row[2],
            "prior_result_ref": row[3],
            "history": json.loads(row[4]) if row[4] else [],
        }

    def save(
        self,
        conversation_id: str,
        *,
        pending_clarification: dict[str, Any] | None = None,
        prior_plan: dict[str, Any] | None = None,
        prior_sql: str | None = None,
        prior_result_ref: str | None = None,
        turn: dict[str, Any] | None = None,
    ) -> None:
        """Save the conversation context; `turn` is appended to the history (last five kept)."""
        history = self.get(conversation_id).get("history", []) if turn else None
        if turn is not None and history is not None:
            history = [*history, turn][-HISTORY_TURNS:]
        with self._connect() as db:
            db.execute(
                """INSERT INTO memory
                (conversation_id,pending_clarification,prior_plan,prior_sql,prior_result_ref,
                history,updated_at)
                VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(conversation_id) DO UPDATE SET
                pending_clarification=excluded.pending_clarification,
                prior_plan=COALESCE(excluded.prior_plan,memory.prior_plan),
                prior_sql=COALESCE(excluded.prior_sql,memory.prior_sql),
                prior_result_ref=COALESCE(excluded.prior_result_ref,memory.prior_result_ref),
                history=COALESCE(excluded.history,memory.history),
                updated_at=CURRENT_TIMESTAMP""",
                (
                    conversation_id,
                    json.dumps(pending_clarification) if pending_clarification else None,
                    json.dumps(prior_plan) if prior_plan else None,
                    prior_sql,
                    prior_result_ref,
                    json.dumps(history, ensure_ascii=False) if history is not None else None,
                ),
            )
