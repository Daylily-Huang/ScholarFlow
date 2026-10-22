"""Install only the standalone paper-close-read skill into a chosen skills directory."""
import argparse,shutil,hashlib
from pathlib import Path

def digest(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
def install(target,replace=False):
    source=Path(__file__).resolve().parents[1]/'skills/paper-close-read';dest=Path(target).expanduser().resolve()/'paper-close-read'
    if dest.exists():
        if digest(source)==digest(dest):return dest
        if not replace:raise ValueError('Target differs. Inspect it first; --replace explicitly replaces this skill only.')
        if dest.resolve()==source.resolve():raise ValueError('Target is the source')
        # The resolved destination is fixed to one named skill under the explicit target.
        shutil.rmtree(dest)
    shutil.copytree(source,dest,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    if digest(source)!=digest(dest):raise ValueError('Installed files differ')
    return dest
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--target',required=True,type=Path);p.add_argument('--replace',action='store_true');a=p.parse_args();print(install(a.target,a.replace))
