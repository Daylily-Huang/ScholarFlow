"""Validate declared media provenance and embedded video bytes (stdlib only).

This is a bounded structural check, not a licence, scientific or playback audit.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import posixpath
import re
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
import xml.etree.ElementTree as ET


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_file(base, value):
    if not isinstance(value, str) or not value:
        raise ValueError('nonempty relative path required')
    rel = PurePosixPath(value)
    if rel.is_absolute() or '..' in rel.parts or '\\' in value or ':' in value:
        raise ValueError('unsafe relative path: ' + value)
    target = (base / value).resolve()
    if base not in target.parents or not target.is_file():
        raise ValueError('missing or escaping file: ' + value)
    return target


def checked_file(base, item, key, hash_key):
    p = local_file(base, item.get(key))
    expected = item.get(hash_key)
    if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected) or digest(p) != expected:
        raise ValueError('hash mismatch: ' + key)
    return p


def valid_url(value):
    return isinstance(value, str) and urlparse(value).scheme in ('http', 'https') and bool(urlparse(value).netloc)


def videos_in_package(path):
    by_slide = {}
    external = []
    with zipfile.ZipFile(path) as z:
        pns = 'http://schemas.openxmlformats.org/presentationml/2006/main'
        rns = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
        rels = {r.get('Id'): r for r in ET.fromstring(z.read('ppt/_rels/presentation.xml.rels'))}
        slides = ET.fromstring(z.read('ppt/presentation.xml')).find(f'{{{pns}}}sldIdLst')
        if slides is None:
            raise ValueError('presentation slide order missing')
        for number, slide in enumerate(slides, 1):
            relation = rels[slide.get(f'{{{rns}}}id')]
            if relation.get('TargetMode') == 'External' or not relation.get('Type', '').endswith('/slide'):
                raise ValueError('invalid presentation slide relationship')
            target = relation.get('Target', '')
            name = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('ppt', target))
            if name not in z.namelist():
                raise ValueError('missing slide part: ' + name)
            by_slide[number] = set()
            folder = posixpath.dirname(name)
            relfile = posixpath.join(folder, '_rels', posixpath.basename(name) + '.rels')
            if relfile not in z.namelist():
                continue
            for rel in ET.fromstring(z.read(relfile)):
                if rel.get('Type', '').rsplit('/', 1)[-1] not in ('video', 'media'):
                    continue
                target = rel.get('Target', '')
                if rel.get('TargetMode') == 'External':
                    external.append({'slide': number, 'target': target})
                    continue
                part = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(folder, target))
                by_slide[number].add(hashlib.sha256(z.read(part)).hexdigest())
    return by_slide, external


def audit(manifest, pptx=None):
    manifest = Path(manifest).resolve()
    base = manifest.parent
    errors = []
    count = 0
    try:
        doc = json.loads(manifest.read_text(encoding='utf-8-sig'))
        if not isinstance(doc, dict) or doc.get('version') != 1 or not isinstance(doc.get('assets'), list):
            raise ValueError('expected version=1 and assets array')
        by_slide, external = videos_in_package(pptx) if pptx else ({}, [])
        if external:
            errors.append('external media relationships: ' + json.dumps(external, ensure_ascii=False))
        ids = set()
        covered = set()
        for item in doc['assets']:
            count += 1
            ident = item.get('id') if isinstance(item, dict) else None
            try:
                if not isinstance(ident, str) or not ident.strip() or ident in ids:
                    raise ValueError('nonempty unique id required')
                ids.add(ident)
                checked_file(base, item, 'path', 'sha256')
                for key in ('origin', 'role', 'representation', 'editable'):
                    choices = {'origin': ('online','original','user'), 'role': ('illustration','concept_animation','evidence'),
                               'representation': ('image','native_shapes','video'), 'editable': ('native','source','replace_only')}
                    if item.get(key) not in choices[key]:
                        raise ValueError('invalid ' + key)
                if not isinstance(item.get('changes'), str) or not item['changes'].strip():
                    raise ValueError('changes required, use none when unchanged')
                pages = item.get('placements')
                if not isinstance(pages, list) or not pages or any(type(p) is not int or p < 1 for p in pages) or len(set(pages)) != len(pages):
                    raise ValueError('placements must be unique positive slide numbers')
                if pptx and any(p not in by_slide for p in pages):
                    raise ValueError('placement slide does not exist')
                if item['origin'] == 'online':
                    for key in ('author','license'):
                        if not isinstance(item.get(key), str) or not item[key].strip():
                            raise ValueError('online asset missing ' + key)
                    if not valid_url(item.get('source_url')) or not valid_url(item.get('license_url')):
                        raise ValueError('online asset needs source/license HTTP(S) URLs')
                if item['editable'] == 'native' and item['representation'] != 'native_shapes':
                    raise ValueError('image/video cannot claim native editability')
                if item['role'] == 'concept_animation':
                    if item.get('schematic') is not True or not isinstance(item.get('explanation'), str) or not item['explanation'].strip():
                        raise ValueError('concept animation needs schematic=true and explanation')
                    checked_file(base, item, 'source_path', 'source_sha256')
                    checked_file(base, item, 'static_fallback', 'fallback_sha256')
                if pptx and item['representation'] == 'video':
                    for page in pages:
                        if item['sha256'] not in by_slide[page]:
                            raise ValueError(f'declared video not embedded on slide {page}')
                        covered.add((page, item['sha256']))
            except (ValueError, TypeError, OSError) as exc:
                errors.append(f'asset {ident or count}: {exc}')
        for page, hashes in by_slide.items():
            for value in hashes:
                if (page, value) not in covered:
                    errors.append(f'undeclared embedded video on slide {page}: {value}')
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        errors.append(str(exc))
    return {'ok': not errors, 'assets': count, 'errors': errors,
            'scope': 'Declared files, hashes, provenance fields, slide numbers and embedded video bytes; not licence truth, scientific validity or playback.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', required=True, type=Path)
    p.add_argument('--pptx', type=Path)
    args = p.parse_args()
    result = audit(args.manifest, args.pptx)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
