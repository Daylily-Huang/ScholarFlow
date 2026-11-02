"""Reading landmarks must not become invented source sections or move evidence."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/paper-close-read/scripts'))
from parse_mineru import parse_document
from reading_outline import outline_errors, navigation
from build_html import build
from validate_content import validate


def fixture():
    source = '# T\n\nA Writer.\n\n## Abstract\n\nThe question.\n\n## Main text\n\nA background.\n\nA comparison.\n\nA result.\n\n## Notes\n\nA note.\n'
    data = parse_document(source)
    records = []
    for sn, section in enumerate(data['sections']):
        for item in section['items']:
            records.append(dict(id=item['id'], zh='译文', note='具体解释', keys=['一个真实联系'], role='metadata' if sn in (0, 3) else 'body'))
    ids = [i['id'] for i in data['sections'][2]['items']]
    guide = {'format': 'legacy', 'question': 'Why?', 'answer': 'Because.', 'why': 'Context.', 'limits': ['Scope.'],
             'claims': [{'title': 'Claim', 'text': 'Answer.', 'refs': [ids[0]]}],
             'checks': [{'question': 'Why?', 'answer': 'Because.', 'refs': [ids[0]]}],
             'reading_outline': [{'start': ids[0], 'title': 'Background'}, {'start': ids[1], 'title': 'Comparison and result'}]}
    return source, data, records, guide


class ReadingOutline(unittest.TestCase):
    def test_landmarks_leave_source_order_and_annotation_ids_intact(self):
        source, data, records, guide = fixture(); before = copy.deepcopy(data)
        html, report = build(data, records, guide, ROOT, source)
        self.assertFalse(report['errors']); self.assertEqual(data, before)
        ids = [i['id'] for i in data['sections'][2]['items']]
        self.assertLess(html.index('id="f-read-'+ids[0]+'"'), html.index('id="'+ids[0]+'"'))
        self.assertLess(html.index('id="'+ids[0]+'"'), html.index('id="'+ids[1]+'"'))
        self.assertIn('data-ann-id="'+ids[0]+'-en"', html)
        self.assertIn('阅读分段 · 整理者添加', html)

    def test_metadata_is_grouped_separately_without_removing_it(self):
        _, data, records, guide = fixture()
        nav = navigation(data, records, guide)
        self.assertLess(nav.index('>Abstract<'), nav.index('>题名与作者<'))
        self.assertIn('出版信息与附录', nav)
        self.assertIn('data-toc-depth="1"', nav)
        self.assertIn('02.1', nav)

    def test_unknown_duplicate_reversed_and_metadata_starts_are_rejected(self):
        _, data, records, guide = fixture()
        for entries in [[{'start': 'missing', 'title': 'X'}], guide['reading_outline'] * 2,
                        list(reversed(guide['reading_outline'])),
                        [{'start': records[0]['id'], 'title': 'Metadata as body'}]]:
            g = dict(guide, reading_outline=entries)
            self.assertTrue(outline_errors(data, records, g))

    def test_bad_outline_shapes_report_input_errors(self):
        _, data, records, guide = fixture()
        for entries in [None, {}, [None], [{'start': [], 'title': 'x'}], [{'start': records[1]['id'], 'title': ''}]]:
            self.assertTrue(outline_errors(data, records, dict(guide, reading_outline=entries)))

    def test_source_heading_levels_are_preserved_in_navigation(self):
        _, data, records, guide = fixture()
        data['sections'][2]['level'] = 3
        nav = navigation(data, records, guide)
        self.assertIn('01.01', nav)
        self.assertIn('data-toc-depth="2"', nav)

    def test_legacy_input_needs_no_invented_landmark(self):
        source, data, records, guide = fixture(); guide.pop('reading_outline')
        html, report = build(data, records, guide, ROOT, source)
        self.assertFalse(report['errors']); self.assertNotIn('class="reading-landmark"', html)

    def test_labels_are_escaped_and_source_section_targets_still_work(self):
        source, data, records, guide = fixture()
        guide['reading_outline'][0]['title'] = '<script>unsafe</script>'
        html, report = build(data, records, guide, ROOT, source)
        self.assertFalse(report['errors']); self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;', html)
        self.assertIn('href="#f-02"', html)
        self.assertNotIn('<h3><script>', html)


if __name__ == '__main__':
    unittest.main()
