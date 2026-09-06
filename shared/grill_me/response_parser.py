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
    ) -> Tuple[Dict[str, DimensionResolution], List[str]]:
        """Parse user response against a list of GrillQuestion objects.

        Returns:
            resolutions: dict mapping dimension_id to DimensionResolution
            unresolved_critical: list of dimension_ids that are CRITICAL but could not be resolved
        """
        resolutions: Dict[str, DimensionResolution] = {}
        if inferred_resolutions:
            resolutions.update(inferred_resolutions)

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
            unresolved = cls._check_unresolved_critical(questions, resolutions)
            return resolutions, unresolved

        # Case 2: Indexed selection (e.g., "1A 2B 3C", "1.A 2.B", "1-B, 2-A", "1:A 2:C", "1选A 2选B")
        indexed_matches = cls._extract_indexed_choices(cleaned_text, len(questions))
        if indexed_matches:
            for idx, key_or_override in indexed_matches.items():
                if 1 <= idx <= len(questions):
                    q = questions[idx - 1]
                    cls._apply_choice_to_dimension(q, key_or_override, resolutions)

        # Case 3: Sequential bare letters if count matches questions (e.g. "A B C" or "A, B, A")
        elif cls._is_sequential_bare_letters(cleaned_text, len(questions)):
            letters = re.findall(r"[A-Da-d]", cleaned_text)
            for idx, letter in enumerate(letters, start=1):
                if idx <= len(questions):
                    q = questions[idx - 1]
                    cls._apply_choice_to_dimension(q, letter.upper(), resolutions)

        # Case 4: Freeform text with explicit overrides or partial mentions
        else:
            cls._extract_freeform_choices(cleaned_text, questions, resolutions)

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

        unresolved = cls._check_unresolved_critical(questions, resolutions)
        return resolutions, unresolved

    @classmethod
    def _extract_indexed_choices(cls, text: str, max_questions: int) -> Dict[int, str]:
        results: Dict[int, str] = {}
        pattern = re.compile(
            r"(?:第|题)?\s*([1-9])\s*(?:题|\.|\:|\-|\)|\s*(?:选|按)?)\s*([A-Da-d]|推荐|建议|[^\s,;，；]+)"
        )
        for m in pattern.finditer(text):
            idx = int(m.group(1))
            val = m.group(2).strip()
            if 1 <= idx <= max_questions:
                results[idx] = val
        return results

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
    ) -> None:
        for idx, q in enumerate(questions, start=1):
            patterns = [
                rf"{idx}[号题]?\s*[:：=选]?\s*([A-Da-d]|推荐|建议)",
                rf"{re.escape(q.dimension.name)}\s*[:：=选]?\s*([A-Da-d]|推荐|建议)",
            ]
            matched = False
            for pat in patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    choice = m.group(1)
                    cls._apply_choice_to_dimension(q, choice, resolutions)
                    matched = True
                    break
            if not matched:
                override_pat = rf"{idx}[号题]?\s*[:：=选]?\s*([^,;，。\n]+)"
                om = re.search(override_pat, text)
                if om:
                    content = om.group(1).strip()
                    if content and not re.match(r"^[1-9]", content):
                        cls._apply_choice_to_dimension(q, content, resolutions)

    @classmethod
    def _apply_choice_to_dimension(
        cls,
        q: GrillQuestion,
        choice_str: str,
        resolutions: Dict[str, DimensionResolution],
    ) -> None:
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
            return

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
            return

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

    @classmethod
    def _check_unresolved_critical(
        cls,
        questions: List[GrillQuestion],
        resolutions: Dict[str, DimensionResolution],
    ) -> List[str]:
        unresolved: List[str] = []
        for q in questions:
            if q.dimension.priority == PriorityTier.CRITICAL:
                if q.dimension.id not in resolutions:
                    unresolved.append(q.dimension.id)
                else:
                    res = resolutions[q.dimension.id]
                    if not res.selected_label or res.selected_key == "":
                        unresolved.append(q.dimension.id)
        return unresolved


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
                    prov = Provenance.CONTEXT
                    if var and var.primary_fact:
                        layer = var.primary_fact.source_layer
                        if layer in ("current_user", "conversation"):
                            prov = Provenance.USER
                        elif layer == "upstream_outputs":
                            prov = Provenance.UPSTREAM
                        elif layer == "project_search":
                            prov = Provenance.PROJECT
                    rat = (
                        f"Resolved from {var.primary_fact.source_layer} ({var.primary_fact.source_ref})"
                        if var and var.primary_fact
                        else "Resolved from research context"
                    )
                    self.resolutions[dim_id] = DimensionResolution(
                        dimension_id=dim.id,
                        dimension_name=dim.name,
                        selected_key="CONTEXT",
                        selected_value=val,
                        selected_label=str(val),
                        provenance=prov,
                        priority=dim.priority,
                        rationale=rat,
                    )
                    inferred[dim_id] = val

        selected_dims: List[GrillDimension] = []

        # Tier 1: CRITICAL dimensions not yet inferred
        for dim in self.all_dimensions.values():
            if dim.priority == PriorityTier.CRITICAL:
                if dim.id not in inferred:
                    selected_dims.append(dim)
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
            if dim.priority == PriorityTier.DEFAULTABLE and dim.id not in self.resolutions:
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

    def submit_response(self, user_response: str) -> Tuple[GrillState, Dict[str, Any]]:
        """Process user response, transition state machine, and return status payload."""
        if self.state not in (GrillState.STAGE0_UNRESOLVED, GrillState.STAGE0_ROUND2):
            raise ValueError(f"Cannot submit response in state {self.state}")

        new_res, unresolved = GrillResponseParser.parse(
            user_response, self.active_questions, self.resolutions
        )
        self.resolutions.update(new_res)

        if not unresolved:
            self.state = GrillState.STAGE0_CONFIRMED
            snapshot = self.generate_snapshot_markdown()
            return self.state, {
                "status": "CONFIRMED",
                "round": self.round,
                "snapshot": snapshot,
                "unresolved": [],
            }

        # If unresolved criticals exist and we haven't reached max rounds:
        if self.round < self.MAX_ROUNDS:
            self.round += 1
            self.state = GrillState.STAGE0_ROUND2
            unresolved_dims = [self.all_dimensions[uid] for uid in unresolved if uid in self.all_dimensions]
            self.active_questions = [
                GrillQuestion(index=idx, dimension=d, prompt=f"[待决要素追问] {d.name}: {d.description}")
                for idx, d in enumerate(unresolved_dims, start=1)
            ]
            return self.state, {
                "status": "ROUND2_REQUIRED",
                "round": self.round,
                "questions": self.active_questions,
                "unresolved": unresolved,
            }
        else:
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
                "snapshot": snapshot,
                "unresolved_forced": unresolved,
            }

    def bypass_headless(self, parameters: Dict[str, Any]) -> Tuple[GrillState, str]:
        """Bypass interactive gate when all parameters are explicitly supplied."""
        for k, v in parameters.items():
            dim = self.all_dimensions.get(k)
            dim_name = dim.name if dim else k
            dim_prio = dim.priority if dim else PriorityTier.HIGH_IMPACT
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
        """Render auditable Markdown Protocol Snapshot with provenance annotations."""
        lines = [
            "# Stage 0 Protocol Snapshot (Research Gate Confirmed)",
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
        lines.append("> **Research Gate Status**: `CONFIRMED`. Substantive execution for Stage 1+ is unblocked.")
        return "\n".join(lines)
