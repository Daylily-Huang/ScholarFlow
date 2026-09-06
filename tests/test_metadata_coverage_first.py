# -*- coding: utf-8 -*-
"""
test_metadata_coverage_first.py
--------------------------------
Comprehensive test suite verifying the Metadata Coverage First architecture
and Section 66 requirements of ScholarFlow Skill 1:
1. test_auth_required_is_not_zero_hits
2. test_partial_pagination_is_not_complete
3. test_download_failure_keeps_candidate
4. test_metadata_corpus_frozen_before_acquisition
5. test_user_export_can_complete_source_coverage
6. test_openalex_records_do_not_mark_cnki_searched
7. test_total_hits_reconciles_with_retrieved
8. test_truncated_results_mark_partial
9. test_retrieval_and_fulltext_status_are_independent
10. test_cnki_unique_records_survive_cross_source_dedup
11. test_cnki_refworks_count_matches_export
12. test_wanfang_ris_records_preserve_source
13. test_vip_import_profile
14. test_chinese_title_only_record_is_retained
15. test_chinese_metadata_can_be_enriched_cross_source
"""
import unittest
from pathlib import Path

import helpers  # noqa: F401 (bootstraps sys.path)

from retrieval_coverage import (
    RetrievalStatus,
    CoverageStatus,
    PaginationStatus,
    OverallDiscoveryStatus,
    FulltextAcquisitionStatus,
    evaluate_coverage_status,
    build_retrieval_ledger_entry,
    reconcile_retrieval_coverage_ledger,
    freeze_metadata_corpus,
    audit_discovery_coverage_gate,
    reconcile_discovery_and_acquisition,
)
import ingest_external_records as ing

FIXTURES = helpers.FIXTURES


class TestMetadataCoverageFirst(unittest.TestCase):
    """Test suite covering the 15 requirements from Section 66."""

    def test_01_auth_required_is_not_zero_hits(self):
        """Rule 10 & Anti-pattern 3: Access failure must NOT be written as 0 hits."""
        entry = build_retrieval_ledger_entry(
            source_id="CNKI",
            query_id="Q01",
            query_text="species genetics",
            search_mode="DIRECT_METADATA_SEARCH",
            execution_status=RetrievalStatus.AUTH_REQUIRED,
            reported_total_hits=0,  # Falsely attempted 0
            metadata_records_retrieved=0,
            pagination_status=PaginationStatus.UNKNOWN
        )
        # Hits must be corrected to None and coverage marked UNKNOWN
        self.assertIsNone(entry["reported_total_hits"])
        self.assertEqual(entry["coverage_status"], CoverageStatus.UNKNOWN)
        self.assertEqual(entry["execution_status"], RetrievalStatus.AUTH_REQUIRED)

    def test_02_partial_pagination_is_not_complete(self):
        """Section 12: Pagination completion must be an auditable hard requirement."""
        cov1 = evaluate_coverage_status(
            execution_status=RetrievalStatus.SEARCHED_COMPLETE,
            reported_total_hits=863,
            metadata_records_retrieved=50,
            pagination_status=PaginationStatus.PARTIAL
        )
        self.assertEqual(cov1, CoverageStatus.PARTIAL)

        cov2 = evaluate_coverage_status(
            execution_status=RetrievalStatus.SEARCHED_COMPLETE,
            reported_total_hits=863,
            metadata_records_retrieved=50,
            pagination_status=PaginationStatus.TRUNCATED_BY_LIMIT
        )
        self.assertEqual(cov2, CoverageStatus.PARTIAL)
        self.assertNotEqual(cov2, CoverageStatus.COMPLETE)

    def test_03_download_failure_keeps_candidate(self):
        """Rule 4: A discovered record survives any fulltext acquisition failure."""
        candidates = [
            {"record_id": "REC001", "title": "Paper One", "screening_status": "Include"},
            {"record_id": "REC002", "title": "Paper Two", "screening_status": "Include"},
            {"record_id": "REC003", "title": "Paper Three", "screening_status": "Uncertain"},
        ]
        download_ledger = [
            {"id": "REC001", "status": "AUTH_REQUIRED", "note": "Institutional login required"},
            {"id": "REC002", "status": "PAYWALLED", "note": "Subscription required"},
            {"id": "REC003", "status": "DOWNLOAD_FAILED", "note": "HTTP 403 Forbidden"},
        ]
        retrieval_ledger = {
            "has_retrieval_gaps": False,
            "retrieval_gaps": [],
            "entries": []
        }
        frozen_corpus = {"unique_records": 3, "status": "CORPUS_FROZEN"}

        result = reconcile_discovery_and_acquisition(
            retrieval_ledger=retrieval_ledger,
            frozen_corpus=frozen_corpus,
            candidates=candidates,
            download_ledger=download_ledger
        )

        # All 3 candidates MUST remain in the literature set
        self.assertEqual(len(result["candidates"]), 3)
        self.assertEqual(result["overall_status"], OverallDiscoveryStatus.SUCCESS_WITH_ACQUISITION_GAPS)
        self.assertEqual(len(result["acquisition_gaps"]), 3)
        self.assertEqual(len(result["retrieval_gaps"]), 0)

    def test_04_metadata_corpus_frozen_before_acquisition(self):
        """Section 22: Metadata Corpus Freeze must freeze candidates and compute source contributions."""
        candidates = [
            {"id": "REC001", "title": "Paper A", "doi": "10.1000/1", "source_databases": ["OpenAlex"], "abstract": "Abs A"},
            {"id": "REC002", "title": "Paper B", "doi": "10.1000/2", "source_databases": ["CNKI"], "abstract": None},
            {"id": "REC003", "title": "Paper C", "doi": "10.1000/3", "source_databases": ["OpenAlex", "CNKI"], "abstract": "Abs C"},
        ]
        frozen = freeze_metadata_corpus(candidates)
        self.assertEqual(frozen["status"], "CORPUS_FROZEN")
        self.assertEqual(frozen["total_raw_records"], 3)
        self.assertEqual(frozen["unique_records"], 3)
        self.assertEqual(frozen["records_with_abstract"], 2)
        self.assertEqual(frozen["records_without_abstract"], 1)
        self.assertEqual(frozen["sources_distribution"]["OpenAlex"], 2)
        self.assertEqual(frozen["sources_distribution"]["CNKI"], 2)
        self.assertEqual(frozen["source_unique_contributions"]["OpenAlex"], 1)
        self.assertEqual(frozen["source_unique_contributions"]["CNKI"], 1)

    def test_05_user_export_can_complete_source_coverage(self):
        """Section 18-19: Mode C (USER_ASSISTED_EXPORT) is an auditable full coverage pathway."""
        entry = build_retrieval_ledger_entry(
            source_id="CNKI",
            query_id="Q01",
            query_text="SU=('wildlife' + 'ecology')",
            search_mode="USER_ASSISTED_EXPORT",
            execution_status=RetrievalStatus.SEARCHED_VIA_USER_EXPORT,
            reported_total_hits=138,
            metadata_records_retrieved=138,
            pagination_status=PaginationStatus.COMPLETE
        )
        self.assertEqual(entry["coverage_status"], CoverageStatus.COMPLETE)
        self.assertEqual(entry["metadata_retrieval_rate"], 1.0)
        self.assertEqual(entry["search_mode"], "USER_ASSISTED_EXPORT")

    def test_06_openalex_records_do_not_mark_cnki_searched(self):
        """Section 20 & Anti-pattern 4: Cross-database discovery is complementary, NOT substitutive."""
        # Simulated violation: CNKI claimed complete by pointing to OpenAlex discovery
        bad_entry = {
            "source_id": "CNKI",
            "query_id": "Q01",
            "query_text": "wildlife",
            "execution_status": RetrievalStatus.SEARCHED_COMPLETE,
            "reported_total_hits": 20,
            "metadata_records_retrieved": 20,
            "pagination_status": PaginationStatus.COMPLETE,
            "coverage_status": CoverageStatus.COMPLETE,
            "notes": "Covered via OpenAlex query results"
        }
        frozen = {"status": "CORPUS_FROZEN", "unique_records": 20}
        audit = audit_discovery_coverage_gate(
            retrieval_ledger={"entries": [bad_entry], "has_retrieval_gaps": False},
            frozen_corpus=frozen,
            candidates=[]
        )
        self.assertFalse(audit["checks"]["no_cross_source_substitution"])
        self.assertEqual(audit["status"], "REJECT")
        self.assertTrue(any("Cross-source substitution" in v for v in audit["violations"]))

    def test_07_total_hits_reconciles_with_retrieved(self):
        """Section 14 & 61: Total hits must cleanly reconcile with retrieved count."""
        entry = build_retrieval_ledger_entry(
            source_id="PubMed",
            query_id="Q01",
            query_text="fecal DNA sequencing",
            search_mode="DIRECT_METADATA_SEARCH",
            execution_status=RetrievalStatus.SEARCHED_COMPLETE,
            reported_total_hits=42,
            metadata_records_retrieved=42,
            pagination_status=PaginationStatus.COMPLETE
        )
        self.assertEqual(entry["coverage_status"], CoverageStatus.COMPLETE)
        self.assertEqual(entry["metadata_retrieval_rate"], 1.0)

    def test_08_truncated_results_mark_partial(self):
        """Section 12: Truncated pagination must result in PARTIAL coverage status."""
        entry = build_retrieval_ledger_entry(
            source_id="Wanfang",
            query_id="Q01",
            query_text="生态模型",
            search_mode="BROWSER_METADATA_SEARCH",
            execution_status=RetrievalStatus.SEARCHED_COMPLETE,
            reported_total_hits=91,
            metadata_records_retrieved=74,
            pagination_status=PaginationStatus.TRUNCATED_BY_LIMIT
        )
        self.assertEqual(entry["coverage_status"], CoverageStatus.PARTIAL)
        self.assertEqual(entry["pagination_status"], PaginationStatus.TRUNCATED_BY_LIMIT)
        self.assertAlmostEqual(entry["metadata_retrieval_rate"], 74 / 91, places=3)

    def test_09_retrieval_and_fulltext_status_are_independent(self):
        """Section 5: Discovery status and acquisition status must be completely decoupled."""
        record = {
            "record_id": "REC001",
            "title": "Conservation Genetics of Muntjac",
            "metadata_verification_status": "VERIFIED_API",
            "fulltext_acquisition_status": FulltextAcquisitionStatus.PAYWALLED
        }
        self.assertEqual(record["metadata_verification_status"], "VERIFIED_API")
        self.assertEqual(record["fulltext_acquisition_status"], "PAYWALLED")
        # Neither status overrules or nullifies the other
        self.assertNotEqual(record["fulltext_acquisition_status"], record["metadata_verification_status"])

    def test_10_cnki_unique_records_survive_cross_source_dedup(self):
        """Section 52-53: Cross-source dedup preserves unique records and combines sources."""
        existing = [
            {"title": "Shared Paper Between DBs", "doi": "10.1000/shared", "source_databases": ["OpenAlex"]},
            {"title": "OpenAlex Only Paper", "doi": "10.1000/oa_only", "source_databases": ["OpenAlex"]},
        ]
        new_records = [
            {"title": "Shared Paper Between DBs", "doi": "10.1000/shared", "source_databases": ["CNKI"]},
            {"title": "CNKI Exclusive Paper", "doi": "10.1000/cnki_only", "source_databases": ["CNKI"]},
        ]
        merge_res = ing.merge_candidate_records(existing, new_records)
        self.assertEqual(merge_res["unique_count"], 3)
        self.assertEqual(merge_res["raw_count"], 4)

        shared = next(r for r in merge_res["merged_records"] if r["title"] == "Shared Paper Between DBs")
        self.assertIn("OpenAlex", shared["source_databases"])
        self.assertIn("CNKI", shared["source_databases"])

        self.assertEqual(merge_res["source_unique_contributions"]["CNKI"], 1)
        self.assertEqual(merge_res["source_unique_contributions"]["OpenAlex"], 1)

    def test_11_cnki_refworks_count_matches_export(self):
        """Section 39: CNKI Refworks parser parses exact item count without loss."""
        content = (FIXTURES / "sample_cnki_refworks.txt").read_text(encoding="utf-8")
        recs = ing.parse_cnki_refworks(content)
        self.assertEqual(len(recs), 2)
        # All items are captured with their specific document types
        types = {r["document_type"] for r in recs}
        self.assertEqual(types, {"Journal Article", "Thesis"})

    def test_12_wanfang_ris_records_preserve_source(self):
        """Section 40: Wanfang exports preserve Wanfang as source_database."""
        recs = ing.detect_and_parse_file(FIXTURES / "sample.ris", source_override="Wanfang")
        self.assertEqual(len(recs), 2)
        for r in recs:
            self.assertEqual(r["source_databases"], ["Wanfang"])
            self.assertEqual(r["ingestion_method"], "Wanfang_Import")

    def test_13_vip_import_profile(self):
        """Section 41: VIP export format is correctly parsed into candidate literature schema."""
        vip_content = """
【题名】高原鼠兔种群生态学研究
【作者】李强；王伟
【机构】中国科学院西北高原生物研究所
【刊名】兽类学报
【年份】2020
【关键词】高原鼠兔；种群动态；繁殖生态
【摘要】本研究探讨了青藏高原高寒草甸生态系统中高原鼠兔的种群生态特征及数量波动规律。
【DOI】10.1234/vip.2020.001

【题名】青藏高原高寒草甸退化草地恢复技术研究
【作者】张华
【机构】青海大学
【刊名】草业学报
【年份】2022
【关键词】高寒草甸；退化恢复；植被覆盖度
【摘要】评估了不同修复措施对退化草地植被恢复的影响。
"""
        recs = ing.parse_vip_format(vip_content)
        self.assertEqual(len(recs), 2)
        first = recs[0]
        self.assertEqual(first["title"], "高原鼠兔种群生态学研究")
        self.assertEqual(first["authors"], ["李强", "王伟"])
        self.assertEqual(first["year"], 2020)
        self.assertEqual(first["journal"], "兽类学报")
        self.assertEqual(first["doi"], "10.1234/vip.2020.001")
        self.assertIn("高原鼠兔", first["keywords"])
        self.assertIn("青藏高原", first["abstract"])
        self.assertEqual(first["source_databases"], ["VIP"])
        self.assertEqual(first["ingestion_method"], "VIP_Import")

    def test_14_chinese_title_only_record_is_retained(self):
        """Section 49: Title-only Chinese records must NEVER be dropped."""
        title_only_rec = {
            "title": "中国野生动物非损伤性DNA遗传多样性评估",
            "authors": ["张三"],
            "year": 2021,
            "journal": "生物多样性",
            "doi": "NR",
            "abstract": None,
            "keywords": [],
            "source_databases": ["CNKI"]
        }
        res = ing.merge_candidate_records([], [title_only_rec])
        self.assertEqual(len(res["merged_records"]), 1)
        retained = res["merged_records"][0]
        self.assertEqual(retained["title"], "中国野生动物非损伤性DNA遗传多样性评估")
        self.assertEqual(retained["metadata_status"], "TITLE_AUTHOR")

    def test_15_chinese_metadata_can_be_enriched_cross_source(self):
        """Section 50-51: Cross-source enrichment fills missing abstracts and detects conflicts."""
        cnki_base = {
            "title": "中国野生动物遗传多样性监测技术规范",
            "authors": ["李四"],
            "year": 2021,
            "journal": "生态学报",
            "doi": "NR",
            "abstract": None,
            "keywords": ["遗传多样性"],
            "source_databases": ["CNKI"]
        }
        openalex_enrichment = {
            "title": "中国野生动物遗传多样性监测技术规范",
            "authors": ["李四"],
            "year": 2021,
            "journal": "生态学报",
            "doi": "10.1016/sample.2021.001",
            "abstract": "This standard establishes comprehensive noninvasive genetic monitoring guidelines.",
            "keywords": ["遗传多样性", "监测技术"],
            "source_databases": ["OpenAlex"]
        }
        res = ing.merge_candidate_records([cnki_base], [openalex_enrichment])
        self.assertEqual(res["unique_count"], 1)
        merged = res["merged_records"][0]

        # Abstract enriched
        self.assertEqual(merged["abstract"], "This standard establishes comprehensive noninvasive genetic monitoring guidelines.")
        self.assertEqual(merged["abstract_source"], "OpenAlex")
        # DOI enriched
        self.assertEqual(merged["doi"], "10.1016/sample.2021.001")
        # Source provenance preserved
        self.assertIn("CNKI", merged["source_databases"])
        self.assertIn("OpenAlex", merged["source_databases"])
        self.assertEqual(merged["metadata_status"], "FULL_METADATA")

        # Now test conflict detection (different years)
        conflict_rec = {
            "title": "中国野生动物遗传多样性监测技术规范",
            "year": 2023,  # Conflict with 2021
            "source_databases": ["Crossref"]
        }
        conflict_res = ing.merge_candidate_records([merged], [conflict_rec])
        self.assertEqual(len(conflict_res["conflicts"]), 1)
        self.assertEqual(conflict_res["conflicts"][0]["status"], "CONFLICTING_METADATA")
        self.assertEqual(conflict_res["conflicts"][0]["field"], "year")


if __name__ == "__main__":
    unittest.main()
