#!/usr/bin/env python3
"""Read-only portable package check. Generation needs only Python 3.10+."""
import argparse,hashlib,json,platform,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
PROFILES={'portable':['Noto Sans CJK SC','Noto Serif CJK SC'],'office':['Microsoft YaHei','SimSun']}
ALIASES={'Microsoft YaHei':['微软雅黑'],'SimSun':['宋体']}

def family_detected(name,installed):
    norm=lambda s:''.join(s.casefold().split())
    for alias in [name]+ALIASES.get(name,[]):
        for raw in installed:
            candidate=norm(raw);base=norm(alias)
            if candidate==base or any(candidate.startswith(base+suffix) for suffix in ['(','&',',','regular','bold','semibold','italic','medium','light','black']):return True
    return False

def capabilities(font_profile):
    fonts=[];font_method='unverified';ppt=False;libre=None
    if platform.system()=='Windows':
        try:
            import winreg
            font_method='Windows font display-name registry'
            for hive in [winreg.HKEY_LOCAL_MACHINE,winreg.HKEY_CURRENT_USER]:
                try:
                    with winreg.OpenKey(hive,r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts') as key:
                        for i in range(winreg.QueryInfoKey(key)[1]):fonts.append(winreg.EnumValue(key,i)[0])
                except OSError:pass
                for app in ['POWERPNT.EXE','soffice.exe']:
                    try:
                        with winreg.OpenKey(hive,'SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\'+app) as key:
                            value=winreg.QueryValue(key,None).strip('"')
                            if Path(value).is_file():
                                if app=='POWERPNT.EXE':ppt=True
                                else:libre=value
                    except OSError:pass
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,'PowerPoint.Application\\CLSID'):ppt=True
            except OSError:pass
        except ImportError:pass
    else:
        fc=shutil.which('fc-list')
        if fc:
            try:
                r=subprocess.run([fc,'--format','%{family}\n'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=8,check=True)
                fonts=r.stdout.replace(',','\n').splitlines();font_method='fontconfig family inventory'
            except (OSError,subprocess.SubprocessError):font_method='fontconfig_probe_failed'
        if platform.system()=='Darwin':ppt=Path('/Applications/Microsoft PowerPoint.app').is_dir()
    libre=libre or shutil.which('libreoffice') or shutil.which('soffice')
    selected=[]
    for name in PROFILES[font_profile]:
        detected=family_detected(name,fonts)
        selected.append({'family':name,'status':'detected' if detected else ('not_detected' if font_method in ['Windows font display-name registry','fontconfig family inventory'] else 'unverified')})
    return {'fonts':selected,'font_detection_method':font_method,
            'renderers':{'powerpoint':'registered_or_app_detected' if ppt else 'not_detected','libreoffice':'command_detected' if libre else 'not_detected'},
            'rendering_verified':False,
            'limitations':'Detection does not prove glyph coverage, app launch, identical rendering, editing or playback. Bundled font bytes do not mean installed fonts. No fonts or settings are changed.'}

def check(font_profile='portable'):
    checks={'evidence_renderer':(ROOT/'scripts/evidence_layouts.py').is_file(),'solid_styler':(ROOT/'scripts/fill_styles.py').is_file(),'python_3_10_or_newer':sys.version_info>=(3,10),'template':(ROOT/'assets/templates/library.pptx').is_file(),'bindings':(ROOT/'assets/templates/bindings.json').is_file()}
    errors=[]
    try:
        for item in json.loads((ROOT/'fonts/sources.json').read_text(encoding='utf-8')):
            path=ROOT/'fonts'/item['file'];checks[item['file']]=path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
    except (OSError,KeyError,ValueError) as exc:errors.append(str(exc))
    return {'ok':all(checks.values()) and not errors,'python':platform.python_version(),'platform':platform.system(),'checks':checks,'errors':errors,'font_profile':font_profile,'capabilities':capabilities(font_profile),'rendering':'Optional external application; absence is not a portable-generation failure.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--font-profile',choices=PROFILES,default='portable');args=parser.parse_args()
    result=check(args.font_profile);print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['ok'] else 1

if __name__=='__main__':raise SystemExit(main())
