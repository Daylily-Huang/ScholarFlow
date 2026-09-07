# -*- coding: utf-8 -*-
"""
test_cross_skill_roundtrip_contract.py
----------------------------------------
ScholarFlow Cross-Skill Producer Contract Integration Test Suite (P0-11).
Verifies producer-to-canonical-schema-to-consumer roundtrips across:
Skill 1 (Discovery) -> Skill 2 (Extraction) -> Skill 3 (Synthesis).

Tests:
- Test A: CNKI -> parser -> finalizer -> literature_record.schema.json
- Test B: Wanfang/VIP -> literature_record.schema.json
- Test C: Retrieval coverage ledger -> retrieval_coverage_ledger.schema.json
- Test D: AECE -> evidence_record.schema.json
- Test E: Claim path cannot bypass A2 (hard gate blocks promotion)
- Test F: ExtractionResult envelope -> extraction_result.schema.json
- Test G: Evidence -> Claim adapter -> claim_record.schema.json (evidence_ids resolvable)
- Test H: Claim -> Synthesis -> synthesis_record.schema.json
- Test I: Full end-to-end roundtrip (Discovery -> Extraction -> Synthesis)

Pure Python standard library (zero external runtime dependencies).
"""

import json
import os
import unittest
from pathlib import Path
from typing import Any, Dict, List

import tests.helpers as helpers
from tests.schema_helpers import validate_payload, JSONSCHEMA_AVAILABLE

# Skill 1 imports
from ingest_external_records import (
    ingest_file,
    parse_cnki_refworks,
    parse_ris,
    parse_csv_tsv,
    finalize_literature_record,
)
from retrieval_coverage import (
    build_retrieval_ledger_entry,
    reconcile_retrieval_coverage_ledger,
    RetrievalStatus,
    PaginationStatus,
    CoverageStatus,
)

# Skill 2 imports
from extraction_pipeline import (
    process_candidate,
    build_extraction_result_envelope,
)
from context_expansion import (
    build_candidate_context_record,
    promote_candidate_to_evidence,
    AlignmentStatus,
    ContextSufficiency,
    SemanticRole,
    CandidateType,
    TINTaskType,
)
from claim_alignment import verify_claim_alignment, RelationStatus

# Skill 3 imports
from evidence_to_claim import (
    map_evidence_to_claim,
    evaluate_consensus_eligibility,
)
from controversy_analyzer import (
    analyze_controversy,
    to_canonical_synthesis_records,
)

ROUNDTRIP_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "roundtrip"


class TestCrossSkillRoundtripContract(unittest.TestCase):
    """Producer-to-Consumer roundtrip contract verification."""

    def setUp(self):
        if os.getenv("SCHOLARFLOW_STRICT_CONTRACT_CI") == "1":
            self.assertTrue(JSONSCHEMA_AVAILABLE, "Strict contract CI requires jsonschema.")

    # ------------------------------------------------------------------
    # Test A — CNKI RefWorks -> finalize -> literature_record.schema.json
    # ------------------------------------------------------------------
    def test_a_cnki_to_canonical_literature_record(self):
        cnki_path = ROUNDTRIP_FIXTURES / "cnki_sample.txt"
        records = ingest_file(str(cnki_path), source_database="CNKI", ingestion_method="Refworks_Import")
        self.assertGreater(len(records), 0, "Should parse at least one record from CNKI sample")

        for rec in records:
            if JSONSCHEMA_AVAILABLE:
                validate_payload(rec, "literature_record.schema.json")
            self.assertEqual(rec.get("schema_version"), "1.0")
            self.assertTrue(rec.get("record_id", "").startswith("REC-"))
            self.assertIn("CNKI", rec.get("source_databases", []))
            self.assertEqual(rec.get("ingestion_method"), "Refworks_Import")
            self.assertIsNotNone(rec.get("title"))
            self.assertIsInstance(rec.get("authors"), list)
            self.assertIsNotNone(rec.get("year"))

    # ------------------------------------------------------------------
    # Test B — Wanfang RIS / VIP CSV -> literature_record.schema.json
    # ------------------------------------------------------------------
    def test_b_wanfang_and_vip_to_canonical_literature_record(self):
        # Wanfang RIS
        wf_path = ROUNDTRIP_FIXTURES / "wanfang_sample.ris"
        wf_records = ingest_file(str(wf_path), source_database="Wanfang", ingestion_method="RIS_Import")
        self.assertGreater(len(wf_records), 0, "Should parse Wanfang records")
        for rec in wf_records:
            if JSONSCHEMA_AVAILABLE:
                validate_payload(rec, "literature_record.schema.json")
            self.assertEqual(rec.get("schema_version"), "1.0")
            self.assertIn("Wanfang", rec.get("source_databases", []))
            self.assertEqual(rec.get("ingestion_method"), "RIS_Import")

        # VIP CSV
        vip_path = ROUNDTRIP_FIXTURES / "vip_sample.csv"
        vip_records = ingest_file(str(vip_path), source_database="VIP", ingestion_method="Table_Import")
        self.assertGreater(len(vip_records), 0, "Should parse VIP records")
        for rec in vip_records:
            if JSONSCHEMA_AVAILABLE:
                validate_payload(rec, "literature_record.schema.json")
            self.assertEqual(rec.get("schema_version"), "1.0")
            self.assertIn("VIP", rec.get("source_databases", []))
            self.assertEqual(rec.get("ingestion_method"), "Table_Import")

    # ------------------------------------------------------------------
    # Test C — Retrieval Coverage Ledger -> retrieval_coverage_ledger.schema.json
    # ------------------------------------------------------------------
    def test_c_retrieval_coverage_ledger_reconciliation(self):
        planned_sources = [
            {
                "source_id": "WOS",
                "search_mode": "DIRECT_API",
                "planned_queries": [
                    {"query_id": "Q01", "query_text": "enzyme kinetics temperature"},
                ],
            },
            {
                "source_id": "CNKI",
                "search_mode": "DIRECT_API",
                "planned_queries": [
                    {"query_id": "Q01", "query_text": "enzyme kinetics temperature"},
                    {"query_id": "Q02", "query_text": "microbial respiration nitrogen"},
                ],
            },
            {
                "source_id": "Wanfang",
                "search_mode": "DIRECT_API",
                "planned_queries": [
                    {"query_id": "Q01", "query_text": "temperate forest respiration"},
                ],
            },
        ]

        executed_entries = [
            build_retrieval_ledger_entry(
                source_id="WOS",
                query_id="Q01",
                query_text="enzyme kinetics temperature",
                search_mode="DIRECT_API",
                execution_status=RetrievalStatus.SEARCHED_COMPLETE,
                reported_total_hits=50,
                metadata_records_retrieved=50,
                unique_records_after_source_dedup=45,
                pagination_status=PaginationStatus.COMPLETE,
                notes="All pages retrieved",
            ),
            build_retrieval_ledger_entry(
                source_id="CNKI",
                query_id="Q01",
                query_text="enzyme kinetics temperature",
                search_mode="DIRECT_API",
                execution_status=RetrievalStatus.SEARCHED_COMPLETE,
                reported_total_hits=50,
                metadata_records_retrieved=50,
                unique_records_after_source_dedup=45,
                pagination_status=PaginationStatus.COMPLETE,
                notes="All pages retrieved",
            ),
            build_retrieval_ledger_entry(
                source_id="Wanfang",
                query_id="Q01",
                query_text="temperate forest respiration",
                search_mode="DIRECT_API",
                execution_status=RetrievalStatus.SEARCHED_PARTIAL,
                reported_total_hits=100,
                metadata_records_retrieved=40,
                pagination_status=PaginationStatus.TRUNCATED_BY_LIMIT,
                failure_reason="Rate limit stopped pagination midway",
            ),
        ]

        ledger = reconcile_retrieval_coverage_ledger(planned_sources, executed_entries)

        if JSONSCHEMA_AVAILABLE:
            validate_payload(ledger, "retrieval_coverage_ledger.schema.json")

        self.assertEqual(ledger["ledger_type"], "RETRIEVAL_COVERAGE_LEDGER_A")
        self.assertEqual(ledger["total_planned_sources"], 3)
        self.assertEqual(ledger["complete_sources"], 1)
        self.assertAlmostEqual(ledger["database_coverage_rate"], 1 / 3, places=2)
        self.assertTrue(ledger["has_retrieval_gaps"])
        self.assertIn("sum_query_reported_hits", ledger)
        self.assertIn("sum_query_retrieved_records", ledger)
        self.assertIn("unique_records_after_cross_query_dedup", ledger)

        # Confirm unexecuted CNKI Q02 generated a NOT_SEARCHED gap
        gap_entries = [e for e in ledger["entries"] if e.get("query_id") == "Q02"]
        self.assertEqual(len(gap_entries), 1)
        self.assertEqual(gap_entries[0]["execution_status"], RetrievalStatus.NOT_SEARCHED)

    # ------------------------------------------------------------------
    # Test D — AECE -> EvidenceRecord schema validation
    # ------------------------------------------------------------------
    def test_d_aece_to_canonical_evidence_record(self):
        doc_path = ROUNDTRIP_FIXTURES / "sample_document.txt"
        doc_text = doc_path.read_text(encoding="utf-8")
        tin_path = ROUNDTRIP_FIXTURES / "sample_tin.json"
        tin = json.loads(tin_path.read_text(encoding="utf-8"))

        hit_text = "Under experimental conditions, nitrogen addition significantly increased microbial respiration by 28.5% compared to the control group (p < 0.01)."
        candidate = {
            "id": "CAND-RT-01",
            "type": CandidateType.TEXT_SENTENCE,
            "text": hit_text,
            "page": 3,
            "offset": doc_text.find(hit_text),
            "section": "Results",
        }

        res = process_candidate(
            tin=tin,
            candidate=candidate,
            doc_text=doc_text,
            record_id="REC-TEST-001",
            field="microbial_respiration",
            extracted_value="+28.5%",
        )

        self.assertTrue(res["promoted"], f"Promotion failed: {res.get('error')}")
        ev_rec = res["evidence_record"]
        self.assertIsNotNone(ev_rec)

        if JSONSCHEMA_AVAILABLE:
            validate_payload(ev_rec, "evidence_record.schema.json")

        self.assertEqual(ev_rec["schema_version"], "1.0")
        self.assertEqual(ev_rec["claim_status"], "SUPPORTED")
        self.assertEqual(ev_rec["source_type"], "Text")
        self.assertEqual(ev_rec["context_sufficiency"], "SUFFICIENT")
        self.assertEqual(ev_rec["location"]["section"], "Results")
        self.assertEqual(ev_rec["location"]["page"], 3)

        ccr = res["candidate_context_record"]
        self.assertIn("spans", ccr["context_expansion"])
        self.assertGreater(len(ccr["context_expansion"]["spans"]), 0)

    # ------------------------------------------------------------------
    # Test E — Claim path cannot bypass A2 (hard gate blocks promotion)
    # ------------------------------------------------------------------
    def test_e_claim_path_cannot_bypass_a2_hard_gate(self):
        doc_path = ROUNDTRIP_FIXTURES / "sample_document.txt"
        doc_text = doc_path.read_text(encoding="utf-8")

        # Case 1: Target asserts increase, but text says did NOT increase
        tin_contradict = {
            "tin_id": "TIN-CONTRA-01",
            "task_type": "COMPARISON",
            "target_entity": "carbon dioxide",
            "expected_field": "fungal biomass",
            "comparator": "control",
            "predicate": "increased",
            "direction": "INCREASE",
            "expected_value_type": "NUMERIC",
            "context_keywords": ["carbon dioxide", "fungal biomass"],
            "allow_contradiction": False,  # Strict: do not allow contradictions as positive evidence
        }

        contra_text = "However, elevated carbon dioxide did not increase fungal biomass in the topsoil layer."
        candidate_contra = {
            "id": "CAND-CONTRA-01",
            "type": CandidateType.TEXT_SENTENCE,
            "text": contra_text,
            "page": 3,
            "offset": doc_text.find(contra_text),
            "section": "Results",
        }

        res_contra = process_candidate(
            tin=tin_contradict,
            candidate=candidate_contra,
            doc_text=doc_text,
            record_id="REC-TEST-002",
            field="fungal_biomass",
            extracted_value="no increase",
        )

        self.assertFalse(
            res_contra["promoted"],
            "Candidate contradicting target without allow_contradiction=True must be rejected by promotion gate",
        )

        # Case 2: Candidate context record manually missing claim_alignment when required
        ccr_missing_alignment = {
            "candidate_id": "CAND-TEST-MISSING",
            "tin_id": "TIN-TEST",
            "locator": {"type": "TEXT_SENTENCE"},
            "hit": {"text": "elevated temperature enhanced enzyme activity"},
            "context_expansion": {
                "context_text": "Furthermore, temperature elevation enhanced enzyme activity across all sampled plots.",
            },
            "decision": {
                "expansion_level": "LEVEL_1_SENTENCE",
                "stop_condition": "STOP_A_MEANING_RESOLVED",
                "semantic_role": "CURRENT_STUDY_RESULT",
                "context_sufficiency": "SUFFICIENT",
                "alignment_status": "ALIGNED",
                "requires_claim_alignment": True,  # Required!
                "eligible_for_extraction": True,
            },
            # "claim_alignment" is deliberately missing!
        }

        ev_missing, err_missing = promote_candidate_to_evidence(
            ccr=ccr_missing_alignment,
            record_id="REC-TEST-003",
            field="enzyme_activity",
            extracted_value="enhanced",
        )
        self.assertIsNone(ev_missing, "Promotion must fail when requires_claim_alignment=True but claim_alignment is missing")
        self.assertIn("A2", err_missing)

    # ------------------------------------------------------------------
    # Test F — ExtractionResult envelope -> extraction_result.schema.json
    # ------------------------------------------------------------------
    def test_f_extraction_result_envelope_schema(self):
        doc_path = ROUNDTRIP_FIXTURES / "sample_document.txt"
        doc_text = doc_path.read_text(encoding="utf-8")
        tin_path = ROUNDTRIP_FIXTURES / "sample_tin.json"
        tin = json.loads(tin_path.read_text(encoding="utf-8"))

        hit_text = "Under experimental conditions, nitrogen addition significantly increased microbial respiration by 28.5% compared to the control group (p < 0.01)."
        candidate = {
            "id": "CAND-RT-01",
            "type": CandidateType.TEXT_SENTENCE,
            "text": hit_text,
            "page": 3,
            "offset": doc_text.find(hit_text),
            "section": "Results",
        }

        res = process_candidate(
            tin=tin,
            candidate=candidate,
            doc_text=doc_text,
            record_id="REC-TEST-001",
            field="microbial_respiration",
            extracted_value="+28.5%",
        )
        self.assertTrue(res["promoted"])

        envelope = build_extraction_result_envelope(
            paper_metadata={
                "title": "Environmental Drivers of Microbial Respiration in Forest Soils",
                "authors": ["Wang Qiang", "Zhao Lei"],
                "year": 2022,
                "doi": "10.13287/j.1001-9332.2022.045",
            },
            evidence_records=[res["evidence_record"]],
            mode="deep_evidence_extraction",
        )

        if JSONSCHEMA_AVAILABLE:
            validate_payload(envelope, "extraction_result.schema.json")

        self.assertEqual(envelope["schema_version"], "1.1")
        self.assertEqual(len(envelope["evidence_records"]), 1)
        self.assertEqual(envelope["auditor_verdict"]["verdict"], "PASS")

    # ------------------------------------------------------------------
    # Test G — Evidence -> Claim adapter -> claim_record.schema.json
    # ------------------------------------------------------------------
    def test_g_evidence_to_claim_adapter_and_eligibility(self):
        doc_path = ROUNDTRIP_FIXTURES / "sample_document.txt"
        doc_text = doc_path.read_text(encoding="utf-8")
        tin_path = ROUNDTRIP_FIXTURES / "sample_tin.json"
        tin = json.loads(tin_path.read_text(encoding="utf-8"))

        hit_text = "Under experimental conditions, nitrogen addition significantly increased microbial respiration by 28.5% compared to the control group (p < 0.01)."
        candidate = {
            "id": "CAND-RT-01",
            "type": CandidateType.TEXT_SENTENCE,
            "text": hit_text,
            "page": 3,
            "offset": doc_text.find(hit_text),
            "section": "Results",
        }

        res = process_candidate(
            tin=tin,
            candidate=candidate,
            doc_text=doc_text,
            record_id="REC-TEST-001",
            field="microbial_respiration",
            extracted_value="+28.5%",
        )
        ev_rec = res["evidence_record"]

        synthesis_target = {
            "topic": "Microbial Respiration",
            "target_claim": "Nitrogen addition stimulates soil microbial respiration",
            "year": 2022,
        }

        claim = map_evidence_to_claim(ev_rec, synthesis_target)

        if JSONSCHEMA_AVAILABLE:
            validate_payload(claim, "claim_record.schema.json")

        self.assertEqual(claim["schema_version"], "1.0")
        self.assertEqual(claim["stance"], "SUPPORT")
        self.assertIn("evidence_ids", claim)
        self.assertEqual(claim["evidence_ids"], [ev_rec["evidence_id"]])

        # Verify all evidence_ids resolve in index
        ev_index = {ev_rec["evidence_id"]: ev_rec}
        eligible, issues = evaluate_consensus_eligibility(claim, ev_index)
        self.assertTrue(eligible, f"Eligible claim rejected: {issues}")
        self.assertEqual(len(issues), 0)

        # Test quality rejection when upstream context is INSUFFICIENT
        bad_ev = dict(ev_rec, context_sufficiency="INSUFFICIENT")
        bad_claim = map_evidence_to_claim(bad_ev, synthesis_target)
        bad_eligible, bad_issues = evaluate_consensus_eligibility(bad_claim, {bad_ev["evidence_id"]: bad_ev})
        self.assertFalse(bad_eligible)
        self.assertTrue(any("INSUFFICIENT" in iss for iss in bad_issues))

    # ------------------------------------------------------------------
    # Test H — Claim -> Synthesis -> synthesis_record.schema.json
    # ------------------------------------------------------------------
    def test_h_claim_to_canonical_synthesis_record(self):
        claims = [
            {
                "claim_id": "CLM-001",
                "paper_id": "PAPER-A",
                "topic": "Microbial Respiration",
                "claim": "Nitrogen addition increases microbial respiration",
                "stance": "SUPPORT",
                "evidence_strength": "DIRECT_EMPIRICAL",
                "year": 2021,
                "independence_group_id": "GROUP-A",
            },
            {
                "claim_id": "CLM-002",
                "paper_id": "PAPER-B",
                "topic": "Microbial Respiration",
                "claim": "Nitrogen addition increases respiration rates in soil",
                "stance": "SUPPORT",
                "evidence_strength": "DIRECT_EMPIRICAL",
                "year": 2022,
                "independence_group_id": "GROUP-B",
            },
            {
                "claim_id": "CLM-003",
                "paper_id": "PAPER-C",
                "topic": "Microbial Respiration",
                "claim": "Nitrogen addition has no significant effect under drought",
                "stance": "REFUTE",
                "evidence_strength": "DIRECT_EMPIRICAL",
                "year": 2023,
                "independence_group_id": "GROUP-C",
            },
        ]

        analysis_results = analyze_controversy(claims)
        synthesis_records = to_canonical_synthesis_records(analysis_results)

        self.assertGreater(len(synthesis_records), 0)
        for srec in synthesis_records:
            if JSONSCHEMA_AVAILABLE:
                validate_payload(srec, "synthesis_record.schema.json")
            self.assertEqual(srec["schema_version"], "1.0")
            self.assertEqual(srec["topic"], "Microbial Respiration")
            self.assertIn("consensus_classification", srec)
            self.assertIn("heuristic_balance_score", srec)
            self.assertIn("controversy_diagnosis", srec)

    # ------------------------------------------------------------------
    # Test I — Full End-to-End Roundtrip (Discovery -> Extraction -> Synthesis)
    # ------------------------------------------------------------------
    def test_i_full_end_to_end_cross_skill_roundtrip(self):
        # Stage 1: Discovery External Ingestion
        wf_path = ROUNDTRIP_FIXTURES / "wanfang_sample.ris"
        lit_records = ingest_file(str(wf_path), source_database="Wanfang", ingestion_method="RIS_Import")
        self.assertGreater(len(lit_records), 0)
        primary_lit = lit_records[0]

        if JSONSCHEMA_AVAILABLE:
            validate_payload(primary_lit, "literature_record.schema.json")

        # Stage 2: Extraction Pipeline
        doc_path = ROUNDTRIP_FIXTURES / "sample_document.txt"
        doc_text = doc_path.read_text(encoding="utf-8")
        tin_path = ROUNDTRIP_FIXTURES / "sample_tin.json"
        tin = json.loads(tin_path.read_text(encoding="utf-8"))

        hit_text = "Under experimental conditions, nitrogen addition significantly increased microbial respiration by 28.5% compared to the control group (p < 0.01)."
        candidate = {
            "id": f"CAND-{primary_lit['record_id']}",
            "type": CandidateType.TEXT_SENTENCE,
            "text": hit_text,
            "page": 3,
            "offset": doc_text.find(hit_text),
            "section": "Results",
        }

        ext_result = process_candidate(
            tin=tin,
            candidate=candidate,
            doc_text=doc_text,
            record_id=primary_lit["record_id"],
            field="microbial_respiration",
            extracted_value="+28.5%",
        )
        self.assertTrue(ext_result["promoted"])
        ev_record = ext_result["evidence_record"]

        if JSONSCHEMA_AVAILABLE:
            validate_payload(ev_record, "evidence_record.schema.json")

        # Stage 2 Envelope
        extraction_envelope = build_extraction_result_envelope(
            paper_metadata={
                "title": primary_lit["title"],
                "authors": primary_lit["authors"],
                "year": primary_lit["year"],
                "doi": primary_lit.get("doi"),
            },
            evidence_records=[ev_record],
        )
        if JSONSCHEMA_AVAILABLE:
            validate_payload(extraction_envelope, "extraction_result.schema.json")

        # Stage 3: Evidence-to-Claim Mapping
        synthesis_target = {
            "topic": "Microbial Respiration Under Nitrogen",
            "target_claim": "Nitrogen addition increases microbial respiration",
            "year": primary_lit["year"],
        }
        claim_record = map_evidence_to_claim(ev_record, synthesis_target)

        if JSONSCHEMA_AVAILABLE:
            validate_payload(claim_record, "claim_record.schema.json")

        # Stage 3 Canonical Matrix Envelope
        matrix_envelope = {
            "schema_version": "1.0",
            "matrix_id": "CEM-E2E-001",
            "topic": synthesis_target["topic"],
            "claims": [claim_record],
            "evidence_records": [ev_record],
        }
        if JSONSCHEMA_AVAILABLE:
            validate_payload(matrix_envelope, "claim_evidence_matrix.schema.json")

        # Stage 3 Synthesis Analysis
        analysis_map = analyze_controversy([claim_record])
        synth_records = to_canonical_synthesis_records(analysis_map)
        self.assertEqual(len(synth_records), 1)
        final_synth = synth_records[0]

        if JSONSCHEMA_AVAILABLE:
            validate_payload(final_synth, "synthesis_record.schema.json")

        # Verify end-to-end provenance lineage
        self.assertEqual(final_synth["topic"], synthesis_target["topic"])
        self.assertEqual(claim_record["evidence_ids"], [ev_record["evidence_id"]])
        self.assertEqual(ev_record["record_id"], primary_lit["record_id"])


if __name__ == "__main__":
    unittest.main()
