#!/usr/bin/env python3
"""Check package relationships, native objects, and chart cache/workbook agreement."""
import argparse,io,json,math,posixpath,re,zipfile
from pathlib import Path
import xml.etree.ElementTree as E

NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','c':'http://schemas.openxmlformats.org/drawingml/2006/chart','s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
def target(owner,path):return posixpath.normpath(posixpath.join(posixpath.dirname(owner),path)).lstrip('/')
def relation_file(part):return posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels')

def audit(path):
    errors=[];counts=dict(slides=0,text_shapes=0,charts=0,tables=0,connectors=0,pictures=0,cache_cells=0)
    with zipfile.ZipFile(path) as z:
        names=set(z.namelist());bad=z.testzip()
        if bad:errors.append('CRC: '+bad)
        pres=E.fromstring(z.read('ppt/presentation.xml'));size=pres.find('p:sldSz',NS)
        for name in sorted(names):
            if name.endswith('.rels'):
                owner='' if name=='_rels/.rels' else name.replace('/_rels/','/').removesuffix('.rels')
                for r in E.fromstring(z.read(name)):
                    if r.get('TargetMode')=='External':errors.append('External relationship: '+name)
                    elif target(owner,r.get('Target')) not in names:errors.append('Missing relationship target: '+name)
            if re.fullmatch(r'ppt/slides/slide\d+\.xml',name):
                root=E.fromstring(z.read(name));counts['slides']+=1
                counts['text_shapes']+=len(root.findall('.//p:sp/p:txBody',NS));counts['tables']+=len(root.findall('.//a:tbl',NS));counts['connectors']+=len(root.findall('.//p:cxnSp',NS));counts['pictures']+=len(root.findall('.//p:pic',NS))
                for extent in root.findall('.//p:pic/p:spPr/a:xfrm/a:ext',NS):
                    if int(extent.get('cx'))>=int(size.get('cx'))*.95 and int(extent.get('cy'))>=int(size.get('cy'))*.95:errors.append('Full-slide raster: '+name)
            if not re.fullmatch(r'ppt/charts/chart\d+\.xml',name):continue
            counts['charts']+=1;root=E.fromstring(z.read(name));ext=root.find('c:externalData',NS)
            if ext is None:errors.append('Missing workbook: '+name);continue
            rels={r.get('Id'):r.get('Target') for r in E.fromstring(z.read(relation_file(name)))}
            book=target(name,rels[ext.get('{'+NS['r']+'}id')])
            with zipfile.ZipFile(io.BytesIO(z.read(book))) as wb:
                cells={}
                for cell in E.fromstring(wb.read('xl/worksheets/sheet1.xml')).findall('.//s:c',NS):
                    cells[cell.get('r')]=''.join(t.text or '' for t in cell.findall('.//s:t',NS)) if cell.get('t')=='inlineStr' else cell.findtext('s:v',namespaces=NS)
            for ref in list(root.iter('{'+NS['c']+'}numRef'))+list(root.iter('{'+NS['c']+'}strRef')):
                formula=ref.findtext('c:f',namespaces=NS) or '';match=re.fullmatch(r"'Chart Data'!\$([A-Z]+)\$(\d+):\$([A-Z]+)\$(\d+)",formula)
                if not match or match[1]!=match[3]:errors.append('Unsupported reference: '+formula);continue
                numeric=ref.tag.endswith('}numRef');cache=ref.find('c:numCache' if numeric else 'c:strCache',NS)
                points=cache.findall('c:pt',NS);expected_count=int(match[4])-int(match[2])+1
                if len(points)!=expected_count or int(cache.find('c:ptCount',NS).get('val'))!=expected_count:errors.append('Point count mismatch: '+name)
                if [int(p.get('idx')) for p in points]!=list(range(expected_count)):errors.append('Point indices mismatch: '+name)
                for point in points:
                    key=match[1]+str(int(match[2])+int(point.get('idx')));actual=cells.get(key);expected=point.findtext('c:v',namespaces=NS);counts['cache_cells']+=1
                    try:equal=math.isclose(float(actual),float(expected),rel_tol=1e-12,abs_tol=1e-12) if numeric else actual==expected
                    except (ValueError,TypeError):equal=False
                    if not equal:errors.append(name+' '+key+': cache/workbook mismatch')
        if len(pres.findall('p:sldIdLst/p:sldId',NS))!=counts['slides']:errors.append('Slide count mismatch')
    return dict(ok=not errors,file=Path(path).name,counts=counts,errors=errors,scope='Structure and cached series/workbook agreement; no scientific validation or rendered-layout proof. Custom error bars are literal, not workbook-linked.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('pptx');args=p.parse_args()
    try:result=audit(args.pptx)
    except Exception as e:result={'ok':False,'errors':[str(e)]}
    print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(0 if result['ok'] else 1)
