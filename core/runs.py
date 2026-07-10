"""
SQLite-backed execution history (MasExecution-style, local single-operator).

DB path is always under the MultiAgent install tree (not the caller's cwd),
so ``multiagent`` works from any directory.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "runs.db"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunHistory:
    """Thread-safe log of MAS pipeline executions."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        if not self._db_path.is_absolute():
            self._db_path = (_PROJECT_ROOT / self._db_path).resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=5.0)
        # Ensure schema exists on every connection (handles empty/partial files).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mas_executions (
                id            TEXT PRIMARY KEY,
                system        TEXT NOT NULL,
                input_summary TEXT NOT NULL,
                status        TEXT NOT NULL,
                result_summary TEXT,
                error         TEXT,
                meta_json     TEXT,
                created_at    TEXT NOT NULL,
                finished_at   TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mas_exec_created "
            "ON mas_executions(created_at DESC)"
        )
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.commit()

    def start(
        self,
        system: str,
        input_summary: str,
        meta: Optional[dict[str, Any]] = None,
    ) -> str:
        """Insert a running row; return its id."""
        run_id = str(uuid.uuid4())
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mas_executions
                    (id, system, input_summary, status, meta_json, created_at)
                VALUES (?, ?, ?, 'running', ?, ?)
                """,
                (
                    run_id,
                    system,
                    input_summary[:2000],
                    json.dumps(meta or {}, ensure_ascii=False),
                    _utcnow(),
                ),
            )
            conn.commit()
        return run_id

    def finish(
        self,
        run_id: str,
        *,
        status: str,
        result_summary: Optional[str] = None,
        error: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        """Mark a run as completed / failed / aborted."""
        with self._lock, self._connect() as conn:
            if meta is not None:
                conn.execute(
                    """
                    UPDATE mas_executions
                    SET status = ?, result_summary = ?, error = ?,
                        meta_json = ?, finished_at = ?
                    WHERE id = ?
                    """,
                    (
                        status,
                        (result_summary or "")[:4000] or None,
                        (error or "")[:2000] if error else None,
                        json.dumps(meta, ensure_ascii=False),
                        _utcnow(),
                        run_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE mas_executions
                    SET status = ?, result_summary = ?, error = ?, finished_at = ?
                    WHERE id = ?
                    """,
                    (
                        status,
                        (result_summary or "")[:4000] or None,
                        (error or "")[:2000] if error else None,
                        _utcnow(),
                        run_id,
                    ),
                )
            conn.commit()

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return newest runs first."""
        with self._lock, self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, system, input_summary, status, result_summary,
                       error, meta_json, created_at, finished_at
                FROM mas_executions
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            if item.get("meta_json"):
                try:
                    item["meta"] = json.loads(item["meta_json"])
                except json.JSONDecodeError:
                    item["meta"] = {}
            else:
                item["meta"] = {}
            del item["meta_json"]
            out.append(item)
        return out


_default_history: Optional[RunHistory] = None


def get_run_history(db_path: Optional[Path] = None) -> RunHistory:
    global _default_history
    if db_path is not None:
        return RunHistory(db_path=db_path)
    if _default_history is None:
        _default_history = RunHistory()
    return _default_history
