"""Failure paths must keep an existing reader and report actionable input errors."""
import importlib.util,json,os,subprocess,sys,tempfile,unittest,copy
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];SCRIPTS=ROOT/'skills/paper-close-read/scripts'
sys.path.insert(0,str(SCRIPTS))
from build_html import atomic_write
from validate_content import validate

class ReaderBuildReliability(unittest.TestCase):
 def test_atomic_write_is_utf8_and_does_not_apply_windows_newline_conversion(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'reader.html';atomic_write(p,'中文\nnext\n');self.assertEqual(p.read_bytes(),'中文\nnext\n'.encode('utf-8'));self.assertEqual(len(list(Path(tmp).iterdir())),1)
 def test_failed_replacement_preserves_previous_reader_and_cleans_owned_temporary(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'reader.html';p.write_bytes(b'previous valid reader')
   with patch('build_html.os.replace',side_effect=OSError('disk or sharing error')):
    with self.assertRaises(OSError):atomic_write(p,'replacement')
   self.assertEqual(p.read_bytes(),b'previous valid reader');self.assertEqual([x.name for x in Path(tmp).iterdir()],['reader.html'])
 def test_invalid_envelopes_return_errors_instead_of_attribute_tracebacks(self):
  for data,records,guide in [([],[],{}),({},'wrong',{}),({},[],[]),({'front':{'title':'T'},'source':{},'sections':[{'name':'x','items':['not a block']}]},[],{})]:
   with self.subTest(data=data,records=records,guide=guide):self.assertTrue(validate(data,records,guide)['errors'])
 def test_malformed_json_cli_does_not_replace_an_existing_output(self):
  with tempfile.TemporaryDirectory() as tmp:
   d=Path(tmp);source=d/'bad.json';source.write_text('{invalid',encoding='utf-8');out=d/'reader.html';out.write_bytes(b'previous')
   result=subprocess.run([sys.executable,str(SCRIPTS/'build_html.py'),str(source),str(source),str(source),str(out),'--asset-root',str(d)],capture_output=True,text=True,encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'})
   self.assertEqual(result.returncode,2);self.assertIn('bad.json',result.stderr);self.assertIn('JSON',result.stderr);self.assertNotIn('Traceback',result.stderr);self.assertEqual(out.read_bytes(),b'previous')
 def test_nested_authoring_mistakes_report_the_input_path(self):
  d=ROOT/'examples/paper-close-read/thomsen/reading-data'
  values=[json.loads((d/n).read_text(encoding='utf-8-sig')) for n in ['fulltext.json','translations.json','guide.json']]
  mutations=[(2,['story','overview','research_map'],{}),(2,['story','walkthrough',0,'table'],[]),(2,['story','walkthrough',0,'motions'],['bad']),
   (2,['mechanisms',0,'visual'],[]),(2,['mechanisms',0,'refs'],'bad'),(1,[0,'terms'],[42]),(0,['sections',0,'items',0,'source','inline_runs'],[{'styles':42}])]
  for index,path,value in mutations:
   candidate=copy.deepcopy(values);at=candidate[index]
   for key in path[:-1]:at=at[key]
   at[path[-1]]=value
   with self.subTest(path=path):
    report=validate(*candidate);self.assertTrue(report['errors']);self.assertIn('must be',str(report['errors']))

class ReaderInstallerReliability(unittest.TestCase):
 def test_copy_failure_keeps_existing_skill_and_no_replace_refuses_changes(self):
  spec=importlib.util.spec_from_file_location('reader_installer',ROOT/'scripts/install_reader.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
  with tempfile.TemporaryDirectory() as tmp:
   dest=Path(tmp)/'paper-close-read';dest.mkdir();(dest/'local.txt').write_text('user changes',encoding='utf-8')
   with self.assertRaises(ValueError):mod.install(tmp)
   with patch.object(mod.shutil,'copytree',side_effect=OSError('interrupted copy')):
    with self.assertRaises(OSError):mod.install(tmp,True)
   self.assertEqual((dest/'local.txt').read_text(encoding='utf-8'),'user changes')
 def test_verified_install_is_repeatable_and_replace_only_changes_named_skill(self):
  spec=importlib.util.spec_from_file_location('reader_installer',ROOT/'scripts/install_reader.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
  with tempfile.TemporaryDirectory() as tmp:
   sibling=Path(tmp)/'another-skill';sibling.mkdir();(sibling/'keep').write_text('keep')
   dest=mod.install(tmp);self.assertEqual(mod.digest(dest),mod.digest(SCRIPTS.parent));self.assertEqual(mod.install(tmp),dest)
   (dest/'SKILL.md').write_text('old');mod.install(tmp,True);self.assertEqual(mod.digest(dest),mod.digest(SCRIPTS.parent));self.assertEqual((sibling/'keep').read_text(),'keep')
 def test_failed_final_directory_switch_restores_previous_installation(self):
  spec=importlib.util.spec_from_file_location('reader_installer',ROOT/'scripts/install_reader.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
  with tempfile.TemporaryDirectory() as tmp:
   dest=Path(tmp)/'paper-close-read';dest.mkdir();(dest/'custom.txt').write_text('previous')
   replace=mod.os.replace
   def interrupted(source,target):
    if Path(source).name=='new':raise OSError('simulated directory switch failure')
    return replace(source,target)
   with patch.object(mod.os,'replace',side_effect=interrupted):
    with self.assertRaises(OSError):mod.install(tmp,True)
   self.assertEqual((dest/'custom.txt').read_text(),'previous');self.assertEqual(len(list(Path(tmp).iterdir())),1)

if __name__=='__main__':unittest.main()
