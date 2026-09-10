"""Shared validation for dimensions that require an explicit user selection (R02).

Some Stage 0 dimensions are *closed*: their value must come from a fixed enum
and must be affirmatively selected by the current user. ``EXECUTION_DEPTH`` is
the canonical example -- an execution budget cannot be "custom text".

Before this module existed the Grill gate only checked that a value was
*present*, so ``1 zzz`` confirmed the dimension with the literal value ``zzz``
and a hand-built ``inferred_values={"EXECUTION_DEPTH": "deep"}`` bypassed the
question entirely.

Zero external dependencies (pure Python standard library).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

# Provenance values that represent a genuine, first-party user decision. An
# inferred or defaulted value may inform a recommendation but must never unlock
# a dimension that demands explicit selection.
_TRUSTED_PROVENANCE_VALUES = ("USER",)


class SelectionProblem(str, Enum):
    """Machine-readable reason a required selection is not satisfied."""

    MISSING = "MISSING"                      # No value supplied at all
    INVALID_VALUE = "INVALID_VALUE"          # Supplied value is not in the closed enum
    UNTRUSTED_PROVENANCE = "UNTRUSTED_PROVENANCE"  # Value did not come from the user
    BLANK = "BLANK"                          # Supplied value is empty/whitespace


@dataclass
class SelectionValidation:
    """Outcome of validating one explicit-selection dimension."""

    dimension_id: str
    satisfied: bool
    problem: Optional[SelectionProblem] = None
    value: Any = None
    provenance: str = ""
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension_id": self.dimension_id,
            "satisfied": self.satisfied,
            "problem": self.problem.value if self.problem else None,
            "value": self.value,
            "provenance": self.provenance,
            "message": self.message,
        }


def requires_explicit_selection(dimension: Any) -> bool:
    """Whether ``dimension`` is a closed dimension demanding explicit selection."""
    return bool(getattr(dimension, "requires_explicit_selection", False)) or (
        getattr(dimension, "id", None) == "EXECUTION_DEPTH"
    )


def normalize_candidate_value(dimension: Any, raw_value: Any) -> Optional[str]:
    """Map a raw selection to a canonical option value, or ``None`` if invalid.

    Accepts the option value, the option key (``"A"``/``"B"``/``"C"``), and -- for
    the depth dimension -- the documented Chinese and English aliases.
    """
    if raw_value is None:
        return None
    if isinstance(raw_value, Enum):
        raw_value = raw_value.value
    text = str(raw_value).strip()
    if not text:
        return None

    normalized_text = text.lower()

    for option in getattr(dimension, "options", []) or []:
        option_value = option.value.value if isinstance(option.value, Enum) else option.value
        if option_value is None:
            continue
        if normalized_text == str(option_value).strip().lower():
            return str(option_value).strip()
        if normalized_text == str(option.key).strip().lower():
            return str(option_value).strip()

    if getattr(dimension, "id", None) == "EXECUTION_DEPTH":
        from shared.execution.selection import normalize_depth

        depth = normalize_depth(text)
        if depth is not None:
            return depth.value

    # A default value is only a canonical fallback, never a free-text escape hatch.
    default_value = getattr(dimension, "default_value", None)
    if default_value is not None and normalized_text == str(default_value).strip().lower():
        return str(default_value).strip()

    return None


def is_valid_selection_value(dimension: Any, raw_value: Any) -> bool:
    """Whether ``raw_value`` is an acceptable value for a closed dimension."""
    return normalize_candidate_value(dimension, raw_value) is not None


def validate_explicit_selection(
    dimension: Any,
    resolution: Any = None,
    provided_value: Any = None,
) -> SelectionValidation:
    """Validate whether an explicit-selection dimension is properly satisfied.

    A selection is satisfied only when a value exists, the value belongs to the
    dimension's closed enum, and the provenance proves a first-party user
    decision. Everything else is reported with a machine-readable problem code
    instead of being silently accepted.
    """
    dimension_id = str(getattr(dimension, "id", "?"))

    raw_value = provided_value
    provenance = ""
    if resolution is not None:
        raw_value = getattr(resolution, "selected_value", None)
        provenance = getattr(getattr(resolution, "provenance", None), "value", "") or ""

    if raw_value is None:
        return SelectionValidation(
            dimension_id=dimension_id,
            satisfied=False,
            problem=SelectionProblem.MISSING,
            provenance=provenance,
            message="No selection supplied.",
        )

    text = str(raw_value).strip()
    if not text:
        return SelectionValidation(
            dimension_id=dimension_id,
            satisfied=False,
            problem=SelectionProblem.BLANK,
            provenance=provenance,
            message="Selection is blank.",
        )

    canonical = normalize_candidate_value(dimension, raw_value)
    if canonical is None:
        return SelectionValidation(
            dimension_id=dimension_id,
            satisfied=False,
            problem=SelectionProblem.INVALID_VALUE,
            value=raw_value,
            provenance=provenance,
            message="Value %r is not a valid option for %s." % (raw_value, dimension_id),
        )

    if resolution is not None and provenance not in _TRUSTED_PROVENANCE_VALUES:
        return SelectionValidation(
            dimension_id=dimension_id,
            satisfied=False,
            problem=SelectionProblem.UNTRUSTED_PROVENANCE,
            value=canonical,
            provenance=provenance,
            message=(
                "%s was not explicitly selected by the user (provenance=%s); "
                "it may inform a recommendation but cannot unlock the dimension."
                % (dimension_id, provenance or "UNKNOWN")
            ),
        )

    return SelectionValidation(
        dimension_id=dimension_id,
        satisfied=True,
        value=canonical,
        provenance=provenance,
        message="Explicit selection confirmed.",
    )


def collect_unsatisfied_required(
    dimensions: Sequence[Any],
    resolutions: Dict[str, Any],
) -> List[SelectionValidation]:
    """Return unsatisfied validations for every closed dimension in ``dimensions``."""
    results: List[SelectionValidation] = []
    for dimension in dimensions:
        if not requires_explicit_selection(dimension):
            continue
        validation = validate_explicit_selection(
            dimension, resolution=resolutions.get(getattr(dimension, "id", ""))
        )
        if not validation.satisfied:
            results.append(validation)
    return results
