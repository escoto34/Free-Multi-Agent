"""
Persistent SQLite-backed quota counters with automatic daily reset.

Limits (safe margins — see ``config/model_router.yaml`` for rationale):

  +--------------+-----+-----------------------------------------------+
  | Provider     | RPD | Scope                                         |
  +--------------+-----+-----------------------------------------------+
  | Groq         | 800 | Per model (independent counters)               |
  | OpenRouter   |  45 | SHARED across all ``:free`` models on account  |
  | Cohere       |  28 | SHARED across all endpoints                    |
  +--------------+-----+-----------------------------------------------+

Daily reset is **implicit**: queries filter by ``date.today()``, so a new day
automatically starts at zero without needing a cron job or background thread.

WARNING — LEGAL, NOT TECHNICAL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The Cohere trial/free tier is **contractually non-commercial use only**.
This is not merely a rate-limit — it is a binding restriction in Cohere's
Terms of Service (https://cohere.com/terms-of-use).  Any commercial or
production deployment requires a paid plan.  This codebase does NOT enforce
that restriction programmatically; compliance is the user's responsibility.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import date
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Default safe-margin limits
# ---------------------------------------------------------------------------
GROQ_DAILY_LIMIT_PER_MODEL: int = 800   # 80 % of real ~1 000 RPD
OPENROUTER_DAILY_LIMIT: int = 45         # 90 % of real ~50 RPD (shared)
COHERE_DAILY_LIMIT: int = 28             # Conservative midpoint 25-30/day

_DEFAULT_DB_PATH = Path("data/quotas.db")


class QuotaTracker:
    """Thread-safe, SQLite-backed quota tracker with automatic daily reset.

    Usage::

        tracker = QuotaTracker()
        if tracker.can_call("groq", "openai/gpt-oss-120b"):
            # ... make the call ...
            tracker.record_call("groq", "openai/gpt-oss-120b")

    The database file is created automatically on first use.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Create the usage table if it doesn't exist yet."""
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS quota_usage (
                    provider   TEXT    NOT NULL,
                    quota_key  TEXT    NOT NULL,
                    usage_date TEXT    NOT NULL,
                    call_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (provider, quota_key, usage_date)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        """Open a connection to the quota database."""
        return sqlite3.connect(str(self._db_path), timeout=5.0)

    @staticmethod
    def _today() -> str:
        """ISO-formatted current date for partitioning."""
        return date.today().isoformat()

    @staticmethod
    def _quota_key(provider: str, model: str) -> str:
        """Determine the tracking key for a (provider, model) pair.

        * **Groq** — each model has its own independent daily budget, so the
          key is the model name itself.
        * **OpenRouter** — all ``:free`` models share a single daily budget,
          so the key collapses to ``__shared__``.
        * **Cohere** — all endpoints share a single daily budget, so the key
          collapses to ``__shared__``.
        """
        if provider == "groq":
            return model
        return "__shared__"

    @staticmethod
    def _limit_for(provider: str) -> int:
        """Return the daily limit for *provider*.

        For Groq the limit is *per model*; for the others it is *per account*.
        """
        limits = {
            "groq": GROQ_DAILY_LIMIT_PER_MODEL,
            "openrouter": OPENROUTER_DAILY_LIMIT,
            "cohere": COHERE_DAILY_LIMIT,
        }
        limit = limits.get(provider)
        if limit is None:
            raise ValueError(
                f"Unknown provider: {provider!r}. "
                f"Valid: {sorted(limits)}"
            )
        return limit

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_usage(self, provider: str, model: str) -> int:
        """Return today's call count for *provider*/*model*."""
        key = self._quota_key(provider, model)
        today = self._today()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT call_count FROM quota_usage "
                "WHERE provider = ? AND quota_key = ? AND usage_date = ?",
                (provider, key, today),
            ).fetchone()
        return row[0] if row else 0

    def remaining(self, provider: str, model: str) -> int:
        """Return how many calls remain today for *provider*/*model*."""
        return self._limit_for(provider) - self.get_usage(provider, model)

    def can_call(self, provider: str, model: str) -> bool:
        """Check whether a call is allowed within today's quota."""
        return self.remaining(provider, model) > 0

    def record_call(self, provider: str, model: str) -> None:
        """Record a successful API call, incrementing today's counter."""
        key = self._quota_key(provider, model)
        today = self._today()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO quota_usage (provider, quota_key, usage_date, call_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT (provider, quota_key, usage_date)
                DO UPDATE SET call_count = call_count + 1
                """,
                (provider, key, today),
            )

    def reset(self, provider: Optional[str] = None) -> None:
        """Manually wipe today's counters.  Useful for testing.

        If *provider* is given, only that provider's counters are cleared;
        otherwise **all** providers' counters for today are cleared.
        """
        today = self._today()
        with self._lock, self._connect() as conn:
            if provider:
                conn.execute(
                    "DELETE FROM quota_usage "
                    "WHERE provider = ? AND usage_date = ?",
                    (provider, today),
                )
            else:
                conn.execute(
                    "DELETE FROM quota_usage WHERE usage_date = ?",
                    (today,),
                )

    def status_summary(self) -> dict[str, dict[str, int]]:
        """Return a snapshot of today's remaining quotas for all providers.

        Returns a dict like::

            {
                "groq/openai/gpt-oss-120b": {"used": 12, "remaining": 788},
                "openrouter/__shared__": {"used": 3, "remaining": 42},
                "cohere/__shared__": {"used": 1, "remaining": 27},
            }
        """
        today = self._today()
        result: dict[str, dict[str, int]] = {}
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT provider, quota_key, call_count "
                "FROM quota_usage WHERE usage_date = ?",
                (today,),
            ).fetchall()
        for provider, key, count in rows:
            limit = self._limit_for(provider)
            label = f"{provider}/{key}"
            result[label] = {"used": count, "remaining": limit - count}
        return result
