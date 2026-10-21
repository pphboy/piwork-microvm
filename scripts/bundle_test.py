import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bundle


class ArtifactNamesTest(unittest.TestCase):
    def test_cli_names_are_unchanged(self):
        self.assertEqual(bundle.artifact_names('cli', 'linux'), {
            'body': 'launcher-linux',
            'payload': 'payload-linux.tar.gz',
            'manifest': 'bundle-manifest-linux.json',
            'artifact': 'piwork-microvm',
            'sha256': 'piwork-microvm.sha256',
        })
        self.assertEqual(bundle.artifact_names('cli', 'windows')['artifact'], 'piwork-microvm.exe')

    def test_gui_names_never_collide_with_cli(self):
        for platform in ('linux', 'windows'):
            cli = bundle.artifact_names('cli', platform)
            gui = bundle.artifact_names('gui', platform)
            self.assertFalse(set(cli.values()) & set(gui.values()))
            self.assertEqual(gui['artifact'], 'piwork-microvm-gui' + ('.exe' if platform == 'windows' else ''))

    def test_unknown_entry_is_rejected(self):
        with self.assertRaises(ValueError):
            bundle.artifact_names('service', 'linux')


class TrailerTest(unittest.TestCase):
    def test_append_and_read_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            body = root / 'body'
            payload = root / 'payload'
            target = root / 'artifact'
            body.write_bytes(b'\x7fELF' + b'body-bytes')
            payload.write_bytes(b'payload-bytes')
            manifest = json.dumps({'version': 2, 'os': 'linux', 'arch': 'amd64'}, sort_keys=True).encode()
            bundle.append_bundle(body, payload, manifest, target)
            info = bundle.read_trailer(target)
            self.assertEqual(info['length'], len(payload.read_bytes()))
            self.assertEqual(info['manifest'], json.loads(manifest))
            self.assertEqual(info['offset'], len(body.read_bytes()))

    def test_missing_magic_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / 'artifact'
            target.write_bytes(b'x' * 100)
            with self.assertRaises(ValueError):
                bundle.read_trailer(target)

    def test_body_magic_must_match_platform(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            elf = root / 'elf'
            pe = root / 'pe'
            elf.write_bytes(b'\x7fELF')
            pe.write_bytes(b'MZ\x90\x00')
            self.assertTrue(bundle.body_magic_ok(elf, 'linux'))
            self.assertFalse(bundle.body_magic_ok(elf, 'windows'))
            self.assertTrue(bundle.body_magic_ok(pe, 'windows'))
            self.assertFalse(bundle.body_magic_ok(pe, 'linux'))


if __name__ == '__main__':
    unittest.main()
