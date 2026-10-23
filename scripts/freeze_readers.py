"""Bind authored inputs, standalone generator and reader bytes after a reproducible build."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/paper-close-read/scripts'))
from build_html import build,atomic_write

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def files(root):
    return {p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}

def freeze(folder):
    folder=Path(folder).resolve();data=folder/'reading-data'
    values=[json.loads((data/n).read_text(encoding='utf-8-sig')) for n in ['fulltext.json','translations.json','guide.json']]
    with (data/'source.md').open(encoding='utf-8-sig',newline='') as stream:source=stream.read()
    html,report=build(*values,data,source)
    if html.encode('utf-8')!=(folder/'reader.html').read_bytes():raise ValueError(str(folder)+': rebuild differs; rebuild and verify the final reader first')
    skill=files(ROOT/'skills/paper-close-read')
    manifest={'phase':'local-reader-quality','paper_id':values[0]['paper_id'],
        'skill_tree_sha256':hashlib.sha256(json.dumps(skill,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'skill_files':skill,'input_sha256':files(data),'html_sha256':sha(folder/'reader.html'),
        'rebuild_script_sha256':sha(ROOT/'scripts/rebuild_readers.py'),
        'source_blocks':report['source_blocks'],'paragraphs':report['paragraphs'],
        'source_warnings':report['warnings'],'reproducible':True}
    atomic_write(folder/'generation-manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folders',nargs='+',type=Path);args=p.parse_args()
    for folder in args.folders:
        try:m=freeze(folder)
        except (OSError,ValueError) as exc:p.exit(2,str(exc)+'\n')
        print(folder,m['html_sha256'],flush=True)
