"""Real package inspection with adversarial display-order and privacy changes."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
g=module('generate');inspect=module('inspect_deck').inspect
handoff=module('prepare_handoff')


class InspectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(dir=os.environ.get('PPT_TEST_TMP'))
        cls.folder=Path(cls.tmp.name)
        d=g.load(ROOT/'assets/examples/adaptive-solid.json');d['slides']=[d['slides'][1],d['slides'][10]]
        cls.source=cls.folder/'base.pptx';g.generate(d,cls.source)
        with zipfile.ZipFile(cls.source) as z:cls.parts={n:z.read(n) for n in z.namelist()}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def variant(self,change):
        parts=dict(self.parts);change(parts);out=self.folder/(self._testMethodName+'.pptx')
        out.write_bytes(g.zipbytes(parts));return out
    def test_real_native_charts_and_embedded_workbooks(self):
        r=inspect(self.source)
        self.assertTrue(r['ok'],r['errors']);self.assertEqual(r['totals']['native_charts'],6)
        self.assertEqual(r['totals']['charts_with_embedded_workbooks'],6)
        self.assertEqual([p['native_charts'] for p in r['pages']],[2,4])
        self.assertEqual(r['privacy_indicators'],[])  # XML namespace URLs are not Windows paths.
    def test_reordered_slides_report_display_order(self):
        def reorder(parts):
            root=ET.fromstring(parts['ppt/presentation.xml']);order=root.find('p:sldIdLst',g.NS)
            a=order[0];order.remove(a);order.append(a);parts['ppt/presentation.xml']=g.xml(root)
        r=inspect(self.variant(reorder))
        self.assertTrue(r['ok']);self.assertEqual([p['native_charts'] for p in r['pages']],[4,2])
    def test_external_dependency_target_not_echoed(self):
        def add(parts):
            n='ppt/slides/_rels/slide1.xml.rels';r=ET.fromstring(parts[n])
            ET.SubElement(r,'{'+g.REL+'}Relationship',Id='rExternal',Type=g.NS['r']+'/image',TargetMode='External',Target='https://example.org/private?token=DO_NOT_ECHO')
            parts[n]=g.xml(r)
        r=inspect(self.variant(add));self.assertTrue(r['ok']);self.assertEqual(r['offline_dependencies'],1)
        self.assertNotIn('DO_NOT_ECHO',json.dumps(r));self.assertNotIn('example.org',json.dumps(r))
    def test_hyperlink_is_not_offline_media_dependency(self):
        def add(parts):
            n='ppt/slides/_rels/slide1.xml.rels';r=ET.fromstring(parts[n])
            ET.SubElement(r,'{'+g.REL+'}Relationship',Id='rLink',Type=g.NS['r']+'/hyperlink',TargetMode='External',Target='https://example.org')
            parts[n]=g.xml(r)
        r=inspect(self.variant(add));self.assertEqual(r['offline_dependencies'],0);self.assertEqual(len(r['external_relationships']),1)
    def test_sensitive_notes_report_location_without_value(self):
        def add(parts):
            n='ppt/notesSlides/notesSlide1.xml';r=ET.fromstring(parts[n])
            r.find('.//a:t',g.NS).text='PRIVATE-CANARY C:\\Users\\private\\secret.txt ghp_'+'a'*30
            parts[n]=g.xml(r)
        r=inspect(self.variant(add));self.assertTrue(r['ok'])
        self.assertEqual({p['code'] for p in r['privacy_indicators']},{'local_path','credential_like'})
        self.assertNotIn('PRIVATE-CANARY',json.dumps(r));self.assertNotIn('secret.txt',json.dumps(r))
    def test_broken_relationship_fails(self):
        def remove(parts):
            n=next(n for n in parts if n.startswith('ppt/embeddings/') and n.endswith('.xlsx'));del parts[n]
        r=inspect(self.variant(remove));self.assertFalse(r['ok']);self.assertTrue(r['errors'])
    def test_image_only_page_is_flagged_without_claiming_editability(self):
        def image_only(parts):
            n='ppt/slides/slide1.xml';r=ET.fromstring(parts[n]);tree=r.find('p:cSld/p:spTree',g.NS)
            for ch in list(tree)[2:]:tree.remove(ch)
            pic=ET.SubElement(tree,g.q('p','pic'));pr=ET.SubElement(pic,g.q('p','spPr'));xf=ET.SubElement(pr,g.q('a','xfrm'))
            ET.SubElement(xf,g.q('a','off'),x='0',y='0');ET.SubElement(xf,g.q('a','ext'),cx=str(1280*9525),cy=str(720*9525))
            parts[n]=g.xml(r)
        r=inspect(self.variant(image_only));self.assertTrue(r['ok']);self.assertTrue(r['pages'][0]['possible_image_only_page'])
    def test_malformed_and_duplicate_archives(self):
        p=self.folder/'bad.pptx';p.write_bytes(b'not a zip');self.assertFalse(inspect(p)['ok'])
        with zipfile.ZipFile(p,'w') as z:
            z.writestr('same.xml','<x/>')
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore');z.writestr('same.xml','<x/>')
        self.assertFalse(inspect(p)['ok'])
    def test_delivery_without_preview_is_honest_and_portable(self):
        out=self.folder/'delivery';r=handoff.prepare(self.source,out)
        self.assertTrue(r['ok']);self.assertFalse(r['render_evidence_matched'])
        self.assertEqual((out/'presentation.pptx').read_bytes(),self.source.read_bytes())
        manifest=json.loads((out/'delivery-manifest.json').read_text(encoding='utf-8'))
        for n,h in manifest['files'].items():self.assertEqual(h,handoff.sha((out/n).read_bytes()))
        self.assertIn('视觉未验证',(out/'使用与编辑.md').read_text(encoding='utf-8'))
        with self.assertRaises(FileExistsError):handoff.prepare(self.source,out)
    def test_delivery_preview_hashes_and_page_order(self):
        preview=self.folder/'preview';preview.mkdir()
        png=b'\x89PNG\r\n\x1a\nTEST ONLY'
        pages=[]
        for i in [1,2]:
            name=f'slide-{i:02d}.png';(preview/name).write_bytes(png)
            pages.append({'slide':i,'preview_file':name,'preview_sha256':handoff.sha(png)})
        report=dict(source='PRIVATE LOCAL SOURCE',source_sha256=handoff.sha(self.source.read_bytes()),quality_ok=True,source_unchanged=True,slides=pages)
        path=preview/'powerpoint-validation.json';path.write_text(json.dumps(report),encoding='utf-8')
        good=self.folder/'with-preview';self.assertTrue(handoff.prepare(self.source,good,preview)['render_evidence_matched'])
        self.assertNotIn('PRIVATE LOCAL SOURCE',(good/'render-validation.json').read_text(encoding='utf-8'))
        (preview/'slide-01.png').write_bytes(b'CHANGED')
        bad=self.folder/'bad-preview'
        with self.assertRaisesRegex(ValueError,'Preview bytes'):handoff.prepare(self.source,bad,preview)
        self.assertFalse(bad.exists())
        (preview/'slide-01.png').write_bytes(png);report['source_sha256']='0'*64;path.write_text(json.dumps(report),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'exact PPTX'):handoff.prepare(self.source,bad,preview)
        report['source_sha256']=handoff.sha(self.source.read_bytes());report['slides'].reverse();path.write_text(json.dumps(report),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'page order'):handoff.prepare(self.source,bad,preview)
    def test_failed_delivery_write_cleans_only_new_owned_directory(self):
        out=self.folder/'failed';original=Path.open
        def fail(path,*args,**kwargs):
            if args and args[0]=='xb':raise OSError('Disk full')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',fail):
            with self.assertRaises(OSError):handoff.prepare(self.source,out)
        self.assertFalse(out.exists());self.assertTrue(self.source.exists())
    def test_public_delivery_blocks_sensitive_notes(self):
        def sensitive(parts):
            n='ppt/notesSlides/notesSlide1.xml';r=ET.fromstring(parts[n]);r.find('.//a:t',g.NS).text='C:\\Users\\private\\paper.pdf';parts[n]=g.xml(r)
        source=self.variant(sensitive);out=self.folder/'public'
        with self.assertRaisesRegex(ValueError,'local paths'):handoff.prepare(source,out,public=True)
        self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
