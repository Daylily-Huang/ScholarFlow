"""Declarative new-topic drawings, explanation coverage and legacy compatibility."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/paper-close-read/scripts'))
from process_scene import validate_process, validate_visual_plan
from build_html import build


def drawing():
    return {'description': 'Teaching object crosses a recording boundary; not fitted data.',
            'elements': [{'id': 'animal', 'type': 'circle', 'meaning': 'same individual',
                          'props': {'x': 100, 'y': 180, 'r': 10, 'fill': '#568ba1'},
                          'frames': [{'at': 0.5, 'x': 300}, {'at': 1, 'x': 600}]}]}


class ProcessScenes(unittest.TestCase):
    def test_new_subject_uses_data_not_new_scene_code(self):
        self.assertEqual(validate_process(drawing()), [])
        d = drawing(); d['elements'][0]['meaning'] = 'moving historical information'
        d['elements'][0]['type'] = 'rect'; d['elements'][0]['props'].update(w=20, h=30)
        self.assertEqual(validate_process(d), [])

    def test_text_and_opacity_reveal_is_not_a_process(self):
        d = drawing(); d['elements'][0]['frames'] = [{'at': 1, 'opacity': 0.5}]
        self.assertTrue(validate_process(d))
        d['elements'][0].update(type='text', props={'x': 100, 'y': 80, 'text': 'A'}, frames=[{'at': 1, 'text': 'B'}])
        self.assertTrue(validate_process(d))

    def test_unsafe_unknown_and_nonfinite_inputs_rejected(self):
        mutations = [('x', float('nan')), ('x', float('inf')), ('x', True), ('fill', 'url(https://x)'),
                     ('fill', '#fff;script'), ('opacity', 2), ('font_size', 0), ('onload', 'execute()')]
        for key, value in mutations:
            d = drawing(); d['elements'][0]['props'][key] = value
            with self.subTest(key=key, value=value): self.assertTrue(validate_process(d))
        d = drawing(); d['elements'][0]['script'] = 'alert(1)'
        self.assertTrue(validate_process(d))

    def test_invalid_envelopes_are_actionable_errors(self):
        for value in [None, [], {}, {'description': 'x', 'elements': [None]},
                      {'description': 'x', 'elements': [{'type': {}, 'id': []}]}]:
            with self.subTest(value=value): self.assertTrue(validate_process(value))

    def test_frames_are_ordered_and_polyline_interpolation_is_shape_safe(self):
        d = drawing(); d['elements'][0]['frames'] = [{'at': 0.5, 'x': 200}, {'at': 0.5, 'x': 400}]
        self.assertTrue(validate_process(d))
        d['elements'][0].update(type='polyline', props={'points': [[0, 0], [100, 100]]},
                                frames=[{'at': 1, 'points': [[0, 0], [50, 50], [100, 100]]}])
        self.assertTrue(validate_process(d))

    def test_strict_plan_links_actual_inline_scene_and_source(self):
        g = {'mechanisms': [{'id': 'motion-new', 'scene': 'process'}],
             'story': {'walkthrough': [{'motions': [{'id': 'motion-new'}]}]},
             'visual_plan': [{'id': 'vp-1', 'question': 'Which change matters?', 'refs': ['block'],
                              'mode': 'motion', 'kind': 'mechanism', 'mechanism': 'motion-new',
                              'reason': 'Need to see a crossing', 'observe': 'Position and recording state'}]}
        self.assertEqual(validate_visual_plan(g, {'block'}, True), [])
        for mutate in [lambda c: c['story']['walkthrough'].clear(),
                       lambda c: c['visual_plan'][0].update(refs=['absent']),
                       lambda c: c['mechanisms'][0].update(scene='argument_map'),
                       lambda c: c['visual_plan'].append(copy.deepcopy(c['visual_plan'][0]))]:
            c = copy.deepcopy(g); mutate(c); self.assertTrue(validate_visual_plan(c, {'block'}, True))
        c = copy.deepcopy(g); c['mechanisms'] = [{}]
        self.assertTrue(validate_visual_plan(c, {'block'}, True))

    def test_static_or_text_explanation_does_not_force_animations(self):
        g = {'visual_plan': [{'id': 'vp', 'question': 'A short transition?', 'refs': ['b'],
                             'mode': 'text', 'reason': 'A sentence is sufficient', 'observe': 'The actual transition'}]}
        self.assertEqual(validate_visual_plan(g, {'b'}, True), [])
        self.assertEqual(validate_visual_plan({}, {'b'}, False), [])
        self.assertTrue(validate_visual_plan({}, {'b'}, True))

    def test_full_build_keeps_legacy_and_supports_new_topic(self):
        r = ROOT / 'examples/paper-close-read/hardy1908/reading-data'
        values = [json.loads((r / n).read_text(encoding='utf-8-sig')) for n in ['fulltext.json', 'translations.json', 'guide.json']]
        source = (r / 'source.md').read_text(encoding='utf-8-sig')
        legacy, _ = build(*values, r, source)
        self.assertIn('reader-config', legacy)
        with self.assertRaisesRegex(ValueError, 'visual_plan'):
            build(*values, r, source, require_visual_plan=True)
        data, records, guide = copy.deepcopy(values)
        ref = next(i['id'] for s in data['sections'] for i in s['items'] if i['t'] == 'p')
        guide['mechanisms'] = [{'id': 'motion-new', 'scene': 'process', 'title': 'New topic', 'question': 'Why move?',
                                'anchor': ref, 'refs': [ref], 'stages': ['Before', 'After'], 'visual': drawing()}]
        for c in guide['story']['walkthrough']: c['motions'] = []
        guide['story']['walkthrough'][0]['motions'] = [{'id': 'motion-new'}]
        guide['visual_plan'] = [{'id': 'vp', 'question': 'Why move?', 'mode': 'motion', 'kind': 'mechanism',
                                'mechanism': 'motion-new', 'refs': [ref], 'reason': 'Position matters', 'observe': 'A crossing'}]
        html, report = build(data, records, guide, r, source, require_visual_plan=True)
        self.assertFalse(report['errors'])
        self.assertEqual(html.count('data-mechanism='), 2)  # one definition, two independent players
        self.assertIn('process:process_scene', html)


if __name__ == '__main__': unittest.main()
