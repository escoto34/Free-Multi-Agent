"""
Persistent SQLite-backed quota counters with automatic daily reset.

Limits are read from ``config/model_router.yaml`` at call time via
``core.agent_config.get_agent_config`` — the YAML is the single source of
truth. The constants below (``GROQ_DAILY_LIMIT_PER_MODEL`` etc.) are kept
only as a fallback for environments where the YAML isn't available (e.g.
some unit tests that construct a ``QuotaTracker`` without a full project
checkout) — if the YAML load succeeds, its values always win.

  +--------------+-----+-----------------------------------------------+
  | Provider     | RPD | Scope                                         |
  +--------------+-----+-----------------------------------------------+
  | Groq         | 800 | Per model (independent counters)               |
  | OpenRouter   |  45 | SHARED across all ``:free`` models on account  |
  | Cohere       |  28 | SHARED across all endpoints                    |
  +--------------+-----+-----------------------------------------------+

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
from datetime import date
from pathlib import Path
from typing import Optional

from core.agent_config import get_agent_config

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
CEREBRAS_DAILY_LIMIT: int = 500  # Free developer tier (approx.)

# Maps provider -> the YAML key under providers.<provider>.* that holds its
# daily limit. Each provider uses a differently-named key because the scope
# differs (per-model vs. shared-across-account).
_YAML_LIMIT_KEY = {
    "groq": "daily_limit_per_model",
    "openrouter": "daily_limit_shared",
    "cohere": "daily_limit",
    "mistral": "daily_limit",
    "gemini": "daily_limit",
    "cerebras": "daily_limit",
}

# Providers that track quota per model name (vs shared account bucket).
_PER_MODEL_PROVIDERS = frozenset({"groq"})

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "quotas.db"


class QuotaTracker:
    """Thread-safe, SQLite-backed quota tracker with automatic daily reset.

    Usage::

        tracker = QuotaTracker()
        if tracker.can_call("groq", "openai/gpt-oss-120b"):
            # ... make the call ...
            tracker.record_call("groq", "openai/gpt-oss-120b")

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

        * **Groq** — each model has its own independent daily budget.
        * **Others** (OpenRouter free, Cohere, Mistral, Gemini, Cerebras) —
          shared daily budget across models on that account.
        """
        if provider in _PER_MODEL_PROVIDERS:
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
        }

        try:
            provider_cfg = get_agent_config("providers", provider)
        except KeyError:
            if provider in fallback_limits:
                return fallback_limits[provider]
            # Unknown provider: generous default so new YAML-only providers work
            return 200

        # Prefer the limit key declared for this provider, then any common key.
        yaml_key = _YAML_LIMIT_KEY.get(provider)
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
                    "DELETE FROM quota_usage WHERE provider = ? AND usage_date = ?",
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
