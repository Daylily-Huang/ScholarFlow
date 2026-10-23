"""Install only the standalone paper-close-read skill into a chosen skills directory."""
import argparse,shutil,hashlib,tempfile,os
from pathlib import Path

def digest(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
def install(target,replace=False):
    source=Path(__file__).resolve().parents[1]/'skills/paper-close-read';dest=Path(target).expanduser().resolve()/'paper-close-read'
    if dest.exists():
        if digest(source)==digest(dest):return dest
        if not replace:raise ValueError('Target differs. Inspect it first; --replace explicitly replaces this skill only.')
        if dest.resolve()==source.resolve():raise ValueError('Target is the source')
        if dest.is_symlink() or dest.resolve().parent != Path(target).expanduser().resolve():
            raise ValueError('Refusing to replace a linked destination')
    dest.parent.mkdir(parents=True,exist_ok=True)
    # Stage and verify first; a failed copy never removes the installed skill.
    tmp=tempfile.mkdtemp(prefix='.reader-install-',dir=str(dest.parent))
    try:
        staging=Path(tmp)/'new';previous=Path(tmp)/'previous'
        shutil.copytree(source,staging,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        if digest(source)!=digest(staging):raise ValueError('Staged files differ; current installation kept')
        moved=False
        try:
            if dest.exists():os.replace(str(dest),str(previous));moved=True
            os.replace(str(staging),str(dest))
        except OSError:
            if moved and not dest.exists():
                try:os.replace(str(previous),str(dest))
                except OSError as exc:raise OSError('Installation failed; previous skill retained at '+str(previous)) from exc
            raise
    finally:
        # If rollback itself failed, retain the old installation for recovery.
        if not (Path(tmp)/'previous').exists() or dest.exists():shutil.rmtree(tmp)
    return dest
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--target',required=True,type=Path);p.add_argument('--replace',action='store_true');a=p.parse_args()
    try:print(install(a.target,a.replace))
    except (OSError,ValueError) as exc:p.exit(2,'Install not completed: '+str(exc)+'\n')
