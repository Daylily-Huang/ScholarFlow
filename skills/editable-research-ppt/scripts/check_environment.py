#!/usr/bin/env python3
"""Read-only portable package check. Generation needs only Python 3.10+."""
import hashlib,json,platform,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
checks={'solid_styler':(ROOT/'scripts/fill_styles.py').is_file(),'python_3_10_or_newer':sys.version_info>=(3,10),'template':(ROOT/'assets/templates/library.pptx').is_file(),'bindings':(ROOT/'assets/templates/bindings.json').is_file()}
for item in json.loads((ROOT/'fonts/sources.json').read_text(encoding='utf-8')):
    path=ROOT/'fonts'/item['file'];checks[item['file']]=path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
print(json.dumps({'ok':all(checks.values()),'python':platform.python_version(),'platform':platform.system(),'checks':checks,'rendering':'Separate Office/WPS/LibreOffice application required for preview. Font presence does not prove identical rendering.'},ensure_ascii=False,indent=2))
raise SystemExit(0 if all(checks.values()) else 1)
