"""Header capacity and optional environment detection without changing approved sizes."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
g=module('generate');audit=module('audit');doctor=module('check_environment')


class BilingualTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ.get('PPT_TEST_TMP'));self.folder=Path(self.tmp.name)
        self.doc=g.load(ROOT/'assets/examples/adaptive-solid.json');self.doc['slides']=[self.doc['slides'][1]]
    def tearDown(self):self.tmp.cleanup()
    def test_english_title_over_38_characters_fits_at_approved_size(self):
        self.doc['slides'][0]['title']='Connecting field observations with habitat models'
        out=self.folder/'long.pptx';g.generate(self.doc,out)
        self.assertTrue(audit.audit(out,strict=True)['ok'])
        with zipfile.ZipFile(out) as z:
            root=ET.fromstring(z.read('ppt/slides/slide1.xml'))
            matching=[sp for sp in root.findall('.//p:sp',g.NS) if self.doc['slides'][0]['title']==''.join(t.text or '' for t in sp.findall('.//a:t',g.NS))]
            self.assertEqual(matching[0].find('.//a:rPr',g.NS).get('sz'),'3150')
    def test_translation_is_native_and_preserves_chart_workbooks(self):
        base=self.folder/'base.pptx';g.generate(self.doc,base)
        self.doc['slides'][0]['title_translation']='Field observations and habitat evidence'
        out=self.folder/'bilingual.pptx';g.generate(self.doc,out)
        self.assertTrue(audit.audit(out,strict=True)['ok'])
        with zipfile.ZipFile(base) as a,zipfile.ZipFile(out) as b:
            for name in a.namelist():
                if name.startswith(('ppt/charts/','ppt/embeddings/','ppt/media/')):self.assertEqual(a.read(name),b.read(name))
            root=ET.fromstring(b.read('ppt/slides/slide1.xml'))
            translated=[sp for sp in root.findall('.//p:sp',g.NS) if sp.find('p:nvSpPr/p:cNvPr',g.NS).get('name','').startswith('title-translation-')]
            self.assertEqual(len(translated),1);self.assertEqual(translated[0].find('.//a:rPr',g.NS).get('sz'),'1275')
    def test_overflow_and_cover_translation_do_not_write_output(self):
        for key,value in [('title','W'*200),('title_translation','a\nb'),('title_translation','W'*300)]:
            doc=copy.deepcopy(self.doc);doc['slides'][0][key]=value;out=self.folder/(key+str(len(value))+'.pptx')
            with self.assertRaises(ValueError):g.generate(doc,out)
            self.assertFalse(out.exists())
        doc=g.load(ROOT/'assets/examples/adaptive-solid.json');doc['slides']=[doc['slides'][4]];doc['slides'][0]['title_translation']='Unsupported cover field'
        with self.assertRaises(ValueError):g.generate(doc,self.folder/'cover.pptx')
    def test_font_family_registry_aliases_are_recognized(self):
        self.assertTrue(doctor.family_detected('Microsoft YaHei',['Microsoft YaHei & Microsoft YaHei UI (TrueType)']))
        self.assertTrue(doctor.family_detected('SimSun',['宋体 (TrueType)']))
        self.assertTrue(doctor.family_detected('Noto Sans CJK SC',['Noto Sans CJK SC Bold (OpenType)']))
        self.assertFalse(doctor.family_detected('SimSun',['SimSun-ExtB (TrueType)']))
    def test_new_layout_bilingual_header_remains_native(self):
        d=g.load(ROOT/'assets/examples/evidence-layouts.json')
        d['slides']=[next(p for p in d['slides'] if p['layout']=='L19')]
        d.update(demo=True,visual_mode='adaptive')
        d['slides'][0]['title_translation']='Monitoring schedule and repeated surveys'
        out=self.folder/'timeline.pptx';g.generate(d,out,base_dir=ROOT/'assets/examples')
        self.assertTrue(audit.audit(out,strict=True)['ok'])
    def test_optional_missing_renderer_does_not_fail_generation_environment(self):
        with patch.object(doctor.platform,'system',return_value='Linux'),patch.object(doctor.shutil,'which',return_value=None):
            r=doctor.check('portable');self.assertTrue(r['ok']);self.assertFalse(r['capabilities']['rendering_verified'])
            self.assertTrue(all(f['status']=='unverified' for f in r['capabilities']['fonts']))


if __name__=='__main__':unittest.main()
