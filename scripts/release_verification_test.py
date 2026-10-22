import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import release


class VerificationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.evidence = pathlib.Path(self.temp.name)
        self.current = release.input_fingerprint()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, **record):
        (self.evidence / name).write_text(json.dumps(record))

    def status(self, scope, platform):
        result = release.verification(self.evidence)
        return result['scopes'][scope]['platforms'][platform]

    def test_no_evidence_still_produces_a_manifest(self):
        with mock.patch.object(release, 'artifacts', return_value=[]):
            manifest = release.manifest('0.2.1', self.evidence)
        self.assertEqual(manifest['verification']['inputFingerprint'], self.current)
        for scope in ('build', 'integration', 'realModel'):
            for platform in ('linux', 'windows'):
                self.assertEqual(
                    manifest['verification']['scopes'][scope]['platforms'][platform]['status'],
                    'not-verified')

    def test_old_real_provider_record_without_fingerprint_is_not_verified(self):
        self.write('real-model-first.json', scope='real-model', platform='linux',
                   status='passed', realProvider=True, version='0.0.11')
        result = self.status('realModel', 'linux')
        self.assertEqual(result['status'], 'not-verified')
        self.assertIn('fingerprint', result['reason'])

    def test_version_only_record_is_not_verified(self):
        self.write('integration-linux.json', scope='integration', platform='linux',
                   status='passed', version='0.0.11')
        self.assertEqual(self.status('integration', 'linux')['status'], 'not-verified')

    def test_matching_fingerprint_verifies_only_its_scope(self):
        self.write('integration-linux.json', scope='integration', platform='linux',
                   status='passed', inputFingerprint=self.current, checkedAt='2026-10-22T00:00:00Z')
        self.assertEqual(self.status('integration', 'linux')['status'], 'verified')
        self.assertEqual(self.status('integration', 'windows')['status'], 'not-verified')
        self.assertEqual(self.status('realModel', 'linux')['status'], 'not-verified')

    def test_any_locked_input_change_invalidates_evidence(self):
        self.write('build-linux.json', scope='build', platform='linux', status='passed',
                   inputFingerprint='0' * 64)
        result = self.status('build', 'linux')
        self.assertEqual(result['status'], 'not-verified')

    def test_upstream_records_are_informational(self):
        self.write('upstream.json', scope='upstream', status='passed',
                   inputFingerprint=self.current)
        verification = release.verification(self.evidence)
        self.assertEqual(verification['scopes']['upstream']['status'], 'reported')
        self.assertEqual(verification['scopes']['integration']['platforms']['linux']['status'],
                         'not-verified')

    def test_failed_record_does_not_verify(self):
        self.write('build-linux.json', scope='build', platform='linux', status='failed',
                   inputFingerprint=self.current)
        self.assertEqual(self.status('build', 'linux')['status'], 'not-verified')


if __name__ == '__main__':
    unittest.main()
