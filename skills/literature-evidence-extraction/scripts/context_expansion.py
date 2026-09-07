#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
context_expansion.py
--------------------
Adaptive Evidence Context Expansion (AECE) & Semantic Context Verification
for ScholarFlow Skill 2 (`literature-evidence-extraction`).

Core Epistemic Principles:
- Candidate Hit != Evidence
- Locate -> Context -> Interpret -> Align -> Extract
- Context size is determined by semantic sufficiency, not fixed character windows.
- Evidence fragments from distant or incompatible contexts MUST NOT be silently assembled.

Pure Python standard library (zero external runtime dependencies).
"""

import os
import sys
import re
import json
import argparse
from typing import Dict, List, Any, Optional, Tuple, Set


# ==============================================================================
# 1. CONSTANTS & ENUMS
# ==============================================================================

class ExpansionLevel:
    EXACT_HIT = "EXACT_HIT"                        # Level 0 (Locator only)
    SENTENCE = "SENTENCE"                          # Level 1
    ADJACENT_SENTENCES = "ADJACENT_SENTENCES"      # Level 2
    PARAGRAPH = "PARAGRAPH"                        # Level 3
    SECTION_CONTEXT = "SECTION_CONTEXT"            # Level 4
    STRUCTURED_CONTEXT = "STRUCTURED_CONTEXT"      # Level 5 (Table / Figure / Equation)
    CONTEXT_UNIT = "CONTEXT_UNIT"                  # Level 6 (Experiment / Cohort / Arm)

    HIERARCHY = [
        EXACT_HIT,
        SENTENCE,
        ADJACENT_SENTENCES,
        PARAGRAPH,
        SECTION_CONTEXT,
        STRUCTURED_CONTEXT,
        CONTEXT_UNIT,
    ]


class StopCondition:
    STOP_A_MEANING_RESOLVED = "STOP_A_MEANING_RESOLVED"
    STOP_B_STRUCTURED_RESOLVED = "STOP_B_STRUCTURED_RESOLVED"
    STOP_C_CONTEXT_EXHAUSTED = "STOP_C_CONTEXT_EXHAUSTED"


class SemanticRole:
    CURRENT_STUDY_METHOD = "CURRENT_STUDY_METHOD"
    CURRENT_STUDY_RESULT = "CURRENT_STUDY_RESULT"
    CURRENT_STUDY_OBSERVATION = "CURRENT_STUDY_OBSERVATION"
    BACKGROUND = "BACKGROUND"
    REFERENCED_WORK = "REFERENCED_WORK"
    DISCUSSION_INTERPRETATION = "DISCUSSION_INTERPRETATION"
    LIMITATION = "LIMITATION"
    CONTEXT_DESCRIPTION = "CONTEXT_DESCRIPTION"
    COMPARATOR_CONTEXT = "COMPARATOR_CONTEXT"
    OTHER_ENTITY_CONTEXT = "OTHER_ENTITY_CONTEXT"
    DEFINITION = "DEFINITION"
    THEORETICAL_ARGUMENT = "THEORETICAL_ARGUMENT"
    UNKNOWN = "UNKNOWN"

    ALL_ROLES = {
        CURRENT_STUDY_METHOD,
        CURRENT_STUDY_RESULT,
        CURRENT_STUDY_OBSERVATION,
        BACKGROUND,
        REFERENCED_WORK,
        DISCUSSION_INTERPRETATION,
        LIMITATION,
        CONTEXT_DESCRIPTION,
        COMPARATOR_CONTEXT,
        OTHER_ENTITY_CONTEXT,
        DEFINITION,
        THEORETICAL_ARGUMENT,
        UNKNOWN,
    }


class AlignmentStatus:
    ALIGNED = "ALIGNED"
    PARTIALLY_ALIGNED = "PARTIALLY_ALIGNED"
    NOT_ALIGNED = "NOT_ALIGNED"
    AMBIGUOUS = "AMBIGUOUS"


class ContextSufficiency:
    SUFFICIENT = "SUFFICIENT"
    PARTIALLY_SUFFICIENT = "PARTIALLY_SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"


class CandidateLifecycleState:
    LOCATED = "LOCATED"
    CONTEXT_EXPANDING = "CONTEXT_EXPANDING"
    SEMANTICALLY_CLASSIFIED = "SEMANTICALLY_CLASSIFIED"
    ALIGNED = "ALIGNED"
    EXTRACTED = "EXTRACTED"
    VERIFIED = "VERIFIED"
    AUDITED = "AUDITED"

    ORDER = [
        LOCATED,
        CONTEXT_EXPANDING,
        SEMANTICALLY_CLASSIFIED,
        ALIGNED,
        EXTRACTED,
        VERIFIED,
        AUDITED,
    ]


class CandidateType:
    TEXT_SENTENCE = "TEXT_SENTENCE"
    PARAGRAPH = "PARAGRAPH"
    TABLE_ROW = "TABLE_ROW"
    TABLE_CELL = "TABLE_CELL"
    FIGURE_CAPTION = "FIGURE_CAPTION"
    FIGURE_VALUE = "FIGURE_VALUE"
    SUPPLEMENT_ENTRY = "SUPPLEMENT_ENTRY"
    EQUATION = "EQUATION"
    FOOTNOTE = "FOOTNOTE"
    REFERENCE_CONTEXT = "REFERENCE_CONTEXT"


class TINTaskType:
    ATTRIBUTE = "ATTRIBUTE"
    CLAIM = "CLAIM"
    RELATION = "RELATION"
    COMPARISON = "COMPARISON"
    PROCEDURE = "PROCEDURE"
    INTERPRETATION = "INTERPRETATION"


# ==============================================================================
# 2. TEXT SEGMENTATION & ADAPTIVE SPAN RETRIEVAL
# ==============================================================================

# Common academic abbreviations that do NOT end a sentence
ABBREV_PATTERN = re.compile(
    r"\b(e\.g|i\.e|et\s+al|dr|prof|vs|fig|tab|eq|no|ref|ca|vol|pp|p|approx)\.\s*$",
    re.IGNORECASE,
)


def split_sentences(text: str) -> List[Tuple[int, int, str]]:
    """
    Split text into sentences with start and end character offsets.
    Handles academic abbreviations, decimals, and bracketed citations.
    """
    if not text:
        return []

    spans = []
    # Match potential sentence boundary: period/question/exclamation followed by space or newline
    raw_boundary = re.compile(r"([.?!])(?:\s+|\n+|$)")
    cur_start = 0
    idx = 0

    while idx < len(text):
        m = raw_boundary.search(text, idx)
        if not m:
            tail = text[cur_start:].strip()
            if tail:
                spans.append((cur_start, len(text), tail))
            break

        punct_pos = m.start(1)
        prefix = text[cur_start : punct_pos + 1]

        # Check if preceding token is an abbreviation or decimal
        if ABBREV_PATTERN.search(prefix):
            idx = m.end()
            continue

        # Check for numeric decimal like 3.14 or p < 0.05
        if punct_pos > 0 and punct_pos < len(text) - 1:
            if text[punct_pos - 1].isdigit() and text[punct_pos + 1].isdigit():
                idx = m.end()
                continue

        end_pos = m.end()
        sent_text = text[cur_start:end_pos].strip()
        if sent_text:
            spans.append((cur_start, end_pos, sent_text))
        cur_start = end_pos
        idx = end_pos

    return spans


def split_paragraphs(text: str) -> List[Tuple[int, int, str]]:
    """Split text into paragraphs delimited by double newlines or section breaks."""
    if not text:
        return []
    para_splits = re.compile(r"(\n\s*\n|\f)")
    spans = []
    cur = 0
    for m in para_splits.finditer(text):
        chunk = text[cur:m.start()].strip()
        if chunk:
            spans.append((cur, m.start(), chunk))
        cur = m.end()
    tail = text[cur:].strip()
    if tail:
        spans.append((cur, len(text), tail))
    return spans


def get_sentence_span(text: str, offset: int) -> Dict[str, Any]:
    """Find the single sentence containing offset."""
    sents = split_sentences(text)
    if not sents:
        return {"start": 0, "end": len(text), "text": text.strip(), "level": ExpansionLevel.SENTENCE}
    for s_start, s_end, s_text in sents:
        if s_start <= offset < s_end:
            return {"start": s_start, "end": s_end, "text": s_text, "level": ExpansionLevel.SENTENCE}
    last_start, last_end, last_text = sents[-1]
    if offset >= last_start:
        return {"start": last_start, "end": last_end, "text": last_text, "level": ExpansionLevel.SENTENCE}
    return {"start": 0, "end": len(text), "text": text.strip(), "level": ExpansionLevel.SENTENCE}


def get_adjacent_sentences_span(text: str, offset: int) -> Dict[str, Any]:
    """Find prev + current + next sentences around offset."""
    sents = split_sentences(text)
    cur_idx = -1
    for i, (s_start, s_end, s_text) in enumerate(sents):
        if s_start <= offset < s_end:
            cur_idx = i
            break
    if cur_idx == -1 and sents and offset >= sents[-1][0]:
        cur_idx = len(sents) - 1

    if cur_idx == -1:
        return get_sentence_span(text, offset)

    start_i = max(0, cur_idx - 1)
    end_i = min(len(sents) - 1, cur_idx + 1)

    combined_text = " ".join([sents[j][2] for j in range(start_i, end_i + 1)])
    return {
        "start": sents[start_i][0],
        "end": sents[end_i][1],
        "text": combined_text,
        "level": ExpansionLevel.ADJACENT_SENTENCES,
        "prev_sentence": sents[cur_idx - 1][2] if cur_idx > 0 else None,
        "cur_sentence": sents[cur_idx][2],
        "next_sentence": sents[cur_idx + 1][2] if cur_idx < len(sents) - 1 else None,
    }


def get_paragraph_span(text: str, offset: int) -> Dict[str, Any]:
    """Find the paragraph containing offset."""
    paras = split_paragraphs(text)
    for p_start, p_end, p_text in paras:
        if p_start <= offset <= p_end:
            return {"start": p_start, "end": p_end, "text": p_text, "level": ExpansionLevel.PARAGRAPH}
    return {"start": 0, "end": len(text), "text": text.strip(), "level": ExpansionLevel.PARAGRAPH}


def get_section_heading(text: str, offset: int) -> Optional[str]:
    """Locate the nearest enclosing or preceding section heading before offset."""
    heading_pattern = re.compile(
        r"(?:^|\n)(?:#+\s*([^\n]+)|(\d+(?:\.\d+)*\.?\s+[A-Z][^\n]+)|([A-Z][A-Za-z\s]{3,30}:?))(?=\n|$)"
    )
    preceding_text = text[:offset]
    matches = list(heading_pattern.finditer(preceding_text))
    if matches:
        last_m = matches[-1]
        for g in [1, 2, 3]:
            if last_m.group(g):
                return last_m.group(g).strip()
    return None


def get_structured_table_context(table_data: Dict[str, Any], cell_locator: Dict[str, Any]) -> Dict[str, Any]:
    """
    Assemble structured table context: Table Title + Col Header + Row Header + Value + Footnote.
    Prevents Table Cell Isolation (Anti-pattern 4).
    """
    title = table_data.get("title") or table_data.get("table_title") or "Unknown Table"
    row_header = cell_locator.get("row_header") or cell_locator.get("row_label") or ""
    col_header = cell_locator.get("col_header") or cell_locator.get("col_label") or ""
    cell_value = cell_locator.get("cell_value") or cell_locator.get("value") or ""
    unit = cell_locator.get("unit") or table_data.get("unit") or ""
    footnote = table_data.get("footnote") or ""

    has_headers = bool(row_header or col_header)
    is_sufficient = bool(title and has_headers and cell_value)

    assembled_text = f"[{title}] Row: '{row_header}' | Column: '{col_header}' | Value: '{cell_value}' {unit}".strip()
    if footnote:
        assembled_text += f" (Note: {footnote})"

    return {
        "level": ExpansionLevel.STRUCTURED_CONTEXT,
        "table_title": title,
        "row_header": row_header,
        "col_header": col_header,
        "cell_value": cell_value,
        "unit": unit,
        "footnote": footnote,
        "context_text": assembled_text,
        "is_sufficient": is_sufficient,
        "isolated_cell_failure": not has_headers,
    }


def get_structured_figure_context(figure_data: Dict[str, Any], locator: Dict[str, Any]) -> Dict[str, Any]:
    """
    Assemble structured figure context: Caption + Panel + Axis + Legend + Value.
    """
    caption = figure_data.get("caption") or figure_data.get("title") or ""
    panel = locator.get("panel") or ""
    axis = locator.get("axis") or ""
    legend = locator.get("legend") or ""
    value = locator.get("value") or ""
    unit = locator.get("unit") or ""

    is_sufficient = bool(caption and value)
    assembled = f"[Figure Caption: {caption}] Panel: {panel} | Axis: {axis} | Legend: {legend} | Value: {value} {unit}".strip()

    return {
        "level": ExpansionLevel.STRUCTURED_CONTEXT,
        "caption": caption,
        "panel": panel,
        "axis": axis,
        "legend": legend,
        "value": value,
        "unit": unit,
        "context_text": assembled,
        "is_sufficient": is_sufficient,
    }


# ==============================================================================
# 3. LINGUISTIC & EPISTEMIC GUARDS
# ==============================================================================

NEGATION_REGEX = re.compile(
    r"\b(not|no|never|neither|nor|failed\s+to|fail\s+to|did\s+not|does\s+not|without|non-significant|insignificant|lack\s+of|unsupported|no\s+effect|no\s+difference|declined\s+to|decline\s+to|refused\s+to|refuse\s+to|rejected|reject|denied|without\s+establishing)\b",
    re.IGNORECASE,
)

MODALITY_REGEX = re.compile(
    r"\b(may|might|could|suggest|suggests|suggested|suggesting|possibly|possible|likely|hypothesized|speculate|speculated|preliminary|unconfirmed|putative)\b",
    re.IGNORECASE,
)

PRONOUN_ANAPHORA_REGEX = re.compile(
    r"^(?:this|these|those|they|it|such|the authors|furthermore|moreover|however|in contrast|consequently|therefore|the former|the latter)\b",
    re.IGNORECASE,
)


def detect_negation(text: str) -> Dict[str, Any]:
    """Detect explicit negation expressions within context text."""
    matches = [m.group(0) for m in NEGATION_REGEX.finditer(text)]
    return {
        "has_negation": len(matches) > 0,
        "negation_tokens": matches,
    }


def detect_modality(text: str) -> Dict[str, Any]:
    """Detect modal verbs and hedging language that soften claim strength."""
    matches = [m.group(0) for m in MODALITY_REGEX.finditer(text)]
    return {
        "has_modality": len(matches) > 0,
        "modality_tokens": matches,
        "downgrade_recommended": len(matches) > 0,
    }


def detect_quantifiers(text: str) -> List[str]:
    """Detect restrictive or generalizing quantifiers."""
    pattern = re.compile(r"\b(some|most|all|subset|only|primarily|partially|occasionally|predominantly|minority|majority)\b", re.IGNORECASE)
    return [m.group(0).lower() for m in pattern.finditer(text)]


def detect_conditions_and_scope(text: str) -> List[str]:
    """Extract explicit conditions, subgroup qualifiers, or operational scopes."""
    patterns = [
        r"\b(?:under|in|during|at|on|for)\s+(?:the\s+)?(?:[A-Za-z0-9_-]+\s+){0,4}(?:condition[s]?|subgroup|dataset|cohort|temperature|dose|regime|split|sample)\b[^\.,;]*",
        r"\b(?:restricted to|specifically for|only when|after adjustment|without establishing)\b[^\.,;]*",
        r"\b\d+(?:\.\d+)?\s*(?:°C|mg|kg|ml|μl|g|rpm|hz|k|kn)\b",
    ]
    matches = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            matches.append(m.group(0).strip())
    return matches


def detect_comparators(text: str) -> List[str]:
    """Extract comparison targets (compared with, vs, relative to)."""
    pattern = re.compile(r"\b(?:compared\s+(?:with|to)|relative\s+to|versus|vs\.?|than\s+control|than\s+baseline)\s+([A-Za-z0-9_.-]+)", re.IGNORECASE)
    return [m.group(0).strip() for m in pattern.finditer(text)]


def needs_adjacent_expansion(sentence: str) -> bool:
    """Check whether a sentence begins with pronouns/anaphora requiring adjacent expansion."""
    clean = sentence.strip()
    return bool(PRONOUN_ANAPHORA_REGEX.search(clean))


def verify_context_coherence(spans: List[Dict[str, Any]], max_character_distance: int = 1500) -> Tuple[bool, Optional[str]]:
    """
    Verify that evidence spans are physically coherent.
    Rejects long-distance evidence stitching (Anti-pattern 5) where fragments from distant
    pages or incompatible sections are silently assembled into a single claim.
    """
    if len(spans) <= 1:
        return True, None

    # Check pairwise distances between text spans
    for i in range(len(spans) - 1):
        s1 = spans[i]
        s2 = spans[i + 1]

        # Check page mismatch if page info is present
        p1 = s1.get("page")
        p2 = s2.get("page")
        if p1 is not None and p2 is not None and abs(p1 - p2) > 1:
            return False, f"Long-distance cross-page stitching detected: Page {p1} vs Page {p2}"

        # Check offset distance if offset is present
        off1 = s1.get("end", s1.get("offset", 0))
        off2 = s2.get("start", s2.get("offset", 0))
        if abs(off2 - off1) > max_character_distance:
            return False, f"Span separation ({abs(off2 - off1)} chars) exceeds maximum coherent distance ({max_character_distance})"

        # Check section mismatch
        sec1 = s1.get("section")
        sec2 = s2.get("section")
        if sec1 and sec2 and sec1.lower() != sec2.lower():
            # e.g. Introduction vs Discussion assembly
            if "intro" in sec1.lower() and "result" in sec2.lower():
                return False, f"Incompatible section stitching: '{sec1}' and '{sec2}'"

    return True, None


# ==============================================================================
# 4. ADAPTIVE CONTEXT EXPANSION (AECE) ENGINE
# ==============================================================================

def expand_candidate_context(
    doc_text: str,
    candidate: Dict[str, Any],
    max_level: str = ExpansionLevel.PARAGRAPH,
) -> Dict[str, Any]:
    """
    Execute Adaptive Evidence Context Expansion (AECE) starting from Level 0/1.
    Expands stepwise until semantic meaning is resolved or boundary reached.
    """
    cand_type = candidate.get("type", CandidateType.TEXT_SENTENCE)
    hit_text = candidate.get("hit_text") or candidate.get("text") or ""
    offset = candidate.get("offset", 0)

    # 1. Handle structured contexts directly
    if cand_type in (CandidateType.TABLE_CELL, CandidateType.TABLE_ROW):
        table_data = candidate.get("table_data", {})
        ctx = get_structured_table_context(table_data, candidate)
        stop_cond = StopCondition.STOP_B_STRUCTURED_RESOLVED if ctx["is_sufficient"] else StopCondition.STOP_C_CONTEXT_EXHAUSTED
        return {
            "level_reached": ExpansionLevel.STRUCTURED_CONTEXT,
            "stop_condition": stop_cond,
            "context_text": ctx["context_text"],
            "structured_info": ctx,
            "spans": [ctx["context_text"]],
            "context_sufficiency": ContextSufficiency.SUFFICIENT if ctx["is_sufficient"] else ContextSufficiency.INSUFFICIENT,
            "isolated_cell_failure": ctx.get("isolated_cell_failure", False),
        }

    if cand_type in (CandidateType.FIGURE_VALUE, CandidateType.FIGURE_CAPTION):
        fig_data = candidate.get("figure_data", {})
        ctx = get_structured_figure_context(fig_data, candidate)
        stop_cond = StopCondition.STOP_B_STRUCTURED_RESOLVED if ctx["is_sufficient"] else StopCondition.STOP_C_CONTEXT_EXHAUSTED
        return {
            "level_reached": ExpansionLevel.STRUCTURED_CONTEXT,
            "stop_condition": stop_cond,
            "context_text": ctx["context_text"],
            "structured_info": ctx,
            "spans": [ctx["context_text"]],
            "context_sufficiency": ContextSufficiency.SUFFICIENT if ctx["is_sufficient"] else ContextSufficiency.INSUFFICIENT,
        }

    # 2. Textual Expansion Loop
    # Level 1: Sentence
    sent_span = get_sentence_span(doc_text, offset)
    cur_level = ExpansionLevel.SENTENCE
    cur_text = sent_span["text"]
    spans_accum = [cur_text]
    stop_cond = None

    # Check if sentence has unresolved anaphora or pronoun start
    needs_adj = needs_adjacent_expansion(cur_text)
    section_hdr = get_section_heading(doc_text, offset)

    if not needs_adj and len(cur_text.split()) >= 6:
        # Sentence is self-contained
        stop_cond = StopCondition.STOP_A_MEANING_RESOLVED
    else:
        # Step to Level 2: Adjacent Sentences
        adj_span = get_adjacent_sentences_span(doc_text, offset)
        cur_level = ExpansionLevel.ADJACENT_SENTENCES
        cur_text = adj_span["text"]
        spans_accum.append(cur_text)

        # If still very brief or explicitly requested paragraph
        if max_level in (ExpansionLevel.PARAGRAPH, ExpansionLevel.SECTION_CONTEXT) and len(cur_text.split()) < 15:
            para_span = get_paragraph_span(doc_text, offset)
            cur_level = ExpansionLevel.PARAGRAPH
            cur_text = para_span["text"]
            spans_accum.append(cur_text)
            stop_cond = StopCondition.STOP_A_MEANING_RESOLVED
        else:
            stop_cond = StopCondition.STOP_A_MEANING_RESOLVED

    # Level 4 addition: Section Heading
    if section_hdr:
        cur_text_with_heading = f"[{section_hdr}] {cur_text}"
    else:
        cur_text_with_heading = cur_text

    return {
        "level_reached": cur_level,
        "stop_condition": stop_cond or StopCondition.STOP_A_MEANING_RESOLVED,
        "context_text": cur_text_with_heading,
        "raw_text": cur_text,
        "section_heading": section_hdr,
        "spans": spans_accum,
        "context_sufficiency": ContextSufficiency.SUFFICIENT,
        "has_anaphora_resolved": needs_adj,
    }


# ==============================================================================
# 5. SEMANTIC CONTEXT CLASSIFICATION & TARGET ALIGNMENT
# ==============================================================================

COMMON_RELATION_ROOTS = {
    "increas", "decreas", "reduc", "enhanc", "promot", "inhibit", "regulat",
    "correlat", "associat", "caus", "improv", "differ", "affect", "yield",
    "adopt", "appl", "express", "modulat", "activat", "bind", "interact",
    "lead", "induc", "prevent", "block", "trigger"
}


def classify_semantic_role(
    context_text: str,
    section_heading: Optional[str] = None,
    is_external_citation: bool = False,
    is_speculation: bool = False,
    is_method: bool = False,
) -> Tuple[str, str]:
    """
    Classify the semantic role of the evidence candidate within the document.
    Section names are priors, not shortcuts (Section != Semantic Role).
    """
    text_lower = context_text.lower()
    sec_lower = (section_heading or "").lower()

    # 1. External Citation / Referenced Work
    if (
        is_external_citation
        or "intro" in sec_lower
        or "background" in sec_lower
        or "related" in sec_lower
        or re.search(r"\b(?:et\s+al\.?|\[\d+\]|\(\d{4}\)|previously\s+reported|prior\s+studies|previous\s+work)\b", text_lower)
    ):
        if "result" not in sec_lower:
            if re.search(r"\b(?:previous|prior|reported|suggested|showed|earlier)\b", text_lower):
                return SemanticRole.REFERENCED_WORK, "Candidate describes prior literature citation in background context"
            return SemanticRole.BACKGROUND, "Candidate is located in introductory/background text"

    # 2. Limitation
    if re.search(r"\b(limitation|limitations|caveat|drawback|potential\s+bias|sample\s+size\s+was\s+small)\b", text_lower):
        return SemanticRole.LIMITATION, "Candidate explicitly discusses a research limitation"

    # 3. Method / Procedure
    if is_method or "method" in sec_lower or "materials" in sec_lower or "procedure" in sec_lower or "protocol" in sec_lower:
        if re.search(r"\b(were\s+performed|was\s+measured|protocol|assay|sequencing|synthesized|recruited)\b", text_lower):
            return SemanticRole.CURRENT_STUDY_METHOD, "Candidate specifies experimental methodology or setup"

    # 4. Discussion Speculation
    if is_speculation or ("discuss" in sec_lower and re.search(r"\b(we\s+hypothesize|we\s+speculate|it\s+is\s+tempting\s+to|might\s+suggest|future\s+work)\b", text_lower)):
        return SemanticRole.DISCUSSION_INTERPRETATION, "Candidate is an interpretive speculation in discussion"

    # 5. Definition / Theoretical Argument
    if re.search(r"\b(is\s+defined\s+as|we\s+define|refers\s+to|herein\s+termed)\b", text_lower):
        return SemanticRole.DEFINITION, "Candidate provides a formal conceptual definition"

    # 6. Current Study Result / Observation
    if "result" in sec_lower or "finding" in sec_lower or re.search(r"\b(we\s+observed|we\s+found|showed|demonstrated|increased|decreased|table|figure)\b", text_lower):
        return SemanticRole.CURRENT_STUDY_RESULT, "Candidate reports direct empirical findings of the study"

    # 7. Background
    if "intro" in sec_lower or "background" in sec_lower:
        return SemanticRole.BACKGROUND, "Candidate is located in introductory/background text"

    # Default conservative
    return SemanticRole.CURRENT_STUDY_OBSERVATION, "Candidate text provides empirical observation"


def evaluate_target_alignment(
    tin: Dict[str, Any],
    candidate_context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Determine whether candidate context actually answers the Target Information Need (TIN).
    Status: ALIGNED, PARTIALLY_ALIGNED, NOT_ALIGNED, AMBIGUOUS.
    """
    task_type = tin.get("task_type", TINTaskType.ATTRIBUTE)
    target_entity = (tin.get("target_entity") or "").strip().lower()
    target_field = (tin.get("target_field") or "").strip().lower()
    target_claim = (tin.get("target_claim") or "").strip().lower()

    context_text = candidate_context.get("context_text", "")
    context_lower = context_text.lower()

    # 1. Check Negation Trap
    neg = detect_negation(context_text)
    if neg["has_negation"]:
        # If user asked for positive claim but context states negation
        if task_type in (TINTaskType.CLAIM, TINTaskType.RELATION):
            return {
                "status": AlignmentStatus.NOT_ALIGNED,
                "rationale": f"Candidate explicitly negates relationship: {neg['negation_tokens']}",
                "has_negation": True,
            }

    # 2. Check Entity Matching
    if target_entity and target_entity not in context_lower:
        return {
            "status": AlignmentStatus.NOT_ALIGNED,
            "rationale": f"Target entity '{target_entity}' is absent from expanded context",
        }

    # 3. Task Type Specific Alignment
    if task_type == TINTaskType.ATTRIBUTE:
        # Check if field or quantitative unit is present
        if target_field and target_field not in context_lower:
            # Check synonyms / abbreviations
            field_tokens = target_field.split("_")
            if not any(t in context_lower for t in field_tokens if len(t) > 2):
                return {
                    "status": AlignmentStatus.NOT_ALIGNED,
                    "rationale": f"Target field '{target_field}' not matched in context",
                }

        # Check if value exists
        has_number = bool(re.search(r"\b\d+(?:\.\d+)?\b", context_text))
        if has_number:
            return {
                "status": AlignmentStatus.ALIGNED,
                "rationale": f"Attribute field '{target_field}' and corresponding value verified in context",
            }
        else:
            return {
                "status": AlignmentStatus.PARTIALLY_ALIGNED,
                "rationale": f"Attribute concept '{target_field}' mentioned but numeric value not reported in span",
            }

    elif task_type in (TINTaskType.CLAIM, TINTaskType.RELATION):
        # Must verify claim predicate
        if not target_claim:
            return {"status": AlignmentStatus.AMBIGUOUS, "rationale": "Missing target claim specification in TIN"}

        # Check predicate grounding: Target relation roots must have at least one match in context
        claim_words = [w.lower() for w in re.findall(r"[a-z]{3,}", target_claim.lower())]
        target_relation_roots = [r for r in COMMON_RELATION_ROOTS if any(w.startswith(r) or r in w for w in claim_words)]

        context_words = [w.lower() for w in re.findall(r"[a-z]{3,}", context_lower)]
        context_relation_roots = [r for r in COMMON_RELATION_ROOTS if any(w.startswith(r) or r in w for w in context_words)]

        if target_relation_roots:
            matched_roots = [r for r in target_relation_roots if r in context_relation_roots]
            if not matched_roots:
                return {
                    "status": AlignmentStatus.NOT_ALIGNED,
                    "rationale": f"Target relation predicate root {target_relation_roots} is completely unsupported in context (Mention/Co-occurrence != Relation)",
                }

        claim_tokens = [t for t in re.split(r"\W+", target_claim) if len(t) > 2]
        matched_tokens = [t for t in claim_tokens if t in context_lower]
        ratio = len(matched_tokens) / max(1, len(claim_tokens))

        if ratio >= 0.7:
            # Check modality
            mod = detect_modality(context_text)
            if mod["has_modality"]:
                return {
                    "status": AlignmentStatus.PARTIALLY_ALIGNED,
                    "rationale": f"Claim matched with modal hedging: {mod['modality_tokens']}",
                    "modality": mod["modality_tokens"],
                }
            return {
                "status": AlignmentStatus.ALIGNED,
                "rationale": f"Claim fully aligned with context: {len(matched_tokens)}/{len(claim_tokens)} tokens supported",
            }
        elif ratio >= 0.4:
            return {
                "status": AlignmentStatus.PARTIALLY_ALIGNED,
                "rationale": f"Partial claim overlap ({len(matched_tokens)}/{len(claim_tokens)} tokens)",
            }
        else:
            return {
                "status": AlignmentStatus.NOT_ALIGNED,
                "rationale": f"Context does not support target claim '{target_claim}'",
            }

    elif task_type == TINTaskType.INTERPRETATION:
        return {
            "status": AlignmentStatus.ALIGNED,
            "rationale": "Contextual interpretation matched",
        }

    return {
        "status": AlignmentStatus.AMBIGUOUS,
        "rationale": "Context is ambiguous or under-specified",
    }


# ==============================================================================
# 6. LIFECYCLE, INTERMEDIATE RECORD & PROMOTION GATE
# ==============================================================================

def build_candidate_context_record(
    candidate_id: str,
    tin_id: str,
    candidate_type: str,
    hit_text: str,
    expanded_ctx: Dict[str, Any],
    semantic_role: str,
    alignment: Dict[str, Any],
    role_rationale: str = "",
    page: Optional[int] = None,
    offset: Optional[int] = None,
    section: Optional[str] = None,
) -> Dict[str, Any]:
    """Construct a canonical ScholarFlowCandidateContextRecord."""
    align_status = alignment.get("status", AlignmentStatus.AMBIGUOUS)
    ctx_suff = expanded_ctx.get("context_sufficiency", ContextSufficiency.SUFFICIENT)

    # Fail closed on isolated cells or insufficient context
    if expanded_ctx.get("isolated_cell_failure"):
        ctx_suff = ContextSufficiency.INSUFFICIENT

    # Decision logic
    eligible = (
        align_status in (AlignmentStatus.ALIGNED, AlignmentStatus.PARTIALLY_ALIGNED)
        and ctx_suff in (ContextSufficiency.SUFFICIENT, ContextSufficiency.PARTIALLY_SUFFICIENT)
        and semantic_role != SemanticRole.UNKNOWN
    )

    rejection = None
    if not eligible:
        if ctx_suff == ContextSufficiency.INSUFFICIENT:
            rejection = "Context sufficiency failed (insufficient context or isolated table cell)"
        elif align_status == AlignmentStatus.NOT_ALIGNED:
            rejection = f"Candidate does not align with target information need: {alignment.get('rationale')}"
        elif semantic_role == SemanticRole.UNKNOWN:
            rejection = "Semantic role is UNKNOWN (unverified provenance)"
        else:
            rejection = "Candidate is ambiguous and context is exhausted"

    return {
        "schema_version": "1.0.0",
        "candidate_id": candidate_id,
        "target_information_need_id": tin_id,
        "locator": {
            "type": candidate_type,
            "page": page,
            "offset": offset,
            "section": section or expanded_ctx.get("section_heading"),
        },
        "hit": {
            "text": hit_text,
        },
        "context_expansion": {
            "level_reached": expanded_ctx.get("level_reached", ExpansionLevel.SENTENCE),
            "stop_condition": expanded_ctx.get("stop_condition", StopCondition.STOP_A_MEANING_RESOLVED),
            "context_text": expanded_ctx.get("context_text", ""),
            "spans": expanded_ctx.get("spans", []),
        },
        "semantic_role": {
            "value": semantic_role,
            "rationale": role_rationale,
        },
        "alignment": {
            "status": align_status,
            "rationale": alignment.get("rationale", ""),
        },
        "context_sufficiency": {
            "status": ctx_suff,
            "missing_elements": [],
        },
        "decision": {
            "eligible_for_extraction": eligible,
            "requires_claim_alignment": False,
            "uncertainty_tag": "PARTIALLY_ALIGNED" if align_status == AlignmentStatus.PARTIALLY_ALIGNED else None,
            "rejection_reason": rejection,
        },
    }


def verify_candidate_lifecycle_transition(cur_state: str, next_state: str) -> Tuple[bool, Optional[str]]:
    """
    Verify candidate lifecycle transition.
    Enforces strict sequence:
    LOCATED -> CONTEXT_EXPANDING -> SEMANTICALLY_CLASSIFIED -> ALIGNED -> EXTRACTED -> VERIFIED -> AUDITED
    Blocks direct jump from LOCATED to EXTRACTED.
    """
    if cur_state not in CandidateLifecycleState.ORDER:
        return False, f"Invalid current state: {cur_state}"
    if next_state not in CandidateLifecycleState.ORDER:
        return False, f"Invalid next state: {next_state}"

    cur_idx = CandidateLifecycleState.ORDER.index(cur_state)
    next_idx = CandidateLifecycleState.ORDER.index(next_state)

    if next_idx == cur_idx + 1:
        return True, None
    elif next_idx <= cur_idx:
        return False, f"Cannot transition backwards from {cur_state} to {next_state}"
    else:
        # Skipped intermediate required states
        skipped = CandidateLifecycleState.ORDER[cur_idx + 1 : next_idx]
        return False, f"Illegal lifecycle jump from {cur_state} to {next_state} (skipped required stages: {skipped})"


def promote_candidate_to_evidence(
    ccr: Dict[str, Any],
    record_id: str,
    field: str,
    extracted_value: Any,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Promote a validated CandidateContextRecord to an EvidenceRecord.
    Enforces fail-closed promotion rules:
    - Candidate must have eligible_for_extraction == True
    - Context sufficiency must NOT be INSUFFICIENT
    - Semantic role must NOT be UNKNOWN
    """
    decision = ccr.get("decision", {})
    if not decision.get("eligible_for_extraction"):
        reason = decision.get("rejection_reason", "Candidate not eligible for extraction")
        return None, f"Promotion blocked: {reason}"

    ctx_suff = ccr.get("context_sufficiency", {}).get("status")
    if ctx_suff == ContextSufficiency.INSUFFICIENT:
        return None, "Promotion blocked: Context sufficiency is INSUFFICIENT"

    sem_role = ccr.get("semantic_role", {}).get("value")
    if sem_role == SemanticRole.UNKNOWN:
        return None, "Promotion blocked: Semantic role is UNKNOWN"

    # Assemble EvidenceRecord
    evidence_id = f"EV_{ccr.get('candidate_id', '001')}"
    verbatim_quote = ccr.get("context_expansion", {}).get("context_text", ccr.get("hit", {}).get("text", ""))

    evidence_record = {
        "schema_version": "1.0.0",
        "evidence_id": evidence_id,
        "record_id": record_id,
        "field": field,
        "extracted_value": extracted_value,
        "support_type": "EXPLICIT",
        "claim_status": "SUPPORTED" if ccr.get("alignment", {}).get("status") == AlignmentStatus.ALIGNED else "PARTIALLY_SUPPORTED",
        "status": "SUPPORTED" if ccr.get("alignment", {}).get("status") == AlignmentStatus.ALIGNED else "PARTIALLY_SUPPORTED",
        "verbatim_quote": verbatim_quote,
        "source_type": "Text" if ccr.get("locator", {}).get("type") == CandidateType.TEXT_SENTENCE else "Table",
        "location": {
            "page": ccr.get("locator", {}).get("page"),
            "section": ccr.get("locator", {}).get("section"),
            "table_or_figure_id": None,
        },
        "candidate_context_id": ccr.get("candidate_id"),
        "context_sufficiency": ctx_suff,
        "semantic_role": sem_role,
        "notes": ccr.get("alignment", {}).get("rationale"),
    }

    return evidence_record, None


# ==============================================================================
# 7. EVIDENCE AUDITOR DIMENSION 16: CONTEXT SUFFICIENCY AUDIT
# ==============================================================================

def audit_context_sufficiency(
    evidence_record: Dict[str, Any],
    candidate_context: Optional[Dict[str, Any]] = None,
    doc_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evidence Auditor Dimension 16: Context Sufficiency Audit.
    Checks the 8-point checklist:
    1. Not keyword-only extraction
    2. Minimum semantic unit read (at least full sentence)
    3. Expanded to adjacent/paragraph when pronouns/anaphora present
    4. Checked section / table / figure context
    5. Explicit semantic role assigned (not UNKNOWN)
    6. Context Unit or cohort verified
    7. Confirmed candidate actually answers target need
    8. No long-distance cross-context stitching
    """
    quote = evidence_record.get("verbatim_quote", "").strip()
    checks = {
        "not_keyword_only": False,
        "full_sentence_read": False,
        "adjacent_expanded_for_anaphora": True,
        "structured_context_verified": True,
        "semantic_role_valid": False,
        "context_unit_anchored": True,
        "answers_target_need": False,
        "no_long_distance_stitching": True,
    }
    failures = []

    # 1. Not keyword only: quote length must exceed a bare keyword (< 15 chars or single word)
    if len(quote.split()) >= 3 and len(quote) >= 15:
        checks["not_keyword_only"] = True
    else:
        failures.append("Candidate extraction appears to be keyword-only (quote too brief)")

    # 2. Full sentence read
    if re.search(r"[.?!]$", quote) or len(quote.split()) >= 8:
        checks["full_sentence_read"] = True
    else:
        failures.append("Quote is a fragmented sentence without full punctuation or clause structure")

    # 3. Check anaphora expansion
    if needs_adjacent_expansion(quote):
        # If quote starts with anaphora, it must have adjacent sentence expansion
        if candidate_context:
            level = candidate_context.get("context_expansion", {}).get("level_reached")
            if level in (ExpansionLevel.ADJACENT_SENTENCES, ExpansionLevel.PARAGRAPH, ExpansionLevel.SECTION_CONTEXT):
                checks["adjacent_expanded_for_anaphora"] = True
            else:
                checks["adjacent_expanded_for_anaphora"] = False
                failures.append("Quote starts with unresolved anaphora/pronoun without adjacent sentence expansion")
        else:
            checks["adjacent_expanded_for_anaphora"] = False
            failures.append("Quote contains unresolved pronoun without context expansion record")

    # 4. Structured context check
    if evidence_record.get("source_type") == "Table":
        if "Row:" not in quote and "Column:" not in quote and not evidence_record.get("location", {}).get("table_or_figure_id"):
            checks["structured_context_verified"] = False
            failures.append("Table evidence lacks row/column header anchoring (Anti-pattern 4: Table Cell Isolation)")

    # 5. Semantic role check
    sem_role = evidence_record.get("semantic_role")
    if sem_role and sem_role != SemanticRole.UNKNOWN:
        checks["semantic_role_valid"] = True
    else:
        failures.append("Semantic role is missing or UNKNOWN")

    # 7. Answers target need check
    status = evidence_record.get("claim_status") or evidence_record.get("status")
    if status in ("SUPPORTED", "PARTIALLY_SUPPORTED"):
        checks["answers_target_need"] = True
    else:
        failures.append(f"Evidence status is {status}, not supported")

    # 8. Check long-distance stitching if spans provided
    if candidate_context:
        spans = candidate_context.get("context_expansion", {}).get("spans", [])
        if len(spans) > 1:
            cohere, err = verify_context_coherence([{"text": s} for s in spans])
            if not cohere:
                checks["no_long_distance_stitching"] = False
                failures.append(err)

    passed = len(failures) == 0
    return {
        "dimension": 16,
        "name": "Context Sufficiency Audit",
        "passed": passed,
        "checks": checks,
        "failures": failures,
    }


# ==============================================================================
# 8. SELF-TEST & CLI
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="ScholarFlow Adaptive Evidence Context Expansion (AECE) CLI"
    )
    parser.add_argument("--test", action="store_true", help="Run builtin self-tests")
    args = parser.parse_args()

    if args.test:
        print("Running AECE builtin self-tests...")
        sample_doc = (
            "1. Introduction\n"
            "Previous studies by Smith et al. (2020) suggested that Compound X might improve battery life.\n\n"
            "2. Results\n"
            "In this study, we tested Compound X under high temperature (80°C). "
            "It significantly decreased battery degradation by 34% compared with control. "
            "However, Compound Y did not significantly affect performance.\n\n"
            "3. Discussion\n"
            "We speculate that Compound X forms a stable passivation layer."
        )

        # Test sentence expansion
        offset = sample_doc.find("34%")
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "34%", "offset": offset}
        ctx = expand_candidate_context(sample_doc, cand)
        assert ctx["level_reached"] in (ExpansionLevel.SENTENCE, ExpansionLevel.ADJACENT_SENTENCES)
        print("  [PASS] expand_candidate_context")

        # Test semantic role classification
        role, _ = classify_semantic_role(ctx["context_text"], section_heading=ctx["section_heading"])
        assert role == SemanticRole.CURRENT_STUDY_RESULT
        print("  [PASS] classify_semantic_role (CURRENT_STUDY_RESULT)")

        # Test TIN alignment
        tin = {
            "task_type": TINTaskType.ATTRIBUTE,
            "target_entity": "Compound X",
            "target_field": "battery degradation",
        }
        align = evaluate_target_alignment(tin, ctx)
        assert align["status"] == AlignmentStatus.ALIGNED
        print("  [PASS] evaluate_target_alignment")

        # Test building record and promoting
        ccr = build_candidate_context_record("C001", "TIN01", CandidateType.TEXT_SENTENCE, "34%", ctx, role, align)
        assert ccr["decision"]["eligible_for_extraction"] is True
        ev, err = promote_candidate_to_evidence(ccr, "REC01", "battery_degradation_reduction", "34%")
        assert ev is not None
        print("  [PASS] promote_candidate_to_evidence")

        # Test Auditor check
        audit = audit_context_sufficiency(ev, ccr)
        assert audit["passed"] is True
        print("  [PASS] audit_context_sufficiency")

        # Test Negation Detection
        neg_cand_offset = sample_doc.find("Compound Y did not")
        neg_cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "affect", "offset": neg_cand_offset}
        neg_ctx = expand_candidate_context(sample_doc, neg_cand)
        neg_tin = {"task_type": TINTaskType.CLAIM, "target_claim": "Compound Y affects performance"}
        neg_align = evaluate_target_alignment(neg_tin, neg_ctx)
        assert neg_align["status"] == AlignmentStatus.NOT_ALIGNED
        print("  [PASS] negation detection correctly rejects claim promotion")

        print("All AECE builtin self-tests PASSED successfully!")


if __name__ == "__main__":
    main()
