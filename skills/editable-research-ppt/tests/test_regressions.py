"""Regression coverage for real-material input and quality-gate failures."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as E
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
g = module('generate'); a = module('audit'); release = module('verify_release')

def png(rgb):
    def chunk(t, b):
        return struct.pack('!I', len(b))+t+b+struct.pack('!I', zlib.crc32(t+b)&0xffffffff)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('!2I5B',100,50,8,2,0,0,0))
            +chunk(b'IDAT',zlib.compress((b'\0'+bytes(rgb)*100)*50))+chunk(b'IEND',b''))

class RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        location = os.environ.get('PPT_TEST_TMP')
        if location: Path(location).mkdir(parents=True, exist_ok=True)
        cls.tmp = tempfile.TemporaryDirectory(prefix='ppt-regression-',dir=location)
        cls.out = Path(cls.tmp.name)
        cls.seed = g.load(ROOT/'assets/examples/all-layouts.json')
        cls.seed.update(demo=False,fill_style='solid',materials={'papers':[]})
        cls.base = cls.out/'baseline.pptx'; g.generate(cls.seed, cls.base)
        with zipfile.ZipFile(cls.base) as z: cls.parts = {n:z.read(n) for n in z.namelist()}
        for name, color in [('a',(40,90,130)),('b',(200,60,20))]:
            (cls.out/f'{name}.png').write_bytes(png(color))
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def doc(self, index=None):
        d = copy.deepcopy(self.seed)
        if index is not None:d['slides']=[d['slides'][index]]
        return d
    def generate(self, d, name='case'):
        p=self.out/f'{name}.pptx';g.generate(d,p,force=True);return p
    def change(self, part, edit):
        parts=dict(self.parts);root=E.fromstring(parts[part]);edit(root);parts[part]=g.xml(root)
        p=self.out/'mutated.pptx';p.write_bytes(g.zipbytes(parts));return p
    def test_release_manifest_detects_drift_and_missing_assets(self):
        root = self.out/'package'
        (root/'assets').mkdir(parents=True)
        (root/'references').mkdir()
        (root/'assets/template-system.json').write_text('{"version":"1.2.1"}', encoding='utf-8')
        (root/'references/v1.2.1-hashes.json').write_text('{"version":"1.2.1","sha256":{}}', encoding='utf-8')
        (root/'references/approved-standard.json').write_text('{"design_files":{},"approved_examples":{}}', encoding='utf-8')
        payload = root/'payload.txt'
        payload.write_text('original', encoding='utf-8')
        manifest = ''.join(f'{release.digest(p)}  {n}\n' for n,p in sorted(release.package_files(root).items()))
        (root/'SHA256SUMS.txt').write_text(manifest, encoding='utf-8')
        self.assertTrue(release.verify(root)['ok'])
        payload.write_text('changed', encoding='utf-8')
        self.assertIn('hash mismatch: payload.txt', release.verify(root)['errors'])
        payload.unlink()
        self.assertIn('missing: payload.txt', release.verify(root)['errors'])
        payload.write_text('original', encoding='utf-8')
        (root/'untracked.txt').write_text('extra', encoding='utf-8')
        self.assertIn('not in manifest: untracked.txt', release.verify(root)['errors'])
    def test_strict_cli_rejects_all_warning_categories(self):
        for kind in ['font','tiny','outside']:
            def edit(root):
                shape=next(s for s in root.findall('.//p:sp',g.NS) if s.findall('.//a:t',g.NS))
                if kind=='font':
                    for n in shape.findall('.//a:ea',g.NS):n.set('typeface','Missing_Font')
                elif kind=='tiny':
                    for n in shape.findall('.//a:rPr',g.NS)+shape.findall('.//a:defRPr',g.NS):n.set('sz','600')
                else:shape.find('p:spPr/a:xfrm/a:off',g.NS).set('x',str(1600*g.EMU))
            p=self.change('ppt/slides/slide1.xml',edit)
            rep=a.audit(p,strict=True);self.assertFalse(rep['ok']);self.assertGreater(rep['warning_count'],0)
            proc=subprocess.run([sys.executable,'-I','-S','-B',str(ROOT/'scripts/audit.py'),str(p),'--strict'],capture_output=True)
            self.assertEqual(proc.returncode,1)
    def test_chart_font_and_size_failures(self):
        def edit(root):
            for n in root.findall('.//a:ea',g.NS):n.set('typeface','Missing_Chart_Font')
            for n in root.findall('.//a:defRPr',g.NS):n.set('sz','75')
        rep=a.audit(self.change('ppt/charts/chart1.xml',edit),strict=True)
        self.assertFalse(rep['ok'])
        self.assertTrue(any('Missing_Chart_Font' in s for s in rep['warnings']))
        self.assertTrue(any('1.0px' in s for s in rep['warnings']))
    def test_table_capacity_rejection_preserves_existing_output(self):
        d=self.doc(3);row=d['slides'][0]['matrix'][1]
        for matrix in [[d['slides'][0]['matrix'][0]]+[row]*24,[[],[]],[['x']*90]*3]:
            d['slides'][0]['matrix']=matrix
            p=self.out/'owned.pptx';p.write_bytes(b'original')
            with self.assertRaises(ValueError):g.generate(d,p,force=True)
            self.assertEqual(p.read_bytes(),b'original')
    def test_audit_rejects_short_table_rows(self):
        def edit(root):
            for row in root.findall('.//a:tbl/a:tr',g.NS):row.set('h',str(10*g.EMU))
        rep=a.audit(self.change('ppt/slides/slide4.xml',edit),strict=True)
        self.assertFalse(rep['ok'])
        self.assertTrue(any('below text minimum' in s for s in rep['warnings']))
    def test_image_missing_or_ambiguous_slot_rejected(self):
        for index in [0,8,10]:
            d=self.doc(index);d['slides'][0]['image']=str(self.out/'a.png')
            with self.assertRaises(ValueError):self.generate(d)
        d=self.doc(4);d['slides'][0]['images']={'unknown':str(self.out/'a.png')}
        with self.assertRaises(ValueError):self.generate(d)
    def test_named_comparison_images_are_distinct_and_visible(self):
        d=self.doc(8);d['slides'][0]['images']={'left_before':str(self.out/'a.png'),'right_before':str(self.out/'b.png')}
        p=self.generate(d)
        with zipfile.ZipFile(p) as z:
            root=E.fromstring(z.read('ppt/slides/slide1.xml'))
            pics=root.findall('.//p:pic',g.NS);self.assertEqual(len(pics),2)
            ids={p.find('p:blipFill/a:blip',g.NS).get(g.q('r','embed')) for p in pics}
            self.assertEqual(len(ids),2)
            rels={r.get('Id'):r.get('Target').lstrip('/') for r in E.fromstring(z.read('ppt/slides/_rels/slide1.xml.rels'))}
            actual={z.read(rels[rid]) for rid in ids}
            self.assertEqual(actual,{(self.out/'a.png').read_bytes(),(self.out/'b.png').read_bytes()})
        self.assertTrue(a.audit(p,strict=True)['ok'])
    def test_duotone_document_inheritance_and_page_override(self):
        for palette in ['P1','P2']:
            for document,page,expected in [(True,None,1),(True,False,0),(False,True,1)]:
                d=self.doc(4);d.update(palette=palette,duotone=document)
                d['slides'][0]['image']=str(self.out/'a.png')
                if page is not None:d['slides'][0]['duotone']=page
                with zipfile.ZipFile(self.generate(d)) as z:
                    r=E.fromstring(z.read('ppt/slides/slide1.xml'))
                    self.assertEqual(len(r.findall('.//a:duotone',g.NS)),expected)
                    pic=r.find('.//p:pic',g.NS);ext=pic.find('p:spPr/a:xfrm/a:ext',g.NS)
                    self.assertAlmostEqual(int(ext.get('cx'))/int(ext.get('cy')),2,places=4)
    def test_highlights_never_silently_truncated(self):
        for hs in [[{'label':str(i)} for i in range(5)],[{'label':'过长标题'*50}],[]]:
            d=self.doc(4);d['slides'][0]['highlights']=hs
            with self.assertRaises(ValueError):self.generate(d)
        d=self.doc(4);d['slides'][0]['highlights']=[{'label':'完整条件','value':'条件满足时成立','detail':'保留全部限定说明'}]
        with zipfile.ZipFile(self.generate(d)) as z:
            text=z.read('ppt/slides/slide1.xml').decode()
            self.assertIn('条件满足时成立',text);self.assertIn('保留全部限定说明',text)
    def test_all_palette_fill_combinations_and_typography(self):
        policy=g.load(ROOT/'assets/template-system.json')['solid_typography']
        for style in ['light','solid']:
            for palette in [f'P{i}' for i in range(1,7)]:
                d=self.doc();d.update(fill_style=style,palette=palette)
                p=self.generate(d);rep=a.audit(p,strict=True)
                self.assertTrue(rep['ok'],rep['errors'])
                with zipfile.ZipFile(p) as z:
                    r=E.fromstring(z.read('ppt/slides/slide4.xml'))
                    for i,row in enumerate(r.findall('.//a:tbl/a:tr',g.NS)):
                        sizes={int(x.get('sz'))/75 for x in row.findall('.//a:rPr',g.NS) if x.get('sz')}
                        self.assertEqual(sizes,{policy['table_header' if i==0 else 'table_data']})
    def test_office_profile(self):
        p=self.out/'office.pptx';g.generate(self.doc(),p,font_profile='office')
        rep=a.audit(p,strict=True);self.assertTrue(rep['ok'],rep['errors'])
    def test_theme_font_and_chart_frame_are_checked(self):
        def edit_theme(root):
            for e in root.findall('.//a:latin',g.NS):e.set('typeface','Bad_Theme_Font')
        parts=dict(self.parts);theme=E.fromstring(parts['ppt/theme/theme1.xml']);edit_theme(theme)
        parts['ppt/theme/theme1.xml']=g.xml(theme)
        chart=E.fromstring(parts['ppt/charts/chart1.xml'])
        for e in chart.findall('.//a:latin',g.NS):e.set('typeface','+mn-lt')
        parts['ppt/charts/chart1.xml']=g.xml(chart)
        p=self.out/'bad-theme.pptx';p.write_bytes(g.zipbytes(parts))
        rep=a.audit(p,strict=True);self.assertFalse(rep['ok'])
        self.assertTrue(any('Bad_Theme_Font' in w for w in rep['warnings']))
        def move(root):
            gf=next(f for f in root.findall('.//p:graphicFrame',g.NS) if f.find('.//c:chart',g.NS) is not None)
            gf.find('p:xfrm/a:off',g.NS).set('x',str(1700*g.EMU))
        self.assertFalse(a.audit(self.change('ppt/slides/slide1.xml',move),strict=True)['ok'])
    def test_config_controls_chart_table_and_title_sizes(self):
        original_load=g.load
        def custom(path):
            d=original_load(path)
            if Path(path).name=='template-system.json':
                d['solid_typography'].update(chart_min=19,table_header=22,table_data=21,title=43)
            return d
        d=self.doc();d['slides']=[d['slides'][3],d['slides'][10]]
        with patch.object(g,'load',side_effect=custom):p=self.generate(d)
        with zipfile.ZipFile(p) as z:
            r=E.fromstring(z.read('ppt/slides/slide1.xml'))
            for i,row in enumerate(r.findall('.//a:tbl/a:tr',g.NS)):
                self.assertEqual({int(x.get('sz'))/75 for x in row.findall('.//a:rPr',g.NS) if x.get('sz')},{22 if i==0 else 21})
            self.assertTrue(any(x.get('sz')=='3225' for x in r.findall('.//a:rPr',g.NS)))
            for n in z.namelist():
                if n.startswith('ppt/charts/chart') and n.endswith('.xml'):
                    chart=E.fromstring(z.read(n))
                    self.assertTrue(all(int(x.get('sz'))>=1425 for x in chart.findall('.//a:defRPr',g.NS) if x.get('sz')))

if __name__=='__main__':unittest.main(verbosity=2)
