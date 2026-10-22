import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import piwork


class ModeSelectionTest(unittest.TestCase):
    def run_main(self, argv):
        with mock.patch.object(sys, 'argv', ['piwork.py'] + argv):
            piwork.main()

    def test_official_lock_uses_the_import_path_only(self):
        calls = []
        with mock.patch.object(piwork.piwork_release, 'check_prepared',
                               side_effect=piwork.piwork_release.ReleaseError('not prepared')), \
             mock.patch.object(piwork.piwork_release, 'prepare_lock',
                               side_effect=lambda lock: calls.append('prepare') or
                               {'version': '0.0.11', 'buildCommit': 'a' * 40}), \
             mock.patch.object(piwork, 'build_from_source',
                               side_effect=lambda: calls.append('source')):
            self.run_main([])
        self.assertEqual(calls, ['prepare'])

    def test_verified_official_input_is_not_prepared_again(self):
        calls = []
        with mock.patch.object(piwork.piwork_release, 'check_prepared',
                               return_value={'tag': 'v0.0.11'}), \
             mock.patch.object(piwork.piwork_release, 'prepare_lock',
                               side_effect=lambda lock: calls.append('prepare')), \
             mock.patch.object(piwork, 'build_from_source',
                               side_effect=lambda: calls.append('source')):
            self.run_main([])
        self.assertEqual(calls, [])

    def test_source_build_is_an_explicit_choice(self):
        calls = []
        with mock.patch.object(piwork.piwork_release, 'prepare_lock',
                               side_effect=lambda lock: calls.append('prepare')), \
             mock.patch.object(piwork, 'build_from_source',
                               side_effect=lambda: calls.append('source')):
            self.run_main(['--source-build'])
        self.assertEqual(calls, ['source'])


if __name__ == '__main__':
    unittest.main()
