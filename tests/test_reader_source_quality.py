"""Source preparation gates; no heuristic is allowed to rewrite research text."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/paper-close-read/scripts'))
from parse_mineru import parse_document
from source_quality import quality_errors, source_risks
from build_html import build
from validate_content import validate


def fixture():
    source = '# Study\n\nInstitutional trust shapes behaviour.\n'
    data = parse_document(source)
    block = data['sections'][0]['items'][0]
    bid = block['id']
    records = [{'id': bid, 'zh': '制度信任影响行为。', 'note': '讨论人怎样依据制度作决定。',
                'keys': ['信任影响后续选择。'], 'terms': [{'en': 'trust', 'zh': '制度信任'}]}]
    guide = {'format': 'legacy', 'question': 'Why?', 'answer': 'An explanation.', 'why': 'A question.',
             'claims': [{'title': 'Claim', 'text': 'Context.', 'refs': [bid]}],
             'limits': ['Teaching fixture.'], 'checks': [{'question': 'Why?', 'answer': 'Context.', 'refs': [bid]}],
             'terminology': [{'id': 'institutional-trust', 'forms': ['trust'], 'identity': 'Confidence in institutions',
                              'preferred_zh': '制度信任', 'aliases': ['机构信任'],
                              'evidence': ['source-review.md#term-definition'], 'refs': [bid]}]}
    data['source_review'] = {aspect: {'status': 'checked', 'evidence': ['source-review.md#' + aspect],
                                    'note': 'Specific fixture scope, not a real paper review.'}
                             for aspect in ('structure', 'terminology', 'citations')}
    data['source_review'].update(decisions=[], issues=[])
    return source, data, records, guide


class SourceQuality(unittest.TestCase):
    def test_legacy_compatible_but_not_strictly_certified(self):
        source, data, records, guide = fixture(); data.pop('source_review')
        self.assertFalse(validate(data, records, guide, source)['errors'])
        self.assertTrue(validate(data, records, guide, source, require_source_review=True)['errors'])

    def test_strict_build_flag_is_connected_and_preserves_source(self):
        source, data, records, guide = fixture(); before = copy.deepcopy(data)
        html, report = build(data, records, guide, ROOT, source, require_source_review=True)
        self.assertFalse(report['errors']); self.assertIn('Institutional trust', html)
        self.assertEqual(data, before)
        data['source_review']['structure']['status'] = 'pending'
        with self.assertRaisesRegex(ValueError, 'Source review pending'):
            build(data, records, guide, ROOT, source, require_source_review=True)

    def test_synonyms_are_accepted_and_wrong_sense_is_rejected(self):
        _, data, records, guide = fixture()
        records[0]['terms'][0]['zh'] = '机构信任'
        self.assertFalse(quality_errors(data, records, guide, True)[0])
        records[0]['terms'][0]['zh'] = '信托'
        self.assertTrue(any('conflicts' in e for e in quality_errors(data, records, guide, True)[0]))

    def test_homonyms_require_explicit_sense(self):
        _, data, records, guide = fixture()
        other = copy.deepcopy(guide['terminology'][0])
        other.update(id='legal-trust', identity='A legal property arrangement', preferred_zh='信托', aliases=[])
        guide['terminology'].append(other)
        self.assertTrue(any('Ambiguous' in e for e in quality_errors(data, records, guide)[0]))
        records[0]['terms'][0]['term_id'] = 'institutional-trust'
        self.assertFalse(quality_errors(data, records, guide)[0])
        records[0]['terms'][0]['term_id'] = 'unknown'
        self.assertTrue(quality_errors(data, records, guide)[0])

    def test_word_number_and_broken_words_are_candidates_not_repairs(self):
        data = parse_document('# T\n\nInteractions6 affect impor- tant outcomes.\n')
        before = copy.deepcopy(data)
        self.assertEqual({r['kind'] for r in source_risks(data)}, {'word-number', 'broken-word'})
        self.assertEqual(before, data)

    def test_legitimate_names_and_numbers_are_never_rewritten(self):
        data = parse_document('# T\n\nIL6 and p53 use R 4.0.398 with low-risk groups and x^2.\n')
        before = copy.deepcopy(data); risks = source_risks(data)
        self.assertTrue(any(r['excerpt'] == 'IL6' for r in risks))
        self.assertEqual(before, data)
        self.assertNotIn('broken-word', [r['kind'] for r in risks])

    def test_paragraph_continuation_candidate_and_complete_sentence(self):
        data = parse_document('# T\n\nA long unresolved\n\ncontinuation of an argument.\n')
        self.assertIn('paragraph-boundary', [r['kind'] for r in source_risks(data)])
        data = parse_document('# T\n\nA complete sentence.\n\na lower-case styled example.\n')
        self.assertNotIn('paragraph-boundary', [r['kind'] for r in source_risks(data)])

    def test_superscript_with_target_is_not_word_number_glue(self):
        data = parse_document('# T\n\nInteractions6 matter.\n\n## References\n\n6. A source.\n')
        block = data['sections'][0]['items'][0]; ref = data['sections'][1]['items'][0]
        block['source']['inline_runs'] = [{'text': 'Interactions'}, {'text': '6', 'styles': ['sup'], 'target': ref['id']}, {'text': ' matter.'}]
        self.assertFalse(source_risks(data))
        block['source']['inline_runs'][1].pop('target')
        self.assertEqual(len(source_risks(data)), 1)

    def test_all_risks_need_evidence_based_dispositions(self):
        _, data, records, guide = fixture()
        data['sections'][0]['items'][0]['raw'] = 'Interactions6 matter.'
        risks = source_risks(data)
        self.assertTrue(any('Unreviewed' in e for e in quality_errors(data, records, guide, True)[0]))
        data['source_review']['decisions'] = [{'risk_id': risks[0]['id'], 'resolution': 'Confirmed reference 6 in PDF.', 'evidence': ['PDF p. 1']}]
        self.assertFalse(quality_errors(data, records, guide, True)[0])
        data['source_review']['decisions'][0]['risk_id'] = 'stale-risk'
        self.assertTrue(quality_errors(data, records, guide, True)[0])

    def test_human_found_issues_cannot_hide_behind_clean_heuristics(self):
        _, data, records, guide = fixture(); bid = records[0]['id']
        self.assertFalse(source_risks(data))
        issue = {'id': 'missing-clause', 'aspect': 'structure', 'refs': [bid],
                 'description': 'An omitted clause found on original page.', 'status': 'open', 'evidence': ['PDF p. 2']}
        data['source_review']['issues'] = [issue]
        self.assertTrue(any('still open' in e for e in quality_errors(data, records, guide, True)[0]))
        issue['status'] = 'resolved'
        self.assertTrue(any('resolution' in e for e in quality_errors(data, records, guide, True)[0]))
        issue['resolution'] = 'Restored in normalized transcript; original extraction retained.'
        self.assertFalse(quality_errors(data, records, guide, True)[0])

    def test_not_applicable_is_allowed_with_scope_and_evidence(self):
        _, data, records, guide = fixture(); guide.pop('terminology'); records[0]['terms'] = []
        self.assertTrue(quality_errors(data, records, guide, True)[0])
        data['source_review']['terminology']['status'] = 'not_applicable'
        self.assertFalse(quality_errors(data, records, guide, True)[0])

    def test_malformed_review_metadata_reports_errors_not_exceptions(self):
        mutations = [lambda d, r, g: g.update(terminology=[None]),
                     lambda d, r, g: d.update(source_review=[]),
                     lambda d, r, g: d['source_review'].update(structure={'status': [], 'note': 'x', 'evidence': ['p1']}),
                     lambda d, r, g: d['source_review'].update(decisions=[{'risk_id': [], 'resolution': 'x', 'evidence': ['p1']}]),
                     lambda d, r, g: r[0]['terms'][0].update(term_id=[])]
        for mutate in mutations:
            _, data, records, guide = fixture(); mutate(data, records, guide)
            self.assertTrue(quality_errors(data, records, guide, True)[0])


if __name__ == '__main__':
    unittest.main()
