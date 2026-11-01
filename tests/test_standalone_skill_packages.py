"""Standalone distribution must preserve installed work and reject corrupt bundles."""
import hashlib
import importlib.util
import json
import io
import urllib.error
import urllib.parse
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('standalone_installer', ROOT / 'scripts/standalone_skill_installer.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
publish_spec = importlib.util.spec_from_file_location('package_publisher', ROOT / 'scripts/publish_skill_packages.py')
publisher = importlib.util.module_from_spec(publish_spec)
publish_spec.loader.exec_module(publisher)


class StandaloneInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.target = self.root / 'bundle', self.root / 'skills'
        self.source.mkdir()
        self.target.mkdir()
        self.fixture()

    def fixture(self, value='new', roots=('example-skill',)):
        files = {}
        for name in roots:
            p = self.source / name / 'data.txt'
            p.parent.mkdir(exist_ok=True)
            p.write_text(value, encoding='utf-8')
            files[name + '/data.txt'] = hashlib.sha256(p.read_bytes()).hexdigest()
        (self.source / 'manifest.json').write_text(json.dumps({'component': 'example-skill', 'minimum_python': [3, 9],
                                                             'install_roots': list(roots), 'files': files}), encoding='utf-8')

    def test_install_idempotence_and_other_skill(self):
        other = self.target / 'other'
        other.mkdir()
        (other / 'keep').write_text('keep', encoding='utf-8')
        self.assertEqual(installer.install(self.source, self.target)['action'], 'installed')
        self.assertEqual(installer.install(self.source, self.target)['action'], 'already-current')
        self.assertEqual((other / 'keep').read_text(encoding='utf-8'), 'keep')

    def test_corrupt_bundle_does_not_write_target(self):
        (self.source / 'example-skill/data.txt').write_text('corrupt', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            installer.install(self.source, self.target)
        self.assertFalse((self.target / 'example-skill').exists())

    def test_different_existing_files_require_backup(self):
        installer.install(self.source, self.target)
        self.fixture('upgrade')
        for options in ({}, {'replace': True}):
            with self.assertRaisesRegex(ValueError, 'Existing files differ'):
                installer.install(self.source, self.target, **options)
            self.assertEqual((self.target / 'example-skill/data.txt').read_text(encoding='utf-8'), 'new')

    def test_upgrade_preserves_custom_files_and_shared_engine(self):
        self.fixture(roots=('example-skill', 'shared'))
        installer.install(self.source, self.target)
        (self.target / 'example-skill/custom.txt').write_text('my edits', encoding='utf-8')
        self.fixture('upgrade', roots=('example-skill', 'shared'))
        backup = self.root / 'backup'
        installer.install(self.source, self.target, replace=True, backup=backup)
        self.assertEqual((backup / 'example-skill/custom.txt').read_text(encoding='utf-8'), 'my edits')
        self.assertEqual((backup / 'shared/data.txt').read_text(encoding='utf-8'), 'new')
        self.assertEqual((self.target / 'shared/data.txt').read_text(encoding='utf-8'), 'upgrade')

    def test_failed_second_root_restores_both_previous_roots(self):
        self.fixture(roots=('example-skill', 'shared'))
        installer.install(self.source, self.target)
        self.fixture('upgrade', roots=('example-skill', 'shared'))
        original = installer.os.rename
        calls = []
        def fail_once(a, b):
            calls.append((a, b))
            if len(calls) == 4:
                raise OSError('simulated install failure')
            return original(a, b)
        with patch.object(installer.os, 'rename', side_effect=fail_once):
            with self.assertRaisesRegex(OSError, 'simulated'):
                installer.install(self.source, self.target, replace=True, backup=self.root / 'backup')
        for name in ('example-skill', 'shared'):
            self.assertEqual((self.target / name / 'data.txt').read_text(encoding='utf-8'), 'new')

    def test_backup_inside_skills_is_rejected(self):
        installer.install(self.source, self.target)
        self.fixture('upgrade')
        with self.assertRaisesRegex(ValueError, 'outside both'):
            installer.install(self.source, self.target, replace=True, backup=self.target / 'backup')


class PublisherGateTests(unittest.TestCase):
    def simulate_publish(self, tag_mode):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            artifacts = root / 'artifacts'
            artifacts.mkdir()
            source = 'b' * 40
            config = {'tag': 'skills-test', 'source_commit': source, 'name': 'Test release', 'components': [{'name': 'example'}]}
            path = root / 'config.json'
            path.write_text(json.dumps(config), encoding='utf-8')
            (artifacts / 'example.zip').write_bytes(b'unit-test-artifact')
            index = {'release': config, 'packages': [{'archive': 'example.zip',
                     'sha256': hashlib.sha256(b'unit-test-artifact').hexdigest(),
                     'verification': {'installed_twice': True, 'unrelated_skill_preserved': True,
                                      'isolated_runtime_probe': 'PASS'}}]}
            (artifacts / 'release-index.json').write_text(json.dumps(index), encoding='utf-8')
            checksums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts.iterdir()}
            (artifacts / 'SHA256SUMS.txt').write_text(''.join(v + '  ' + k + '\n' for k, v in checksums.items()), encoding='utf-8')
            checksums['SHA256SUMS.txt'] = hashlib.sha256((artifacts / 'SHA256SUMS.txt').read_bytes()).hexdigest()
            calls, tag_reads = [], []
            release = {'id': 123, 'draft': True, 'assets': [], 'tag_name': config['tag'],
                       'target_commitish': source, 'html_url': 'https://github.com/Daylily-Huang/ScholarFlow/releases/tag/skills-test'}
            def reply(req, **kwargs):
                url, method = req.full_url, req.get_method()
                calls.append((method, url))
                if '/actions/runs?' in url:
                    result = {'workflow_runs': [{'name': 'tests', 'event': 'push', 'head_sha': 'a' * 40,
                              'status': 'completed', 'conclusion': 'success'}]}
                elif '/git/ref/tags/' in url:
                    tag_reads.append(1)
                    if tag_mode == 'missing' and len(tag_reads) == 1:
                        raise urllib.error.HTTPError(url, 404, 'missing', {}, None)
                    bad = tag_mode == 'wrong' or (tag_mode == 'moves' and len(tag_reads) > 1)
                    result = {'object': {'type': 'tag' if tag_mode == 'annotated' else 'commit',
                                         'sha': 'c' * 40 if tag_mode == 'annotated' else ('d' * 40 if bad else source)}}
                elif '/git/tags/' in url:
                    result = {'object': {'type': 'commit', 'sha': source}}
                elif url.endswith('/git/refs'):
                    self.assertEqual(json.loads(req.data), {'ref': 'refs/tags/skills-test', 'sha': source})
                    result = {'object': {'type': 'commit', 'sha': source}}
                elif '/releases/tags/' in url:
                    raise urllib.error.HTTPError(url, 404, 'missing', {}, None)
                elif '/assets?name=' in url:
                    name = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['name'][0]
                    self.assertEqual(hashlib.sha256(req.data.read()).hexdigest(), checksums[name])
                    result = {'name': name, 'digest': 'sha256:' + checksums[name]}
                elif method == 'PATCH':
                    result = dict(release, draft=False)
                else:
                    result = release
                return io.BytesIO(json.dumps(result).encode('utf-8'))
            with patch.dict(publisher.os.environ, {'GITHUB_TOKEN': 'synthetic-only',
                                                  'GITHUB_REPOSITORY': 'Daylily-Huang/ScholarFlow'}), \
                    patch.object(publisher.urllib.request, 'urlopen', side_effect=reply):
                try:
                    result = publisher.publish(path, artifacts, 'a' * 40)
                    return result, calls, None
                except ValueError as exc:
                    return None, calls, str(exc)

    def test_existing_wrong_tag_never_creates_or_publishes_release(self):
        result, calls, error = self.simulate_publish('wrong')
        self.assertIsNone(result)
        self.assertIn('different source', error)
        self.assertTrue(all(method == 'GET' for method, _ in calls))

    def test_correct_annotated_tag_can_publish(self):
        result, calls, error = self.simulate_publish('annotated')
        self.assertIsNone(error)
        self.assertTrue(result['published'])
        self.assertEqual(sum(method == 'PATCH' for method, _ in calls), 1)
        self.assertEqual(sum('/git/tags/' in url for _, url in calls), 2)

    def test_tag_moved_during_upload_keeps_draft(self):
        result, calls, error = self.simulate_publish('moves')
        self.assertIsNone(result)
        self.assertIn('changed during upload', error)
        self.assertFalse(any(method == 'PATCH' for method, _ in calls))

    def test_missing_tag_is_created_once_at_expected_commit(self):
        result, calls, error = self.simulate_publish('missing')
        self.assertIsNone(error)
        self.assertTrue(result['published'])
        self.assertEqual(sum(url.endswith('/git/refs') for _, url in calls), 1)

    def test_failed_exact_commit_ci_cannot_create_a_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / 'release.json'
            config.write_text('{}', encoding='utf-8')
            data = {'workflow_runs': [{'name': 'tests', 'event': 'push', 'head_sha': 'a' * 40,
                                      'status': 'completed', 'conclusion': 'failure'}]}
            calls = []
            def reply(req, **kwargs):
                calls.append(req)
                return io.BytesIO(json.dumps(data).encode('utf-8'))
            with patch.dict(publisher.os.environ, {'GITHUB_TOKEN': 'synthetic-only',
                                                  'GITHUB_REPOSITORY': 'Daylily-Huang/ScholarFlow'}), \
                    patch.object(publisher.urllib.request, 'urlopen', side_effect=reply):
                with self.assertRaisesRegex(ValueError, 'CI did not succeed'):
                    publisher.publish(config, root, 'a' * 40)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0].get_method(), 'GET')
            self.assertNotIn('Authorization', calls[0].headers)
            self.assertNotIn('synthetic-only', calls[0].full_url)

    def test_changed_downloaded_artifact_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / 'config.json'
            config.write_text('{}', encoding='utf-8')
            (root / 'changed.zip').write_bytes(b'changed')
            (root / 'SHA256SUMS.txt').write_text('0' * 64 + '  changed.zip\n', encoding='utf-8')
            data = {'workflow_runs': [{'name': 'tests', 'event': 'push', 'head_sha': 'a' * 40,
                                      'status': 'completed', 'conclusion': 'success'}]}
            with patch.dict(publisher.os.environ, {'GITHUB_TOKEN': 'synthetic-only',
                                                  'GITHUB_REPOSITORY': 'Daylily-Huang/ScholarFlow'}), \
                    patch.object(publisher.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(data).encode('utf-8'))) as network:
                with self.assertRaisesRegex(ValueError, 'checksum differs'):
                    publisher.publish(config, root, 'a' * 40)
            self.assertEqual(network.call_count, 1)


if __name__ == '__main__':
    unittest.main()
