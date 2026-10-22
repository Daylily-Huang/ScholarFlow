"""Import publisher JATS into the reader's source Markdown; does not author explanations."""
import argparse,copy,html,json,re,xml.etree.ElementTree as ET
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_mineru import parse_document

def text(el):
    return re.sub(r'\s+',' ',''.join(el.itertext())).strip() if el is not None else ''

def rich_text(el):
    """Keep text and safe inline semantics in the same normalized character stream."""
    chars=[]
    styles={'italic':'em','bold':'strong','sup':'sup','sub':'sub'}
    def visit(node,active=(),target=None):
        active=active+((styles[node.tag],) if node.tag in styles else ())
        target=node.get('rid') if node.tag=='xref' else target
        chars.extend((c,active,target) for c in (node.text or ''))
        for child in node:
            visit(child,active,target)
            chars.extend((c,active,target) for c in (child.tail or ''))
    visit(el);normalized=[]
    for c,st,tar in chars:
        if c.isspace():
            if normalized and normalized[-1][0]!=' ':normalized.append((' ',(),None))
        else:normalized.append((c,st,tar))
    if normalized and normalized[-1][0]==' ':normalized.pop()
    runs=[]
    for c,st,tar in normalized:
        signature=(list(st),tar)
        if runs and (runs[-1].get('styles',[]),runs[-1].get('xml_target'))==signature:runs[-1]['text']+=c
        else:runs.append({'text':c,'styles':list(st),**({'xml_target':tar} if tar else {})})
    return ''.join(x['text'] for x in runs),runs

def import_article(xml_path, output):
    root=ET.parse(xml_path).getroot();output=Path(output);output.mkdir(parents=True,exist_ok=True)
    title=text(root.find('.//article-title'));doi=next((text(e) for e in root.findall('.//article-id') if e.get('pub-id-type')=='doi'),None)
    authors=[text(n.find('given-names'))+' '+text(n.find('surname')) for n in [c.find('name') for group in root.findall('./front/article-meta/contrib-group') if group.get('content-type','author')!='editor' for c in group.findall('contrib') if c.get('contrib-type','author')=='author' and c.find('name') is not None]]
    chunks=['# '+title+'\n\n',' '.join(authors)+'\n\n'];locations={};figures=[];warnings=[]
    def add(value,el=None,**meta):
        line=''.join(chunks).count('\n')+1;chunks.append(value+'\n\n')
        if el is not None:locations[line]={'xml_id':el.get('id'),'xml_tag':el.tag,**meta}
    blocks={'disp-quote','list','boxed-text','def-list','statement','fig','table-wrap'}
    def paragraph(el,context=None,attribution=None,footnote=None):
        segment=ET.Element('p');segment.text=el.text
        def flush():
            value,runs=rich_text(segment)
            if value:add(value,el,inline_runs=runs,**({'context':context,'quote_attribution':attribution or ''} if context else {}),**({'footnote_label':footnote} if footnote else {}))
        for child in el:
            if child.tag in blocks:
                flush();walk_container(child,context=context);segment=ET.Element('p');segment.text=child.tail
            else:segment.append(copy.deepcopy(child))
        flush()
    def walk_container(el,level=2,context=None):
        tag=el.tag
        if tag=='disp-quote':
            attribution=text(el.find('attrib'))
            for child in el:
                if child.tag=='p':paragraph(child,'quote',attribution)
            return
        walk(el,level,context)
    def walk(el,level=2,context=None):
        for child in el:
            tag=child.tag.split('}')[-1]
            if tag=='sec':
                name=text(child.find('title'))
                if name:add('#'*min(level,6)+' '+name)
                walk(child,level+1)
            elif tag=='p':paragraph(child,context)
            elif tag in {'disp-quote','boxed-text','list','list-item','def-list','def-item','statement'}:walk_container(child,level,context)
            elif tag=='fig':
                label=text(child.find('label'));caption=text(child.find('caption'));graphic=child.find('.//graphic')
                href=next((v for k,v in graphic.attrib.items() if k.endswith('href')),'') if graphic is not None else ''
                name='images/'+(href.rsplit('/',1)[-1] or child.get('id','figure'))
                if not Path(name).suffix:name+='.jpg'
                add('!['+(label+' '+caption).replace(']','）')+']('+name+')',child);figures.append({'path':name,'href':href,'xml_id':child.get('id')})
            elif tag=='table-wrap':
                add(text(child.find('label'))+' '+text(child.find('caption')),child)
                table=child.find('.//table')
                if table is not None:add(ET.tostring(table,encoding='unicode').replace('\n',' '),table)
                foot=child.find('table-wrap-foot')
                if foot is not None:add(text(foot),foot)
            elif tag=='disp-formula':
                tex=child.find('.//{http://www.w3.org/1998/Math/MathML}math')
                add(text(child),child);warnings.append('Formula requires source review: '+str(child.get('id')))
            elif tag=='ref-list':
                add('## References')
                for ref in child.findall('ref'):
                    value,runs=rich_text(ref);add(value,ref,inline_runs=runs)
            elif tag=='fn':
                first=True
                for para in child.findall('p'):
                    before=len(locations);paragraph(para,footnote=text(child.find('label')))
                    if first and len(locations)>before:
                        locations[list(locations)[before]]['xml_id']=child.get('id');first=False
            elif tag in {'ack','app-group','app','fn-group','bio','notes'}:
                if child.find('title') is not None:add('## '+text(child.find('title')))
                walk(child,level)
            elif tag in {'title','label','object-id'}:pass
            else:
                if list(child):walk(child,level)
                elif text(child):add(text(child),child)
    abstracts=root.findall('./front/article-meta/abstract')
    for abstract in abstracts:add('## '+(text(abstract.find('title')) or 'Abstract'));walk(abstract,3)
    body=root.find('body')
    if body is None:raise ValueError('JATS has no body')
    walk(body)
    back=root.find('back')
    if back is not None:walk(back)
    funding=root.findall('./front/article-meta/funding-group/funding-statement')
    if funding:
        add('## Funding')
        for statement in funding:add(text(statement),statement)
    source=''.join(chunks);(output/'source.md').write_bytes(source.encode('utf-8'))
    data=parse_document(source,'source.md',doi)
    data['front'].update(title=title,citation='; '.join(authors)+' · '+str(doi or ''))
    for section in data['sections']:
        for item in section['items']:item['source'].update(locations.get(item['source']['line_start'],{}))
    xml_targets={}
    for sec in data['sections']:
        for i in sec['items']:
            if i['source'].get('xml_id'):xml_targets.setdefault(i['source']['xml_id'],i['id'])
    for sec in data['sections']:
        for item in sec['items']:
            for run in item['source'].get('inline_runs',[]):
                rid=run.pop('xml_target',None)
                if rid:
                    if rid in xml_targets:run['target']=xml_targets[rid]
                    else:warnings.append('Unresolved JATS cross-reference: '+rid)
    (output/'fulltext.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest={'title':title,'doi':doi,'authors':authors,'figures':figures,'warnings':warnings,'licenses':[text(e) for e in root.findall('.//license')]}
    (output/'import.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('xml',type=Path);ap.add_argument('output',type=Path);a=ap.parse_args();print(json.dumps(import_article(a.xml,a.output),ensure_ascii=False,indent=2))
