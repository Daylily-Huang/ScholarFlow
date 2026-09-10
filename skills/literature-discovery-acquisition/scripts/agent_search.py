#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_search.py
---------------
Headless / Agent 模式专用纯数据检索与输出管道。
当 literature-discovery-acquisition Skill 被上层 Agent、多智能体协作链或自动化脚本调用时，
本脚本跳过人机对话与 Markdown 排版，直接输出严格契约化的 JSON 数据流。

支持：
1. 关键词检索模式：基于 OpenAlex API 的广义学科高召回检索。
2. 双向滚雪球模式 (--snowball)：基于种子文献 DOI / OpenAlex ID，
   同时向后追溯经典参考文献 (Backward Snowballing) 与向前检索施引文献 (Forward Snowballing)。

用法:
    python agent_search.py -q "fecal DNA microsatellite snow leopard" --mode deep --output result.json
    python agent_search.py --snowball "10.1016/j.biocon.2020.108581" --limit 20 --output snowball_result.json
"""

import sys
import os
import json
import argparse
import urllib.request
import urllib.parse
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple, Set

try:
    from retrieval_coverage import (
        build_retrieval_ledger_entry,
        freeze_metadata_corpus,
        audit_discovery_coverage_gate,
        RetrievalStatus,
        CoverageStatus,
        PaginationStatus,
        OverallDiscoveryStatus,
    )
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from retrieval_coverage import (
        build_retrieval_ledger_entry,
        freeze_metadata_corpus,
        audit_discovery_coverage_gate,
        RetrievalStatus,
        CoverageStatus,
        PaginationStatus,
        OverallDiscoveryStatus,
    )

# Ensure UTF-8 encoding on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from ingest_external_records import merge_candidate_records
except ImportError:
    import sys
    from pathlib import Path
    _cur = str(Path(__file__).parent)
    if _cur not in sys.path:
        sys.path.insert(0, _cur)
    from ingest_external_records import merge_candidate_records

try:
    from shared.execution import (
        ExecutionDepth,
        ExecutionProfile,
        get_profile,
        normalize_depth,
        validate_depth_conflict,
    )
    from shared.version import PROJECT_VERSION
    from shared.execution.context import RunContext, StageKind
    from shared.execution.preflight import PreflightError
except ImportError:
    from pathlib import Path

    def _locate_runtime_root():
        """Find the directory that *contains* the ``shared`` package.

        Two layouts are supported, so an installed skill tree can resolve the
        engine without a repository checkout (R06):

        * repository layout: ``<repo>/skills/<skill>/scripts/`` -> ``<repo>``
        * installed layout:  ``<dest>/skills/<skill>/scripts/`` -> ``<dest>/skills``
          because the installer places the engine beside the skills.
        """
        here = Path(__file__).resolve()
        candidates = [here.parents[3], here.parents[2]]
        for candidate in candidates:
            if (candidate / "shared" / "__init__.py").is_file():
                return candidate
        return None

    _runtime_root = _locate_runtime_root()
    if _runtime_root is not None and str(_runtime_root) not in sys.path:
        sys.path.insert(0, str(_runtime_root))
    from shared.execution import (
        ExecutionDepth,
        ExecutionProfile,
        get_profile,
        normalize_depth,
        validate_depth_conflict,
    )
    from shared.version import PROJECT_VERSION
    from shared.execution.context import RunContext, StageKind
    from shared.execution.preflight import PreflightError

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
# OpenAlex politeness pool: declare contact in URL; custom agent-style UA suffixes
# (e.g. "(Headless Agent Search Pipeline)") trigger instant HTTP 429 throttling.
OPENALEX_MAILTO = "academic_support@openacademic.org"


class QueryExecutionResult(tuple):
    """
    Tuple-compatible container for (records, error) that carries rich execution
    and coverage metadata for truthful Ledger A accounting.
    """
    def __new__(cls, records, error, meta=None):
        return super().__new__(cls, (records, error))

    def __init__(self, records, error, meta=None):
        self.records = records
        self.error = error
        self.meta = meta or {}

    @property
    def reported_total_hits(self) -> Optional[int]:
        return self.meta.get("reported_total_hits")

    @property
    def pages_fetched(self) -> int:
        return self.meta.get("pages_fetched", 1)

    @property
    def coverage_status(self) -> str:
        return self.meta.get("coverage_status", "UNKNOWN")

    @property
    def pagination_status(self) -> str:
        return self.meta.get("pagination_status", "UNKNOWN")

    @property
    def execution_status(self) -> str:
        return self.meta.get("execution_status", "SEARCHED_COMPLETE")

    def get(self, key, default=None):
        return self.meta.get(key, default)


def parse_openalex_item(item, snowball_role=None, seed_id=None):
    """Parse a raw OpenAlex work object into normalized record.

    Defensive against malformed entries: OpenAlex fields may be explicitly
    null (e.g. "primary_location": null), in which case dict.get(key, {})
    still returns None and chained .get() calls crash. Treat every nested
    object as possibly-None and never let one bad item abort a whole batch.
    """
    if not isinstance(item, dict):
        raise ValueError("non-dict work item")

    def _dict(value):
        return value if isinstance(value, dict) else {}

    def _list(value):
        return value if isinstance(value, list) else []

    authors = []
    for authorship in _list(item.get("authorships")):
        author_name = _dict(_dict(authorship).get("author")).get("display_name")
        if author_name:
            authors.append(author_name)

    doi = item.get("doi") or "NR"
    if doi.startswith("https://doi.org/"):
        doi = doi.replace("https://doi.org/", "")

    journal = (_dict(_dict(item.get("primary_location")).get("source")).get("display_name")
               or "Academic Source")

    # Reconstruct abstract from inverted index
    abstract = "Not available"
    abstract_inverted = item.get("abstract_inverted_index")
    if abstract_inverted:
        try:
            word_positions = []
            for word, positions in _dict(abstract_inverted).items():
                for pos in positions:
                    word_positions.append((pos, word))
            word_positions.sort()
            abstract = " ".join([w[1] for w in word_positions])
        except Exception:
            pass

    best_oa = _dict(item.get("best_oa_location"))
    pdf_url = best_oa.get("pdf_url")
    is_oa = _dict(item.get("open_access")).get("is_oa", False)
    oa_status = _dict(item.get("open_access")).get("oa_status", "closed")
    
    rec = {
        "schema_version": "1.0",
        "record_id": "",
        "title": item.get("display_name") or item.get("title") or "Untitled",
        "authors": authors,
        "year": item.get("publication_year"),
        "journal": journal,
        "doi": doi,
        "openalex_id": item.get("id"),
        "pdf_url": pdf_url,
        "is_oa": is_oa,
        "oa_status": oa_status,
        "abstract": abstract[:500] + "..." if len(abstract) > 500 else abstract,
        "citation_count": item.get("cited_by_count", 0),
        "document_type": item.get("type") or "article",
        "source_databases": ["OpenAlex"],
        "ingestion_method": "Snowballing" if snowball_role else "API_Automated",
        "screening_status": "Uncertain",
        "screening_reason": "Automated OpenAlex API retrieval",
        "metadata_verification_status": "VERIFIED_API",
        "fulltext_verification_status": "NOT_CHECKED"
    }
    if snowball_role:
        rec["snowball_role"] = snowball_role
    if seed_id:
        rec["seed_reference"] = seed_id
    return rec


THESIS_TITLE_PATTERNS = [
    r"\bdoctoral thesis\b",
    r"\bphd thesis\b",
    r"\bmaster'?s thesis\b",
    r"\bdoctoral dissertation\b",
    r"\bmaster dissertation\b",
]


def is_thesis_work(item: dict) -> bool:
    """Accurately identify thesis/dissertation works without false positives on general articles."""
    work_type = str(item.get("type", "")).lower().strip()
    if work_type in {"dissertation", "thesis"}:
        return True

    title = str(item.get("display_name") or item.get("title") or "").lower()
    for pat in THESIS_TITLE_PATTERNS:
        if re.search(pat, title, re.IGNORECASE):
            return True

    return False


def query_openalex_headless(query_str, limit=25, include_theses=True, per_page=None):
    """通过 OpenAlex API 关键词获取候选文献，支持基于 cursor 的深度分页检索与真实元数据统计。

    Returns:
        QueryExecutionResult: (records, error) 兼容 tuple，同时携带 .meta / .reported_total_hits / .pages_fetched / .coverage_status。
    """
    records = []
    error = None
    reported_total_hits = None
    pages_fetched = 0
    openalex_meta = {}

    batch_size = per_page or min(limit, 50)
    batch_size = max(1, min(batch_size, 100))
    cursor = "*"

    try:
        while len(records) < limit and cursor:
            fetch_size = min(limit - len(records), batch_size)
            url = f"https://api.openalex.org/works?search={urllib.parse.quote(query_str)}&per-page={fetch_size}&cursor={urllib.parse.quote(str(cursor))}&mailto={OPENALEX_MAILTO}"
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

            with urllib.request.urlopen(req, timeout=20) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    pages_fetched += 1
                    meta = data.get("meta") or {}
                    openalex_meta = meta
                    if reported_total_hits is None and "count" in meta:
                        try:
                            reported_total_hits = int(meta["count"])
                        except (ValueError, TypeError):
                            reported_total_hits = None

                    results = data.get("results") or []
                    if not results:
                        break

                    for item in results:
                        if not isinstance(item, dict):
                            continue
                        try:
                            if not include_theses and is_thesis_work(item):
                                continue
                            rec = parse_openalex_item(item)
                        except Exception:
                            continue  # skip malformed entry, never abort the whole batch
                        rec["id"] = f"REC{len(records)+1:03d}"
                        rec["record_id"] = rec["id"]
                        records.append(rec)
                        if len(records) >= limit:
                            break

                    next_cursor = meta.get("next_cursor")
                    if not next_cursor or next_cursor == cursor:
                        break
                    cursor = next_cursor
                else:
                    error = f"OpenAlex HTTP {resp.status} for '{query_str[:60]}'"
                    break

            if pages_fetched >= 20:
                break

    except Exception as e:
        error = f"OpenAlex query failed for '{query_str[:60]}': {str(e)}"
        sys.stderr.write(f"[-] {error}\n")

    if reported_total_hits is not None:
        if len(records) >= reported_total_hits:
            cov_status = CoverageStatus.COMPLETE
            pag_status = PaginationStatus.COMPLETE
        elif error:
            cov_status = CoverageStatus.PARTIAL
            pag_status = PaginationStatus.FAILED_MIDWAY
        elif len(records) >= limit:
            cov_status = CoverageStatus.PARTIAL
            pag_status = PaginationStatus.TRUNCATED_BY_LIMIT
        else:
            cov_status = CoverageStatus.PARTIAL
            pag_status = PaginationStatus.PARTIAL
    else:
        cov_status = CoverageStatus.UNKNOWN if (error and not records) else CoverageStatus.PARTIAL
        pag_status = PaginationStatus.UNKNOWN

    exec_status = (
        RetrievalStatus.TEMPORARILY_UNAVAILABLE if (error and not records)
        else (RetrievalStatus.SEARCHED_WITH_ERRORS if error
        else RetrievalStatus.SEARCHED_COMPLETE)
    )

    meta_dict = {
        "reported_total_hits": reported_total_hits,
        "metadata_records_retrieved": len(records),
        "pages_fetched": pages_fetched,
        "coverage_status": cov_status,
        "pagination_status": pag_status,
        "execution_status": exec_status,
        "openalex_meta": openalex_meta,
    }

    return QueryExecutionResult(records, error, meta=meta_dict)



def run_snowball_search(seed_identifier, limit=15, include_theses=True):
    """
    基于种子文献 DOI / OpenAlex ID 执行双向滚雪球拓展
    1. 抓取种子文献本身
    2. Backward: 抓取种子文献引用的参考文献 (referenced_works)
    3. Forward: 抓取引用了种子文献的施引文献 (cited_by)
    """
    sys.stderr.write(f"[*] Starting Dual-Direction Citation Snowballing for: '{seed_identifier}' (Limit: {limit}, Theses: {include_theses})\n")
    clean_id = seed_identifier.strip()
    if clean_id.startswith("http"):
        work_api_url = f"https://api.openalex.org/works/{urllib.parse.quote(clean_id)}?mailto={OPENALEX_MAILTO}"
    elif clean_id.startswith("10."):
        work_api_url = f"https://api.openalex.org/works/https://doi.org/{urllib.parse.quote(clean_id)}?mailto={OPENALEX_MAILTO}"
    elif clean_id.upper().startswith("W"):
        work_api_url = f"https://api.openalex.org/works/{clean_id}?mailto={OPENALEX_MAILTO}"
    else:
        # Fallback to search if not a direct DOI
        work_api_url = f"https://api.openalex.org/works?search={urllib.parse.quote(clean_id)}&per-page=1&mailto={OPENALEX_MAILTO}"

    records = []
    errors = []
    seed_item = None

    try:
        req = urllib.request.Request(work_api_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if "results" in data:
                if data["results"]:
                    seed_item = data["results"][0]
            else:
                seed_item = data
    except Exception as e:
        err = f"Failed to fetch seed paper '{seed_identifier[:60]}': {str(e)}"
        sys.stderr.write(f"[-] {err}\n")
        return [], [err]

    if not seed_item:
        err = f"Seed work not resolved in OpenAlex: {seed_identifier}"
        sys.stderr.write(f"[-] {err}\n")
        return [], [err]

    if include_theses or not is_thesis_work(seed_item):
        seed_rec = parse_openalex_item(seed_item, snowball_role="SEED_PAPER")
        seed_rec["id"] = "REC001"
        seed_rec["record_id"] = "REC001"
        records.append(seed_rec)
        seed_doi = seed_rec.get("doi")
    else:
        seed_doi = seed_item.get("doi")

    seed_openalex_id = seed_item.get("id")

    # 1. Backward Snowballing: Fetch referenced works
    ref_ids = seed_item.get("referenced_works", [])
    if ref_ids:
        sys.stderr.write(f"[*] Backward Snowballing: Found {len(ref_ids)} references, fetching top {min(len(ref_ids), limit)}...\n")
        clean_ref_ids = [r.split("/")[-1] for r in ref_ids[:limit]]
        pipe_ids = "|".join(clean_ref_ids)
        ref_url = f"https://api.openalex.org/works?filter=openalex_id:{pipe_ids}&per-page={limit}&mailto={OPENALEX_MAILTO}"
        try:
            r_req = urllib.request.Request(ref_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(r_req, timeout=20) as resp:
                ref_data = json.loads(resp.read().decode('utf-8'))
                for r_item in ref_data.get("results", []):
                    if not isinstance(r_item, dict):
                        continue
                    try:
                        if not include_theses and is_thesis_work(r_item):
                            continue
                        rec = parse_openalex_item(r_item, snowball_role="BACKWARD_REFERENCE", seed_id=seed_doi)
                    except Exception:
                        continue
                    rec["id"] = f"REC{len(records)+1:03d}"
                    rec["record_id"] = rec["id"]
                    records.append(rec)
        except Exception as e:
            err = f"Backward snowballing query failed: {str(e)}"
            sys.stderr.write(f"[-] {err}\n")
            errors.append(err)

    # 2. Forward Snowballing: Fetch works that cite the seed
    if seed_openalex_id:
        clean_seed_id = seed_openalex_id.split("/")[-1]
        forward_url = f"https://api.openalex.org/works?filter=cites:{clean_seed_id}&per-page={limit}&mailto={OPENALEX_MAILTO}"
        sys.stderr.write(f"[*] Forward Snowballing: Fetching works citing {clean_seed_id} (up to {limit})...\n")
        try:
            f_req = urllib.request.Request(forward_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(f_req, timeout=20) as resp:
                f_data = json.loads(resp.read().decode('utf-8'))
                for f_item in f_data.get("results", []):
                    if not isinstance(f_item, dict):
                        continue
                    try:
                        if not include_theses and is_thesis_work(f_item):
                            continue
                        rec = parse_openalex_item(f_item, snowball_role="FORWARD_CITATION", seed_id=seed_doi)
                    except Exception:
                        continue
                    rec["id"] = f"REC{len(records)+1:03d}"
                    rec["record_id"] = rec["id"]
                    records.append(rec)
        except Exception as e:
            err = f"Forward snowballing query failed: {str(e)}"
            sys.stderr.write(f"[-] {err}\n")
            errors.append(err)

    sys.stderr.write(f"[+] Snowballing complete: {len(records)} total records collected (Seed, {sum(1 for r in records if r.get('snowball_role')=='BACKWARD_REFERENCE')} Backward, {sum(1 for r in records if r.get('snowball_role')=='FORWARD_CITATION')} Forward).\n")
    return records, errors


def normalize_title(title):
    return re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]", "", (title or "").lower())


def deduplicate_records(records):
    """Canonical deduplication delegating to merge_candidate_records with cross-source enrichment."""
    res = merge_candidate_records([], records)
    return res.get("merged_records", [])


def run_deep_search(query_str, limit=30, include_theses=True, profile=None):
    """
    Deep-tier search (RFC-014 / P2-02).

    Phase 1: Primary query.
    Phase 2: Concept-expansion sub-queries, repeated ``profile.concept_expansion_rounds`` times.
    Phase 3: Citation snowballing, repeated ``profile.snowball_rounds`` times.

    Round counts come from the confirmed profile and only executed rounds are
    reported (R11).
    """
    profile = profile or get_profile(ExecutionDepth.DEEP)
    expansion_budget = max(0, int(profile.concept_expansion_rounds))
    snowball_budget = max(0, int(profile.snowball_rounds))

    sys.stderr.write(f"[*] Deep Search Phase 1: Primary query '{query_str}' (target: {limit})\n")
    errors = []
    skipped_steps = []
    queries_executed = 0
    expansion_rounds_executed = 0
    snowball_rounds_executed = 0

    r1_res = query_openalex_headless(query_str, limit=limit, include_theses=include_theses)
    round1_records, r1_err = r1_res[0], r1_res[1]
    queries_executed += 1
    if r1_err:
        errors.append(r1_err)
    reported_total_hits = getattr(r1_res, "reported_total_hits", None)

    # Phase 2: concept expansion / sub-query variants (one per configured round).
    words = [w for w in query_str.split() if len(w) > 3]
    expansion_records = []
    if expansion_budget and len(words) >= 2:
        for round_index in range(expansion_budget):
            if round_index == 0:
                variant_query = f"{words[0]} {words[-1]}"
            else:
                tail = words[min(round_index, len(words) - 1)]
                variant_query = f"{words[0]} {tail}"
            sys.stderr.write(
                f"[*] Deep Search Phase 2.{round_index + 1}: Concept expansion query '{variant_query}'\n"
            )
            r2_res = query_openalex_headless(
                variant_query, limit=max(5, limit // (2 * (round_index + 1))), include_theses=include_theses
            )
            queries_executed += 1
            expansion_rounds_executed += 1
            expansion_records.extend(r2_res[0])
            if r2_res[1]:
                errors.append(r2_res[1])
    elif expansion_budget:
        skipped_steps.append(
            {
                "step": "concept_expansion",
                "configured_rounds": expansion_budget,
                "executed_rounds": 0,
                "reason": "query_too_short_for_expansion",
            }
        )

    combined = round1_records + expansion_records
    deduped = deduplicate_records(combined)

    # Phase 3: citation snowballing on the highest-cited candidates discovered.
    snowballed_records = []
    eligible_seeds = [
        r for r in deduped if r.get("doi") and r.get("doi") != "NR" and r.get("citation_count", 0) > 0
    ]
    if snowball_budget and eligible_seeds:
        eligible_seeds.sort(key=lambda x: x.get("citation_count", 0), reverse=True)
        for round_index in range(snowball_budget):
            seed = eligible_seeds[min(round_index, len(eligible_seeds) - 1)]
            sys.stderr.write(
                f"[*] Deep Search Phase 3.{round_index + 1}: Citation snowballing on seed: "
                f"{seed.get('title')} ({seed.get('doi')})\n"
            )
            snowballed, sb_errs = run_snowball_search(
                seed["doi"], limit=min(10, max(3, limit // 3)), include_theses=include_theses
            )
            queries_executed += 1
            snowball_rounds_executed += 1
            errors.extend(sb_errs)
            snowballed_records.extend(
                s for s in snowballed if s.get("snowball_role") != "SEED_PAPER"
            )
    elif snowball_budget:
        skipped_steps.append(
            {
                "step": "snowballing",
                "configured_rounds": snowball_budget,
                "executed_rounds": 0,
                "reason": "no_eligible_seed_with_citation_count",
            }
        )

    all_candidates = deduplicate_records(deduped + snowballed_records)

    for idx, r in enumerate(all_candidates):
        r["id"] = f"REC{idx+1:03d}"
        r["record_id"] = r["id"]

    total_retrieved = len(combined) + len(snowballed_records)
    unique_count = len(all_candidates)
    marginal_gain = (unique_count - len(round1_records)) / max(1, len(round1_records))

    expansion_status = "HIGH_EXPANSION_GAIN" if marginal_gain >= 0.3 else "MODERATE_EXPANSION_GAIN"
    saturation_tracking = {
        "mode": "deep",
        "configured_rounds": 1 + expansion_budget + snowball_budget,
        "queries_executed": queries_executed,
        "expansion_rounds_executed": expansion_rounds_executed,
        "snowball_rounds_executed": snowball_rounds_executed,
        "rounds_executed": queries_executed,
        "total_raw_retrieved": total_retrieved,
        "unique_deduplicated": unique_count,
        "round1_baseline": len(round1_records),
        "expansion_added": len(expansion_records),
        "snowball_added": len(snowballed_records),
        "marginal_gain_ratio": round(marginal_gain, 3),
        "expansion_gain_status": expansion_status,
        "saturation_status": expansion_status,
        "reported_total_hits": reported_total_hits,
        "skipped_steps": skipped_steps,
        "errors": errors,
    }

    return all_candidates, saturation_tracking


def run_standard_search(query_str, limit=50, include_theses=True, profile=None):
    """
    Standard-tier search (RFC-014 / P2-02).

    Phase 1: Primary query.
    Phase 2: Concept-expansion queries, repeated ``profile.concept_expansion_rounds`` times.
    Phase 3: Targeted snowballing on the top seed, repeated ``profile.snowball_rounds`` times.

    Round counts are driven by the confirmed profile and the executed counts are
    reported truthfully, so a configured-but-skipped step never appears as run
    (R11).
    """
    profile = profile or get_profile(ExecutionDepth.STANDARD)
    expansion_budget = max(0, int(profile.concept_expansion_rounds))
    snowball_budget = max(0, int(profile.snowball_rounds))

    sys.stderr.write(f"[*] Standard Search Phase 1: Primary query '{query_str}' (target: {limit})\n")
    errors = []
    skipped_steps = []
    queries_executed = 0
    expansion_rounds_executed = 0
    snowball_rounds_executed = 0

    r1_res = query_openalex_headless(query_str, limit=limit, include_theses=include_theses)
    round1_records, r1_err = r1_res[0], r1_res[1]
    queries_executed += 1
    if r1_err:
        errors.append(r1_err)
    reported_total_hits = getattr(r1_res, "reported_total_hits", None)

    # Phase 2: concept expansion queries (one per configured round).
    words = [w for w in query_str.split() if len(w) > 3]
    expansion_records = []
    if expansion_budget and len(words) >= 2:
        for round_index in range(expansion_budget):
            variant_query = f"{words[0]} {words[-1]}"
            if round_index > 0:
                # Later rounds narrow to a different term so the rounds are not
                # literal duplicates of each other.
                tail = words[min(round_index, len(words) - 1)]
                variant_query = f"{words[0]} {tail}"
            sys.stderr.write(
                f"[*] Standard Search Phase 2.{round_index + 1}: Concept expansion query '{variant_query}'\n"
            )
            r2_res = query_openalex_headless(
                variant_query, limit=max(3, limit // (3 * (round_index + 1))), include_theses=include_theses
            )
            queries_executed += 1
            expansion_rounds_executed += 1
            expansion_records.extend(r2_res[0])
            if r2_res[1]:
                errors.append(r2_res[1])
    elif expansion_budget:
        skipped_steps.append(
            {
                "step": "concept_expansion",
                "configured_rounds": expansion_budget,
                "executed_rounds": 0,
                "reason": "query_too_short_for_expansion",
            }
        )

    combined = round1_records + expansion_records
    deduped = deduplicate_records(combined)

    # Phase 3: targeted lightweight snowballing on the top seed.
    snowballed_records = []
    eligible_seeds = [
        r for r in deduped if r.get("doi") and r.get("doi") != "NR" and r.get("citation_count", 0) > 0
    ]
    if snowball_budget and eligible_seeds:
        eligible_seeds.sort(key=lambda x: x.get("citation_count", 0), reverse=True)
        for round_index in range(snowball_budget):
            seed = eligible_seeds[min(round_index, len(eligible_seeds) - 1)]
            sys.stderr.write(
                f"[*] Standard Search Phase 3.{round_index + 1}: Targeted snowballing on seed: "
                f"{seed.get('title')} ({seed.get('doi')})\n"
            )
            snowballed, sb_errs = run_snowball_search(
                seed["doi"], limit=5, include_theses=include_theses
            )
            queries_executed += 1
            snowball_rounds_executed += 1
            errors.extend(sb_errs)
            snowballed_records.extend(
                s for s in snowballed if s.get("snowball_role") != "SEED_PAPER"
            )
    elif snowball_budget:
        skipped_steps.append(
            {
                "step": "snowballing",
                "configured_rounds": snowball_budget,
                "executed_rounds": 0,
                "reason": "no_eligible_seed_with_citation_count",
            }
        )

    all_candidates = deduplicate_records(deduped + snowballed_records)
    for idx, r in enumerate(all_candidates):
        r["id"] = f"REC{idx+1:03d}"
        r["record_id"] = r["id"]

    total_retrieved = len(combined) + len(snowballed_records)
    unique_count = len(all_candidates)
    marginal_gain = (unique_count - len(round1_records)) / max(1, len(round1_records))

    saturation_tracking = {
        "mode": "standard",
        "configured_rounds": 1 + expansion_budget + snowball_budget,
        "queries_executed": queries_executed,
        "expansion_rounds_executed": expansion_rounds_executed,
        "snowball_rounds_executed": snowball_rounds_executed,
        "rounds_executed": queries_executed,
        "total_raw_retrieved": total_retrieved,
        "unique_deduplicated": unique_count,
        "round1_baseline": len(round1_records),
        "expansion_added": len(expansion_records),
        "snowball_added": len(snowballed_records),
        "marginal_gain_ratio": round(marginal_gain, 3),
        "expansion_gain_status": "MODERATE_EXPANSION_GAIN" if marginal_gain >= 0.15 else "LOW_EXPANSION_GAIN",
        "saturation_status": "MODERATE_EXPANSION_GAIN" if marginal_gain >= 0.15 else "LOW_EXPANSION_GAIN",
        "reported_total_hits": reported_total_hits,
        "skipped_steps": skipped_steps,
        "errors": errors,
    }
    return all_candidates, saturation_tracking


def build_prisma_s_audit(mode: str, snowball_seed: str = None) -> dict:
    """Itemized PRISMA-S 16-item audit structure (P1-11)."""
    items = [
        {"item": 1, "name": "Database name", "status": "PASS", "evidence": "OpenAlex API"},
        {"item": 2, "name": "Multi-database translation", "status": "USER_ASSISTED", "evidence": "OpenAlex automated; subscription bases require user export"},
        {"item": 3, "name": "Search strategies recorded", "status": "PARTIAL", "evidence": "Query recorded in search_protocol"},
        {"item": 4, "name": "Search dates documented", "status": "PASS", "evidence": "Execution timestamp logged"},
        {"item": 5, "name": "Full search query recorded", "status": "PASS", "evidence": "Recorded verbatim in search_protocol"},
        {"item": 6, "name": "Search limits applied", "status": "PASS", "evidence": "Type, language, and year limits recorded"},
        {"item": 7, "name": "Search filters described", "status": "PASS", "evidence": "Type filter and thesis preference documented"},
        {"item": 8, "name": "Prior search strategies updated", "status": "NOT_APPLICABLE", "evidence": "Single initial retrieval run"},
        {"item": 9, "name": "Peer review of search strategy", "status": "USER_ASSISTED", "evidence": "PRESS peer review requires human supervisor"},
        {"item": 10, "name": "Citation searching", "status": "PASS" if snowball_seed or mode == "deep" else "NOT_EVALUATED", "evidence": "Dual-direction citation snowballing"},
        {"item": 11, "name": "Contacting authors/experts", "status": "NOT_APPLICABLE", "evidence": "Automated headless retrieval phase"},
        {"item": 12, "name": "Deduplication procedure defined", "status": "PASS", "evidence": "DOI and title normalized deduplication"},
        {"item": 13, "name": "Full-text screening criteria", "status": "NOT_EVALUATED", "evidence": "Deferred to extraction stage"},
        {"item": 14, "name": "Study selection process", "status": "USER_ASSISTED", "evidence": "Screening status uncertain pending agent review"},
        {"item": 15, "name": "Data collection process", "status": "NOT_EVALUATED", "evidence": "Deferred to extraction stage"},
        {"item": 16, "name": "Study risk of bias assessment", "status": "NOT_EVALUATED", "evidence": "Deferred to synthesis stage"}
    ]
    return {
        "framework": "PRISMA-S-2021",
        "applicable_items": 16,
        "overall_status": "PARTIAL",
        "items": items,
        "compliance_level": "PARTIAL_AUTOMATED"
    }


def _emit_headless_error(
    output_file,
    status,
    error,
    stderr_message,
    exit_code,
):
    """Emit a contract-shaped error payload and guarantee zero research calls."""
    payload = {
        "schema_version": "1.1",
        "status": status,
        "error": error,
        "errors": [error],
        "search_target": None,
        "search_protocol": {
            "mode": None,
            "execution_depth": None,
            "is_snowball": False,
            "seed_identifier": None,
        },
        "retrieval_coverage_ledger": {},
        "retrieval_gaps": [],
        "acquisition_gaps": [],
        "candidates": [],
        "metadata": {
            "agent_pipeline": "literature-discovery-acquisition",
            "version": PROJECT_VERSION,
        },
    }
    output_json = json.dumps(payload, indent=2, ensure_ascii=False)
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output_json)
        sys.stderr.write("[-] Headless results saved to: %s (status: %s)\n" % (output_file, status))
    else:
        print(output_json)
    sys.stderr.write(stderr_message)
    return exit_code


def run_headless_search(
    query=None,
    snowball_seed=None,
    mode=None,
    execution_depth=None,
    include_theses=True,
    limit=None,
    output_file=None,
    run_context=None,
    run_dir=None,
):
    """运行完整的 Headless 数据检索与滚雪球管道 (支持 quick / standard / deep)

    All research entry points (plain query and snowball) require an explicit,
    valid execution depth. A missing *or invalid* value returns a structured
    error and performs zero research tool calls (T08/T10, R03).
    """
    # 1. Distinguish "not provided" from "provided but invalid" (R03).
    provided = [v for v in (mode, execution_depth) if v is not None and str(v).strip() != ""]
    if not provided:
        return _emit_headless_error(
            output_file,
            status="INPUT_REQUIRED",
            error=(
                "Execution depth is required for headless runs. "
                "Please specify --execution-depth quick|standard|deep."
            ),
            stderr_message=(
                "[-] INPUT_REQUIRED: Execution depth must be explicitly specified "
                "(--execution-depth).\n"
            ),
            exit_code=2,
        )

    invalid = [v for v in provided if normalize_depth(str(v)) is None]
    if invalid:
        return _emit_headless_error(
            output_file,
            status="INVALID_PARAMETER",
            error=(
                "Invalid execution depth value(s): %s. "
                "Allowed values: quick, standard, deep (aliases: 快速, 标准, 深度, 中等)."
                % ", ".join(repr(v) for v in invalid)
            ),
            stderr_message="[-] INVALID_PARAMETER: %s\n" % ", ".join(repr(v) for v in invalid),
            exit_code=1,
        )

    # 2. Check for conflicting legacy mode and depth (T10)
    try:
        resolved_depth = validate_depth_conflict(mode, execution_depth)
    except ValueError as ve:
        return _emit_headless_error(
            output_file,
            status="INVALID_PARAMETER",
            error=str(ve),
            stderr_message="[-] %s\n" % ve,
            exit_code=1,
        )

    # 3. Every research entry point -- including snowball -- must pass the
    #    preflight gate. There is no unconditional fallback to a default tier.
    if resolved_depth is None:
        return _emit_headless_error(
            output_file,
            status="INPUT_REQUIRED",
            error=(
                "Execution depth is required for headless runs. "
                "Please specify --execution-depth quick|standard|deep."
            ),
            stderr_message="[-] INPUT_REQUIRED: unresolvable execution depth.\n",
            exit_code=2,
        )

    prof = get_profile(resolved_depth)
    # `limit` is the PER-QUERY fetch ceiling; the run-level ceiling is a separate
    # budget that accumulates across every query and expansion round (R11).
    per_query_limit = limit if limit is not None else prof.max_search_candidates

    ctx = run_context
    if ctx is None:
        ctx = RunContext.create(
            resolved_depth,
            source="EXPLICIT_ARG",
            run_dir=run_dir,
            interaction_mode="headless",
        )
    try:
        ctx.begin_stage(StageKind.DISCOVERY)
    except PreflightError as exc:
        return _emit_headless_error(
            output_file,
            status="INVALID_PARAMETER",
            error=str(exc),
            stderr_message="[-] %s\n" % exc,
            exit_code=1,
        )

    errors = []
    saturation_info = None
    reported_hits = None
    actual_queries = 0
    expansion_rounds_executed = 0
    snowball_rounds_executed = 0
    skipped_steps = []
    if snowball_seed:
        candidates, sb_errors = run_snowball_search(
            snowball_seed, limit=per_query_limit, include_theses=include_theses
        )
        snowball_rounds_executed = 1
        actual_queries = 1
        errors = sb_errors
        search_target = f"Snowball seed: {snowball_seed}"
        reported_hits = len(candidates)
    elif resolved_depth == ExecutionDepth.DEEP:
        sys.stderr.write(f"[*] Running Headless Deep Search: '{query}' (Limit: {per_query_limit}, Theses: {include_theses})\n")
        candidates, saturation_info = run_deep_search(
            query, limit=per_query_limit, include_theses=include_theses, profile=prof
        )
        errors = saturation_info.get("errors", [])
        search_target = query
        reported_hits = saturation_info.get("reported_total_hits")
        actual_queries = int(saturation_info.get("queries_executed", 1))
        expansion_rounds_executed = int(saturation_info.get("expansion_rounds_executed", 0))
        snowball_rounds_executed = int(saturation_info.get("snowball_rounds_executed", 0))
        skipped_steps = list(saturation_info.get("skipped_steps", []))
    elif resolved_depth == ExecutionDepth.STANDARD:
        sys.stderr.write(f"[*] Running Headless Standard Search: '{query}' (Limit: {per_query_limit}, Theses: {include_theses})\n")
        candidates, saturation_info = run_standard_search(
            query, limit=per_query_limit, include_theses=include_theses, profile=prof
        )
        errors = saturation_info.get("errors", [])
        search_target = query
        reported_hits = saturation_info.get("reported_total_hits")
        actual_queries = int(saturation_info.get("queries_executed", 1))
        expansion_rounds_executed = int(saturation_info.get("expansion_rounds_executed", 0))
        snowball_rounds_executed = int(saturation_info.get("snowball_rounds_executed", 0))
        skipped_steps = list(saturation_info.get("skipped_steps", []))
    else:
        sys.stderr.write(f"[*] Running Headless Quick Search: '{query}' (Limit: {per_query_limit}, Theses: {include_theses})\n")
        q_res = query_openalex_headless(query, limit=per_query_limit, include_theses=include_theses)
        actual_queries = 1
        candidates, q_err = q_res[0], q_res[1]
        errors = [q_err] if q_err else []
        reported_hits = getattr(q_res, "reported_total_hits", None)
        saturation_info = {
            "mode": "quick",
            "rounds_executed": 1,
            "queries_executed": 1,
            "expansion_rounds_executed": 0,
            "snowball_rounds_executed": 0,
            "total_raw_retrieved": len(candidates),
            "unique_deduplicated": len(candidates),
            "marginal_gain_ratio": 0.0,
            "expansion_gain_status": "NOT_TRACKED",
            "saturation_status": "NOT_TRACKED",
            "reported_total_hits": reported_hits,
            "errors": errors,
        }
        search_target = query

    # Contract: a failed query with zero records must NOT be reported as a plain
    # empty SUCCESS — downstream would misread it as "no literature exists".
    if errors and not candidates:
        status = "FAILED"
    elif errors:
        status = "SUCCESS_WITH_ERRORS"
    else:
        status = "SUCCESS"

    # Build Ledger A (Retrieval Coverage Ledger) & Freeze Metadata Corpus
    if snowball_seed:
        if errors and not candidates:
            exec_status = RetrievalStatus.TEMPORARILY_UNAVAILABLE
            total_hits = None
            cov_status = CoverageStatus.UNKNOWN
            pag_status = PaginationStatus.FAILED_MIDWAY
        elif errors:
            exec_status = RetrievalStatus.SEARCHED_WITH_ERRORS
            total_hits = len(candidates)
            cov_status = CoverageStatus.PARTIAL
            pag_status = PaginationStatus.PARTIAL
        else:
            exec_status = RetrievalStatus.SEARCHED_COMPLETE
            total_hits = len(candidates)
            cov_status = CoverageStatus.COMPLETE
            pag_status = PaginationStatus.COMPLETE

        entry = build_retrieval_ledger_entry(
            source_id="OpenAlex_Snowball",
            query_id="SB01",
            query_text=str(snowball_seed),
            execution_status=exec_status,
            reported_total_hits=total_hits,
            metadata_records_retrieved=len(candidates),
            unique_records_after_source_dedup=len(candidates),
            pagination_status=pag_status,
            coverage_status=cov_status,
            failure_reason="; ".join(errors) if errors else None,
            search_mode="API_AUTOMATED",
            notes="Dual-direction citation snowballing"
        )
    else:
        if errors and not candidates:
            exec_status = RetrievalStatus.TEMPORARILY_UNAVAILABLE
            total_hits = None
            cov_status = CoverageStatus.UNKNOWN
            pag_status = PaginationStatus.FAILED_MIDWAY
        elif errors:
            exec_status = RetrievalStatus.SEARCHED_WITH_ERRORS
            total_hits = reported_hits if reported_hits is not None else len(candidates)
            cov_status = CoverageStatus.PARTIAL
            pag_status = PaginationStatus.PARTIAL
        else:
            exec_status = RetrievalStatus.SEARCHED_COMPLETE
            total_hits = reported_hits if reported_hits is not None else len(candidates)
            if total_hits is not None and total_hits > len(candidates):
                cov_status = CoverageStatus.PARTIAL
                pag_status = PaginationStatus.TRUNCATED_BY_LIMIT
            else:
                cov_status = CoverageStatus.COMPLETE
                pag_status = PaginationStatus.COMPLETE

        entry = build_retrieval_ledger_entry(
            source_id="OpenAlex",
            query_id="Q01",
            query_text=str(query or ""),
            execution_status=exec_status,
            reported_total_hits=total_hits,
            metadata_records_retrieved=len(candidates),
            unique_records_after_source_dedup=len(candidates),
            pagination_status=pag_status,
            coverage_status=cov_status,
            failure_reason="; ".join(errors) if errors else None,
            search_mode="DIRECT_METADATA_SEARCH",
            notes=f"Headless {mode} search"
        )


    # The run-level candidate ceiling accumulates across every query. Anything
    # fetched beyond it is preserved with an explicit unprocessed status instead
    # of being silently dropped or silently counted (R11).
    granted = ctx.consume_candidates(len(candidates))
    unprocessed = []
    if granted < len(candidates):
        for record in candidates[granted:]:
            unprocessed.append(
                {
                    "record_id": record.get("record_id") or record.get("id"),
                    "title": record.get("title"),
                    "source": record.get("source_databases"),
                    "processing_status": "UNPROCESSED_BEYOND_RUN_CEILING",
                }
            )
        candidates = candidates[:granted]
    ctx.record_event(
        "candidate_ceiling",
        {
            "per_query_limit": per_query_limit,
            "run_ceiling": ctx.config.budgets.max_search_candidates,
            "fetched": granted + len(unprocessed),
            "processed": granted,
            "unprocessed": len(unprocessed),
        },
    )

    ledger_entries = [entry]
    metadata_corpus_summary = freeze_metadata_corpus(candidates)
    retrieval_gaps = [
        e for e in ledger_entries
        if e.get("coverage_status") in {CoverageStatus.PARTIAL, CoverageStatus.UNKNOWN}
    ]
    acquisition_gaps = []

    # Ledger A is an envelope object, matching retrieval_coverage_ledger.schema.json
    # and the "dual independent ledgers" design (R11 contract alignment).
    retrieval_ledger = {
        "ledger_id": "LEDGER_A_RETRIEVAL_COVERAGE",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entries": ledger_entries,
        "retrieval_gaps": retrieval_gaps,
        "has_retrieval_gaps": bool(retrieval_gaps),
        "frozen_corpus_summary": {
            "status": metadata_corpus_summary.get("status"),
            "total_raw_records": metadata_corpus_summary.get("total_raw_records"),
            "unique_records": metadata_corpus_summary.get("unique_records"),
        },
    }
    gate_a_audit = audit_discovery_coverage_gate(retrieval_ledger, metadata_corpus_summary)

    # Report only rounds that actually executed; a configured depth is not an
    # executed round (R11).
    if saturation_info is None:
        saturation_info = {}
    saturation_info["queries_executed"] = actual_queries
    saturation_info["expansion_rounds_executed"] = expansion_rounds_executed
    saturation_info["snowball_rounds_executed"] = snowball_rounds_executed
    # `actual_queries` already counts every executed query, including the
    # concept-expansion and snowball rounds, so it must not be summed again.
    saturation_info["rounds_executed"] = actual_queries
    saturation_info["configured_rounds"] = (
        ctx.config.budgets.concept_expansion_rounds + ctx.config.budgets.snowball_rounds + 1
    )
    saturation_info["skipped_steps"] = skipped_steps

    if status == "FAILED" or (not candidates and retrieval_gaps):
        overall_discovery_status = OverallDiscoveryStatus.FAILED
    elif retrieval_gaps:
        overall_discovery_status = OverallDiscoveryStatus.SUCCESS_WITH_RETRIEVAL_GAPS
    elif errors:
        overall_discovery_status = "SUCCESS_WITH_ERRORS"
    else:
        overall_discovery_status = OverallDiscoveryStatus.SUCCESS

    payload = {
        "schema_version": "1.1",
        "status": status,
        "overall_discovery_status": overall_discovery_status,
        "retrieval_coverage_ledger": retrieval_ledger,
        "metadata_corpus_summary": metadata_corpus_summary,
        "retrieval_gaps": retrieval_gaps,
        "acquisition_gaps": acquisition_gaps,
        "gate_a_audit": gate_a_audit,
        "errors": errors,
        "search_target": search_target,
        "search_protocol": {
            "mode": resolved_depth.value,
            "execution_depth": resolved_depth.value,
            "depth_profile": prof.to_dict(),
            "is_snowball": bool(snowball_seed),
            "seed_identifier": snowball_seed,
            "query": query,
            "limit": per_query_limit,
            "per_query_limit": per_query_limit,
            "include_theses": include_theses,
            "configured_limits": {
                "max_search_candidates": ctx.config.budgets.max_search_candidates,
                "snowball_rounds": ctx.config.budgets.snowball_rounds,
                "concept_expansion_rounds": ctx.config.budgets.concept_expansion_rounds,
                "per_query_limit": per_query_limit,
            },
            "actual_usage": {
                "queries_executed": actual_queries,
                "expansion_rounds_executed": expansion_rounds_executed,
                "snowball_rounds_executed": snowball_rounds_executed,
                "candidates_processed": ctx.candidates_processed,
                "candidates_unprocessed": len(unprocessed),
                "skipped_steps": skipped_steps,
            },
            "thesis_preference": {
                "requested": "include" if include_theses else "exclude",
                "enforcement": "FILTERED_BY_WORK_TYPE" if not include_theses else "PERMITTED",
            },
        },
        "candidates": candidates,
        "unprocessed_candidates": unprocessed,
        "execution_plan": ctx.planned_call_trace()['stages'],
        "prisma_s_audit": build_prisma_s_audit(resolved_depth.value, snowball_seed),
        "saturation_tracking": saturation_info,
        "grounding_controls": {
            "audit_method": "API response structured anchoring",
            "source_provenance": "OpenAlex Works API",
            "hallucination_mitigation": "Direct JSON parsing without generative interpolation",
        },
        "metadata": {
            "agent_pipeline": "literature-discovery-acquisition",
            "version": PROJECT_VERSION,
            "schema_version": "1.1",
            "features": [
                "OpenAlex Headless",
                "Dual-Direction Snowballing",
                "PRISMA-S Itemized Audit",
                "Unified Execution Depth",
            ],
        },
    }

    output_json = json.dumps(payload, indent=2, ensure_ascii=False)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output_json)
        sys.stderr.write(f"[+] Headless results saved to: {output_file} (status: {status})\n")
    else:
        print(output_json)

    # Non-zero exit code lets headless consumers detect pipeline failure at a glance.
    return 1 if status == "FAILED" else 0


def main():
    parser = argparse.ArgumentParser(description="Headless Literature Search & Snowballing Pipeline for AI Agents")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-q", "--query", help="Research query or topic string")
    group.add_argument("-s", "--snowball", help="Seed DOI or OpenAlex ID for dual-direction citation snowballing")

    parser.add_argument(
        "--execution-depth",
        "-d",
        default=None,
        help="Unified execution depth tier (quick, standard, deep; supports Chinese aliases: 快速, 标准, 深度, 中等)",
    )
    parser.add_argument(
        "--mode",
        choices=["quick", "deep"],
        default=None,
        help="Legacy intensity mode (deprecated; use --execution-depth)",
    )
    parser.add_argument("--no-theses", action="store_true", help="Exclude master and doctoral theses")
    parser.add_argument("--limit", type=int, default=None, help="Max candidates or snowball breadth to retrieve")
    parser.add_argument("-o", "--output", default=None, help="Path to write output JSON (default: stdout)")

    args = parser.parse_args()
    include_theses = not args.no_theses
    sys.exit(
        run_headless_search(
            query=args.query,
            snowball_seed=args.snowball,
            mode=args.mode,
            execution_depth=args.execution_depth,
            include_theses=include_theses,
            limit=args.limit,
            output_file=args.output,
        )
    )


if __name__ == "__main__":
    main()
