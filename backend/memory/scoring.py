"""Pure scoring functions for deterministic action ranking."""

from __future__ import annotations

from datetime import datetime, timezone


def confidence(success_count: int, fail_count: int) -> float:
    """Empirical action reliability: successes divided by all recorded attempts."""
    total = success_count + fail_count
    return success_count / total if total else 0.0


def freshness(
    last_success_at: datetime | None,
    last_env_version: str | None,
    current_env_version: str | None = None,
    *,
    as_of: datetime | None = None,
    half_life_days: float = 30.0,
) -> float:
    """Decay a successful fix over time and penalize a changed environment.

    This is intentionally a single swappable function. Version comparison is
    conservative: any unequal non-empty version is considered an environment move.
    """
    if last_success_at is None:
        return 0.0
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")
    reference = as_of or datetime.now(timezone.utc)
    if last_success_at.tzinfo is None:
        last_success_at = last_success_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (reference - last_success_at).total_seconds() / 86_400)
    time_score = 0.5 ** (age_days / half_life_days)
    environment_penalty = 0.5 if current_env_version and current_env_version != last_env_version else 1.0
    return time_score * environment_penalty
