"""Input diagnostics and interrupted-save tests for ordinary authoring."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

g=module('generate');p=module('preflight')


class AuthoringTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ.get('PPT_TEST_TMP'))
        self.folder=Path(self.tmp.name)
        self.doc=json.loads((ROOT/'assets/examples/adaptive-solid.json').read_text(encoding='utf-8'))
    def tearDown(self):self.tmp.cleanup()
    def test_valid_current_example(self):
        self.assertTrue(p.inspect(self.doc)['ok'])
    def test_malformed_container_and_required_field_paths(self):
        for obj in [None,[],{'slides':'bad'},{'scenario':[],'palette':{},'slides':[None]}]:
            self.assertFalse(p.inspect(obj)['ok'])
        del self.doc['slides'][0]['center']
        result=p.inspect(self.doc)
        self.assertTrue(any(i['path']=='slides[0].center' for i in result['issues']))
    def test_chapter_number_highlight_and_title(self):
        for key,value in [('section','04'),('active',True),('chapters',['wrong']*4),('lines',['wrong','detail'])]:
            doc=copy.deepcopy(self.doc);doc['slides'][6][key]=value
            self.assertFalse(p.inspect(doc)['ok'],key)
    def test_repetition_advisory_does_not_ban_legitimate_reuse(self):
        self.doc['slides']=[self.doc['slides'][0]]*3
        result=p.inspect(self.doc)
        self.assertTrue(result['ok'])
        self.assertIn('repetitive_rhythm',[i['code'] for i in result['issues']])
    def test_source_and_image_paths(self):
        self.doc['slides'][0]['sources']=[]
        self.doc['slides'][1]['image']='missing.png'
        result=p.inspect(self.doc,self.folder)
        self.assertFalse(result['ok'])
        codes={i['code'] for i in result['issues']}
        self.assertTrue({'sources_required','file_unavailable'} <= codes)
    def test_atomic_save_existing_and_success(self):
        out=self.folder/'talk.pptx';out.write_bytes(b'ORIGINAL')
        with self.assertRaises(FileExistsError):g.atomic_write(out,b'NEW')
        self.assertEqual(out.read_bytes(),b'ORIGINAL')
        g.atomic_write(out,b'NEW',force=True)
        self.assertEqual(out.read_bytes(),b'NEW')
        self.assertEqual(list(self.folder.iterdir()),[out])
    def test_interrupted_replace_preserves_original(self):
        out=self.folder/'talk.pptx';out.write_bytes(b'ORIGINAL')
        with patch.object(g.os,'replace',side_effect=PermissionError('File locked')):
            with self.assertRaises(PermissionError):g.atomic_write(out,b'NEW',force=True)
        self.assertEqual(out.read_bytes(),b'ORIGINAL')
        self.assertEqual(list(self.folder.iterdir()),[out])
    def test_racing_creator_is_never_overwritten(self):
        out=self.folder/'talk.pptx'
        def competing_link(source,destination):
            Path(destination).write_bytes(b'CONCURRENT FILE')
            raise FileExistsError('created while generating')
        with patch.object(g.os,'link',side_effect=competing_link):
            with self.assertRaises(FileExistsError):g.atomic_write(out,b'NEW')
        self.assertEqual(out.read_bytes(),b'CONCURRENT FILE')
        self.assertEqual(list(self.folder.iterdir()),[out])
    def test_failed_flush_never_publishes(self):
        out=self.folder/'talk.pptx'
        with patch.object(g.os,'fsync',side_effect=OSError('Disk full')):
            with self.assertRaises(OSError):g.atomic_write(out,b'NEW')
        self.assertEqual(list(self.folder.iterdir()),[])


if __name__=='__main__':unittest.main()
