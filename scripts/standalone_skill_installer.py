"""Install the extracted, checksummed bundle into an explicitly chosen skills directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_links(path):
    for p in [path, *path.parents]:
        if p.exists() or p.is_symlink():
            flags = getattr(p.lstat(), 'st_file_attributes', 0)
            if p.is_symlink() or flags & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0):
                raise ValueError('Linked paths are not accepted: ' + str(p))


def inventory(root):
    result = {}
    if not root.is_dir():
        return result
    for p in root.rglob('*'):
        reject_links(p)
        if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc':
            result[p.relative_to(root).as_posix()] = digest(p)
    return result


def overlaps(a, b):
    return a == b or a in b.parents or b in a.parents


def install(source, target, replace=False, backup=None):
    source, target = Path(source).absolute(), Path(target).expanduser().absolute()
    reject_links(source)
    reject_links(target)
    source, target = source.resolve(), target.resolve()
    if overlaps(source, target):
        raise ValueError('Source and installation target must be separate, non-nested directories')
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    if tuple(sys.version_info[:2]) < tuple(manifest['minimum_python']):
        raise ValueError('This skill requires Python ' + '.'.join(map(str, manifest['minimum_python'])))
    expected = manifest['files']
    for name in expected:
        p = PurePosixPath(name)
        if not p.parts or p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe manifest path')
    actual = inventory(source)
    actual.pop('manifest.json', None)
    if actual != expected:
        raise ValueError('Bundle integrity failed; download and extract the complete ZIP again')
    roots = manifest['install_roots']
    if not roots or len(roots) != len(set(roots)):
        raise ValueError('Invalid installation roots')
    if any(len(PurePosixPath(name).parts) != 1 or name in ('.', '..') or ':' in name or '\\' in name for name in roots):
        raise ValueError('Unsafe installation root')
    changed, existing = [], []
    for name in roots:
        dest = target / name
        reject_links(dest)
        wanted = {k[len(name) + 1:]: v for k, v in expected.items() if k.startswith(name + '/')}
        if not wanted:
            raise ValueError('Empty installation root: ' + name)
        if dest.exists() and not dest.is_dir():
            raise ValueError('Installation root is not a directory: ' + name)
        if not dest.exists() or inventory(dest) != wanted:
            changed.append(name)
            if dest.exists():
                existing.append(name)
    if existing and (not replace or not backup):
        raise ValueError('Existing files differ. Inspect them, then use --replace --backup <new-directory> to preserve them')
    backup_path = Path(backup).expanduser().absolute() if backup else None
    if backup_path:
        reject_links(backup_path)
        backup_path = backup_path.resolve()
        if backup_path.exists() or overlaps(backup_path, source) or overlaps(backup_path, target):
            raise ValueError('Backup must be a new directory outside both source and target')
        if backup_path.anchor.lower() != target.anchor.lower():
            raise ValueError('Backup must use the same filesystem as the target')
    if not changed:
        return {'ok': True, 'component': manifest['component'], 'action': 'already-current'}
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.scholarflow-stage-', dir=str(target)) as temp:
        stage = Path(temp)
        for name in changed:
            shutil.copytree(source / name, stage / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            if inventory(stage / name) != inventory(source / name):
                raise ValueError('Staged files differ; installed files were not changed')
        moved, installed = [], []
        if existing:
            backup_path.mkdir(parents=True)
        try:
            for name in changed:
                dest = target / name
                if dest.exists():
                    os.rename(dest, backup_path / name)
                    moved.append(name)
                os.rename(stage / name, dest)
                installed.append(name)
        except BaseException:
            # Put new files back into staging, then restore every preserved root.
            for name in reversed(installed):
                os.rename(target / name, stage / name)
            for name in reversed(moved):
                os.rename(backup_path / name, target / name)
            raise
    return {'ok': True, 'component': manifest['component'], 'action': 'installed',
            'roots': changed, 'backup': str(backup_path) if existing else None}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target', required=True, type=Path, help='The skills directory actually read by your AI assistant')
    p.add_argument('--replace', action='store_true')
    p.add_argument('--backup', type=Path)
    args = p.parse_args()
    try:
        print(json.dumps(install(Path(__file__).resolve().parent, args.target, args.replace, args.backup), ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError) as exc:
        p.exit(2, 'Install not completed: ' + str(exc) + '\n')
