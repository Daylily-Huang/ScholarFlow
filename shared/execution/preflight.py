"""ScholarFlow Preflight Check Protocol (RFC-014 / P2-02).

Enforces that an explicit, valid execution profile is confirmed
before substantive research execution (searching, downloading, LLM extraction)
is permitted to begin.
Zero external dependencies (pure Python standard library).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from shared.execution.profiles import ExecutionDepth, ExecutionProfile, get_profile
from shared.execution.selection import normalize_depth


class PreflightError(Exception):
    """Raised when execution starts without valid confirmed depth or budget."""
    pass


def preflight_check(
    depth_input: Any,
    run_id: Optional[str] = None,
    allow_unconfirmed: bool = False,
) -> Tuple[bool, Optional[ExecutionProfile], str]:
    """Preflight validator for all research execution entry points.

    Returns:
        (is_passed, profile, message)
    """
    if not depth_input:
        if allow_unconfirmed:
            return False, None, "Execution depth is unconfirmed."
        raise PreflightError(
            "Preflight failed: execution_depth is required before substantive execution. "
            "Please confirm 'quick', 'standard', or 'deep' via Stage 0 Grill-Me or CLI flag."
        )

    norm_depth = normalize_depth(str(depth_input))
    if not norm_depth:
        msg = f"Invalid execution depth '{depth_input}'. Allowed values: quick, standard, deep."
        if allow_unconfirmed:
            return False, None, msg
        raise PreflightError(msg)

    profile = get_profile(norm_depth)
    return True, profile, f"Preflight passed: execution profile confirmed ({profile.name_zh})."
