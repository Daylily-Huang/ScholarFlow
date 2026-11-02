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
    xml_path=Path(xml_path);output=Path(output)
    for name in ('source.md','fulltext.json','import.json'):
        if (output/name).exists() or (output/name).is_symlink():
            raise ValueError('JATS output already exists; use a new directory to preserve reviews: '+str(output/name))
    root=ET.parse(xml_path).getroot()
    for node in root.iter():
        node.tag=node.tag.rsplit('}',1)[-1]
    for node in root.iter():
        if node.tag in {'disp-formula','inline-formula'} and not any(g.tag in {'graphic','inline-graphic'} for g in node.iter()):
            raise ValueError('JATS formula needs a source image or separately verified LaTeX transcription; refusing to flatten mathematics: '+str(node.get('id','')))
    title=text(root.find('.//article-title'));doi=next((text(e) for e in root.findall('.//article-id') if e.get('pub-id-type')=='doi'),None)
    authors=[text(n.find('given-names'))+' '+text(n.find('surname')) for n in [c.find('name') for group in root.findall('./front/article-meta/contrib-group') if group.get('content-type','author')!='editor' for c in group.findall('contrib') if c.get('contrib-type','author')=='author' and c.find('name') is not None]]
    chunks=['# '+title+'\n\n',' '.join(authors)+'\n\n'];locations={};figures=[];warnings=[]
    def add(value,el=None,**meta):
        line=''.join(chunks).count('\n')+1;chunks.append(value+'\n\n')
        if el is not None or meta:locations[line]={'xml_id':el.get('id') if el is not None else None,'xml_tag':el.tag if el is not None else 'p',**meta}
    blocks={'disp-quote','list','boxed-text','def-list','statement','fig','table-wrap','disp-formula'}
    def paragraph(el,context=None,attribution=None,footnote=None):
        segment=ET.Element('p');segment.text=el.text
        def flush():
            value,runs=rich_text(segment)
            if value:add(value,el,inline_runs=runs,**({'context':context,'quote_attribution':attribution or ''} if context else {}),**({'footnote_label':footnote} if footnote else {}))
        for child in el:
            if child.tag in blocks or child.tag in {'graphic','inline-graphic'} or (child.tag in {'inline-formula','alternatives'} and (child.find('.//graphic') is not None or child.find('.//inline-graphic') is not None)):
                flush();walk_container(child,context=context);segment=ET.Element('p');segment.text=child.tail
            else:segment.append(copy.deepcopy(child))
        flush()
    def walk_container(el,level=2,context=None):
        tag=el.tag
        if tag in {'graphic','inline-graphic','alternatives'}:
            emit_graphics(el,'Original inline image '+str(el.get('id','')));return
        if tag in {'disp-formula','inline-formula'}:
            if not emit_graphics(el,'Original equation '+str(el.get('id',''))):
                add(text(el),el);warnings.append('Formula requires source review: '+str(el.get('id')))
            return
        if tag=='disp-quote':
            attribution=text(el.find('attrib'))
            if el.text and el.text.strip():add(el.text.strip(),context='quote',quote_attribution=attribution)
            for child in el:
                if child.tag!='attrib':
                    before=set(locations)
                    if child.tag=='p':paragraph(child,'quote',attribution)
                    else:walk_container(child,level,'quote')
                    for line in set(locations)-before:
                        locations[line]['context']='quote'
                        if not locations[line].get('quote_attribution'):locations[line]['quote_attribution']=attribution
                if child.tail and child.tail.strip():add(child.tail.strip(),context='quote',quote_attribution=attribution)
            return
        if not any(n.tag in blocks or n.tag in {'p','verse-line','graphic','inline-graphic'} for n in el.iter() if n is not el):
            value,runs=rich_text(el)
            if value:add(value,el,inline_runs=runs,**({'context':context} if context else {}))
            return
        walk(el,level,context)
    def emit_graphics(el,caption):
        graphics=[g for g in el.iter() if g.tag in {'graphic','inline-graphic'}]
        alternative_groups={id(g):id(group) for group in el.iter('alternatives') for g in group.iter() if g.tag in {'graphic','inline-graphic'}}
        emitted=set()
        for graphic in graphics:
            if any(graphic in list(group.iter()) and group.find('.//table') is not None for group in el.iter('alternatives')):continue
            key=alternative_groups.get(id(graphic),id(graphic))
            if key in emitted:continue
            emitted.add(key)
            href=next((v for k,v in graphic.attrib.items() if k.endswith('href')),'')
            if not href:raise ValueError('Source graphic has no file reference: '+str(el.get('id')))
            name='images/'+href.rsplit('/',1)[-1]
            if not Path(name).suffix:name+='.jpg'
            add('!['+caption.replace(']','）')+']('+name+')',el,graphic_href=href)
            figures.append({'path':name,'href':href,'xml_id':el.get('id')})
        return bool(emitted)
    def walk(el,level=2,context=None):
        if el.text and el.text.strip():add(el.text.strip(),context=context or '')
        for child in el:
            tag=child.tag.split('}')[-1]
            if tag=='sec':
                name=text(child.find('title'))
                if name:add('#'*min(level,6)+' '+name)
                walk(child,level+1)
            elif tag in {'p','verse-line'}:paragraph(child,context)
            elif tag in {'graphic','inline-graphic','alternatives'}:walk_container(child,level,context)
            elif tag in {'disp-quote','boxed-text','list','list-item','def-list','def-item','statement'}:walk_container(child,level,context)
            elif tag=='fig':
                label=text(child.find('label'));caption=text(child.find('caption'))
                if not emit_graphics(child,label+' '+caption):raise ValueError('Source figure has no extractable graphic: '+str(child.get('id')))
            elif tag=='table-wrap':
                add(text(child.find('label'))+' '+text(child.find('caption')),child)
                table=child.find('.//table')
                if table is not None:add(ET.tostring(table,encoding='unicode').replace('\n',' '),table)
                if any(g.tag in {'graphic','inline-graphic'} for g in child.iter()):
                    emit_graphics(child,text(child.find('label'))+' '+text(child.find('caption')))
                foot=child.find('table-wrap-foot')
                if foot is not None:add(text(foot),foot)
            elif tag=='disp-formula':
                walk_container(child,level,context)
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
                elif text(child):
                    value,runs=rich_text(child);add(value,child,inline_runs=runs,**({'context':context} if context else {}))
            if child.tail and child.tail.strip():add(child.tail.strip(),context=context or '')
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
    source=''.join(chunks)
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
    from figure_inventory import draft_inventory
    data['figure_inventory']=draft_inventory(data,xml_path,'jats')
    manifest={'title':title,'doi':doi,'authors':authors,'figures':figures,'warnings':warnings,'licenses':[text(e) for e in root.findall('.//license')]}
    source_name=xml_path.name if xml_path.resolve().parent==output.resolve() else 'original-jats.xml'
    data['figure_inventory']['source']['file']=source_name
    payload={'source.md':source.encode('utf-8'),'fulltext.json':json.dumps(data,ensure_ascii=False,indent=2).encode('utf-8'),
             'import.json':json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')}
    if (output/source_name).resolve()!=xml_path.resolve():payload[source_name]=xml_path.read_bytes()
    output.mkdir(parents=True,exist_ok=True);created=[]
    try:
        for name,raw in payload.items():
            with (output/name).open('xb') as stream:created.append(output/name);stream.write(raw)
    except OSError:
        for path in created:path.unlink()
        raise
    return manifest
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('xml',type=Path);ap.add_argument('output',type=Path);a=ap.parse_args();print(json.dumps(import_article(a.xml,a.output),ensure_ascii=False,indent=2))
