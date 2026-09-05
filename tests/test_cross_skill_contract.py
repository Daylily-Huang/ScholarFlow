# -*- coding: utf-8 -*-
"""
test_cross_skill_contract.py
----------------------------
Integration & contract tests validating:
1. JSON Schema integrity across all 4 pipeline stages.
2. Decoupling of extraction `support_type` from synthesis `evidence_strength`.
3. Strict 0.0 weighting for NOT_REPORTED claims.
4. Candidate Evidence Locator co-location logic and document parse auditing.
"""

import json
import unittest
from pathlib import Path

try:
    import helpers
except ImportError:
    from tests import helpers
from controversy_analyzer import resolve_evidence_weight, analyze_controversy
from audit_claims import audit_single_claim, compute_relevance_score, load_full_text
from agent_search import parse_openalex_item
from school_clustering import cluster_by_paradigm, detect_paradigm_shifts

REPO_ROOT = helpers.REPO_ROOT
SCHEMAS_DIR = REPO_ROOT / "schemas"


class TestContractSchemas(unittest.TestCase):
    """Test that all formal contract JSON schemas are valid and consistent."""

    def test_all_schemas_exist_and_are_valid_json(self):
        schema_files = [
            "literature_record.schema.json",
            "evidence_record.schema.json",
            "claim_record.schema.json",
            "synthesis_record.schema.json"
        ]
        for name in schema_files:
            p = SCHEMAS_DIR / name
            self.assertTrue(p.is_file(), f"Schema missing: {name}")
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data.get("$schema"), "https://json-schema.org/draft/2020-12/schema")
            self.assertIn("title", data)
            self.assertIn("required", data)
            self.assertIn("schema_version", data["required"])


class TestExtractionSynthesisDecoupling(unittest.TestCase):
    """Verify orthogonal semantics between extraction support_type and synthesis evidence_strength."""

    def test_not_reported_always_yields_zero_weight(self):
        """NOT_REPORTED in extraction must never be counted as valid evidence in synthesis."""
        claim_nr1 = {
            "claim_id": "C01",
            "support_type": "NOT_REPORTED",
            "evidence_strength": "DIRECT_EMPIRICAL"  # Contradictory attempt
        }
        w1, _, _ = resolve_evidence_weight(claim_nr1)
        self.assertEqual(w1, 0.0, "NOT_REPORTED must force weight to 0.0 regardless of evidence_strength.")

        claim_nr2 = {
            "claim_id": "C02",
            "support_type": "NR"
        }
        w2, _, _ = resolve_evidence_weight(claim_nr2)
        self.assertEqual(w2, 0.0, "NR support_type must force weight to 0.0.")

    def test_evidence_strength_mapping(self):
        """Verify proper resolution of evidence_strength tiers."""
        strengths = {
            "DIRECT_EMPIRICAL": 1.0,
            "MODELED_EMPIRICAL": 0.8,
            "AUTHOR_INTERPRETATION": 0.4,
            "SECONDARY_EVIDENCE": 0.2,
            "EXPERT_OPINION": 0.1,
            "UNKNOWN": 0.3
        }
        for s, expected in strengths.items():
            claim = {"claim_id": "C", "evidence_strength": s}
            w, _, _ = resolve_evidence_weight(claim)
            self.assertEqual(w, expected, f"Weight mismatch for {s}")

    def test_legacy_evidence_tier_backward_compatibility(self):
        """Ensure E1-E4 backward compatibility converts correctly."""
        claim_e1 = {"claim_id": "C", "evidence_tier": "E1"}
        w1, _, _ = resolve_evidence_weight(claim_e1)
        self.assertEqual(w1, 1.0)

        claim_e4 = {"claim_id": "C", "evidence_tier": "E4"}
        w4, _, _ = resolve_evidence_weight(claim_e4)
        self.assertEqual(w4, 0.1)

    def test_appraisal_adjustments(self):
        """Test that multi-dimensional appraisal modifies the base weight appropriately."""
        claim_high_bias = {
            "claim_id": "C",
            "evidence_strength": "DIRECT_EMPIRICAL",
            "appraisal": {
                "risk_of_bias": "HIGH",
                "directness": "LOW"
            }
        }
        w, _, factors = resolve_evidence_weight(claim_high_bias)
        self.assertLess(w, 1.0, "High bias and low directness should reduce weight.")
        self.assertIn("bias_high(-0.3)", factors)
        self.assertIn("indirect(-0.2)", factors)


class TestCandidateEvidenceLocator(unittest.TestCase):
    """Test candidate evidence localization and co-location matching in audit_claims.py."""

    def setUp(self):
        self.sample_pages = [
            {
                "page": 1,
                "text": "Ecological survey of wildlife populations. We deployed 24 camera traps in the reserve."
            },
            {
                "page": 2,
                "text": "Genotyping protocol: PCR amplification was conducted in a total volume of 20 uL with 35 cycles."
            }
        ]

    def test_relevance_gatekeeper(self):
        res_high = compute_relevance_score("camera traps survey", self.sample_pages)
        self.assertEqual(res_high["decision"], "PROCEED")
        self.assertGreaterEqual(res_high["score"], 6)

        res_low = compute_relevance_score("deep marine oceanography trench", self.sample_pages)
        self.assertEqual(res_low["decision"], "PRUNE")
        self.assertLess(res_low["score"], 6)

    def test_colocated_keyword_and_number(self):
        res = audit_single_claim("PCR volume was 20 uL", self.sample_pages)
        self.assertEqual(res["verdict"], "LOCATED_CO_OCCURRING")
        self.assertEqual(res["best_match_page"], 2)
        self.assertTrue(res["co_located"])

    def test_dislocated_number(self):
        # Number 24 is on page 1, but "PCR" is on page 2
        res = audit_single_claim("PCR reactions had 24 replicates", self.sample_pages)
        self.assertEqual(res["verdict"], "NUMBER_DISLOCATED")
        self.assertEqual(res["best_match_page"], 2)
        self.assertFalse(res["co_located"])

    def test_no_match(self):
        res = audit_single_claim("Antarctic ice core climate samples", self.sample_pages)
        self.assertEqual(res["verdict"], "NO_SURFACE_MATCH")
        self.assertIsNone(res["best_match_page"])


class TestHeadlessSearchContract(unittest.TestCase):
    """Test that agent_search.py outputs conform to Literature Record schema."""

    def test_parse_openalex_item_fields(self):
        mock_item = {
            "id": "https://openalex.org/W12345",
            "title": "A Test Wildlife Paper",
            "publication_year": 2023,
            "doi": "https://doi.org/10.1234/test.2023",
            "authorships": [{"author": {"display_name": "Test Author"}}],
            "primary_location": {"source": {"display_name": "Journal of Testing"}}
        }
        rec = parse_openalex_item(mock_item)
        self.assertEqual(rec["schema_version"], "1.0")
        self.assertEqual(rec["title"], "A Test Wildlife Paper")
        self.assertEqual(rec["year"], 2023)
        self.assertEqual(rec["doi"], "10.1234/test.2023")
        self.assertIn("OpenAlex", rec["source_databases"])
        self.assertEqual(rec["ingestion_method"], "API_Automated")


class TestSchoolClustering(unittest.TestCase):
    """Test deterministic paradigm clustering and shift detection."""

    def test_cluster_by_paradigm_and_shifts(self):
        studies = [
            {
                "paper_id": "P1",
                "year": 2010,
                "paradigm": "Morphological Survey",
                "method": "Direct count",
                "is_established_school": False
            },
            {
                "paper_id": "P2",
                "year": 2020,
                "paradigm": "Molecular Ecology",
                "method": "Metabarcoding",
                "is_established_school": True
            }
        ]
        clustered = cluster_by_paradigm(studies)
        self.assertIn("Morphological Survey", clustered)
        self.assertIn("Molecular Ecology", clustered)
        self.assertEqual(clustered["Morphological Survey"]["status"], "ANALYTICAL GROUPING")
        self.assertEqual(clustered["Molecular Ecology"]["status"], "ESTABLISHED SCHOOL")

        shifts = detect_paradigm_shifts(clustered)
        self.assertEqual(len(shifts), 1)
        self.assertIn("Morphological Survey", shifts[0]["transition"])
        self.assertIn("Molecular Ecology", shifts[0]["transition"])


if __name__ == "__main__":
    unittest.main()
