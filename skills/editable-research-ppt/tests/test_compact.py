"""Approved-subset, data mutation, palette/fill and portable runtime tests."""
import copy
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
    spec=importlib.util.spec_from_file_location('compact_test_'+name,ROOT/'scripts'/(name+'.py'))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

g=module('generate');a=module('audit');p=module('preflight')

class CompactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir=os.environ.get('PPT_TEST_TMP'));cls.out=Path(cls.temp.name)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def doc(self):return g.load(ROOT/'assets/examples/compact-approved.json')
    def generate(self,doc,name):
        out=self.out/(name+'.pptx');g.generate(doc,out,force=True,base_dir=ROOT/'assets/examples')
        self.assertTrue(a.audit(out,strict=True)['ok'],a.audit(out,strict=True));return out
    def test_exact_approved_subset(self):
        catalog=g.load(ROOT/'assets/templates/compact-bindings.json')
        self.assertEqual(catalog['approved_reference_pages'],[2,4,5,8,9,10])
        self.assertEqual(sorted(t['source_page'] for t in catalog['templates'].values()),[2,4,5,8,9,10])
        with zipfile.ZipFile(ROOT/'assets/templates/compact-library.pptx') as z:
            pres=E.fromstring(z.read('ppt/presentation.xml'))
            self.assertEqual(len(pres.findall('p:sldIdLst/p:sldId',g.NS)),6)
            slideparts=[n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
            self.assertEqual(len(slideparts),6)
    def test_every_palette_both_fills_and_scenarios(self):
        for pid in range(1,11):
            for fill in ['light','solid']:
                doc=self.doc();doc.update(palette='P'+str(pid),fill_style=fill,palette_showcase=False)
                doc['scenario']=['academic','coursework','progress'][(pid-1)%3]
                for page in doc['slides']:page.pop('palette')
                self.assertTrue(p.inspect(doc)['ok'])
                out=self.generate(doc,f'p{pid}-{fill}')
                report=a.audit(out,strict=True)
                self.assertEqual((report['counts']['charts'],report['counts']['tables'],report['counts']['pictures']),(8,1,0))
    def test_changed_text_chart_and_table_persist(self):
        doc=self.doc();doc['slides'][0]['title']='比较新调查结果'
        doc['slides'][0]['charts'][0]['series'][0]['values'][0]=27
        doc['slides'][0]['texts']['site1_input']='点位甲：独立记录27，有效相机日120'
        doc['slides'][4]['table'][1][1]='18 组合'
        out=self.generate(doc,'changed')
        with zipfile.ZipFile(out) as z:
            self.assertIn('比较新调查结果',z.read('ppt/slides/slide1.xml').decode())
            self.assertIn('18 组合',z.read('ppt/slides/slide5.xml').decode())
            chart=E.fromstring(z.read('ppt/charts/chart1.xml'))
            self.assertEqual(float(chart.find('.//c:ser/c:val/c:numRef/c:numCache/c:pt/c:v',g.NS).text),27)
    def test_mixed_old_and_new_order(self):
        doc=self.doc();old=g.load(ROOT/'assets/examples/adaptive-solid.json')['slides'][0]
        doc['slides']=[doc['slides'][3],old,doc['slides'][0],copy.deepcopy(doc['slides'][3])]
        out=self.generate(doc,'mixed')
        self.assertEqual(a.audit(out)['counts']['slides'],4)
    def test_invalid_input_does_not_replace_existing_output(self):
        for name,mutate in [
            ('variant',lambda d:d['slides'][0].update(variant='not-approved')),
            ('missing',lambda d:d['slides'][0]['texts'].pop('numerator')),
            ('extra',lambda d:d['slides'][0].update(image='ignored.png')),
            ('long',lambda d:d['slides'][0].update(title='很长的标题'*40)),
            ('chart',lambda d:d['slides'][0]['charts'][0]['series'][0].update(values=[1])),
            ('table',lambda d:d['slides'][4]['table'][1].append('extra'))]:
            doc=self.doc();mutate(doc);out=self.out/(name+'.pptx');out.write_bytes(b'KEEP')
            with self.assertRaises(ValueError):g.generate(doc,out,force=True)
            self.assertEqual(out.read_bytes(),b'KEEP')
    def test_formal_paper_inventory_is_still_required(self):
        doc=self.doc();doc['demo']=False
        with self.assertRaises(ValueError):g.generate(doc,self.out/'formal.pptx',force=True)
        doc['materials']={'papers':[]};doc['footer']='自有数据测试'
        self.generate(doc,'formal-no-papers')
    def test_source_project_rebuild_without_site_packages(self):
        source=self.out/'input.json';source.write_text(json.dumps(self.doc(),ensure_ascii=False),encoding='utf-8')
        project=self.out/'compact project';module('export_project').export(source,project)
        out=self.out/'rebuilt.pptx'
        subprocess.run([sys.executable,'-I','-S','-B',str(project/'rebuild.py'),'--output',str(out)],check=True,capture_output=True)
        self.assertTrue(a.audit(out,strict=True)['ok'])

if __name__=='__main__':unittest.main()
