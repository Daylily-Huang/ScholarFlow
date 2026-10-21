"""Adversarial media provenance and PPT embedding checks, no Office required."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('audit_media',ROOT/'scripts/audit_media.py')
media=importlib.util.module_from_spec(spec);spec.loader.exec_module(media)


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ.get('PPT_TEST_TMP'))
        self.root=Path(self.tmp.name)
        for name,data in [('demo.mp4',b'opaque-media-byte-test'),('source.svg',b'<svg/>'),('still.png',b'opaque-still-byte-test')]:
            (self.root/name).write_bytes(data)
        sha=lambda name:hashlib.sha256((self.root/name).read_bytes()).hexdigest()
        self.item={'id':'demo','path':'demo.mp4','sha256':sha('demo.mp4'),'origin':'original',
                   'role':'concept_animation','representation':'video','editable':'source','changes':'rendered SVG',
                   'placements':[1],'source_path':'source.svg','source_sha256':sha('source.svg'),
                   'static_fallback':'still.png','fallback_sha256':sha('still.png'),'schematic':True,'explanation':'geometry only'}
        self.pptx=self.root/'demo.pptx'
        self.package()
    def tearDown(self):self.tmp.cleanup()
    def package(self,external=False,wrong=False,parts=(1,),video_part=1):
        ns='http://schemas.openxmlformats.org/package/2006/relationships'
        rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships/video'
        target='https://example.org/demo.mp4' if external else '../media/demo.mp4'
        mode=' TargetMode="External"' if external else ''
        with zipfile.ZipFile(self.pptx,'w') as z:
            office='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
            ids=''.join(f'<p:sldId id="{256+i}" r:id="rId{i}"/>' for i in parts)
            z.writestr('ppt/presentation.xml',f'<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="{office}"><p:sldIdLst>{ids}</p:sldIdLst></p:presentation>')
            rels=''.join(f'<Relationship Id="rId{i}" Type="{office}/slide" Target="slides/slide{i}.xml"/>' for i in parts)
            z.writestr('ppt/_rels/presentation.xml.rels',f'<Relationships xmlns="{ns}">{rels}</Relationships>')
            for i in parts:z.writestr(f'ppt/slides/slide{i}.xml','<slide/>')
            z.writestr(f'ppt/slides/_rels/slide{video_part}.xml.rels',f'<Relationships xmlns="{ns}"><Relationship Id="rId1" Type="{rel}" Target="{target}"{mode}/></Relationships>')
            if not external:z.writestr('ppt/media/demo.mp4',b'wrong' if wrong else (self.root/'demo.mp4').read_bytes())
    def check(self,item=None,pptx=True):
        p=self.root/'manifest.json';p.write_text(json.dumps({'version':1,'assets':[self.item if item is None else item]}),encoding='utf-8')
        return media.audit(p,self.pptx if pptx else None)
    def test_valid_embedded_media(self):self.assertTrue(self.check()['ok'])
    def test_missing_or_changed_source_and_fallback(self):
        for key in ['path','source_path','static_fallback']:
            item=copy.deepcopy(self.item);item[key]='missing.file';self.assertFalse(self.check(item)['ok'])
        for key in ['sha256','source_sha256','fallback_sha256']:
            item=copy.deepcopy(self.item);item[key]='0'*64;self.assertFalse(self.check(item)['ok'])
    def test_online_license_required(self):
        item=copy.deepcopy(self.item);item['origin']='online';self.assertFalse(self.check(item)['ok'])
        item.update(author='Artist',license='CC BY 4.0',source_url='https://example.org/art',license_url='https://creativecommons.org/licenses/by/4.0/')
        self.assertTrue(self.check(item)['ok'])
        item['source_url']='file:///secret';self.assertFalse(self.check(item)['ok'])
    def test_video_cannot_claim_native_editability(self):
        item=copy.deepcopy(self.item);item['editable']='native';self.assertFalse(self.check(item)['ok'])
    def test_path_traversal_and_absolute_paths(self):
        for name in ['../demo.mp4','/demo.mp4','C:/demo.mp4','..\\demo.mp4']:
            item=copy.deepcopy(self.item);item['path']=name;self.assertFalse(self.check(item)['ok'])
    def test_wrong_page_and_boolean_page(self):
        for pages in [[2],[True],[0],[],[1,1]]:
            item=copy.deepcopy(self.item);item['placements']=pages;self.assertFalse(self.check(item)['ok'])
    def test_external_and_wrong_video_bytes(self):
        self.package(external=True);self.assertFalse(self.check()['ok'])
        self.package(wrong=True);self.assertFalse(self.check()['ok'])
    def test_missing_schematic_explanation(self):
        for key in ['schematic','explanation']:
            item=copy.deepcopy(self.item);del item[key];self.assertFalse(self.check(item)['ok'])
    def test_undeclared_video_and_duplicate_id(self):
        p=self.root/'manifest.json'
        for assets in [[],[self.item,self.item]]:
            p.write_text(json.dumps({'version':1,'assets':assets}),encoding='utf-8')
            self.assertFalse(media.audit(p,self.pptx)['ok'])
    def test_reordered_slides_use_display_order(self):
        self.package(parts=(2,1),video_part=1)
        self.assertFalse(self.check()['ok'])
        self.item['placements']=[2]
        self.assertTrue(self.check()['ok'])
    def test_nonconsecutive_slide_part_names(self):
        self.package(parts=(8,42),video_part=42)
        self.item['placements']=[2]
        self.assertTrue(self.check()['ok'])
        self.item['placements']=[42]
        self.assertFalse(self.check()['ok'])
    def test_malformed_manifest_returns_failure(self):
        p=self.root/'bad.json'
        for data in ['[]','null','{bad','{"version":1,"assets":[null]}']:
            p.write_text(data,encoding='utf-8');self.assertFalse(media.audit(p)['ok'])


if __name__=='__main__':unittest.main()
