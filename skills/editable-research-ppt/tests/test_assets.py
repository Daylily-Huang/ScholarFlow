"""Offline library integrity and native insertion behavior (stdlib only)."""
from pathlib import Path
import copy,hashlib,importlib.util,json,tempfile,unittest,zipfile
import xml.etree.ElementTree as E

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    s=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
a=module('assets');compiler=module('compile_svg_asset')

class AssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.out=Path(self.tmp.name)/'result.pptx'
        self.base=ROOT/'examples/assets/ecology-showcase-base.pptx'
        self.config={'placements':[{'slide':1,'asset':'lucide/camera','box':[80,250,120,120]}]}

    def test_all_originals_caches_and_licenses_are_bound(self):
        doc=a.load_catalog()
        for item in doc['assets']:
            self.assertEqual(hashlib.sha256((a.LIBRARY/item['path']).read_bytes()).hexdigest(),item['sha256'])
            for name in [item['license_file'],*item.get('additional_license_files',[])]:self.assertTrue(a.library_file(a.LIBRARY,name).is_file())
            if item['native'].get('path'):
                root=a.checked_native(item,a.LIBRARY)
                self.assertEqual(len(root.findall('p:sp',a.NS)),item['native']['native_parts'])
                self.assertEqual(item['native']['edit_probe'],'passed')

    def test_theme_is_optional_and_semantics_are_truthful(self):
        themed=a.search(theme='ecology-field-genetics')
        self.assertGreater(len(themed),80)
        self.assertGreater(len(a.search()),len(themed))
        deer=a.search('emoji_u1f98c')[0];self.assertIn('非物种鉴定依据',deer['label_zh'])
        self.assertTrue(a.search('相机',theme='camera-monitoring',native_only=True))
        self.assertFalse(a.search('zzzz_nonexistent_term'))
        with self.assertRaises(ValueError):a.search(theme='nonexistent')

    def test_native_insertion_has_unique_ids_notes_and_scaled_strokes(self):
        source_hash=hashlib.sha256(self.base.read_bytes()).hexdigest()
        self.config['placements'].append({'slide':1,'asset':'lucide/camera','box':[240,250,240,240]})
        report=a.insert(self.base,self.out,self.config)
        self.assertEqual(len(report['placements']),2)
        with zipfile.ZipFile(self.out) as z:
            root=E.fromstring(z.read('ppt/slides/slide1.xml'))
            ids=[n.get('id') for n in root.findall('.//p:cNvPr',a.NS)]
            self.assertEqual(len(ids),len(set(ids)))
            groups=root.findall('p:cSld/p:spTree/p:grpSp',a.NS)
            self.assertEqual(len(groups),2)
            for group in groups:self.assertFalse(group.findall('.//p:pic',a.NS))
            small=int(groups[0].find('.//a:ln',a.NS).get('w'));big=int(groups[1].find('.//a:ln',a.NS).get('w'))
            self.assertAlmostEqual(big/small,2,places=3)
            self.assertIn(b'lucide',z.read('ppt/notesSlides/notesSlide1.xml').lower())
        self.assertEqual(hashlib.sha256(self.base.read_bytes()).hexdigest(),source_hash)
        with self.assertRaises(FileExistsError):a.insert(self.base,self.out,self.config)

    def test_reserved_slot_replacement_and_original_colors(self):
        cfg={'placements':[{'slide':1,'asset':'noto/emoji_u1f333','target':'hero-0','name':'forest-asset'}]}
        a.insert(self.base,self.out,cfg)
        with zipfile.ZipFile(self.out) as z:
            root=E.fromstring(z.read('ppt/slides/slide1.xml'));names=[n.get('name') for n in root.findall('.//p:cNvPr',a.NS)]
            self.assertNotIn('hero-0',names);self.assertIn('forest-asset',names)
            group=next(g for g in root.findall('.//p:grpSp',a.NS) if g.find('p:nvGrpSpPr/p:cNvPr',a.NS).get('name')=='forest-asset')
            self.assertGreater(len({n.get('val') for n in group.findall('.//a:srgbClr',a.NS)}),2)

    def test_unsupported_svg_is_not_silently_rasterized(self):
        item=next(x for x in a.load_catalog()['assets'] if not x['native'].get('path'))
        self.config['placements'][0]['asset']=item['id']
        with self.assertRaises(ValueError):a.insert(self.base,self.out,self.config)
        self.assertFalse(self.out.exists())

    def test_invalid_placements_leave_no_partial_output(self):
        cases=[{'slide':0},{'slide':True},{'box':[-1,0,10,10]},{'box':[1270,0,40,40]},{'box':[0,0,float('nan'),40]},{'target':'missing','box':None},{'color':'oops'},{'asset':'missing'}]
        for delta in cases:
            cfg=copy.deepcopy(self.config);cfg['placements'][0].update(delta)
            with self.assertRaises((ValueError,KeyError)):a.insert(self.base,self.out,cfg)
            self.assertFalse(self.out.exists())

    def test_path_traversal_and_changed_cache_are_rejected(self):
        with self.assertRaises(ValueError):a.library_file(a.LIBRARY,'../../SKILL.md')
        item=copy.deepcopy(next(x for x in a.load_catalog()['assets'] if x['id']=='lucide/camera'))
        item['native']['sha256']='0'*64
        with self.assertRaises(ValueError):a.checked_native(item,a.LIBRARY)

    def test_active_svg_and_unsupported_features_rejected_before_parser(self):
        for body in ['<script>alert(1)</script>','<image href="https://example.org/x.png"/>','<path onload="x()" d="M0 0L1 1"/>','<linearGradient/>']:
            data=('<svg xmlns="http://www.w3.org/2000/svg">'+body+'</svg>').encode()
            with self.assertRaises(ValueError):compiler.precheck(data)
        with self.assertRaises(ValueError):compiler.precheck(b'<!DOCTYPE svg [<!ENTITY x "a">]><svg/>')

if __name__=='__main__':unittest.main()
