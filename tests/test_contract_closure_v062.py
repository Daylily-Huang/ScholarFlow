#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ScholarFlow v0.6.2 Contract Closure & Anti-Fragility Test Suite.

Covers all 16 contract and adversarial tests mandated by
ScholarFlow_v0.6.2_Contract_Closure_修复操作手册.md (Section 11).
"""

import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import tests.helpers as helpers

from agent_search import (
    is_thesis_work,
    query_openalex_headless,
    run_snowball_search,
    run_deep_search,
    parse_openalex_item,
)
from controversy_analyzer import (
    diagnose_controversy_type,
    compute_topic_consensus,
    normalize_claim,
)
from scripts.domain_neutrality_linter import check_skill_frontmatter_for_default_domain
from scripts.verify_package_assets import verify_repo_assets
from tests.schema_helpers import validate_payload, JSONSCHEMA_AVAILABLE, ValidationError


class TestContractClosureV062(unittest.TestCase):
    """16 specific contract closure tests for ScholarFlow v0.6.2."""

    def setUp(self):
        if os.getenv("SCHOLARFLOW_STRICT_CONTRACT_CI") == "1":
            self.assertTrue(JSONSCHEMA_AVAILABLE, "Strict contract CI must have jsonschema installed")

    # 1. test_discovery_skill_points_to_canonical_schema
    def test_discovery_skill_points_to_canonical_schema(self):
        sk_path = helpers.REPO_ROOT / "skills" / "literature-discovery-acquisition" / "SKILL.md"
        text = sk_path.read_text(encoding="utf-8")

        self.assertIn("schemas/discovery_result.schema.json", text)
        self.assertIn("schemas/literature_record.schema.json", text)
        self.assertNotIn("assets/candidate_literature_schema.json", text)

    # 2. test_no_legacy_discovery_schema_as_active_contract
    def test_no_legacy_discovery_schema_as_active_contract(self):
        legacy = (
            helpers.REPO_ROOT
            / "skills"
            / "literature-discovery-acquisition"
            / "assets"
            / "candidate_literature_schema.json"
        )
        self.assertFalse(legacy.exists(), "Legacy candidate_literature_schema.json should be removed")

    # 3. test_no_theses_applies_to_backward_snowball
    def test_no_theses_applies_to_backward_snowball(self):
        seed_data = {
            "id": "https://openalex.org/W001",
            "doi": "https://doi.org/10.1000/seed",
            "display_name": "Seed Paper",
            "type": "article",
            "referenced_works": ["https://openalex.org/W101", "https://openalex.org/W102"],
        }
        ref_data = {
            "results": [
                {
                    "id": "https://openalex.org/W101",
                    "doi": "https://doi.org/10.1000/ref1",
                    "display_name": "Legitimate Journal Article",
                    "type": "article",
                },
                {
                    "id": "https://openalex.org/W102",
                    "doi": "https://doi.org/10.1000/ref2",
                    "display_name": "PhD Thesis On Ecosystems",
                    "type": "dissertation",
                },
            ]
        }

        class MockResponse:
            def __init__(self, payload):
                self.status = 200
                self._data = json.dumps(payload).encode("utf-8")
            def read(self):
                return self._data
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

        def fake_urlopen(req, timeout=20):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "filter=openalex_id" in url:
                return MockResponse(ref_data)
            elif "filter=cites" in url:
                return MockResponse({"results": []})
            else:
                return MockResponse(seed_data)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            records, _ = run_snowball_search("10.1000/seed", limit=10, include_theses=False)

        titles = [r.get("title") for r in records]
        self.assertIn("Legitimate Journal Article", titles)
        self.assertNotIn("PhD Thesis On Ecosystems", titles)

    # 4. test_no_theses_applies_to_forward_snowball
    def test_no_theses_applies_to_forward_snowball(self):
        seed_data = {
            "id": "https://openalex.org/W001",
            "doi": "https://doi.org/10.1000/seed",
            "display_name": "Seed Paper",
            "type": "article",
            "referenced_works": [],
        }
        cites_data = {
            "results": [
                {
                    "id": "https://openalex.org/W201",
                    "doi": "https://doi.org/10.1000/cite1",
                    "display_name": "Subsequent Journal Paper",
                    "type": "article",
                },
                {
                    "id": "https://openalex.org/W202",
                    "doi": "https://doi.org/10.1000/cite2",
                    "display_name": "Doctoral Dissertation on Topic",
                    "type": "thesis",
                },
            ]
        }

        class MockResponse:
            def __init__(self, payload):
                self.status = 200
                self._data = json.dumps(payload).encode("utf-8")
            def read(self):
                return self._data
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

        def fake_urlopen(req, timeout=20):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "filter=cites" in url:
                return MockResponse(cites_data)
            else:
                return MockResponse(seed_data)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            records, _ = run_snowball_search("10.1000/seed", limit=10, include_theses=False)

        titles = [r.get("title") for r in records]
        self.assertIn("Subsequent Journal Paper", titles)
        self.assertNotIn("Doctoral Dissertation on Topic", titles)

    # 5. test_deep_search_no_theses_does_not_reintroduce_thesis
    def test_deep_search_no_theses_does_not_reintroduce_thesis(self):
        r1 = [
            {
                "schema_version": "1.1",
                "record_id": "REC001",
                "title": "Paper 1",
                "doi": "10.1000/1",
                "citation_count": 50,
                "document_type": "article",
                "source_databases": ["OpenAlex"],
                "ingestion_method": "API_Automated",
                "screening_status": "Include",
                "authors": ["Author A"],
                "year": 2021,
            }
        ]

        def fake_snowball(seed_doi, limit=15, include_theses=True):
            self.assertFalse(include_theses, "Deep search phase 3 must pass include_theses=False")
            return [
                {
                    "schema_version": "1.1",
                    "record_id": "REC002",
                    "title": "Snowballed Journal Article",
                    "doi": "10.1000/2",
                    "citation_count": 10,
                    "document_type": "article",
                    "source_databases": ["OpenAlex"],
                    "ingestion_method": "Snowballing",
                    "screening_status": "Include",
                    "snowball_role": "BACKWARD_REFERENCE",
                    "authors": ["Author B"],
                    "year": 2020,
                }
            ], []

        with patch("agent_search.query_openalex_headless", return_value=(r1, None)):
            with patch("agent_search.run_snowball_search", side_effect=fake_snowball):
                candidates, _ = run_deep_search("biodiversity survey", limit=10, include_theses=False)

        types = [c.get("document_type") for c in candidates]
        self.assertNotIn("dissertation", types)
        self.assertNotIn("thesis", types)

    # 6. test_degree_of_freedom_article_is_not_thesis
    def test_degree_of_freedom_article_is_not_thesis(self):
        article_normal = {
            "type": "article",
            "display_name": "Degrees of freedom in statistical models",
        }
        self.assertFalse(is_thesis_work(article_normal))

        degree_day = {
            "type": "journal-article",
            "display_name": "Growing degree-days and crop yields",
        }
        self.assertFalse(is_thesis_work(degree_day))

        actual_thesis_type = {
            "type": "dissertation",
            "display_name": "Statistical methods for high-dimensional data",
        }
        self.assertTrue(is_thesis_work(actual_thesis_type))

        actual_thesis_title = {
            "type": "article",
            "display_name": "PhD Thesis: Deep Learning in Genomic Medicine",
        }
        self.assertTrue(is_thesis_work(actual_thesis_title))

    # 7. test_real_headless_payload_validates_discovery_schema
    def test_real_headless_payload_validates_discovery_schema(self):
        if not JSONSCHEMA_AVAILABLE:
            self.skipTest("jsonschema not installed")

        raw_item = {
            "id": "https://openalex.org/W999",
            "display_name": "High-Throughput Sequencing of Fecal DNA",
            "authorships": [{"author": {"display_name": "Smith, J."}}],
            "publication_year": 2024,
            "type": "article",
            "doi": "https://doi.org/10.1000/seq2024",
            "open_access": {"is_oa": True, "oa_status": "gold"},
            "best_oa_location": {"pdf_url": "https://example.com/seq.pdf"},
            "cited_by_count": 5,
        }
        candidate = parse_openalex_item(raw_item)
        candidate["record_id"] = "REC001"

        payload = {
            "schema_version": "1.1",
            "status": "SUCCESS",
            "search_target": "noninvasive genetics",
            "search_protocol": {
                "mode": "quick",
                "query": "noninvasive genetics",
                "limit": 10,
                "include_theses": True,
            },
            "candidates": [candidate],
        }

        validate_payload(payload, "discovery_result.schema.json")

    # 8. test_invalid_discovery_payload_rejected
    def test_invalid_discovery_payload_rejected(self):
        if not JSONSCHEMA_AVAILABLE:
            self.skipTest("jsonschema not installed")

        bad_payload = {
            "schema_version": "1.1",
            "status": "NON_EXISTENT_STATUS",
            "search_protocol": {"mode": "quick"},
            "candidates": [],
        }
        with self.assertRaises(ValidationError):
            validate_payload(bad_payload, "discovery_result.schema.json")

    # 9. test_real_extraction_payload_validates_schema
    def test_real_extraction_payload_validates_schema(self):
        if not JSONSCHEMA_AVAILABLE:
            self.skipTest("jsonschema not installed")

        valid_extraction = {
            "schema_version": "1.1",
            "paper_metadata": {
                "title": "Quantitative PCR Performance Analysis",
                "authors": ["Lee, K.", "Wong, T."],
                "year": 2023,
                "doi": "10.1000/qpcr.2023",
            },
            "extraction_metadata": {
                "mode": "standard",
                "timestamp": "2026-09-06T10:00:00Z",
            },
            "evidence_records": [
                {
                    "schema_version": "1.1",
                    "evidence_id": "EV001",
                    "record_id": "REC001",
                    "field": "Annealing Temperature",
                    "extracted_value": 58.5,
                    "support_type": "EXPLICIT",
                    "evidence_strength": "DIRECT_EMPIRICAL",
                    "claim_status": "SUPPORTED",
                }
            ],
            "auditor_verdict": {
                "verdict": "PASS",
                "checklist_passed": True,
                "auditor_notes": "All claims grounded verbatim.",
            },
        }
        validate_payload(valid_extraction, "extraction_result.schema.json")

    # 10. test_invalid_support_type_rejected
    def test_invalid_support_type_rejected(self):
        if not JSONSCHEMA_AVAILABLE:
            self.skipTest("jsonschema not installed")

        bad_evidence = {
            "schema_version": "1.1",
            "evidence_id": "EV001",
            "record_id": "REC001",
            "field": "Sample Size",
            "extracted_value": 42,
            "support_type": "E4",  # Bare legacy E4 is forbidden in canonical schema
            "claim_status": "SUPPORTED",
        }
        with self.assertRaises(ValidationError):
            validate_payload(bad_evidence, "evidence_record.schema.json")

    # 11. test_no_skill_local_json_schema_contracts
    def test_no_skill_local_json_schema_contracts(self):
        skills_dir = helpers.REPO_ROOT / "skills"
        local_schemas = list(skills_dir.rglob("*.schema.json"))
        self.assertEqual(local_schemas, [], f"Found local schema files in skills: {local_schemas}")

        # Check explicit forbidden legacy names
        cand_schema = (
            skills_dir
            / "literature-discovery-acquisition"
            / "assets"
            / "candidate_literature_schema.json"
        )
        ext_schema = (
            skills_dir
            / "literature-evidence-extraction"
            / "assets"
            / "evidence_extraction_schema.json"
        )
        self.assertFalse(cand_schema.exists(), "candidate_literature_schema.json must not exist")
        self.assertFalse(ext_schema.exists(), "evidence_extraction_schema.json must not exist")

    # 12. test_disjoint_methods_do_not_claim_causal_artifact
    def test_disjoint_methods_do_not_claim_causal_artifact(self):
        claims = [
            {"topic": "T1", "paper_id": "P1", "stance": "SUPPORT", "method": "Method Alpha", "weight": 1.0},
            {"topic": "T1", "paper_id": "P2", "stance": "REFUTE", "method": "Method Beta", "weight": 1.0},
        ]
        diag = diagnose_controversy_type(claims)
        self.assertNotEqual(diag.get("confidence"), "High")
        self.assertEqual(diag.get("causal_status"), "NOT_ESTABLISHED")
        self.assertIn("requires_review", diag)
        self.assertIn("observed_pattern", diag)

    # 13. test_large_metric_difference_requires_comparability
    def test_large_metric_difference_requires_comparability(self):
        claims = [
            {"topic": "T1", "paper_id": "P1", "stance": "SUPPORT", "method": "M", "metric_value": 10.0, "weight": 1.0},
            {"topic": "T1", "paper_id": "P2", "stance": "REFUTE", "method": "M", "metric_value": 2.0, "weight": 1.0},
        ]
        diag = diagnose_controversy_type(claims)
        self.assertNotEqual(diag.get("confidence"), "High")
        self.assertEqual(diag.get("causal_status"), "NOT_ESTABLISHED")
        self.assertIn("comparability", diag.get("reason", "").lower())
        self.assertIn("requires_review", diag)

    # 14. test_consensus_is_scoped_to_current_evidence_set
    def test_consensus_is_scoped_to_current_evidence_set(self):
        claims = [
            {"topic": "T1", "paper_id": "P1", "stance": "SUPPORT", "weight": 1.0},
            {"topic": "T1", "paper_id": "P2", "stance": "SUPPORT", "weight": 1.0},
        ]
        res = compute_topic_consensus(claims)
        self.assertEqual(res.get("classification_scope"), "CURRENT_EVIDENCE_SET_ONLY")
        self.assertIs(res.get("external_consensus_claim"), False)
        reason = res["controversy_diagnosis"].get("reason", "").lower()
        self.assertIn("supplied evidence set", reason)

    # 15. test_skill_frontmatter_has_no_default_domain
    def test_skill_frontmatter_has_no_default_domain(self):
        skills_dir = helpers.REPO_ROOT / "skills"
        for sk_md in skills_dir.glob("*/SKILL.md"):
            violations = check_skill_frontmatter_for_default_domain(str(sk_md))
            self.assertEqual(violations, [], f"Domain bias found in {sk_md}: {violations}")

    # 16. test_repository_contains_required_skill_assets
    def test_repository_contains_required_skill_assets(self):
        verified = verify_repo_assets(helpers.REPO_ROOT)
        self.assertTrue(verified, "verify_repo_assets must return True")


if __name__ == "__main__":
    unittest.main()

