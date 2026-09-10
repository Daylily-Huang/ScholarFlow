"""ScholarFlow Preflight Check Protocol (RFC-014 / P2-02).

Enforces that an explicit, valid execution profile is confirmed
before substantive research execution (searching, downloading, LLM extraction)
is permitted to begin.
Zero external dependencies (pure Python standard library).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from shared.execution.config import RunExecutionConfig
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

    # An ExecutionDepth member must be used directly; str(enum) would yield
    # "ExecutionDepth.STANDARD" and fail validation (R04).
    if isinstance(depth_input, ExecutionDepth):
        norm_depth = depth_input
    else:
        norm_depth = normalize_depth(str(depth_input))
    if not norm_depth:
        msg = f"Invalid execution depth '{depth_input}'. Allowed values: quick, standard, deep."
        if allow_unconfirmed:
            return False, None, msg
        raise PreflightError(msg)

    profile = get_profile(norm_depth)
    return True, profile, f"Preflight passed: execution profile confirmed ({profile.name_zh})."


def preflight_run_config(
    config: Any,
    run_id: Optional[str] = None,
    stage: Optional[str] = None,
    allow_unconfirmed: bool = False,
) -> Tuple[bool, Optional[RunExecutionConfig], str]:
    """Preflight a *run configuration* rather than a bare depth value (R04/R07).

    The previously unused ``run_id`` parameter of :func:`preflight_check` now
    genuinely participates: a configuration only authorises work for the run it
    was confirmed for, and only for the stages it lists.

    Args:
        config: a :class:`RunExecutionConfig`, a canonical dict, or a path/run dir.
        run_id: the run currently being executed; must match the configuration.
        stage: the pipeline stage about to start (discovery/extraction/synthesis).
        allow_unconfirmed: return a failure tuple instead of raising.

    Returns:
        ``(is_passed, config, message)``
    """
    def _fail(message: str):
        if allow_unconfirmed:
            return False, None, message
        raise PreflightError(message)

    loaded: Optional[RunExecutionConfig] = None
    if isinstance(config, RunExecutionConfig):
        loaded = config
    elif isinstance(config, dict):
        try:
            loaded = RunExecutionConfig.from_dict(config)
        except ValueError as exc:
            return _fail("Preflight failed: %s" % exc)
    elif isinstance(config, str):
        try:
            loaded = RunExecutionConfig.load(config)
        except (FileNotFoundError, ValueError) as exc:
            return _fail("Preflight failed: %s" % exc)
    else:
        return _fail("Preflight failed: unsupported run configuration type %r" % (type(config).__name__,))

    problems = loaded.validate()
    if problems:
        return _fail("Preflight failed: invalid run configuration: %s" % "; ".join(problems))

    if not loaded.is_confirmed:
        return _fail(
            "Preflight failed: run configuration is not confirmed (selection.status=%s). "
            "A tier preset cannot authorise execution." % loaded.selection.status
        )

    if run_id is not None and run_id != loaded.run_id:
        return _fail(
            "Preflight failed: configuration belongs to run %r, not %r. "
            "Resource authorisation never transfers across runs." % (loaded.run_id, run_id)
        )

    if stage is not None and not loaded.authorises_stage(stage):
        return _fail(
            "Preflight failed: run configuration does not authorise stage %r (authorised: %s)."
            % (stage, ", ".join(loaded.stages))
        )

    return True, loaded, "Preflight passed: run %s authorised at %s depth." % (
        loaded.run_id,
        loaded.depth.value,
    )
