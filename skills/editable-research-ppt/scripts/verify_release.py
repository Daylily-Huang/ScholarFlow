"""Read-only integrity check for the portable package, using only stdlib."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def package_files(root):
    return {
        p.relative_to(root).as_posix(): p
        for p in root.rglob('*')
        if p.is_file()
        and not any(x in {'.git', '__pycache__'} for x in p.relative_to(root).parts)
        and p.suffix != '.pyc' and p.name not in {'.DS_Store', 'Thumbs.db', 'SHA256SUMS.txt'}
        and not p.name.startswith('~$')
    }


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root=ROOT):
    root = Path(root).resolve()
    errors = []
    actual = package_files(root)
    expected = {}
    try:
        for line in (root / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
            hash_value, name = line.split('  ', 1)
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
                raise ValueError(f'unsafe manifest path: {name}')
            if name in expected or len(hash_value) != 64 or any(c not in '0123456789abcdef' for c in hash_value):
                raise ValueError(f'invalid or duplicate manifest entry: {name}')
            expected[name] = hash_value
        for name in sorted(expected.keys() - actual.keys()):
            errors.append(f'missing: {name}')
        for name in sorted(actual.keys() - expected.keys()):
            errors.append(f'not in manifest: {name}')
        for name in sorted(expected.keys() & actual.keys()):
            if digest(actual[name]) != expected[name]:
                errors.append(f'hash mismatch: {name}')
        system = json.loads((root / 'assets/template-system.json').read_text(encoding='utf-8'))
        version = system['version']
        snapshot = json.loads((root / f'references/v{version}-hashes.json').read_text(encoding='utf-8'))
        if snapshot['version'] != version:
            errors.append('snapshot version mismatch')
        standard = json.loads((root / 'references/approved-standard.json').read_text(encoding='utf-8'))
        for group in [snapshot['sha256'], standard['design_files'], standard['approved_examples'],
                      standard.get('current_examples', {})]:
            for name, hash_value in group.items():
                if name not in actual or digest(actual[name]) != hash_value:
                    errors.append(f'snapshot/standard mismatch: {name}')
    except (OSError, ValueError, KeyError) as e:
        errors.append(str(e))
    return {'ok': not errors, 'files': len(actual), 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    result = verify(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
