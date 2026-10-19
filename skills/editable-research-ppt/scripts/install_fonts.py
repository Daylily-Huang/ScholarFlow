#!/usr/bin/env python3
"""Install the bundled OFL fonts for the current user only. No administrator access."""
import argparse, ctypes, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Check installed copies without modifying anything')
    args=parser.parse_args()
    if sys.platform=='win32':dest=Path(os.environ['LOCALAPPDATA'])/'Microsoft/Windows/Fonts'
    elif sys.platform=='darwin':dest=Path.home()/'Library/Fonts'
    else:dest=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'fonts/editable-research-ppt'
    records=json.loads((ROOT/'fonts/sources.json').read_text(encoding='utf-8'))
    font_records=[r for r in records if r['file'].endswith('.otf')]
    # Validate every source and conflict before copying any font.
    for rec in font_records:
        source=ROOT/'fonts'/rec['file'];target=dest/source.name
        if hashlib.sha256(source.read_bytes()).hexdigest()!=rec['sha256']:raise SystemExit('Bundled font checksum mismatch: '+source.name)
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=rec['sha256']:raise SystemExit('Existing font differs; no overwrite: '+str(target))
    if args.check:
        missing=[r['file'] for r in font_records if not (dest/r['file']).is_file()]
        print(json.dumps({'current_user_font_copies_ok':not missing,'missing':missing,'note':'Checks this installer location and hashes, not actual rendering or fonts installed elsewhere.'}))
        return int(bool(missing))
    dest.mkdir(parents=True,exist_ok=True)
    for rec in font_records:
        source=ROOT/'fonts'/rec['file'];target=dest/source.name
        if not target.exists():shutil.copyfile(source,target)
        if sys.platform=='win32':
            import winreg
            family=('Noto Sans CJK SC' if 'Sans' in source.name else 'Noto Serif CJK SC')+(' Bold' if 'Bold' in source.name else '')
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows NT\CurrentVersion\Fonts') as key:
                winreg.SetValueEx(key,family+' (OpenType)',0,winreg.REG_SZ,str(target))
            ctypes.windll.gdi32.AddFontResourceW(str(target))
    if sys.platform=='win32':ctypes.windll.user32.SendMessageTimeoutW(0xFFFF,0x001D,0,0,2,1000,None)
    elif sys.platform!='darwin' and shutil.which('fc-cache'):subprocess.run(['fc-cache','-f',str(dest)],check=True)
    print('Installed current-user fonts. Restart presentation applications before rendering. Location: '+str(dest))
    return 0

if __name__=='__main__':raise SystemExit(main())
