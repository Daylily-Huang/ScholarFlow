# -*- coding: utf-8 -*-
"""Tests for claim_linter.py (narrative-review Claim ID traceability gate)."""
import unittest

import helpers  # noqa: F401

import claim_linter as cl  # type: ignore


def _matrix():
    return {
        "matrix_id": "M1",
        "topic": "black muntjac diet",
        "generated_at": "2026-09-06T00:00:00Z",
        "claims": [
            {"claim_id": "CLM-001", "paper_id": "Wang2021", "stance": "SUPPORT",
             "evidence_tier": "E1", "claim_text": "Fecal DNA metabarcoding identifies 32 plant taxa."},
            {"claim_id": "CLM-002", "paper_id": "Zhang2022", "stance": "CONDITIONAL",
             "evidence_tier": "E2", "claim_text": "Density estimates vary with survey effort."},
            {"claim_id": "CLM-003", "paper_id": "Li2023", "stance": "NEUTRAL",
             "evidence_tier": "E4", "claim_text": "Expert opinion on habitat trend."},
        ],
    }


GOOD_NARRATIVE = (
    "# 综述\n\n"
    "黑麂食性研究以粪便显微组织学为主。研究表明，粪便 DNA 宏条形码可鉴定 32 个植物类群 "
    "[CLM-001]，但密度估计对调查强度敏感 [CLM-002]。\n\n"
    "## 讨论框架\n\n"
    "| 主题 | 方法 |\n|---|---|\n| 食性 | 宏条形码 |\n"
)

ORPHAN_NARRATIVE = (
    "黑麂食性研究进展综述。\n\n"
    "有研究报道黑麂食性季节变化显著，冬季木质化程度上升 35%。\n\n"
    "前人指出 [CLM-999] 密度被高估。\n"
)

UNCITED_NARRATIVE = (
    "综述正文。\n\n"
    "研究表明宏条形码优于显微组织学 [CLM-001]。\n"
)


class TestExtractClaimRefs(unittest.TestCase):
    def test_ordered_unique_and_case_insensitive(self):
        refs = cl.extract_claim_refs("a [CLM-001] b (clm-002) c [CLM-001] d [CLM-12]")
        self.assertEqual(refs, ["CLM-001", "CLM-002"])


class TestLintNarrative(unittest.TestCase):
    def test_good_narrative(self):
        rep = cl.lint_narrative(GOOD_NARRATIVE, _matrix())
        self.assertEqual(rep["unresolved_refs"], [])
        self.assertEqual(rep["flagged_paragraphs"], [])
        self.assertEqual(rep["uncited_claims"], ["CLM-003"])
        self.assertFalse(cl.gate_failed(rep))

    def test_unresolved_ref_fails_gate(self):
        rep = cl.lint_narrative(ORPHAN_NARRATIVE, _matrix())
        self.assertEqual(rep["unresolved_refs"], ["CLM-999"])
        self.assertTrue(cl.gate_failed(rep))

    def test_orphan_factual_paragraph_flagged(self):
        rep = cl.lint_narrative(ORPHAN_NARRATIVE, _matrix())
        # first paragraph has a reporting cue ("有研究报道", "35%") but no Claim ID
        self.assertEqual(len(rep["flagged_paragraphs"]), 1)
        self.assertIn("季节变化", rep["flagged_paragraphs"][0])

    def test_prose_skip_headings_and_tables(self):
        rep = cl.lint_narrative(GOOD_NARRATIVE, _matrix())
        # heading/table paragraphs must not be flagged even though the table
        # row contains no Claim ID
        self.assertEqual(rep["flagged_paragraphs"], [])

    def test_strict_fails_on_flagged_paragraph(self):
        rep = cl.lint_narrative(ORPHAN_NARRATIVE, _matrix())
        self.assertTrue(cl.gate_failed(rep, strict=True))

    def test_citation_coverage_stat(self):
        rep = cl.lint_narrative(GOOD_NARRATIVE, _matrix())
        self.assertAlmostEqual(rep["stats"]["citation_coverage"], round(2 / 3, 4))


class TestValidateMatrix(unittest.TestCase):
    def test_valid_matrix_passes(self):
        self.assertEqual(cl.validate_matrix(_matrix()), [])

    def test_missing_required_key(self):
        m = _matrix()
        del m["claims"][0]["stance"]
        issues = cl.validate_matrix(m)
        self.assertTrue(any("stance" in i for i in issues))

    def test_invalid_stance(self):
        m = _matrix()
        m["claims"][1]["stance"] = "MAYBE"
        issues = cl.validate_matrix(m)
        self.assertTrue(any("invalid stance" in i for i in issues))

    def test_duplicate_claim_id(self):
        m = _matrix()
        m["claims"][1]["claim_id"] = "CLM-001"
        issues = cl.validate_matrix(m)
        self.assertTrue(any("duplicate" in i for i in issues))


if __name__ == "__main__":
    unittest.main()
