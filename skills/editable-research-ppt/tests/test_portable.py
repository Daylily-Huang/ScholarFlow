"""Integration tests: package integrity, real data changes, relocation, and limits."""
import copy,hashlib,importlib.util,io,json,os,shutil,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
import xml.etree.ElementTree as E

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
g=module('generate');a=module('audit')

class PortableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        location=os.environ.get('PPT_TEST_TMP')
        if location:Path(location).mkdir(parents=True,exist_ok=True)
        cls.tmp=tempfile.TemporaryDirectory(prefix='research-ppt-',dir=location);cls.out=Path(cls.tmp.name)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def example(self,name='all-layouts'):return g.load(ROOT/'assets/examples'/(name+'.json'))
    def output(self,name,doc):
        p=self.out/(name+'.pptx');g.generate(doc,p,base_dir=ROOT/'assets/examples');self.assertTrue(a.audit(p)['ok'],a.audit(p));return p
    def test_all_examples(self):
        for path in sorted((ROOT/'assets/examples').glob('*.json')):
            doc=g.load(path);out=self.output('all-'+path.stem,doc)
            self.assertEqual(a.audit(out)['counts']['slides'],len(doc['slides']))
    def test_solid_preserves_data_and_text_in_all_palettes(self):
        seed=self.example();light=self.output('evidence-light',seed)
        with zipfile.ZipFile(light) as z:baseline={n:z.read(n) for n in z.namelist()}
        for i in range(1,7):
            doc=copy.deepcopy(seed);doc.update(fill_style='solid',palette='P'+str(i));out=self.output('solid-all-P'+str(i),doc)
            with zipfile.ZipFile(out) as z:
                for n,raw in baseline.items():
                    if n.startswith('ppt/embeddings/'):self.assertEqual(raw,z.read(n))
                    if n.startswith('ppt/slides/slide') and n.endswith('.xml'):
                        before=E.fromstring(raw);after=E.fromstring(z.read(n))
                        self.assertEqual(''.join(x.text or '' for x in before.findall('.//a:t',g.NS)),''.join(x.text or '' for x in after.findall('.//a:t',g.NS)))
                        self.assertEqual(len(before.findall('.//p:pic',g.NS)),len(after.findall('.//p:pic',g.NS)))
                # Dark chart title must contain real white text, not black fallback.
                panel=E.fromstring(z.read('ppt/slides/slide11.xml'))
                title=next(s for s in panel.findall('.//p:sp',g.NS) if '丰富度沿梯度变化'==''.join(t.text or '' for t in s.findall('.//a:t',g.NS)))
                prop=title.find('.//a:rPr',g.NS)
                self.assertEqual(prop.find('a:solidFill/a:srgbClr',g.NS).get('val'),'FFFFFF')
                self.assertLess(list(prop).index(prop.find('a:solidFill',g.NS)),list(prop).index(prop.find('a:latin',g.NS)))
    def test_fill_style_relocation_scenarios_and_invalid_values(self):
        relocated=self.out/'solid relocated';(relocated/'scripts').mkdir(parents=True)
        for n in ['generate.py','fill_styles.py','evidence_layouts.py']:shutil.copyfile(ROOT/'scripts'/n,relocated/'scripts'/n)
        shutil.copytree(ROOT/'assets',relocated/'assets')
        for scene in ['academic','coursework','progress']:
            doc=self.example();doc.update(fill_style='solid',scenario=scene);doc['slides']=[doc['slides'][4],doc['slides'][10]]
            source=self.out/(scene+'-input.json');source.write_text(json.dumps(doc),encoding='utf-8');out=self.out/(scene+'-relocated.pptx')
            subprocess.run([sys.executable,'-I','-S','-B',str(relocated/'scripts/generate.py'),'--input',str(source),'--output',str(out)],check=True,stdout=subprocess.PIPE,cwd=self.out)
            self.assertTrue(a.audit(out)['ok'])
        for change in ['invalid','mixed']:
            doc=self.example()
            if change=='invalid':doc['fill_style']='opaque-ish'
            else:doc['slides'][0]['fill_style']='solid'
            with self.assertRaises(ValueError):g.generate(doc,self.out/(change+'.pptx'))
    def test_legacy_examples_byte_identical(self):
        def contents(data):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                return {n:contents(archive.read(n)) if n.endswith('.xlsx') else archive.read(n) for n in archive.namelist()}
        for name in ['academic','coursework','progress','palettes','all-layouts']:
            out=self.output('legacy-'+name,self.example(name));expected=(ROOT/'examples'/(name+'.pptx')).read_bytes()
            self.assertEqual(contents(out.read_bytes()),contents(expected))
            if sys.platform=='win32':self.assertEqual(out.read_bytes(),expected)
    def test_reorder_duplicate_and_relocate(self):
        doc=self.example();doc['slides']=[copy.deepcopy(doc['slides'][10]),copy.deepcopy(doc['slides'][0]),copy.deepcopy(doc['slides'][10])]
        first=self.output('reordered',doc);self.assertEqual(a.audit(first)['counts']['charts'],9)
        second=self.output('reordered2',doc);self.assertEqual(first.read_bytes(),second.read_bytes())
        relocated=self.out/'a folder with spaces'/'skill'
        (relocated/'scripts').mkdir(parents=True);shutil.copyfile(ROOT/'scripts/generate.py',relocated/'scripts/generate.py');shutil.copytree(ROOT/'assets',relocated/'assets')
        inputfile=self.out/'relocated-input.json';inputfile.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8');output=self.out/'relocated.pptx'
        subprocess.run([sys.executable,'-I','-S',str(relocated/'scripts/generate.py'),'--input',str(inputfile),'--output',str(output)],check=True,stdout=subprocess.PIPE,cwd=self.out)
        self.assertEqual(first.read_bytes(),output.read_bytes())
    def test_new_data_and_text(self):
        doc=self.example();page=copy.deepcopy(doc['slides'][10]);doc['slides']=[page];page['title']='新材料验证';page['charts'][0]['series'][0]['values'][0]=77.125
        page['sources']=['PAGE_SOURCE_TEST'];page['charts'][0]['source']='CHART_SOURCE_TEST_741'
        page['charts'][3]['series'][0]['values'][0]=.4;page['charts'][3]['errors'][0]['lower'][0]=.2;page['charts'][3]['errors'][0]['upper'][0]=.6
        out=self.output('new-data',doc)
        with zipfile.ZipFile(out) as z:
            text=z.read('ppt/slides/slide1.xml').decode();self.assertIn('新材料验证',text)
            notes=z.read('ppt/notesSlides/notesSlide1.xml').decode();self.assertIn('PAGE_SOURCE_TEST',notes);self.assertIn('charts.0: CHART_SOURCE_TEST_741',notes)
            roots=[E.fromstring(z.read(n)) for n in z.namelist() if n.startswith('ppt/charts/chart') and n.endswith('.xml')]
            vals=[float(x.text) for root in roots for x in root.findall('.//c:numCache/c:pt/c:v',g.NS)]
            self.assertIn(77.125,vals)
            effects=roots[-1];plus=effects.find('.//c:errBars/c:plus/c:numLit/c:pt/c:v',g.NS);minus=effects.find('.//c:errBars/c:minus/c:numLit/c:pt/c:v',g.NS)
            self.assertAlmostEqual(float(plus.text),.2);self.assertAlmostEqual(float(minus.text),.2)
    def test_box_definition_and_intervals(self):
        doc=self.example();page=copy.deepcopy(doc['slides'][10]);doc['slides']=[page]
        page['charts'][1]['series'][0]['values']=[.2,.4,.6,.8,1.0]
        out=self.output('box',doc)
        with zipfile.ZipFile(out) as z:
            box=E.fromstring(z.read('ppt/charts/chart2.xml'));sers=box.findall('.//c:ser',g.NS)
            values=[float(s.find('c:val/c:numRef/c:numCache/c:pt/c:v',g.NS).text) for s in sers]
            self.assertEqual(values,[.4,.2,.2])
            self.assertAlmostEqual(float(sers[0].find('c:errBars/c:minus/c:numLit/c:pt/c:v',g.NS).text),.2)
            self.assertAlmostEqual(float(sers[2].find('c:errBars/c:plus/c:numLit/c:pt/c:v',g.NS).text),.2)
    def test_reject_clipped_and_invalid_uncertainty(self):
        doc=self.example();doc['slides']=[copy.deepcopy(doc['slides'][10])]
        for change in ['clipped','badinterval','nan','series']:
            bad=copy.deepcopy(doc);charts=bad['slides'][0]['charts']
            if change=='clipped':charts[0]['yMax']=1
            elif change=='badinterval':charts[2]['lower'][0]=9
            elif change=='nan':charts[0]['series'][0]['values'][0]=float('nan')
            else:charts[0]['series'].pop()
            with self.assertRaises(ValueError):g.generate(bad,self.out/(change+'.pptx'))
            self.assertFalse((self.out/(change+'.pptx')).exists())
    def test_protect_existing_output(self):
        target=self.out/'user.pptx';target.write_bytes(b'user-owned')
        with self.assertRaises(ValueError):g.generate(self.example(),target)
        self.assertEqual(target.read_bytes(),b'user-owned')
    def test_reject_missing_source_and_capacity(self):
        for change in ['source','length','topology','active']:
            doc=self.example()
            if change=='source':doc['slides'][0]['sources']=[]
            elif change=='length':doc['slides'][0]['title']='x'*50
            elif change=='topology':doc['slides'][0]['stages'].pop()
            else:doc['slides'][6]['active']=0
            with self.assertRaises(ValueError):g.generate(doc,self.out/(change+'.pptx'))
    def test_fixed_labels_and_no_external_paths(self):
        doc=self.example();page=copy.deepcopy(doc['slides'][3]);page['labels']={'样地 × 工作环节':'样品 × 工作环节'};doc['slides']=[page]
        out=self.output('labels',doc)
        with zipfile.ZipFile(out) as z:
            slide=z.read('ppt/slides/slide1.xml').decode();self.assertIn('样品 × 工作环节',slide)
            for name in z.namelist():
                if name.endswith(('.xml','.rels')):
                    raw=z.read(name).decode();self.assertNotIn('file://',raw);self.assertNotIn('Administrator',raw);self.assertNotIn('D:\\',raw)
    def test_adaptive_mode_and_strict_audit(self):
        doc=self.example();doc['demo']=False;doc['fill_style']='solid';doc['materials']={'papers':[]}
        # Customize icons, dynamic L7 active index, and L4 table values
        doc['slides'][0]['stages'][0]['icon']='dna'
        doc['slides'][0]['stages'][1]['icon']='pcr'
        doc['slides'][6]['active']=0
        doc['slides'][3]['matrix'][2][1]='193–202'
        out=self.output('adaptive-solid',doc)
        rep=a.audit(out,strict=True)
        self.assertTrue(rep['ok'],rep)
        self.assertEqual(rep['warning_count'],0,rep['warnings'])
        with zipfile.ZipFile(out) as z:
            # L5 (slide5), L7 (slide7), L9 (slide9), L14 (slide14) should use native editable cards, not stock bitmaps
            for sname in ['ppt/slides/slide5.xml','ppt/slides/slide7.xml','ppt/slides/slide9.xml','ppt/slides/slide14.xml']:
                r=E.fromstring(z.read(sname))
                self.assertEqual(len(r.findall('.//p:pic',g.NS)),0,sname)
            # L4 (slide4) table data cells must have uniform font size and no leftover #AF3D3D red fill
            s4=z.read('ppt/slides/slide4.xml').decode()
            self.assertNotIn('AF3D3D',s4)
            r4=E.fromstring(s4)
            tbl=r4.find('.//a:tbl',g.NS)
            data_sz={rp.get('sz') for tr in tbl.findall('a:tr',g.NS)[1:] for rp in tr.findall('.//a:rPr',g.NS) if rp.get('sz')}
            self.assertEqual(data_sz,{'1500'})
            # L10 (slide10) scatter chart must not keep hardcoded trendline unless requested
            c1=E.fromstring(z.read('ppt/charts/chart2.xml'))
            self.assertIsNone(c1.find('.//c:trendline',g.NS))

if __name__=='__main__':unittest.main(verbosity=2)
