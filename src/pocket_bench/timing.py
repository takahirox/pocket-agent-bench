"""Execution safety limits are independent of observed efficiency metrics."""

import math
import warnings

DEFAULT_HARD_TIMEOUT_SECONDS = 3600.0


def hard_timeout_seconds(value=None, legacy=None):
    if value is not None and legacy is not None:
        raise ValueError("Use hard_timeout_seconds only; do not also set agent_seconds")
    if legacy is not None:
        warnings.warn(
            "agent_seconds is deprecated; it now means a wall-clock safety timeout, "
            "not an aggregate role budget. Use hard_timeout_seconds.",
            FutureWarning,
            stacklevel=2,
        )
    seconds = float(
        value
        if value is not None
        else (legacy if legacy is not None else DEFAULT_HARD_TIMEOUT_SECONDS)
    )
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("hard timeout must be finite and positive")
    return seconds
