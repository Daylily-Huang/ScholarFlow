"""Synthetic, non-scientific regression fixtures. Outputs only to explicit work directory."""
import argparse
import base64
import copy
import json
import sys
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True
from parse_mineru import parse_document
from validate_content import validate
from build_html import build
from render_full import embed_image


def run(work):
    work.mkdir(parents=True, exist_ok=True)
    checks = []
    def check(condition, name):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
    source = ('Metadata before title.\n\n# Synthetic reader evaluation\n\n'
              'This is a synthetic fixture, not a real paper.\n\n'
              '## Methods\n\nOnly 12 plots were sampled; this does not establish causation.\n\n'
              '### Results and limits\n\nThe estimate was -2.50 units, not 25; uncertainty remains.\n\n'
              '$$\np = 1 - \\exp(-H)\n$$\n\n'
              '<table><tr><th>Parameter</th><th>Value</th></tr><tr><td>test</td><td>0.0399</td></tr><tr><td>unique</td><td>999</td></tr></table>\n\n'
              '## References\n\nNo actual publications are cited in this synthetic fixture.\n')
    data = parse_document(source, 'synthetic.md', 'synthetic-reader-fixture-a')
    items = [i for s in data['sections'] for i in s['items']]
    paragraphs = [i for i in items if i['t'] == 'p']
    check(len(paragraphs) == 5, 'preserve pre-title and pre-subheading paragraphs')
    check(any(s['level'] == 3 for s in data['sections']), 'retain nested headings')
    check(parse_document('Plain text without headings.\n')['sections'][0]['items'][0]['raw'].startswith('Plain'), 'no heading is supported')
    check('Æ' in parse_document('# Test\n\n0Æ6 and 1¼2 stay uncertain.\n')['sections'][0]['items'][0]['raw'], 'never infer decimal corrections')
    pairs = [
        ('标题前的元信息。', '这行说明材料位于标题之前，也应保留。'),
        ('这是合成测试材料，不是真实论文。', '这里用虚构材料检验阅读工具，不提供科研结论。'),
        ('只调查了 12 个样地；这不能确立因果关系。', '有观察记录，不等于知道是什么导致了差异。'),
        ('估计为 −2.50 单位，不是 25；仍存在不确定性。', '看数字要同时看正负号和不确定性；这组数字只用于测试。'),
        ('本合成材料没有引用实际出版物。', '不要把演示当作真实文献。')]
    records = [dict(id=p['id'], zh=zh, note=note, keys=[note], trap='', terms=[])
               for p, (zh, note) in zip(paragraphs, pairs)]
    guide = {'scope': '合成验证样例，不代表真实文献；全部段落用于软件检查。',
             'question': '读懂一个结果，为什么还要回看它的证据？',
             'answer': '先看数据怎么来，再看它能支持多强的结论。下面的数字仅供软件测试。',
             'why': '试着沿“说法 → 原文 → 限制”走一遍，体验不用从第一页硬读的路线。',
             'claims': [{'title': '观察与因果之间还有距离', 'kind': '教学解释', 'text': '记录了样地，不代表已经排除其他解释。', 'refs': [paragraphs[2]['id']]},
                        {'title': '数字带着符号和边界才有意义', 'kind': '教学解释', 'text': '−2.50 和 25 不能互换；原文也保留了不确定性。', 'refs': [paragraphs[3]['id']]}],
             'limits': ['这是一份虚构的工具验证输入，不能用于科研引用。'],
             'glossary': [{'term': '证据', 'meaning': '用来支持一个说法的观察、设计或推理。'}],
             'transfer': ['真实研究需要回到原始设计与完整结果，再判断能否采用。'],
             'checks': [{'question': '只看到两个量一起变化，能直接说一个导致另一个吗？',
                         'answer': '不能；本样例明确说没有确立因果。还需要相应研究设计与证据。', 'refs': [paragraphs[2]['id']]}],
             'animations': []}
    guide['format'] = 'legacy'  # Only exercise the explicitly opted-in compatibility path.
    report = validate(data, records, guide, source)
    check(not report['errors'], 'valid complete input passes')
    bad = copy.deepcopy(data);bad['sections'][2]['items'][0]['raw'] += 'changed'
    check(bool(validate(bad, records, guide, source)['errors']), 'full source span mutation rejected')
    bad = copy.deepcopy(data)
    eq = next(i for s in bad['sections'] for i in s['items'] if i['t'] == 'eq')
    eq['latex'] = 'p=1+H'
    check(bool(validate(bad, records, guide, source)['errors']), 'formula payload alteration rejected')
    bad = copy.deepcopy(data);bad['sections'].pop()
    check(bool(validate(bad, records[:-1], guide, source)['errors']), 'whole section omission rejected')
    for invalid_page in (-7, 0, 1.5, True, '1'):
        bad = copy.deepcopy(data)
        bad['sections'][0]['items'][0]['source'].update(pdf_page=invalid_page, status='verified', verification_note='synthetic test')
        check(bool(validate(bad, records, guide, source)['errors']), 'invalid PDF page rejected: ' + repr(invalid_page))
    check(bool(validate(data, records+[records[0]], guide, source)['errors']), 'duplicate translations rejected')
    check(bool(validate(data, records[:-1], guide, source)['errors']), 'missing translations rejected')
    empty_logic=copy.deepcopy(records);empty_logic[2]['keys']=[]
    check(bool(validate(data,empty_logic,guide,source)['errors']), 'empty body logic rejected')
    broken = copy.deepcopy(guide);broken['claims'][0]['refs']=['absent']
    check(bool(validate(data, records, broken, source)['errors']), 'bad evidence ref rejected')
    html, _ = build(data, records, guide, work, source)
    check('999' in html and '650.38' not in html and 'p.602' not in html and 'Royle' not in html, 'no paper-specific table, page or author injection')
    check('https://' not in html and 'src="assets/' not in html, 'reader has no runtime external asset URLs')
    motion = copy.deepcopy(guide)
    motion['mechanisms']=[dict(id='motion-test',scene='hazard',title='Synthetic mechanism',question='How does the cumulative process work?',anchor=paragraphs[2]['id'],refs=[paragraphs[2]['id']],stages=['Local contribution','Cumulative contribution'])]
    rendered,_=build(data,records,motion,work,source)
    check('id="motion-test"' in rendered and rendered.index('id="motion-test"')>rendered.index('id="'+paragraphs[2]['id']+'"'), 'mechanism rendered after planned source anchor')
    bad_motion=copy.deepcopy(motion);bad_motion['mechanisms'][0]['anchor']='absent'
    check(bool(validate(data,records,bad_motion,source)['errors']), 'missing mechanism anchor rejected')
    bad_motion=copy.deepcopy(motion);bad_motion['mechanisms'][0]['refs']=['absent']
    check(bool(validate(data,records,bad_motion,source)['errors']), 'missing mechanism evidence rejected')
    bad_motion=copy.deepcopy(motion);bad_motion['mechanisms'][0]['scene']='not-implemented'
    check(bool(validate(data,records,bad_motion,source)['errors']), 'unimplemented mechanism rejected')
    evil = copy.deepcopy(records);evil[0]['note']='<img src=x onerror=alert(1)> </script>'
    safe, _ = build(data, evil, guide, work, source)
    check('&lt;img src=x onerror=alert(1)&gt;' in safe, 'explanations are escaped')
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
    (work/'frame.png').write_bytes(png)
    check(embed_image('frame.png',work).startswith('data:image/png;base64,'), 'image embedded as data URI')
    try:
        embed_image('../outside.png',work)
        raise AssertionError('outside asset root accepted')
    except ValueError:
        checks.append('outside asset root rejected')
    guide['animations']=[{'title':'播放器测试帧', 'alt':'合成帧', 'explanation':'仅检验播放器控制。',
                          'frames':['frame.png','frame.png','frame.png'], 'durations':[200,200,200]}]
    html, _ = build(data,records,guide,work,source)
    for name,obj in [('fulltext.json',data),('translations.json',records),('guide.json',guide)]:
        (work/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    (work/'synthetic.md').write_text(source,encoding='utf-8',newline='')
    (work/'reader-a.html').write_text(html,encoding='utf-8')
    other=copy.deepcopy(data);other['paper_id']='synthetic-reader-fixture-b';other['front']['title']='Second independent synthetic paper'
    (work/'reader-b.html').write_text(build(other,records,guide,work,source)[0],encoding='utf-8')
    from render_story import render_story
    scene={'id':'motion-example','scene':'hazard','title':'局部强度','question':'如何累计？','refs':[], 'stages':['局部','累计']}
    chapter={'title':'解释','bridge':'前提','paragraphs':['先说明过程。'],'connection':'得到结果。','refs':[], 'motions':[{'id':'motion-example','label':'演示'}]}
    story={'overview':{'title':'问题','lead':'回答','paragraphs':[],'chain':[],'takeaway':'结论','refs':[]}, 'walkthrough':[chapter,chapter]}
    inline_story=render_story(story,[scene])
    check(inline_story.count('class="mechanism"')==2, 'guide embeds players for both explanations')
    check('id="guide-motion-1-motion-example"' in inline_story and 'id="guide-motion-2-motion-example"' in inline_story, 'reused guide scene has unique instance IDs')
    check('href="#motion-example"' not in inline_story, 'guide mechanism does not require route jump')
    # A fresh, unrelated topic exercises the default path without editing generated HTML.
    fresh_source = ('# Synthetic coating study\n\nFictional teaching material.\n\n'
                    '## Experiment\n\nBoth coatings initially blocked water. After repeated bending, A cracked and leaked while B remained intact and blocked water. Flexibility may help preserve the barrier.\n')
    fresh = parse_document(fresh_source, 'coating.md', 'synthetic-coating')
    ps = [i for sec in fresh['sections'] for i in sec['items'] if i['t']=='p']
    fid = ps[1]['id']
    fresh_records = [dict(id=ps[0]['id'],role='metadata',zh='虚构教学材料。'),
        dict(id=fid,zh='两种涂层最初都防水。反复弯折后，甲开裂并漏水，乙保持完整且防水。柔韧性可能帮助维持屏障。',
             note='刚涂好时，两者都挡得住水。反复弯折才拉开差距：甲折出了裂缝，水有了穿过去的路；乙仍完整，继续挡水。作者因此怀疑，能否经受弯折才是长期防水的关键。',
             keys=['起初都防水，初始表现不能解释后来的差距。','弯折后的开裂和渗水出现在同一种材料上，差异指向结构完整性。','这为柔韧性维持屏障提供线索，仍需单独改变裂缝情况来检验这一解释。'])]
    fresh_guide = {'scope':'虚构的软件与写作示例，不是真实研究。','story':{
        'overview':{'title':'刚做出来都防水，怎样选出更耐用的涂层？',
          'lead':'把涂层反复弯折，再看谁还能保持完整并挡水。',
          'paragraphs':['初始防水表现相同，不能直接决定哪种材料更耐用。模拟使用中的反复弯折后，甲开裂并漏水，乙仍完整；这让结构完整性成为解释差异的线索。'],
          'chain':['初始表现相同','用弯折引入使用过程','对照裂缝与漏水','提出维持屏障的解释'],
          'takeaway':'选材要看使用后还能否挡水；裂缝与漏水的对应提供机制线索。','refs':[fid]},
        'walkthrough':[
          {'title':'为什么还要折一折？','bridge':'初始防水试验没能分出差距',
           'paragraphs':['两种涂层刚做出来都挡水，这次测量回答的是现在漏不漏。实际使用还会弯折，所以需要加上重复弯折，再测一次防水性。'],
           'connection':'现在有了使用前后两次表现，下一步比较差异出现在哪里。','refs':[fid]},
          {'title':'裂缝和漏水怎样连起来？','bridge':'弯折后只有甲失去防水性',
           'paragraphs':['把两个现象放在一起看：甲开裂也漏水，乙没有开裂也没有漏水。裂缝像屏障上的缺口，因此作者把柔韧性作为保持防水的可能解释。'],
           'connection':'回到选材问题，要比较使用后的屏障是否完整；本例还需要进一步实验区分机制解释。','refs':[fid]}]}}
    check(not validate(fresh,fresh_records,fresh_guide,fresh_source)['errors'], 'new topic accepts story without legacy checklist and metadata without filler')
    fresh_html,_ = build(fresh,fresh_records,fresh_guide,work,fresh_source)
    check('story-step-2' in fresh_html and '为什么还要折一折' in fresh_html, 'fresh topic builds explanatory walkthrough directly')
    check('这篇论文的证据路线</h2>' not in fresh_html, 'fresh topic does not fall back to legacy checklist')
    check(bool(validate(fresh,fresh_records,{},fresh_source)['errors']), 'new guide missing story rejected')
    broken=copy.deepcopy(fresh_guide);broken['story']['overview']['paragraphs']='not an array'
    check(bool(validate(fresh,fresh_records,broken,fresh_source)['errors']), 'story paragraph string rejected instead of rendering characters')
    for name,obj in [('coating-fulltext.json',fresh),('coating-translations.json',fresh_records),('coating-guide.json',fresh_guide)]:
        (work/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    (work/'coating.html').write_text(fresh_html,encoding='utf-8')
    (work/'coating.md').write_text(fresh_source,encoding='utf-8')
    arranged=copy.deepcopy(fresh)
    arranged['sections'][0].update(kind='metadata',display_name='附：资料信息')
    arranged_html,_=build(arranged,fresh_records,fresh_guide,work,fresh_source)
    check(arranged_html.index('id="f-01"')<arranged_html.index('id="f-00"'), 'generic renderer moves metadata after body preserving IDs')
    check('附：资料信息' in arranged_html, 'display headings are authored without mutating source headings')
    corrected=copy.deepcopy(fresh)
    block=corrected['sections'][1]['items'][0]
    block['source'].update(pdf_page=1,status='verified',verification_note='Synthetic correction fixture',corrections=[dict(old='Flexibility',new='Verified display word',pdf_page=1,reason='Synthetic test only')])
    check(not validate(corrected,fresh_records,fresh_guide,fresh_source)['errors'], 'verified display correction preserves source validation')
    ch,_=build(corrected,fresh_records,fresh_guide,work,fresh_source)
    check('Verified display word' in ch and 'Flexibility' in block['raw'], 'display correction leaves raw text intact')
    block['source']['corrections'][0]['old']='not present'
    check(bool(validate(corrected,fresh_records,fresh_guide,fresh_source)['errors']), 'unmatched display correction rejected')
    from render_mechanisms import SCENES
    check({'molecular_sampling','pcr_slippage','replicate_consensus'}.issubset(SCENES), 'new paper mechanisms registered')
    (work/'report.json').write_text(json.dumps({'passed':checks},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':len(checks),'work_dir':str(work)},ensure_ascii=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir',required=True,type=Path)
    run(parser.parse_args().work_dir.resolve())
