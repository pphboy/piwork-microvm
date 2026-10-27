"""Acceptance claims must follow the complete locked input, independently by scope."""
import copy
import json
import pathlib
import shutil
import tempfile
import tarfile
import unittest
from unittest import mock
import release


class EvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.inputs = release.locked_inputs()
        self.patch = mock.patch.object(release, 'locked_inputs', side_effect=lambda: self.inputs)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def record(self, **fields):
        value = {'scope': 'integration', 'platform': 'linux', 'status': 'passed',
                 'checkedAt': '2026-10-22T12:00:00Z',
                 'inputFingerprint': release.input_fingerprint(), **fields}
        (self.root / 'record.json').write_text(json.dumps(value))

    def status(self, scope='integration', platform='linux'):
        return release.verification(self.root)['scopes'][scope]['platforms'][platform]['status']

    def test_absent_evidence_still_generates_unverified_scopes(self):
        value = release.verification(self.root)
        self.assertEqual(value['basis'], 'locked-inputs')
        self.assertEqual(self.status(), 'not-verified')
        self.assertEqual(self.status('realModel'), 'not-verified')

    def test_old_real_provider_and_version_only_cannot_verify(self):
        for fields in ({'realProvider': True, 'inputFingerprint': None},
                       {'version': '0.0.11', 'inputFingerprint': None},
                       {'realProvider': True, 'inputFingerprint': 'old-input'}):
            self.record(scope='real-model', **fields)
            self.assertEqual(self.status('realModel'), 'not-verified')

    def test_full_match_only_verifies_recorded_platform_and_scope(self):
        self.record()
        self.assertEqual(self.status(), 'verified')
        self.assertEqual(self.status(platform='windows'), 'not-verified')
        self.assertEqual(self.status('build'), 'not-verified')
        self.assertEqual(self.status('realModel'), 'not-verified')

    def test_each_locked_identity_change_invalidates_same_version_evidence(self):
        original = copy.deepcopy(self.inputs)
        paths = [('piwork', 'commit'), ('piwork', 'release', 'releaseCommit'),
                 ('piwork', 'release', 'assets', 'archive', 'sha256'),
                 ('piwork', 'release', 'assets', 'releaseBuild', 'sha256'),
                 ('piwork', 'release', 'assets', 'releaseManifest', 'sha256'),
                 ('kernel', 'sha256'), ('qemu', 'sha256'),
                 ('toolchain', 'guestBaseImage'), ('toolchain', 'go')]
        # Include every nested image identity and the entire lock digest.
        paths += [('piwork', 'release', 'images'), ('buildLockSHA256',)]
        self.record()
        for path in paths:
            with self.subTest(path=path):
                self.inputs = copy.deepcopy(original)
                target = self.inputs
                for key in path[:-1]: target = target[key]
                target[path[-1]] = 'changed'
                self.assertEqual(self.status(), 'not-verified')

    def test_passing_fresh_case_does_not_hide_same_input_failure(self):
        self.record()
        failure = {'scope': 'integration', 'platform': 'linux', 'status': 'failed',
                   'inputFingerprint': release.input_fingerprint(),
                   'failed': 'retained data WAL validation'}
        (self.root / 'retained-data.json').write_text(json.dumps(failure))
        status = release.verification(self.root)['scopes']['integration']['platforms']['linux']
        self.assertEqual(status['status'], 'verified-with-known-issues')
        self.assertEqual(status['knownIssues'][0]['summary'], failure['failed'])
        self.assertEqual(self.status(platform='windows'), 'not-verified')
        failure['inputFingerprint'] = 'historical-input'
        (self.root / 'retained-data.json').write_text(json.dumps(failure))
        self.assertEqual(self.status(), 'verified')

    def test_current_failure_without_passing_case_stays_unverified(self):
        self.record(status='failed', failed='reopen failed')
        status = release.verification(self.root)['scopes']['integration']['platforms']['linux']
        self.assertEqual(status['status'], 'not-verified')
        self.assertEqual(status['knownIssues'][0]['summary'], 'reopen failed')

    def generated_notes(self):
        with mock.patch.object(release, 'artifacts', return_value=[]), \
             mock.patch.object(release, 'guest_package_count', return_value=None), \
             mock.patch.object(release, 'guest_license_summary', return_value=None), \
             mock.patch.object(release, 'official_license_gaps', return_value=None):
            return release.notes('0.2.2', self.root)

    def test_notes_follow_upstream_version_and_preview_status(self):
        for version, preview in [('0.0.12', True), ('0.0.13', False)]:
            with self.subTest(version=version, preview=preview):
                self.inputs['builtInputMode'] = 'official-release'
                self.inputs['upstreamPiworkVersion'] = version
                self.inputs['piwork']['release']['tag'] = 'v' + version
                self.inputs['piwork']['release']['prerelease'] = preview
                notes = self.generated_notes()
                kind = 'upstream Preview' if preview else 'upstream release'
                self.assertIn('Bundles original Piwork ' + version + ' at commit', notes)
                self.assertIn('Official release input: `v' + version + '` (' + kind + ')', notes)
                self.assertIn('- Piwork ' + version + ' is an ' + kind + '.', notes)
                self.assertNotIn('Piwork 0.0.11', notes)
                if not preview:
                    self.assertNotIn('Preview', notes)

    def test_notes_and_patch_attachment_identify_both_locked_sources(self):
        notes = self.generated_notes()
        slirp = self.inputs['qemu']['libslirp']
        for text in (slirp['windows']['url'], slirp['windows']['revision'], slirp['linux']['sourceBase'], slirp['linux']['version']):
            self.assertIn(text, notes)
        archive = self.root / 'patches.tar.gz'
        release.patches(archive)
        with tarfile.open(archive) as tar:
            names = set(tar.getnames())
        self.assertEqual(names, {pathlib.Path(p['file']).name for p in self.inputs['qemu']['windowsPatches'] + slirp['windows']['patches'] + slirp['linux']['patches']})
        lock = json.loads((release.ROOT / 'build.lock.json').read_text())
        (self.root / 'build.lock.json').write_text(json.dumps(lock))
        for patch in lock['qemu']['windowsPatches'] + slirp['windows']['patches']:
            target = self.root / patch['file']; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(release.ROOT / patch['file'], target)
        with mock.patch.object(release, 'ROOT', self.root):
            release.patches(archive)
            (self.root / slirp['windows']['patches'][0]['file']).write_text('tampered')
            with self.assertRaisesRegex(release.Failure, 'differs from the lock'):
                release.patches(archive)

    def test_source_notes_do_not_invent_an_official_release_status(self):
        self.inputs['builtInputMode'] = 'source'
        self.inputs['piwork'].pop('release', None)
        notes = self.generated_notes()
        self.assertIn('a locked upstream source input', notes)
        self.assertNotIn('Official release input:', notes)
        self.assertNotIn('upstream Preview', notes)

    def test_notes_retain_known_failure_source_offer_and_unverified_scopes(self):
        self.record(status='failed', failed='retained WAL case')
        notes = self.generated_notes()
        for text in ['Unresolved linux integration case: retained WAL case',
                     'Corresponding source', 'Written offer:', 'BusyBox', 'qboot',
                     'libfdt', '| integration | windows | not-verified |',
                     '| realModel | linux | not-verified |']:
            self.assertIn(text, notes)

    def test_upstream_report_never_upgrades_microvm_integration(self):
        self.record(scope='upstream')
        self.assertEqual(release.verification(self.root)['scopes']['upstream']['status'], 'reported')
        self.assertEqual(self.status(), 'not-verified')


if __name__ == '__main__':
    unittest.main()
