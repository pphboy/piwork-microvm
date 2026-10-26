import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

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


class BuildModeTest(unittest.TestCase):
    def test_marker_overrides_the_lock_for_bundling(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            (out / 'piwork').mkdir()
            lock = {'piwork': {'inputMode': 'official-release'}}
            self.assertEqual(bundle.built_input_mode(out, lock), 'official-release')
            (out / 'piwork/build-mode.json').write_text(json.dumps({'inputMode': 'source'}))
            self.assertEqual(bundle.built_input_mode(out, lock), 'source')


class BodyRecordTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        shutil.copyfile(pathlib.Path(bundle.ROOT) / 'build.lock.json',
                        self.root / 'build.lock.json')
        for relative in ('cmd/piwork-launcher/frontend', 'tools/gui-resources'):
            shutil.copytree(pathlib.Path(bundle.ROOT) / relative, self.root / relative)
        for relative in ('cmd/piwork-launcher/ui-sources.json',
                         'scripts/gui-build.py', 'scripts/gui-build-windows.ps1'):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pathlib.Path(bundle.ROOT) / relative, target)
        self.out = self.root / 'dist'
        (self.out / 'piwork').mkdir(parents=True)
        (self.out / 'piwork/metadata.json').write_text(json.dumps({'releaseVersion': '0.0.11'}))
        self.body = self.out / 'launcher-gui-linux'
        self.body.write_bytes(b'\x7fELF' + b'body')
        self.patch = mock.patch.object(bundle, 'ROOT', self.root)
        self.patch.start()
        self.identity = bundle.build_identity(self.out, 2)

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_record_binds_the_body_and_locked_inputs(self):
        record = bundle.write_body_record('gui', 'linux', self.body, self.identity)
        self.assertEqual(record['body']['sha256'], bundle.sha(self.body))
        self.assertEqual(record['inputFingerprint'], bundle.input_fingerprint())
        self.assertEqual(bundle.verify_body_record('gui', 'linux', self.body, self.identity),
                         record)

    def test_unrecorded_body_cannot_be_packaged(self):
        with self.assertRaises(SystemExit):
            bundle.verify_body_record('gui', 'linux', self.body, self.identity)

    def test_changed_body_cannot_be_packaged(self):
        bundle.write_body_record('gui', 'linux', self.body, self.identity)
        self.body.write_bytes(self.body.read_bytes() + b'changed')
        with self.assertRaises(SystemExit):
            bundle.verify_body_record('gui', 'linux', self.body, self.identity)

    def test_other_entry_or_platform_record_is_rejected(self):
        bundle.write_body_record('cli', 'linux', self.body, self.identity)
        with self.assertRaises(SystemExit):
            bundle.verify_body_record('gui', 'linux', self.body, self.identity)
        bundle.write_body_record('gui', 'windows', self.body, self.identity)
        with self.assertRaises(SystemExit):
            bundle.verify_body_record('gui', 'linux', self.body, self.identity)

    def test_old_version_cannot_be_packaged(self):
        bundle.write_body_record('gui', 'linux', self.body, self.identity)
        other = dict(self.identity, version='0.1.9')
        with self.assertRaises(SystemExit):
            bundle.verify_body_record('gui', 'linux', self.body, other)

    def test_body_from_other_go_sources_is_rejected(self):
        (self.root / 'main.go').write_text('package main\n')
        bundle.write_body_record('gui', 'linux', self.body, self.identity)
        (self.root / 'main.go').write_text('package main\n// changed\n')
        with self.assertRaises(SystemExit):
            bundle.verify_body_record('gui', 'linux', self.body, self.identity)

    def test_changed_lock_invalidates_the_body(self):
        bundle.write_body_record('gui', 'linux', self.body, self.identity)
        lock = json.loads((self.root / 'build.lock.json').read_text())
        lock['piwork']['commit'] = 'f' * 40
        (self.root / 'build.lock.json').write_text(json.dumps(lock))
        with self.assertRaises(SystemExit):
            bundle.verify_body_record('gui', 'linux', self.body, self.identity)

    def test_gui_resource_inputs_invalidate_body_without_affecting_cli(self):
        for relative in ('cmd/piwork-launcher/frontend/assets/piwork-logo.png',
                         'cmd/piwork-launcher/frontend/index.html',
                         'cmd/piwork-launcher/ui-sources.json',
                         'scripts/gui-build.py', 'scripts/gui-build-windows.ps1'):
            with self.subTest(input=relative):
                bundle.write_body_record('gui', 'linux', self.body, self.identity)
                cli = bundle.source_fingerprint(entry='cli')
                path = self.root / relative
                original = path.read_bytes()
                path.write_bytes(original + b'changed')
                with self.assertRaisesRegex(SystemExit, 'body inputs'):
                    bundle.verify_body_record('gui', 'linux', self.body, self.identity)
                self.assertEqual(cli, bundle.source_fingerprint(entry='cli'))
                path.write_bytes(original)

    def test_generated_resources_do_not_invalidate_record(self):
        record = bundle.write_body_record('gui', 'linux', self.body, self.identity)
        resource = self.root / 'cmd/piwork-launcher/rsrc_windows_amd64.syso'
        resource.write_bytes(b'temporary COFF')
        self.assertEqual(record, bundle.verify_body_record('gui', 'linux', self.body, self.identity))
        resource.unlink()
        self.assertEqual(record, bundle.verify_body_record('gui', 'linux', self.body, self.identity))

    def test_missing_gui_input_is_rejected(self):
        (self.root / 'cmd/piwork-launcher/frontend/assets/piwork-logo.png').unlink()
        with self.assertRaisesRegex(SystemExit, 'missing GUI body input'):
            bundle.write_body_record('gui', 'linux', self.body, self.identity)


if __name__ == '__main__':
    unittest.main()
