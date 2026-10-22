"""Validate source spans, coverage, IDs and evidence links. Not a scientific truth checker."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))


def validate(data, records, guide, source_text=None, allow_incomplete=False):
    errors, warnings = [], []
    if data.get("schema_version") != 2 or not data.get("paper_id"):
        errors.append("Expected schema_version 2 and a nonempty paper_id; reparse legacy JSON")
    items = [i for s in data.get("sections", []) for i in s["items"]]
    ids = [i["id"] for i in items]
    if not ids:
        errors.append("No source blocks")
    if len(ids) != len(set(ids)):
        errors.append("Duplicate source block IDs")
    tids = [r["id"] for r in records]
    if len(tids) != len(set(tids)):
        errors.append("Duplicate translation IDs")
    expected = {i["id"] for i in items if i["t"] == "p"}
    extra = set(tids) - expected
    if extra:
        errors.append("Unknown translation IDs: " + ', '.join(sorted(extra)))
    missing = expected - set(tids)
    if missing:
        (warnings if allow_incomplete else errors).append(f"Missing translations: {len(missing)}")
    for r in records:
        role = r.get("role", "body")
        if role not in {"body", "metadata", "reference", "supporting", "label"}:
            errors.append("Unknown paragraph role: " + r["id"])
        if role == "body" and (not isinstance(r.get("keys"), list) or not r["keys"] or any(not isinstance(k, str) or not k.strip() for k in r["keys"])):
            (warnings if allow_incomplete else errors).append("Body paragraph needs logic points: " + r["id"])
        if not isinstance(r.get("zh"), str) or not r.get("zh", "").strip() or (role == "body" and not str(r.get("note", "")).strip()):
            (warnings if allow_incomplete else errors).append("Translation/explanation missing: " + r["id"])
    if source_text is not None:
        digest = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        if digest != data.get("source", {}).get("sha256"):
            errors.append("Source SHA-256 mismatch")
        from parse_mineru import parse_document
        rebuilt = parse_document(source_text, data.get("source", {}).get("file", "paper.md"), data.get("paper_id"))
        original_items = [i for s in rebuilt["sections"] for i in s["items"]]
        if [(s["name"], s["level"]) for s in rebuilt["sections"]] != [(s["name"], s.get("level")) for s in data["sections"]]:
            errors.append("Section headings/order differ from source")
        fields = ("id", "t", "raw", "latex", "src", "caption")
        if [[i.get(k) for k in fields] for i in items] != [[i.get(k) for k in fields] for i in original_items]:
            errors.append("Source blocks removed, reordered, or altered")
        lines = source_text.splitlines(keepends=True)
        for i in items:
            s = i["source"]
            raw = ''.join(lines[s["line_start"] - 1:s["line_end"]])
            if raw != i["raw"]:
                errors.append("Source span altered: " + i["id"])
    else:
        warnings.append("Source Markdown bytes not checked in this run")
    if not guide.get('story'):
        if guide.get('format') == 'legacy':
            for key in ('question', 'answer', 'why', 'claims', 'limits'):
                if not guide.get(key):
                    (warnings if allow_incomplete else errors).append('Legacy guide missing: ' + key)
        else:
            (warnings if allow_incomplete else errors).append('New guide requires story.overview and story.walkthrough; legacy format must be explicit')
    for block in guide.get("claims", []) + guide.get("checks", []):
        if not block.get("refs"):
            errors.append("Claim/check needs evidence refs")
        for ref in block.get("refs", []):
            if ref not in ids:
                errors.append("Unknown evidence ref: " + ref)
    for claim in guide.get("claims", []):
        if not claim.get("title") or not claim.get("text"):
            errors.append("Claim needs title and text")
        if claim.get("kind", "作者解释") not in {"作者结果", "作者解释", "教学解释", "迁移假设"}:
            errors.append("Unknown claim kind")
    for check in guide.get("checks", []):
        if not check.get("question") or not check.get("answer"):
            errors.append("Check needs question and answer")
    for i in items:
        src = i.get("source", {})
        runs=src.get('inline_runs')
        if runs is not None:
            if not isinstance(runs,list) or any(not isinstance(r,dict) or not isinstance(r.get('text'),str) for r in runs):errors.append('Invalid inline source runs: '+i['id'])
            elif ''.join(r['text'] for r in runs)!=i['raw'].strip():errors.append('Inline source text differs from original: '+i['id'])
            else:
                for r in runs:
                    if any(x not in {'em','strong','sup','sub'} for x in r.get('styles',[])) or (r.get('target') and r['target'] not in ids):errors.append('Unsafe style or unknown source cross-reference: '+i['id'])
            if src.get('corrections'):errors.append('Inline source runs must be regenerated after display corrections: '+i['id'])
        page = src.get("pdf_page")
        if page is not None and (type(page) is not int or page < 1):
            errors.append("PDF page must be a positive integer: " + i["id"])
        if src.get("status") == "verified" and (not str(src.get("verification_note", "")).strip() or page is None):
            errors.append("Verified source needs PDF page and verification_note: " + i["id"])
        display_raw = i['raw']
        for correction in src.get('corrections', []):
            old, new = correction.get('old'), correction.get('new')
            if (i['t'] != 'p' or src.get('status') != 'verified' or not isinstance(old, str) or not old
                or not isinstance(new, str) or not new or not correction.get('reason')
                or type(correction.get('pdf_page')) is not int or correction['pdf_page'] < 1
                or display_raw.count(old) != 1):
                errors.append('Display correction needs a unique exact source match and verified PDF evidence: ' + i['id'])
            else:
                display_raw = display_raw.replace(old, new, 1)
    from render_mechanisms import SCENES
    mids = set()
    for mechanism in guide.get('mechanisms', []):
        mid = mechanism.get('id', '')
        if not isinstance(mid, str) or not mid.startswith('motion-') or mid in mids or mid in ids:
            errors.append('Mechanism needs unique motion- ID')
        mids.add(mid)
        if mechanism.get('scene') not in SCENES:
            errors.append('Unknown mechanism scene: ' + str(mechanism.get('scene')))
        if mechanism.get('anchor') not in ids:
            errors.append('Unknown mechanism anchor: ' + str(mechanism.get('anchor')))
        if not mechanism.get('refs') or any(ref not in ids for ref in mechanism.get('refs', [])):
            errors.append('Mechanism needs valid source refs')
        if not mechanism.get('title') or not mechanism.get('question'):
            errors.append('Mechanism needs title and reader question')
        if mechanism.get('scene') in {'argument_map', 'evidence_coding', 'repeated_measures', 'source_timeline', 'communication', 'text_focus'}:
            from render_mechanisms import validate_scene_data
            errors.extend(validate_scene_data(mechanism))
        if mechanism.get('scene')=='text_focus':
            quote=mechanism.get('visual',{}).get('quote','')
            if not quote or not any(quote in i['raw'] for i in items if i['id'] in mechanism.get('refs',[])):errors.append('Text focus quote must exactly match a referenced source block')
        stages = mechanism.get('stages')
        if not isinstance(stages, list) or len(stages)<2 or any(not isinstance(s,str) or not s.strip() for s in stages):
            errors.append('Mechanism needs explanatory stages')
    from render_concepts import validate_concepts
    errors.extend(validate_concepts(guide.get('concepts', []), ids))
    concept_ids = {c.get('id') for c in guide.get('concepts', []) if isinstance(c, dict)}
    for concept in guide.get('concepts', []):
        if isinstance(concept, dict) and concept.get('anchor', concept.get('refs', [None])[0] if concept.get('refs') else None) not in ids:
            errors.append('Unknown concept anchor')
    if guide.get('attribution') and (not isinstance(guide['attribution'], dict) or any(not isinstance(guide['attribution'].get(k), str) or not guide['attribution'][k].strip() for k in ['citation','url','license','changes'])):
        errors.append('Attribution needs citation/url/license/changes text')
    from render_further import validate_further
    errors.extend(validate_further(guide.get('further_reading', []), ids))
    if guide.get('story'):
        story = guide['story']
        overview = story.get('overview', {})
        mapped=overview.get('format')=='research-map'
        if overview.get('format') not in {None,'narrative','research-map'}:errors.append('Unknown overview format')
        if mapped:
            from render_story import RESEARCH_STEPS
            steps=overview.get('research_map',[])
            if not isinstance(steps,list) or [x.get('step') if isinstance(x,dict) else None for x in steps]!=[s[0] for s in RESEARCH_STEPS]:errors.append('Research map needs background/gap/question/method/findings/conclusion in order')
            else:
                for step in steps:
                    if not isinstance(step.get('text'),str) or not step['text'].strip():errors.append('Research map needs concrete text: '+step['step'])
                    if not isinstance(step.get('refs'),list) or not step['refs'] or any(r not in ids for r in step['refs']):errors.append('Research map needs valid source refs: '+step['step'])
                    if 'title' in step and (not isinstance(step['title'],str) or not step['title'].strip()):errors.append('Research map title must be text')
        for key in (('title','lead','takeaway') if mapped else ('title', 'lead', 'paragraphs', 'chain', 'takeaway')):
            if not overview.get(key): errors.append('Story overview missing: ' + key)
        if not story.get('walkthrough'): errors.append('Story needs a walkthrough')
        for block in [overview] + story.get('walkthrough', []):
            if not block.get('refs') or any(r not in ids for r in block['refs']):
                errors.append('Story needs valid source refs')
        for chapter in story.get('walkthrough', []):
            if any(c not in concept_ids for c in chapter.get('concepts', [])):
                errors.append('Story links unknown concept')
            for key in ('title', 'bridge', 'paragraphs', 'connection'):
                if not chapter.get(key): errors.append('Story chapter missing: ' + key)
            if any(m.get('id') not in mids for m in chapter.get('motions', [])):
                errors.append('Story links unknown mechanism')
            motion_ids = [m.get('id') for m in chapter.get('motions', [])]
            if len(motion_ids) != len(set(motion_ids)):
                errors.append('Duplicate mechanism in one story chapter')
        for block in [overview] + story.get('walkthrough', []):
            for key in (() if mapped else ('paragraphs', 'chain')) if block is overview else ('paragraphs',):
                value = block.get(key)
                if not isinstance(value, list) or not value or any(not isinstance(x, str) or not x.strip() for x in value):
                    errors.append('Story needs a nonempty text array: ' + key)
            for key in ('title', 'lead', 'takeaway') if block is overview else ('title', 'bridge', 'connection'):
                if not isinstance(block.get(key), str) or not block[key].strip():
                    errors.append('Story needs text: ' + key)
            if block.get('table'):
                table = block['table']
                head, rows = table.get('head', []), table.get('rows', [])
                if not head or not rows or any(len(row) != len(head) for row in rows) or any(not isinstance(x, str) for row in [head] + rows for x in row):
                    errors.append('Story table needs text cells and matching column counts')
        for metric in overview.get('metrics', []):
            if any(not isinstance(metric.get(k), str) or not metric[k].strip() for k in ('label', 'value', 'meaning')):
                errors.append('Story metric needs label/value/meaning text')
    unchecked = sum(i.get("source", {}).get("status") != "verified" for i in items)
    if unchecked:
        warnings.append(f"{unchecked}/{len(items)} source blocks have not been verified against original pages")
    return {"errors": errors, "warnings": warnings, "source_blocks": len(items),
            "paragraphs": len(expected), "translations": len(tids), "missing": sorted(missing)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("data", "translations", "guide"):
        ap.add_argument(name, type=Path)
    ap.add_argument("--source", type=Path)
    ap.add_argument("--allow-incomplete", action="store_true")
    args = ap.parse_args()
    values = [json.loads(p.read_text(encoding="utf-8-sig")) for p in (args.data, args.translations, args.guide)]
    source = None
    if args.source:
        with args.source.open(encoding="utf-8-sig", newline="") as f:
            source = f.read()
    report = validate(*values, source, args.allow_incomplete)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(bool(report["errors"]))


if __name__ == "__main__":
    main()
