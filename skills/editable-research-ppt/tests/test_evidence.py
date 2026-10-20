"""Behavioral tests for mandatory paper originals and new editable layouts."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as E

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
g=module('generate');a=module('audit')


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        location=os.environ.get('PPT_TEST_TMP')
        if location:Path(location).mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=location)
        self.out=Path(self.temp.name)
        self.doc=g.load(ROOT/'assets/examples/evidence-layouts.json')
        self.base=ROOT/'assets/examples'
    def tearDown(self):self.temp.cleanup()
    def generate(self,d):
        out=self.out/'result.pptx'
        g.generate(d,out,force=True,base_dir=self.base)
        return out
    def formal(self):
        d=copy.deepcopy(self.doc)
        d.update(demo=False,materials={'papers':[{'id':'demo-study','path':'figures/synthetic-study.pdf','figure_status':'relevant'}]})
        d['slides']=d['slides'][:1]
        return d
    def test_original_gate_and_successful_embedding(self):
        d=self.formal();out=self.generate(d)
        self.assertTrue(a.audit(out,strict=True)['ok'])
        with zipfile.ZipFile(out) as z:
            original=(self.base/d['slides'][0]['figures'][0]['path']).read_bytes()
            self.assertIn(original,[z.read(n) for n in z.namelist() if n.startswith('ppt/media/')])
        for field in ['materials']:
            bad=copy.deepcopy(d);bad.pop(field)
            with self.assertRaisesRegex(ValueError,'inventory'):self.generate(bad)
        bad=copy.deepcopy(d);bad['slides']=[copy.deepcopy(self.doc['slides'][4])]
        with self.assertRaisesRegex(ValueError,'Missing original'):self.generate(bad)
        for key,value in [('verified_complete',False),('pdf_sha256','0'*64),('png_sha256','0'*64),('render_method','redraw')]:
            bad=copy.deepcopy(d);bad['slides'][0]['figures'][0]['provenance'][key]=value
            with self.assertRaises(ValueError):self.generate(bad)
        bad=copy.deepcopy(d);bad['materials']['papers'][0]['figure_status']='unavailable'
        with self.assertRaisesRegex(ValueError,'unavailable'):self.generate(bad)
        bad=copy.deepcopy(d);bad['slides'][0]['duotone']=True
        with self.assertRaisesRegex(ValueError,'original color'):self.generate(bad)
    def test_post_edit_audit_catches_missing_or_altered_original(self):
        out=self.generate(self.formal())
        with zipfile.ZipFile(out) as z:parts={n:z.read(n) for n in z.namelist()}
        media=next(n for n in parts if n.startswith('ppt/media/evidence_'))
        bad=dict(parts);bad[media]=bad[media]+b'tampered'
        out.write_bytes(g.zipbytes(bad))
        self.assertFalse(a.audit(out,strict=True)['ok'])
        bad=dict(parts);root=E.fromstring(bad['ppt/slides/slide1.xml'])
        tree=root.find('p:cSld/p:spTree',g.NS)
        for pic in list(tree.findall('p:pic',g.NS)):tree.remove(pic)
        bad['ppt/slides/slide1.xml']=g.xml(root);out.write_bytes(g.zipbytes(bad))
        self.assertTrue(any('Missing embedded' in e for e in a.audit(out)['errors']))
    def test_six_palettes_two_styles_and_variants(self):
        for sample in ['evidence-layouts','evidence-variants']:
            for style in ['light','solid']:
                for palette in ['P1','P2','P3','P4','P5','P6']:
                    d=g.load(ROOT/f'assets/examples/{sample}.json')
                    d.update(palette=palette,fill_style=style)
                    for p in d['slides']:p.pop('palette',None)
                    out=self.generate(d);report=a.audit(out,strict=True)
                    self.assertTrue(report['ok'],report['errors'])
                    with zipfile.ZipFile(out) as z:
                        p=E.fromstring(z.read('ppt/slides/slide3.xml'))
                        pictures=p.findall('.//p:pic',g.NS)
                        self.assertEqual(len(pictures),3)
                        rels={r.get('Id'):r.get('Target') for r in E.fromstring(z.read('ppt/slides/_rels/slide3.xml.rels'))}
                        payloads=[z.read(rels[pic.find('p:blipFill/a:blip',g.NS).get(g.q('r','embed'))].lstrip('/')) for pic in pictures]
                        self.assertEqual(payloads[0],payloads[1]);self.assertEqual(payloads[0],payloads[2])
    def test_old_original_figure_variant_and_native_components(self):
        d=self.formal();p=d['slides'][0];p.update(layout='L11',variant='original_figure')
        p['components']=[{'type':'number','text':'①','box':[8,100,24,28]}]
        out=self.generate(d);self.assertTrue(a.audit(out,strict=True)['ok'])
        with zipfile.ZipFile(out) as z:
            root=E.fromstring(z.read('ppt/slides/slide1.xml'))
            self.assertIn('①',[t.text for t in root.findall('.//a:t',g.NS)])
            self.assertEqual(len(root.findall('.//p:pic',g.NS)),1)
    def test_bad_layout_inputs_fail_without_silent_truncation(self):
        d=copy.deepcopy(self.doc);d['slides'][0]['sections'][0]['body']='长文字'*100
        with self.assertRaisesRegex(ValueError,'exceeds region'):self.generate(d)
        d=copy.deepcopy(self.doc);d['slides'][2]['zooms'][0]['rect']=[0,0,1.2,1]
        with self.assertRaisesRegex(ValueError,'normalized'):self.generate(d)
        d=copy.deepcopy(self.doc);d['slides'][4]['groups'][0]['events']=['one']
        with self.assertRaisesRegex(ValueError,'align'):self.generate(d)
    def test_existing_variants_keep_labels_data_and_panels_together(self):
        d=g.load(ROOT/'assets/examples/existing-variants.json')
        out=self.generate(d)
        self.assertTrue(a.audit(out,strict=True)['ok'])
        with zipfile.ZipFile(out) as z:
            root=E.fromstring(z.read('ppt/slides/slide1.xml'))
            rows=root.findall('.//a:tbl/a:tr',g.NS)
            cells=rows[0].findall('a:tc',g.NS)
            self.assertEqual(''.join(t.text or '' for t in cells[0].findall('.//a:t',g.NS)),'群落乙')
            r=E.fromstring(z.read('ppt/slides/slide3.xml'))
            titles={}
            for sp in r.findall('.//p:sp',g.NS):
                text=''.join(t.text or '' for t in sp.findall('.//a:t',g.NS))
                off=sp.find('p:spPr/a:xfrm/a:off',g.NS)
                if off is not None:titles[text]=int(off.get('y'))
            self.assertLess(titles['季节动态'],titles['丰富度沿梯度变化'])


if __name__=='__main__':unittest.main()
