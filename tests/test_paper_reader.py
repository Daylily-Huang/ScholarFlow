"""Regression coverage for standalone reader import and humanities contracts."""
import copy,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/paper-close-read/scripts'))
from import_jats import import_article
from parse_mineru import parse_document
from build_html import build
from validate_content import validate
from render_mechanisms import validate_scene_data

class PaperReader(unittest.TestCase):
 def test_jats_editor_is_not_author_and_quotes_survive(self):
  xml='''<article><front><article-meta><title-group><article-title>Test</article-title></title-group><contrib-group content-type="author"><contrib><name><given-names>A</given-names><surname>Writer</surname></name></contrib></contrib-group><contrib-group content-type="editor"><contrib><name><given-names>E</given-names><surname>Editor</surname></name></contrib></contrib-group><abstract><p>Abstract.</p></abstract></article-meta></front><body><sec><title>Findings</title><p>Interpretation.</p><disp-quote><p>Participant quote.</p><p>(Participant 1)</p></disp-quote><p>Before list<list><list-item><p>Nested point</p></list-item></list></p></sec></body></article>'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'source.xml';p.write_text(xml,encoding='utf-8');m=import_article(p,Path(tmp)/'data');source=(Path(tmp)/'data/source.md').read_text(encoding='utf-8')
   self.assertEqual(m['authors'],['A Writer']);self.assertIn('Participant quote.',source);self.assertIn('Nested point',source);self.assertNotIn('E Editor',source)
 def fixture(self):
  source='# Test\n\n## Argument\n\nA claim.\n'
  d=parse_document(source);i=d['sections'][1]['items'][0]['id']
  t=[dict(id=i,zh='一个主张。',note='需要看到它的理由。',keys=['理由引出主张。'])]
  g={'story':{'overview':{'title':'问题','lead':'解释','paragraphs':['具体场景'],'chain':['问题','回答'],'takeaway':'关系','refs':[i]},'walkthrough':[{'title':'展开','bridge':'为什么','paragraphs':['进一步解释'],'connection':'因此','refs':[i],'concepts':['concept-a']}]},'concepts':[{'id':'concept-a','term':'词','meaning':'意义','distinction':'区别','example':'教学例子','refs':[i]}]}
  return source,d,t,g
 def test_concepts_render_inline_and_preserve_original_anchor(self):
  source,d,t,g=self.fixture()
  with tempfile.TemporaryDirectory() as tmp:html,report=build(d,t,g,Path(tmp),source)
  self.assertFalse(report['errors']);self.assertIn('id="guide-concept-1-concept-a"',html);self.assertIn('id="concept-a"',html);self.assertIn('data-ann-id="'+t[0]['id']+'-en"',html)
 def test_missing_concept_source_is_rejected(self):
  source,d,t,g=self.fixture();g['concepts'][0]['refs']=['not-in-source'];self.assertTrue(validate(d,t,g,source)['errors'])
 def test_unknown_chapter_concept_is_rejected(self):
  source,d,t,g=self.fixture();g['story']['walkthrough'][0]['concepts']=['concept-missing'];self.assertIn('Story links unknown concept',validate(d,t,g,source)['errors'])
 def test_diagram_relation_and_stage_require_valid_meaning(self):
  m={'scene':'argument_map','stages':['start','end'],'visual':{'nodes':[{'id':'a','label':'A','lines':['premise'],'stage':0},{'id':'b','label':'B','lines':['conclusion'],'stage':1}],'edges':[{'from':'a','to':'b','relation':'supports'}]}}
  self.assertEqual(validate_scene_data(m),[])
  m['visual']['edges'][0]['relation']='arbitrary';self.assertTrue(validate_scene_data(m))
  m['visual']['edges'][0]['relation']='supports';m['visual']['nodes'][1]['stage']=4;self.assertTrue(validate_scene_data(m))
 def test_coding_three_columns_and_stage_order_are_enforced(self):
  m={'scene':'evidence_coding','stages':['start','end'],'visual':{'nodes':[{'id':'a','label':'A','lines':['quote'],'stage':1},{'id':'b','label':'B','lines':['theme'],'stage':0}],'edges':[]}}
  errors=validate_scene_data(m);self.assertIn('Coding scene needs exactly 3 nodes',errors);self.assertIn('Node stages must follow reading order',errors)
 def test_chinese_source_label(self):
  source,d,t,g=self.fixture();d['front']['language']='zh'
  with tempfile.TemporaryDirectory() as tmp:html,_=build(d,t,g,Path(tmp),source)
  self.assertIn('body class="source-zh"',html)

 def test_nested_quote_is_not_duplicated_and_tail_and_attribution_survive(self):
  xml='<article><front><article-meta><title-group><article-title>T</article-title></title-group><funding-group><funding-statement>No external funding.</funding-statement></funding-group></article-meta></front><body><sec><title>Reading</title><p>Before <italic>book</italic>.<disp-quote><p>A quoted line.</p><attrib>(p. 9)</attrib></disp-quote>After quotation.</p></sec></body><back><fn-group><title>Notes</title><fn id="n1"><label>1</label><p>Note with <italic>emphasis</italic>.</p></fn></fn-group></back></article>'
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'a.xml';p.write_text(xml,encoding='utf-8');import_article(p,Path(tmp)/'data');d=json.loads((Path(tmp)/'data/fulltext.json').read_text(encoding='utf-8'));items=[i for sec in d['sections'] for i in sec['items']];raw=''.join(i['raw'] for i in items)
   self.assertIn('No external funding.',raw);self.assertEqual(raw.count('A quoted line.'),1);self.assertIn('After quotation.',raw)
   quote=next(i for i in items if i['raw'].startswith('A quoted'));self.assertEqual(quote['source']['context'],'quote');self.assertEqual(quote['source']['quote_attribution'],'(p. 9)')
   self.assertTrue(any(i['source'].get('footnote_label')=='1' for i in items));self.assertIn('Notes',[s['name'] for s in d['sections']])
 def test_inline_semantics_cannot_change_source_or_link_to_unknown_target(self):
  source,d,t,g=self.fixture();i=d['sections'][1]['items'][0];i['source']['inline_runs']=[{'text':'Changed claim.','styles':['em']}]
  self.assertTrue(any('Inline source text differs' in x for x in validate(d,t,g,source)['errors']))
  i['source']['inline_runs']=[{'text':i['raw'].strip(),'styles':['script'],'target':'missing'}]
  self.assertTrue(any('Unsafe style' in x for x in validate(d,t,g,source)['errors']))
 def test_text_focus_requires_an_exact_source_excerpt(self):
  source,d,t,g=self.fixture();i=t[0]['id'];g['mechanisms']=[{'id':'motion-text','scene':'text_focus','anchor':i,'refs':[i],'title':'Read','question':'Why?','stages':['A','B'],'visual':{'quote':'Not in source','attribution':'Teaching','focuses':[{'text':'Not','meaning':'A'},{'text':'source','meaning':'B'}]}}]
  self.assertIn('Text focus quote must exactly match a referenced source block',validate(d,t,g,source)['errors'])

 def test_communication_cannot_switch_to_an_unidentified_participant(self):
  m={'scene':'communication','stages':['first','last'],'visual':{'nodes':[{'id':x,'label':x} for x in ['a','b','c']],'steps':[{'message':'M','interpretation':'I','labels':{'unknown':'New person'},'channels':[]},{'message':'M','interpretation':'I','channels':[]}]}}
  self.assertIn('Communication labels must name existing participants',validate_scene_data(m))

 def mapped_fixture(self):
  source,d,t,g=self.fixture();i=t[0]['id']
  from render_story import RESEARCH_STEPS
  q=g['story']['overview'];q['format']='research-map';q['research_map']=[{'step':k,'text':label+'的具体回答','refs':[i]} for k,label,_ in RESEARCH_STEPS]
  q.pop('paragraphs');q.pop('chain');return source,d,t,g
 def test_research_map_renders_complete_six_steps_without_old_narrative(self):
  source,d,t,g=self.mapped_fixture();g['story']['overview']['research_map'][4]['title']='细读发现'
  with tempfile.TemporaryDirectory() as tmp:html,report=build(d,t,g,Path(tmp),source)
  self.assertFalse(report['errors']);self.assertEqual(html.count('<article class="research-step '),6);self.assertIn('细读发现',html);self.assertNotIn('<ol class="story-chain">',html)
  self.assertIn('id="story-step-1"',html);self.assertIn('data-ann-id="'+t[0]['id']+'-en"',html)
 def test_research_map_cannot_omit_gap_or_duplicate_a_step(self):
  source,d,t,g=self.mapped_fixture();g['story']['overview']['research_map'][1]['step']='background'
  self.assertTrue(any('Research map needs background/gap/question' in x for x in validate(d,t,g,source)['errors']))
 def test_research_map_needs_source_for_each_answer(self):
  source,d,t,g=self.mapped_fixture();g['story']['overview']['research_map'][3]['refs']=['missing']
  self.assertIn('Research map needs valid source refs: method',validate(d,t,g,source)['errors'])
 def test_research_map_cannot_ship_an_empty_findings_answer(self):
  source,d,t,g=self.mapped_fixture();g['story']['overview']['research_map'][4]['text']='  '
  self.assertIn('Research map needs concrete text: findings',validate(d,t,g,source)['errors'])

if __name__=='__main__':unittest.main()
