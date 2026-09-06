#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_external_records.py
--------------------------
ScholarFlow External Bibliography Ingestion Pipeline

Ingests and normalizes structured reference export files from commercial databases
(CNKI, Wanfang, Web of Science, Scopus, PubMed) into the ScholarFlow standardized
candidate literature schema (schemas/literature_record.schema.json).

Supported Formats:
1. CNKI Refworks export (*.txt) - supports journal articles, master/doctoral theses
2. RIS format (*.ris, *.txt) - universal standard (WoS, Scopus, Springer, Wiley)
3. EndNote export (*.enw, *.txt) - standard Tagged format (%0, %T, %A, %D, etc.)
4. Tabular export (*.csv, *.tsv) - table exports with configurable columns

Usage:
    python ingest_external_records.py -i cnki_export.txt -o cnki_candidates.json --source CNKI
    python ingest_external_records.py -i ./external_imports/ -o all_imported_candidates.json
    python ingest_external_records.py -i wos_savedrecs.ris -o wos_candidates.json
"""

import os
import sys
import re
import csv
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def clean_str(val: Optional[str]) -> str:
    """Strip whitespace and normalize spacing."""
    if not val:
        return ""
    return re.sub(r"\s+", " ", str(val)).strip()


def parse_cnki_refworks(content: str) -> List[Dict[str, Any]]:
    """
    Parses CNKI Refworks format (standard CNKI multi-item export).
    Items typically begin with RT (Reference Type) or SR (Serial).
    Fields:
      RT: Reference Type (Journal Article, Thesis, etc.)
      T1 / TI: Title
      A1 / AU: Authors
      AD: Author address / University
      JF / JO: Journal / Source
      YR: Publication year
      AB: Abstract
      K1: Keywords
      DOI: DOI
      LK: CNKI URL
    """
    records = []
    # Split by delimiter indicating new record
    raw_blocks = re.split(r"\n\s*(?=RT\s+|Reference Type:\s*|\bSR\s+1\b)", content)
    
    for block in raw_blocks:
        if not block.strip():
            continue
        
        lines = block.splitlines()
        fields: Dict[str, List[str]] = {}
        curr_tag = None
        
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            # Match 2-4 uppercase letter tags like "RT ", "A1 ", "T1 ", "AB ", "K1 ", "YR "
            match = re.match(r"^([A-Z0-9]{2,4}|[A-Za-z ]+?)\s*[:-]\s*(.*)$", line_str)
            if match and len(match.group(1)) <= 15:
                curr_tag = match.group(1).upper()
                val = match.group(2).strip()
                if curr_tag not in fields:
                    fields[curr_tag] = []
                fields[curr_tag].append(val)
            elif curr_tag and curr_tag in fields:
                # Continuation line
                fields[curr_tag][-1] += " " + line_str

        # Extract normalized attributes
        raw_rt = " ".join(fields.get("RT", [])).lower()
        title = clean_str(" ".join(fields.get("T1", fields.get("TI", fields.get("TITLE", [])))))
        if not title:
            continue
        
        authors_raw = fields.get("A1", fields.get("AU", fields.get("AUTHOR", [])))
        authors = []
        for a in authors_raw:
            for sub_a in re.split(r"[;,、]", a):
                cleaned = clean_str(sub_a)
                if cleaned and cleaned not in authors:
                    authors.append(cleaned)
        
        year_str = clean_str(" ".join(fields.get("YR", fields.get("YEAR", fields.get("PY", [])))))
        year_match = re.search(r"\b(19\d\d|20\d\d)\b", year_str)
        year = int(year_match.group(1)) if year_match else None
        
        journal = clean_str(" ".join(fields.get("JF", fields.get("JO", fields.get("SO", fields.get("PB", []))))))
        abstract = clean_str(" ".join(fields.get("AB", fields.get("ABSTRACT", []))))
        
        kw_raw = fields.get("K1", fields.get("KW", fields.get("KEYWORDS", [])))
        keywords = []
        for kw in kw_raw:
            for sub_kw in re.split(r"[;,、/]", kw):
                cleaned = clean_str(sub_kw)
                if cleaned and cleaned not in keywords:
                    keywords.append(cleaned)
                    
        doi_raw = clean_str(" ".join(fields.get("DOI", fields.get("DO", []))))
        doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", doi_raw)
        doi = doi_match.group(0) if doi_match else "NR"
        
        url = clean_str(" ".join(fields.get("LK", fields.get("URL", []))))
        address = clean_str(" ".join(fields.get("AD", [])))
        
        # Determine document type & thesis specifics
        doc_type = "Journal Article"
        thesis_info = {}
        if "thesis" in raw_rt or "学位" in raw_rt or "硕士" in raw_rt or "博士" in raw_rt or "dissertation" in raw_rt:
            doc_type = "Thesis"
            degree = "Doctoral" if ("博" in raw_rt or "phd" in raw_rt or "doctoral" in raw_rt) else "Master"
            thesis_info = {
                "degree": degree,
                "institution": address or journal,
                "document_type": "Thesis"
            }
            
        record = {
            "title": title,
            "authors": authors,
            "year": year,
            "journal": journal,
            "doi": doi,
            "url": url if url else None,
            "abstract": abstract if abstract else None,
            "keywords": keywords,
            "document_type": doc_type,
            "source_databases": ["CNKI"],
            "evidence_tier": "UNVERIFIED",
            "screening_status": "Uncertain",
            "ingestion_method": "CNKI_Refworks_Import"
        }
        if thesis_info:
            record["thesis_metadata"] = thesis_info
            
        records.append(record)
        
    return records


def parse_ris(content: str) -> List[Dict[str, Any]]:
    """
    Parses standard RIS format (Used by WoS, Scopus, PubMed, IEEE, etc.).
    Tags:
      TY  - Type of reference (JOUR, THES, CONF, etc.)
      TI / T1  - Title
      AU / A1  - Authors
      PY / Y1  - Publication year
      JO / JF / T2 / SO  - Journal name
      AB / N2  - Abstract
      KW  - Keywords
      DO  - DOI
      UR  - URL
      PB  - Publisher / University
      ER  - End of Reference
    """
    records = []
    blocks = re.split(r"\bER\s*-\s*", content)
    
    for block in blocks:
        if not block.strip():
            continue
        
        lines = block.splitlines()
        fields: Dict[str, List[str]] = {}
        curr_tag = None
        
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            match = re.match(r"^([A-Z0-9]{2})\s*-\s*(.*)$", line_str)
            if match:
                curr_tag = match.group(1).upper()
                val = match.group(2).strip()
                if curr_tag not in fields:
                    fields[curr_tag] = []
                fields[curr_tag].append(val)
            elif curr_tag and curr_tag in fields:
                fields[curr_tag][-1] += " " + line_str
                
        ty = clean_str(" ".join(fields.get("TY", []))).upper()
        title = clean_str(" ".join(fields.get("TI", fields.get("T1", []))))
        if not title:
            continue
            
        authors_raw = fields.get("AU", fields.get("A1", []))
        authors = [clean_str(a) for a in authors_raw if clean_str(a)]
        
        py_str = clean_str(" ".join(fields.get("PY", fields.get("Y1", fields.get("DA", [])))))
        year_match = re.search(r"\b(19\d\d|20\d\d)\b", py_str)
        year = int(year_match.group(1)) if year_match else None
        
        journal = clean_str(" ".join(fields.get("JO", fields.get("JF", fields.get("T2", fields.get("SO", []))))))
        abstract = clean_str(" ".join(fields.get("AB", fields.get("N2", []))))
        
        kw_raw = fields.get("KW", [])
        keywords = []
        for kw in kw_raw:
            for sub_kw in re.split(r"[;,/]", kw):
                cleaned = clean_str(sub_kw)
                if cleaned and cleaned not in keywords:
                    keywords.append(cleaned)
                    
        doi_raw = clean_str(" ".join(fields.get("DO", fields.get("DI", []))))
        doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", doi_raw)
        doi = doi_match.group(0) if doi_match else "NR"
        
        url = clean_str(" ".join(fields.get("UR", [])))
        publisher = clean_str(" ".join(fields.get("PB", [])))
        
        doc_type = "Journal Article"
        thesis_info = {}
        if ty in {"THES", "DISSERTATION"} or "thesis" in ty.lower() or "dissertation" in ty.lower():
            doc_type = "Thesis"
            thesis_info = {
                "degree": "Doctoral / Master",
                "institution": publisher or journal,
                "document_type": "Thesis"
            }
        elif ty in {"CONF", "CPAPER"}:
            doc_type = "Conference Proceeding"
            
        record = {
            "title": title,
            "authors": authors,
            "year": year,
            "journal": journal,
            "doi": doi,
            "url": url if url else None,
            "abstract": abstract if abstract else None,
            "keywords": keywords,
            "document_type": doc_type,
            "source_databases": ["RIS_Import"],
            "evidence_tier": "UNVERIFIED",
            "screening_status": "Uncertain",
            "ingestion_method": "RIS_Import"
        }
        if thesis_info:
            record["thesis_metadata"] = thesis_info
            
        records.append(record)
        
    return records


def parse_endnote_enw(content: str) -> List[Dict[str, Any]]:
    """
    Parses EndNote Tagged format (*.enw).
    Tags:
      %0  - Reference Type (Journal Article, Thesis, etc.)
      %T  - Title
      %A  - Author
      %D  - Year
      %J / %B  - Journal / Book
      %X  - Abstract
      %K  - Keywords
      %R  - DOI
      %U  - URL
      %I  - Publisher / University
    """
    records = []
    blocks = re.split(r"\n\s*(?=%0\s+)", content)
    
    for block in blocks:
        if not block.strip():
            continue
            
        lines = block.splitlines()
        fields: Dict[str, List[str]] = {}
        curr_tag = None
        
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            match = re.match(r"^(%[0-9A-Za-z])\s+(.*)$", line_str)
            if match:
                curr_tag = match.group(1)
                val = match.group(2).strip()
                if curr_tag not in fields:
                    fields[curr_tag] = []
                fields[curr_tag].append(val)
            elif curr_tag and curr_tag in fields:
                fields[curr_tag][-1] += " " + line_str
                
        ref_type = clean_str(" ".join(fields.get("%0", []))).lower()
        title = clean_str(" ".join(fields.get("%T", [])))
        if not title:
            continue
            
        authors = [clean_str(a) for a in fields.get("%A", []) if clean_str(a)]
        year_str = clean_str(" ".join(fields.get("%D", [])))
        year_match = re.search(r"\b(19\d\d|20\d\d)\b", year_str)
        year = int(year_match.group(1)) if year_match else None
        
        journal = clean_str(" ".join(fields.get("%J", fields.get("%B", []))))
        abstract = clean_str(" ".join(fields.get("%X", [])))
        
        kw_raw = fields.get("%K", [])
        keywords = []
        for kw in kw_raw:
            for sub_kw in re.split(r"[;,/]", kw):
                cleaned = clean_str(sub_kw)
                if cleaned and cleaned not in keywords:
                    keywords.append(cleaned)
                    
        doi_raw = clean_str(" ".join(fields.get("%R", [])))
        doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", doi_raw)
        doi = doi_match.group(0) if doi_match else "NR"
        
        url = clean_str(" ".join(fields.get("%U", [])))
        publisher = clean_str(" ".join(fields.get("%I", [])))
        
        doc_type = "Journal Article"
        thesis_info = {}
        if "thesis" in ref_type or "dissertation" in ref_type or "学位" in ref_type:
            doc_type = "Thesis"
            thesis_info = {
                "degree": "Thesis",
                "institution": publisher or journal,
                "document_type": "Thesis"
            }
            
        record = {
            "title": title,
            "authors": authors,
            "year": year,
            "journal": journal,
            "doi": doi,
            "url": url if url else None,
            "abstract": abstract if abstract else None,
            "keywords": keywords,
            "document_type": doc_type,
            "source_databases": ["EndNote_Import"],
            "evidence_tier": "UNVERIFIED",
            "screening_status": "Uncertain",
            "ingestion_method": "EndNote_Import"
        }
        if thesis_info:
            record["thesis_metadata"] = thesis_info
            
        records.append(record)
        
    return records


def parse_csv_tsv(file_path: Path) -> List[Dict[str, Any]]:
    """Parses CSV or TSV table exports with column auto-detection."""
    records = []
    delimiter = "\t" if file_path.suffix.lower() == ".tsv" else ","
    
    with open(file_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        if not reader.fieldnames:
            return []
            
        header_map = {}
        for h in reader.fieldnames:
            norm_h = h.strip().lower()
            if any(k in norm_h for k in ["title", "题名", "篇名", "文章名称"]):
                header_map["title"] = h
            elif any(k in norm_h for k in ["author", "作者", "creator"]):
                header_map["author"] = h
            elif any(k in norm_h for k in ["year", "年", "date", "出版年", "发表时间"]):
                header_map["year"] = h
            elif any(k in norm_h for k in ["journal", "刊名", "来源", "source", "出版物"]):
                header_map["journal"] = h
            elif any(k in norm_h for k in ["abstract", "摘要"]):
                header_map["abstract"] = h
            elif any(k in norm_h for k in ["keyword", "关键词"]):
                header_map["keyword"] = h
            elif any(k in norm_h for k in ["doi"]):
                header_map["doi"] = h
            elif any(k in norm_h for k in ["url", "链接"]):
                header_map["url"] = h
                
        if "title" not in header_map:
            return []
            
        for row in reader:
            title = clean_str(row.get(header_map.get("title", "")))
            if not title:
                continue
                
            raw_authors = clean_str(row.get(header_map.get("author", "")))
            authors = [clean_str(a) for a in re.split(r"[;,、/]", raw_authors) if clean_str(a)]
            
            year_str = clean_str(row.get(header_map.get("year", "")))
            year_match = re.search(r"\b(19\d\d|20\d\d)\b", year_str)
            year = int(year_match.group(1)) if year_match else None
            
            journal = clean_str(row.get(header_map.get("journal", "")))
            abstract = clean_str(row.get(header_map.get("abstract", "")))
            
            raw_kw = clean_str(row.get(header_map.get("keyword", "")))
            keywords = [clean_str(k) for k in re.split(r"[;,、/]", raw_kw) if clean_str(k)]
            
            doi_raw = clean_str(row.get(header_map.get("doi", "")))
            doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", doi_raw)
            doi = doi_match.group(0) if doi_match else "NR"
            
            url = clean_str(row.get(header_map.get("url", "")))
            
            records.append({
                "title": title,
                "authors": authors,
                "year": year,
                "journal": journal,
                "doi": doi,
                "url": url if url else None,
                "abstract": abstract if abstract else None,
                "keywords": keywords,
                "document_type": "Journal Article",
                "source_databases": ["Table_Import"],
                "evidence_tier": "UNVERIFIED",
                "screening_status": "Uncertain",
                "ingestion_method": "Table_Import"
            })
            
    return records


def detect_and_parse_file(file_path: Path, source_override: Optional[str] = None) -> List[Dict[str, Any]]:
    """Automatically detects format and parses single export file."""
    ext = file_path.suffix.lower()
    
    if ext in {".csv", ".tsv"}:
        return parse_csv_tsv(file_path)
        
    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
            content = f.read()
    except Exception as e:
        print(f"[ERROR] Failed to read {file_path}: {e}", file=sys.stderr)
        return []
        
    # Check for Refworks signature
    if source_override == "CNKI" or re.search(r"\b(RT\s+Journal|RT\s+Thesis|Reference Type:|SR\s+1|K1\s+)", content):
        return parse_cnki_refworks(content)
        
    # Check for RIS signature
    if ext == ".ris" or source_override in {"RIS", "WoS", "Scopus"} or re.search(r"^TY\s*-\s*", content, re.M):
        return parse_ris(content)
        
    # Check for EndNote signature
    if ext == ".enw" or source_override == "EndNote" or re.search(r"^%0\s+", content, re.M):
        return parse_endnote_enw(content)
        
    # Fallback to Refworks if Chinese keywords present
    if "【关键词】" in content or "【作者】" in content or "【摘要】" in content:
        return parse_cnki_refworks(content)
        
    # Default fallback to RIS or Refworks
    records = parse_cnki_refworks(content)
    if records:
        return records
    return parse_ris(content)


def main():
    parser = argparse.ArgumentParser(
        description="ScholarFlow External Bibliography Ingestion Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest CNKI exported Refworks text:
  python ingest_external_records.py -i cnki_refworks.txt -o cnki_candidates.json --source CNKI
  
  # Ingest a folder of diverse export files:
  python ingest_external_records.py -i ./papers/external_imports/ -o all_imported.json
  
  # Ingest Web of Science RIS export:
  python ingest_external_records.py -i savedrecs.ris -o wos_candidates.json
        """
    )
    parser.add_argument("-i", "--input", required=True, help="Input export file path (*.txt, *.ris, *.enw, *.csv) or directory containing export files")
    parser.add_argument("-o", "--output", required=True, help="Output standardized JSON file path")
    parser.add_argument("-s", "--source", choices=["CNKI", "Wanfang", "WoS", "Scopus", "EndNote", "RIS", "auto"], default="auto", help="Source database identifier override (default: auto)")
    
    args = parser.parse_args()
    
    in_path = Path(args.input)
    if not in_path.exists():
        print(f"[ERROR] Input path does not exist: {in_path}", file=sys.stderr)
        sys.exit(1)
        
    target_files: List[Path] = []
    if in_path.is_dir():
        for ext in [".txt", ".ris", ".enw", ".csv", ".tsv"]:
            target_files.extend(list(in_path.glob(f"*{ext}")))
    else:
        target_files.append(in_path)
        
    if not target_files:
        print(f"[WARNING] No compatible export files found in {in_path}", file=sys.stderr)
        sys.exit(0)
        
    all_records: List[Dict[str, Any]] = []
    for tf in target_files:
        records = detect_and_parse_file(tf, None if args.source == "auto" else args.source)
        print(f"[INGEST] Parsed {len(records)} records from {tf.name}")
        all_records.extend(records)
        
    # Deduplicate within this imported batch by Title
    deduped_records = []
    seen_titles = set()
    for r in all_records:
        norm_title = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]", "", r["title"].lower())
        if norm_title in seen_titles:
            continue
        seen_titles.add(norm_title)
        deduped_records.append(r)
        
    # Compute summary stats
    theses_count = sum(1 for r in deduped_records if r.get("document_type") == "Thesis")
    journal_count = sum(1 for r in deduped_records if r.get("document_type") == "Journal Article")
    with_doi_count = sum(1 for r in deduped_records if r.get("doi") and r.get("doi") != "NR")
    with_abs_count = sum(1 for r in deduped_records if r.get("abstract"))
    
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(deduped_records, f, ensure_ascii=False, indent=2)
        
    print("\n========================================================")
    print(" ScholarFlow External Records Ingestion Summary")
    print("========================================================")
    print(f" Total files processed : {len(target_files)}")
    print(f" Raw records extracted : {len(all_records)}")
    print(f" Deduplicated records  : {len(deduped_records)}")
    print(f" - Theses (博硕士学位) : {theses_count}")
    print(f" - Journal Articles    : {journal_count}")
    print(f" - With Valid DOI      : {with_doi_count} ({with_doi_count/len(deduped_records)*100:.1f}%)" if deduped_records else "0")
    print(f" - With Abstract       : {with_abs_count} ({with_abs_count/len(deduped_records)*100:.1f}%)" if deduped_records else "0")
    print(f" Output saved to       : {out_path.resolve()}")
    print("========================================================\n")


if __name__ == "__main__":
    main()
