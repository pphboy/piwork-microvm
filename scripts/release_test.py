import argparse
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bundle
import release


class Result:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class ReleaseGateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        shutil_target = pathlib.Path(bundle.ROOT) / 'build.lock.json'
        (self.root / 'build.lock.json').write_text(shutil_target.read_text())
        self.patches = [mock.patch.object(release, 'ROOT', self.root),
                        mock.patch.object(bundle, 'ROOT', self.root)]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.temp.cleanup()

    def make_artifact(self, entry, platform, version='0.2.1', trailer_manifest=None):
        dist = self.root / 'dist'
        names = bundle.artifact_names(entry, platform)
        body = dist / names['body']
        payload = dist / names['payload']
        dist.mkdir(parents=True, exist_ok=True)
        body.write_bytes(b'\x7fELF' + b'body')
        payload.write_bytes(b'payload')
        manifest = trailer_manifest or {'version': 2, 'os': platform, 'arch': 'amd64',
                                        'payloadSha256': bundle.sha(payload), 'files': []}
        raw = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
        (dist / names['manifest']).write_bytes(raw)
        artifact = dist / names['artifact']
        bundle.append_bundle(body, payload, raw, artifact)
        record = {'recordVersion': 1, 'entry': entry, 'platform': platform, 'arch': 'amd64',
                  'version': version, 'manifest': 'v2',
                  'upstream': {'mode': 'source', 'version': '0.0.11',
                               'buildCommit': 'a' * 40, 'releaseCommit': None},
                  'inputFingerprint': bundle.input_fingerprint(),
                  'body': {'path': body.name, 'size': body.stat().st_size,
                           'sha256': bundle.sha(body)}}
        target = bundle.body_record_path(entry, platform)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(record))
        return artifact

    def test_missing_gui_refuses_a_release(self):
        self.make_artifact('cli', 'linux')
        with mock.patch.object(release, 'verify_resources'), \
             self.assertRaises(release.Failure):
            release.run_build(True, '0.2.1')
        self.assertFalse(release.artifact_path('gui', 'linux').exists())

    def test_old_version_is_rejected_before_assets(self):
        for entry, platform in release.ENTRIES:
            self.make_artifact(entry, platform, version='0.1.9')
        with mock.patch.object(release, 'verify_resources'), \
             self.assertRaises(release.Failure):
            release.verify_artifact_version('0.2.1')

    def test_changed_body_is_rejected(self):
        artifact = self.make_artifact('cli', 'linux')
        record = json.loads(bundle.body_record_path('cli', 'linux').read_text())
        record['body']['sha256'] = '0' * 64
        bundle.body_record_path('cli', 'linux').write_text(json.dumps(record))
        fake = mock.patch.object(release.subprocess, 'run',
                                 return_value=Result(0, 'piwork-microvm 0.2.1\n'))
        with fake, mock.patch.object(release, 'verify_resources'), self.assertRaises(release.Failure):
            release.verify_artifact_version('0.2.1')

    def test_reuse_gate_checks_complete_body_identity(self):
        for field, value in [('entry', 'gui'), ('platform', 'windows'),
                             ('sourceFingerprint', 'stale'), ('inputFingerprint', 'old')]:
            with self.subTest(field=field):
                self.make_artifact('cli', 'linux')
                path = bundle.body_record_path('cli', 'linux')
                record = json.loads(path.read_text())
                record['sourceFingerprint'] = bundle.source_fingerprint()
                lock = json.loads((self.root / 'build.lock.json').read_text())
                record['upstream'] = {'mode': release.built_input_mode(),
                                     'version': release.upstream_version(),
                                     'buildCommit': lock['piwork']['commit'],
                                     'releaseCommit': lock['piwork']['release']['releaseCommit']}
                record[field] = value
                path.write_text(json.dumps(record))
                with mock.patch.object(release, 'verify_resources'), self.assertRaises(release.Failure):
                    release.verify_artifact_version('0.2.1')

    def test_resource_mismatch_is_rejected(self):
        self.make_artifact('cli', 'linux')
        path = self.root / 'dist/current-input'
        path.write_bytes(b'current')
        manifest = {'version': 2, 'os': 'linux', 'arch': 'amd64',
                    'payloadSha256': '0' * 64,
                    'files': [{'path': 'guest/kernel', 'size': 1, 'sha256': 'f' * 64}]}
        (self.root / 'dist' / bundle.artifact_names('cli', 'linux')['manifest']).write_text(
            json.dumps(manifest))
        with mock.patch.object(bundle, 'collect_inputs', return_value={'guest/kernel': path}), \
             self.assertRaises(release.Failure):
            release.verify_resources('cli', 'linux')

    def test_test_failure_prevents_tag_and_publication(self):
        args = argparse.Namespace(version='0.2.1', evidence_dir=str(self.root / 'evidence'),
                                  manifest_out=None, notes_out=None, patches_out=None,
                                  dry_run=False)
        calls = []
        with mock.patch.object(release, 'preflight'), \
             mock.patch.object(release, 'run_tests', side_effect=release.Failure('tests failed')), \
             mock.patch.object(release.subprocess, 'run',
                               side_effect=lambda *a, **k: calls.append(a)), \
             self.assertRaises(release.Failure):
            release.cmd_publish(args)
        self.assertEqual(calls, [])

    def test_input_failure_prevents_tag_and_publication(self):
        args = argparse.Namespace(version='0.2.1', evidence_dir=str(self.root / 'evidence'),
                                  manifest_out=None, notes_out=None, patches_out=None,
                                  dry_run=False)
        calls = []
        with mock.patch.object(release, 'preflight', side_effect=release.Failure('input failed')), \
             mock.patch.object(release.subprocess, 'run',
                               side_effect=lambda *a, **k: calls.append(a)), \
             self.assertRaises(release.Failure):
            release.cmd_publish(args)
        self.assertEqual(calls, [])

    def test_asset_names_cover_all_four_entries(self):
        labels = {release.asset_label('0.2.1', entry, platform,
                                      bundle.artifact_names(entry, platform)['artifact'])
                  for entry, platform in release.ENTRIES}
        self.assertEqual(labels, {'piwork-microvm-v0.2.1-linux-amd64',
                                  'piwork-microvm-v0.2.1-windows-amd64.exe',
                                  'piwork-microvm-gui-v0.2.1-linux-amd64',
                                  'piwork-microvm-gui-v0.2.1-windows-amd64.exe'})

    def test_preflight_rejects_a_failed_official_input(self):
        lock = json.loads((self.root / 'build.lock.json').read_text())
        if lock['piwork'].get('inputMode') != 'official-release':
            lock['piwork']['inputMode'] = 'official-release'
            lock['piwork']['release'] = {'metadata': {'releaseVersion': '0.0.11'}}
            (self.root / 'build.lock.json').write_text(json.dumps(lock))
        with mock.patch.object(release, 'check_tree_clean'), \
             mock.patch.object(release, 'check_tag_absent'), \
             mock.patch.object(release.piwork_release, 'check_prepared',
                               side_effect=release.piwork_release.ReleaseError('bad input')), \
             self.assertRaises(release.Failure):
            release.preflight('0.2.1', False)


if __name__ == '__main__':
    unittest.main()
