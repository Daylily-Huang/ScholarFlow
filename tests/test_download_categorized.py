# -*- coding: utf-8 -*-
"""Unit tests for download_oa_papers categorized output layout, .intermediate hiding, and reorganization."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import helpers

REPO_ROOT = helpers.REPO_ROOT
SCRIPTS = REPO_ROOT / "skills" / "literature-discovery-acquisition" / "scripts"
DOWNLOAD_SCRIPT = SCRIPTS / "download_oa_papers.py"

import importlib.util
spec = importlib.util.spec_from_file_location("download_oa_papers", str(DOWNLOAD_SCRIPT))
dop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dop)


class TestCategorizedDownloadLayout(unittest.TestCase):
    """Test that download_oa_papers categorizes outputs into pdfs/, metadata/, reports/ and .intermediate/."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_categorized_layout_default(self):
        records = [{
            "record_id": "REC001",
            "title": "Quantum Error Correction",
            "authors": ["Alice Smith"],
            "year": 2024,
            "doi": "10.1000/182",
            "pdf_url": "https://example.org/qec.pdf",
            "screening_status": "Include",
            "oa_status": "gold"
        }]
        in_json = Path(self.temp_dir) / "in.json"
        in_json.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        out_dir = Path(self.temp_dir) / "out"

        def fake_download(url, target_path, timeout=30):
            Path(target_path).write_bytes(b"%PDF-1.4 dummy valid pdf content here")
            return True, "Success"

        with patch.object(dop, "download_file", side_effect=fake_download):
            rc = dop.run_pipeline(str(in_json), str(out_dir), categorized=True)

        self.assertEqual(rc, 0)

        # 1. PDFs must be in out/pdfs/
        pdf_dir = out_dir / "pdfs"
        self.assertTrue(pdf_dir.is_dir())
        pdf_files = list(pdf_dir.glob("*.pdf"))
        self.assertEqual(len(pdf_files), 1)

        # 2. Single CSL files must be in out/.intermediate/csl_singles/ (hidden)
        csl_single_dir = out_dir / ".intermediate" / "csl_singles"
        self.assertTrue(csl_single_dir.is_dir())
        csl_files = list(csl_single_dir.glob("*.csl.json"))
        self.assertEqual(len(csl_files), 1)

        # 3. No single .csl.json or .pdf in out root
        root_csl = list(out_dir.glob("*_Alice_*.csl.json"))
        self.assertEqual(len(root_csl), 0, "Single CSL files should not be in root")
        root_pdf = list(out_dir.glob("*.pdf"))
        self.assertEqual(len(root_pdf), 0, "PDFs should be in pdfs/ not root")

        # 4. Metadata in metadata/ and backward-compatible in root
        meta_dir = out_dir / "metadata"
        self.assertTrue(meta_dir.is_dir())
        self.assertTrue((meta_dir / "zotero_import.csl.json").is_file())
        self.assertTrue((meta_dir / "download_ledger.json").is_file())
        self.assertTrue((out_dir / "zotero_import.csl.json").is_file())
        self.assertTrue((out_dir / "download_ledger.json").is_file())

        # 5. Reports in reports/ and backward-compatible in root
        reports_dir = out_dir / "reports"
        self.assertTrue(reports_dir.is_dir())
        self.assertTrue((reports_dir / "download_ledger.md").is_file())
        self.assertTrue((out_dir / "download_ledger.md").is_file())

        # 6. zotero_import has relative path pdfs/...
        zotero_data = json.loads((meta_dir / "zotero_import.csl.json").read_text(encoding="utf-8"))
        self.assertEqual(len(zotero_data), 1)
        self.assertTrue(zotero_data[0]["file"].startswith("pdfs/"))

    def test_flat_layout_mode(self):
        records = [{
            "record_id": "REC002",
            "title": "Flat Mode Paper",
            "authors": ["Bob Jones"],
            "year": 2023,
            "doi": "10.1000/183",
            "pdf_url": "https://example.org/flat.pdf",
            "screening_status": "Include",
            "oa_status": "gold"
        }]
        in_json = Path(self.temp_dir) / "in.json"
        in_json.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        out_dir = Path(self.temp_dir) / "out_flat"

        def fake_download(url, target_path, timeout=30):
            Path(target_path).write_bytes(b"%PDF-1.4 dummy valid pdf content here")
            return True, "Success"

        with patch.object(dop, "download_file", side_effect=fake_download):
            rc = dop.run_pipeline(str(in_json), str(out_dir), categorized=False)

        self.assertEqual(rc, 0)
        # In flat mode, PDF is in root
        root_pdf = list(out_dir.glob("*.pdf"))
        self.assertEqual(len(root_pdf), 1)
        # Single CSL is in root
        root_csl = list(out_dir.glob("*_Bob_*.csl.json"))
        self.assertEqual(len(root_csl), 1)

    def test_organize_directory(self):
        messy_dir = Path(self.temp_dir) / "messy"
        messy_dir.mkdir(parents=True, exist_ok=True)

        (messy_dir / "2024_Smith_Quantum.pdf").write_text("dummy pdf", encoding="utf-8")
        (messy_dir / "2024_Smith_Quantum.csl.json").write_text("{}", encoding="utf-8")
        (messy_dir / "2024_Smith_Quantum.txt").write_text("dummy text", encoding="utf-8")
        (messy_dir / "article.html").write_text("<html></html>", encoding="utf-8")
        (messy_dir / "screening_reviewer_a.json").write_text("[]", encoding="utf-8")
        (messy_dir / "download_ledger.json").write_text("[]", encoding="utf-8")
        (messy_dir / "download_ledger.md").write_text("# Ledger", encoding="utf-8")

        stats = dop.organize_directory(str(messy_dir))

        self.assertEqual(stats["pdfs"], 1)
        self.assertEqual(stats["htmls"], 1)
        self.assertEqual(stats["csl_singles"], 1)
        self.assertEqual(stats["text_dumps"], 1)
        self.assertEqual(stats["screening"], 1)
        self.assertEqual(stats["metadata"], 1)
        self.assertEqual(stats["reports"], 1)

        self.assertTrue((messy_dir / "pdfs" / "2024_Smith_Quantum.pdf").is_file())
        self.assertTrue((messy_dir / "htmls" / "article.html").is_file())
        self.assertTrue((messy_dir / ".intermediate" / "csl_singles" / "2024_Smith_Quantum.csl.json").is_file())
        self.assertTrue((messy_dir / ".intermediate" / "text_dumps" / "2024_Smith_Quantum.txt").is_file())
        self.assertTrue((messy_dir / ".intermediate" / "screening" / "screening_reviewer_a.json").is_file())
        self.assertTrue((messy_dir / "metadata" / "download_ledger.json").is_file())
        self.assertTrue((messy_dir / "reports" / "download_ledger.md").is_file())


if __name__ == "__main__":
    unittest.main()
