"""ScholarFlow Context Resolution Layer - ContextResolver & Provider Engine.

Deterministic, multi-layer context resolution engine for Stage 0 research gates.
Extracts existing decisions from conversation history, attachments, upstream outputs,
and on-demand project search to eliminate redundant questioning.
Zero external dependencies (pure Python standard library).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class ContextScope(str, Enum):
    CURRENT_ONLY = "CURRENT_ONLY"
    CURRENT_PLUS_UPSTREAM = "CURRENT_PLUS_UPSTREAM"
    PROJECT_AWARE = "PROJECT_AWARE"


class VariableStatus(str, Enum):
    RESOLVED_FROM_USER = "RESOLVED_FROM_USER"
    RESOLVED_FROM_CONTEXT = "RESOLVED_FROM_CONTEXT"
    INFERRED_HIGH_CONFIDENCE = "INFERRED_HIGH_CONFIDENCE"
    DEFAULTABLE = "DEFAULTABLE"
    UNRESOLVED = "UNRESOLVED"
    UNRESOLVED_CONFLICT = "UNRESOLVED_CONFLICT"


class FactVolatility(str, Enum):
    STATIC = "STATIC"
    SEMI_STATIC = "SEMI_STATIC"
    VOLATILE = "VOLATILE"


class FactType(str, Enum):
    FACT = "FACT"
    USER_PREFERENCE = "USER_PREFERENCE"
    TASK_DECISION = "TASK_DECISION"
    INFERENCE = "INFERENCE"
    DEFAULT = "DEFAULT"


# Precedence mapping (higher index = higher priority)
SOURCE_LAYER_PRIORITY = {
    "default": 0,
    "inferred": 1,
    "project_search": 2,
    "upstream_outputs": 3,
    "current_attachments": 4,
    "conversation": 5,
    "current_user": 6,
}


@dataclass
class ContextFact:
    dimension_id: str
    field_name: str
    value: Any
    source_layer: str            # 'current_user', 'conversation', 'current_attachments', 'upstream_outputs', 'project_search'
    source_ref: str              # e.g., 'current_turn', 'protocol_v2.md', 'evidence_table.json'
    fact_type: FactType = FactType.FACT
    volatility: FactVolatility = FactVolatility.SEMI_STATIC
    confidence: float = 1.0
    timestamp: float = 0.0
    domain_tags: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class ResolvedVariable:
    dimension_id: str
    field_name: str
    value: Any
    status: VariableStatus
    primary_fact: ContextFact
    overridden_facts: List[ContextFact] = field(default_factory=list)
    conflicting_facts: List[ContextFact] = field(default_factory=list)


class ContextProvider:
    """Abstract interface for context providers."""

    def get_source_layer(self) -> str:
        raise NotImplementedError

    def is_available(self) -> bool:
        return True

    def fetch_facts(
        self,
        task_prompt: str,
        target_dimension_ids: List[str],
        domain_hint: Optional[str] = None,
    ) -> List[ContextFact]:
        raise NotImplementedError


class ConversationContextProvider(ContextProvider):
    """Parses historical statements and user confirmations in ongoing conversation."""

    def __init__(self, turns: Optional[List[Dict[str, str]]] = None):
        self.turns = turns or []

    def get_source_layer(self) -> str:
        return "conversation"

    def fetch_facts(
        self,
        task_prompt: str,
        target_dimension_ids: List[str],
        domain_hint: Optional[str] = None,
    ) -> List[ContextFact]:
        facts: List[ContextFact] = []
        full_text = " ".join([turn.get("content", "") for turn in self.turns])
        if not full_text:
            return facts

        # Pattern: language constraint mentioned in prior turns
        if re.search(r"(仅限英文|only english|english only|只查英文)", full_text, re.IGNORECASE):
            facts.append(
                ContextFact(
                    dimension_id="D10",
                    field_name="language_scope",
                    value="en_only",
                    source_layer="conversation",
                    source_ref="conversation_history",
                    fact_type=FactType.USER_PREFERENCE,
                )
            )
        elif re.search(r"(中英双语|中英文|bilingual)", full_text, re.IGNORECASE):
            facts.append(
                ContextFact(
                    dimension_id="D10",
                    field_name="language_scope",
                    value="en_and_zh",
                    source_layer="conversation",
                    source_ref="conversation_history",
                    fact_type=FactType.USER_PREFERENCE,
                )
            )

        # Pattern: time range mentioned in prior turns
        m_time = re.search(r"(20\d{2})\s*(?:年)?\s*(?:至今|以后|起|–|-|~)\s*(20\d{2})?", full_text)
        if m_time:
            start_yr = m_time.group(1)
            end_yr = m_time.group(2) or "present"
            facts.append(
                ContextFact(
                    dimension_id="D8",
                    field_name="time_scope",
                    value=f"{start_yr}-{end_yr}",
                    source_layer="conversation",
                    source_ref="conversation_history",
                    fact_type=FactType.TASK_DECISION,
                )
            )

        # Pattern: exclude theses mentioned in prior turns
        if re.search(r"(不需要硕博|不要学位论文|排除学位论文|no theses|no dissertations)", full_text, re.IGNORECASE):
            facts.append(
                ContextFact(
                    dimension_id="D9",
                    field_name="document_types",
                    value="peer_reviewed_articles",
                    source_layer="conversation",
                    source_ref="conversation_history",
                    fact_type=FactType.USER_PREFERENCE,
                )
            )

        return facts


class AttachmentContextProvider(ContextProvider):
    """Extracts facts from attachments and uploaded task files."""

    def __init__(self, attachments: Optional[List[Dict[str, Any]]] = None):
        self.attachments = attachments or []

    def get_source_layer(self) -> str:
        return "current_attachments"

    def fetch_facts(
        self,
        task_prompt: str,
        target_dimension_ids: List[str],
        domain_hint: Optional[str] = None,
    ) -> List[ContextFact]:
        facts: List[ContextFact] = []
        for att in self.attachments:
            name = att.get("name", "")
            content = att.get("text", "")
            if not content and not name:
                continue

            # Check if full text document is available -> E2 fulltext_pdf
            if (
                name.endswith((".pdf", ".txt", ".md", ".docx", ".html"))
                or any(k in name.lower() for k in ("fulltext", "paper", "trial", "study", "article"))
                or len(content) > 50
            ):
                facts.append(
                    ContextFact(
                        dimension_id="E2",
                        field_name="corpus_boundary",
                        value="fulltext_pdf",
                        source_layer="current_attachments",
                        source_ref=name or "uploaded_document",
                        fact_type=FactType.FACT,
                        volatility=FactVolatility.STATIC,
                    )
                )

            # Check if multi-cohort or multi-dataset mentioned
            cohort_matches = re.findall(r"(?:cohort|dataset|treatment arm|assay)\s*([A-Z0-9]+|\b\d+\b)", content, re.IGNORECASE)
            distinct_cohorts = set(cohort_matches)
            if len(distinct_cohorts) >= 2:
                # Note: Do NOT pre-resolve E4 because deciding whether to isolate or aggregate multiple cohorts
                # is a methodological decision requiring user input or adaptive grill.
                facts.append(
                    ContextFact(
                        dimension_id="DETECTED_COHORTS",
                        field_name="detected_cohorts",
                        value=len(distinct_cohorts),
                        source_layer="current_attachments",
                        source_ref=f"{name} (multiple contexts detected: {len(distinct_cohorts)})",
                        fact_type=FactType.FACT,
                        notes=f"Detected multiple independent units: {list(distinct_cohorts)[:4]}",
                    )
                )

        return facts


class UpstreamArtifactContextProvider(ContextProvider):
    """Consumes artifacts from upstream ScholarFlow executions (e.g. Discovery -> Extraction -> Synthesis)."""

    def __init__(self, upstream_data: Optional[Dict[str, Any]] = None):
        self.upstream_data = upstream_data or {}

    def get_source_layer(self) -> str:
        return "upstream_outputs"

    def fetch_facts(
        self,
        task_prompt: str,
        target_dimension_ids: List[str],
        domain_hint: Optional[str] = None,
    ) -> List[ContextFact]:
        facts: List[ContextFact] = []
        if not self.upstream_data:
            return facts

        # If upstream has previous extraction schema snapshot -> reuse for E3
        if "extraction_schema" in self.upstream_data:
            facts.append(
                ContextFact(
                    dimension_id="E3",
                    field_name="schema_selection",
                    value=self.upstream_data["extraction_schema"],
                    source_layer="upstream_outputs",
                    source_ref="upstream_extraction_snapshot",
                    fact_type=FactType.TASK_DECISION,
                )
            )

        # If upstream has structured evidence table or records -> S3 audited_extraction_table
        if "evidence_records" in self.upstream_data or "evidence_table" in self.upstream_data:
            facts.append(
                ContextFact(
                    dimension_id="S3",
                    field_name="evidence_corpus_boundary",
                    value="audited_extraction_table",
                    source_layer="upstream_outputs",
                    source_ref="upstream_evidence_table",
                    fact_type=FactType.FACT,
                    notes=f"Found {len(self.upstream_data.get('evidence_records', []))} structured evidence records",
                )
            )

        # If upstream Discovery established search boundaries -> inherit
        if "search_protocol" in self.upstream_data:
            proto = self.upstream_data["search_protocol"]
            if "time_scope" in proto:
                facts.append(
                    ContextFact(
                        dimension_id="D8",
                        field_name="time_scope",
                        value=proto["time_scope"],
                        source_layer="upstream_outputs",
                        source_ref="upstream_search_protocol",
                        fact_type=FactType.TASK_DECISION,
                    )
                )

        return facts


class ProjectSearchContextProvider(ContextProvider):
    """Performs query-driven lookup in project files for unresolved variables with domain relevance filtering."""

    def __init__(self, project_docs: Optional[Dict[str, str]] = None, is_enabled: bool = True):
        self.project_docs = project_docs or {}
        self.is_enabled = is_enabled

    def get_source_layer(self) -> str:
        return "project_search"

    def is_available(self) -> bool:
        return self.is_enabled

    def fetch_facts(
        self,
        task_prompt: str,
        target_dimension_ids: List[str],
        domain_hint: Optional[str] = None,
    ) -> List[ContextFact]:
        if not self.is_enabled or not self.project_docs:
            return []

        facts: List[ContextFact] = []
        task_lower = task_prompt.lower()

        # Relevance scoring: filter out cross-domain orthogonal documents
        task_is_cs = bool(re.search(r"(transformer|algorithm|llm|benchmark|neural|model|deep learning)", task_lower))
        task_is_bio = bool(re.search(r"(cancer|patient|drug|clinical|trial|treatment|disease)", task_lower))
        task_is_eco = bool(re.search(r"(wildlife|species|ecology|fecal|dna|cervid|population|pcr)", task_lower))

        for filename, doc_text in self.project_docs.items():
            doc_lower = doc_text.lower()

            # Orthogonality guard: skip irrelevant files
            doc_is_eco = bool(re.search(r"(wildlife|species|ecology|biodiversity|habitat|zoology)", doc_lower))
            if task_is_cs and doc_is_eco:
                # Strictly ignore ecology files when task is computer science
                continue

            # Query-driven entity / population detection
            if "D3" in target_dimension_ids or "E2" in target_dimension_ids:
                m_target = re.search(r"(?:target entity|target disease|target population|research target|研究对象|目标对象|研究人群|目标人群)\s*[:：=]\s*([^\n,;，。]+)", doc_text, re.IGNORECASE)
                if m_target:
                    entity_val = m_target.group(1).strip()
                    facts.append(
                        ContextFact(
                            dimension_id="D3",
                            field_name="target_entity",
                            value=entity_val,
                            source_layer="project_search",
                            source_ref=filename,
                            fact_type=FactType.FACT,
                            volatility=FactVolatility.STATIC,
                        )
                    )

            # Query-driven sample size detection
            m_sample = re.search(r"(?:sample size|total sample|总样本量|样本量)\s*[:：=]\s*(\d+)", doc_text, re.IGNORECASE)
            if m_sample:
                facts.append(
                    ContextFact(
                        dimension_id="SAMPLE_SIZE",
                        field_name="sample_size",
                        value=int(m_sample.group(1)),
                        source_layer="project_search",
                        source_ref=filename,
                        fact_type=FactType.FACT,
                        volatility=FactVolatility.VOLATILE,
                    )
                )

        return facts


class ContextResolver:
    """Master orchestrator coordinating all context providers, precedence resolution, and conflict detection."""

    def __init__(self, scope: ContextScope = ContextScope.PROJECT_AWARE):
        self.scope = scope
        self.providers: List[ContextProvider] = []
        self.resolved_variables: Dict[str, ResolvedVariable] = {}
        self.unresolved_dimensions: List[str] = []
        self.conflicts: List[ResolvedVariable] = []

    def add_provider(self, provider: ContextProvider) -> None:
        if provider.is_available():
            self.providers.append(provider)

    def resolve(
        self,
        task_prompt: str,
        target_dimensions: List[str],
        domain_hint: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], List[str]]:
        """Resolve known parameters from all registered providers.

        Returns:
            inferred_values: dict mapping dimension_id -> resolved value (for GrillEngine)
            unresolved_dims: list of dimension_ids still needing user resolution
        """
        all_facts: List[ContextFact] = []

        # Layer 1: Parse current user message directly
        user_facts = self._parse_current_user_message(task_prompt)
        all_facts.extend(user_facts)

        # Query registered providers
        for prov in self.providers:
            # Respect scope restrictions
            if self.scope == ContextScope.CURRENT_ONLY and prov.get_source_layer() in ("upstream_outputs", "project_search"):
                continue
            if self.scope == ContextScope.CURRENT_PLUS_UPSTREAM and prov.get_source_layer() == "project_search":
                continue

            fetched = prov.fetch_facts(task_prompt, target_dimensions, domain_hint)
            all_facts.extend(fetched)

        # Group facts by dimension_id
        facts_by_dim: Dict[str, List[ContextFact]] = {}
        for f in all_facts:
            facts_by_dim.setdefault(f.dimension_id, []).append(f)

        inferred_values: Dict[str, Any] = {}
        self.resolved_variables.clear()
        self.conflicts.clear()

        # Resolve each dimension using strict precedence
        for dim_id in target_dimensions:
            dim_facts = facts_by_dim.get(dim_id, [])
            if not dim_facts:
                continue

            # Sort facts by source layer priority descending
            dim_facts.sort(key=lambda x: SOURCE_LAYER_PRIORITY.get(x.source_layer, 0), reverse=True)

            highest_layer = dim_facts[0].source_layer
            candidates_at_top = [f for f in dim_facts if f.source_layer == highest_layer]

            # Check for conflict at equal top layer
            distinct_values = {str(c.value).strip().lower(): c for c in candidates_at_top}
            if len(distinct_values) > 1:
                # Equal priority conflict!
                resolved_var = ResolvedVariable(
                    dimension_id=dim_id,
                    field_name=dim_facts[0].field_name,
                    value=None,
                    status=VariableStatus.UNRESOLVED_CONFLICT,
                    primary_fact=candidates_at_top[0],
                    conflicting_facts=candidates_at_top,
                )
                self.conflicts.append(resolved_var)
                self.resolved_variables[dim_id] = resolved_var
                continue

            # Single winner at top layer
            winner = candidates_at_top[0]
            if winner.value == "reuse_upstream_schema":
                upstream_candidates = [f for f in dim_facts if f.source_layer == "upstream_outputs"]
                if upstream_candidates:
                    winner = upstream_candidates[0]
            overridden = [f for f in dim_facts if f != winner and str(f.value).strip().lower() != str(winner.value).strip().lower()]

            status = (
                VariableStatus.RESOLVED_FROM_USER
                if winner.source_layer in ("current_user", "conversation")
                else VariableStatus.RESOLVED_FROM_CONTEXT
            )

            resolved_var = ResolvedVariable(
                dimension_id=dim_id,
                field_name=winner.field_name,
                value=winner.value,
                status=status,
                primary_fact=winner,
                overridden_facts=overridden,
            )
            self.resolved_variables[dim_id] = resolved_var
            inferred_values[dim_id] = winner.value

        # Identify unresolved dimensions
        self.unresolved_dimensions = [
            dim_id
            for dim_id in target_dimensions
            if dim_id not in inferred_values or dim_id in [c.dimension_id for c in self.conflicts]
        ]

        return inferred_values, self.unresolved_dimensions

    def _parse_current_user_message(self, text: str) -> List[ContextFact]:
        facts: List[ContextFact] = []
        cleaned = text.strip()

        # Time range: e.g. "2018-2024", "近5年", "2020年以后"
        m_time = re.search(r"(20\d{2})\s*(?:–|-|~|到)\s*(20\d{2})", cleaned)
        if m_time:
            facts.append(
                ContextFact(
                    dimension_id="D8",
                    field_name="time_scope",
                    value=f"{m_time.group(1)}-{m_time.group(2)}",
                    source_layer="current_user",
                    source_ref="current_user_message",
                    fact_type=FactType.TASK_DECISION,
                )
            )
        elif re.search(r"近\s*5\s*年", cleaned):
            facts.append(
                ContextFact(
                    dimension_id="D8",
                    field_name="time_scope",
                    value="recent_5y",
                    source_layer="current_user",
                    source_ref="current_user_message",
                    fact_type=FactType.TASK_DECISION,
                )
            )

        # Language: e.g. "英文", "仅限英文", "english only"
        if re.search(r"(仅限英文|only english|english only|只查英文)", cleaned, re.IGNORECASE):
            facts.append(
                ContextFact(
                    dimension_id="D10",
                    field_name="language_scope",
                    value="en_only",
                    source_layer="current_user",
                    source_ref="current_user_message",
                    fact_type=FactType.USER_PREFERENCE,
                )
            )

        # Document type: e.g. "不需要学位论文", "只要期刊"
        if re.search(r"(不需要硕博|不要学位论文|仅限期刊|journal only)", cleaned, re.IGNORECASE):
            facts.append(
                ContextFact(
                    dimension_id="D9",
                    field_name="document_types",
                    value="peer_reviewed_articles",
                    source_layer="current_user",
                    source_ref="current_user_message",
                    fact_type=FactType.USER_PREFERENCE,
                )
            )

        # Population / entity override: e.g. "这次包括儿童", "include children", "包含儿童"
        if re.search(r"(这次包括儿童|包含儿童|包括儿童|include children|including children)", cleaned, re.IGNORECASE):
            facts.append(
                ContextFact(
                    dimension_id="D3",
                    field_name="target_entity",
                    value="adults + children",
                    source_layer="current_user",
                    source_ref="current_user_message",
                    fact_type=FactType.TASK_DECISION,
                )
            )

        # Schema selection: e.g. "使用通用实证Schema", "继续按上一篇的标准提取"
        if "general_empirical" in cleaned or "通用实证" in cleaned:
            facts.append(
                ContextFact(
                    dimension_id="E3",
                    field_name="schema_selection",
                    value="general_empirical_v1",
                    source_layer="current_user",
                    source_ref="current_user_message",
                    fact_type=FactType.TASK_DECISION,
                )
            )
        elif re.search(r"(按上一篇|复用上一篇|上篇标准|按上篇)", cleaned):
            facts.append(
                ContextFact(
                    dimension_id="E3",
                    field_name="schema_selection",
                    value="reuse_upstream_schema",
                    source_layer="current_user",
                    source_ref="current_user_message",
                    fact_type=FactType.TASK_DECISION,
                )
            )

        return facts

    def render_context_brief_markdown(self) -> str:
        """Render concise human-readable brief for Stage 0B presentation."""
        lines = ["### 现有科研上下文确认简报 (Context Resolution Brief)"]
        if self.resolved_variables:
            lines.append("**已从当前上下文自动确认以下要素 (无需重复确认)**：")
            for dim_id, var in self.resolved_variables.items():
                if var.status != VariableStatus.UNRESOLVED_CONFLICT:
                    val_str = str(var.value)
                    src_str = f"来源: `{var.primary_fact.source_layer}` ({var.primary_fact.source_ref})"
                    lines.append(f"- **{var.field_name}** (`{dim_id}`): `{val_str}` — *[{src_str}]*")
                    if var.overridden_facts:
                        over_str = f"覆盖历史设置: `{var.overridden_facts[0].value}` from `{var.overridden_facts[0].source_ref}`"
                        lines.append(f"  *(注: {over_str})*")
        else:
            lines.append("*未从前序上下文与文档中检测到已知约束，进入全量自适应决策。*")

        if self.conflicts:
            lines.append("")
            lines.append("⚠️ **检测到以下待仲裁的同级上下文冲突**：")
            for c in self.conflicts:
                con_list = [f"`{f.value}` ({f.source_ref})" for f in c.conflicting_facts]
                lines.append(f"- **{c.field_name}** (`{c.dimension_id}`): 存在分歧 -> " + " vs ".join(con_list))

        return "\n".join(lines)
