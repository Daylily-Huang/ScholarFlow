"""ScholarFlow Adaptive Research Grill Engine - Response Parser and State Model.

Deterministic parser and state machine for Stage 0 interactive research gates.
Supports shorthand responses ("按推荐", "1A 2B 3C", overrides) and provenance tracking.
Zero external dependencies (pure Python standard library).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from shared.grill_me.selection_validation import (
    SelectionProblem,
    SelectionValidation,
    collect_unsatisfied_required,
    normalize_candidate_value,
    requires_explicit_selection,
    validate_explicit_selection,
)


class PriorityTier(str, Enum):
    CRITICAL = "CRITICAL"          # Must be resolved; blocks execution if ambiguous
    HIGH_IMPACT = "HIGH_IMPACT"    # Significantly impacts strategy; should ask if unstated
    DEFAULTABLE = "DEFAULTABLE"    # Sensible scientific default applies; mention in snapshot
    COSMETIC = "COSMETIC"          # Format/styling; never ask in Stage 0


class Provenance(str, Enum):
    USER = "USER"                  # Explicitly chosen or overridden by user
    INFERRED = "INFERRED"          # Inferred with high confidence from user's initial prompt
    DEFAULTED = "DEFAULTED"        # Applied from canonical scientific domain default
    SYSTEM_RULE = "SYSTEM_RULE"    # Enforced by ScholarFlow methodology rules (e.g. E1-E4)
    CONTEXT = "CONTEXT"            # Resolved from task attachments or conversational context
    UPSTREAM = "UPSTREAM"          # Inherited from upstream ScholarFlow skill output
    PROJECT = "PROJECT"            # Retrieved on-demand from project repository documentation


class GrillState(str, Enum):
    STAGE0_NOT_STARTED = "STAGE0_NOT_STARTED"
    STAGE0_UNRESOLVED = "STAGE0_UNRESOLVED"      # Questions emitted, waiting for user response
    STAGE0_ROUND2 = "STAGE0_ROUND2"              # Follow-up round (max 2 questions)
    STAGE0_CONFIRMED = "STAGE0_CONFIRMED"        # Parameters locked, execution allowed
    STAGE0_BYPASSED = "STAGE0_BYPASSED"          # Headless/expert mode with all parameters provided
    STAGE0_INPUT_REQUIRED = "STAGE0_INPUT_REQUIRED"  # Blocked: explicit user input required (e.g. depth missing)


@dataclass
class DimensionOption:
    key: str                       # e.g., "A", "B", "C", "D"
    label: str                     # Human readable option text
    is_recommended: bool = False
    rationale: str = ""            # 1-sentence justification for recommendation
    confidence: str = "high"       # "high", "moderate", "low"
    value: Any = None              # Internal value mapped to this option


@dataclass
class GrillDimension:
    id: str                        # e.g., "D1", "E3", "S2"
    name: str                      # Human readable dimension name
    priority: PriorityTier
    description: str
    options: List[DimensionOption] = field(default_factory=list)
    default_key: str = "A"
    default_value: Any = None
    category: str = "general"
    requires_explicit_selection: bool = False

    def get_recommended_option(self) -> Optional[DimensionOption]:
        for opt in self.options:
            if opt.is_recommended:
                return opt
        if self.options:
            return self.options[0]
        return None

    def get_option_by_key(self, key: str) -> Optional[DimensionOption]:
        key_upper = key.strip().upper()
        for opt in self.options:
            if opt.key.upper() == key_upper:
                return opt
        return None


@dataclass
class GrillQuestion:
    index: int                     # 1-indexed for display (1, 2, 3...)
    dimension: GrillDimension
    prompt: str
    custom_options: Optional[List[DimensionOption]] = None

    @property
    def options(self) -> List[DimensionOption]:
        return self.custom_options if self.custom_options is not None else self.dimension.options

    @property
    def recommended_option(self) -> Optional[DimensionOption]:
        for opt in self.options:
            if opt.is_recommended:
                return opt
        if self.options:
            return self.options[0]
        return None


@dataclass
class DimensionResolution:
    dimension_id: str
    dimension_name: str
    selected_key: str
    selected_value: Any
    selected_label: str
    provenance: Provenance
    priority: PriorityTier
    rationale: str = ""
    user_notes: str = ""


class GrillResponseParser:
    """Deterministic parser for user responses to Grill-Me questions."""

    # Fast-reply affirmative keywords for "accept all recommended" (P1-08: explicit phrases only)
    ALL_RECOMMENDED_PATTERNS = [
        r"^按推荐$",
        r"^全部按推荐$",
        r"^全部推荐$",
        r"^全选推荐$",
        r"^同意全部推荐$",
        r"^all\s*recommended$",
        r"^accept\s*all\s*(?:recommended)?$",
        r"^按建议$",
        r"^全部按建议$",
    ]

    @classmethod
    def is_all_recommended(cls, user_text: str) -> bool:
        cleaned = user_text.strip().lower()
        for pat in cls.ALL_RECOMMENDED_PATTERNS:
            if re.match(pat, cleaned, re.IGNORECASE):
                return True
        return False

    @classmethod
    def parse(
        cls,
        user_text: str,
        questions: List[GrillQuestion],
        inferred_resolutions: Optional[Dict[str, DimensionResolution]] = None,
        all_critical_dimensions: Optional[List[GrillDimension]] = None,
    ) -> Tuple[Dict[str, DimensionResolution], List[str]]:
        """Parse a user response (public, backward-compatible entry point).

        Returns:
            resolutions: dict mapping dimension_id to DimensionResolution
            unresolved_critical: list of dimension_ids that are CRITICAL but could not be resolved

        Use :meth:`parse_with_errors` when the caller also needs the rejected
        raw values (R02).
        """
        resolutions, unresolved, _invalid = cls.parse_with_errors(
            user_text,
            questions,
            inferred_resolutions=inferred_resolutions,
            all_critical_dimensions=all_critical_dimensions,
        )
        return resolutions, unresolved

    @classmethod
    def parse_with_errors(
        cls,
        user_text: str,
        questions: List[GrillQuestion],
        inferred_resolutions: Optional[Dict[str, DimensionResolution]] = None,
        all_critical_dimensions: Optional[List[GrillDimension]] = None,
    ) -> Tuple[Dict[str, DimensionResolution], List[str], Dict[str, str]]:
        """Parse a user response and also report rejected values.

        Returns:
            resolutions: dict mapping dimension_id to DimensionResolution
            unresolved_critical: list of dimension_ids that are CRITICAL but could not be resolved
            invalid_values: dict mapping dimension_id to a rejected raw value
        """
        resolutions: Dict[str, DimensionResolution] = {}
        if inferred_resolutions:
            resolutions.update(inferred_resolutions)

        # Values that were supplied but rejected (R02). A rejected value must
        # block confirmation rather than silently unlock the dimension.
        invalid: Dict[str, str] = {}

        def _apply(q: GrillQuestion, raw_choice: str) -> None:
            canonical = cls._apply_choice_to_dimension(q, raw_choice, resolutions)
            if canonical is None and requires_explicit_selection(q.dimension):
                resolutions.pop(q.dimension.id, None)
                invalid[q.dimension.id] = raw_choice.strip()

        cleaned_text = user_text.strip()

        # Case 1: User chose "accept all recommended"
        if cls.is_all_recommended(cleaned_text):
            for q in questions:
                rec = q.recommended_option
                key = rec.key if rec else q.dimension.default_key
                label = rec.label if rec else str(q.dimension.default_value)
                val = rec.value if (rec and rec.value is not None) else label
                rationale = rec.rationale if rec else "Accepted recommended default"
                resolutions[q.dimension.id] = DimensionResolution(
                    dimension_id=q.dimension.id,
                    dimension_name=q.dimension.name,
                    selected_key=key,
                    selected_value=val,
                    selected_label=label,
                    provenance=Provenance.USER,
                    priority=q.dimension.priority,
                    rationale=f"User accepted recommended option: {rationale}",
                )
            unresolved = cls._check_unresolved_critical(questions, resolutions, all_critical_dimensions)
            return resolutions, unresolved, invalid

        # Case 2: Indexed selection (e.g., "1A 2B 3C", "1.A 2.B", "1-B, 2-A", "1:A 2:C", "1选A 2选B")
        indexed_matches, indexed_raw = cls._indexed_choice_and_raw(cleaned_text, len(questions))
        if indexed_matches or indexed_raw:
            for idx, key_or_override in indexed_matches.items():
                q = questions[idx - 1]
                _apply(q, key_or_override)
            for idx, leftover in indexed_raw.items():
                q = questions[idx - 1]
                if requires_explicit_selection(q.dimension):
                    resolutions.pop(q.dimension.id, None)
                    invalid[q.dimension.id] = leftover

        # Case 3: Sequential bare letters if count matches questions (e.g. "A B C" or "A, B, A")
        elif cls._is_sequential_bare_letters(cleaned_text, len(questions)):
            letters = re.findall(r"[A-Da-d]", cleaned_text)
            for idx, letter in enumerate(letters, start=1):
                if idx <= len(questions):
                    q = questions[idx - 1]
                    _apply(q, letter.upper())

        # Case 4: Freeform text with explicit overrides or partial mentions
        else:
            cls._extract_freeform_choices(cleaned_text, questions, resolutions, invalid)

        # Ensure any question not explicitly answered falls back appropriately or stays unresolved
        for q in questions:
            if q.dimension.id not in resolutions:
                if q.dimension.priority != PriorityTier.CRITICAL:
                    rec = q.recommended_option
                    key = rec.key if rec else q.dimension.default_key
                    label = rec.label if rec else str(q.dimension.default_value)
                    val = rec.value if (rec and rec.value is not None) else label
                    resolutions[q.dimension.id] = DimensionResolution(
                        dimension_id=q.dimension.id,
                        dimension_name=q.dimension.name,
                        selected_key=key,
                        selected_value=val,
                        selected_label=label,
                        provenance=Provenance.DEFAULTED,
                        priority=q.dimension.priority,
                        rationale="Defaulted because not specified in user response",
                    )

        unresolved = cls._check_unresolved_critical(questions, resolutions, all_critical_dimensions)
        for dimension_id in invalid:
            if dimension_id not in unresolved:
                unresolved.append(dimension_id)
        return resolutions, unresolved, invalid

    #: A single option letter, or a recognised "accept the recommendation" word.
    #: Chinese depth aliases are matched whole so that "深度" is accepted while
    #: the leading character of an unrelated word ("banana" -> "B") is not.
    #: The letter alternative requires a token boundary, so the leading "b" of
    #: an unrelated word ("banana") is not mistaken for option B.
    _CHOICE_VALUE_PATTERN = (
        r"(推荐|建议|rec(?:ommended)?|深度|快速|中等|标准|[A-Da-d](?![A-Za-z0-9]))"
    )
    _CHOICE_VALUE_RE = re.compile(_CHOICE_VALUE_PATTERN)
    _INDEXED_PREFIX_RE = re.compile(r"(?<![0-9])(?:第)?\s*([1-9])\s*(?:题)?")
    _DIGIT_GROUP_RE = re.compile(r"(?<![0-9])[1-9](?![0-9])")

    @classmethod
    def _indexed_choice_and_raw(
        cls, text: str, max_questions: int
    ) -> Tuple[Dict[int, str], Dict[int, str]]:
        """Return (resolved choices, raw text supplied per index).

        ``raw`` lets the caller detect an answer that carries free text which
        maps to no option, so a closed dimension can report a field error
        instead of silently treating it as "not answered" (R02).
        """
        choices: Dict[int, str] = {}
        raw: Dict[int, str] = {}
        for group in cls._split_digit_groups(text):
            prefix = cls._INDEXED_PREFIX_RE.match(group)
            if not prefix:
                continue
            idx = int(prefix.group(1))
            if not (1 <= idx <= max_questions):
                continue
            remainder = group[prefix.end():]
            stripped = remainder.lstrip(" .:-)]=选按\t")
            value_match = cls._CHOICE_VALUE_RE.match(stripped)
            if value_match:
                choices[idx] = value_match.group(1)
                continue
            override = cls._extract_override_from_group(group)
            if override:
                choices[idx] = override
                continue
            leftover = stripped.strip()
            if leftover:
                raw[idx] = leftover
        return choices, raw

    @classmethod
    def _extract_indexed_choices(cls, text: str, max_questions: int) -> Dict[int, str]:
        """Extract ``question index -> choice`` pairs from shorthand answers.

        Only a whole token counts as a choice: ``1A``/``1 A``/``1选B``/``1. A``
        are accepted, while ``1 banana`` is not read as option ``B``.
        """
        results: Dict[int, str] = {}
        for group in cls._split_digit_groups(text):
            prefix = cls._INDEXED_PREFIX_RE.match(group)
            if not prefix:
                continue
            idx = int(prefix.group(1))
            if not (1 <= idx <= max_questions):
                continue
            remainder = group[prefix.end():]
            value_match = cls._CHOICE_VALUE_RE.match(remainder.lstrip(" .:-)]=选按	"))
            if value_match:
                results[idx] = value_match.group(1)
                continue
            # A free-text override must be introduced by an explicit delimiter
            # ("1: 只用开放获取文献"); a stray word after the index ("1 banana")
            # is not a selection and must not be interpreted as option B.
            override = cls._extract_override_from_group(group)
            if override:
                results[idx] = override
        return results

    #: Separator that introduces a free-text override value ("3自定义：...").
    _OVERRIDE_DELIMITER_RE = re.compile(r"[:：=]")

    @classmethod
    def _extract_override_from_group(cls, group: str) -> Optional[str]:
        """Return the free-text value of one index group, if it declares one."""
        prefix = cls._INDEXED_PREFIX_RE.match(group)
        if not prefix:
            return None
        remainder = group[prefix.end():]
        if cls._CHOICE_VALUE_RE.match(remainder.lstrip(" .:-)]=选按\t")):
            return None
        delimiter = cls._OVERRIDE_DELIMITER_RE.search(remainder)
        if not delimiter:
            return None
        override = remainder[delimiter.end():].strip()
        return override or None

    @classmethod
    def _split_digit_groups(cls, text: str) -> List[str]:
        """Split shorthand text into index groups starting at each bare digit."""
        boundaries: List[int] = []
        for m in cls._DIGIT_GROUP_RE.finditer(text):
            start = m.start()
            while boundaries and start - boundaries[-1] <= 2:
                break
            boundaries.append(start)
        groups: List[str] = []
        for position, start in enumerate(boundaries):
            end = boundaries[position + 1] if position + 1 < len(boundaries) else len(text)
            chunk = text[start:end].strip()
            if chunk:
                groups.append(chunk)
        return groups

    @classmethod
    def _extract_freeform_override_value(cls, text: str) -> Optional[str]:
        """Extract a free-text override value for an *open* dimension.

        The value is read from a single index group, so embedded years are not
        mistaken for new question indices. Returns ``None`` when the override
        carries no explicit delimiter, because a stray word after an index is
        not a free-text specification.
        """
        for group in cls._split_digit_groups(text):
            override = cls._extract_override_from_group(group)
            if override:
                return override
        return None

    @classmethod
    def _is_sequential_bare_letters(cls, text: str, expected_count: int) -> bool:
        tokens = [t.strip().upper() for t in re.split(r"[\s,;，；]+", text.strip()) if t.strip()]
        if len(tokens) == expected_count and all(re.match(r"^[A-D]$", t) for t in tokens):
            return True
        return False

    @classmethod
    def _extract_freeform_choices(
        cls,
        text: str,
        questions: List[GrillQuestion],
        resolutions: Dict[str, DimensionResolution],
        invalid: Optional[Dict[str, str]] = None,
    ) -> None:
        for idx, q in enumerate(questions, start=1):
            # The letter alternative needs a token boundary so that "1 banana"
            # is not read as option B; Chinese aliases are matched whole.
            value = r"([A-Da-d](?![A-Za-z0-9])|推荐|建议|深度|快速|中等|标准)"
            patterns = [
                rf"(?<![0-9]){idx}[号题]?\s*[:：=选]?\s*" + value,
                rf"{re.escape(q.dimension.name)}\s*[:：=选]?\s*" + value,
            ]
            matched = False
            for pat in patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    choice = m.group(1)
                    canonical = cls._apply_choice_to_dimension(q, choice, resolutions)
                    if canonical is None and requires_explicit_selection(q.dimension):
                        resolutions.pop(q.dimension.id, None)
                        if invalid is not None:
                            invalid[q.dimension.id] = choice.strip()
                    matched = True
                    break
            if not matched:
                content = cls._extract_freeform_override_value(text)
                if content:
                    canonical = cls._apply_choice_to_dimension(q, content, resolutions)
                    if canonical is None and requires_explicit_selection(q.dimension):
                        resolutions.pop(q.dimension.id, None)
                        if invalid is not None:
                            invalid[q.dimension.id] = content

    @classmethod
    def _apply_choice_to_dimension(
        cls,
        q: GrillQuestion,
        choice_str: str,
        resolutions: Dict[str, DimensionResolution],
    ) -> Optional[str]:
        """Apply one answer to a dimension.

        Returns the canonical selected value, or ``None`` when the value is
        rejected because a closed dimension only accepts its declared options.
        """
        choice_clean = choice_str.strip()
        if choice_clean in ("推荐", "建议", "rec", "recommended"):
            rec = q.recommended_option
            key = rec.key if rec else q.dimension.default_key
            label = rec.label if rec else str(q.dimension.default_value)
            val = rec.value if (rec and rec.value is not None) else label
            rationale = rec.rationale if rec else "User explicitly accepted recommendation"
            resolutions[q.dimension.id] = DimensionResolution(
                dimension_id=q.dimension.id,
                dimension_name=q.dimension.name,
                selected_key=key,
                selected_value=val,
                selected_label=label,
                provenance=Provenance.USER,
                priority=q.dimension.priority,
                rationale=rationale,
            )
            return val

        opt = q.dimension.get_option_by_key(choice_clean)
        if opt:
            resolutions[q.dimension.id] = DimensionResolution(
                dimension_id=q.dimension.id,
                dimension_name=q.dimension.name,
                selected_key=opt.key,
                selected_value=opt.value if opt.value is not None else opt.label,
                selected_label=opt.label,
                provenance=Provenance.USER,
                priority=q.dimension.priority,
                rationale=opt.rationale or f"User explicitly selected Option {opt.key}",
            )
            return opt.value if opt.value is not None else opt.label

        # A closed dimension (e.g. EXECUTION_DEPTH) has no free-text fallback:
        # "1 zzz" must never confirm it with the literal value "zzz" (R02).
        if requires_explicit_selection(q.dimension):
            canonical = normalize_candidate_value(q.dimension, choice_clean)
            if canonical is None:
                # Record the rejection so the engine can surface a field error
                # and stay unresolved instead of silently accepting garbage.
                return None
            for o in q.dimension.options:
                o_val = o.value.value if isinstance(o.value, Enum) else str(o.value)
                if o_val == canonical:
                    resolutions[q.dimension.id] = DimensionResolution(
                        dimension_id=q.dimension.id,
                        dimension_name=q.dimension.name,
                        selected_key=o.key,
                        selected_value=canonical,
                        selected_label=o.label,
                        provenance=Provenance.USER,
                        priority=q.dimension.priority,
                        rationale=o.rationale or f"User explicitly selected {canonical}",
                    )
                    return canonical
            resolutions[q.dimension.id] = DimensionResolution(
                dimension_id=q.dimension.id,
                dimension_name=q.dimension.name,
                selected_key="CUSTOM",
                selected_value=canonical,
                selected_label=canonical,
                provenance=Provenance.USER,
                priority=q.dimension.priority,
                rationale=f"User explicitly selected {canonical}",
            )
            return canonical

        resolutions[q.dimension.id] = DimensionResolution(
            dimension_id=q.dimension.id,
            dimension_name=q.dimension.name,
            selected_key="CUSTOM",
            selected_value=choice_clean,
            selected_label=choice_clean,
            provenance=Provenance.USER,
            priority=q.dimension.priority,
            rationale="User-provided custom parameter specification",
            user_notes=choice_clean,
        )
        return choice_clean

    @classmethod
    def _check_unresolved_critical(
        cls,
        questions: List[GrillQuestion],
        resolutions: Dict[str, DimensionResolution],
        all_critical_dimensions: Optional[List[GrillDimension]] = None,
    ) -> List[str]:
        unresolved: List[str] = []

        def _is_unresolved(dim: GrillDimension) -> bool:
            if dim.id not in resolutions:
                return True
            res = resolutions[dim.id]
            if not res.selected_label or res.selected_key == "":
                return True
            # A closed dimension is only resolved by a valid, user-provenanced
            # selection -- presence alone is not enough (R02).
            if requires_explicit_selection(dim):
                return not validate_explicit_selection(dim, resolution=res).satisfied
            return False

        for q in questions:
            if q.dimension.priority == PriorityTier.CRITICAL and _is_unresolved(q.dimension):
                unresolved.append(q.dimension.id)

        if all_critical_dimensions:
            for dim in all_critical_dimensions:
                if dim.id not in unresolved and _is_unresolved(dim):
                    unresolved.append(dim.id)
        return unresolved


def _classify_context_provenance(var: Any):
    """Map a resolved context variable to (provenance, rationale, is_first_party).

    Only a value that can be traced to the current user's own words counts as a
    first-party decision; everything else may inform a recommendation but must
    not unlock a closed dimension on its own (R02).
    """
    if var is None or not getattr(var, "primary_fact", None):
        return Provenance.CONTEXT, "Resolved from research context", False
    fact = var.primary_fact
    layer = getattr(fact, "source_layer", "") or ""
    notes = str(getattr(fact, "notes", "") or "")
    if layer in ("current_user", "conversation"):
        provenance = Provenance.USER
        is_first_party = True
    elif layer == "upstream_outputs":
        # An upstream value only counts as an authorisation when the context
        # layer verified that it belongs to the *current* run (R07).
        provenance = Provenance.UPSTREAM
        is_first_party = "run_binding=verified" in notes
    elif layer == "project_search":
        provenance = Provenance.PROJECT
        is_first_party = False
    else:
        provenance = Provenance.CONTEXT
        is_first_party = False
    rationale = "Resolved from %s (%s)" % (layer or "context", getattr(fact, "source_ref", "unknown"))
    return provenance, rationale, is_first_party


class GrillEngine:
    """Core state engine coordinating question selection, budget enforcement, and gate approval."""

    MAX_QUESTIONS_PER_ROUND = 5
    MIN_QUESTIONS_PER_ROUND = 3
    MAX_ROUNDS = 2

    def __init__(self, skill_name: str, domain: str = "generic"):
        self.skill_name = skill_name
        self.domain = domain
        self.state = GrillState.STAGE0_NOT_STARTED
        self.round = 0
        self.active_questions: List[GrillQuestion] = []
        self.resolutions: Dict[str, DimensionResolution] = {}
        self.all_dimensions: Dict[str, GrillDimension] = {}
        self.context_brief: str = ""
        self.context_resolver: Optional[Any] = None
        # R02: raw values that were supplied but rejected by closed-dimension validation
        self.invalid_selections: Dict[str, str] = {}
        # R02: non-first-party candidates kept as recommendations only
        self.recommended_selections: Dict[str, Any] = {}
        # R08: answers are bound to a question set so a reshuffled round cannot
        # reinterpret an old index as a new question.
        self.question_set_id: str = ""
        self._question_set_counter: int = 0
        self.pending_selections: Dict[str, DimensionResolution] = {}

    def _next_question_set_id(self) -> str:
        self._question_set_counter += 1
        return "%s-q%d" % (self.skill_name or "stage0", self._question_set_counter)

    def register_dimensions(self, dimensions: List[GrillDimension]) -> None:
        for dim in dimensions:
            self.all_dimensions[dim.id] = dim

    def select_questions(
        self,
        task_prompt: str,
        inferred_values: Optional[Dict[str, Any]] = None,
        context_resolver: Optional[Any] = None,
    ) -> List[GrillQuestion]:
        """Select 3-5 high impact questions based on priority tiers, unstated parameters, and resolved context."""
        inferred = dict(inferred_values or {})

        if context_resolver is not None:
            self.context_resolver = context_resolver
            target_dims = list(self.all_dimensions.keys())
            ctx_resolved, unresolved_dims = context_resolver.resolve(
                task_prompt, target_dims, domain_hint=self.domain
            )
            self.context_brief = context_resolver.render_context_brief_markdown()
            for dim_id, val in ctx_resolved.items():
                if dim_id in self.all_dimensions:
                    dim = self.all_dimensions[dim_id]
                    var = context_resolver.resolved_variables.get(dim_id)
                    provenance, rationale, is_first_party = _classify_context_provenance(var)
                    if requires_explicit_selection(dim):
                        canonical = normalize_candidate_value(dim, val)
                        if canonical is None:
                            # A closed dimension cannot be unlocked by a stray
                            # value found in context (R02).
                            continue
                        val = canonical
                        if not is_first_party:
                            # Keep it as a *recommendation* only: the user still
                            # has to select the tier explicitly.
                            self.recommended_selections[dim_id] = val
                            continue
                    self.resolutions[dim_id] = DimensionResolution(
                        dimension_id=dim.id,
                        dimension_name=dim.name,
                        selected_key="CONTEXT",
                        selected_value=val,
                        selected_label=str(val),
                        provenance=provenance,
                        priority=dim.priority,
                        rationale=rationale,
                    )
                    inferred[dim_id] = val

        selected_dims: List[GrillDimension] = []

        # Tier 1: CRITICAL dimensions not yet inferred
        critical_dims: List[GrillDimension] = []
        for dim in self.all_dimensions.values():
            if dim.priority == PriorityTier.CRITICAL:
                if requires_explicit_selection(dim):
                    # An inferred value may only inform the recommendation (R02);
                    # the dimension stays open until the user actually selects it.
                    if dim.id not in self.resolutions:
                        canonical = normalize_candidate_value(dim, inferred.get(dim.id))
                        if canonical:
                            self.recommended_selections[dim.id] = canonical
                        critical_dims.append(dim)
                    continue
                if dim.id not in inferred:
                    critical_dims.append(dim)
                elif dim.id not in self.resolutions:
                    self.resolutions[dim.id] = DimensionResolution(
                        dimension_id=dim.id,
                        dimension_name=dim.name,
                        selected_key="INFERRED",
                        selected_value=inferred[dim.id],
                        selected_label=str(inferred[dim.id]),
                        provenance=Provenance.INFERRED,
                        priority=dim.priority,
                        rationale="Inferred from clear task prompt",
                    )

        # Prioritize dimensions requiring explicit selection (e.g. EXECUTION_DEPTH)
        # so they are never pushed out of round 1 when CRITICAL dimensions exceed MAX_QUESTIONS_PER_ROUND (T04)
        critical_dims.sort(
            key=lambda d: 0 if getattr(d, "requires_explicit_selection", False) or d.id == "EXECUTION_DEPTH" else 1
        )
        selected_dims.extend(critical_dims[: self.MAX_QUESTIONS_PER_ROUND])

        # Tier 2: HIGH_IMPACT dimensions not yet inferred, until budget reached
        if len(selected_dims) < self.MAX_QUESTIONS_PER_ROUND:
            for dim in self.all_dimensions.values():
                if dim.priority == PriorityTier.HIGH_IMPACT and dim.id not in inferred:
                    if dim not in selected_dims:
                        selected_dims.append(dim)
                        if len(selected_dims) >= self.MAX_QUESTIONS_PER_ROUND:
                            break

        # Tier 3: DEFAULTABLE dimensions apply standard defaults silently
        for dim in self.all_dimensions.values():
            if (
                dim.priority == PriorityTier.DEFAULTABLE
                and dim.id not in self.resolutions
                and not requires_explicit_selection(dim)
            ):
                if dim.id in inferred:
                    self.resolutions[dim.id] = DimensionResolution(
                        dimension_id=dim.id,
                        dimension_name=dim.name,
                        selected_key="INFERRED",
                        selected_value=inferred[dim.id],
                        selected_label=str(inferred[dim.id]),
                        provenance=Provenance.INFERRED,
                        priority=dim.priority,
                        rationale="Inferred from user prompt",
                    )
                else:
                    rec = dim.get_recommended_option()
                    k = rec.key if rec else dim.default_key
                    val = rec.value if (rec and rec.value is not None) else dim.default_value
                    lbl = rec.label if rec else str(dim.default_value)
                    self.resolutions[dim.id] = DimensionResolution(
                        dimension_id=dim.id,
                        dimension_name=dim.name,
                        selected_key=k,
                        selected_value=val,
                        selected_label=lbl,
                        provenance=Provenance.DEFAULTED,
                        priority=dim.priority,
                        rationale=rec.rationale if rec else "Standard scientific domain default applied",
                    )

        # Build GrillQuestion list (bounded to MAX_QUESTIONS_PER_ROUND)
        self.active_questions = []
        for idx, dim in enumerate(selected_dims[: self.MAX_QUESTIONS_PER_ROUND], start=1):
            q = GrillQuestion(
                index=idx,
                dimension=dim,
                prompt=f"{dim.name}: {dim.description}",
            )
            self.active_questions.append(q)

        self.round = 1
        if not self.active_questions:
            self.state = GrillState.STAGE0_CONFIRMED
        else:
            self.state = GrillState.STAGE0_UNRESOLVED
        return self.active_questions

    def render_presentation(self) -> str:
        """Render complete presentation including context brief (Stage 0A) and questions (Stage 0B)."""
        parts = []
        if self.context_brief:
            parts.append(self.context_brief)
            parts.append("")
        if self.active_questions:
            parts.append("### 待确认科研决策维度 (Unresolved Dimensions)")
            for q in self.active_questions:
                parts.append(f"**{q.index}. {q.prompt}**")
                for opt in q.options:
                    rec_tag = " `[Recommended]`" if opt.is_recommended else ""
                    parts.append(f"  - **[{opt.key}]** {opt.label}{rec_tag}")
                    if opt.rationale:
                        parts.append(f"    *{opt.rationale}*")
                parts.append("")
        elif self.state == GrillState.STAGE0_CONFIRMED:
            parts.append(self.generate_snapshot_markdown())
        return "\n".join(parts)

    #: States in which a user response may be consumed. ``STAGE0_INPUT_REQUIRED``
    #: is included so a blocked run can be resumed instead of restarted (R08).
    SUBMITTABLE_STATES = (
        GrillState.STAGE0_UNRESOLVED,
        GrillState.STAGE0_ROUND2,
        GrillState.STAGE0_INPUT_REQUIRED,
    )

    def submit_response(
        self, user_response: str, question_set_id: Optional[str] = None
    ) -> Tuple[GrillState, Dict[str, Any]]:
        """Process user response, transition state machine, and return status payload.

        Args:
            user_response: raw user answer text.
            question_set_id: optional binding. When supplied and it does not match
                the active question set, stale answers are rejected instead of
                being reinterpreted against a reshuffled question list (R08).
        """
        if self.state not in self.SUBMITTABLE_STATES:
            raise ValueError(f"Cannot submit response in state {self.state}")

        if (
            question_set_id is not None
            and self.question_set_id
            and question_set_id != self.question_set_id
        ):
            raise ValueError(
                "Stale answer for question set %r; the active set is %r"
                % (question_set_id, self.question_set_id)
            )

        resuming = self.state == GrillState.STAGE0_INPUT_REQUIRED
        if resuming:
            # Preserve everything already answered; only the blocked items are
            # re-presented for completion.
            self.state = GrillState.STAGE0_ROUND2

        all_critical = [d for d in self.all_dimensions.values() if d.priority == PriorityTier.CRITICAL]
        new_res, unresolved, invalid_values = GrillResponseParser.parse_with_errors(
            user_response,
            self.active_questions,
            self.resolutions,
            all_critical_dimensions=all_critical,
        )
        self.resolutions.update(new_res)
        self.invalid_selections = dict(invalid_values)

        if invalid_values:
            rejected = ", ".join(
                "%s=%r" % (dim_id, raw) for dim_id, raw in sorted(invalid_values.items())
            )
            # Invalid input is a field error: it must not confirm anything.
            self.state = GrillState.STAGE0_INPUT_REQUIRED if resuming or self.round >= self.MAX_ROUNDS else GrillState.STAGE0_ROUND2
            return self.state, {
                "status": "INVALID_SELECTION",
                "round": self.round,
                "invalid_selections": invalid_values,
                "unresolved": unresolved,
                "message": "Rejected value(s) for closed dimension(s): %s" % rejected,
                "snapshot": self.generate_snapshot_markdown(),
            }

        if not unresolved:
            self.state = GrillState.STAGE0_CONFIRMED
            snapshot = self.generate_snapshot_markdown()
            return self.state, {
                "status": "CONFIRMED",
                "round": self.round,
                "question_set_id": self.question_set_id,
                "snapshot": snapshot,
                "unresolved": [],
            }

        # If unresolved criticals exist and we haven't reached max rounds:
        if self.round < self.MAX_ROUNDS and not resuming:
            self.round += 1
            self.state = GrillState.STAGE0_ROUND2
            unresolved_dims = [self.all_dimensions[uid] for uid in unresolved if uid in self.all_dimensions]
            self.active_questions = [
                GrillQuestion(index=idx, dimension=d, prompt=f"[待决要素追问] {d.name}: {d.description}")
                for idx, d in enumerate(unresolved_dims, start=1)
            ]
            self.question_set_id = self._next_question_set_id()
            return self.state, {
                "status": "ROUND2_REQUIRED",
                "round": self.round,
                "question_set_id": self.question_set_id,
                "questions": self.active_questions,
                "unresolved": unresolved,
            }

        # Closed dimensions can never be force-defaulted: they block instead (T05, R02).
        blocked = collect_unsatisfied_required(
            [self.all_dimensions[uid] for uid in unresolved if uid in self.all_dimensions],
            self.resolutions,
        )
        if blocked:
            self.state = GrillState.STAGE0_INPUT_REQUIRED
            self.active_questions = [
                GrillQuestion(
                    index=idx,
                    dimension=self.all_dimensions[item.dimension_id],
                    prompt=f"[需要明确选择] {self.all_dimensions[item.dimension_id].name}: "
                    f"{self.all_dimensions[item.dimension_id].description}",
                )
                for idx, item in enumerate(blocked, start=1)
                if item.dimension_id in self.all_dimensions
            ]
            self.question_set_id = self._next_question_set_id()
            return self.state, {
                "status": "INPUT_REQUIRED",
                "round": self.round,
                "question_set_id": self.question_set_id,
                "questions": self.active_questions,
                "unresolved": [item.dimension_id for item in blocked],
                "field_errors": [item.to_dict() for item in blocked],
                "message": (
                    "Dimension(s) %s require an explicit, valid selection. "
                    "Stage 1 execution is blocked until they are supplied."
                    % [item.dimension_id for item in blocked]
                ),
                "snapshot": self.generate_snapshot_markdown(),
            }

        # No CRITICAL dimension is listed as unresolved, but a closed dimension
        # may still be unsatisfied (e.g. it was answered with an invalid value in
        # an earlier round). Confirmation must not slip through that gap (R02).
        still_blocked = collect_unsatisfied_required(self.all_dimensions.values(), self.resolutions)
        if still_blocked:
            self.state = GrillState.STAGE0_INPUT_REQUIRED
            self.active_questions = [
                GrillQuestion(
                    index=idx,
                    dimension=self.all_dimensions[item.dimension_id],
                    prompt=f"[需要明确选择] {self.all_dimensions[item.dimension_id].name}: "
                    f"{self.all_dimensions[item.dimension_id].description}",
                )
                for idx, item in enumerate(still_blocked, start=1)
                if item.dimension_id in self.all_dimensions
            ]
            self.question_set_id = self._next_question_set_id()
            return self.state, {
                "status": "INPUT_REQUIRED",
                "round": self.round,
                "question_set_id": self.question_set_id,
                "questions": self.active_questions,
                "unresolved": [item.dimension_id for item in still_blocked],
                "field_errors": [item.to_dict() for item in still_blocked],
                "message": (
                    "Dimension(s) %s require an explicit, valid selection. "
                    "Stage 1 execution is blocked until they are supplied."
                    % [item.dimension_id for item in still_blocked]
                ),
                "snapshot": self.generate_snapshot_markdown(),
            }

        # Normal safe conservative default upon budget exhaustion for standard critical dimensions
        for uid in unresolved:
            d = self.all_dimensions[uid]
            rec = d.get_recommended_option()
            k = rec.key if rec else d.default_key
            val = rec.value if (rec and rec.value is not None) else d.default_value
            lbl = rec.label if rec else str(d.default_value)
            self.resolutions[uid] = DimensionResolution(
                dimension_id=uid,
                dimension_name=d.name,
                selected_key=k,
                selected_value=val,
                selected_label=lbl,
                provenance=Provenance.SYSTEM_RULE,
                priority=d.priority,
                rationale="Enforced safe conservative default upon budget exhaustion",
            )
        self.state = GrillState.STAGE0_CONFIRMED
        snapshot = self.generate_snapshot_markdown()
        return self.state, {
            "status": "CONFIRMED_WITH_WARNING",
            "round": self.round,
            "question_set_id": self.question_set_id,
            "snapshot": snapshot,
            "unresolved_forced": unresolved,
        }

    def resume_input(self, user_response: str, question_set_id: Optional[str] = None):
        """Resume a run blocked in ``STAGE0_INPUT_REQUIRED`` (R08).

        Previously the blocked state rejected every answer, so the only recovery
        was restarting the whole gate. Already-answered parameters are preserved.
        """
        if self.state != GrillState.STAGE0_INPUT_REQUIRED:
            raise ValueError(
                "resume_input requires state STAGE0_INPUT_REQUIRED, current state is %s" % self.state
            )
        return self.submit_response(user_response, question_set_id=question_set_id)

    def bypass_headless(self, parameters: Dict[str, Any]) -> Tuple[GrillState, str]:
        """Bypass interactive gate when all parameters are explicitly supplied."""
        # Validate every closed dimension: missing AND invalid values both block
        # headless execution (T08 + R02/R03). A value such as "banana" must not be
        # accepted just because the key is present.
        canonical_values: Dict[str, Any] = {}
        field_errors: List[Dict[str, Any]] = []
        for dim in self.all_dimensions.values():
            if not requires_explicit_selection(dim):
                continue
            raw_value = parameters.get(dim.id)
            if raw_value is None or str(raw_value).strip() == "":
                if dim.id not in self.resolutions:
                    field_errors.append(
                        SelectionValidation(
                            dimension_id=dim.id,
                            satisfied=False,
                            problem=SelectionProblem.MISSING,
                            message="Explicit parameter required.",
                        ).to_dict()
                    )
                continue
            canonical = normalize_candidate_value(dim, raw_value)
            if canonical is None:
                field_errors.append(
                    SelectionValidation(
                        dimension_id=dim.id,
                        satisfied=False,
                        problem=SelectionProblem.INVALID_VALUE,
                        value=raw_value,
                        message="%r is not a valid option for %s." % (raw_value, dim.id),
                    ).to_dict()
                )
                continue
            canonical_values[dim.id] = canonical

        if field_errors:
            self.invalid_selections = {
                item["dimension_id"]: str(item.get("value"))
                for item in field_errors
                if item.get("problem") == SelectionProblem.INVALID_VALUE.value
            }
            self.state = GrillState.STAGE0_INPUT_REQUIRED
            blocked_ids = [item["dimension_id"] for item in field_errors]
            msg = (
                "INPUT_REQUIRED: Headless execution blocked. "
                "Explicit parameter(s) required or invalid: %s" % blocked_ids
            )
            return self.state, msg

        for k, v in parameters.items():
            dim = self.all_dimensions.get(k)
            dim_name = dim.name if dim else k
            dim_prio = dim.priority if dim else PriorityTier.HIGH_IMPACT
            if dim is not None and requires_explicit_selection(dim):
                v = canonical_values.get(k, v)
            self.resolutions[k] = DimensionResolution(
                dimension_id=k,
                dimension_name=dim_name,
                selected_key="EXPLICIT",
                selected_value=v,
                selected_label=str(v),
                provenance=Provenance.USER,
                priority=dim_prio,
                rationale="Supplied headlessly via parameter configuration",
            )
        for dim in self.all_dimensions.values():
            if requires_explicit_selection(dim):
                # Already validated above; never fall back to a default here.
                continue
            if dim.priority == PriorityTier.CRITICAL and dim.id not in self.resolutions:
                rec = dim.get_recommended_option()
                k = rec.key if rec else dim.default_key
                val = rec.value if (rec and rec.value is not None) else dim.default_value
                lbl = rec.label if rec else str(dim.default_value)
                self.resolutions[dim.id] = DimensionResolution(
                    dimension_id=dim.id,
                    dimension_name=dim.name,
                    selected_key=k,
                    selected_value=val,
                    selected_label=lbl,
                    provenance=Provenance.SYSTEM_RULE,
                    priority=dim.priority,
                    rationale="Headless mode fallback default",
                )

        self.state = GrillState.STAGE0_BYPASSED
        return self.state, self.generate_snapshot_markdown()

    def generate_snapshot_markdown(self) -> str:
        """Render auditable Markdown Protocol Snapshot with provenance annotations (T19)."""
        is_confirmed = self.state in (GrillState.STAGE0_CONFIRMED, GrillState.STAGE0_BYPASSED)
        header_tag = "(Research Gate Confirmed)" if is_confirmed else "(Research Gate Pending / Blocked)"

        lines = [
            f"# Stage 0 Protocol Snapshot {header_tag}",
            f"- **Skill**: `{self.skill_name}`",
            f"- **Domain Lens**: `{self.domain}`",
            f"- **State**: `{self.state.value}`",
            f"- **Interaction Rounds**: `{self.round}`",
            "",
            "| Dimension ID | Dimension Name | Priority | Selected Setting / Boundary | Provenance | Rationale / Notes |",
            "|---|---|---|---|---|---|",
        ]
        for dim_id, res in sorted(self.resolutions.items(), key=lambda x: x[0]):
            val_display = str(res.selected_label).replace("\n", " ").strip()
            if len(val_display) > 60:
                val_display = val_display[:57] + "..."
            rat_display = str(res.rationale).replace("\n", " ").strip()
            if len(rat_display) > 60:
                rat_display = rat_display[:57] + "..."
            lines.append(
                f"| `{res.dimension_id}` | {res.dimension_name} | `{res.priority.value}` | "
                f"{val_display} | `[{res.provenance.value}]` | {rat_display} |"
            )
        lines.append("")
        lines.append("> [!NOTE]")
        if is_confirmed:
            lines.append("> **Research Gate Status**: `CONFIRMED`. Substantive execution for Stage 1+ is unblocked.")
        else:
            lines.append(f"> **Research Gate Status**: `{self.state.value}`. Substantive execution is BLOCKED pending explicit confirmation.")
        return "\n".join(lines)
