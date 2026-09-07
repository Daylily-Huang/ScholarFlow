# -*- coding: utf-8 -*-
"""
test_semantic_audit_closure_v0641.py
--------------------------------------
ScholarFlow v0.6.4.1 Semantic & Audit Closure Regression Test Suite.
Covers Tests 1 through 17 from Section 31 of the Closure Manual:
1. Long sentence != meaning resolved
2. Context exhausted implies insufficient
3. Evidence span survives CCR to EvidenceRecord
4. Structured spans keep location metadata for coherence audit
5. Auditor reject revokes promotion
6. Extraction envelope truthfully reflects audit results
7. Dynamic ISO 8601 timestamp in extraction envelope
8. ExtractionResult version contract enforces const 1.1
9. Support type EXPLICIT does not inflate evidence strength
10. No fabricated optimistic appraisal defaults
11. No fabricated method from section or placeholder
12. Target proposition mismatch maps to NEUTRAL
13. Missing evidence index fails canonical consensus eligibility
14. PARTIALLY_SUFFICIENT context ineligible for full-strength consensus
15. Single canonical claim matrix schema in schemas/
16. Unknown independence cannot achieve Level 1 strong consensus
17. School missing provenance defaults to ANALYTICAL GROUPING

Pure Python standard library (zero external runtime dependencies).
"""

import json
import os
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import tests.helpers as helpers
from tests.schema_helpers import validate_payload, JSONSCHEMA_AVAILABLE

from shared.version import EXTRACTION_RESULT_SCHEMA_VERSION

from context_expansion import (
    CandidateType,
    TINTaskType,
    ExpansionLevel,
    StopCondition,
    SemanticRole,
    AlignmentStatus,
    ContextSufficiency,
    expand_candidate_context,
    build_candidate_context_record,
    promote_candidate_to_evidence,
    audit_context_sufficiency,
    verify_context_coherence,
)
from extraction_pipeline import (
    process_candidate,
    build_extraction_result_envelope,
)
from evidence_to_claim import (
    map_evidence_to_claim,
    evaluate_consensus_eligibility,
    check_target_proposition_compatibility,
)
from controversy_analyzer import (
    compute_topic_consensus,
    analyze_controversy,
)
from school_clustering import (
    cluster_by_paradigm,
)


class TestSemanticAuditClosureV0641(unittest.TestCase):
    """v0.6.4.1 Semantic and Audit Closure Regression Suite."""

    # ------------------------------------------------------------------
    # Test 1 — Long Sentence != Meaning Resolved
    # ------------------------------------------------------------------
    def test_01_long_sentence_not_meaning_resolved(self):
        doc_text = (
            "In recent investigations across several experimental plots, various environmental parameters "
            "were systematically evaluated under standardized laboratory conditions to ensure maximum consistency "
            "and reproducibility across all observation intervals without introducing confounding factors."
        )
        tin = {
            "tin_id": "TIN-T1",
            "task_type": "COMPARISON",
            "target_entity": "compound z",
            "expected_field": "degradation_rate",
        }
        cand = {
            "type": CandidateType.TEXT_SENTENCE,
            "hit_text": "conditions",
            "offset": doc_text.find("conditions"),
        }
        res = expand_candidate_context(doc_text, cand, tin=tin)
        self.assertNotEqual(res["stop_condition"], StopCondition.STOP_A_MEANING_RESOLVED)
        self.assertEqual(res["stop_condition"], StopCondition.STOP_C_CONTEXT_EXHAUSTED)
        self.assertEqual(res["context_sufficiency"], ContextSufficiency.INSUFFICIENT)

    # ------------------------------------------------------------------
    # Test 2 — Context Exhausted
    # ------------------------------------------------------------------
    def test_02_context_exhausted_implies_insufficient(self):
        doc_text = "The sample was tested. However, nothing occurred in control."
        tin = {
            "tin_id": "TIN-T2",
            "task_type": "COMPARISON",
            "target_entity": "nitrogen treatment",
            "expected_field": "respiration",
        }
        cand = {
            "type": CandidateType.TEXT_SENTENCE,
            "hit_text": "sample",
            "offset": 4,
        }
        res = expand_candidate_context(doc_text, cand, tin=tin)
        self.assertEqual(res["stop_condition"], StopCondition.STOP_C_CONTEXT_EXHAUSTED)
        self.assertEqual(res["context_sufficiency"], ContextSufficiency.INSUFFICIENT)

        ccr = build_candidate_context_record(
            candidate_id="CAND-EXH",
            tin_id="TIN-T2",
            candidate_type=CandidateType.TEXT_SENTENCE,
            hit_text="sample",
            expanded_ctx=res,
            semantic_role=SemanticRole.CURRENT_STUDY_RESULT,
            alignment={"status": AlignmentStatus.NOT_ALIGNED},
        )
        ev_rec, err = promote_candidate_to_evidence(ccr, "REC-1", "respiration", "N/A")
        self.assertIsNone(ev_rec)
        self.assertIn("Promotion blocked", err)

    # ------------------------------------------------------------------
    # Test 3 — Evidence Span Survives CCR
    # ------------------------------------------------------------------
    def test_03_evidence_span_survives_ccr_to_evidence(self):
        doc_text = (
            "Section 1. Results\n"
            "Compound Alpha treatment significantly decreased bacterial density by 45% compared to control (p < 0.01). "
            "This confirms the initial laboratory hypothesis."
        )
        hit = "density by 45%"
        cand = {
            "candidate_id": "CAND-03",
            "type": CandidateType.TEXT_SENTENCE,
            "hit_text": hit,
            "offset": doc_text.find(hit),
            "page": 2,
            "section": "Results",
        }
        tin = {
            "tin_id": "TIN-03",
            "task_type": "COMPARISON",
            "target_entity": "compound alpha",
            "expected_field": "bacterial density",
            "comparator": "control",
            "predicate": "decreased",
            "direction": "DECREASE",
        }
        ctx = expand_candidate_context(doc_text, cand, tin=tin)
        self.assertIn("evidence_span", ctx)
        ev_span_text = ctx["evidence_span"]["text"]

        ccr = build_candidate_context_record(
            candidate_id="CAND-03",
            tin_id="TIN-03",
            candidate_type=CandidateType.TEXT_SENTENCE,
            hit_text=hit,
            expanded_ctx=ctx,
            semantic_role=SemanticRole.CURRENT_STUDY_RESULT,
            alignment={"status": AlignmentStatus.ALIGNED, "rationale": "Direct decrease observed"},
            page=2,
            section="Results",
            requires_claim_alignment=False,
        )
        self.assertIn("evidence_span", ccr["context_expansion"])
        self.assertEqual(ccr["context_expansion"]["evidence_span"]["text"], ev_span_text)

        ev, err = promote_candidate_to_evidence(ccr, "REC-03", "bacterial_density", "-45%")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["verbatim_quote"], ev_span_text)

    # ------------------------------------------------------------------
    # Test 4 — Structured Spans Keep Location
    # ------------------------------------------------------------------
    def test_04_structured_spans_location_awareness(self):
        distant_spans = [
            {"text": "Early measurements on Page 2 showed modest growth.", "page": 2, "offset": 100, "section": "Results"},
            {"text": "Late measurements on Page 12 showed total collapse.", "page": 12, "offset": 50000, "section": "Results"},
        ]
        coherent, err = verify_context_coherence(distant_spans)
        self.assertFalse(coherent)
        self.assertIn("cross-page", err.lower())

        ev_record = {
            "schema_version": "1.0",
            "evidence_id": "EV-04",
            "record_id": "REC-04",
            "field": "test_field",
            "extracted_value": "10",
            "support_type": "EXPLICIT",
            "claim_status": "SUPPORTED",
            "verbatim_quote": "A valid full sentence quote describing observed metric.",
            "source_type": "Text",
            "semantic_role": SemanticRole.CURRENT_STUDY_RESULT,
        }
        ccr_unprovenanced = {
            "context_expansion": {
                "spans": ["First span without location.", "Second distant span."],
                "structured_spans": [],
            }
        }
        audit = audit_context_sufficiency(ev_record, ccr_unprovenanced, "dummy doc text")
        self.assertFalse(audit["passed"])
        self.assertTrue(any("provenance is unavailable" in f for f in audit["failures"]))

    # ------------------------------------------------------------------
    # Test 5 — Auditor Reject Revokes Promotion
    # ------------------------------------------------------------------
    def test_05_auditor_reject_revokes_promotion(self):
        doc_text = "Results: We observed enzyme activity."
        tin = {
            "tin_id": "TIN-05",
            "task_type": "ATTRIBUTE",
            "target_entity": "enzyme",
            "target_field": "enzyme activity",
            "expected_value_type": "TEXT",
        }
        cand = {
            "id": "CAND-05",
            "type": CandidateType.TEXT_SENTENCE,
            "text": "enzyme",
            "offset": doc_text.find("enzyme"),
            "section": "Results",
        }
        res = process_candidate(
            tin=tin,
            candidate=cand,
            doc_text=doc_text,
            record_id="REC-05",
            field="enzyme_activity",
            extracted_value="observed",
        )
        if not res["audit_result"] or not res["audit_result"].get("passed"):
            self.assertFalse(res["promoted"])
            self.assertIsNone(res["evidence_record"])

    # ------------------------------------------------------------------
    # Test 6 — Extraction Envelope Audit Truth
    # ------------------------------------------------------------------
    def test_06_extraction_envelope_audit_truth(self):
        failed_audit = {
            "dimension": 16,
            "passed": False,
            "failures": ["Long-distance cross-page stitching detected"],
        }
        envelope = build_extraction_result_envelope(
            paper_metadata={"title": "Paper 6", "authors": ["Author"], "year": 2023},
            evidence_records=[],
            audit_results=[failed_audit],
        )
        self.assertEqual(envelope["auditor_verdict"]["verdict"], "REJECT")
        self.assertFalse(envelope["auditor_verdict"]["checklist_passed"])

    # ------------------------------------------------------------------
    # Test 7 — Dynamic Timestamp
    # ------------------------------------------------------------------
    def test_07_dynamic_iso_timestamp(self):
        envelope = build_extraction_result_envelope(
            paper_metadata={"title": "Paper 7", "authors": ["Author"], "year": 2024},
            evidence_records=[],
        )
        ts = envelope["extraction_metadata"]["timestamp"]
        self.assertNotEqual(ts, "2026-09-07T00:00:00Z")
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        self.assertIsInstance(parsed, datetime)

    # ------------------------------------------------------------------
    # Test 8 — ExtractionResult Version Contract
    # ------------------------------------------------------------------
    def test_08_extraction_result_version_contract(self):
        payload_10 = {
            "schema_version": "1.0",
            "paper_metadata": {"title": "P", "authors": ["A"], "year": 2020},
            "extraction_metadata": {"mode": "quick", "timestamp": "2026-09-07T12:00:00Z"},
            "evidence_records": [],
            "auditor_verdict": {"verdict": "PASS", "checklist_passed": True},
        }
        payload_11 = dict(payload_10, schema_version="1.1")

        if JSONSCHEMA_AVAILABLE:
            with self.assertRaises(Exception):
                validate_payload(payload_10, "extraction_result.schema.json")
            validate_payload(payload_11, "extraction_result.schema.json")

    # ------------------------------------------------------------------
    # Test 9 — Explicit != Direct Empirical
    # ------------------------------------------------------------------
    def test_09_explicit_support_does_not_inflate_strength(self):
        ev = {
            "evidence_id": "EV-09",
            "record_id": "REC-09",
            "support_type": "EXPLICIT",
            "semantic_role": "DISCUSSION_INTERPRETATION",
            "evidence_strength": None,
            "claim_status": "SUPPORTED",
            "verbatim_quote": "We speculate that Compound X acts as an inhibitor.",
        }
        claim = map_evidence_to_claim(ev, {"topic": "T", "target_claim": "We speculate that Compound X acts as an inhibitor."})
        self.assertEqual(claim["evidence_strength"], "UNKNOWN")
        eligible, issues = evaluate_consensus_eligibility(claim, {ev["evidence_id"]: ev})
        self.assertFalse(eligible)
        self.assertTrue(any("UNKNOWN" in iss for iss in issues))

    # ------------------------------------------------------------------
    # Test 10 — No Fabricated Appraisal
    # ------------------------------------------------------------------
    def test_10_no_fabricated_appraisal(self):
        ev = {
            "evidence_id": "EV-10",
            "record_id": "REC-10",
            "claim_status": "SUPPORTED",
            "evidence_strength": "DIRECT_EMPIRICAL",
        }
        claim = map_evidence_to_claim(ev, {"topic": "T"})
        for dim, val in claim["appraisal"].items():
            self.assertEqual(val, "UNKNOWN")

    # ------------------------------------------------------------------
    # Test 11 — No Fabricated Method
    # ------------------------------------------------------------------
    def test_11_no_fabricated_method(self):
        ev = {
            "evidence_id": "EV-11",
            "record_id": "REC-11",
            "location": {"section": "Results"},
            "method": None,
        }
        claim = map_evidence_to_claim(ev, {"topic": "T"})
        self.assertIsNone(claim["method"])

    # ------------------------------------------------------------------
    # Test 12 — Different Target Proposition
    # ------------------------------------------------------------------
    def test_12_different_target_proposition_maps_to_neutral(self):
        ev = {
            "evidence_id": "EV-12",
            "record_id": "REC-12",
            "source_target_claim": "Drug A reduces blood pressure",
            "claim_status": "SUPPORTED",
            "evidence_strength": "DIRECT_EMPIRICAL",
        }
        synthesis_target = {
            "topic": "Cardiovascular Mortality",
            "target_claim": "Drug A reduces cardiovascular mortality",
        }
        claim = map_evidence_to_claim(ev, synthesis_target)
        self.assertEqual(claim["stance"], "NEUTRAL")
        self.assertEqual(claim["stance_mapping_status"], "DIFFERENT_PROPOSITION")

    # ------------------------------------------------------------------
    # Test 13 — Missing Evidence Index
    # ------------------------------------------------------------------
    def test_13_missing_evidence_index_fails_consensus_eligibility(self):
        claim = {
            "schema_version": "1.0",
            "claim_id": "CLM-13",
            "topic": "T",
            "paper_id": "P-13",
            "claim": "Claim text",
            "stance": "SUPPORT",
            "evidence_ids": ["EV-13"],
            "evidence_strength": "DIRECT_EMPIRICAL",
        }
        eligible, issues = evaluate_consensus_eligibility(claim, evidence_index=None, mode="AUDITED_CANONICAL")
        self.assertFalse(eligible)
        self.assertTrue(any("evidence index" in iss.lower() for iss in issues))

    # ------------------------------------------------------------------
    # Test 14 — Partial Sufficiency
    # ------------------------------------------------------------------
    def test_14_partial_sufficiency_ineligible_for_full_consensus(self):
        ev = {
            "evidence_id": "EV-14",
            "context_sufficiency": "PARTIALLY_SUFFICIENT",
            "claim_status": "SUPPORTED",
            "support_type": "EXPLICIT",
            "evidence_strength": "DIRECT_EMPIRICAL",
        }
        claim = {
            "schema_version": "1.0",
            "claim_id": "CLM-14",
            "topic": "T",
            "paper_id": "P-14",
            "claim": "Claim text",
            "stance": "SUPPORT",
            "evidence_ids": ["EV-14"],
            "evidence_strength": "DIRECT_EMPIRICAL",
        }
        eligible, issues = evaluate_consensus_eligibility(claim, {"EV-14": ev}, mode="AUDITED_CANONICAL")
        self.assertFalse(eligible)
        self.assertTrue(any("PARTIALLY_SUFFICIENT" in iss for iss in issues))

    # ------------------------------------------------------------------
    # Test 15 — Duplicate Active Schema Prevention
    # ------------------------------------------------------------------
    def test_15_duplicate_active_schema_prevention(self):
        local_schema = Path("skills/literature-synthesis/assets/claim_evidence_matrix_schema.json")
        self.assertFalse(local_schema.exists(), "Duplicate local schema must be deleted")

        canonical_schema = Path("schemas/claim_evidence_matrix.schema.json")
        self.assertTrue(canonical_schema.exists(), "Canonical schema in schemas/ must exist")

    # ------------------------------------------------------------------
    # Test 16 — Unknown Independence
    # ------------------------------------------------------------------
    def test_16_unknown_independence_cannot_reach_level1_consensus(self):
        claims = [
            {
                "claim_id": "CLM-16A",
                "paper_id": "PAPER-1",
                "topic": "Enzyme Kinetics",
                "claim": "Inhibitor decreases Km value",
                "stance": "SUPPORT",
                "evidence_strength": "DIRECT_EMPIRICAL",
                "weight": 1.0,
                "independence_status": "UNKNOWN",
            },
            {
                "claim_id": "CLM-16B",
                "paper_id": "PAPER-2",
                "topic": "Enzyme Kinetics",
                "claim": "Inhibitor decreases Km value",
                "stance": "SUPPORT",
                "evidence_strength": "DIRECT_EMPIRICAL",
                "weight": 1.0,
                "independence_status": "UNKNOWN",
            },
        ]
        res = compute_topic_consensus(claims)
        self.assertNotEqual(res["consensus_classification"], "STRONG_CONSENSUS")
        self.assertNotIn("Level 1", res["consensus_level"])

    # ------------------------------------------------------------------
    # Test 17 — School Missing Provenance
    # ------------------------------------------------------------------
    def test_17_school_missing_provenance_defaults_to_analytical_grouping(self):
        studies = [
            {
                "paper_id": "PAPER-S1",
                "year": 2021,
                "paradigm": "Equilibrium Modeling",
                "is_established_school": True,
            }
        ]
        clustered = cluster_by_paradigm(studies)
        paradigm_data = clustered["Equilibrium Modeling"]
        self.assertNotEqual(paradigm_data["status"], "ESTABLISHED SCHOOL")
        self.assertEqual(paradigm_data["status"], "ANALYTICAL GROUPING")


if __name__ == "__main__":
    unittest.main()
