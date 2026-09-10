#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
download_oa_papers.py
---------------------
批量自动下载合法开放获取 (Open Access, OA) 学术文献 PDF，
并执行严格的文件二进制魔数检验 (%PDF-) 与完整性审计。

适用于 literature-discovery-acquisition Skill 的 Stage 8 全文获取环节。
无需外部三方依赖，完全基于 Python 标准库。
"""

import os
import sys
import json
import csv
import re
import time
import argparse
import urllib.request
import urllib.error
import urllib.parse

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 (Academic Retrieval Bot; mailto:academic_support@openacademic.org)"
MIN_PDF_BYTES = 10240  # 10 KB


def sanitize_filename(title, authors=None, year=None, doc_type=None, degree_level=None):
    """
    生成规范化文件名:
    普通文献: <Year>_<FirstAuthor>_<TitleSlug>.pdf
    学位论文: <Year>_<DegreeLevel/Thesis>_<FirstAuthor>_<TitleSlug>.pdf
    """
    first_author = "Unknown"
    if authors and len(authors) > 0:
        raw_author = authors[0]
        parts = re.split(r'[, ]+', str(raw_author).strip())
        if parts:
            first_author = parts[0]
    
    first_author = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fa5]', '', first_author)
    yr = str(year).strip() if year else "UnknownYear"
    
    # 学位论文前缀
    type_prefix = ""
    if doc_type and "thesis" in str(doc_type).lower():
        if degree_level and ("phd" in str(degree_level).lower() or "doctor" in str(degree_level).lower() or "博士" in str(degree_level)):
            type_prefix = "PhD_"
        elif degree_level and ("master" in str(degree_level).lower() or "硕士" in str(degree_level)):
            type_prefix = "Master_"
        else:
            type_prefix = "Thesis_"

    # 标题清洗
    clean_title = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fa5\s]', '', str(title or "paper"))
    slug_words = [w for w in clean_title.split() if len(w) > 1][:6]
    slug = "_".join(slug_words) if slug_words else "document"
    slug = slug[:50]
    
    return f"{yr}_{type_prefix}{first_author}_{slug}.pdf"


def build_csl_item(rec, saved_filename=None):
    """
    构建符合 CSL-JSON 规范的文献对象，供 Zotero 原生导入与附件关联
    """
    doc_type = rec.get("document_type", "Article")
    csl_type = "article-journal"
    if doc_type and "thesis" in str(doc_type).lower():
        csl_type = "thesis"
    elif doc_type and "conference" in str(doc_type).lower():
        csl_type = "paper-conference"
    elif doc_type and "chapter" in str(doc_type).lower():
        csl_type = "chapter"
    elif doc_type and "book" in str(doc_type).lower():
        csl_type = "book"

    authors_csl = []
    raw_authors = rec.get("authors", [])
    if isinstance(raw_authors, list):
        for a in raw_authors:
            parts = re.split(r'[, ]+', str(a).strip())
            if len(parts) >= 2:
                authors_csl.append({"family": parts[0], "given": " ".join(parts[1:])})
            elif parts:
                authors_csl.append({"literal": parts[0]})
    elif isinstance(raw_authors, str) and raw_authors:
        authors_csl.append({"literal": raw_authors})

    csl = {
        "id": str(rec.get("id", "item")),
        "type": csl_type,
        "title": str(rec.get("title", "")),
        "author": authors_csl,
    }

    if rec.get("year"):
        try:
            csl["issued"] = {"date-parts": [[int(rec["year"])]]}
        except (ValueError, TypeError):
            pass

    if csl_type == "thesis":
        if rec.get("institution"):
            csl["publisher"] = str(rec["institution"])
        if rec.get("degree_level"):
            csl["genre"] = f"{rec['degree_level']} Thesis"
    else:
        if rec.get("journal"):
            csl["container-title"] = str(rec["journal"])

    if rec.get("doi") and rec["doi"] != "NR":
        csl["DOI"] = str(rec["doi"])
        csl["URL"] = f"https://doi.org/{rec['doi']}"
    elif rec.get("url"):
        csl["URL"] = str(rec["url"])

    if rec.get("abstract") and rec["abstract"] != "Not available":
        csl["abstract"] = str(rec["abstract"])

    if rec.get("keywords"):
        kws = rec["keywords"]
        csl["keyword"] = ", ".join(kws) if isinstance(kws, list) else str(kws)

    if saved_filename:
        csl["file"] = saved_filename

    return csl


def query_openalex_oa(doi):
    """
    通过 OpenAlex API 探测 DOI 的合法 OA 直链
    """
    if not doi or doi == "NR" or "10." not in doi:
        return None, None
    
    clean_doi = doi.lower().strip()
    if clean_doi.startswith("https://doi.org/"):
        clean_doi = clean_doi.replace("https://doi.org/", "")
    elif clean_doi.startswith("doi:"):
        clean_doi = clean_doi.replace("doi:", "")
        
    api_url = f"https://api.openalex.org/works/https://doi.org/{urllib.parse.quote(clean_doi)}"
    req = urllib.request.Request(api_url, headers={"User-Agent": USER_AGENT})
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                oa_info = data.get("open_access", {})
                best_oa = data.get("best_oa_location") or {}
                
                pdf_url = best_oa.get("pdf_url")
                is_oa = oa_info.get("is_oa", False)
                oa_status = oa_info.get("oa_status", "closed")
                
                # 如果 best_oa 没有 pdf_url，检查 primary_location
                if not pdf_url and data.get("primary_location"):
                    pdf_url = data["primary_location"].get("pdf_url")
                
                return pdf_url, oa_status
    except Exception as e:
        # 网络波动或未收录
        pass
    
    return None, "closed"


def verify_pdf_integrity(filepath):
    """
    严格核验文件是否为真实未损坏的有效 PDF:
    1. 前 5 字节必须是 %PDF-
    2. 文件体量必须 >= 10 KB
    """
    if not os.path.exists(filepath):
        return False, "File does not exist"
    
    size = os.path.getsize(filepath)
    if size < MIN_PDF_BYTES:
        return False, f"File too small ({size} bytes < {MIN_PDF_BYTES} bytes limit)"
    
    try:
        with open(filepath, "rb") as f:
            header = f.read(5)
            if header != b"%PDF-":
                return False, f"Invalid magic bytes ({header!r}), expected b'%PDF-'"
    except Exception as e:
        return False, f"Read error: {str(e)}"
        
    return True, "Valid PDF"


def download_file(url, target_path, timeout=30):
    """
    流式安全下载文件
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response, open(target_path, 'wb') as out_file:
            # 检查响应头
            content_type = response.headers.get("Content-Type", "")
            if "text/html" in content_type.lower():
                # 很多反爬/登录页会返回 200 HTML
                pass
            
            # 分块下载
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                out_file.write(chunk)
                
        # 下载完毕核验
        valid, reason = verify_pdf_integrity(target_path)
        if not valid:
            if os.path.exists(target_path):
                os.remove(target_path)
            return False, f"Integrity check failed: {reason}"
            
        return True, "Success"
    except Exception as e:
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except OSError:
                pass
        return False, str(e)


#: Envelope keys that carry a usable candidate list, in reading order.
_CANDIDATE_LIST_KEYS = ("records", "candidates", "literature_records", "items")

#: Envelope keys that indicate the producer reported a failure.
_FAILURE_STATUS_KEYS = ("status", "overall_discovery_status")
_FAILURE_STATUS_VALUES = {"FAILED", "INPUT_REQUIRED", "INVALID_PARAMETER"}


class InputContractError(Exception):
    """Raised when the input structure cannot be interpreted as a record list."""


def load_candidate_records(input_path):
    """Read a candidate list from a discovery JSON or CSV export.

    Three outcomes are deliberately distinguished, because conflating them is
    what let a silent no-op masquerade as success (R06 follow-up):

    * unrecognised structure / parse failure -> :class:`InputContractError`
    * upstream reported a failure            -> ``([] , "FAILED_UPSTREAM")``
    * genuinely empty result                 -> ``([] , "EMPTY")``

    Returns:
        ``(records, state)`` where state is ``"OK"``, ``"EMPTY"`` or
        ``"FAILED_UPSTREAM"``.
    """
    if input_path.endswith('.json'):
        with open(input_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        if isinstance(raw, list):
            return raw, ("OK" if raw else "EMPTY")
        if not isinstance(raw, dict):
            raise InputContractError(
                "JSON root must be an object or array, got %s" % type(raw).__name__
            )
        for status_key in _FAILURE_STATUS_KEYS:
            status_value = raw.get(status_key)
            if isinstance(status_value, str) and status_value.upper() in _FAILURE_STATUS_VALUES:
                return [], "FAILED_UPSTREAM"
        for key in _CANDIDATE_LIST_KEYS:
            if key in raw:
                value = raw[key]
                if not isinstance(value, list):
                    raise InputContractError("'%s' must be a list, got %s" % (key, type(value).__name__))
                return value, ("OK" if value else "EMPTY")
        raise InputContractError(
            "No candidate list found. Recognised keys: %s. Present keys: %s"
            % (", ".join(_CANDIDATE_LIST_KEYS), ", ".join(sorted(raw.keys())) or "(none)")
        )

    if input_path.endswith('.csv'):
        records = []
        with open(input_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            if not fieldnames:
                raise InputContractError("CSV has no header row")
            for row in reader:
                if "authors" in row and isinstance(row["authors"], str):
                    row["authors"] = [a.strip() for a in row["authors"].split(";") if a.strip()]
                records.append(row)
        return records, ("OK" if records else "EMPTY")

    raise InputContractError("Unsupported file format: %s" % input_path)


def run_pipeline(input_path, output_dir, max_downloads=None):
    os.makedirs(output_dir, exist_ok=True)

    # 1. Parse input records. Not understanding the input is an error; an empty
    #    but well-formed result is not, and a failed upstream is preserved.
    try:
        records, input_state = load_candidate_records(input_path)
    except InputContractError as exc:
        print(f"[-] INPUT_CONTRACT_ERROR: {exc}")
        print("[-] Refusing to report success: the input was not understood.")
        return 3
    except (ValueError, OSError) as exc:
        print(f"[-] INPUT_CONTRACT_ERROR: cannot read {input_path}: {exc}")
        return 3

    print(f"[*] Loaded {len(records)} candidate records from {input_path}")

    if input_state == "FAILED_UPSTREAM":
        print("[-] UPSTREAM_FAILED: the discovery run did not succeed; no acquisition attempted.")
        return 2
    if input_state == "EMPTY":
        print("[!] NO_PROCESSABLE_RECORDS: input is valid but contains no candidates.")
        print("[!] Nothing was downloaded. This is not a completed acquisition.")
        return 0

    
    ledger = []
    csl_library = []
    downloaded_count = 0
    paywalled_count = 0
    failed_count = 0

    for idx, rec in enumerate(records):
        if max_downloads and downloaded_count >= max_downloads:
            print(f"[!] Reached max download limit: {max_downloads}")
            break

        rec_id = rec.get("id", f"REC{idx+1:03d}")
        title = rec.get("title", "Untitled")
        authors = rec.get("authors", [])
        year = rec.get("year")
        doi = rec.get("doi", "NR")
        status = rec.get("screening_status", "Include")
        
        # 只下载 Include 与 Uncertain
        if status not in ["Include", "Uncertain"]:
            continue

        print(f"\n[{idx+1}/{len(records)}] Processing: {rec_id} - {title[:50]}...")
        
        pdf_url = rec.get("pdf_url")
        oa_status = rec.get("oa_status", "unknown")
        
        # 如果未提供 pdf_url，尝试通过 API 探测
        if not pdf_url and doi and doi != "NR":
            print(f"    Resolving OA status via OpenAlex for DOI: {doi}")
            resolved_url, resolved_status = query_openalex_oa(doi)
            if resolved_url:
                pdf_url = resolved_url
                oa_status = resolved_status
                print(f"    Found OA link ({oa_status}): {pdf_url[:60]}...")
            else:
                oa_status = resolved_status

        ledger_entry = {
            "id": rec_id,
            "title": title,
            "authors": authors,
            "year": year,
            "doi": doi,
            "pdf_url": pdf_url,
            "status": "PAYWALLED",
            "saved_file": None,
            "note": ""
        }

        if pdf_url:
            doc_type = rec.get("document_type")
            degree_level = rec.get("degree_level")
            filename = sanitize_filename(title, authors, year, doc_type, degree_level)
            target_path = os.path.join(output_dir, filename)
            
            print(f"    Downloading to: {filename}")
            ok, msg = download_file(pdf_url, target_path)
            if ok:
                downloaded_count += 1
                ledger_entry["status"] = "OA_DOWNLOADED" if oa_status != "green" else "PREPRINT_AVAILABLE"
                ledger_entry["saved_file"] = filename
                ledger_entry["note"] = f"Downloaded successfully ({msg})"
                print(f"    [+] Success: {filename}")

                # 1. 生成单篇配对的 CSL-JSON
                csl_item = build_csl_item(rec, saved_filename=filename)
                csl_library.append(csl_item)
                
                base_name = os.path.splitext(filename)[0]
                csl_single_path = os.path.join(output_dir, f"{base_name}.csl.json")
                with open(csl_single_path, 'w', encoding='utf-8') as f_csl:
                    json.dump(csl_item, f_csl, indent=2, ensure_ascii=False)
            else:
                failed_count += 1
                # 三级状态分类（stage8_oa_download.md 五）：实质 OA 被反爬拦截时
                # 必须标 OA_BOT_BLOCKED 并给免费 DOI 指引，严禁误导用户付费。
                if str(oa_status).lower() in ("gold", "hybrid", "bronze", "diamond", "green"):
                    ledger_entry["status"] = "OA_BOT_BLOCKED"
                    ledger_entry["note"] = (f"实质开放获取({oa_status})但反爬/网络拦截: {msg}. "
                                            "浏览器打开 DOI 直链即可免费下载")
                else:
                    ledger_entry["status"] = "DOWNLOAD_FAILED"
                    ledger_entry["note"] = f"Download failed: {msg}"
                print(f"    [-] Failed ({ledger_entry['status']}): {msg}")
        else:
            paywalled_count += 1
            ledger_entry["status"] = "PAYWALLED"
            ledger_entry["note"] = "No open-access full-text link detected. Requires subscription/institutional login."
            print(f"    [!] Paywalled: Requires institutional access")

        ledger.append(ledger_entry)
        time.sleep(0.5)  # 礼貌请求间隔

    # 2. 输出台账 (JSON & Markdown)
    ledger_json_path = os.path.join(output_dir, "download_ledger.json")
    with open(ledger_json_path, 'w', encoding='utf-8') as f:
        json.dump(ledger, f, indent=2, ensure_ascii=False)

    # 3. 输出全局 Zotero 导入集合 CSL-JSON
    if csl_library:
        zotero_csl_path = os.path.join(output_dir, "zotero_import.csl.json")
        with open(zotero_csl_path, 'w', encoding='utf-8') as f_zot:
            json.dump(csl_library, f_zot, indent=2, ensure_ascii=False)
        print(f"    [+] Generated Zotero Watch Folder pool: {zotero_csl_path} ({len(csl_library)} items)")

    ledger_md_path = os.path.join(output_dir, "download_ledger.md")
    with open(ledger_md_path, 'w', encoding='utf-8') as f:
        f.write("# 全文文献获取台账 (Full-Text Acquisition Ledger)\n\n")
        f.write(f"- **总审查记录数**：{len(ledger)}\n")
        f.write(f"- **已下载成功 (OA / 预印本)**：{downloaded_count}\n")
        f.write(f"- **需商业权限 (Paywalled)**：{paywalled_count}\n")
        f.write(f"- **下载受阻失败**：{failed_count}\n\n")
        f.write("## 详细文献获取明细\n\n")
        f.write("| ID | 标题 | 第一作者 | 年份 | DOI | 获取状态 | 本地文件名 / 访问指引 |\n")
        f.write("|---|---|---|:---:|---|:---:|---|\n")
        for entry in ledger:
            st = entry["status"]
            if st in ["OA_DOWNLOADED", "PREPRINT_AVAILABLE"]:
                badge = "🟢 已下载"
            elif st == "PAYWALLED":
                badge = "🔒 付费墙"
            elif st == "OA_BOT_BLOCKED":
                badge = "🟠 OA-反爬拦截(免费)"
            else:
                badge = "🔴 失败"
            author = entry["authors"][0] if entry.get("authors") else "Unknown"
            doi_link = f"[{entry['doi']}](https://doi.org/{entry['doi']})" if entry.get("doi") and entry["doi"] != "NR" else "NR"
            if entry["saved_file"]:
                loc = entry["saved_file"]
            elif st == "OA_BOT_BLOCKED":
                loc = "浏览器打开上方 DOI 直链免费下载"
            elif st == "PAYWALLED":
                loc = "校园网 IP 内访问 DOI / 馆际互借(CALIS/NSTL)"
            else:
                loc = entry["note"]
            f.write(f"| {entry['id']} | {entry['title']} | {author} | {entry['year']} | {doi_link} | {badge} | {loc} |\n")

    # 4. 台账覆盖度自检 (Ledger Coverage Guard)：每一条 Include/Uncertain 输入
    #    记录必须出现在台账中并带三级状态之一；缺失即 FAIL（exit 2）。
    #    2026-09-06 端到端测试发现：无直链文献被静默跳过会导致台账残缺。
    eligible = [r for r in records if r.get("screening_status", "Include") in ["Include", "Uncertain"]]
    covered = {e.get("id") for e in ledger}
    missing = [r.get("id", "?") for r in eligible if r.get("id") not in covered]
    if missing:
        print(f"\n[!] LEDGER COVERAGE FAILURE: {len(missing)} 条 Include/Uncertain 记录未入台账: {missing[:10]}")
        print("    stage8_oa_download.md 五: 所有初筛合格文献必须归入三级状态之一。")
        coverage_ok = False
    else:
        coverage_ok = True
        print(f"\n[+] Ledger coverage check PASSED: {len(covered)}/{len(eligible)} eligible records classified.")

    print(f"\n[+] Pipeline completed!")
    print(f"    Downloaded: {downloaded_count}, Paywalled: {paywalled_count}, Failed: {failed_count}")
    print(f"    Ledger saved to: {ledger_md_path}")
    return 0 if coverage_ok else 2


def main():
    parser = argparse.ArgumentParser(description="Download Open Access academic papers and audit integrity.")
    parser.add_argument("-i", "--input", required=True, help="Path to candidate literature JSON or CSV file")
    parser.add_argument("-o", "--output-dir", default="papers/downloads", help="Directory to save downloaded PDFs")
    parser.add_argument("--max-downloads", type=int, default=None, help="Maximum number of papers to download")

    args = parser.parse_args()
    sys.exit(run_pipeline(args.input, args.output_dir, args.max_downloads))


if __name__ == "__main__":
    main()
