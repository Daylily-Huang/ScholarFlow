"""Regression coverage for contextual vocabulary and failure-safe PDF export."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/paper-close-read/scripts'))
from build_html import build
from validate_content import validate
from export_pdf import export_pdf


class VocabularyAndPdf(unittest.TestCase):
    def setUp(self):
        self.folder = ROOT / 'examples/paper-close-read/hardy1908/reading-data'
        self.values = [json.loads((self.folder / name).read_text(encoding='utf-8-sig')) for name in ('fulltext.json', 'translations.json', 'guide.json')]

    def test_unattested_duplicate_or_malformed_vocabulary_rejected(self):
        for vocab in ([{'en':'absent-vocabulary','zh':'missing'}], [{'en':'TO','zh':'x'}, {'en':'to','zh':'y'}], [{'en':'TO'}], [42], 'not a list'):
            values=copy.deepcopy(self.values)
            body=next(r for r in values[1] if r.get('role','body')=='body')
            body['vocabulary']=vocab
            with self.subTest(vocab=vocab):
                self.assertTrue(validate(*values)['errors'])

    def test_legacy_without_vocabulary_still_builds_and_new_values_are_escaped(self):
        legacy=copy.deepcopy(self.values)
        for record in legacy[1]:record.pop('vocabulary',None)
        self.assertFalse(validate(*legacy)['errors'])
        record=next(r for r in self.values[1] if r.get('role','body')=='body')
        record['vocabulary']=[{'en':'TO','zh':'<img src=x onerror=evil()> & meaning'}]
        html,_=build(*self.values,self.folder)
        self.assertIn('&lt;img src=x onerror=evil()&gt; &amp; meaning',html)
        self.assertIn('class="paragraph-vocabulary"',html)
        self.assertIn('window.readerPDF={prepare,restore}',html)

    def test_bad_source_or_render_failure_keeps_existing_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'reader.html';out=root/'keep.pdf';out.write_bytes(b'previous PDF')
            source.write_text('old page',encoding='utf-8')
            with self.assertRaises(ValueError):export_pdf(source,out,root)
            source.write_text('window.readerPDF={prepare,restore}',encoding='utf-8')
            class Failed:
                returncode=1
                stdout=b'failed rendering'
            with patch('export_pdf.find_browser',return_value='browser'),patch('export_pdf.subprocess.run',return_value=Failed()):
                with self.assertRaises(ValueError):export_pdf(source,out,root)
            self.assertEqual(out.read_bytes(),b'previous PDF')

    def test_all_example_vocabulary_is_attested_and_originals_unchanged(self):
        for data in (ROOT/'examples/paper-close-read').glob('*/reading-data'):
            values=[json.loads((data/name).read_text(encoding='utf-8-sig')) for name in ('fulltext.json','translations.json','guide.json')]
            with (data/'source.md').open(encoding='utf-8-sig',newline='') as stream:source=stream.read()
            with self.subTest(paper=data.parent.name):
                self.assertFalse(validate(*values,source)['errors'])
                self.assertTrue(all(r.get('vocabulary') for r in values[1] if r.get('role','body')=='body'))


if __name__=='__main__':unittest.main()
