"""Source-preparation checks; flags are review candidates, never automatic repairs."""
import hashlib
import re


ASPECTS = ('structure', 'terminology', 'citations')


def text(value):
    return isinstance(value, str) and bool(value.strip())


def texts(value):
    return isinstance(value, list) and bool(value) and all(text(x) for x in value)


def source_risks(data):
    """Stable findings over original blocks. Deliberately conservative, not exhaustive."""
    risks = []
    for section in data.get('sections', []):
        previous = None
        auxiliary = section.get('kind', 'body') != 'body' or section.get('name', '').casefold() in {
            'references', 'bibliography', '参考文献', '致谢', 'acknowledgements', 'acknowledgments'}
        for item in section.get('items', []):
            if item.get('t') != 'p' or auxiliary:
                previous = None
                continue
            raw = item.get('raw', '').strip()
            def add(kind, excerpt, offset=0, refs=None):
                refs = refs or [item['id']]
                key = '|'.join([kind, *refs, str(offset), excerpt])
                risks.append({'id': 'risk-' + hashlib.sha256(key.encode('utf-8')).hexdigest()[:16],
                              'kind': kind, 'refs': refs, 'excerpt': excerpt})
            # Digits attached to words can also be legitimate names (IL6, H2O, p53).
            # A source run only clears this lexical flag when it explicitly styles
            # the digit as a superscript and links to an existing source target.
            runs = item.get('source', {}).get('inline_runs', [])
            known = []
            if isinstance(runs, list) and all(isinstance(r, dict) and isinstance(r.get('text'), str) for r in runs):
                at = 0
                for run in runs:
                    if 'sup' in run.get('styles', []) and run.get('target'):
                        known.append((at, at + len(run['text'])))
                    at += len(run['text'])
            for match in re.finditer(r'[A-Za-z]{2,}(\d+(?:[,–−-]\d+)*)', raw):
                if not any(a <= match.start(1) and match.end(1) <= b for a, b in known):
                    add('word-number', match.group(), match.start())
            for match in re.finditer(r'[A-Za-z]{2,}-\s+[A-Za-z]{2,}', raw):
                add('broken-word', match.group(), match.start())
            if previous and raw and re.match(r'^[a-z]', raw):
                before = previous['raw'].strip()
                if before and not re.search(r'[.!?。！？:;][\s\)\]”’"\']*$', before):
                    add('paragraph-boundary', before[-65:] + ' | ' + raw[:65],
                        refs=[previous['id'], item['id']])
            previous = item
    return risks


def quality_errors(data, records, guide, required=False):
    errors, warnings = [], []
    items = {i['id']: i for s in data['sections'] for i in s['items']}
    terms = guide.get('terminology', [])
    registry, by_form = {}, {}
    if not isinstance(terms, list):
        errors.append('guide.terminology must be an array'); terms = []
    for n, term in enumerate(terms):
        where = f'guide.terminology[{n}]'
        if (not isinstance(term, dict) or not all(text(term.get(k)) for k in ('id', 'preferred_zh', 'identity'))
            or not texts(term.get('forms')) or not texts(term.get('evidence')) or not texts(term.get('refs'))
            or any(r not in items for r in term.get('refs', []))
            or not isinstance(term.get('aliases', []), list) or any(not text(x) for x in term.get('aliases', []))):
            errors.append(where + ' needs id/forms/preferred_zh/identity/aliases/evidence and valid refs'); continue
        if term['id'] in registry:
            errors.append('Duplicate terminology id: ' + term['id']); continue
        registry[term['id']] = term
        for form in term['forms']:
            by_form.setdefault(form.casefold().strip(), []).append(term)
    # Check authored term pairs only; ordinary prose may legitimately use pronouns
    # or omit a repeated name. A synonym is not a mistranslation by definition.
    for record in records:
        for pair in record.get('terms', []):
            candidates = by_form.get(pair.get('en', '').casefold().strip(), [])
            tid = pair.get('term_id')
            if tid is not None:
                if not text(tid) or tid not in registry or registry[tid] not in candidates:
                    errors.append('Unknown or mismatched term_id: ' + record['id']); continue
                candidates = [registry[tid]]
            if len(candidates) > 1:
                errors.append('Ambiguous term needs term_id for its sense: ' + record['id'])
            elif candidates and pair.get('zh') not in [candidates[0]['preferred_zh'], *candidates[0].get('aliases', [])]:
                errors.append('Translation term conflicts with terminology registry: ' + record['id'] + ' / ' + pair['en'])
    risks = source_risks(data)
    review = data.get('source_review')
    if review is None:
        if required: errors.append('New complete reader requires fulltext.source_review')
        return errors, warnings, risks
    if not isinstance(review, dict):
        return errors + ['fulltext.source_review must be an object'], warnings, risks
    for aspect in ASPECTS:
        entry = review.get(aspect)
        if (not isinstance(entry, dict) or entry.get('status') not in ('checked', 'not_applicable', 'pending')
            or not texts(entry.get('evidence')) or not text(entry.get('note'))):
            errors.append('source_review.' + aspect + ' needs status, evidence and a specific note'); continue
        if entry['status'] == 'pending':
            (errors if required else warnings).append('Source review pending: ' + aspect)
        if required and aspect == 'terminology' and entry['status'] == 'checked' and not registry:
            errors.append('Checked terminology review requires guide.terminology; explain not_applicable if none')
    decisions = review.get('decisions', [])
    resolved = set()
    risk_ids = {r['id'] for r in risks}
    if not isinstance(decisions, list):
        errors.append('source_review.decisions must be an array'); decisions = []
    for entry in decisions:
        if (not isinstance(entry, dict) or not text(entry.get('risk_id')) or entry.get('risk_id') not in risk_ids
            or not text(entry.get('resolution')) or not texts(entry.get('evidence'))):
            errors.append('Source risk decision needs a current risk_id, resolution and evidence'); continue
        if entry['risk_id'] in resolved: errors.append('Duplicate source risk decision: ' + entry['risk_id'])
        resolved.add(entry['risk_id'])
    if required:
        for risk in risks:
            if risk['id'] not in resolved:
                errors.append('Unreviewed source risk: ' + risk['id'] + ' / ' + risk['kind'])
    # Explicit human-found issues matter even when no heuristic detects them.
    issues = review.get('issues', [])
    if not isinstance(issues, list):
        errors.append('source_review.issues must be an array'); issues = []
    seen = set()
    for issue in issues:
        if (not isinstance(issue, dict) or not text(issue.get('id')) or issue['id'] in seen
            or issue.get('aspect') not in ASPECTS or issue.get('status') not in ('open', 'resolved')
            or not texts(issue.get('refs')) or any(r not in items for r in issue.get('refs', []))
            or not text(issue.get('description')) or not texts(issue.get('evidence'))):
            errors.append('Invalid or duplicate source review issue'); continue
        seen.add(issue['id'])
        if issue['status'] == 'resolved' and not text(issue.get('resolution')):
            errors.append('Resolved source issue needs its resolution: ' + issue['id'])
        if issue['status'] == 'open':
            (errors if required else warnings).append('Source issue still open: ' + issue['id'])
    return errors, warnings, risks
