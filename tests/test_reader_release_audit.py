"""Release audit regressions over independently reproduced source-loss shapes."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/paper-close-read/scripts'))
from import_jats import import_article
from figure_inventory import jats_figures
from build_html import build
from validate_content import validate
import test_paper_reader


class ReleaseAudit(unittest.TestCase):
    def test_image_tables_inline_images_and_poetry_survive_independent_inventory(self):
        xml='''<article xmlns:xlink="http://www.w3.org/1999/xlink"><front><article-meta><article-title>Study</article-title></article-meta></front><body><sec><title>Evidence</title><table-wrap id="t1"><label>Table 1</label><graphic xlink:href="measurements.png"/></table-wrap><p>Before <inline-graphic xlink:href="symbol.png"/> after.</p><disp-quote><verse-group><verse-line>First <italic>specific</italic> line.</verse-line><verse-line>Second line.</verse-line></verse-group><attrib>Poet p. 8</attrib></disp-quote></sec></body></article>'''
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'a.xml';source.write_text(xml,encoding='utf-8')
            import_article(source,root/'data')
            data=json.loads((root/'data/fulltext.json').read_text(encoding='utf-8'))
            items=[i for s in data['sections'] for i in s['items']]
            self.assertEqual([i['src'] for i in items if i['t']=='figure'],['images/measurements.png','images/symbol.png'])
            self.assertEqual(sum(len(e['hrefs']) for e in jats_figures(source)),2)
            lines=[i for i in items if i['raw'].strip() in ['First specific line.','Second line.']]
            self.assertEqual(len(lines),2)
            self.assertTrue(all(i['source']['quote_attribution']=='Poet p. 8' for i in lines))
            self.assertTrue(any('em' in r.get('styles',[]) for r in lines[0]['source']['inline_runs']))
            self.assertEqual((root/'data/original-jats.xml').read_bytes(),source.read_bytes())

    def test_structured_table_alternative_is_verified_without_duplicating_raster(self):
        from figure_inventory import inventory_errors
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);xml=root/'a.xml'
            xml.write_text('<article xmlns:xlink="http://www.w3.org/1999/xlink"><body><table-wrap id="T1"><alternatives><graphic xlink:href="duplicate.png"/><table><tr><td>Reliable value 42</td></tr></table></alternatives></table-wrap></body></article>',encoding='utf-8')
            import_article(xml,root/'data');data=json.loads((root/'data/fulltext.json').read_text(encoding='utf-8'))
            self.assertEqual(len(jats_figures(xml)),0)
            self.assertEqual(sum(i['t']=='table' for s in data['sections'] for i in s['items']),1)
            self.assertFalse(any('structured table content differs' in e for e in inventory_errors(data,{},root/'data')[0]))
            for section in data['sections']:section['items']=[i for i in section['items'] if i['t']!='table']
            self.assertTrue(any('structured table content differs' in e for e in inventory_errors(data,{},root/'data')[0]))

    def test_quote_mixed_inline_text_and_wrapper_tails_are_not_dropped(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);xml=root/'a.xml'
            xml.write_text('<article><body><disp-quote>Opening <italic>key <bold>phrase</bold></italic> matters.<attrib>Poet p. 4</attrib></disp-quote><boxed-text>Container opening.<p>Inner evidence.</p>Container tail.</boxed-text></body></article>',encoding='utf-8')
            import_article(xml,root/'data')
            data=json.loads((root/'data/fulltext.json').read_text(encoding='utf-8'))
            items=[i for s in data['sections'] for i in s['items']]
            joined=' '.join(i['raw'].strip() for i in items)
            for fragment in ['Opening','key phrase','matters.','Container opening.','Inner evidence.','Container tail.']:self.assertIn(fragment,joined)
            phrase=next(i for i in items if i['raw'].strip()=='key phrase')
            self.assertEqual(phrase['source'].get('quote_attribution'),'Poet p. 4')
            self.assertTrue(any('em' in run['styles'] for run in phrase['source']['inline_runs']))

    def test_repeat_import_preserves_existing_source_and_reviews(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'a.xml';source.write_text('<article><body><p>Evidence.</p></body></article>',encoding='utf-8')
            import_article(source,root/'data')
            full=root/'data/fulltext.json';full.write_text(full.read_text(encoding='utf-8')+'\n',encoding='utf-8')
            before={p.name:p.read_bytes() for p in (root/'data').iterdir() if p.is_file()}
            with self.assertRaisesRegex(ValueError,'already exists'):import_article(source,root/'data')
            self.assertEqual(before,{p.name:p.read_bytes() for p in (root/'data').iterdir() if p.is_file()})

    def test_unsupported_math_is_explicit_and_does_not_write_partial_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'a.xml';source.write_text('<article><body><p>Before<inline-formula><math><mfrac><mi>a</mi><mi>b</mi></mfrac></math></inline-formula>after.</p></body></article>',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'refusing to flatten'):import_article(source,root/'data')
            self.assertFalse((root/'data/source.md').exists())

    def test_motion_can_follow_first_paragraph_without_splitting_story(self):
        source,data,records,guide=test_paper_reader.PaperReader().fixture();bid=records[0]['id']
        chapter=guide['story']['walkthrough'][0];chapter['paragraphs']=['Explain here.','Later distinct point.']
        guide['mechanisms']=[{'id':'motion-a','scene':'spatial','title':'Example','question':'Why?','anchor':bid,'refs':[bid],'stages':['A','B']}]
        chapter['motions']=[{'id':'motion-a','after':0}]
        html,report=build(data,records,guide,ROOT,source)
        self.assertFalse(report['errors'])
        self.assertLess(html.index('id="guide-motion-1-motion-a"'),html.index('Later distinct point.'))
        chapter['motions'][0]['after']=2
        self.assertTrue(any('motion after' in e for e in validate(data,records,guide,source)['errors']))

    def test_cli_default_requires_complete_input_and_keeps_existing_page(self):
        source,data,records,guide=test_paper_reader.PaperReader().fixture()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name,value in [('data',data),('records',records),('guide',guide)]:
                (root/(name+'.json')).write_text(json.dumps(value),encoding='utf-8')
            (root/'source.md').write_bytes(source.encode('utf-8'));output=root/'reader.html';output.write_bytes(b'previous reader')
            command=[sys.executable,'-B',str(ROOT/'skills/paper-close-read/scripts/build_html.py'),root/'data.json',root/'records.json',root/'guide.json',output,'--asset-root',root,'--source',root/'source.md']
            result=subprocess.run(list(map(str,command)),capture_output=True)
            self.assertNotEqual(result.returncode,0);self.assertEqual(output.read_bytes(),b'previous reader')
            result=subprocess.run(list(map(str,command))+['--profile','legacy'],capture_output=True)
            self.assertEqual(result.returncode,0);self.assertIn('兼容重建'.encode(),output.read_bytes())

    def test_working_tree_package_does_not_claim_head_is_payload_commit(self):
        spec=importlib.util.spec_from_file_location('package_reader_audit',ROOT/'scripts/package_reader.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);skill=root/'skills/paper-close-read';(skill/'scripts').mkdir(parents=True)
            (skill/'scripts/build_html.py').write_text("GENERATOR_VERSION='9.0.0'\n",encoding='utf-8')
            (skill/'SKILL.md').write_text('local candidate',encoding='utf-8')
            (root/'scripts').mkdir();(root/'scripts/standalone_skill_installer.py').write_text('installer',encoding='utf-8')
            docs=root/'docs/releases/paper-close-read-v9.0.0';docs.mkdir(parents=True)
            for name in ['INSTALL.zh-CN.md','CHANGELOG.zh-CN.md']:(docs/name).write_text('candidate',encoding='utf-8')
            with patch.object(module,'ROOT',root),patch.object(module.subprocess,'check_output',return_value=b'a'*40),patch.object(module.subprocess,'run',return_value=subprocess.CompletedProcess([],1,b'',b'missing')):
                result=module.package(root/'out')
                self.assertIsNone(result['source_commit']);self.assertEqual(result['source_state'],'working-tree')
                with self.assertRaisesRegex(ValueError,'differs from HEAD'):module.package(root/'release',require_committed=True)


if __name__=='__main__':unittest.main()
