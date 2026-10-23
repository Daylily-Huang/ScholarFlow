"""Report nested input type mistakes before semantic validation or rendering."""

def shape_errors(data, records, guide):
    errors = []
    def obj(value, path, fields):
        if not isinstance(value, dict):
            errors.append(path + ' must be an object'); return
        for key, rule in fields.items():
            if key in value: rule(value[key], path + '.' + key)
    def text(value, path):
        if not isinstance(value, str): errors.append(path + ' must be text')
    def integer(value, path):
        if type(value) is not int: errors.append(path + ' must be an integer')
    def number(value,path):
        if type(value) not in (int,float):errors.append(path+' must be a number')
    def array(rule):
        def check(value, path):
            if not isinstance(value, list): errors.append(path + ' must be an array'); return
            for n, item in enumerate(value): rule(item, path + '[' + str(n) + ']')
        return check
    def mapping(fields): return lambda value, path: obj(value, path, fields)
    texts = array(text)
    evidence = {'id':text, 'title':text, 'text':text, 'refs':texts}
    node = mapping({'id':text,'label':text,'lines':texts,'stage':integer})
    edge = mapping({'from':text,'to':text,'relation':text,'mode':text})
    visual = mapping({'quote':text,'attribution':text,'before':text,'interval':text,'after':text,'meaning':text,
        'layers':array(mapping({'label':text,'date':text,'detail':text})),
        'nodes':array(node),'edges':array(edge),
        'steps':array(mapping({'message':text,'interpretation':text,'channels':array(edge),
            'labels':lambda v,p: obj(v,p,{k:text for k in v} if isinstance(v,dict) else {})})),
        'focuses':array(mapping({'text':text,'meaning':text})),
        'curves':array(mapping({'label':text}))})
    overview = {**evidence,'format':text,'lead':text,'takeaway':text,'paragraphs':texts,'chain':texts,
        'research_map':array(mapping({'step':text,'title':text,'text':text,'refs':texts})),
        'metrics':array(mapping({'label':text,'value':text,'meaning':text}))}
    table_object = mapping({'head':texts,'rows':array(texts)})
    table = lambda value,path: table_object(value,path) if value is not None else None
    chapter = {**evidence,'bridge':text,'connection':text,'paragraphs':texts,'concepts':texts,
        'motions':array(mapping({'id':text})),'table':table}
    obj(guide, 'guide', {
        'story':mapping({'overview':mapping({**overview,'table':table}),'walkthrough':array(mapping(chapter))}),
        'claims':array(mapping({**evidence,'kind':text})),
        'checks':array(mapping({**evidence,'question':text,'answer':text})),
        'mechanisms':array(mapping({**evidence,'scene':text,'anchor':text,'question':text,'stages':texts,'visual':visual,'note':text,'label':text})),
        'concepts':array(mapping({**evidence,'anchor':text,'term':text,'meaning':text,'distinction':text,'example':text})),
        'further_reading':array(mapping({**evidence,'citation':text,'role':text,'priority':text,'relation':text,'reason':text,'focus':text,'url':text})),
        'attribution':mapping({'citation':text,'url':text,'license':text,'changes':text}),
        'limits':texts,'transfer':texts,'scope':text,'question':text,'answer':text,'why':text,
        'glossary':array(mapping({'term':text,'meaning':text})),
        'animations':array(mapping({'frames':texts,'durations':array(number),'title':text,'alt':text,'explanation':text}))})
    source = mapping({'facsimile':text,'verification_note':text,'status':text,'inline_runs':array(mapping({'text':text,'styles':texts,'target':text})),
        'corrections':array(mapping({'old':text,'new':text,'reason':text,'pdf_page':integer}))})
    obj(data,'fulltext',{'paper_id':text,'sections':array(mapping({'level':integer,'kind':text,
        'items':array(mapping({'latex':text,'src':text,'caption':text,'source':source}))}))})
    array(mapping({'id':text,'role':text,'zh':text,'note':text,'keys':texts,'trap':text,
        'terms':array(mapping({'en':text,'zh':text}))}))(records,'translations')
    return errors
