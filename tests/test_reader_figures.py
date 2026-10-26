"""Original figure loss, panel omissions and explanatory placement regressions."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/paper-close-read/scripts'))
from figure_inventory import draft_inventory, inventory_errors
from import_jats import import_article
from parse_mineru import parse_document
from validate_content import validate
from build_html import build
import test_paper_reader


class OriginalFigures(unittest.TestCase):
    def source(self,root):
        xml=root/'original.xml'
        xml.write_text('<article xmlns:xlink="http://www.w3.org/1999/xlink"><front><article-meta><title-group><article-title>Trial</article-title></title-group></article-meta></front><body><sec><title>Results</title><p>Before.</p><fig id="f1"><label>Figure 1</label><caption><p>Two panels A and B.</p></caption><graphic xlink:href="panel-a.jpg"/><graphic xlink:href="panel-b.jpg"/></fig><p>After.</p></sec></body></article>',encoding='utf-8')
        import_article(xml,root)
        data=json.loads((root/'fulltext.json').read_text(encoding='utf-8'))
        images=[i for s in data['sections'] for i in s['items'] if i['t']=='figure']
        (root/'images').mkdir(exist_ok=True)
        # Rendering only embeds bytes; browser-level real-article tests verify image decoding.
        for i in images:(root/i['src']).write_bytes(b'fixture image bytes')
        audit=draft_inventory(data,xml,'jats');audit.update(status='verified',review_note='Checked against source figure and panels')
        for entry in audit['figures']:entry.update(panels=['A','B'],checked_panels=['A','B'],caption_checked=True,verified=True,verification_note='Both complete panels and caption compared')
        audit['asset_sha256']={i['id']:hashlib.sha256((root/i['src']).read_bytes()).hexdigest() for i in images}
        data['figure_inventory']=audit
        return data,images

    def test_jats_import_keeps_multiple_graphics_and_following_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,images=self.source(Path(tmp))
            self.assertEqual(len(images),2)
            self.assertTrue(any(i['raw'].strip()=='After.' for s in data['sections'] for i in s['items']))
            self.assertEqual(inventory_errors(data,{},tmp,True)[0],[])

    def test_jats_missing_source_figure_or_one_graphic_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,images=self.source(Path(tmp))
            for mode in ['drop_entry','drop_block']:
                changed=copy.deepcopy(data)
                if mode=='drop_entry':changed['figure_inventory']['figures']=[]
                else:
                    changed['figure_inventory']['figures'][0]['blocks'].pop()
                    for s in changed['sections']:s['items']=[i for i in s['items'] if i['id']!=images[-1]['id']]
                with self.subTest(mode=mode):self.assertTrue(inventory_errors(changed,{},tmp,True)[0])

    def test_unchecked_panel_changed_source_changed_image_and_wrong_mapping_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,images=self.source(root)
            changed=copy.deepcopy(data);changed['figure_inventory']['figures'][0]['checked_panels']=['A']
            self.assertTrue(inventory_errors(changed,{},root,True)[0])
            changed=copy.deepcopy(data);changed['figure_inventory']['figures'][0]['blocks']=['unknown']
            self.assertTrue(inventory_errors(changed,{},root,True)[0])
            file=root/images[0]['src'];file.write_bytes(b'changed picture')
            self.assertTrue(any('image SHA256' in e for e in inventory_errors(data,{},root,True)[0]))
            (root/'original.xml').write_text('<article/>',encoding='utf-8')
            self.assertTrue(any('source SHA256' in e for e in inventory_errors(data,{},root,True)[0]))

    def test_pdf_needs_every_page_reviewed_even_when_figures_list_is_empty(self):
        data={'sections':[],'figure_inventory':{'source':{'kind':'pdf','file':'original.pdf','sha256':'a'*64,'page_count':3},'status':'verified','review_note':'review','checked_pages':[1,2],'figures':[],'asset_sha256':{}}}
        self.assertTrue(any('every page' in e for e in inventory_errors(data,{},None)[0]))
        data['figure_inventory']['checked_pages']=[1,2,3]
        self.assertFalse(inventory_errors(data,{},None)[0])

    def test_new_strict_mode_blocks_missing_audit_but_legacy_reports_warning(self):
        source,data,records,guide=test_paper_reader.PaperReader().fixture()
        with tempfile.TemporaryDirectory() as tmp:
            html,report=build(data,records,guide,tmp,source)
            self.assertIn('原图完整性待核对',html)
            with self.assertRaisesRegex(ValueError,'图清单'):build(data,records,guide,tmp,source,require_figure_audit=True)

    def test_malformed_inventory_reports_input_errors_instead_of_traceback(self):
        source,data,records,guide=test_paper_reader.PaperReader().fixture()
        for inventory in ([],{'source':{'kind':[]},'figures':[]},{'source':{},'figures':[42]}, {'source':{},'figures':[],'pdf_review':'bad'}):
            data['figure_inventory']=inventory
            with self.subTest(inventory=inventory):self.assertTrue(validate(data,records,guide,source)['errors'])

    def test_inline_formula_graphics_and_alternative_formats_preserve_one_picture_each(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'input.xml'
            source.write_text('<article xmlns:xlink="http://www.w3.org/1999/xlink"><front><article-meta><title-group><article-title>Example</article-title></title-group></article-meta></front><body><p>Before<inline-formula id="eq1"><inline-graphic xlink:href="eq.png"/></inline-formula>after.</p><fig id="f1"><label>Figure 1</label><alternatives><graphic xlink:href="result.jpg"/><graphic xlink:href="result.tif"/></alternatives></fig></body></article>',encoding='utf-8')
            import_article(source,root)
            data=json.loads((root/'fulltext.json').read_text(encoding='utf-8'))
            items=[i for s in data['sections'] for i in s['items']]
            self.assertEqual([i['src'] for i in items if i['t']=='figure'],['images/eq.png','images/result.jpg'])
            self.assertTrue(any(i['raw'].strip()=='after.' for i in items))
            inventory=draft_inventory(data,source,'jats')
            self.assertEqual([len(e['blocks']) for e in inventory['figures']],[1,1])

    def test_inline_image_markup_cannot_silently_render_as_plain_prose(self):
        source,data,records,guide=test_paper_reader.PaperReader().fixture()
        data['sections'][1]['items'][0]['raw']='See ![Result](plot.png) here.'
        self.assertTrue(any('Image markup was parsed as prose' in e for e in validate(data,records,guide)['errors']))

    def test_real_key_result_is_required_in_walkthrough_and_rendered_in_place(self):
        folder=ROOT/'examples/paper-close-read/wilcox/reading-data'
        values=[json.loads((folder/n).read_text(encoding='utf-8-sig')) for n in ['fulltext.json','translations.json','guide.json']]
        html,report=build(*values,folder,require_figure_audit=True)
        self.assertFalse(report['errors']);self.assertIn('data-source-figure=',html)
        self.assertEqual(html.count('class="guide-source-figure"'),3)
        removed=copy.deepcopy(values)
        for c in removed[2]['story']['walkthrough']:c.pop('figures',None)
        self.assertTrue(any('Key result images' in e for e in validate(*removed,asset_root=folder)['errors']))
        wrong=copy.deepcopy(values);c=next(c for c in wrong[2]['story']['walkthrough'] if c.get('figures'));c['figures'][0]['after']=999
        self.assertTrue(any('existing paragraph index' in e for e in validate(*wrong,asset_root=folder)['errors']))


if __name__=='__main__':unittest.main()
