"""Release/privacy failures must not be hidden by regenerating a SHA manifest."""
from pathlib import Path
import importlib.util,io,json,tempfile,unittest,zipfile

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('publication',ROOT/'scripts/verify_publication.py');p=importlib.util.module_from_spec(s);s.loader.exec_module(p)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def fixture(self):
        (self.root/'references').mkdir();(self.root/'assets').mkdir()
        contract=json.loads((ROOT/'references/design-contract.json').read_text(encoding='utf-8'))
        contract['runtime_sha256']={};contract['template_structure']={}
        system=json.loads((ROOT/'assets/template-system.json').read_text(encoding='utf-8'))
        (self.root/'references/design-contract.json').write_text(json.dumps(contract),encoding='utf-8')
        self.save(system);return system

    def save(self,system):(self.root/'assets/template-system.json').write_text(json.dumps(system),encoding='utf-8')

    def test_shipped_design_matches_contract(self):
        self.assertEqual(p.check_design(),[])
        contract=json.loads((ROOT/'references/design-contract.json').read_text(encoding='utf-8'))['system']
        self.assertEqual(set(contract['layouts']),{'L'+str(i) for i in range(1,24)})
        self.assertEqual(set(contract['palettes']),{'P'+str(i) for i in range(1,11)})
        self.assertEqual(set(contract['scenarios']),{'academic','coursework','progress'})
        self.assertEqual(set(contract['fill_styles']),{'light','solid'})
        self.assertEqual(contract['solid_typography']['title'],42)
        self.assertEqual(contract['compact_typography']['title'],36)
        self.assertEqual(contract['solid_typography']['content_side_margin'],32)
        self.assertEqual(contract['solid_typography']['chart_min'],17)
        self.assertEqual(contract['approved_compact']['reference_pages'],[2,4,5,8,9,10])

    def test_palette_or_layout_loss_is_design_drift(self):
        system=self.fixture();system['palettes']['P1']['primary']='#FF00FF';self.save(system)
        self.assertTrue(p.check_design(self.root))
        system['layouts'].pop('L23');self.save(system)
        self.assertIn('Design drift: template-system.layouts',p.check_design(self.root))

    def test_typography_evidence_and_rhythm_cannot_drift(self):
        system=self.fixture()
        for key,field,value in [('compact_typography','title',42),('solid_typography','chart_min',12),('composition_policy','figure_fit','cover'),('evidence_policy','required_formal_inventory','optional')]:
            original=system[key][field];system[key][field]=value;self.save(system)
            self.assertIn('Design drift: template-system.'+key,p.check_design(self.root))
            system[key][field]=original

    def test_machine_path_and_project_content_are_rejected(self):
        file=self.root/'README.md';file.write_text('C:/Users/example-person/private/research.txt',encoding='utf-8')
        self.assertTrue(p.scan_privacy(self.root)['findings'])
        file.write_text('\u9ed1\u9e82\u9879\u76ee',encoding='utf-8')
        self.assertTrue(any(x['kind']=='local_project' for x in p.scan_privacy(self.root)['findings']))

    def test_nested_workbook_metadata_and_secret_are_scanned(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr('docProps/core.xml','<core><creator>Private Person</creator></core>')
        file=self.root/'example.pptx'
        with zipfile.ZipFile(file,'w') as z:z.writestr('ppt/embeddings/data.xlsx',stream.getvalue())
        r=p.scan_privacy(self.root);self.assertTrue(any(x['kind']=='unreviewed_office_author' for x in r['findings']))
        (self.root/'token.txt').write_text('ghp_'+'x'*30,encoding='utf-8')
        self.assertTrue(any(x['kind']=='credential' for x in p.scan_privacy(self.root)['findings']))

    def test_third_party_license_and_public_sources_are_allowed(self):
        (self.root/'LICENSE.txt').write_text('Copyright Example Author; https://github.com/example/icons; MIT',encoding='utf-8')
        self.assertEqual(p.scan_privacy(self.root)['findings'],[])


if __name__=='__main__':unittest.main()
