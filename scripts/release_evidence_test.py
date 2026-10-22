"""Acceptance claims must follow the complete locked input, independently by scope."""
import copy
import json
import pathlib
import tempfile
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

    def test_upstream_report_never_upgrades_microvm_integration(self):
        self.record(scope='upstream')
        self.assertEqual(release.verification(self.root)['scopes']['upstream']['status'], 'reported')
        self.assertEqual(self.status(), 'not-verified')


if __name__ == '__main__':
    unittest.main()
