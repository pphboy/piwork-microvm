import importlib.util
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('gui_build', pathlib.Path(__file__).with_name('gui-build.py'))
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)


class WindowsResourcesTest(unittest.TestCase):
    def test_cleanup_after_success_and_build_failure(self):
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as temp:
                root = pathlib.Path(temp)
                (root / 'dist').mkdir()
                (root / 'cmd/piwork-launcher').mkdir(parents=True)
                resource = root / 'cmd/piwork-launcher/rsrc_windows_amd64.syso'
                body = root / 'dist/body.exe'
                def run(cmd, **kwargs):
                    if cmd[1] == 'run':
                        self.assertFalse(resource.exists())
                        resource.write_bytes(b'COFF')
                    else:
                        self.assertTrue(resource.exists())
                        if fail:
                            raise subprocess.CalledProcessError(1, cmd)
                        body.write_bytes(b'MZbody')
                with mock.patch.object(gui, 'ROOT', root), mock.patch.object(gui, 'run', side_effect=run), \
                     mock.patch.object(gui.bundle, 'source_fingerprint'), \
                     mock.patch.object(gui.bundle, 'write_body_record') as record:
                    if fail:
                        with self.assertRaises(subprocess.CalledProcessError):
                            gui.build_body('windows', body, dict(version='dev', upstream='upstream', commit='commit', manifest='v2'), {})
                        record.assert_not_called()
                    else:
                        gui.build_body('windows', body, dict(version='dev', upstream='upstream', commit='commit', manifest='v2'), {})
                        record.assert_called_once()
                    self.assertFalse(resource.exists())
                    self.assertEqual(list((root / 'dist').glob('gui-resources-*')), [])

    def test_generator_failure_never_removes_another_builds_resource(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / 'dist').mkdir()
            (root / 'cmd/piwork-launcher').mkdir(parents=True)
            resource = root / 'cmd/piwork-launcher/rsrc_windows_amd64.syso'
            resource.write_bytes(b'other build')
            with mock.patch.object(gui, 'ROOT', root), mock.patch.object(gui, 'run', side_effect=subprocess.CalledProcessError(1, 'go')):
                with self.assertRaises(subprocess.CalledProcessError):
                    with gui.windows_resources({}):
                        self.fail('must not build without resource ownership')
            self.assertEqual(resource.read_bytes(), b'other build')
            self.assertEqual(list((root / 'dist').iterdir()), [])
