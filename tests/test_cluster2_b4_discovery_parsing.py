# -*- coding: utf-8 -*-
"""Cluster-2 round-2, batch B4 regression tests (discovery parsing family).

Fixes under test (panel consensus CONSENSUS.md, 决议表 H-18/23/24/25/26/27/60):
- H-24  CNKI colon-format multi-record fusion (record-boundary block splitting);
- H-25  encoding robustness (gb18030 fallback, U+FFFD lossy counting, 0-record
        WARNING for space-separated export variants);
- H-26  RIS variant parsing (lowercase tags) + explicit 0-record WARNING;
- H-23  unified `_norm_doi` (placeholder list, prefix/trailing-punctuation/
        percent-encoding/case normalization) + openalex_id/title-hash identity
        fallback in generate_record_id (new records only, no retro migration);
- H-18  CJK concept-expansion word filter counts characters (>=2 CJK chars
        qualify), English behaviour unchanged;
- H-27  kappa gate independence (IDENTICAL_SOURCES rc=1) and reviewer
        coverage (coverage_warning, non-PASS status, no blocking);
- H-60  PRISMA-S item 6 PASS -> NOT_APPLICABLE with disclosure.

Attack fixtures are ported from the verifier report:
端到端真实跑/20260913-e2e-cluster2/02-discovery/verifier/REPORT.md (§2/§3/§4/§6).
"""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

import helpers  # noqa: F401  (sys.path bootstrap)

import agent_search as ags  # type: ignore
import calculate_screening_agreement as csa  # type: ignore
import ingest_external_records as ing  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[1]
KAPPA_SCRIPT = (
    REPO_ROOT / "skills" / "literature-discovery-acquisition" / "scripts"
    / "calculate_screening_agreement.py"
)

# ---------------------------------------------------------------------------
# Ported verifier fixtures (02-discovery/verifier/fixtures/ingest/*)
# ---------------------------------------------------------------------------

CNKI_COLON_UTF8 = (
    "RT: 期刊论文\r\n"
    "T1: 微塑料对大型溞的毒性效应研究\r\n"
    "A1: 张三;李四\r\n"
    "YR: 2021\r\n"
    "JF: 生态学报\r\n"
    "DOI: 10.5555/colon.1\r\n"
    "\r\n"
    "RT: 学位论文\r\n"
    "T1: 纳米塑料水生毒理学综述\r\n"
    "A1: 王五\r\n"
    "YR: 2022\r\n"
)

CNKI_COLON_GBK_BYTES = CNKI_COLON_UTF8.replace("\r\n", "\n").encode("gb18030")

CNKI_SPACE_UTF8 = (
    "RT 期刊论文\r\n"
    "T1 微塑料对大型溞的毒性效应研究\r\n"
    "A1 张三;李四\r\n"
    "YR 2021\r\n"
    "JF 生态学报\r\n"
    "DOI 10.5555/space.1\r\n"
    "\r\n"
    "RT 学位论文\r\n"
    "T1 纳米塑料水生毒理学综述\r\n"
    "A1 王五\r\n"
    "YR 2022\r\n"
)

GBK_CHINESE_CSV_BYTES = (
    "Title,Authors,Year,Journal,DOI\r\n"
    "微塑料对水蚤行为的影响,张三;李四,2021,生态学报,10.5555/gbk.1\r\n"
    "另一种纳米颗粒毒性研究,王五,2022,环境科学,10.5555/gbk.2\r\n"
).encode("gb18030")

LOWERCASE_RIS = (
    "ty  - JOUR\r\n"
    "ti  - Lowercase tag study\r\n"
    "au  - X, Y\r\n"
    "py  - 2020\r\n"
    "do  - 10.5555/lc.1\r\n"
    "er  - \r\n"
)

# 0xFF is not a valid lead byte in gb18030 either -> replacement chars survive
TRULY_BROKEN_CSV_BYTES = (
    b"Title,Authors,Year,DOI\r\n"
    b"\xff\xfe Broken \xff Paper,Auth,2021,\r\n"
)


def _write(tmp, name, data):
    """Write bytes or str into tmp dir, return Path."""
    p = Path(tmp) / name
    if isinstance(data, bytes):
        p.write_bytes(data)
    else:
        p.write_text(data, encoding="utf-8")
    return p


class _DiagnosticsReset(unittest.TestCase):
    def setUp(self):
        ing.reset_ingest_diagnostics()

    def tearDown(self):
        ing.reset_ingest_diagnostics()


# ---------------------------------------------------------------------------
# H-24: CNKI colon-format multi-record fusion
# ---------------------------------------------------------------------------

class TestH24CnkiRecordFusion(_DiagnosticsReset):
    def test_colon_format_two_records_not_fused(self):
        """DIS-V-11: two 'RT:/T1:' records must stay two independent records."""
        recs = ing.parse_cnki_refworks(CNKI_COLON_UTF8)
        self.assertEqual(len(recs), 2)
        first, second = recs
        # Field attribution must be per-record (no cross-contamination).
        self.assertEqual(first["title"], "微塑料对大型溞的毒性效应研究")
        self.assertEqual(first["doi"], "10.5555/colon.1")
        self.assertEqual(first["document_type"], "Journal Article")
        self.assertEqual(first["authors"], ["张三", "李四"])
        self.assertEqual(first["year"], 2021)
        self.assertEqual(second["title"], "纳米塑料水生毒理学综述")
        self.assertNotIn("微塑料", second["title"])
        self.assertEqual(second["document_type"], "Thesis")
        self.assertEqual(second["authors"], ["王五"])
        self.assertEqual(second["year"], 2022)

    def test_colon_gbk_record_count_and_fields(self):
        """GBK-encoded colon export: fallback decode + per-record parsing."""
        with tempfile.TemporaryDirectory() as td:
            p = _write(td, "cnki_colon_gbk.txt", CNKI_COLON_GBK_BYTES)
            recs = ing.detect_and_parse_file(p)
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["title"], "微塑料对大型溞的毒性效应研究")
        self.assertEqual(recs[1]["title"], "纳米塑料水生毒理学综述")
        self.assertNotIn("\ufffd", recs[0]["title"] + recs[1]["title"])

    def test_dash_format_regression_two_records(self):
        """Legacy dash-format CNKI Refworks keeps parsing both records."""
        content = (helpers.FIXTURES / "sample_cnki_refworks.txt").read_text(
            encoding="utf-8"
        )
        recs = ing.parse_cnki_refworks(content)
        self.assertEqual(len(recs), 2)
        self.assertEqual({r["document_type"] for r in recs},
                         {"Journal Article", "Thesis"})

    def test_record_without_rt_marker_on_second_record(self):
        """Belt-and-braces: repeated T1 line inside one block is a boundary."""
        content = (
            "RT: 期刊论文\n"
            "T1: 标题甲的研究\n"
            "A1: 张三\n"
            "YR: 2021\n"
            "T1: 标题乙的研究\n"
            "A1: 李四\n"
            "YR: 2022\n"
        )
        recs = ing.parse_cnki_refworks(content)
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["title"], "标题甲的研究")
        self.assertEqual(recs[1]["title"], "标题乙的研究")
        self.assertEqual(recs[0]["authors"], ["张三"])
        self.assertEqual(recs[1]["authors"], ["李四"])


# ---------------------------------------------------------------------------
# H-25: encoding robustness
# ---------------------------------------------------------------------------

class TestH25EncodingRobustness(_DiagnosticsReset):
    def test_gbk_csv_fallback_decodes_cleanly(self):
        """DIS-V-12: GBK CSV must decode via gb18030 without mojibake."""
        with tempfile.TemporaryDirectory() as td:
            p = _write(td, "gbk_chinese.csv", GBK_CHINESE_CSV_BYTES)
            recs = ing.parse_csv_tsv(p)
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["title"], "微塑料对水蚤行为的影响")
        self.assertEqual(recs[1]["title"], "另一种纳米颗粒毒性研究")
        self.assertEqual(recs[0]["authors"], ["张三", "李四"])
        self.assertEqual(recs[0]["doi"], "10.5555/gbk.1")
        self.assertNotIn("\ufffd", recs[0]["title"])
        self.assertNotIn("encoding_lossy", recs[0])

    def test_residual_replacement_chars_counted_and_flagged(self):
        """Bytes invalid in utf-8 AND gb18030: counted, flagged, never silent."""
        with tempfile.TemporaryDirectory() as td:
            p = _write(td, "broken.csv", TRULY_BROKEN_CSV_BYTES)
            recs = ing.parse_csv_tsv(p)
        self.assertEqual(len(recs), 1)
        rec = recs[0]
        self.assertIn("\ufffd", rec["title"])
        self.assertIs(rec.get("encoding_lossy"), True)
        self.assertIn("title", rec.get("encoding_lossy_fields", []))
        diag = ing.get_ingest_diagnostics()
        self.assertEqual(diag["encoding_lossy_count"], 1)
        self.assertIn("broken.csv", diag["encoding_lossy_files"])

    def test_utf8_clean_file_not_flagged(self):
        recs = ing.parse_cnki_refworks(
            (helpers.FIXTURES / "sample_cnki_refworks.txt").read_text(encoding="utf-8")
        )
        self.assertEqual(len(recs), 2)
        self.assertEqual(ing.get_ingest_diagnostics()["encoding_lossy_count"], 0)
        self.assertNotIn("encoding_lossy", recs[0])

    def test_space_format_zero_records_warning(self):
        """DIS-V-10: space-separated CNKI export parses 0 records with WARNING."""
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as td:
            p = _write(td, "cnki_space_utf8.txt", CNKI_SPACE_UTF8)
            with contextlib.redirect_stderr(stderr):
                recs = ing.detect_and_parse_file(p)
        self.assertEqual(recs, [])
        out = stderr.getvalue()
        self.assertIn("[WARNING]", out)
        self.assertIn("cnki_space_utf8.txt", out)
        self.assertIn("0 records", out)
        self.assertTrue(ing.get_ingest_diagnostics()["warnings"])

    def test_rc_semantics_preserved_for_zero_record_parse(self):
        """A clean 0-record parse returns [] — no exception, no blocking."""
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as td:
            p = _write(td, "space_only.txt", CNKI_SPACE_UTF8)
            with contextlib.redirect_stderr(stderr):
                recs = ing.ingest_file(p)
        self.assertEqual(recs, [])

    def test_empty_file_does_not_warn(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as td:
            p = _write(td, "empty.ris", "")
            with contextlib.redirect_stderr(stderr):
                recs = ing.detect_and_parse_file(p)
        self.assertEqual(recs, [])
        self.assertNotIn("[WARNING]", stderr.getvalue())
        self.assertEqual(ing.get_ingest_diagnostics()["warnings"], [])

    def test_main_writes_ingest_report_sidecar(self):
        """encoding_lossy_count lands in the sidecar artifact (not silent)."""
        with tempfile.TemporaryDirectory() as td:
            src = _write(td, "broken.csv", TRULY_BROKEN_CSV_BYTES)
            out = Path(td) / "out.json"
            argv = ["ingest", "-i", str(src), "-o", str(out)]
            with unittest.mock.patch.object(sys, "argv", argv):
                with contextlib.redirect_stderr(io.StringIO()):
                    ing.main()
            records = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(len(records), 1)
            sidecar = Path(td) / "out.ingest_report.json"
            self.assertTrue(sidecar.exists())
            report = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(report["encoding_lossy_count"], 1)
            self.assertIn("broken.csv", report["encoding_lossy_files"])

    def test_main_no_sidecar_for_clean_input(self):
        with tempfile.TemporaryDirectory() as td:
            src = _write(td, "cnki_colon_utf8.txt", CNKI_COLON_UTF8)
            out = Path(td) / "clean.json"
            argv = ["ingest", "-i", str(src), "-o", str(out)]
            with unittest.mock.patch.object(sys, "argv", argv):
                ing.main()
            records = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(len(records), 2)
            self.assertFalse((Path(td) / "clean.ingest_report.json").exists())


# ---------------------------------------------------------------------------
# H-26: RIS variant parsing
# ---------------------------------------------------------------------------

class TestH26RisVariant(_DiagnosticsReset):
    def test_lowercase_ris_tags_parse(self):
        """DIS-V-14: lowercase-tag RIS must parse >0 records."""
        with tempfile.TemporaryDirectory() as td:
            p = _write(td, "lowercase_tags.ris", LOWERCASE_RIS)
            recs = ing.detect_and_parse_file(p)
        self.assertEqual(len(recs), 1)
        rec = recs[0]
        self.assertEqual(rec["title"], "Lowercase tag study")
        self.assertEqual(rec["doi"], "10.5555/lc.1")
        self.assertEqual(rec["year"], 2020)
        self.assertEqual(rec["authors"], ["X, Y"])
        self.assertEqual(rec["ingestion_method"], "RIS_Import")

    def test_uppercase_ris_regression(self):
        recs = ing.parse_ris(
            (helpers.FIXTURES / "sample.ris").read_text(encoding="utf-8")
        )
        self.assertEqual(len(recs), 2)
        journal = next(r for r in recs if r["document_type"] == "Journal Article")
        self.assertEqual(journal["doi"], "10.1000/fake-doi-001")

    def test_zero_record_path_warns_for_nonempty_ris(self):
        """Comments-only RIS: clean EMPTY rc but explicit WARNING (H-26)."""
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as td:
            p = _write(td, "comments_only.ris", "# just a comment line\n")
            with contextlib.redirect_stderr(stderr):
                recs = ing.detect_and_parse_file(p)
        self.assertEqual(recs, [])
        self.assertIn("[WARNING]", stderr.getvalue())


# ---------------------------------------------------------------------------
# H-23: unified _norm_doi / identity keys
# ---------------------------------------------------------------------------

def _rec(title, doi=None, extra=None):
    r = {
        "title": title, "authors": ["A. Author"], "year": 2020, "journal": "J",
        "doi": doi if doi is not None else "NR",
        "source_databases": ["OpenAlex"], "abstract": None, "keywords": [],
    }
    if extra:
        r.update(extra)
    return r


class TestH23DoiNormalization(unittest.TestCase):
    def test_placeholder_dois_never_become_keys(self):
        for placeholder in ["N/A", "n/a", "N.A.", "NR", "", None, "12345",
                            "99999", ".,;", "-", "none"]:
            self.assertIsNone(ing._norm_doi(placeholder),
                              f"placeholder {placeholder!r} must not key")

    def test_url_prefix_trailing_punct_case_variants_unify(self):
        variants = [
            "https://doi.org/10.1000/Abc.",
            "https://dx.doi.org/10.1000/abc",
            "doi:10.1000/ABC.",
            "10.1000/abc;",
            " 10.1000/abc ",
        ]
        norms = {ing._norm_doi(v) for v in variants}
        self.assertEqual(norms, {"10.1000/abc"})

    def test_percent_encoding_unified(self):
        self.assertEqual(ing._norm_doi("10.1000/a%2Fb"), "10.1000/a/b")
        self.assertEqual(ing._norm_doi("10.1000/first%20part"),
                         "10.1000/first part")
        self.assertEqual(ing._norm_doi("10.1000/x%79z"), "10.1000/xyz")

    def test_doi_variants_merge_across_titles(self):
        """DIS-V-09: trailing-period DOI merges even with isolated titles."""
        m = ing.merge_candidate_records(
            [], [_rec("Study Alpha about X", "10.1000/abc."),
                 _rec("Study Beta about Y", "10.1000/abc")]
        )
        self.assertEqual(m["unique_count"], 1)

    def test_placeholder_doi_distinct_titles_not_merged(self):
        """DIS-V-06/07: 'N/A' and pure-numeric pseudo DOIs never merge works."""
        m = ing.merge_candidate_records(
            [], [_rec("Alpha distinct study", "N/A"),
                 _rec("Beta distinct study", "n/a")]
        )
        self.assertEqual(m["unique_count"], 2)
        m = ing.merge_candidate_records(
            [], [_rec("Numeric DOI one", "12345"),
                 _rec("Numeric DOI two", "12345")]
        )
        self.assertEqual(m["unique_count"], 2)

    def test_same_title_placeholder_still_merges_by_title(self):
        m = ing.merge_candidate_records(
            [], [_rec("Same title placeholder A", "N/A"),
                 _rec("Same title placeholder A", "N/A")]
        )
        self.assertEqual(m["unique_count"], 1)

    def test_record_id_no_collision_on_placeholder_doi(self):
        """DIS-V-08: distinct works with N/A DOIs get distinct record_ids."""
        r1 = ing.generate_record_id(
            {"title": "First distinct paper about A", "doi": "N/A",
             "authors": ["X"], "year": 2020}
        )
        r2 = ing.generate_record_id(
            {"title": "Second distinct paper about B", "doi": "n/a",
             "authors": ["X"], "year": 2020}
        )
        self.assertNotEqual(r1, r2)

    def test_record_id_unifies_doi_variants(self):
        """DIS-V-08: URL-prefixed and bare DOI share one identity."""
        r_url = ing.generate_record_id(
            {"title": "URL form", "doi": "https://doi.org/10.1000/xyz",
             "authors": [], "year": 2020}
        )
        r_bare = ing.generate_record_id(
            {"title": "Bare form", "doi": "10.1000/XYZ", "authors": [],
             "year": 2020}
        )
        self.assertEqual(r_url, r_bare)

    def test_record_id_openalex_id_fallback(self):
        """P1-13 semantics: invalid DOI falls back to openalex_id."""
        r1 = ing.generate_record_id(
            {"title": "Whatever one", "openalex_id": "https://openalex.org/W123",
             "doi": "NR", "authors": [], "year": 2020}
        )
        r2 = ing.generate_record_id(
            {"title": "Whatever two", "openalex_id": "https://openalex.org/W123",
             "doi": "N/A", "authors": [], "year": 2021}
        )
        self.assertEqual(r1, r2)
        r3 = ing.generate_record_id(
            {"title": "Other work", "openalex_id": "https://openalex.org/W456",
             "doi": "NR", "authors": [], "year": 2020}
        )
        self.assertNotEqual(r1, r3)

    def test_record_id_title_hash_fallback(self):
        r1 = ing.generate_record_id(
            {"title": "A title, here!", "doi": "N/A", "authors": ["Ann"],
             "year": 2020}
        )
        r2 = ing.generate_record_id(
            {"title": "A title here", "doi": "N/A", "authors": ["Ann"],
             "year": 2020}
        )
        self.assertEqual(r1, r2)

    def test_normalization_version_declared_in_docstring(self):
        """H-23 red line: v2 declaration + no retroactive migration on record."""
        doc = (ing.__doc__ or "")
        self.assertIn("v2", doc)
        self.assertIn("2026-09-13", doc)
        self.assertIn("NOT retroactively", doc)


# ---------------------------------------------------------------------------
# H-18: CJK-aware concept expansion word filter
# ---------------------------------------------------------------------------

class TestH18CjkExpansionWords(unittest.TestCase):
    def test_cjk_words_qualify_by_char_count(self):
        self.assertEqual(
            ags.concept_expansion_words("微塑料 水蚤 行为毒性"),
            ["微塑料", "水蚤", "行为毒性"],
        )

    def test_single_cjk_char_still_filtered(self):
        self.assertEqual(ags.concept_expansion_words("蚤 行为 toxicity"),
                         ["行为", "toxicity"])

    def test_english_filter_unchanged(self):
        self.assertEqual(ags.concept_expansion_words("ab cd efgh"), ["efgh"])
        self.assertEqual(ags.concept_expansion_words("abcd efgh"),
                         ["abcd", "efgh"])

    def test_mixed_cjk_ascii_word_qualifies(self):
        self.assertEqual(
            ags.concept_expansion_words("microplastics 蚤 行为 toxicity"),
            ["microplastics", "行为", "toxicity"],
        )


class _ExpansionHarness(unittest.TestCase):
    """Offline harness: monkeypatch the OpenAlex query entry point."""

    def setUp(self):
        self.calls = []
        self._orig = ags.query_openalex_headless

        def fake_query(query_str, limit=25, include_theses=True, per_page=None):
            self.calls.append(query_str)
            return ags.QueryExecutionResult(
                [], None,
                meta={
                    "reported_total_hits": 0,
                    "execution_status": "SEARCHED_COMPLETE",
                    "coverage_status": "COMPLETE",
                    "pagination_status": "COMPLETE",
                },
            )

        ags.query_openalex_headless = fake_query
        self.profile = SimpleNamespace(concept_expansion_rounds=2,
                                       snowball_rounds=0)

    def tearDown(self):
        ags.query_openalex_headless = self._orig


class TestH18ExpansionRounds(_ExpansionHarness):
    def test_standard_search_chinese_expansion_real(self):
        """DIS-R-01/DIS-V-21: Chinese queries must reach the expansion rounds."""
        _, sat = ags.run_standard_search("微塑料 水蚤 行为毒性", limit=10,
                                         profile=self.profile)
        self.assertEqual(sat["expansion_rounds_executed"], 2)
        expansion_queries = self.calls[1:]
        self.assertEqual(len(expansion_queries), 2)
        for q in expansion_queries:
            self.assertTrue(any(ags._cjk_char_count(w) for w in q.split()),
                            f"expansion query lost Chinese terms: {q!r}")
        self.assertNotIn("concept_expansion",
                         [s["step"] for s in sat["skipped_steps"]])

    def test_deep_search_chinese_expansion_real(self):
        _, sat = ags.run_deep_search("微塑料 水蚤 行为毒性", limit=10,
                                     profile=self.profile)
        self.assertEqual(sat["expansion_rounds_executed"], 2)
        self.assertEqual(len(self.calls), 3)
        self.assertTrue(all(any(ags._cjk_char_count(w) for w in q.split())
                            for q in self.calls))

    def test_short_english_query_still_skips_expansion(self):
        _, sat = ags.run_standard_search("ab cd", limit=10,
                                         profile=self.profile)
        self.assertEqual(sat["expansion_rounds_executed"], 0)
        self.assertEqual(len(self.calls), 1)
        self.assertIn("concept_expansion",
                      [s["step"] for s in sat["skipped_steps"]])

    def test_english_query_expansion_unchanged(self):
        _, sat = ags.run_standard_search("biodiversity survey", limit=10,
                                         profile=self.profile)
        self.assertEqual(sat["expansion_rounds_executed"], 2)
        self.assertEqual(self.calls[1], "biodiversity survey")


# ---------------------------------------------------------------------------
# H-27: kappa gate independence & coverage
# ---------------------------------------------------------------------------

def _kappa_records(n=10):
    statuses = ["Include", "Exclude", "Uncertain"]
    return [{"id": f"R{i:03d}", "title": f"paper {i}",
             "status": statuses[i % 3]} for i in range(n)]


def _write_json(td, name, payload):
    p = Path(td) / name
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


class TestH27IdenticalSources(unittest.TestCase):
    def _write_file(self, td, name, payload):
        return _write_json(td, name, payload)

    def test_same_file_fed_to_both_reviewers_rejected(self):
        """Verifier K1: one file as both A and B -> IDENTICAL_SOURCES."""
        with tempfile.TemporaryDirectory() as td:
            same = self._write_file(td, "rev_same.json", _kappa_records())
            data = csa.load_decisions(same)
            res = csa.check_source_independence(same, same, data, dict(data))
        self.assertIsNotNone(res)
        self.assertEqual(res["error"], "IDENTICAL_SOURCES")
        self.assertEqual(res["fingerprint_a"], res["fingerprint_b"])

    def test_identical_content_different_paths_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            pa = self._write_file(td, "a.json", _kappa_records())
            pb = self._write_file(td, "b.json", _kappa_records())
            ma, mb = csa.load_decisions(pa), csa.load_decisions(pb)
            res = csa.check_source_independence(pa, pb, ma, mb)
        self.assertIsNotNone(res)
        self.assertEqual(res["error"], "IDENTICAL_SOURCES")

    def test_independent_files_with_full_agreement_allowed(self):
        """Legitimately independent reviewers agreeing 100% must NOT block."""
        with tempfile.TemporaryDirectory() as td:
            pa = self._write_file(
                td, "a.json",
                [{"id": "R1", "title": "T", "status": "Include",
                  "reason_code": "INC_TAXON_A"}])
            pb = self._write_file(
                td, "b.json",
                [{"id": "R1", "title": "T", "status": "Include",
                  "reason_code": "INC_ENDPOINT_B"}])
            ma, mb = csa.load_decisions(pa), csa.load_decisions(pb)
            res = csa.check_source_independence(pa, pb, ma, mb)
        self.assertIsNone(res)

    def test_same_task_id_reuse_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            pa = self._write_file(
                td, "a.json",
                [{"id": "R1", "title": "T", "status": "Include",
                  "task_id": "task-9"}])
            pb = self._write_file(
                td, "b.json",
                [{"id": "R1", "title": "T", "status": "Exclude",
                  "task_id": "task-9"}])
            ma, mb = csa.load_decisions(pa), csa.load_decisions(pb)
            res = csa.check_source_independence(pa, pb, ma, mb)
        self.assertIsNotNone(res)
        self.assertEqual(res["error"], "IDENTICAL_SOURCES")
        self.assertTrue(any("task_id" in r for r in res["reasons"]))

    def test_cli_identical_sources_exit_code_1(self):
        """Verifier K1 end-to-end: same file both sides -> rc=1, no report."""
        with tempfile.TemporaryDirectory() as td:
            same = self._write_file(td, "rev_same.json", _kappa_records())
            out_md = Path(td) / "report.md"
            proc = subprocess.run(
                [sys.executable, str(KAPPA_SCRIPT), "-a", str(same),
                 "-b", str(same), "-o", str(out_md)],
                capture_output=True, text=True,
            )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("IDENTICAL_SOURCES", proc.stderr)
        self.assertFalse(out_md.exists(), "no passing report may be emitted")


class TestH27CoverageWarning(unittest.TestCase):
    def test_partial_reviewer_b_coverage_warns(self):
        """Verifier K2: B reviewed 2/10 -> coverage WARNING, 8 missing."""
        a_map = {f"R{i:03d}": {"id": f"R{i:03d}", "status": "Include"}
                 for i in range(10)}
        b_map = {"R000": {"id": "R000", "status": "Include"},
                 "R001": {"id": "R001", "status": "Exclude"}}
        cov = csa.check_reviewer_coverage(a_map, b_map)
        self.assertTrue(cov["coverage_warning"])
        self.assertEqual(cov["coverage_status"], "WARNING")
        self.assertEqual(cov["union_records"], 10)
        self.assertEqual(cov["common_records"], 2)
        self.assertEqual(len(cov["missing_from_reviewer_b"]), 8)
        self.assertEqual(cov["missing_from_reviewer_a"], [])

    def test_full_coverage_passes_without_warning(self):
        a_map = {f"R{i}": {"id": f"R{i}", "status": "Include"}
                 for i in range(5)}
        b_map = {f"R{i}": {"id": f"R{i}", "status": "Include"}
                 for i in range(5)}
        cov = csa.check_reviewer_coverage(a_map, b_map)
        self.assertFalse(cov["coverage_warning"])
        self.assertEqual(cov["coverage_status"], "PASS")

    def test_coverage_warning_does_not_block_valid_kappa(self):
        """rc semantics: kappa still computed on the common subset (rc=0)."""
        records = _kappa_records(10)
        a_map = {r["id"]: {"id": r["id"], "status": r["status"]} for r in records}
        b_map = {r["id"]: {"id": r["id"], "status": r["status"]}
                 for r in records[:2]}
        metrics = csa.calculate_cohens_kappa(a_map, b_map)
        self.assertNotIn("error", metrics)
        self.assertEqual(metrics["sample_size"], 2)
        cov = csa.check_reviewer_coverage(a_map, b_map)
        metrics["coverage"] = cov
        md = csa.generate_markdown_report(metrics, "a.json", "b.json")
        self.assertIn("评阅覆盖率核查", md)
        self.assertIn("WARNING", md)
        self.assertIn("缺审", md)
        self.assertIn("Coverage Status", md)

    def test_cli_partial_coverage_rc0_with_warning(self):
        """Verifier K2 end-to-end: rc stays 0, warning + md section present."""
        with tempfile.TemporaryDirectory() as td:
            full = _write_json(td, "rev_full.json", _kappa_records())
            part = _write_json(td, "rev_part.json", _kappa_records()[:2])
            out_md = Path(td) / "report.md"
            proc = subprocess.run(
                [sys.executable, str(KAPPA_SCRIPT), "-a", str(full),
                 "-b", str(part), "-o", str(out_md)],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("Reviewer coverage gap", proc.stderr)
            md = out_md.read_text(encoding="utf-8")
        self.assertIn("WARNING", md)
        self.assertIn("缺审", md)

    def test_arbitration_queue_carries_coverage_flag(self):
        metrics = {"discrepancies": [], "coverage":
                   {"coverage_warning": True, "coverage_status": "WARNING"}}
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "arb.json"
            csa.export_arbitration_queue(metrics, out)
            payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertTrue(payload["coverage_warning"])
        self.assertEqual(payload["coverage_status"], "WARNING")


# ---------------------------------------------------------------------------
# H-60: PRISMA-S item 6 honesty
# ---------------------------------------------------------------------------

class TestH60PrismaItem6(unittest.TestCase):
    def test_item6_not_applicable_with_disclosure(self):
        audit = ags.build_prisma_s_audit("standard", None)
        item6 = next(i for i in audit["items"] if i["item"] == 6)
        self.assertEqual(item6["name"], "Search limits applied")
        self.assertEqual(item6["status"], "NOT_APPLICABLE")
        evidence = item6["evidence"]
        self.assertIn("filter", evidence.lower())
        self.assertIn("不支持", evidence)
        self.assertIn("年份", evidence)

    def test_item6_not_applicable_for_deep_and_snowball(self):
        for mode, seed in (("deep", None), ("standard", "10.1000/seed")):
            audit = ags.build_prisma_s_audit(mode, seed)
            item6 = next(i for i in audit["items"] if i["item"] == 6)
            self.assertEqual(item6["status"], "NOT_APPLICABLE", mode)

    def test_no_item_claims_type_language_year_limits(self):
        audit = ags.build_prisma_s_audit("deep", None)
        for item in audit["items"]:
            if item["item"] == 6:
                continue
            self.assertNotIn("Type, language, and year limits recorded",
                             item["evidence"])


if __name__ == "__main__":
    unittest.main()
