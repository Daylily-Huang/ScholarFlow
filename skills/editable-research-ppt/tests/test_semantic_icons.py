"""Semantic fidelity of native fallback icons; user choices beat deduplication."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('styles',ROOT/'scripts/fill_styles.py');styles=importlib.util.module_from_spec(spec);spec.loader.exec_module(styles)


class SemanticIconTests(unittest.TestCase):
    def test_explicit_ecology_icons_are_preserved(self):
        for icon in ['camera','tree','leaf','calendar','database']:
            self.assertEqual(styles.infer_semantic_icon(icon,'来源于样点的观测'),icon)
            self.assertEqual(styles.infer_semantic_icon(icon,'异常冲突',{icon}),icon)
    def test_contextual_matching_is_case_insensitive(self):
        for hint,expected in [('红外相机记录','camera'),('CAMERA records','camera'),('植被调查','tree'),('叶绿素测量','leaf'),('统一时间窗','calendar'),('database archive','database')]:
            self.assertEqual(styles.infer_semantic_icon('',hint),expected)
    def test_source_and_individual_do_not_imply_a_map_pin(self):
        self.assertNotEqual(styles.infer_semantic_icon('','个体来源说明'),'location')
    def test_repeated_semantics_do_not_force_unrelated_icons(self):
        self.assertEqual(styles.infer_semantic_icon('','诊断与验证',{'check'}),'check')
        self.assertEqual(styles.infer_semantic_icon('','候选模型'),'workflow')
    def test_each_icon_has_bounded_native_geometry_and_unique_ids(self):
        for icon in ['camera','tree','leaf','calendar','database']:
            shapes,last=styles.build_vector_icon(100,icon,(10,20,40,40),'173D67')
            self.assertTrue(shapes);self.assertEqual(last,100+len(shapes))
            ids=[]
            for shape in shapes:
                ids.append(shape.find('p:nvSpPr/p:cNvPr',styles.NS).get('id'))
                x,y,w,h=styles.box(shape)
                self.assertGreaterEqual(x,10);self.assertGreaterEqual(y,20)
                self.assertLessEqual(x+w,50.001);self.assertLessEqual(y+h,60.001)
                self.assertFalse(shape.findall('.//p:pic',styles.NS))
            self.assertEqual(len(ids),len(set(ids)))


if __name__=='__main__':unittest.main()
