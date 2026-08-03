"""
LLM call failure taxonomy and per-class retry budgets (reserved name, binding
decision 5 of the roadmap).

``CallOutcome`` classifies *why* an LLM call failed so the router can apply a
hard, per-failure-class retry budget instead of a single ``max_retries`` number
that treats a network blip and a quota wall identically. Never merge this with
``agents/deep_research.SourceResultStatus`` — that enum models search-source
failures and shares some member names only by coincidence.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

# Body words that reliably signal a real quota wall (vs an ordinary rate limit).
# When present we short-circuit: no retry, no cascade-retry on the same wall.
_QUOTA_BODY_RE = re.compile(
    r"\b(quota|credit|insufficient|exhausted)\b",
    re.I,
)


class CallOutcome(StrEnum):
    SUCCESS = "success"
    NETWORK_TRANSIENT = "network_transient"
    SCHEMA_INVALID = "schema_invalid"
    QUALITY_REJECTED = "quality_rejected"
    QUOTA_EXHAUSTED = "quota_exhausted"
    RATE_LIMITED = "rate_limited"
    PROVIDER_ERROR = "provider_error"


# Hard budgets per failure class. Network blips deserve the most retries;
# repair/revision get exactly one because a second identical repair is unlikely
# to help and each gets billed by free-tier providers.
RETRY_BUDGETS: dict[CallOutcome, int] = {
    CallOutcome.NETWORK_TRANSIENT: 2,
    CallOutcome.RATE_LIMITED: 2,
    CallOutcome.SCHEMA_INVALID: 1,
    CallOutcome.QUALITY_REJECTED: 1,
}

# Outcomes that are never worth retrying the same call for.
NON_RETRIABLE: frozenset[CallOutcome] = frozenset(
    {CallOutcome.SUCCESS, CallOutcome.QUOTA_EXHAUSTED, CallOutcome.PROVIDER_ERROR}
)


def classify_http_status(
    status: int, body: str = "", provider: str = ""
) -> CallOutcome:
    """Map an HTTP status (plus optional response body) to a CallOutcome.

    A body carrying quota wording wins over the generic transient mapping, so
    a quota-worded 429 is classified as QUOTA_EXHAUSTED rather than RATE_LIMITED.
    """
    if status == 429:
        if _QUOTA_BODY_RE.search(body or ""):
            return CallOutcome.QUOTA_EXHAUSTED
        return CallOutcome.RATE_LIMITED
    if status in (408, 502, 503, 504):
        return CallOutcome.NETWORK_TRANSIENT
    if status in (402, 409, 413, 401):
        if _QUOTA_BODY_RE.search(body or ""):
            return CallOutcome.QUOTA_EXHAUSTED
        return CallOutcome.PROVIDER_ERROR
    if status == 422:
        return CallOutcome.QUALITY_REJECTED
    return CallOutcome.PROVIDER_ERROR


def retry_budget_for(outcome: CallOutcome) -> int:
    """Return the hard retry budget for a classifier outcome (0 = no retry)."""
    return RETRY_BUDGETS.get(outcome, 0)