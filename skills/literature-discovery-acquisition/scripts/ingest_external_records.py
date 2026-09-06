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


def parse_vip_format(content: str, source_name: str = "VIP") -> List[Dict[str, Any]]:
    """
    Parses VIP (维普) database export formats.
    Supports:
      - Bracketed tag format (e.g. 【题名】/【作者】/【机构】/【刊名】/【年份】/【摘要】/【关键词】/【DOI】)
      - Standard VIP field tag format (U: Title, A: Author, J: Journal, Y: Year, R: Abstract, K: Keywords)
    """
    if not content or not content.strip():
        return []

    records = []
    # Split records by bracketed title, or tagged U:, or [序号]
    if "【题" in content or "【文章题目】" in content or "【Title】" in content:
        blocks = re.split(r"\n\s*(?=【(?:题名|题\s*名|文章题目|Title)】)", content)
    elif re.search(r"\n\s*(?=\[\d+\]|\[序号\])", content):
        blocks = re.split(r"\n\s*(?=\[\d+\]|\[序号\])", content)
    elif re.search(r"(?:^|\n)U:\s+", content):
        blocks = re.split(r"\n\s*(?=U:\s+)", content)
    else:
        blocks = re.split(r"\n\s*\n", content)

    for block in blocks:
        if not block.strip():
            continue

        fields: Dict[str, List[str]] = {}
        curr_tag = None

        for line in block.splitlines():
            line_str = line.strip()
            if not line_str:
                continue

            bracket_match = re.match(r"^【([^】]+)】\s*[:-]?\s*(.*)$", line_str)
            if bracket_match:
                tag_name = re.sub(r"\s+", "", bracket_match.group(1))
                curr_tag = tag_name
                val = bracket_match.group(2).strip()
                if curr_tag not in fields:
                    fields[curr_tag] = []
                if val:
                    fields[curr_tag].append(val)
                continue

            tag_match = re.match(r"^([A-Z]{1,3}|[A-Za-z ]{2,10})\s*[:-]\s*(.*)$", line_str)
            if tag_match:
                curr_tag = tag_match.group(1).upper().strip()
                val = tag_match.group(2).strip()
                if curr_tag not in fields:
                    fields[curr_tag] = []
                if val:
                    fields[curr_tag].append(val)
                continue

            if curr_tag and curr_tag in fields and fields[curr_tag]:
                fields[curr_tag][-1] += " " + line_str
            elif curr_tag and curr_tag in fields and not fields[curr_tag]:
                fields[curr_tag].append(line_str)

        # Extract field values by first matching tag
        def _get_first(tags):
            for t in tags:
                if t in fields and fields[t]:
                    return fields[t]
            return []

        title_candidates = _get_first(["题名", "题 名", "文章题目", "Title", "TITLE", "U", "TI", "T1"])
        title = clean_str(" ".join(title_candidates))
        if not title:
            continue

        author_candidates = _get_first(["作者", "作 者", "作名", "Author", "A", "AU", "A1"])
        authors = []
        for a_str in author_candidates:
            for sub_a in re.split(r"[;；,，、/]", a_str):
                cleaned = clean_str(sub_a)
                if cleaned and cleaned not in authors:
                    authors.append(cleaned)

        inst_candidates = _get_first(["机构", "机 构", "工作单位", "单位", "AD", "IN"])
        institution = clean_str(" ".join(inst_candidates))

        journal_candidates = _get_first(["刊名", "刊 名", "来源出处", "Journal", "J", "JF", "JO"])
        journal = clean_str(" ".join(journal_candidates))

        year_candidates = _get_first(["年份", "年卷(期)", "年，卷(期)", "年", "出版年", "出 版 年", "Y", "YR", "PY"])
        year_str = clean_str(" ".join(year_candidates))
        year_match = re.search(r"\b(19\d\d|20\d\d)\b", year_str)
        year = int(year_match.group(1)) if year_match else None

        abs_candidates = _get_first(["文摘", "摘要", "摘 要", "Abstract", "R", "AB"])
        abstract = clean_str(" ".join(abs_candidates))

        kw_candidates = _get_first(["关键词", "关 键 词", "Keywords", "K", "K1", "KW"])
        keywords = []
        for kw_str in kw_candidates:
            for sub_kw in re.split(r"[;；,，、/]", kw_str):
                cleaned = clean_str(sub_kw)
                if cleaned and cleaned not in keywords:
                    keywords.append(cleaned)

        doi_candidates = _get_first(["DOI", "doi", "DO"])
        doi_raw = clean_str(" ".join(doi_candidates))
        doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", doi_raw)
        doi = doi_match.group(0) if doi_match else "NR"

        doc_type = "Journal Article"
        thesis_info = {}
        if any(k in title or k in journal for k in ["硕士", "博士", "学位论文", "硕士论文", "博士论文"]):
            doc_type = "Thesis"
            degree = "Doctoral" if ("博" in title or "博" in journal) else "Master"
            thesis_info = {
                "degree": degree,
                "institution": institution or journal,
                "document_type": "Thesis"
            }

        record = {
            "title": title,
            "authors": authors,
            "year": year,
            "journal": journal,
            "doi": doi,
            "url": None,
            "abstract": abstract if abstract else None,
            "keywords": keywords,
            "document_type": doc_type,
            "source_databases": [source_name],
            "evidence_tier": "UNVERIFIED",
            "screening_status": "Uncertain",
            "ingestion_method": f"{source_name}_Import"
        }
        if thesis_info:
            record["thesis_metadata"] = thesis_info

        records.append(record)

    return records


def detect_and_parse_file(file_path: Path, source_override: Optional[str] = None) -> List[Dict[str, Any]]:
    """Automatically detects format and parses single export file."""
    ext = file_path.suffix.lower()

    if ext in {".csv", ".tsv"}:
        records = parse_csv_tsv(file_path)
        if source_override and source_override != "auto":
            for r in records:
                r["source_databases"] = [source_override]
                r["ingestion_method"] = f"{source_override}_Import"
        return records

    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
            content = f.read()
    except Exception as e:
        print(f"[ERROR] Failed to read {file_path}: {e}", file=sys.stderr)
        return []

    # Direct source overrides
    if source_override == "CNKI":
        return parse_cnki_refworks(content)
    elif source_override == "VIP":
        recs = parse_vip_format(content, source_name="VIP")
        if not recs:
            recs = parse_cnki_refworks(content)
            for r in recs:
                r["source_databases"] = ["VIP"]
                r["ingestion_method"] = "VIP_Import"
        return recs
    elif source_override == "Wanfang":
        if ext == ".ris" or re.search(r"^TY\s*-\s*", content, re.M):
            recs = parse_ris(content)
        elif ext == ".enw" or re.search(r"^%0\s+", content, re.M):
            recs = parse_endnote_enw(content)
        else:
            recs = parse_cnki_refworks(content) or parse_ris(content)
        for r in recs:
            r["source_databases"] = ["Wanfang"]
            r["ingestion_method"] = "Wanfang_Import"
        return recs

    # Auto-detection based on file markers
    # 1. VIP signature
    if re.search(r"^【(?:题名|文章题目|题\s*名|文摘|机构|分类号)】", content, re.M) or re.search(r"^U:\s+", content, re.M):
        recs = parse_vip_format(content, source_name="VIP")
        if recs:
            return recs

    # 2. Refworks signature
    if re.search(r"\b(RT\s+Journal|RT\s+Thesis|Reference Type:|SR\s+1|K1\s+)", content):
        return parse_cnki_refworks(content)

    # 3. RIS signature
    if ext == ".ris" or source_override in {"RIS", "WoS", "Scopus"} or re.search(r"^TY\s*-\s*", content, re.M):
        recs = parse_ris(content)
        if source_override and source_override not in {"auto", "RIS"}:
            for r in recs:
                r["source_databases"] = [source_override]
                r["ingestion_method"] = f"{source_override}_Import"
        return recs

    # 4. EndNote signature
    if ext == ".enw" or source_override == "EndNote" or re.search(r"^%0\s+", content, re.M):
        return parse_endnote_enw(content)

    # 5. Chinese keywords fallback
    if "【关键词】" in content or "【作者】" in content or "【摘要】" in content:
        vip_recs = parse_vip_format(content)
        if vip_recs:
            return vip_recs
        return parse_cnki_refworks(content)

    # Default fallback
    records = parse_cnki_refworks(content)
    if records:
        return records
    return parse_ris(content)


def merge_candidate_records(
    existing_records: List[Dict[str, Any]],
    new_records: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Merges newly imported candidate records into existing candidate corpus.
    Features:
    1. Cross-source deduplication via normalized DOI and normalized Title.
    2. Source tracking: preserves all contributing sources in `source_databases`.
    3. Metadata enrichment: fills missing abstract, keywords, DOI, URL from new records.
    4. Conflict detection: flags non-matching publication years or contradictory metadata
       as `CONFLICTING_METADATA` without silently overwriting.
    5. Retains title-only records (never dropped).
    6. Returns structured summary with unique contributions and source distributions.
    """
    def _norm_t(t: Optional[str]) -> str:
        return re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]", "", str(t or "").lower())

    def _norm_doi(d: Optional[str]) -> Optional[str]:
        d_str = str(d or "").strip().lower()
        return d_str if d_str and d_str != "nr" else None

    # Deep copy existing records
    merged: List[Dict[str, Any]] = [dict(r) for r in existing_records]
    doi_index: Dict[str, int] = {}
    title_index: Dict[str, int] = {}

    for idx, r in enumerate(merged):
        doi = _norm_doi(r.get("doi"))
        if doi:
            doi_index[doi] = idx
        nt = _norm_t(r.get("title"))
        if nt:
            title_index[nt] = idx

    conflicts: List[Dict[str, Any]] = []

    for new_r in new_records:
        rec_copy = dict(new_r)
        new_doi = _norm_doi(rec_copy.get("doi"))
        new_nt = _norm_t(rec_copy.get("title"))

        matched_idx = None
        if new_doi and new_doi in doi_index:
            matched_idx = doi_index[new_doi]
        elif new_nt and new_nt in title_index:
            matched_idx = title_index[new_nt]

        if matched_idx is not None:
            target = merged[matched_idx]
            # 1. Preserve and union source databases
            existing_sources = target.get("source_databases", [])
            incoming_sources = rec_copy.get("source_databases", [])
            for s in incoming_sources:
                if s not in existing_sources:
                    existing_sources.append(s)
            target["source_databases"] = existing_sources

            # 2. Check for conflicting metadata (e.g. publication year)
            old_year = target.get("year")
            new_year = rec_copy.get("year")
            if old_year and new_year and old_year != new_year:
                conflict_entry = {
                    "title": target.get("title"),
                    "field": "year",
                    "existing_value": old_year,
                    "incoming_value": new_year,
                    "status": "CONFLICTING_METADATA"
                }
                conflicts.append(conflict_entry)
                if "metadata_conflicts" not in target:
                    target["metadata_conflicts"] = []
                target["metadata_conflicts"].append(conflict_entry)

            # 3. Metadata enrichment (fill missing fields without overwriting valid data)
            if not target.get("abstract") and rec_copy.get("abstract"):
                target["abstract"] = rec_copy["abstract"]
                target["abstract_source"] = incoming_sources[0] if incoming_sources else "CrossSourceEnriched"

            if (not target.get("doi") or target.get("doi") == "NR") and new_doi:
                target["doi"] = rec_copy.get("doi")
                doi_index[new_doi] = matched_idx

            if not target.get("url") and rec_copy.get("url"):
                target["url"] = rec_copy["url"]

            if not target.get("authors") and rec_copy.get("authors"):
                target["authors"] = rec_copy["authors"]

            existing_kw = target.get("keywords", [])
            for kw in rec_copy.get("keywords", []):
                if kw not in existing_kw:
                    existing_kw.append(kw)
            target["keywords"] = existing_kw

            # Check metadata completeness
            has_title = bool(target.get("title"))
            has_abs = bool(target.get("abstract"))
            has_authors = bool(target.get("authors"))
            if has_title and has_abs and has_authors:
                target["metadata_status"] = "FULL_METADATA"
            elif has_title and has_abs:
                target["metadata_status"] = "TITLE_ABSTRACT"
            elif has_title and has_authors:
                target["metadata_status"] = "TITLE_AUTHOR"
            elif has_title:
                target["metadata_status"] = "TITLE_ONLY"

        else:
            # Title-only or new candidate record: retain in corpus
            has_title = bool(rec_copy.get("title"))
            has_abs = bool(rec_copy.get("abstract"))
            has_authors = bool(rec_copy.get("authors"))
            if has_title and has_abs and has_authors:
                rec_copy["metadata_status"] = "FULL_METADATA"
            elif has_title and has_abs:
                rec_copy["metadata_status"] = "TITLE_ABSTRACT"
            elif has_title and has_authors:
                rec_copy["metadata_status"] = "TITLE_AUTHOR"
            elif has_title:
                rec_copy["metadata_status"] = "TITLE_ONLY"

            new_idx = len(merged)
            merged.append(rec_copy)
            if new_doi:
                doi_index[new_doi] = new_idx
            if new_nt:
                title_index[new_nt] = new_idx

    # Calculate source distribution and unique contributions
    source_dist: Dict[str, int] = {}
    unique_contribs: Dict[str, int] = {}

    for r in merged:
        sources = r.get("source_databases", [])
        for s in sources:
            source_dist[s] = source_dist.get(s, 0) + 1
        if len(sources) == 1:
            unique_contribs[sources[0]] = unique_contribs.get(sources[0], 0) + 1

    for s in source_dist:
        if s not in unique_contribs:
            unique_contribs[s] = 0

    return {
        "merged_records": merged,
        "raw_count": len(existing_records) + len(new_records),
        "unique_count": len(merged),
        "source_distribution": source_dist,
        "source_unique_contributions": unique_contribs,
        "conflicts": conflicts
    }


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
    parser.add_argument("-s", "--source", choices=["CNKI", "Wanfang", "VIP", "WoS", "Scopus", "EndNote", "RIS", "auto"], default="auto", help="Source database identifier override (default: auto)")
    
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
