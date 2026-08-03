"""
Persistent SQLite-backed quota counters with automatic daily reset.

Limits are read from ``config/model_router.yaml`` at call time via
``core.agent_config.get_agent_config`` — the YAML is the single source of
truth. The constants below (``GROQ_DAILY_LIMIT_PER_MODEL`` etc.) are kept
only as a fallback for environments where the YAML isn't available (e.g.
some unit tests that construct a ``QuotaTracker`` without a full project
checkout) — if the YAML load succeeds, its values always win.

  +--------------+------+-----------------------------------------------+
  | Provider     | RPD  | Scope                                         |
  +--------------+------+-----------------------------------------------+
  | Groq         |  800 | Per model (independent; compound-mini ~250 real)|
  | OpenRouter   |   45 | SHARED across all ``:free`` models on account |
  | Cohere       |   28 | SHARED across all endpoints                   |
  | Mistral      |  200 | Shared experiment tier (conservative)         |
  | Gemini       |  400 | AI Studio Flash-class (varies by model)       |
  | Cerebras     |  150 | Free ~5 RPM / ~1M TPD (call soft-cap)         |
  | Agnes        | 2000 | Free fair-use ~20 RPM text; soft local cap    |
  | Ollama       | 100k | Local — effectively unlimited                 |
  +--------------+------+-----------------------------------------------+

Daily reset is **implicit**: queries filter by ``date.today()``, so a new
day automatically starts at zero without needing a cron job or background
thread.

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
from datetime import date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Optional

from core.agent_config import get_agent_config
from core.provider_registry import is_per_model_provider, provider_limit_key

# ---------------------------------------------------------------------------
# Fallback safe-margin limits — used only if config/model_router.yaml can't
# be loaded (see _limit_for below). Keep these in sync with the YAML anyway;
# they're a safety net, not the primary source.
# ---------------------------------------------------------------------------
GROQ_DAILY_LIMIT_PER_MODEL: int = 800  # 80 % of real ~1 000 RPD
OPENROUTER_DAILY_LIMIT: int = 45  # 90 % of real ~50 RPD (shared)
COHERE_DAILY_LIMIT: int = 28  # Conservative midpoint 25-30/day
MISTRAL_DAILY_LIMIT: int = 200  # Free Experiment tier — conservative call cap
GEMINI_DAILY_LIMIT: int = 400  # AI Studio free Flash-class (varies by model)
CEREBRAS_DAILY_LIMIT: int = 150  # Free ~5 RPM / ~1M TPD — call soft-cap
OLLAMA_DAILY_LIMIT: int = 100_000  # Local — effectively unlimited for tracking
AGNES_DAILY_LIMIT: int = 2000  # Free fair-use (~20 RPM text); soft local cap

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "quotas.db"


class ReserveState(StrEnum):
    """Lifecycle of a reserved quota row ("the wallet").

    A row is created in ``RESERVED`` before an LLM call goes out on the wire,
    then transitioned exactly once to either ``confirmed`` (the provider was
    reached, so the call counts against the bucket) or ``refunded`` (the
    provider was never reached — e.g. a network blip before any bytes left the
    process). Refunds preserve today's reserved amount; confirmed rows roll the
    amount into the daily tally, so a reservation that starts just before
    midnight and resolves just after is attributed to the day it was *reserved*.
    """

    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    REFUNDED = "refunded"


class QuotaTracker:
    """Thread-safe, SQLite-backed quota tracker with automatic daily reset.

    Usage::

        tracker = QuotaTracker()
        if tracker.can_call("groq", "openai/gpt-oss-120b"):
            row_id = tracker.reserve("groq", "openai/gpt-oss-120b")
            # ... make the call ...
            tracker.confirm(row_id)

    The database file is created automatically on first use, always under the
    MultiAgent install tree (not the caller's cwd).
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        if not self._db_path.is_absolute():
            self._db_path = (_PROJECT_ROOT / self._db_path).resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Create the usage and reservation tables if they don't exist yet."""
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS quota_reservations (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider   TEXT    NOT NULL,
                    quota_key  TEXT    NOT NULL,
                    usage_date TEXT    NOT NULL,
                    state      TEXT    NOT NULL,
                    created_at TEXT    NOT NULL
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

        * **Groq** — each model has its own independent daily budget.
        * **Others** (OpenRouter free, Cohere, Mistral, Gemini, Cerebras) —
          shared daily budget across models on that account.
        """
        if is_per_model_provider(provider):
            return model
        return "__shared__"

    @staticmethod
    def _limit_for(provider: str) -> int:
        """Return the daily limit for *provider*.

        Reads from ``config/model_router.yaml`` (``providers.<provider>.*``)
        first; falls back to the hardcoded module-level constants above if
        the YAML can't be loaded or doesn't define that provider's limit key
        (e.g. a stripped-down test fixture config).
        """
        fallback_limits = {
            "groq": GROQ_DAILY_LIMIT_PER_MODEL,
            "openrouter": OPENROUTER_DAILY_LIMIT,
            "cohere": COHERE_DAILY_LIMIT,
            "mistral": MISTRAL_DAILY_LIMIT,
            "gemini": GEMINI_DAILY_LIMIT,
            "cerebras": CEREBRAS_DAILY_LIMIT,
            "ollama": OLLAMA_DAILY_LIMIT,
            "agnes": AGNES_DAILY_LIMIT,
        }

        try:
            provider_cfg = get_agent_config("providers", provider)
        except KeyError:
            if provider in fallback_limits:
                return fallback_limits[provider]
            # Unknown provider: generous default so new YAML-only providers work
            return 200

        # Prefer the limit key declared for this provider, then any common key.
        yaml_key = provider_limit_key(provider)
        if yaml_key and yaml_key in provider_cfg:
            return int(provider_cfg[yaml_key])
        for key in (
            "daily_limit",
            "daily_limit_shared",
            "daily_limit_per_model",
        ):
            if key in provider_cfg:
                return int(provider_cfg[key])
        return int(fallback_limits.get(provider, 200))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def _used_locked(
        conn: sqlite3.Connection, provider: str, key: str, today: str
    ) -> int:
        """Committed usage (legacy count + active reservations) on an open connection."""
        row = conn.execute(
            "SELECT call_count FROM quota_usage "
            "WHERE provider = ? AND quota_key = ? AND usage_date = ?",
            (provider, key, today),
        ).fetchone()
        reserved = conn.execute(
            "SELECT COUNT(*) FROM quota_reservations "
            "WHERE provider = ? AND quota_key = ? AND usage_date = ? "
            "AND state IN (?, ?)",
            (provider, key, today, ReserveState.RESERVED, ReserveState.CONFIRMED),
        ).fetchone()[0]
        return (row[0] if row else 0) + reserved

    def get_usage(self, provider: str, model: str) -> int:
        """Return today's committed call count for *provider*/*model*.

        Counts confirmed legacy rows plus every active reservation (reserved
        or confirmed), so a pending reservation already eats into the bucket.
        """
        key = self._quota_key(provider, model)
        today = self._today()
        with self._lock, self._connect() as conn:
            return self._used_locked(conn, provider, key, today)

    def remaining(self, provider: str, model: str) -> int:
        """Return how many calls remain today for *provider*/*model*."""
        return self._limit_for(provider) - self.get_usage(provider, model)

    def can_call(self, provider: str, model: str) -> bool:
        """Check whether a call is allowed within today's quota."""
        return self.remaining(provider, model) > 0

    def reserve(self, provider: str, model: str) -> int:
        """Reserve one call against today's bucket; return the ledger row id.

        The reservation must later be resolved with :meth:`confirm` or
        :meth:`refund`.  Prefer :meth:`try_reserve` when the caller wants the
        limit check to be atomic with the reservation.
        """
        key = self._quota_key(provider, model)
        now = datetime.now()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO quota_reservations "
                "(provider, quota_key, usage_date, state, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    provider,
                    key,
                    self._today(),
                    ReserveState.RESERVED,
                    now.isoformat(),
                ),
            )
            return int(cur.lastrowid)

    def try_reserve(self, provider: str, model: str) -> Optional[int]:
        """Atomically check the bucket and reserve one call if there's room.

        Returns the ledger row id on success, or ``None`` when today's limit is
        already exhausted.  The limit check and the insert run under the same
        connection and lock, so concurrent callers can never over-commit past
        the limit.
        """
        key = self._quota_key(provider, model)
        today = self._today()
        now = datetime.now()
        with self._lock, self._connect() as conn:
            used = self._used_locked(conn, provider, key, today)
            if self._limit_for(provider) - used <= 0:
                return None
            cur = conn.execute(
                "INSERT INTO quota_reservations "
                "(provider, quota_key, usage_date, state, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    provider,
                    key,
                    today,
                    ReserveState.RESERVED,
                    now.isoformat(),
                ),
            )
            return int(cur.lastrowid)

    def confirm(self, row_id: int) -> None:
        """Mark a reservation as consumed: the provider was reached.

        The amount stays in today's bucket.  Transitions are only valid from
        ``RESERVED``; confirming twice is a no-op guard.
        """
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE quota_reservations SET state = ? "
                "WHERE id = ? AND state = ?",
                (ReserveState.CONFIRMED, row_id, ReserveState.RESERVED),
            )

    def refund(self, row_id: int) -> None:
        """Release a reservation back into today's bucket.

        Only meaningful for rows still in ``RESERVED``: the provider was never
        reached, so the slot must not count against the limit.  The row stays
        in the ledger (marked ``refunded``) for auditability.
        """
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE quota_reservations SET state = ? "
                "WHERE id = ? AND state = ?",
                (ReserveState.REFUNDED, row_id, ReserveState.RESERVED),
            )

    def record_call(self, provider: str, model: str) -> None:
        """Record a successful API call, incrementing today's counter.

        Legacy helper retained for backward compatibility — the router now
        uses :meth:`reserve`/:meth:`confirm` instead.
        """
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
                    "DELETE FROM quota_usage WHERE provider = ? AND usage_date = ?",
                    (provider, today),
                )
                conn.execute(
                    "DELETE FROM quota_reservations WHERE provider = ? AND usage_date = ?",
                    (provider, today),
                )
            else:
                conn.execute(
                    "DELETE FROM quota_usage WHERE usage_date = ?",
                    (today,),
                )
                conn.execute(
                    "DELETE FROM quota_reservations WHERE usage_date = ?",
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

        ``used`` includes active reservations, so a pending reservation shows
        up before the call has resolved.
        """
        today = self._today()
        result: dict[str, dict[str, int]] = {}
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT provider, quota_key, call_count "
                "FROM quota_usage WHERE usage_date = ?",
                (today,),
            ).fetchall()
            reservations = conn.execute(
                "SELECT provider, quota_key, COUNT(*) "
                "FROM quota_reservations WHERE usage_date = ? "
                "AND state IN (?, ?) GROUP BY provider, quota_key",
                (today, ReserveState.RESERVED, ReserveState.CONFIRMED),
            ).fetchall()
        for provider, key, count in rows:
            limit = self._limit_for(provider)
            label = f"{provider}/{key}"
            result[label] = {"used": count, "remaining": limit - count}
        for provider, key, count in reservations:
            limit = self._limit_for(provider)
            label = f"{provider}/{key}"
            used = result.get(label, {}).get("used", 0) + count
            result[label] = {"used": used, "remaining": limit - used}
        return result
