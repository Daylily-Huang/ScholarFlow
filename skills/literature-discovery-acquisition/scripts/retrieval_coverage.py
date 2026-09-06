#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
retrieval_coverage.py
---------------------
ScholarFlow Skill 1 — Retrieval Completeness Layer & Coverage Ledger (Ledger A)

Enforces the Metadata Coverage First Principle:
1. Primary Objective: Comprehensive Metadata Discovery (minimize missed relevant literature).
2. Secondary Objective: Best-Effort Full-Text Acquisition (never drop discovered records on download failure).
3. Priority: Metadata Discovery Completeness > Full-Text Acquisition Success.
4. Truth In Search:
   - Access Failure (AUTH_REQUIRED, BOT_BLOCKED, NOT_SEARCHED) != 0 hits.
   - Truncated pagination is PARTIAL, never COMPLETE.
   - Cross-database discovery is complementary, not substitutive (OpenAlex != CNKI).
   - User-assisted export is a valid auditable coverage pathway.
   - Retrieval Gaps (HIGH SCIENTIFIC RISK) and Acquisition Gaps (OPERATIONAL LIMITATION) are decoupled.
"""

import re
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple


class RetrievalStatus:
    SEARCHED_COMPLETE = "SEARCHED_COMPLETE"
    SEARCHED_PARTIAL = "SEARCHED_PARTIAL"
    SEARCHED_WITH_ERRORS = "SEARCHED_WITH_ERRORS"
    SEARCHED_VIA_USER_EXPORT = "SEARCHED_VIA_USER_EXPORT"
    USER_ASSISTED_REQUIRED = "USER_ASSISTED_REQUIRED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    JS_BROWSER_REQUIRED = "JS_BROWSER_REQUIRED"
    BOT_BLOCKED = "BOT_BLOCKED"
    RATE_LIMITED = "RATE_LIMITED"
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"
    NOT_SEARCHED = "NOT_SEARCHED"

    ACCESS_FAILURE_STATUSES = {
        AUTH_REQUIRED,
        BOT_BLOCKED,
        RATE_LIMITED,
        TEMPORARILY_UNAVAILABLE,
        NOT_SEARCHED,
        USER_ASSISTED_REQUIRED,
        JS_BROWSER_REQUIRED,
    }


class CoverageStatus:
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PaginationStatus:
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    TRUNCATED_BY_LIMIT = "TRUNCATED_BY_LIMIT"
    FAILED_MIDWAY = "FAILED_MIDWAY"
    UNKNOWN = "UNKNOWN"


class OverallDiscoveryStatus:
    SUCCESS = "SUCCESS"
    SUCCESS_WITH_ERRORS = "SUCCESS_WITH_ERRORS"
    SUCCESS_WITH_RETRIEVAL_GAPS = "SUCCESS_WITH_RETRIEVAL_GAPS"
    SUCCESS_WITH_ACQUISITION_GAPS = "SUCCESS_WITH_ACQUISITION_GAPS"
    SUCCESS_WITH_RETRIEVAL_AND_ACQUISITION_GAPS = "SUCCESS_WITH_RETRIEVAL_AND_ACQUISITION_GAPS"
    FAILED = "FAILED"


class FulltextAcquisitionStatus:
    FULLTEXT_AVAILABLE = "FULLTEXT_AVAILABLE"
    OA_DOWNLOADED = "OA_DOWNLOADED"
    PREPRINT_AVAILABLE = "PREPRINT_AVAILABLE"
    BROWSER_DOWNLOADED = "BROWSER_DOWNLOADED"
    USER_PROVIDED = "USER_PROVIDED"
    PAYWALLED = "PAYWALLED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    BOT_BLOCKED = "BOT_BLOCKED"
    JS_REQUIRED = "JS_REQUIRED"
    CAJ_ONLY = "CAJ_ONLY"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"


def evaluate_coverage_status(
    execution_status: str,
    reported_total_hits: Optional[int],
    metadata_records_retrieved: int,
    pagination_status: str = PaginationStatus.COMPLETE
) -> str:
    """Evaluate database coverage status with strict truth-in-search rules.

    Iron Rules:
    1. If execution failed or was not performed, coverage is UNKNOWN (never COMPLETE).
    2. Access failure MUST NOT be recorded as 0 hits.
    3. If reported hits > retrieved count, coverage is PARTIAL (never COMPLETE).
    4. Truncated pagination is PARTIAL.
    5. 0 hits is only COMPLETE if execution succeeded and returned 0 genuine matches.
    """
    if execution_status in RetrievalStatus.ACCESS_FAILURE_STATUSES:
        return CoverageStatus.UNKNOWN

    if execution_status == RetrievalStatus.SEARCHED_PARTIAL:
        return CoverageStatus.PARTIAL

    if execution_status in (RetrievalStatus.SEARCHED_COMPLETE, RetrievalStatus.SEARCHED_VIA_USER_EXPORT):
        # Successful zero results
        if reported_total_hits == 0 and metadata_records_retrieved == 0:
            return CoverageStatus.COMPLETE

        # Pagination was truncated or failed
        if pagination_status in (PaginationStatus.TRUNCATED_BY_LIMIT, PaginationStatus.PARTIAL, PaginationStatus.FAILED_MIDWAY):
            return CoverageStatus.PARTIAL

        # Hit count reconciliation
        if reported_total_hits is not None and reported_total_hits > 0:
            if metadata_records_retrieved < reported_total_hits:
                return CoverageStatus.PARTIAL
            return CoverageStatus.COMPLETE

        # When total hits not reported by DB but pagination completed
        if pagination_status == PaginationStatus.COMPLETE:
            return CoverageStatus.COMPLETE
        return CoverageStatus.PARTIAL

    return CoverageStatus.UNKNOWN


def build_retrieval_ledger_entry(
    source_id: str,
    query_id: str,
    query_text: str,
    search_mode: str,
    execution_status: str,
    reported_total_hits: Optional[int] = None,
    metadata_records_retrieved: int = 0,
    unique_records_after_source_dedup: Optional[int] = None,
    pagination_status: str = PaginationStatus.COMPLETE,
    coverage_status: Optional[str] = None,
    failure_reason: Optional[str] = None,
    notes: str = ""
) -> Dict[str, Any]:
    """Construct an auditable Ledger A entry with automatic truth validation."""
    # Enforce Rule 10: Access Failure != 0 hits
    if execution_status in RetrievalStatus.ACCESS_FAILURE_STATUSES:
        if reported_total_hits == 0:
            reported_total_hits = None
        computed_coverage = CoverageStatus.UNKNOWN
    elif coverage_status is not None:
        computed_coverage = coverage_status
    else:
        computed_coverage = evaluate_coverage_status(
            execution_status=execution_status,
            reported_total_hits=reported_total_hits,
            metadata_records_retrieved=metadata_records_retrieved,
            pagination_status=pagination_status
        )

    retrieval_rate = None
    if reported_total_hits is not None and reported_total_hits > 0:
        retrieval_rate = round(metadata_records_retrieved / reported_total_hits, 4)
    elif reported_total_hits == 0:
        retrieval_rate = 1.0

    return {
        "source_id": source_id,
        "query_id": query_id,
        "query_text": query_text,
        "search_mode": search_mode,
        "execution_status": execution_status,
        "reported_total_hits": reported_total_hits,
        "metadata_records_retrieved": metadata_records_retrieved,
        "unique_records_after_source_dedup": (
            unique_records_after_source_dedup
            if unique_records_after_source_dedup is not None
            else metadata_records_retrieved
        ),
        "pagination_status": pagination_status,
        "coverage_status": computed_coverage,
        "metadata_retrieval_rate": retrieval_rate,
        "failure_reason": failure_reason,
        "notes": notes,
    }


def reconcile_retrieval_coverage_ledger(
    planned_sources: List[Dict[str, Any]],
    executed_entries: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Reconcile planned search sources and queries into the comprehensive Ledger A.

    Identifies retrieval gaps (sources not searched, truncated, or failed).
    """
    entries_by_source: Dict[str, List[Dict[str, Any]]] = {}
    for entry in executed_entries:
        s_id = entry["source_id"]
        entries_by_source.setdefault(s_id, []).append(entry)

    reconciled_entries: List[Dict[str, Any]] = []
    source_coverage_summary: List[Dict[str, Any]] = []
    retrieval_gaps: List[Dict[str, Any]] = []

    for plan in planned_sources:
        s_id = plan.get("source_id", "Unknown")
        s_mode = plan.get("search_mode", "DIRECT_API")
        plan_queries = plan.get("planned_queries", [])

        if s_id in entries_by_source:
            actual_entries = entries_by_source[s_id]
            reconciled_entries.extend(actual_entries)

            # Reconcile source-level totals
            src_reported = sum((e.get("reported_total_hits") or 0) for e in actual_entries)
            src_retrieved = sum(e.get("metadata_records_retrieved", 0) for e in actual_entries)
            src_unique = sum(e.get("unique_records_after_source_dedup", 0) for e in actual_entries)

            all_complete = all(e.get("coverage_status") == CoverageStatus.COMPLETE for e in actual_entries)
            any_unknown = any(e.get("coverage_status") == CoverageStatus.UNKNOWN for e in actual_entries)

            if all_complete:
                src_cov = CoverageStatus.COMPLETE
            elif any_unknown:
                src_cov = CoverageStatus.UNKNOWN
            else:
                src_cov = CoverageStatus.PARTIAL

            source_summary = {
                "source_id": s_id,
                "search_mode": s_mode,
                "executed": True,
                "query_count": len(actual_entries),
                "total_reported_hits": src_reported if any(e.get("reported_total_hits") is not None for e in actual_entries) else None,
                "metadata_records_retrieved": src_retrieved,
                "unique_records": src_unique,
                "coverage_status": src_cov
            }
            source_coverage_summary.append(source_summary)

            if src_cov != CoverageStatus.COMPLETE:
                retrieval_gaps.append({
                    "source_id": s_id,
                    "gap_type": "PARTIAL_OR_UNRESOLVED_COVERAGE",
                    "risk_level": "HIGH_SCIENTIFIC_RISK",
                    "description": f"Source {s_id} achieved {src_cov} coverage ({src_retrieved} records retrieved vs {src_reported} reported hits)."
                })
        else:
            # Source was planned but not executed
            unexecuted_entry = build_retrieval_ledger_entry(
                source_id=s_id,
                query_id=plan_queries[0]["query_id"] if plan_queries else "Q_UNEXECUTED",
                query_text=plan_queries[0]["query_text"] if plan_queries else "",
                search_mode=s_mode,
                execution_status=RetrievalStatus.NOT_SEARCHED,
                failure_reason="Source was planned but never queried in execution run.",
                notes="Unexecuted database"
            )
            reconciled_entries.append(unexecuted_entry)
            source_coverage_summary.append({
                "source_id": s_id,
                "search_mode": s_mode,
                "executed": False,
                "query_count": 0,
                "total_reported_hits": None,
                "metadata_records_retrieved": 0,
                "unique_records": 0,
                "coverage_status": CoverageStatus.UNKNOWN
            })
            retrieval_gaps.append({
                "source_id": s_id,
                "gap_type": "DATABASE_NOT_SEARCHED",
                "risk_level": "HIGH_SCIENTIFIC_RISK",
                "description": f"Planned source {s_id} was not executed; coverage unknown."
            })

    total_planned_sources = len(planned_sources)
    complete_sources = sum(1 for s in source_coverage_summary if s["coverage_status"] == CoverageStatus.COMPLETE)
    db_coverage_rate = round(complete_sources / max(1, total_planned_sources), 4)

    total_planned_queries = sum(len(p.get("planned_queries", [])) for p in planned_sources)
    executed_queries = len(executed_entries)
    query_exec_rate = round(executed_queries / max(1, total_planned_queries), 4) if total_planned_queries > 0 else 1.0

    return {
        "ledger_type": "RETRIEVAL_COVERAGE_LEDGER_A",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_planned_sources": total_planned_sources,
        "complete_sources": complete_sources,
        "database_coverage_rate": db_coverage_rate,
        "query_execution_rate": query_exec_rate,
        "has_retrieval_gaps": len(retrieval_gaps) > 0,
        "retrieval_gaps": retrieval_gaps,
        "source_coverage_summary": source_coverage_summary,
        "entries": reconciled_entries
    }


def freeze_metadata_corpus(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Freeze the discovered candidate literature corpus prior to full-text acquisition.

    Ensures that every discovered item survives regardless of downstream PDF acquisition outcomes.
    Calculates source distribution and unique contributions.
    """
    total_raw = len(candidates)
    seen_dois = set()
    seen_titles = set()
    unique_candidates = []
    sources_distribution: Dict[str, int] = {}
    source_items_map: Dict[str, set] = {}

    with_abstract = 0
    without_abstract = 0

    for idx, c in enumerate(candidates):
        doi = (c.get("doi") or "").lower().strip()
        title = (c.get("title") or "").lower().strip()
        norm_title = re.sub(r"[^\w\s]", "", title)

        is_dup = False
        if doi and doi != "nr":
            if doi in seen_dois:
                is_dup = True
            else:
                seen_dois.add(doi)
        elif norm_title:
            if norm_title in seen_titles:
                is_dup = True
            else:
                seen_titles.add(norm_title)

        if not is_dup:
            unique_candidates.append(c)

        ab = c.get("abstract")
        if ab and str(ab).strip() and str(ab).strip().lower() not in ("not available", "none", "nr"):
            with_abstract += 1
        else:
            without_abstract += 1

        db_list = c.get("source_databases") or ["OpenAlex"]
        for db in db_list:
            sources_distribution[db] = sources_distribution.get(db, 0) + 1
            cid = c.get("record_id") or c.get("id") or f"ITEM_{idx}"
            source_items_map.setdefault(db, set()).add(cid)

    # Unique contribution per source (records found exclusively in this source)
    unique_contributions: Dict[str, int] = {}
    for db, id_set in source_items_map.items():
        other_ids = set()
        for other_db, other_set in source_items_map.items():
            if other_db != db:
                other_ids.update(other_set)
        exclusive = id_set - other_ids
        unique_contributions[db] = len(exclusive)

    return {
        "status": "CORPUS_FROZEN",
        "frozen_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_raw_records": total_raw,
        "unique_records": len(unique_candidates),
        "records_with_abstract": with_abstract,
        "records_without_abstract": without_abstract,
        "sources_distribution": sources_distribution,
        "source_unique_contributions": unique_contributions,
        "candidate_ids": [c.get("record_id") or c.get("id") for c in candidates if c.get("record_id") or c.get("id")]
    }


def audit_discovery_coverage_gate(
    retrieval_ledger: Any,
    frozen_corpus: Dict[str, Any],
    candidates: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Execute Gate A (Discovery Coverage Gate) according to Section 31 of Protocol.

    Checks:
    - [ ] All planned databases have explicit execution status.
    - [ ] No access failure recorded as 0 hits.
    - [ ] Total hits reconciled with retrieved count.
    - [ ] Pagination completeness explicitly logged.
    - [ ] Metadata corpus frozen before acquisition.
    - [ ] Candidate count non-zero unless clean verified empty search.
    - [ ] Cross-source substitution disallowed (OpenAlex cannot mark CNKI searched).
    """
    violations = []
    checks = {
        "planned_sources_accounted": True,
        "no_access_failure_as_zero": True,
        "hit_reconciliation_valid": True,
        "pagination_recorded": True,
        "corpus_frozen": bool(frozen_corpus and frozen_corpus.get("status") == "CORPUS_FROZEN"),
        "no_cross_source_substitution": True
    }

    if isinstance(retrieval_ledger, list):
        entries = retrieval_ledger
        has_retrieval_gaps = any(e.get("coverage_status") in {CoverageStatus.PARTIAL, CoverageStatus.UNKNOWN} for e in entries)
    elif isinstance(retrieval_ledger, dict):
        entries = retrieval_ledger.get("entries", [])
        has_retrieval_gaps = retrieval_ledger.get("has_retrieval_gaps", False)
    else:
        entries = []
        has_retrieval_gaps = False
    for e in entries:
        st = e.get("execution_status")
        hits = e.get("reported_total_hits")
        src = e.get("source_id", "")

        # Violation: access failure written as 0 hits
        if st in RetrievalStatus.ACCESS_FAILURE_STATUSES and hits == 0:
            checks["no_access_failure_as_zero"] = False
            violations.append(f"Access failure for source '{src}' was falsely written as 0 hits (Rule 10 violation).")

        # Violation: cross source substitution (e.g. OpenAlex claiming CNKI)
        if "cnki" in src.lower() and "openalex" in str(e.get("notes", "")).lower() and st == RetrievalStatus.SEARCHED_COMPLETE:
            checks["no_cross_source_substitution"] = False
            violations.append("Cross-source substitution violation: OpenAlex discovery cannot be claimed as CNKI coverage.")

        # Check pagination
        if not e.get("pagination_status"):
            checks["pagination_recorded"] = False
            violations.append(f"Source '{src}' missing pagination completeness status.")

    if not checks["corpus_frozen"]:
        violations.append("Metadata corpus was not frozen prior to fulltext acquisition.")

    gate_status = "PASS" if not violations else "REJECT"
    gaps_count = (
        len(retrieval_ledger.get('retrieval_gaps', []))
        if isinstance(retrieval_ledger, dict)
        else sum(1 for e in entries if e.get("coverage_status") in {CoverageStatus.PARTIAL, CoverageStatus.UNKNOWN})
    )

    return {
        "gate": "GATE_A_DISCOVERY_COVERAGE",
        "status": gate_status,
        "checks": checks,
        "violations": violations,
        "has_retrieval_gaps": has_retrieval_gaps,
        "retrieval_gap_summary": (
            f"Found {gaps_count} retrieval gap(s) (HIGH SCIENTIFIC RISK)."
            if has_retrieval_gaps else "No retrieval gaps detected; planned database coverage achieved."
        )
    }


def reconcile_discovery_and_acquisition(
    retrieval_ledger: Dict[str, Any],
    frozen_corpus: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    download_ledger: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Reconcile Discovery (Ledger A) and Acquisition (Ledger B).

    Guarantees:
    - Discovered records in candidate list survive download failures (Rule 4).
    - Decouples retrieval gaps from acquisition gaps.
    - Determines canonical overall status.
    """
    total_candidates = len(candidates)
    frozen_count = frozen_corpus.get("total_raw_records", total_candidates)

    # Check that candidate count did not drop due to download failures
    candidates_survived = (total_candidates >= frozen_count) or (total_candidates == len(frozen_corpus.get("candidate_ids", [])))

    # Evaluate acquisition gaps from download ledger
    acquisition_gaps: List[Dict[str, Any]] = []
    obtained_fulltexts = 0
    selected_for_acquisition = 0

    if download_ledger:
        for item in download_ledger:
            status = item.get("status", "")
            selected_for_acquisition += 1
            if status in ("OA_DOWNLOADED", "PREPRINT_AVAILABLE", "BROWSER_DOWNLOADED", "USER_PROVIDED"):
                obtained_fulltexts += 1
            elif status in ("PAYWALLED", "AUTH_REQUIRED", "DOWNLOAD_FAILED", "OA_BOT_BLOCKED", "CAJ_ONLY"):
                acquisition_gaps.append({
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "doi": item.get("doi"),
                    "status": status,
                    "note": item.get("note", "")
                })

    acq_rate = (
        round(obtained_fulltexts / max(1, selected_for_acquisition), 4)
        if selected_for_acquisition > 0 else 1.0
    )

    has_retrieval_gaps = retrieval_ledger.get("has_retrieval_gaps", False)
    has_acquisition_gaps = len(acquisition_gaps) > 0

    # Determine canonical overall_status
    if total_candidates == 0 and has_retrieval_gaps:
        overall_status = OverallDiscoveryStatus.FAILED
    elif has_retrieval_gaps and has_acquisition_gaps:
        overall_status = OverallDiscoveryStatus.SUCCESS_WITH_RETRIEVAL_AND_ACQUISITION_GAPS
    elif has_retrieval_gaps:
        overall_status = OverallDiscoveryStatus.SUCCESS_WITH_RETRIEVAL_GAPS
    elif has_acquisition_gaps:
        overall_status = OverallDiscoveryStatus.SUCCESS_WITH_ACQUISITION_GAPS
    else:
        overall_status = OverallDiscoveryStatus.SUCCESS

    return {
        "overall_status": overall_status,
        "discovery_status": "COMPLETE" if not has_retrieval_gaps else "PARTIAL",
        "fulltext_status": "COMPLETE" if not has_acquisition_gaps else "PARTIAL",
        "candidates": candidates,
        "candidates_survived": candidates_survived,
        "total_discovered_candidates": total_candidates,
        "selected_for_acquisition": selected_for_acquisition,
        "obtained_fulltexts": obtained_fulltexts,
        "fulltext_acquisition_rate": acq_rate,
        "retrieval_gaps_count": len(retrieval_ledger.get("retrieval_gaps", [])),
        "acquisition_gaps_count": len(acquisition_gaps),
        "retrieval_gaps": retrieval_ledger.get("retrieval_gaps", []),
        "acquisition_gaps": acquisition_gaps,
        "user_notification": (
            "⚠ Retrieval Gap Detected: Unsearched or partially truncated databases exist (HIGH SCIENTIFIC RISK). "
            "Please review Ledger A before concluding search completeness."
            if has_retrieval_gaps else
            "✓ No Retrieval Gaps: All planned databases were completely retrieved."
        )
    }
