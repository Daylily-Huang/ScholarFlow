"""Install a verified local skill folder with an explicit, preserved upgrade backup.

No downloads, font installation, global settings changes or Git operations.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat
import uuid

ROOT=Path(__file__).resolve().parents[1]
NAME='editable-research-ppt'


def verifier():
    spec=importlib.util.spec_from_file_location('local_release_verifier',ROOT/'scripts/verify_release.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def reject_links(root):
    # Do not read/copy arbitrary destinations through a linked asset directory.
    for path in [root,*root.rglob('*')]:
        st=path.lstat()
        if path.is_symlink() or getattr(st,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0):
            raise ValueError('Linked files/directories are not accepted in an installation tree')


def overlaps(a,b):
    return a==b or a.is_relative_to(b) or b.is_relative_to(a)


def copy_package(source,target,checker):
    for name,path in {**checker.package_files(source),'SHA256SUMS.txt':source/'SHA256SUMS.txt'}.items():
        dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open('xb') as stream:stream.write(path.read_bytes())


def install(source,target,*,backup=None,replace=False,allow_local_changes=False,dry_run=False):
    checker=verifier();raw_source=Path(source).absolute();raw_target=Path(target).absolute()
    for raw in (raw_source,raw_target):
        if raw.exists() or raw.is_symlink():
            flags=getattr(raw.lstat(),'st_file_attributes',0)
            if raw.is_symlink() or flags&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0):
                raise ValueError('Source/target must not be a linked directory')
    source=raw_source.resolve();target=raw_target.resolve()
    if target.name!=NAME:raise ValueError('Target must name the exact editable-research-ppt skill folder')
    if overlaps(source,target):raise ValueError('Source and target must be separate, non-nested folders')
    reject_links(source)
    checked=checker.verify(source)
    if not checked['ok']:raise ValueError('Source release integrity failed: '+str(checked['errors']))
    source_skill=(source/'SKILL.md').read_text(encoding='utf-8')
    if '\nname: '+NAME+'\n' not in source_skill:raise ValueError('Source is not the expected skill')
    exists=target.exists();current=None
    if exists:
        if not target.is_dir():raise ValueError('Target is not a directory')
        if not replace:raise FileExistsError('Target exists; use --replace with a new backup directory')
        if not backup:raise ValueError('Upgrades require an explicit new backup directory')
        reject_links(target)
        if not (target/'SKILL.md').is_file() or '\nname: '+NAME+'\n' not in (target/'SKILL.md').read_text(encoding='utf-8'):
            raise ValueError('Existing target is not the expected skill; refusing to move it')
        current=checker.verify(target)
        if not current['ok'] and not allow_local_changes:
            raise ValueError('Installed files differ or lack integrity evidence; reconcile edits first, or preserve all of them with --allow-local-changes')
    backup_dir=Path(backup).absolute().resolve() if backup else None
    if backup_dir:
        if backup_dir.exists():raise FileExistsError('Backup directory already exists; choose a new directory')
        if overlaps(backup_dir,source) or overlaps(backup_dir,target):raise ValueError('Backup must be outside both source and target')
    if exists and backup_dir.anchor.lower()!=target.anchor.lower():
        raise ValueError('Backup and installed target must be on the same filesystem for rename and recovery')
    result={'ok':True,'action':'upgrade' if exists else 'install','target':str(target),
            'source_files':checked['files'],'dry_run':dry_run,'local_changes_preserved':bool(current and not current['ok'])}
    if exists:result['backup']=str(backup_dir/NAME)
    if dry_run:return result
    old=None;owned=False
    if exists:
        backup_dir.parent.mkdir(parents=True,exist_ok=True);backup_dir.mkdir()
        old=backup_dir/NAME
        # An exclusive backup container prevents replacing someone else's backup.
        os.rename(target,old)
    try:
        target.parent.mkdir(parents=True,exist_ok=True);target.mkdir();owned=True
        copy_package(source,target,checker)
        installed=checker.verify(target)
        if not installed['ok']:raise ValueError('Installed integrity check failed: '+str(installed['errors']))
    except BaseException as exc:
        failed=None
        if owned and target.exists():
            failed=(backup_dir/'failed-install') if old else target.parent/(NAME+'.failed-'+uuid.uuid4().hex)
            os.rename(target,failed)
        if old is not None and old.exists():os.rename(old,target)
        if isinstance(exc,(KeyboardInterrupt,SystemExit)):raise
        raise RuntimeError('Installation failed; previous folder restored when present. Partial new files retained at '+str(failed)) from exc
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,default=ROOT)
    p.add_argument('--target',type=Path,required=True);p.add_argument('--backup',type=Path)
    p.add_argument('--replace',action='store_true');p.add_argument('--allow-local-changes',action='store_true');p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    try:result=install(a.source,a.target,backup=a.backup,replace=a.replace,allow_local_changes=a.allow_local_changes,dry_run=a.dry_run)
    except (OSError,ValueError,RuntimeError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False));return 1
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
