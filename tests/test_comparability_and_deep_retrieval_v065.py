# -*- coding: utf-8 -*-
"""
test_comparability_and_deep_retrieval_v065.py
---------------------------------------------
ScholarFlow v0.6.5 (RFC-013) Regression & Verification Test Suite.

Covers:
1. Comparability Matrix & Pre-synthesis Stratification (comparability.py)
   - Incompatible metrics/boundaries require stratification and do not trigger false controversy.
   - Subject discrepancies / metric incompatibilities marked as NOT_COMPARABLE.
   - Unit transformations recognized (ind/km2 vs ind/100km2).
2. Study-Level Independence Weight Capping (controversy_analyzer.py)
   - Multi-claim inflation from the same independence group / paper is capped at 1.0 total weight.
   - Single paper cannot overwhelm independent studies by generating dozens of sub-claims.
3. QueryExecutionResult & Cursor Pagination (agent_search.py)
   - QueryExecutionResult 2-tuple unpacking contract.
   - OpenAlex cursor pagination loop and truthful reported_total_hits capture.
   - Retrieval Coverage Ledger (Ledger A) reflects PARTIAL & TRUNCATED_BY_LIMIT when hits > retrieved.
4. Canonical Deduplication & Multi-source Lineage (agent_search.py & ingest_external_records.py)
   - deduplicate_records unifies with merge_candidate_records.
   - Preserves multi-source provenance and enriches missing metadata.
5. Canonical Schema Validation (schemas/comparison_record.schema.json)
   - Validates generated ComparisonRecords against Draft 2020-12 schema.

Pure Python standard library + internal engine (zero heavy runtime dependencies).
"""

import io
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

import tests.helpers as helpers
from tests.schema_helpers import validate_payload, JSONSCHEMA_AVAILABLE

# Ensure skills scripts are in sys.path
_synthesis_scripts = helpers.REPO_ROOT / "skills" / "literature-synthesis" / "scripts"
_discovery_scripts = helpers.REPO_ROOT / "skills" / "literature-discovery-acquisition" / "scripts"
for p in [str(_synthesis_scripts), str(_discovery_scripts)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from comparability import (
    ComparabilityStatus,
    DimensionStatus,
    evaluate_claim_comparability,
    stratify_claims_by_comparability,
    evaluate_dimension_subject,
    evaluate_dimension_method,
    evaluate_dimension_metric,
    evaluate_dimension_boundary,
)
from controversy_analyzer import (
    compute_topic_consensus,
    analyze,
)
from agent_search import (
    QueryExecutionResult,
    query_openalex_headless,
    deduplicate_records,
    run_headless_search,
)
from retrieval_coverage import CoverageStatus, PaginationStatus, RetrievalStatus


class TestComparabilityAndDeepRetrievalV065(unittest.TestCase):
    """Test suite for ScholarFlow v0.6.5 comparability matrix and deep retrieval features."""

    # -------------------------------------------------------------------------
    # 1. Comparability Matrix & Pre-synthesis Stratification Tests
    # -------------------------------------------------------------------------

    def test_01_incompatible_boundaries_require_stratification_no_false_controversy(self):
        """Claims with incompatible environmental boundaries (winter vs summer) require stratification."""
        claim_winter = {
            "claim_id": "CLM-001",
            "topic": "Snow leopard density in Sanjiangyuan",
            "paper_id": "Zhang2018",
            "independence_group_id": "GROUP_ZHANG",
            "claim": "Sanjiangyuan density is high in winter snow conditions",
            "stance": "SUPPORT",
            "method": "Line transect scrape count",
            "boundary": "winter snow season only",
            "metric": "density",
            "unit": "ind/100km2",
            "evidence_tier": "E2",
            "weight": 0.8,
        }
        claim_summer = {
            "claim_id": "CLM-002",
            "topic": "Snow leopard density in Sanjiangyuan",
            "paper_id": "Li2020",
            "independence_group_id": "GROUP_LI",
            "claim": "Sanjiangyuan density is lower during summer dry period",
            "stance": "REFUTE",
            "method": "Line transect scrape count",
            "boundary": "summer dry season only",
            "metric": "density",
            "unit": "ind/100km2",
            "evidence_tier": "E2",
            "weight": 0.8,
        }

        # Pairwise comparison check
        comp = evaluate_claim_comparability(claim_winter, claim_summer)
        self.assertEqual(comp["status"], ComparabilityStatus.STRATIFY_REQUIRED)
        self.assertEqual(
            comp["dimension_evaluations"]["environment_or_setting"],
            DimensionStatus.DIFFERENT_STRATUM,
        )
        self.assertIsNotNone(comp["stratification_key"])
        self.assertIn("boundary", comp["stratification_key"])

        # Pre-synthesis stratification check
        strat_res = stratify_claims_by_comparability([claim_winter, claim_summer])
        self.assertIn("core_stratum", strat_res["strata"])
        # Winter and summer are isolated into separate strata
        self.assertEqual(len(strat_res["strata"]), 2)
        self.assertEqual(len(strat_res["uncomparable_claims"]), 0)

        # Full analysis check: parallel strata preserved, headline consensus not falsely conflated
        res = analyze([claim_winter, claim_summer])
        topic_res = res["Snow leopard density in Sanjiangyuan"]
        self.assertIn("strata", topic_res)
        self.assertEqual(len(topic_res["strata"]), 2)
        self.assertIn("comparability_records", topic_res)
        self.assertEqual(len(topic_res["comparability_records"]), 1)

    def test_02_disparate_entities_or_incompatible_metrics_marked_not_comparable(self):
        """Claims with completely disparate subjects or incompatible metrics are NOT_COMPARABLE."""
        claim_a = {
            "claim_id": "CLM-101",
            "topic": "Carnivore density",
            "subject": "snow leopard",
            "metric": "population density",
            "unit": "ind/km2",
            "method": "camera trap",
            "weight": 1.0,
        }
        claim_b = {
            "claim_id": "CLM-102",
            "topic": "Carnivore density",
            "subject": "tibetan wolf",
            "metric": "home range size",
            "unit": "km2",
            "method": "gps collar",
            "weight": 1.0,
        }

        comp = evaluate_claim_comparability(claim_a, claim_b)
        self.assertEqual(comp["status"], ComparabilityStatus.NOT_COMPARABLE)
        self.assertIn("disparate entities or metrics", comp["rationale"])

        strat_res = stratify_claims_by_comparability([claim_a, claim_b])
        self.assertIn(claim_b, strat_res["uncomparable_claims"])

    def test_03_convertible_metric_units_identified(self):
        """Density units ind/km2 and ind/100km2 are detected as convertible."""
        claim_a = {
            "claim_id": "CLM-201",
            "subject": "black muntjac",
            "metric": "density",
            "unit": "ind/km2",
            "method": "fecal dna secr",
            "weight": 1.0,
        }
        claim_b = {
            "claim_id": "CLM-202",
            "subject": "black muntjac",
            "metric": "density",
            "unit": "ind/100km2",
            "method": "fecal dna secr",
            "weight": 1.0,
        }

        comp = evaluate_claim_comparability(claim_a, claim_b)
        self.assertEqual(comp["status"], ComparabilityStatus.COMPARABLE_AFTER_TRANSFORM)
        self.assertEqual(
            comp["dimension_evaluations"]["outcome_metric"],
            DimensionStatus.CONVERTIBLE,
        )
        self.assertIsNotNone(comp["transform_rule"])
        self.assertIn("factor", comp["transform_rule"])

    def test_04_comparison_record_schema_conformance(self):
        """Comparison records generated across all statuses conform to schemas/comparison_record.schema.json."""
        if not JSONSCHEMA_AVAILABLE:
            self.skipTest("jsonschema library not available in environment")

        claim_base = {
            "claim_id": "CLM-001",
            "subject": "snow leopard",
            "metric": "density",
            "unit": "ind/km2",
            "method": "camera trap",
            "boundary": "natural habitat",
        }

        variations = [
            # DIRECTLY_COMPARABLE
            {"claim_id": "CLM-002", "subject": "snow leopard", "metric": "density", "unit": "ind/km2", "method": "camera trap", "boundary": "natural habitat"},
            # STRATIFY_REQUIRED
            {"claim_id": "CLM-003", "subject": "snow leopard", "metric": "density", "unit": "ind/km2", "method": "camera trap", "boundary": "captive laboratory enclosure"},
            # COMPARABLE_AFTER_TRANSFORM
            {"claim_id": "CLM-004", "subject": "snow leopard", "metric": "density", "unit": "ind/100km2", "method": "camera trap", "boundary": "natural habitat"},
            # NOT_COMPARABLE
            {"claim_id": "CLM-005", "subject": "red panda", "metric": "blood glucose", "unit": "mmol/l", "method": "blood test", "boundary": "zoo"},
        ]

        for other_claim in variations:
            comp = evaluate_claim_comparability(claim_base, other_claim)
            validate_payload(comp, "comparison_record.schema.json")

    # -------------------------------------------------------------------------
    # 2. Study-Level Independence Weight Capping Tests
    # -------------------------------------------------------------------------

    def test_05_study_level_independence_capping_prevents_multi_claim_inflation(self):
        """A single study generating multiple sub-claims is strictly capped at cumulative weight 1.0."""
        # Team A generates 5 claims supporting hypothesis X from 1 single paper
        team_a_claims = [
            {
                "claim_id": f"CLM-A{i}",
                "topic": "Muntjac gene flow corridor",
                "paper_id": "Wang2020",
                "study_id": "STUDY_WANG_2020",
                "independence_group_id": "LAB_WANG",
                "stance": "SUPPORT",
                "weight": 0.8,
                "evidence_tier": "E2",
            }
            for i in range(1, 6)
        ]

        # Team B (completely independent) generates 1 claim refuting hypothesis X
        team_b_claim = {
            "claim_id": "CLM-B1",
            "topic": "Muntjac gene flow corridor",
            "paper_id": "Zhao2021",
            "study_id": "STUDY_ZHAO_2021",
            "independence_group_id": "LAB_ZHAO",
            "stance": "REFUTE",
            "weight": 1.0,
            "evidence_tier": "E1",
        }

        all_claims = team_a_claims + [team_b_claim]
        consensus = compute_topic_consensus(all_claims)

        # Total weight for Team A (5 * 0.8 = 4.0 raw) MUST be scaled down to 1.0
        # Team B has 1.0 weight.
        # Total scaled weight = 1.0 (SUPPORT) + 1.0 (REFUTE) = 2.0.
        self.assertAlmostEqual(consensus["stance_weights"]["SUPPORT"], 1.0, places=2)
        self.assertAlmostEqual(consensus["stance_weights"]["REFUTE"], 1.0, places=2)
        self.assertAlmostEqual(consensus["total_evidence_weight"], 2.0, places=2)
        self.assertAlmostEqual(consensus["heuristic_balance_score"]["SUPPORT"], 50.0, places=1)
        self.assertAlmostEqual(consensus["heuristic_balance_score"]["REFUTE"], 50.0, places=1)
        # Verify Team A's 5 sub-claims did NOT hijack the consensus
        self.assertIn(consensus["consensus_classification"], ["ACTIVE_CONTROVERSY", "CONDITIONAL_CONSENSUS"])


    # -------------------------------------------------------------------------
    # 3. QueryExecutionResult & Cursor Pagination Tests
    # -------------------------------------------------------------------------

    def test_06_query_execution_result_tuple_contract(self):
        """QueryExecutionResult behaves as a 2-tuple while carrying rich metadata."""
        sample_records = [{"title": "Paper 1", "id": "REC001"}, {"title": "Paper 2", "id": "REC002"}]
        res = QueryExecutionResult(
            records=sample_records,
            error=None,
            meta={
                "reported_total_hits": 4500,
                "pages_fetched": 3,
                "coverage_status": CoverageStatus.PARTIAL,
                "pagination_status": PaginationStatus.TRUNCATED_BY_LIMIT,
            }
        )

        # 1. Unpacking check
        recs, err = res
        self.assertEqual(recs, sample_records)
        self.assertIsNone(err)

        # 2. Length & indexing check
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0], sample_records)
        self.assertEqual(res[1], None)

        # 3. Metadata properties
        self.assertEqual(res.reported_total_hits, 4500)
        self.assertEqual(res.pages_fetched, 3)
        self.assertEqual(res.coverage_status, CoverageStatus.PARTIAL)
        self.assertEqual(res.pagination_status, PaginationStatus.TRUNCATED_BY_LIMIT)
        self.assertEqual(res.get("pages_fetched"), 3)

    @patch("urllib.request.urlopen")
    def test_07_openalex_cursor_pagination_and_coverage_ledger_partial(self, mock_urlopen):
        """Cursor pagination retrieves across pages up to limit and faithfully records PARTIAL in Ledger A."""
        # Simulated responses for page 1 and page 2
        page1_data = {
            "meta": {"count": 12500, "next_cursor": "CURSOR_TOKEN_PAGE2"},
            "results": [
                {"id": "W1", "display_name": "Paper 1", "type": "article", "publication_year": 2021, "authorships": []},
                {"id": "W2", "display_name": "Paper 2", "type": "article", "publication_year": 2022, "authorships": []},
            ]
        }
        page2_data = {
            "meta": {"count": 12500, "next_cursor": "CURSOR_TOKEN_PAGE3"},
            "results": [
                {"id": "W3", "display_name": "Paper 3", "type": "article", "publication_year": 2023, "authorships": []},
                {"id": "W4", "display_name": "Paper 4", "type": "article", "publication_year": 2024, "authorships": []},
            ]
        }

        mock_resp1 = MagicMock()
        mock_resp1.status = 200
        mock_resp1.read.return_value = json.dumps(page1_data).encode("utf-8")
        mock_resp1.__enter__.return_value = mock_resp1

        mock_resp2 = MagicMock()
        mock_resp2.status = 200
        mock_resp2.read.return_value = json.dumps(page2_data).encode("utf-8")
        mock_resp2.__enter__.return_value = mock_resp2

        mock_urlopen.side_effect = [mock_resp1, mock_resp2]

        # Request limit=3 (requires 2 pages: 2 from page 1, 1 from page 2)
        q_res = query_openalex_headless("habitat connectivity", limit=3, per_page=2)
        self.assertEqual(len(q_res.records), 3)
        self.assertEqual(q_res.pages_fetched, 2)
        self.assertEqual(q_res.reported_total_hits, 12500)
        self.assertEqual(q_res.coverage_status, CoverageStatus.PARTIAL)
        self.assertEqual(q_res.pagination_status, PaginationStatus.TRUNCATED_BY_LIMIT)

        # Now test run_headless_search Ledger A truthfulness
        mock_urlopen.side_effect = [mock_resp1, mock_resp2]
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "out.json"
            exit_code = run_headless_search(
                query="habitat connectivity",
                mode="quick",
                limit=3,
                output_file=str(out_file)
            )
            self.assertEqual(exit_code, 0)
            data = json.loads(out_file.read_text(encoding="utf-8"))

            ledger = data["retrieval_coverage_ledger"]
            self.assertEqual(len(ledger), 1)
            entry = ledger[0]
            # Must faithfully record 12500 total hits and PARTIAL coverage
            self.assertEqual(entry["reported_total_hits"], 12500)
            self.assertEqual(entry["metadata_records_retrieved"], 3)
            self.assertEqual(entry["coverage_status"], "PARTIAL")
            self.assertEqual(entry["pagination_status"], "TRUNCATED_BY_LIMIT")
            self.assertEqual(data["overall_discovery_status"], "SUCCESS_WITH_RETRIEVAL_GAPS")

    # -------------------------------------------------------------------------
    # 4. Canonical Deduplication & Multi-source Lineage Tests
    # -------------------------------------------------------------------------

    def test_08_canonical_deduplicate_records_lineage_and_cross_source(self):
        """deduplicate_records unifies with merge_candidate_records and preserves multi-source provenance."""
        rec_openalex = {
            "record_id": "REC-001",
            "doi": "10.1016/j.biocon.2020.108581",
            "title": "Camera trapping reveals muntjac dynamics",
            "source_databases": ["OpenAlex"],
            "abstract": None,
        }
        rec_crossref = {
            "record_id": "REC-002",
            "doi": "10.1016/j.biocon.2020.108581",
            "title": "Camera Trapping Reveals Muntjac Dynamics",
            "source_databases": ["Crossref"],
            "abstract": "A comprehensive study on muntjac occupancy across years.",
        }
        rec_cnki = {
            "record_id": "REC-003",
            "doi": "NR",
            "title": "黑麂种群遗传多样性与保护对策研究",
            "source_databases": ["CNKI"],
            "abstract": "本文对浙江省黑麂种群进行了系统研究...",
        }

        deduped = deduplicate_records([rec_openalex, rec_crossref, rec_cnki])

        # OpenAlex and Crossref merged into 1; CNKI retained -> total 2 records
        self.assertEqual(len(deduped), 2)

        # Check merged record
        m = next(r for r in deduped if r.get("doi") == "10.1016/j.biocon.2020.108581")
        self.assertIn("OpenAlex", m["source_databases"])
        self.assertIn("Crossref", m["source_databases"])
        # Abstract enriched from second source
        self.assertEqual(m["abstract"], "A comprehensive study on muntjac occupancy across years.")

        # Check CNKI record preserved
        cnki_r = next(r for r in deduped if "黑麂" in r.get("title", ""))
        self.assertIsNotNone(cnki_r)


if __name__ == "__main__":
    unittest.main()
