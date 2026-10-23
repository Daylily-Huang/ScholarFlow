"""Check the frozen design contract and scan public package content. Stdlib only.

This complements verify_release.py. It does not perform OCR, validate science,
re-check online licenses, or replace rendered-slide and independent review.
"""
from __future__ import annotations
import argparse,hashlib,io,json,re,zipfile
from pathlib import Path
import xml.etree.ElementTree as E

ROOT=Path(__file__).resolve().parents[1]
TEXT={'.md','.py','.ps1','.json','.html','.txt','.svg','.yml','.yaml','.xml','.rels'}
OFFICE={'.pptx','.xlsx','.docx'}
PATTERNS={
    'local_project':re.compile('\u9ed1\u9e82|munt'+'jac|Muntiacus '+'crinifrons',re.I),
    'private_path':re.compile(r'(?:[A-Z]:[\\/]+(?:Users|Desktop|WeChat-Document|ScholarFlow|Caches)[\\/]+|/mnt/[a-z]/(?:Users|ScholarFlow)/|/'+r'Users/[^/]+/|/'+r'home/[^/]+/)',re.I),
    'private_identity':re.compile(r'wxid_[A-Za-z0-9_]+|\u8dbe\u8431\s*\u9ec4|\u9ec4\u8dbe\u8431'),
    'credential':re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,}|sk-[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)')}
# These source files deliberately contain fake private paths to test rejection.
# No exemptions apply to Office content, shipped data, or credential patterns.
SYNTHETIC_FIXTURES={'tests/test_inspection.py','tests/test_media.py','tests/test_publication.py'}


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def template_structure(path):
    result={}
    with zipfile.ZipFile(path) as z:
        for name in sorted(z.namelist()):
            if name.startswith(('ppt/slides/','ppt/slideLayouts/','ppt/slideMasters/','ppt/theme/','ppt/charts/')) and name.endswith('.xml'):
                node=E.fromstring(z.read(name))
                for child in node.iter():
                    tag=child.tag.rsplit('}',1)[-1]
                    if tag in {'t','v'}:child.text=None
                    if tag=='cNvPr':
                        for key in ('name','descr','title'):child.attrib.pop(key,None)
                def normalized(element):
                    return [element.tag,sorted(element.attrib.items()),(element.text or '').strip(),[normalized(c) for c in element]]
                payload=json.dumps(normalized(node),ensure_ascii=False,separators=(',',':')).encode('utf-8')
                result[name]=hashlib.sha256(payload).hexdigest()
    return result


def check_design(root=ROOT):
    root=Path(root);contract=json.loads((root/'references/design-contract.json').read_text(encoding='utf-8'))
    system=json.loads((root/'assets/template-system.json').read_text(encoding='utf-8'));errors=[]
    for key,expected in contract['system'].items():
        if system.get(key)!=expected:errors.append('Design drift: template-system.'+key)
    for name,expected in contract['runtime_sha256'].items():
        if not (root/name).is_file() or digest(root/name)!=expected:errors.append('Design/runtime drift: '+name)
    for name,expected in contract['template_structure'].items():
        if template_structure(root/name)!=expected:errors.append('Template geometry/style drift: '+name)
    return errors


def scan_privacy(root=ROOT):
    root=Path(root);findings=[];files=0;office_parts=0
    def inspect(text,label,fixture=False):
        for kind,pattern in PATTERNS.items():
            if fixture and kind!='credential':continue
            if pattern.search(text):findings.append({'path':label,'kind':kind})
    def office(data,label,depth=0):
        nonlocal office_parts
        if depth>3:raise ValueError('Office embedding depth exceeds scan limit')
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist())>600_000_000:raise ValueError('Office package too large for scan')
            for name in z.namelist():
                inspect(name,label+'!'+name)
                ext=Path(name).suffix.lower()
                if ext in OFFICE:office(z.read(name),label+'!'+name,depth+1)
                elif ext in TEXT or ext=='.vml':
                    office_parts+=1;text=z.read(name).decode('utf-8-sig',errors='replace');inspect(text,label+'!'+name)
                    if name=='docProps/core.xml':
                        for child in E.fromstring(text):
                            if child.tag.rsplit('}',1)[-1] in {'creator','lastModifiedBy'} and child.text not in {None,'','ScholarFlow contributors','editable-research-ppt contributors','OpenAI','python-pptx'}:
                                findings.append({'path':label+'!'+name,'kind':'unreviewed_office_author'})
    for path in sorted(root.rglob('*')):
        if not path.is_file() or any(x in {'.git','__pycache__'} for x in path.relative_to(root).parts):continue
        rel=path.relative_to(root).as_posix();files+=1;inspect(rel,rel)
        if path.suffix.lower() in OFFICE:office(path.read_bytes(),rel)
        elif path.suffix.lower() in TEXT:inspect(path.read_text(encoding='utf-8-sig',errors='replace'),rel,rel in SYNTHETIC_FIXTURES)
    return {'files_scanned':files,'office_xml_parts_scanned':office_parts,'findings':findings,
            'scope':'Text, filenames, Office XML/relationships and embedded workbooks. Images require separate visual review; third-party copyright and source attribution are retained.'}


def verify(root=ROOT):
    root=Path(root)
    design=check_design(root);privacy=scan_privacy(root)
    return {'ok':not design and not privacy['findings'],'design_errors':design,'privacy':privacy}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT);a=p.parse_args()
    try:r=verify(a.root)
    except (OSError,ValueError,KeyError,E.ParseError,zipfile.BadZipFile) as exc:r={'ok':False,'error':str(exc)}
    print(json.dumps(r,ensure_ascii=False,indent=2));return 0 if r['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
