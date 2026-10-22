"""Rebuild authored readers from portable inputs, without patching generated HTML."""
import argparse,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/paper-close-read/scripts'))
from build_html import build

def rebuild(folder):
    folder=Path(folder);data=folder/'reading-data'
    if not data.is_dir():data=folder
    values=[json.loads((data/n).read_text(encoding='utf-8-sig')) for n in ['fulltext.json','translations.json','guide.json']]
    source=(data/'source.md').read_text(encoding='utf-8-sig')
    result,report=build(*values,data,source)
    target=folder/'reader.html';target.write_bytes(result.encode('utf-8'))
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folders',nargs='+',type=Path);args=p.parse_args()
    for folder in args.folders:print(folder, json.dumps(rebuild(folder),ensure_ascii=False))
