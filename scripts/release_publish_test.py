import copy
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import release

VERSION = '0.2.1'
COMMIT = 'a' * 40


def digest(data):
    return hashlib.sha256(data).hexdigest()


class FakeRemote:
    def __init__(self, release_value=None, fail_on=None):
        self.value = release_value
        self.calls = []
        self.fail_on = fail_on

    def release(self, tag):
        return copy.deepcopy(self.value)

    def create_draft(self, tag, title, notes_file):
        self.calls.append(('create', tag))
        self.value = {'tag_name': tag, 'draft': True, 'assets': []}

    def upload(self, tag, path, name):
        self.calls.append(('upload', name))
        if self.fail_on == name:
            raise release.Failure('simulated upload failure')
        data = pathlib.Path(path).read_bytes()
        self.value['assets'].append({'name': name, 'size': len(data),
                                     'digest': 'sha256:' + digest(data), 'state': 'uploaded'})

    def delete_asset(self, tag, name):
        self.calls.append(('delete', name))
        self.value['assets'] = [a for a in self.value['assets'] if a['name'] != name]

    def publish(self, tag):
        self.calls.append(('publish', tag))
        self.value['draft'] = False


class PublishPlanTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        (self.root / 'build.lock.json').write_text(
            (pathlib.Path(release.ROOT) / 'build.lock.json').read_text())
        self.patches = [mock.patch.object(release, 'ROOT', self.root)]
        for patch in self.patches:
            patch.start()
        self.plan = self.make_plan()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.temp.cleanup()

    def make_plan(self, files=None):
        target = release.plan_dir(VERSION)
        target.mkdir(parents=True)
        assets = []
        for name, data in (files or {'alpha.bin': b'alpha', 'beta.bin': b'beta'}).items():
            (target / name).write_bytes(data)
            assets.append({'name': name, 'size': len(data), 'sha256': digest(data)})
        plan = {'planVersion': 1, 'version': VERSION, 'tag': 'v' + VERSION,
                'sourceCommit': COMMIT, 'inputFingerprint': release.input_fingerprint(),
                'createdAt': '2026-10-22T00:00:00Z', 'assets': assets,
                'notes': 'notes\n'}
        release.write_json(release.plan_path(VERSION), plan)
        (target / 'notes.md').write_text('notes\n')
        return plan

    def run_publish(self, remote, dry_run=False):
        with mock.patch.object(release, 'ensure_remote_tag'), \
             mock.patch.object(release, 'git_out', side_effect=lambda *a: COMMIT):
            return release.publish_plan(self.plan, VERSION, remote, dry_run=dry_run)

    def test_dry_run_writes_nothing_remote(self):
        remote = FakeRemote()
        with mock.patch.object(release, 'ensure_remote_tag', side_effect=AssertionError('tag write')):
            result = self.run_publish(remote, dry_run=True)
        self.assertEqual(result['status'], 'dry-run')
        self.assertEqual(remote.calls, [])

    def test_interrupted_retry_reuses_matching_assets(self):
        remote = FakeRemote({'tag_name': 'v' + VERSION, 'draft': True, 'assets': [
            {'name': 'alpha.bin', 'size': 5, 'digest': 'sha256:' + digest(b'alpha'),
             'state': 'uploaded'}]})
        result = self.run_publish(remote)
        self.assertEqual(result['status'], 'published')
        self.assertNotIn(('upload', 'alpha.bin'), remote.calls)
        self.assertIn(('upload', 'beta.bin'), remote.calls)
        self.assertIn(('publish', 'v' + VERSION), remote.calls)

    def test_incomplete_placeholder_is_cleaned_then_reuploaded(self):
        remote = FakeRemote({'tag_name': 'v' + VERSION, 'draft': True, 'assets': [
            {'name': 'alpha.bin', 'size': 0, 'digest': None, 'state': 'starter'}]})
        self.run_publish(remote)
        self.assertIn(('delete', 'alpha.bin'), remote.calls)
        self.assertIn(('upload', 'alpha.bin'), remote.calls)
        self.assertEqual(remote.calls.index(('delete', 'alpha.bin')),
                         remote.calls.index(('upload', 'alpha.bin')) - 1)

    def test_completed_conflicting_asset_is_not_overwritten(self):
        remote = FakeRemote({'tag_name': 'v' + VERSION, 'draft': True, 'assets': [
            {'name': 'alpha.bin', 'size': 5, 'digest': 'sha256:' + '0' * 64,
             'state': 'uploaded'}]})
        with self.assertRaises(release.Failure):
            self.run_publish(remote)
        self.assertNotIn(('delete', 'alpha.bin'), remote.calls)
        self.assertNotIn(('publish', 'v' + VERSION), remote.calls)

    def test_upload_failure_keeps_the_draft(self):
        remote = FakeRemote(fail_on='beta.bin')
        with self.assertRaises(release.Failure):
            self.run_publish(remote)
        self.assertNotIn(('publish', 'v' + VERSION), remote.calls)

    def test_published_release_with_matching_assets_is_idempotent(self):
        remote = FakeRemote(self.published('v' + VERSION))
        result = self.run_publish(remote)
        self.assertEqual(result['status'], 'already-published')
        self.assertEqual([call[0] for call in remote.calls], [])

    def test_published_release_with_different_assets_is_refused(self):
        value = self.published('v' + VERSION)
        value['assets'][0]['sha256'] = '0' * 64
        value['assets'][0]['digest'] = 'sha256:' + '0' * 64
        remote = FakeRemote(value)
        with self.assertRaises(release.Failure):
            self.run_publish(remote)
        self.assertEqual([call[0] for call in remote.calls], [])

    def test_tag_on_another_commit_blocks_publication(self):
        remote = FakeRemote()
        with mock.patch.object(release, 'ensure_remote_tag',
                               side_effect=release.Failure('tag points elsewhere')), \
             mock.patch.object(release, 'git_out', side_effect=lambda *a: COMMIT), \
             self.assertRaises(release.Failure):
            release.publish_plan(self.plan, VERSION, remote)
        self.assertEqual(remote.calls, [])

    def published(self, tag):
        return {'tag_name': tag, 'draft': False, 'body': 'notes\n', 'assets': [
            {'name': asset['name'], 'size': asset['size'],
             'digest': 'sha256:' + asset['sha256'], 'state': 'uploaded'}
            for asset in self.plan['assets']]}

    def test_draft_with_other_notes_is_refused(self):
        remote = FakeRemote({'tag_name': 'v' + VERSION, 'draft': True, 'body': 'different notes',
                             'assets': []})
        with self.assertRaises(release.Failure):
            self.run_publish(remote)
        self.assertNotIn(('publish', 'v' + VERSION), remote.calls)

    def test_plan_from_other_inputs_is_refused(self):
        self.plan['inputFingerprint'] = '0' * 64
        with self.assertRaises(release.Failure):
            self.run_publish(FakeRemote())


if __name__ == '__main__':
    unittest.main()
