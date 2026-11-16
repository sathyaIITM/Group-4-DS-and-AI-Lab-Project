from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Any

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

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def get(self, conversation_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute(
                "SELECT pending_clarification, prior_plan, prior_sql, prior_result_ref "
                "FROM memory WHERE conversation_id=?", (conversation_id,)
            ).fetchone()
        if row is None:
            return {}
        return {
            "pending_clarification": json.loads(row[0]) if row[0] else None,
            "prior_plan": json.loads(row[1]) if row[1] else None,
            "prior_sql": row[2],
            "prior_result_ref": row[3],
        }

    def save(self, conversation_id: str, *, pending_clarification: dict | None = None,
             prior_plan: dict | None = None, prior_sql: str | None = None,
             prior_result_ref: str | None = None) -> None:
        with self._connect() as db:
            db.execute("""INSERT INTO memory
                (conversation_id,pending_clarification,prior_plan,prior_sql,prior_result_ref,updated_at)
                VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(conversation_id) DO UPDATE SET
                pending_clarification=excluded.pending_clarification,
                prior_plan=COALESCE(excluded.prior_plan,memory.prior_plan),
                prior_sql=COALESCE(excluded.prior_sql,memory.prior_sql),
                prior_result_ref=COALESCE(excluded.prior_result_ref,memory.prior_result_ref),
                updated_at=CURRENT_TIMESTAMP""",
                (conversation_id, json.dumps(pending_clarification) if pending_clarification else None,
                 json.dumps(prior_plan) if prior_plan else None, prior_sql, prior_result_ref))
