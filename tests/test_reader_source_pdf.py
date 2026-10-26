"""Source-page mapping, integrity and compatibility without a PDF runtime dependency."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/paper-close-read/scripts'))
from source_pdf import page_button,validate_source_pdf
from build_html import build
import test_paper_reader


class SourcePdf(unittest.TestCase):
    def fixture(self,root):
        source,data,records,guide=test_paper_reader.PaperReader().fixture()
        pdf=root/'original.pdf';pdf.write_bytes(b'%PDF-fixture: validator checks bytes, real rendering tested separately')
        page=root/'page.jpg';page.write_bytes(b'page fixture image')
        data['source_pdf']={'file':'original.pdf','sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'page_count':2,
          'pages':[{'page':1,'src':'page.jpg','sha256':hashlib.sha256(page.read_bytes()).hexdigest()}]}
        return source,data,records,guide

    def test_verified_page_has_direct_button_unknown_page_only_browses(self):
        with tempfile.TemporaryDirectory() as tmp:
            source,data,records,guide=self.fixture(Path(tmp));item=data['sections'][1]['items'][0]
            item['source']['pdf_page']=1
            self.assertIn('data-pdf-located="false"',page_button(item,data))
            item['source'].update(status='verified',verification_note='Compared with source page')
            self.assertIn('data-open-pdf-page="1"',page_button(item,data))
            item['source']['pdf_page']=2
            self.assertIn('data-pdf-located="false"',page_button(item,data))

    def test_bad_page_catalog_original_or_image_fails_without_modifying_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,data,records,guide=self.fixture(root)
            self.assertFalse(validate_source_pdf(data,root))
            for value in ([],{'pages':'bad'}, {'pages':[],'page_count':0}, {'pages':[None],'page_count':2,'file':'original.pdf','sha256':'a'*64}):
                changed=copy.deepcopy(data);changed['source_pdf']=value
                with self.subTest(value=value):self.assertTrue(validate_source_pdf(changed,root))
            duplicate=copy.deepcopy(data);duplicate['source_pdf']['pages']*=2
            self.assertTrue(any('Duplicate' in e for e in validate_source_pdf(duplicate,root)))
            invalid=copy.deepcopy(data);invalid['source_pdf']['pages'][0]['page']=3
            self.assertTrue(validate_source_pdf(invalid,root))
            (root/'page.jpg').write_bytes(b'wrong page')
            self.assertTrue(any('page image' in e for e in validate_source_pdf(data,root)))
            original=(root/'original.pdf').read_bytes();(root/'original.pdf').write_bytes(original+b'changed')
            self.assertTrue(any('original PDF' in e for e in validate_source_pdf(data,root)))

    def test_single_file_embeds_only_prepared_pages_and_legacy_still_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            source,data,records,guide=self.fixture(Path(tmp))
            html,_=build(data,records,guide,tmp,source)
            self.assertIn('data:image/jpeg;base64,',html)
            self.assertIn('readerPdfPages={open}',html)
            config=json.loads(html.split('<script id="reader-config" type="application/json">',1)[1].split('</script>',1)[0])
            self.assertEqual(config['sourcePdf']['pageCount'],2)
            self.assertEqual(len(config['sourcePdf']['pages']),1)
            data.pop('source_pdf');html,_=build(data,records,guide,tmp,source)
            config=json.loads(html.split('<script id="reader-config" type="application/json">',1)[1].split('</script>',1)[0])
            self.assertIsNone(config['sourcePdf'])


if __name__=='__main__':unittest.main()
