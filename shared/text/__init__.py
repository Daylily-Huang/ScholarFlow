# -*- coding: utf-8 -*-
"""ScholarFlow shared text-analysis lexicons.

公开接口由 :mod:`shared.text.polarity` 提供（导出清单见其模块 docstring）：
否定/反义/反转词表与三值极性判定（H-01/H-02/H-82，2026-09-13 B2 批次）。
消费方（claim_alignment、debate_handoff 等）统一从这里 import，禁止各自复制词表。
"""

from shared.text.polarity import (  # noqa: F401
    AECE_NEGATION_MARKERS,
    AECE_NEGATION_RE,
    ANTONYM_LOOKUP,
    ANTONYM_PAIRS,
    CLAUSE_SPLIT_RE,
    CONTRASTIVE_MARKERS,
    DOUBLE_NEGATION_RES,
    NEGATION_MARKERS,
    NEGATION_TOKEN_RE,
    REVERSAL_MARKERS,
    REVERSAL_RE,
    check_polarity,
    clause_polarity,
    find_negations,
    is_negated,
    net_negation_count,
    polarity_signature,
    predicate_stem,
    split_clauses,
)

__all__ = [
    "AECE_NEGATION_MARKERS", "AECE_NEGATION_RE", "ANTONYM_LOOKUP", "ANTONYM_PAIRS",
    "CLAUSE_SPLIT_RE", "CONTRASTIVE_MARKERS", "DOUBLE_NEGATION_RES",
    "NEGATION_MARKERS", "NEGATION_TOKEN_RE", "REVERSAL_MARKERS", "REVERSAL_RE",
    "check_polarity", "clause_polarity", "find_negations", "is_negated",
    "net_negation_count", "polarity_signature", "predicate_stem", "split_clauses",
]
