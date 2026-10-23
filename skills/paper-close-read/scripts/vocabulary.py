"""Validate authored vocabulary against the paragraph, without inventing meanings."""
import html
import re
import unicodedata


def normalized(text):
    text = unicodedata.normalize('NFKC', html.unescape(text)).casefold()
    text = re.sub('[\u2010-\u2015\u2212]', '-', text)
    return ' '.join(text.split())


def occurs(phrase, source):
    phrase = normalized(phrase)
    return bool(phrase and re.search(r'(?<![a-z0-9])' + re.escape(phrase) + r'(?![a-z0-9])', normalized(source)))


def vocabulary_errors(record, source):
    errors, seen = [], set()
    for n, entry in enumerate(record.get('vocabulary', [])):
        where = record['id'] + '.vocabulary[' + str(n) + ']'
        en, zh = entry.get('en', ''), entry.get('zh', '')
        if not en.strip() or not zh.strip():
            errors.append(where + ' needs an English surface form and its contextual Chinese meaning')
            continue
        if len(en) > 140 or len(zh) > 400:
            errors.append(where + ' is too long for a vocabulary entry')
        if not occurs(en, source):
            errors.append(where + ' English word/phrase is absent from the original paragraph: ' + en)
        key = normalized(en)
        if key in seen:
            errors.append(where + ' repeats a vocabulary entry')
        seen.add(key)
    return errors
