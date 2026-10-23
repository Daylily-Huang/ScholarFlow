"""Preserved upgrades and error recovery, using isolated manifest fixtures."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('install_local',ROOT/'scripts/install_local.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ.get('PPT_TEST_TMP'));self.root=Path(self.tmp.name)
        self.one=self.package('one');self.two=self.package('two');self.target=self.root/'skills/editable-research-ppt'
    def tearDown(self):self.tmp.cleanup()
    def package(self,label):
        root=self.root/label;root.mkdir()
        data={'SKILL.md':'---\nname: editable-research-ppt\ndescription: fixture\n---\n'+label,
              'assets/template-system.json':json.dumps({'version':label}),
              'references/v'+label+'-hashes.json':json.dumps({'version':label,'sha256':{}}),
              'references/approved-standard.json':json.dumps({'design_files':{},'approved_examples':{}}),
              'scripts/payload.py':label}
        for name,text in data.items():
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
        manifest=''.join(hashlib.sha256((root/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in sorted(data))
        (root/'SHA256SUMS.txt').write_text(manifest,encoding='utf-8');return root
    def test_first_install_and_dry_run(self):
        result=m.install(self.one,self.target,dry_run=True);self.assertTrue(result['dry_run']);self.assertFalse(self.target.exists())
        m.install(self.one,self.target);self.assertTrue(m.verifier().verify(self.target)['ok'])
        self.assertEqual((self.target/'SKILL.md').read_bytes(),(self.one/'SKILL.md').read_bytes())
    def test_upgrade_and_rollback_preserve_both_versions(self):
        m.install(self.one,self.target);backup=self.root/'backup-one'
        result=m.install(self.two,self.target,replace=True,backup=backup)
        self.assertEqual(Path(result['backup']), (backup/'editable-research-ppt').resolve())
        self.assertEqual((self.target/'scripts/payload.py').read_text(),'two')
        m.install(backup/'editable-research-ppt',self.target,replace=True,backup=self.root/'backup-two')
        self.assertEqual((self.target/'scripts/payload.py').read_text(),'one')
        self.assertEqual((self.root/'backup-two/editable-research-ppt/scripts/payload.py').read_text(),'two')
    def test_local_edits_block_default_and_survive_explicit_backup(self):
        m.install(self.one,self.target);(self.target/'user-notes.txt').write_text('private custom note')
        with self.assertRaisesRegex(ValueError,'Installed files differ'):
            m.install(self.two,self.target,replace=True,backup=self.root/'backup')
        self.assertTrue((self.target/'user-notes.txt').exists());self.assertFalse((self.root/'backup').exists())
        m.install(self.two,self.target,replace=True,backup=self.root/'backup',allow_local_changes=True)
        self.assertEqual((self.root/'backup/editable-research-ppt/user-notes.txt').read_text(),'private custom note')
        self.assertFalse((self.target/'user-notes.txt').exists())
    def test_copy_failure_restores_original_and_keeps_partial_files(self):
        m.install(self.one,self.target)
        def fail(source,target,checker):
            (target/'partial.txt').write_text('partial');raise OSError('simulated write failure')
        with mock.patch.object(m,'copy_package',side_effect=fail),self.assertRaisesRegex(RuntimeError,'previous folder restored'):
            m.install(self.two,self.target,replace=True,backup=self.root/'failed-backup')
        self.assertTrue(m.verifier().verify(self.target)['ok'])
        self.assertEqual((self.target/'scripts/payload.py').read_text(),'one')
        self.assertTrue((self.root/'failed-backup/failed-install/partial.txt').is_file())
    def test_invalid_source_existing_backup_and_nested_paths_leave_target_intact(self):
        m.install(self.one,self.target)
        (self.two/'scripts/payload.py').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'Source release integrity'):
            m.install(self.two,self.target,replace=True,backup=self.root/'backup')
        with self.assertRaises(FileExistsError):m.install(self.one,self.target)
        with self.assertRaises(ValueError):m.install(self.one,self.one/'editable-research-ppt')
        self.assertTrue(m.verifier().verify(self.target)['ok'])
    def test_backup_destination_is_never_reused(self):
        m.install(self.one,self.target);p=self.root/'existing-backup';p.mkdir();(p/'keep.txt').write_text('keep')
        with self.assertRaises(FileExistsError):m.install(self.two,self.target,replace=True,backup=p)
        self.assertEqual((p/'keep.txt').read_text(),'keep');self.assertTrue(m.verifier().verify(self.target)['ok'])


if __name__=='__main__':unittest.main()
