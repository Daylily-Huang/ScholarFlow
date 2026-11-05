"""Deliberate-violation proofs: the structure gate must stop the deck, not trust a promise.

Each test builds a deck that is wrong in one specific way and asserts the check
refuses it. A gate that only reads declarations would pass all of these.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
g=module('generate');s=module('structure_audit');handoff=module('prepare_handoff');preflight=module('preflight')


class StructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir=os.environ.get('PPT_TEST_TMP'))
        cls.out=Path(cls.temp.name)
        cls.base=g.load(ROOT/'assets/examples/all-layouts.json')
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def page(self,index):
        page=copy.deepcopy(self.base['slides'][index]);page.pop('palette',None);return page
    def deck(self,indices,structures=None):
        doc=dict(demo=True,scenario='coursework',palette='P8',fill_style='solid',visual_mode='adaptive',
                 materials={'papers':[]},slides=[self.page(i) for i in indices])
        if structures is not None:
            for page,structure in zip(doc['slides'],structures):
                page['task']='这一页承担论证链条中的一环';page['structure']=structure
        return doc
    def codes(self,doc):return {x['code'] for x in s.inspect(doc)['issues']}
    def two_charts_and_a_cover(self,structures):
        # L3 and L11 both draw native charts, so changing the layout id cannot hide a repeated structure.
        return self.deck([4,2,10],structures)

    # 1. Three pages in a row with the same structure are refused outright.
    def test_three_identical_structures_are_refused(self):
        doc=self.two_charts_and_a_cover(['cover','chart','chart'])
        doc['slides'].append(self.page(2));doc['slides'][3].update(task='t',structure='chart')
        report=s.inspect(doc)
        self.assertFalse(report['ok'])
        self.assertIn('repetitive_structure',{x['code'] for x in report['issues']})
        target=self.out/'rhythm.pptx'
        with self.assertRaises(ValueError):g.generate(doc,target,force=True)
        self.assertFalse(target.exists(),'a refused deck must not leave a file behind')

    # 2. Layout ids differ but the drawn structure is the same: still a run.
    def test_swapping_layout_ids_without_changing_structure_is_still_a_run(self):
        doc=self.two_charts_and_a_cover(['cover','chart','chart'])
        doc['slides'].append(self.page(10));doc['slides'][3].update(task='t',structure='chart')
        self.assertEqual([p['layout'] for p in doc['slides'][1:]],[ 'L3','L11','L11'])
        self.assertIn('repetitive_structure',self.codes(doc))
        doc['slides'][2]['structure']='chart'
        self.assertEqual(len({p['layout'] for p in doc['slides'][1:]}),2,'different layout numbers, same structure')

    # 3. A run is allowed only when the deck states why, and the reason is recorded.
    def test_declared_reason_downgrades_the_same_run(self):
        doc=self.two_charts_and_a_cover(['cover','chart','chart'])
        doc['slides'].append(self.page(2));doc['slides'][3].update(task='t',structure='chart')
        doc['slides'][1]['rhythm_exception']='同一组三张原生图表连续对照，拆开会打断读图顺序'
        report=s.inspect(doc)
        self.assertTrue(report['ok'],report['issues'])
        self.assertIn('explained_rhythm',{x['code'] for x in report['issues']})
        target=self.out/'explained.pptx';g.generate(doc,target,force=True)
        receipt=s.check_pptx(target)
        self.assertEqual(receipt['status'],'review_required')
        self.assertTrue(receipt['exceptions'],'the declared reason must survive into the receipt')

    # 4. A page planned as image_led but drawn as text cards cannot pass on the plan alone.
    def test_plan_disagreeing_with_the_written_deck_is_refused(self):
        evidence=g.load(ROOT/'assets/examples/evidence-layouts.json')['slides'][0]
        page=copy.deepcopy(evidence)
        for key in ('figures','sections'):page.pop(key,None)
        page.pop('palette',None)
        page.update(layout='L16',variant='full_width',task='这一页讲清一条判定依据',structure='image_led')
        page['composition']=[
            {'kind':'text','name':'page-title','text':page['title'],'box':[32,20,1216,58],'size':42,'bold':True},
            {'kind':'shape','name':'rule','box':[32,120,420,10],'fill':'primary'},
            {'kind':'text','name':'point-1','text':'第一条依据先把样品状态固定','box':[32,160,520,70],'size':24},
            {'kind':'text','name':'point-2','text':'第二条依据统一顶空平衡条件','box':[32,250,520,70],'size':24},
            {'kind':'text','name':'point-3','text':'第三条依据才谈回收率是否达标','box':[32,340,520,70],'size':24},
            {'kind':'text','name':'take','text':page['takeaway'],'box':[48,642,1184,32],'size':23}]
        doc=dict(demo=True,scenario='coursework',palette='P8',fill_style='solid',visual_mode='adaptive',
                 materials={'papers':[]},slides=[page])
        self.assertTrue(preflight.inspect(doc)['ok'],'declarations alone look consistent')
        target=self.out/'lie.pptx'
        with self.assertRaisesRegex(ValueError,'Structure check failed'):g.generate(doc,target,force=True)
        self.assertFalse(target.exists())
        actual=s.measure(s.readzip(self.measured(page)))[0]
        self.assertNotEqual(actual['structure'],'image_led','no picture was drawn, so the page cannot be image-led')
        self.assertEqual(actual['pictures'],[])
    def measured(self,page):
        doc=dict(demo=True,scenario='coursework',palette='P8',fill_style='solid',visual_mode='adaptive',
                 materials={'papers':[]},slides=[copy.deepcopy(page)])
        doc['slides'][0].pop('structure');doc['slides'][0].pop('task')
        target=self.out/'measured.pptx';g.generate(doc,target,force=True);return target

    # 5. A deck that passed cannot be edited afterwards and keep its report.
    def test_editing_after_the_check_invalidates_the_report(self):
        doc=self.two_charts_and_a_cover(['cover','chart','chart'])
        doc['slides'].append(self.page(3));doc['slides'][3].update(task='t',structure='data')
        target=self.out/'sealed.pptx';g.generate(doc,target,force=True)
        self.assertEqual(s.check_pptx(target)['status'],'confirmed')
        with zipfile.ZipFile(target) as z:parts={n:z.read(n) for n in z.namelist()}
        parts['ppt/slides/slide2.xml']=parts['ppt/slides/slide2.xml'].replace(b'</p:sld>',b' </p:sld>')
        target.write_bytes(g.zipbytes(parts))
        with self.assertRaisesRegex(ValueError,'stale'):s.check_pptx(target)
        with self.assertRaisesRegex(ValueError,'stale'):handoff.prepare(target,self.out/'after edit')
        self.assertFalse((self.out/'after edit').exists())

    # 6. The formal delivery entry refuses a deck whose structure check never passed.
    def test_formal_delivery_requires_a_passing_structure_report(self):
        # A draft may hold a deck whose structure check failed; it must not be deliverable as formal.
        doc=self.two_charts_and_a_cover(['cover','chart','chart'])
        doc['slides'].append(self.page(2));doc['slides'][3].update(task='t',structure='chart')
        draft=self.out/'draft.pptx';g.generate(doc,draft,force=True,draft=True)
        self.assertIn('repetitive_structure',{x['code'] for x in s.inspect(doc)['issues']})
        with self.assertRaisesRegex(ValueError,'Structure check did not pass'):s.check_pptx(draft)
        with self.assertRaises(ValueError):handoff.prepare(draft,self.out/'formal')
        self.assertFalse((self.out/'formal').exists())
        handoff.prepare(draft,self.out/'draft delivery',draft=True)
        manifest=json.loads((self.out/'draft delivery/delivery-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['structure_status'],'draft')
        guide=next((self.out/'draft delivery').glob('*.md')).read_text(encoding='utf-8')
        self.assertIn('验证状态：待审稿',guide)
        self.assertNotIn('结构检查通过',guide)
        self.assertTrue((self.out/'draft delivery/structure-validation.json').is_file())
        # A draft still shows what was planned and what was measured, so the reviewer sees the gap.
        review=json.loads((self.out/'draft delivery/structure-validation.json').read_text(encoding='utf-8'))
        self.assertEqual(review['plan'][3]['structure'],'chart')
        self.assertEqual(len(review['actual']),len(doc['slides']))

    def test_l20_minimum_matrix_is_measured_as_data(self):
        page=copy.deepcopy(g.load(ROOT/'assets/examples/evidence-layouts.json')['slides'][5])
        page['matrix']=page['matrix'][:2]
        page.pop('palette',None)
        page.update(task='Compare the four criteria',structure='data')
        doc=dict(demo=True,scenario='academic',palette='P1',fill_style='solid',slides=[page])
        target=self.out/'minimum-matrix.pptx'
        g.generate(doc,target)
        metrics=s.check_pptx(target)['actual'][0]
        self.assertEqual(metrics['tables'],0)
        self.assertEqual(metrics['structure'],'data')
        self.assertTrue(metrics['matrix_grid'])

    def test_measured_run_blocks_alternating_labels_and_layouts(self):
        doc=self.deck([2,10,2],['chart','data','chart'])
        self.assertTrue(s.inspect(doc)['ok'])
        target=self.out/'mixed-labels.pptx'
        with self.assertRaisesRegex(ValueError,r'repetitive_structure.*measured'):
            g.generate(doc,target)
        self.assertFalse(target.exists())

    # 7. Undeclared and half-declared decks are reported, and demo examples stay usable.
    def test_undeclared_decks_are_reported_not_silently_accepted(self):
        doc=self.deck([4,2])
        self.assertEqual(s.inspect(doc)['status'],'undeclared')
        self.assertIn('structure_undeclared',self.codes(doc))
        self.assertTrue(preflight.inspect(doc)['ok'],'shipped demo examples must stay usable')
        doc['slides'][0].update(task='t',structure='cover')
        self.assertIn('structure_partial',self.codes(doc))
        doc['slides'][1].update(task='t',structure='chart')
        self.assertNotIn('structure_partial',self.codes(doc))

    # 8. Layout capacity is checked while authoring, before anything is rendered.
    def test_layout_capacity_is_checked_before_generation(self):
        doc=self.two_charts_and_a_cover(['cover','chart','chart'])
        doc['slides'][1]['structure']='image_led'
        self.assertIn('structure_capacity_mismatch',self.codes(doc))
        doc['slides'][0]['structure']='section'
        self.assertIn('structure_layout_mismatch',self.codes(doc),'L5 can only be a cover')
        doc['slides'][0]['structure']='cover'
        doc['slides'][1]['structure']='section'
        self.assertIn('structure_capacity_mismatch',self.codes(doc),'L3 draws charts or tables, never a section divider')
        doc['slides'][1]['structure']='chart'
        self.assertNotIn('structure_capacity_mismatch',self.codes(doc))


if __name__=='__main__':unittest.main()
