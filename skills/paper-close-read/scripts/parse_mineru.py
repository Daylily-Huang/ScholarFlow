# -*- coding: utf-8 -*-
"""Conservative MinerU Markdown parser. Never repairs scientific values automatically."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def parse_document(text, filename="paper.md", paper_id=None):
    lines = text.splitlines(keepends=True)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    data = {"schema_version": 2, "paper_id": paper_id or "paper-" + digest[:20],
            "front": {"title": Path(filename).stem},
            "source": {"file": Path(filename).name, "sha256": digest,
                       "locator_basis": "Markdown lines; PDF page mapping requires verification"},
            "sections": [], "fixes": [], "warnings": []}
    current = None
    counts = {}

    def section(name, level):
        nonlocal current
        current = {"name": name, "level": level, "kind": "body", "items": []}
        data["sections"].append(current)

    def add(kind, start, end, **extra):
        if current is None:
            section("正文起始", 1)
        raw = "".join(lines[start:end])
        fingerprint = hashlib.sha256((kind + "\0" + raw).encode("utf-8")).hexdigest()[:16]
        counts[fingerprint] = counts.get(fingerprint, 0) + 1
        item = {"t": kind, "id": "b-" + fingerprint + "-" + str(counts[fingerprint]),
                "raw": raw, "source": {"file": Path(filename).name, "line_start": start + 1,
                "line_end": end, "pdf_page": None, "printed_page": None, "status": "unverified"}}
        item.update(extra)
        current["items"].append(item)
        if re.search(r"[Æ¼�]", raw):
            data["warnings"].append({"id": item["id"], "message": "疑似 OCR 字符，保留原样；须看原页确认"})

    i = 0
    title_seen = False
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", s)
        if heading:
            level, name = len(heading[1]), heading[2]
            if not title_seen and level == 1:
                data["front"]["title"] = name
                title_seen = True
            section(name, level)
            i += 1
            continue
        start = i
        if s.startswith("$$"):
            if not (len(s) > 4 and s.endswith("$$")):
                i += 1
                while i < len(lines) and "$$" not in lines[i]:
                    i += 1
                if i == len(lines):
                    raise ValueError(f"Unclosed formula at line {start + 1}")
            i += 1
            raw = "".join(lines[start:i]).strip()
            add("eq", start, i, latex=raw[2:-2].strip())
        elif s.lower().startswith("<table"):
            while i < len(lines) and "</table>" not in lines[i].lower():
                i += 1
            if i == len(lines):
                raise ValueError(f"Unclosed table at line {start + 1}")
            i += 1
            add("table", start, i)
        elif re.match(r"^!\[", s):
            m = re.fullmatch(r"!\[([^\]]*)\]\((.+?)\)", s)
            if m:
                add("figure", i, i + 1, src=m[2], caption=m[1])
            else:
                add("p", i, i + 1, en=s)
            i += 1
        else:
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(
                    r"^(#{1,6}\s|\$\$|!\[|<table)", lines[i].strip(), re.I):
                i += 1
            add("p", start, i, en="".join(lines[start:i]).strip())
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("markdown", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--paper-id", help="Stable DOI or identifier; never reuse for a different paper")
    args = ap.parse_args()
    # newline preservation lets the source validator compare complete original spans.
    with args.markdown.open(encoding="utf-8-sig", newline="") as f:
        text = f.read()
    data = parse_document(text, args.markdown.name, args.paper_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"sections": len(data["sections"]),
                      "blocks": sum(len(s["items"]) for s in data["sections"]),
                      "warnings": len(data["warnings"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
