# -*- coding: utf-8 -*-
"""Tests for ingest_external_records.py (CNKI Refworks / RIS / EndNote / CSV parsers)."""
import unittest
from pathlib import Path

import helpers  # noqa: F401

import ingest_external_records as ing  # type: ignore

FIXTURES = helpers.FIXTURES

REQUIRED_KEYS = {"title", "authors", "year", "journal", "doi", "document_type",
                 "source_databases", "evidence_tier", "screening_status",
                 "ingestion_method"}


class TestParseCnkiRefworks(unittest.TestCase):
    def test_journal_and_thesis(self):
        recs = ing.parse_cnki_refworks((FIXTURES / "sample_cnki_refworks.txt")
                                       .read_text(encoding="utf-8"))
        self.assertEqual(len(recs), 2)
        for r in recs:
            self.assertTrue(REQUIRED_KEYS.issubset(r.keys()))
            self.assertEqual(r["evidence_tier"], "UNVERIFIED")
            self.assertEqual(r["screening_status"], "Uncertain")

        journal = next(r for r in recs if r["document_type"] == "Journal Article")
        self.assertIn("马鹿", journal["title"])
        self.assertEqual(journal["year"], 2021)
        self.assertEqual(len(journal["authors"]), 2)

        thesis = next(r for r in recs if r["document_type"] == "Thesis")
        self.assertIn("生境选择", thesis["title"])
        self.assertEqual(thesis["thesis_metadata"]["degree"], "Master")

    def test_empty_content_returns_empty(self):
        self.assertEqual(ing.parse_cnki_refworks(""), [])
        self.assertEqual(ing.parse_cnki_refworks("\n\n  \n"), [])


class TestParseRis(unittest.TestCase):
    def test_journal_and_thesis(self):
        recs = ing.parse_ris((FIXTURES / "sample.ris").read_text(encoding="utf-8"))
        self.assertEqual(len(recs), 2)

        journal = next(r for r in recs if r["document_type"] == "Journal Article")
        self.assertEqual(journal["year"], 2021)
        self.assertEqual(journal["doi"], "10.1000/fake-doi-001")
        self.assertEqual(journal["authors"], ["Wang, Ming", "Li, Hua"])
        self.assertIn("metabarcoding", " ".join(journal["keywords"]))

        thesis = next(r for r in recs if r["document_type"] == "Thesis")
        self.assertEqual(thesis["thesis_metadata"]["document_type"], "Thesis")


class TestParseEndnoteEnw(unittest.TestCase):
    def test_journal_and_thesis(self):
        recs = ing.parse_endnote_enw((FIXTURES / "sample.enw").read_text(encoding="utf-8"))
        self.assertEqual(len(recs), 2)
        journal = next(r for r in recs if r["document_type"] == "Journal Article")
        self.assertEqual(journal["doi"], "10.1000/enw-001")
        self.assertEqual(journal["year"], 2021)
        thesis = next(r for r in recs if r["document_type"] == "Thesis")
        self.assertIn("微卫星", thesis["title"])


class TestParseCsvTsv(unittest.TestCase):
    def test_csv_chinese_headers(self):
        recs = ing.parse_csv_tsv(FIXTURES / "sample_records.csv")
        self.assertEqual(len(recs), 2)
        first = recs[0]
        self.assertIn("马鹿", first["title"])
        self.assertEqual(first["year"], 2021)
        self.assertEqual(first["doi"], "10.1234/abc.2021.001")
        self.assertEqual(first["authors"], ["王明", "李华"])
        self.assertEqual(first["ingestion_method"], "Table_Import")

    def test_csv_without_title_column_returns_empty(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.csv"
            p.write_text("author,year\nWang,2021\n", encoding="utf-8")
            self.assertEqual(ing.parse_csv_tsv(p), [])


class TestDetectAndParse(unittest.TestCase):
    def test_ris_extension_autodetect(self):
        recs = ing.detect_and_parse_file(FIXTURES / "sample.ris")
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["ingestion_method"], "RIS_Import")

    def test_tsv_extension_dispatch(self):
        # TSV path goes through parse_csv_tsv regardless of content style
        recs = ing.detect_and_parse_file(FIXTURES / "sample_records.csv")
        self.assertTrue(all(r["ingestion_method"] == "Table_Import" for r in recs))


if __name__ == "__main__":
    unittest.main()
