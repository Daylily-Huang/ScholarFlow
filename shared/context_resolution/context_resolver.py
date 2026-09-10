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


class DepthIntent(str, Enum):
    """Classification of a depth-keyword mention inside a text span (R01).

    Only ``DECISION`` may be treated as an explicit user selection. Every other
    member must stay unresolved (or be presented as a non-decision) so that a
    keyword mention can never masquerade as a confirmed execution depth.
    """

    NONE = "NONE"                  # No depth keyword at all
    DECISION = "DECISION"          # Affirmative selection by the current user
    CORRECTED = "CORRECTED"        # Explicit self-correction; last value wins
    NEGATED = "NEGATED"            # "不要用深度模式" -> explicitly declined
    QUESTION = "QUESTION"          # "深度模式是什么意思" -> asking, not choosing
    QUOTED = "QUOTED"              # Direct quotation of someone else's wording
    CONDITIONAL = "CONDITIONAL"    # "如果时间够就用深度档" -> not committed
    AMBIGUOUS = "AMBIGUOUS"        # Two conflicting selections, no correction

    @property
    def is_confirmable(self) -> bool:
        """Whether this intent may unlock an explicit-selection dimension."""
        return self in (DepthIntent.DECISION, DepthIntent.CORRECTED)


@dataclass
class ExecutionDepthIntentResult:
    """Structured outcome of depth-intent detection (R01).

    Replaces the previous bare ``Optional[str]`` return so that callers can
    distinguish "extracted a word" from "the user actually confirmed it".
    """

    intent: DepthIntent = DepthIntent.NONE
    value: Optional[str] = None            # Canonical depth value, only when confirmable
    source: str = "text"                   # Where the signal came from
    scope: str = "current_run"             # Applicability of the decision
    ambiguity: bool = False
    candidates: List[str] = field(default_factory=list)
    evidence: str = ""                     # The matched span, for auditability
    reason: str = ""                       # Why this classification was reached

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent.value,
            "value": self.value,
            "source": self.source,
            "scope": self.scope,
            "ambiguity": self.ambiguity,
            "candidates": list(self.candidates),
            "evidence": self.evidence,
            "reason": self.reason,
        }


# Depth-surface forms that are NOT depth selections. Masking happens before any
# keyword scan so that "深度学习" can never be read as "深度档". Patterns are
# deliberately narrow (lookahead-bound) so that legitimate tier words such as a
# bare "中等" alias or "快速模式" survive masking.
_DEPTH_FALSE_POSITIVE_PATTERNS = (
    # 深度 + domain noun (never a tier)
    r"深度(?=学习|神经网络|网络|模型|融合|参与|访谈|分析|阅读|挖掘|合作|交流|改革|报道|调查)",
    r"deep\s+(?=learning|neural|network|model|fusion|dive|read)",
    # 快速 + domain noun (never a tier)
    r"快速(?=检测|测定|筛查|诊断|方法|响应|原型|充电|排序|幂|部署|上手|验证|评估|检测法)",
    r"rapid\s+(?=detection|test|prototyp|response|sort|charging)",
    # 标准 as a norm/reference, not a tier
    r"标准(?=差|偏差|化|规范|文件|委员会|值|品|物质|溶液|曲线|误|误差|大气压|状况)",
    r"(?<=国家|行业|国际|地方|企业|技术|安全|质量|检测)标准",
    r"金标准",
    r"standard\s+(?=deviation|error|curve|solution|reference|committee|operating)",
    r"gold\s+standard",
    # 中等 + domain noun (never the "standard tier" alias)
    r"中等(?=收入|规模|水平|教育|城市|城市群|职业|专业|技术|强度|大小|体型|以上|以下)",
    # 快速/中等 in clearly adjectival verb phrases
    r"快速(?=增长|发展|上升|下降|变化|扩张|增加|减少)",
)

# Someone else proposing/discussing a tier is not the current user selecting it.
# Split by direction: a *preceding* attribution means the tier is reported speech
# ("作者建议深度模式"), a *trailing* attribution means the tier is being inquired
# about ("深度模式的文献"). A trailing topic noun far to the right is just wording.
_ATTRIBUTION_BEFORE_MARKERS = (
    "建议", "推荐", "作者", "论文中", "文献中", "原文", "有人", "他说", "她说",
    "据称", "声称", "提到过", "讨论", "询问", "考虑", "是否需要", "要不要",
    "suggest", "recommend", "author",
)
_ATTRIBUTION_AFTER_MARKERS = (
    "是什么", "什么意思", "有哪些", "怎么样", "的文献", "的论文", "的说法",
)
_NON_DECISION_ATTRIBUTION_MARKERS = _ATTRIBUTION_BEFORE_MARKERS + _ATTRIBUTION_AFTER_MARKERS

# A depth keyword plus an optional tier suffix. Used for candidate extraction.
# The lookbehind stops "标准深度" from being read as two competing tiers.
_DEPTH_KEYWORD_PATTERN = re.compile(
    r"(?P<word>快速|标准|深度|中等|quick|standard|deep)"
    r"(?:\s*(?P<suffix>模式|档位|档次|档|运行|执行|level|tier|mode|depth))?",
    re.IGNORECASE,
)

# Suffixes that make a bare keyword a genuine tier reference ("深度模式").
_TIER_SUFFIXES = ("模式", "档位", "档次", "档", "运行", "执行", "level", "tier", "mode", "depth")

_NEGATION_MARKERS = (
    "不要", "不用", "不想", "别用", "别选", "不选", "不采用", "不使用", "不按",
    "取消", "无需", "不必", "禁止", "避免", "拒绝", "排除", "否掉", "否",
    "do not", "don't", "dont", "no need", "avoid", "cancel", "without",
)

_QUESTION_MARKERS = (
    "是什么意思", "什么意思", "是什么", "有哪些", "哪种", "哪个", "怎么", "如何",
    "是否", "能否", "可以吗", "行吗", "吗", "呢", "为何", "为什么", "解释",
    "what is", "what's", "which", "how ", "why", "does ", "should ",
)

_QUOTE_PAIRS = (("“", "”"), ("「", "」"), ("『", "』"), ('"', '"'), ("'", "'"), ("《", "》"))

_CORRECTION_MARKERS = (
    "不，", "不,", "不对", "不是", "更正", "纠正", "更正为",
    "应该说", "准确说", "准确地说", "其实", "而是", "重新选",
    "rather", "instead", "correction", "actually",
)

# An explicit switch is stronger than a bare negation: it replaces the earlier
# tier instead of merely declining it ("不要用标准档，改用快速档" -> quick).
_SWITCH_MARKERS = (
    "改用", "换成", "换为", "换到", "改选", "重选", "重新选", "改为用",
    "switch to", "change to", "instead use",
)

_CONDITIONAL_MARKERS = (
    "如果", "假如", "若", "要是", "万一", "除非", "取决于", "看情况",
    "if ", "unless", "depending",
)

# Commitment verbs that turn a hedge into an instruction. "就"/"则" are omitted
# on purpose: they are the standard Chinese conditional correlatives.
_COMMITMENT_MARKERS = ("请你", "帮我", "请用", "决定", "确定", "采用", "开始", "执行", "please ")

_CLAUSE_SPLIT_PATTERN = re.compile(r"[，。！？；、\n\r\t]+|[!?;]+")


def _iter_protected_quote_spans(text: str) -> List[Tuple[int, int]]:
    """Return character spans that sit inside a quotation pair.

    Quoted wording is treated as reported speech, never as the user's own
    instruction, so a quoted depth keyword must not confirm anything.
    """
    spans: List[Tuple[int, int]] = []
    for open_ch, close_ch in _QUOTE_PAIRS:
        start = 0
        while True:
            begin = text.find(open_ch, start)
            if begin == -1:
                break
            end = text.find(close_ch, begin + 1)
            if end == -1:
                # Unterminated quote: treat the remainder as quoted.
                spans.append((begin, len(text)))
                break
            spans.append((begin, end))
            start = end + 1
    return spans


def _offset_in_spans(offset: int, spans: List[Tuple[int, int]]) -> bool:
    return any(begin <= offset <= end for begin, end in spans)


def _iter_clauses_with_offsets(text: str) -> List[Tuple[str, int]]:
    """Split ``text`` into clause-level spans, without cutting inside quotes.

    Chinese quotation marks routinely contain commas ("论文中写着“采用深度模式，
    但样本少”"), so a naive punctuation split would leak quoted wording into a
    standalone clause and misread it as a user decision.
    """
    protected = _iter_protected_quote_spans(text)
    clauses: List[Tuple[str, int]] = []
    start = 0
    for idx, ch in enumerate(text):
        if ch not in "，。！？；、\n\r\t!?;":
            continue
        if _offset_in_spans(idx, protected):
            continue
        chunk = text[start:idx].strip()
        if chunk:
            clauses.append((chunk, start))
        start = idx + 1
    tail = text[start:].strip()
    if tail:
        clauses.append((tail, start))
    return clauses


def _iter_sentences_with_offsets(text: str) -> List[Tuple[str, int]]:
    """Split ``text`` into sentence-level spans, never cutting inside quotes."""
    protected = _iter_protected_quote_spans(text)
    sentences: List[Tuple[str, int]] = []
    start = 0
    for idx, ch in enumerate(text):
        if ch not in "。！？!?\n\r；;":
            continue
        if _offset_in_spans(idx, protected):
            continue
        chunk = text[start:idx].strip()
        if chunk:
            sentences.append((chunk, start))
        start = idx + 1
    tail = text[start:].strip()
    if tail:
        sentences.append((tail, start))
    return sentences


def _contains_any(haystack: str, needles: Tuple[str, ...]) -> Optional[str]:
    for needle in needles:
        if needle in haystack:
            return needle
    return None


def _has_adjacent_marker(
    clause_text: str,
    clause_offset: int,
    mention_offset: int,
    markers: Tuple[str, ...],
    before: int = 6,
    after: int = 4,
) -> bool:
    """Whether an attribution marker sits tightly around a mention.

    The window is deliberately small: a topic noun several characters away
    ("检索...文献") is ordinary wording, not attribution of the tier choice.
    """
    local = mention_offset - clause_offset
    local_start = max(0, local - before)
    local_end = min(len(clause_text), local + after)
    window = clause_text[local_start:local_end]
    return any(marker in window for marker in markers)


def classify_execution_depth_intent(
    text: str,
    source: str = "current_user",
    scope: str = "current_run",
) -> ExecutionDepthIntentResult:
    """Classify whether ``text`` contains a *confirmed* execution-depth selection (R01).

    Extraction and confirmation are deliberately separate concerns here. The
    function still finds depth keywords, but only an affirmative selection made
    by the current user is reported as confirmable; negation, questions,
    quotations, conditionals and unresolved multi-mentions are reported as
    non-decisions with an auditable reason.
    """
    from shared.execution.selection import normalize_depth

    if not text or not text.strip():
        return ExecutionDepthIntentResult(reason="empty_text")

    # 1. Mask surface forms that merely contain a depth keyword.
    masked = text
    for pattern in _DEPTH_FALSE_POSITIVE_PATTERNS:
        masked = re.sub(pattern, "___MASKED___", masked, flags=re.IGNORECASE)

    protected = _iter_protected_quote_spans(masked)

    # 2. Collect genuine tier mentions as (offset, canonical_value, span_text).
    mentions: List[Tuple[int, str, str]] = []
    for m in _DEPTH_KEYWORD_PATTERN.finditer(masked):
        if m.group("word").startswith("___"):
            continue
        suffix = (m.group("suffix") or "").strip().lower()
        in_quote = _offset_in_spans(m.start(), protected)
        # A bare keyword is only a tier reference when it carries a tier suffix,
        # unless it is quoted (reported speech), an explicit command prefix, or
        # the entire message (a bare "中等" reply to the depth question).
        if not suffix and not in_quote:
            preceding = masked[max(0, m.start() - 6):m.start()].strip()
            whole_message = masked.strip() == m.group(0).strip()
            # Only a command prefix *immediately* before the tier word counts;
            # "标准深度" must not be read as two tiers just because "按" is
            # nearby in "按标准深度".
            has_command_prefix = any(
                preceding.endswith(p)
                for p in ("用", "按", "选", "走", "以", "成", "到", "为", "是", "set", "use", "to")
            )
            if not whole_message and not has_command_prefix:
                continue
        norm = normalize_depth(m.group("word"))
        if not norm:
            continue
        mentions.append((m.start(), norm.value, m.group(0).strip()))

    # A standard-tier word immediately followed by a depth-form modifier
    # ("标准深度", "标准档深度") is one compound phrase, not two competing tiers.
    # The gap stays at one character, so "用深度档还是标准档" keeps both mentions.
    compound_filtered: List[Tuple[int, str, str]] = []
    for offset, value, span in mentions:
        gap_end = offset + len(span)
        swallowed = any(
            gap_end <= other_offset <= gap_end + 1 and other_span.startswith("深度")
            for other_offset, _, other_span in mentions
            if other_offset != offset
        )
        if not swallowed:
            compound_filtered.append((offset, value, span))
    if compound_filtered:
        mentions = compound_filtered

    if not mentions:
        return ExecutionDepthIntentResult(reason="no_depth_mention")

    # 3. Quoted mentions are reported speech, not user instructions.
    unquoted = [item for item in mentions if not _offset_in_spans(item[0], protected)]
    if not unquoted:
        return ExecutionDepthIntentResult(
            intent=DepthIntent.QUOTED,
            source=source,
            scope=scope,
            evidence=mentions[0][2],
            reason="depth_mention_inside_quotation",
        )

    # 4. Classify clause by clause so negation/question scope stays local.
    clauses = _iter_clauses_with_offsets(masked)
    correction_marker: Optional[str] = None
    conditional_marker: Optional[str] = None
    negation_marker: Optional[str] = None
    question_marker: Optional[str] = None
    attribution_marker: Optional[str] = None
    conditional_clause_committed = False

    for clause_text, clause_offset in clauses:
        clause_end = clause_offset + len(clause_text)
        clause_mentions = [item for item in unquoted if clause_offset <= item[0] <= clause_end]
        found_correction = _contains_any(clause_text, _CORRECTION_MARKERS)
        found_negation = _contains_any(clause_text, _NEGATION_MARKERS)
        found_conditional = _contains_any(clause_text, _CONDITIONAL_MARKERS)
        found_question = _contains_any(clause_text, _QUESTION_MARKERS)
        found_attribution = _contains_any(clause_text, _NON_DECISION_ATTRIBUTION_MARKERS)
        if found_correction:
            correction_marker = correction_marker or found_correction
        if found_negation:
            negation_marker = negation_marker or found_negation
        if found_conditional:
            conditional_marker = conditional_marker or found_conditional
        if found_question:
            question_marker = question_marker or found_question
        if found_attribution and clause_mentions:
            # Attribution must sit *next to* the tier word. A distant "文献"
            # elsewhere in a long clause is topic wording, not attribution.
            for mention_offset, _, _ in clause_mentions:
                if _has_adjacent_marker(
                    clause_text, clause_offset, mention_offset, _ATTRIBUTION_BEFORE_MARKERS
                ) or _has_adjacent_marker(
                    clause_text, clause_offset, mention_offset, _ATTRIBUTION_AFTER_MARKERS
                ):
                    attribution_marker = attribution_marker or found_attribution
                    break
    # "这次不用深度，换成快速": the switch target wins over the negated tier.
    switch_override: Optional[Tuple[str, str]] = None
    for offset, value, span in unquoted:
        tail_start = offset + len(span)
        tail = masked[tail_start:tail_start + 12]
        stop = _CLAUSE_SPLIT_PATTERN.search(tail)
        if stop:
            tail = tail[:stop.start()]
        tail_marker = _contains_any(tail, _SWITCH_MARKERS)
        if tail_marker:
            switch_override = (value, tail_marker)
            break

    for clause_text, clause_offset in clauses:
        # A conditional only commits the user when the *same clause* also
        # carries a commitment verb ("如果时间够就请你用深度档").
        if found_conditional and clause_mentions:
            if any(marker in clause_text for marker in _COMMITMENT_MARKERS):
                conditional_clause_committed = True

    # A conditional that spans clauses ("如果时间够就用深度档") is still a hedge,
    # so a commitment verb only counts when it lands in a *separate sentence*
    # ("如果样本多就用深度档。请用深度档。").
    if conditional_marker and not conditional_clause_committed:
        for sentence, sentence_offset in _iter_sentences_with_offsets(masked):
            sentence_end = sentence_offset + len(sentence)
            sentence_mentions = [item for item in unquoted if sentence_offset <= item[0] <= sentence_end]
            if not sentence_mentions:
                continue
            if _contains_any(sentence, _CONDITIONAL_MARKERS):
                continue
            if any(marker in sentence for marker in _COMMITMENT_MARKERS):
                conditional_clause_committed = True
                break

    # An explicit switch ("不要用标准档，改用快速档") revises the earlier tier.
    if not correction_marker and switch_override:
        # Prefer the tier named right after the switch verb.
        candidates.clear()
        candidates.append(switch_override[0])
        return _result(
            DepthIntent.CORRECTED,
            switch_override[0],
            f"explicit_switch_via:{switch_override[1]}",
        )

    if not correction_marker:
        switch_marker = _contains_any(masked, _SWITCH_MARKERS)
        if switch_marker:
            correction_marker = switch_marker

    # A mid-sentence self-correction ("先用快速模式，不，改用深度模式") is split
    # across clauses by the comma, so also look for the correction marker in the
    # whole span whenever more than one tier was mentioned.
    if not correction_marker and len({item[1] for item in unquoted}) > 1:
        correction_marker = _contains_any(masked, _CORRECTION_MARKERS)

    # A trailing question mark over the whole span is also an interrogative.
    if not question_marker and re.search(r"[?？]\s*$", text.strip()):
        question_marker = "?"

    candidates: List[str] = []
    for _, value, _ in unquoted:
        if value not in candidates:
            candidates.append(value)

    def _result(intent: DepthIntent, value: Optional[str], reason: str, evidence: str = "") -> ExecutionDepthIntentResult:
        return ExecutionDepthIntentResult(
            intent=intent,
            value=value,
            source=source,
            scope=scope,
            ambiguity=intent == DepthIntent.AMBIGUOUS,
            candidates=list(candidates),
            evidence=evidence or (unquoted[-1][2] if unquoted else ""),
            reason=reason,
        )

    # An explicit self-correction overrides everything else: the user is
    # actively revising their own earlier statement, so the last value wins.
    if correction_marker:
        last_value = unquoted[-1][1]
        return _result(
            DepthIntent.CORRECTED,
            last_value,
            f"explicit_correction_via:{correction_marker}",
        )

    if negation_marker and not switch_override:
        return _result(DepthIntent.NEGATED, None, f"negation_marker:{negation_marker}")

    if question_marker:
        return _result(DepthIntent.QUESTION, None, f"question_marker:{question_marker}")

    if attribution_marker:
        return _result(
            DepthIntent.AMBIGUOUS,
            None,
            f"tier_attributed_to_third_party:{attribution_marker}",
        )

    if conditional_marker and not conditional_clause_committed:
        return _result(
            DepthIntent.CONDITIONAL,
            None,
            f"conditional_marker_without_commitment:{conditional_marker}",
        )

    if len(candidates) > 1:
        return _result(
            DepthIntent.AMBIGUOUS,
            None,
            "multiple_conflicting_depth_mentions_without_correction",
        )

    return _result(DepthIntent.DECISION, candidates[0], "affirmative_user_selection")


def extract_execution_depth_from_text(text: str) -> Optional[str]:
    """Backward-compatible wrapper returning only a *confirmable* depth value (R01).

    Returns ``None`` for negations, questions, quotations, conditionals and
    unresolved conflicts, so existing callers can no longer treat a keyword
    mention as a confirmed selection.
    """
    result = classify_execution_depth_intent(text)
    return result.value if result.intent.is_confirmable else None


class ConversationContextProvider(ContextProvider):
    """Parses historical statements and user confirmations in ongoing conversation.

    Only user-role turns may establish a decision (R01). An assistant message
    that *recommends* a tier is not the user's selection, so it must never
    resolve an explicit-selection dimension.
    """

    def __init__(self, turns: Optional[List[Dict[str, str]]] = None):
        self.turns = turns or []

    def get_source_layer(self) -> str:
        return "conversation"

    @staticmethod
    def _is_user_turn(turn: Dict[str, Any]) -> bool:
        """Treat a turn without a role as user content for backward compatibility."""
        role = str(turn.get("role", "user") or "user").strip().lower()
        return role in ("user", "human", "current_user")

    def fetch_facts(
        self,
        task_prompt: str,
        target_dimension_ids: List[str],
        domain_hint: Optional[str] = None,
    ) -> List[ContextFact]:
        facts: List[ContextFact] = []
        if not self.turns:
            return facts

        resolved_dims: Set[str] = set()

        # Scan from newest to oldest turn so latest confirmed decisions win (P1-02 / 42.C)
        for turn_idx, turn in enumerate(reversed(self.turns)):
            content = turn.get("content", "")
            if not content:
                continue

            is_user_turn = self._is_user_turn(turn)
            timestamp = float(turn.get("timestamp", len(self.turns) - turn_idx))

            # Pattern: execution depth mentioned in prior turns (T06, T07 / R01).
            # Only a user-role turn can establish the decision; assistant prose
            # that merely recommends a tier must not resolve the dimension.
            if is_user_turn and "EXECUTION_DEPTH" not in resolved_dims:
                intent = classify_execution_depth_intent(
                    content,
                    source="conversation",
                    scope="current_run",
                )
                if intent.intent.is_confirmable and intent.value:
                    facts.append(
                        ContextFact(
                            dimension_id="EXECUTION_DEPTH",
                            field_name="execution_depth",
                            value=intent.value,
                            source_layer="conversation",
                            source_ref=f"conversation_turn_{len(self.turns)-turn_idx}",
                            fact_type=FactType.TASK_DECISION,
                            volatility=FactVolatility.VOLATILE,
                            timestamp=timestamp,
                            notes=f"intent={intent.intent.value};{intent.reason}",
                        )
                    )
                    resolved_dims.add("EXECUTION_DEPTH")

            # Pattern: language constraint mentioned in prior turns
            if "D10" not in resolved_dims:
                if re.search(r"(中英双语|中英文|bilingual|zh_and_en|en_and_zh)", content, re.IGNORECASE):
                    facts.append(
                        ContextFact(
                            dimension_id="D10",
                            field_name="language_scope",
                            value="en_and_zh",
                            source_layer="conversation",
                            source_ref=f"conversation_turn_{len(self.turns)-turn_idx}",
                            fact_type=FactType.USER_PREFERENCE,
                            volatility=FactVolatility.VOLATILE,
                            timestamp=timestamp,
                        )
                    )
                    resolved_dims.add("D10")
                elif re.search(r"(仅限英文|only english|english only|只查英文|en_only)", content, re.IGNORECASE):
                    facts.append(
                        ContextFact(
                            dimension_id="D10",
                            field_name="language_scope",
                            value="en_only",
                            source_layer="conversation",
                            source_ref=f"conversation_turn_{len(self.turns)-turn_idx}",
                            fact_type=FactType.USER_PREFERENCE,
                            volatility=FactVolatility.VOLATILE,
                            timestamp=timestamp,
                        )
                    )
                    resolved_dims.add("D10")

            # Pattern: time range mentioned in prior turns
            if "D8" not in resolved_dims:
                m_time = re.search(r"(20\d{2})\s*(?:年)?\s*(?:至今|以后|起|–|-|~)\s*(20\d{2})?", content)
                if m_time:
                    start_yr = m_time.group(1)
                    end_yr = m_time.group(2) or "present"
                    facts.append(
                        ContextFact(
                            dimension_id="D8",
                            field_name="time_scope",
                            value=f"{start_yr}-{end_yr}",
                            source_layer="conversation",
                            source_ref=f"conversation_turn_{len(self.turns)-turn_idx}",
                            fact_type=FactType.TASK_DECISION,
                            volatility=FactVolatility.VOLATILE,
                            timestamp=timestamp,
                        )
                    )
                    resolved_dims.add("D8")

            # Pattern: exclude theses mentioned in prior turns
            if "D9" not in resolved_dims:
                if re.search(r"(不需要硕博|不要学位论文|排除学位论文|no theses|no dissertations)", content, re.IGNORECASE):
                    facts.append(
                        ContextFact(
                            dimension_id="D9",
                            field_name="document_types",
                            value="peer_reviewed_articles",
                            source_layer="conversation",
                            source_ref=f"conversation_turn_{len(self.turns)-turn_idx}",
                            fact_type=FactType.USER_PREFERENCE,
                            volatility=FactVolatility.VOLATILE,
                            timestamp=timestamp,
                        )
                    )
                    resolved_dims.add("D9")

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

            name_lower = name.lower()
            content_lower = content.lower()

            # Determine document kind (P1-01 / 42.B)
            if any(k in name_lower for k in ("protocol", "plan", "方案", "设计", "流程")):
                doc_kind = "PROTOCOL"
            elif any(k in name_lower for k in ("note", "meeting", "readme", "笔记", "会议", "说明")):
                doc_kind = "NOTES"
            elif name_lower.endswith((".csv", ".tsv", ".xlsx")) or any(k in name_lower for k in ("table", "data", "matrix", "数据", "表格")):
                doc_kind = "DATA_TABLE"
            elif any(k in name_lower for k in ("supplement", "appendix", "附录", "补充")):
                doc_kind = "SUPPLEMENT"
            elif (
                name_lower.endswith(".pdf")
                or any(k in name_lower for k in ("fulltext", "paper", "article", "manuscript", "journal", "thesis", "dissertation", "trial", "study", "clinical", "论文", "文献"))
                or (len(content) > 200 and any(k in content_lower for k in ("abstract", "introduction", "references", "doi:", "methods", "results")))
            ):
                doc_kind = "PAPER_FULLTEXT"
            else:
                doc_kind = "UNKNOWN"

            facts.append(
                ContextFact(
                    dimension_id="DOC_KIND",
                    field_name="document_kind",
                    value=doc_kind,
                    source_layer="current_attachments",
                    source_ref=name or "uploaded_document",
                    fact_type=FactType.FACT,
                    volatility=FactVolatility.STATIC,
                )
            )

            # Check if full text document is available -> E2 fulltext_pdf (Only PAPER_FULLTEXT unlocks E2)
            if doc_kind == "PAPER_FULLTEXT":
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

    def __init__(
        self,
        upstream_data: Optional[Dict[str, Any]] = None,
        current_run_id: Optional[str] = None,
    ):
        self.upstream_data = upstream_data or {}
        #: The run currently being executed. Resource authorisation never
        #: transfers across runs, so this must match the upstream run id (R07).
        self.current_run_id = current_run_id
        #: Auditable record of upstream configuration that was NOT inherited.
        self.rejected_inheritance: List[Dict[str, Any]] = []

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

        # Inherit the confirmed execution depth only from the SAME run (T11, R07).
        inherited = self._resolve_inherited_execution_depth()
        if inherited is not None:
            depth_value, source_ref, rationale = inherited
            facts.append(
                ContextFact(
                    dimension_id="EXECUTION_DEPTH",
                    field_name="execution_depth",
                    value=depth_value,
                    source_layer="upstream_outputs",
                    source_ref=source_ref,
                    fact_type=FactType.TASK_DECISION,
                    notes="%s|run_binding=verified" % rationale,
                )
            )

        return facts

    def _resolve_inherited_execution_depth(self):
        """Return ``(depth, source_ref, rationale)`` for a same-run confirmation.

        Scientific evidence carried by the upstream artifact stays usable
        regardless; only the *resource authorisation* is run-bound. A missing or
        mismatched ``run_id``, or an unconfirmed selection, is recorded in
        :attr:`rejected_inheritance` and yields no inherited depth at all.
        """
        payload = None
        source_ref = "upstream_execution_profile"
        if isinstance(self.upstream_data.get("execution_profile"), (dict,)):
            payload = self.upstream_data["execution_profile"]
        elif isinstance(self.upstream_data.get("execution_profile"), object) and hasattr(
            self.upstream_data.get("execution_profile"), "to_dict"
        ):
            payload = self.upstream_data["execution_profile"].to_dict()
        elif "execution_depth" in self.upstream_data:
            payload = {"depth": self.upstream_data["execution_depth"]}
            source_ref = "upstream_execution_depth"

        if payload is None:
            return None

        upstream_run_id = self.upstream_data.get("run_id") or payload.get("run_id")

        if not upstream_run_id:
            self.rejected_inheritance.append(
                {
                    "reason": "missing_run_id",
                    "message": (
                        "Upstream execution configuration carries no run_id; "
                        "resource authorisation cannot be inherited."
                    ),
                }
            )
            return None

        # No current run on record means resource authorisation cannot be
        # verified, so it is not inherited (R07). Scientific evidence carried by
        # the same artifact remains usable.
        if not self.current_run_id:
            self.rejected_inheritance.append(
                {
                    "reason": "no_current_run",
                    "upstream_run_id": upstream_run_id,
                    "message": (
                        "No current run_id is known; upstream resource "
                        "authorisation cannot be verified for this run."
                    ),
                }
            )
            return None

        if upstream_run_id != self.current_run_id:
            self.rejected_inheritance.append(
                {
                    "reason": "run_id_mismatch",
                    "upstream_run_id": upstream_run_id,
                    "current_run_id": self.current_run_id,
                    "message": (
                        "Upstream configuration belongs to run %r, not %r."
                        % (upstream_run_id, self.current_run_id)
                    ),
                }
            )
            return None

        selection = payload.get("selection")
        if isinstance(selection, dict):
            status = str(selection.get("status", "")).lower()
            if status and status != "confirmed":
                self.rejected_inheritance.append(
                    {
                        "reason": "unconfirmed_selection",
                        "upstream_run_id": upstream_run_id,
                        "selection_status": status,
                        "message": (
                            "Upstream run %r has an unconfirmed depth selection."
                            % upstream_run_id
                        ),
                    }
                )
                return None

        depth_raw = payload.get("depth", payload.get("execution_depth"))
        if depth_raw is None:
            self.rejected_inheritance.append(
                {"reason": "missing_depth", "upstream_run_id": upstream_run_id,
                 "message": "Upstream configuration carries no depth value."}
            )
            return None

        from shared.execution.selection import normalize_depth

        normalized = normalize_depth(depth_raw.value if hasattr(depth_raw, "value") else str(depth_raw))
        if normalized is None:
            self.rejected_inheritance.append(
                {"reason": "invalid_depth", "upstream_run_id": upstream_run_id,
                 "upstream_value": str(depth_raw),
                 "message": "Upstream depth %r is not a valid tier." % (depth_raw,)}
            )
            return None

        return (
            normalized.value,
            source_ref,
            "Inherited from confirmed upstream run %s" % upstream_run_id,
        )


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

        # Canonical domain detection and orthogonality filter (P1-03 / 42.E)
        def _detect_domains(text: str) -> Set[str]:
            t = text.lower()
            domains = set()
            if re.search(r"(transformer|algorithm|llm|benchmark|neural|model|deep learning|software|code|gpu|compute)", t):
                domains.add("computer_science")
            if re.search(r"(wildlife|species|ecology|biodiversity|habitat|zoology|fecal|cervid|population|dna|pcr|conservation)", t):
                domains.add("ecology_environment")
            if re.search(r"(patient|clinical|drug|disease|trial|therapy|treatment|cancer|hospital|medical|immunotherapy)", t):
                domains.add("biomedical")
            if re.search(r"(synthesis|catalyst|molecule|chemical|polymer|nanoparticle|reaction)", t):
                domains.add("chemistry_materials")
            if re.search(r"(physics|quantum|optics|mechanics|thermodynamic)", t):
                domains.add("physical_sciences")
            if re.search(r"(survey|interview|policy|economy|economic|social|sociology|education)", t):
                domains.add("social_sciences")
            return domains

        DOMAIN_ALIASES = {
            "clinical": "biomedical",
            "medicine": "biomedical",
            "molecular_biology": "life_sciences",
            "ecology": "ecology_environment",
            "environmental": "ecology_environment",
        }
        task_domains = _detect_domains(task_prompt)
        if domain_hint:
            hint_norm = DOMAIN_ALIASES.get(domain_hint.lower(), domain_hint.lower())
            task_domains.add(hint_norm)
            task_domains.update(_detect_domains(domain_hint))

        for filename, doc_text in self.project_docs.items():
            doc_domains = _detect_domains(doc_text + " " + filename)

            # Orthogonality guard: skip irrelevant files with zero domain overlap
            if task_domains and doc_domains and not task_domains.intersection(doc_domains):
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

            # Query-driven sample size detection.
            #
            # NOTE: `SAMPLE_SIZE` is NOT a Grill dimension -- no skill registers
            # it, so `GrillEngine.select_questions()` never passes it in
            # `target_dimensions` and this fact is filtered out of the normal
            # Stage 0 flow. It stays because the fact is a live carrier for the
            # equal-layer conflict path: callers that request the key explicitly
            # (and their tests) rely on two project files disagreeing here to
            # produce UNRESOLVED_CONFLICT. Do not mistake its presence for
            # Stage 0 sample-size coverage.
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
                # P1-04: If facts are VOLATILE with valid timestamps, newest timestamp wins
                volatile_candidates = [c for c in candidates_at_top if c.volatility == FactVolatility.VOLATILE and c.timestamp > 0]
                if len(volatile_candidates) == len(candidates_at_top):
                    candidates_at_top.sort(key=lambda c: (c.timestamp, c.confidence), reverse=True)
                    winner = candidates_at_top[0]
                    top_ts = winner.timestamp
                    tied = [c for c in candidates_at_top if c.timestamp == top_ts and str(c.value).strip().lower() != str(winner.value).strip().lower()]
                    if not tied:
                        candidates_at_top = [winner]
                        distinct_values = {str(winner.value).strip().lower(): winner}
                else:
                    # Compare confidence if one has strictly higher confidence
                    candidates_at_top.sort(key=lambda c: c.confidence, reverse=True)
                    if len(candidates_at_top) > 1 and candidates_at_top[0].confidence > candidates_at_top[1].confidence:
                        winner = candidates_at_top[0]
                        candidates_at_top = [winner]
                        distinct_values = {str(winner.value).strip().lower(): winner}

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

        # Execution depth intent from current prompt (T06, T07 / R01).
        # A keyword mention is only a decision when the intent classification
        # says the current user affirmatively selected a tier.
        depth_intent = classify_execution_depth_intent(
            cleaned,
            source="current_user",
            scope="current_run",
        )
        if depth_intent.intent.is_confirmable and depth_intent.value:
            facts.append(
                ContextFact(
                    dimension_id="EXECUTION_DEPTH",
                    field_name="execution_depth",
                    value=depth_intent.value,
                    source_layer="current_user",
                    source_ref="current_user_message",
                    fact_type=FactType.TASK_DECISION,
                    notes=f"intent={depth_intent.intent.value};{depth_intent.reason}",
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
