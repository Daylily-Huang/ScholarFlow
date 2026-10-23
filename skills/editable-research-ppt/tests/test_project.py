"""Source relocation and native compositions, including real paper-crop fixtures."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    s=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
g=module('generate');exporter=module('export_project');audit=module('audit')


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ.get('PPT_TEST_TMP'));self.folder=Path(self.tmp.name)
        self.doc=g.load(ROOT/'assets/examples/evidence-layouts.json');self.doc['slides']=self.doc['slides'][:1]
        self.doc.update(demo=False,materials={'papers':[{'id':'demo-study','path':'figures/synthetic-study.pdf','figure_status':'relevant'}]})
        examples=ROOT/'assets/examples'
        for paper in self.doc['materials']['papers']:
            p=(examples/paper['path']).resolve();shutil.copyfile(p,self.folder/'paper.pdf');paper['path']='paper.pdf'
        fig=self.doc['slides'][0]['figures'][0];shutil.copyfile((examples/fig['path']).resolve(),self.folder/'figure.png');fig['path']='figure.png'
        self.source=self.folder/'input.json'
    def tearDown(self):self.tmp.cleanup()
    def save(self):self.source.write_text(json.dumps(self.doc,ensure_ascii=False),encoding='utf-8')
    def test_portable_project_rebuild_without_installed_skill(self):
        self.save();a=self.folder/'source project';exporter.export(self.source,a)
        moved=self.folder/'moved folder';a.rename(moved)
        out=self.folder/'rebuilt.pptx';subprocess.run([sys.executable,'-I','-S','-B',str(moved/'rebuild.py'),'--output',str(out)],cwd=self.folder,check=True,capture_output=True)
        self.assertTrue(audit.audit(out,strict=True)['ok'])
        with zipfile.ZipFile(out) as z:
            self.assertIn((self.folder/'figure.png').read_bytes(),[z.read(n) for n in z.namelist() if n.startswith('ppt/media/')])
        self.assertNotIn(str(self.folder), (moved/'input.json').read_text(encoding='utf-8'))
    def test_project_refuses_overwrite_and_outside_asset(self):
        self.save();out=self.folder/'project';out.mkdir()
        with self.assertRaises(FileExistsError):exporter.export(self.source,out)
        self.doc['materials']['papers'][0]['path']='../outside.pdf';self.save()
        with self.assertRaises(ValueError):exporter.export(self.source,self.folder/'new')
        self.assertFalse((self.folder/'new').exists())
    def test_project_rejects_tampering_before_generating(self):
        self.save();p=self.folder/'project';exporter.export(self.source,p)
        (p/'runtime/scripts/generate.py').write_text('CHANGED',encoding='utf-8');out=self.folder/'unexpected.pptx'
        r=subprocess.run([sys.executable,'-I','-S','-B',str(p/'rebuild.py'),'--output',str(out)],capture_output=True)
        self.assertNotEqual(r.returncode,0);self.assertFalse(out.exists())
    def test_edited_input_requires_explicit_opt_in(self):
        self.save();p=self.folder/'project';exporter.export(self.source,p)
        doc=json.loads((p/'input.json').read_text(encoding='utf-8'));doc['slides'][0]['title']='修改后保留原始证据'
        (p/'input.json').write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8');out=self.folder/'edited.pptx'
        cmd=[sys.executable,'-I','-S','-B',str(p/'rebuild.py'),'--output',str(out)]
        blocked=subprocess.run(cmd,capture_output=True);self.assertNotEqual(blocked.returncode,0);self.assertFalse(out.exists())
        subprocess.run(cmd+['--allow-input-edits'],check=True,capture_output=True)
        self.assertTrue(audit.audit(out,strict=True)['ok'])
    def composition(self):
        page=self.doc['slides'][0];page.update(layout='L16',variant='full_width')
        fig=page['figures'][0]
        page['composition']=[{'kind':'text','name':'title','text':page['title'],'box':[32,20,1216,58],'size':42,'bold':True},
          {'kind':'image','figure_index':0,'slot':'original','box':[32,104,850,450]},
          {'kind':'text','name':'caption','text':fig['caption'],'box':[32,568,1216,30],'size':20},
          {'kind':'text','name':'source','text':fig['source'],'box':[32,602,1216,26],'size':17}]
        return page
    def test_native_composition_preserves_complete_original(self):
        self.composition();out=self.folder/'native.pptx';g.generate(self.doc,out,base_dir=self.folder)
        self.assertTrue(audit.audit(out,strict=True)['ok'])
    def test_composition_theme_token_changes_text_not_evidence_pixels(self):
        page=self.composition();page['composition'][0]['color']='primary';self.doc['palette']='P2';page.pop('palette',None)
        out=self.folder/'themed.pptx';g.generate(self.doc,out,base_dir=self.folder)
        self.assertTrue(audit.audit(out,strict=True)['ok'])
        with zipfile.ZipFile(out) as z:
            self.assertIn((self.folder/'figure.png').read_bytes(),[z.read(n) for n in z.namelist() if n.startswith('ppt/media/')])
            expected=g.load(ROOT/'assets/template-system.json')['solid_palettes']['P2']['primary'][1:].encode()
            self.assertIn(expected,z.read('ppt/slides/slide1.xml'))
    def test_composition_rejects_unused_figure_or_missing_caption(self):
        page=self.composition();page['composition']=[n for n in page['composition'] if n['kind']!='image']
        with self.assertRaises(ValueError):g.generate(self.doc,self.folder/'unused.pptx',base_dir=self.folder)
        page=self.composition();page['composition']=[n for n in page['composition'] if n.get('name')!='caption']
        with self.assertRaises(ValueError):g.generate(self.doc,self.folder/'caption.pptx',base_dir=self.folder)
    def test_composition_rejects_unsafe_box_unknown_field_and_tiny_text(self):
        for field,value in [('box',[-1,0,400,40]),('box',[0,0,float('nan'),40]),('size',8),('unsupported','value')]:
            d=copy.deepcopy(self.doc);self.composition();page=copy.deepcopy(self.doc['slides'][0]);page['composition'][0][field]=value;d['slides']=[page]
            with self.assertRaises(ValueError):g.generate(d,self.folder/'bad.pptx',base_dir=self.folder)
        self.composition();bad=copy.deepcopy(self.doc);bad['slides'][0]['layout']='L1';bad['demo']=True
        with self.assertRaisesRegex(ValueError,'composition'):g.generate(bad,self.folder/'wrong-layout.pptx',base_dir=self.folder)
        page=self.composition();page['experiment_scene']=page.pop('composition')
        with self.assertRaisesRegex(ValueError,'experiment_scene'):g.generate(self.doc,self.folder/'legacy.pptx',base_dir=self.folder)


if __name__=='__main__':unittest.main()
