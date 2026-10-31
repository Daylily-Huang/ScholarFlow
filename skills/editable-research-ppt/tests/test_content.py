"""Cross-domain behavior and end-to-end content gates, using synthetic sources."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as E

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
c=module('content_audit');g=module('generate');handoff=module('prepare_handoff');exporter=module('export_project');preflight=module('preflight')


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ.get('PPT_TEST_TMP'));self.folder=Path(self.tmp.name)
        self.doc=g.load(ROOT/'assets/examples/all-layouts.json');page=copy.deepcopy(self.doc['slides'][2])
        self.doc.update(demo=False,materials={'papers':[]},slides=[page],fill_style='solid',visual_mode='adaptive')
        self.plan(self.doc)
    def tearDown(self):self.tmp.cleanup()
    def plan(self,doc):
        titles=[p['title'] for p in doc['slides']]
        source=self.folder/'source.txt';source.write_text('\n'.join(titles)+'\nSynthetic source: sample 20; change 30 percent. May improve stability. No significant difference. Projected expansion.\n',encoding='utf-8')
        evidence=[];claims=[]
        for i,p in enumerate(doc['slides'],1):
            evidence.append(dict(id='e'+str(i),source_id='s',quote=p['title'],locator='synthetic paragraph '+str(i),kind='background',context='fixture',status='verified'))
            claims.append(dict(id='c'+str(i),text=p['title'],kind='background',context='fixture',evidence_ids=['e'+str(i)],targets=[dict(slide=i,field='title')]))
        doc['content_plan']=dict(version=1,sources=[dict(id='s',path='source.txt',sha256=hashlib.sha256(source.read_bytes()).hexdigest())],evidence=evidence,claims=claims,
            coverage=[dict(id='topic',topic='Synthetic fixture concepts',required=True,claim_ids=[x['id'] for x in claims])],
            pages=[dict(slide=i,role='content',message=p['title']) for i,p in enumerate(doc['slides'],1)],
            review=dict(status='verified',scope='all_visible_substantive_content',reviewer='synthetic test fixture',note='Fixture declarations exercise software behavior, not scientific validation',slides_sha256=c.slides_digest(doc)))
    def codes(self,doc=None):return {x['code'] for x in c.inspect(doc or self.doc,self.folder)['issues']}
    def refresh(self):self.doc['content_plan']['review']['slides_sha256']=c.slides_digest(self.doc)
    def test_valid_cross_domain_inputs_and_scenarios(self):
        for scenario,title in [('academic','Historical text interpretation'),('coursework','A mathematical derivation'),('progress','Instrument calibration results')]:
            d=copy.deepcopy(self.doc);d['scenario']=scenario;d['slides'][0]['title']=title;self.plan(d)
            self.assertTrue(c.inspect(d,self.folder)['ok'])
        self.plan(self.doc)
        self.assertTrue(preflight.inspect(self.doc,self.folder)['ok'])
    def test_missing_plan_blocks_formal_generation_and_preserves_existing_file(self):
        del self.doc['content_plan'];p=self.folder/'keep.pptx';p.write_bytes(b'USER FILE')
        with self.assertRaisesRegex(ValueError,'Content review'):g.generate(self.doc,p,force=True,base_dir=self.folder)
        self.assertEqual(p.read_bytes(),b'USER FILE');self.assertFalse(preflight.inspect(self.doc,self.folder)['ok'])
    def test_changed_slides_invalidate_review_and_claim_binding(self):
        self.doc['slides'][0]['title']='Changed conclusion'
        self.assertTrue({'stale_review','claim_text_mismatch'}<=self.codes())
    def test_source_bytes_and_quote_are_checked(self):
        p=self.doc['content_plan'];p['evidence'][0]['quote']='Absent quote'
        self.assertIn('quote_mismatch',self.codes())
        (self.folder/'source.txt').write_text('CHANGED',encoding='utf-8')
        self.assertIn('source_hash_mismatch',self.codes())
    def test_origin_hash_is_checked(self):
        p=self.doc['content_plan'];p['sources'][0]['origin']=dict(path='source.txt',sha256='0'*64)
        self.assertIn('source_hash_mismatch',self.codes())
    def test_projection_or_inference_cannot_be_recorded_as_observation(self):
        p=self.doc['content_plan'];p['claims'][0]['kind']='observation'
        for kind in ('projection','inference'):
            p['evidence'][0]['kind']=kind
            self.assertIn('evidence_kind_mismatch',self.codes())
    def test_non_significance_does_not_establish_equivalence_or_causality(self):
        p=self.doc['content_plan'];p['evidence'][0]['relation']='not_different'
        for relation in ('equivalent','causal'):
            p['claims'][0]['relation']=relation
            self.assertIn('relation_overstatement',self.codes())
        p['evidence'][0]['relation']='equivalent';p['claims'][0]['relation']='equivalent'
        self.assertNotIn('relation_overstatement',self.codes())
    def test_unknown_information_is_allowed_but_not_as_assertion_support(self):
        p=self.doc['content_plan'];p['evidence'][0]['status']='not_reported'
        self.assertIn('unverified_support',self.codes())
        p['claims'][0]['kind']='question'
        self.assertIn('visible_question_required',self.codes())
        p['claims'][0]['text']='Is this result established?';self.doc['slides'][0]['title']=p['claims'][0]['text'];self.refresh()
        self.assertTrue(c.inspect(self.doc,self.folder)['ok'])
    def test_inference_qualifier_must_be_visible_and_language_independent(self):
        p=self.doc['content_plan'];p['claims'][0]['kind']='inference'
        self.assertIn('visible_qualifier_required',self.codes())
        title='May improve stability';self.doc['slides'][0]['title']=title;p['claims'][0]['text']=title;p['claims'][0]['qualifier']='May';self.refresh()
        self.assertTrue(c.inspect(self.doc,self.folder)['ok'])
    def test_numeric_value_unit_population_baseline_and_timeframe(self):
        p=self.doc['content_plan'];e=p['evidence'][0];claim=p['claims'][0]
        self.doc['slides'][0]['title']='Change 30 percent';claim['text']=self.doc['slides'][0]['title'];e['quote']='change 30 percent.'
        facts=dict(value=30,unit='percent',population='apparatus A',comparison='baseline A',timeframe='test window A')
        e['facts']=facts;claim['facts']=[dict(evidence_id=e['id'],**facts)];self.refresh()
        self.assertTrue(c.inspect(self.doc,self.folder)['ok'])
        for key in c.FACT_FIELDS:
            bad=copy.deepcopy(self.doc);bad['content_plan']['claims'][0]['facts'][0][key]=31 if key=='value' else 'different'
            self.assertIn('numeric_context_mismatch',self.codes(bad),key)
        claim['text']='Change 99 percent';self.doc['slides'][0]['title']=claim['text'];self.refresh()
        self.assertIn('numeric_display_mismatch',self.codes())
    def test_numeric_tokens_accept_chinese_and_do_not_merge_comma_lists(self):
        self.assertIn(c.number(30),c.numeric_tokens('共有30种，变化30%'))
        self.assertEqual(c.numeric_tokens('1,2'),{c.number(1),c.number(2)})
        self.assertEqual(c.numeric_tokens('1,000,000'),{c.number(1000000)})
    def test_distinct_study_contexts_cannot_be_silently_merged(self):
        self.doc['content_plan']['claims'][0]['context']='a different survey'
        self.assertIn('context_mismatch',self.codes())
    def test_coverage_required_topics_and_explicit_optional_omissions(self):
        p=self.doc['content_plan'];p['coverage'].append(dict(id='limits',topic='Applicability conditions',required=True,claim_ids=[]))
        self.assertIn('uncovered_topic',self.codes())
        p['coverage'][-1].update(required=False,omission_reason='Not applicable to this synthetic concept-only fixture')
        self.assertNotIn('uncovered_topic',self.codes())
    def test_actual_page_coverage_and_hidden_field_binding(self):
        p=self.doc['content_plan'];p['pages'][0]['role']='navigation'
        self.assertIn('invalid_page_role',self.codes())
        p['pages'][0]['role']='content';p['claims'][0]['targets'][0]['field']='sources.0'
        self.assertIn('invalid_target',self.codes())
        p['pages']=[];self.assertIn('incomplete_page_plan',self.codes())
    def test_dependencies_and_deliberate_conclusion_first_exception(self):
        self.doc['slides']*=2;self.plan(self.doc);p=self.doc['content_plan'];p['claims'][0]['depends_on']=['c2']
        self.assertIn('unexplained_forward_reference',self.codes())
        p['claims'][0]['forward_reference_reason']='Deliberate preview; the method is explained next'
        report=c.inspect(self.doc,self.folder);self.assertTrue(report['ok']);self.assertIn('intentional_forward_reference',self.codes())
        p['claims'][1]['depends_on']=['c1'];self.assertIn('dependency_cycle',self.codes())
    def test_malformed_plan_is_rejected_without_traceback(self):
        for key in ('sources','evidence','claims','coverage','pages','review'):
            for value in (None,True,'bad',[],{}):
                d=copy.deepcopy(self.doc);d['content_plan'][key]=value
                self.assertFalse(c.inspect(d,self.folder)['ok'],(key,value))
    def test_explicit_draft_is_labeled_and_cannot_be_formally_handed_off(self):
        del self.doc['content_plan'];p=self.folder/'draft.pptx';r=g.generate(self.doc,p,base_dir=self.folder,draft=True)
        self.assertEqual(r['content_status'],'draft')
        with self.assertRaisesRegex(ValueError,'draft'):handoff.prepare(p,self.folder/'formal')
        handoff.prepare(p,self.folder/'draft handoff',draft=True)
        d=json.loads((self.folder/'draft handoff/delivery-manifest.json').read_text(encoding='utf-8'));self.assertEqual(d['content_status'],'draft')
    def test_formal_generation_handoff_and_manual_text_edit_detection(self):
        p=self.folder/'formal.pptx';g.generate(self.doc,p,base_dir=self.folder)
        self.assertEqual(c.check_pptx(p)['status'],'reviewed')
        handoff.prepare(p,self.folder/'formal handoff')
        with zipfile.ZipFile(p) as z:parts={n:z.read(n) for n in z.namelist()}
        parts['ppt/slides/slide1.xml']=parts['ppt/slides/slide1.xml'].replace(self.doc['slides'][0]['title'].encode(),b'Changed conclusion')
        p.write_bytes(g.zipbytes(parts))
        with self.assertRaisesRegex(ValueError,'changed'):handoff.prepare(p,self.folder/'stale')
    def test_reordered_presentation_invalidates_actual_exposition_order(self):
        self.doc['slides']=[copy.deepcopy(self.doc['slides'][0]) for _ in range(2)]
        self.doc['slides'][0]['title']='Method prerequisites';self.doc['slides'][1]['title']='Results interpretation';self.plan(self.doc)
        self.doc['content_plan']['claims'][1]['depends_on']=['c1']
        p=self.folder/'ordered.pptx';g.generate(self.doc,p,base_dir=self.folder)
        self.assertEqual(c.check_pptx(p)['status'],'reviewed')
        with zipfile.ZipFile(p) as z:parts={n:z.read(n) for n in z.namelist()}
        root=E.fromstring(parts['ppt/presentation.xml']);ids=root.find('p:sldIdLst',g.NS);ids[:]=list(ids)[::-1]
        parts['ppt/presentation.xml']=g.xml(root);p.write_bytes(g.zipbytes(parts))
        with self.assertRaisesRegex(ValueError,'changed'):handoff.prepare(p,self.folder/'reordered formal')
        self.assertFalse((self.folder/'reordered formal').exists())
    def test_relationship_notes_and_picture_context_edits_invalidate_receipt(self):
        p=self.folder/'bound.pptx';g.generate(self.doc,p,base_dir=self.folder)
        with zipfile.ZipFile(p) as z:base={n:z.read(n) for n in z.namelist()}
        for name in ('ppt/_rels/presentation.xml.rels','ppt/slides/_rels/slide1.xml.rels','ppt/notesSlides/notesSlide1.xml','ppt/slides/slide1.xml'):
            parts=dict(base);parts[name]+=b'\n';p.write_bytes(g.zipbytes(parts))
            with self.assertRaisesRegex(ValueError,'changed'):c.check_pptx(p)
    def test_edited_deck_re_review_requires_exact_output_hash_and_actual_claims(self):
        p=self.folder/'manual.pptx';g.generate(self.doc,p,base_dir=self.folder,draft=True)
        with self.assertRaisesRegex(ValueError,'exact SHA256'):c.check_edited(self.doc,self.folder,p)
        self.doc['content_plan']['review']['pptx_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        source=self.folder/'input.json';source.write_text(json.dumps(self.doc),encoding='utf-8')
        handoff.prepare(p,self.folder/'reviewed edited',content_input=source)
        self.doc['slides'][0]['title']='Not on actual deck';self.doc['content_plan']['claims'][0]['text']=self.doc['slides'][0]['title'];self.refresh()
        with self.assertRaisesRegex(ValueError,'claim missing'):c.check_edited(self.doc,self.folder,p)
    def test_portable_source_copies_only_referenced_extracts_and_enforces_review_after_edits(self):
        source=self.folder/'input.json';source.write_text(json.dumps(self.doc),encoding='utf-8');(self.folder/'private-unreferenced.txt').write_text('private',encoding='utf-8')
        project=self.folder/'portable';exporter.export(source,project)
        moved=self.folder/'relocated';project.rename(moved);p=self.folder/'rebuilt.pptx'
        command=[sys.executable,'-I','-S','-B',str(moved/'rebuild.py'),'--output',str(p)]
        subprocess.run(command,check=True,capture_output=True)
        self.assertEqual(c.check_pptx(p)['status'],'reviewed');self.assertFalse(list(moved.rglob('private-unreferenced.txt')))
        doc=json.loads((moved/'input.json').read_text(encoding='utf-8'));doc['slides'][0]['title']='Changed';(moved/'input.json').write_text(json.dumps(doc),encoding='utf-8');p.unlink()
        blocked=subprocess.run(command+['--allow-input-edits'],capture_output=True);self.assertNotEqual(blocked.returncode,0);self.assertFalse(p.exists())
        subprocess.run(command+['--allow-input-edits','--draft'],check=True,capture_output=True)
        with self.assertRaisesRegex(ValueError,'draft'):c.check_pptx(p)
    def test_portable_content_supports_markdown_and_opaque_original_data(self):
        (self.folder/'source.md').write_bytes((self.folder/'source.txt').read_bytes())
        original=self.folder/'raw-data.bin';original.write_bytes(b'synthetic non-executable original evidence')
        source_record=self.doc['content_plan']['sources'][0];source_record['path']='source.md'
        source_record['origin']=dict(path='raw-data.bin',sha256=hashlib.sha256(original.read_bytes()).hexdigest())
        source=self.folder/'input.json';source.write_text(json.dumps(self.doc),encoding='utf-8')
        project=self.folder/'portable';exporter.export(source,project)
        self.assertEqual(len(list((project/'assets').glob('*.bin'))),1)
        subprocess.run([sys.executable,'-I','-S','-B',str(project/'rebuild.py'),'--output',str(self.folder/'rebuilt.pptx')],check=True,capture_output=True)


if __name__=='__main__':unittest.main()
