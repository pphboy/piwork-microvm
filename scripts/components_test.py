import copy
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import components


def lock_record():
    return {
        'piwork': {'commit': 'a' * 40, 'url': 'https://github.com/pphboy/piwork.git'},
        'go': 'go1.25.5',
        'dockerImage': 'docker@sha256:1',
        'guestBaseImage': 'debian@sha256:2',
        'debianSnapshot': '20261018T000000Z',
        'dockerVersion': '28.5.2',
        'linux': {'version': '6.6.159', 'url': 'https://example.invalid/linux.tar.xz',
                  'sha256': '3' * 64},
        'qemu': {'version': '10.0.8', 'url': 'https://example.invalid/qemu.tar.xz',
                 'sha256': '4' * 64,
                 'windowsPatches': [{'file': 'guest/qemu/pipe-poll.patch', 'sha256': '5' * 64}],
                 'windowsToolchain': {'manifest': 'guest/qemu/windows-toolchain.lock.json',
                                      'sha256': '6' * 64,
                                      'baseImage': 'fedora@sha256:7'}},
        'qboot': {'file': 'qboot', 'sha256': '8' * 64},
    }


class Result:
    def __init__(self, returncode=0, stdout=''):
        self.returncode = returncode
        self.stdout = stdout


def runner(args, **kwargs):
    if args[:3] == ['docker', 'image', 'inspect']:
        return Result(0, 'sha256:builder\n')
    return Result(1)


class ComponentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.lock = lock_record()
        (self.root / 'build.lock.json').write_text(json.dumps(self.lock))
        files = ['scripts/kernel.sh', 'guest/Dockerfile.build', 'guest/kernel/config.fragment',
                 'scripts/qemu.sh', 'scripts/qemu-bundle.py', 'scripts/qemu-windows.sh',
                 'scripts/qemu-windows-bundle.py', 'scripts/windows-toolchain.py',
                 'guest/qemu/Dockerfile.windows', 'guest/qemu/pipe-poll.patch',
                 'guest/qemu/windows-toolchain.lock.json', 'scripts/rootfs.py',
                 'scripts/rootfs-assemble.sh', 'scripts/guest-licenses.py',
                 'guest/rootfs/Dockerfile', 'guest/initramfs/init',
                 'guest/rootfs/files/service', 'cmd/piwork-guest/main.go',
                 'internal/agent/main.go', 'go.mod', 'go.sum']
        for name in files:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('content of ' + name + '\n')
        guest = self.root / 'dist/guest'
        guest.mkdir(parents=True)
        for name, data in [('kernel', b'kernel'), ('kernel.config', b'config'),
                           ('rootfs.ext4', b'rootfs'), ('initramfs', b'initrd'),
                           ('state.qcow2', b'state'), ('firmware.json', b'{}')]:
            (guest / name).write_bytes(data)
        (guest / 'qemu-data').mkdir()
        (guest / 'qemu-data/qboot.rom').write_bytes(b'rom')
        (guest / 'guest-licenses').mkdir()
        (guest / 'guest-licenses/index.json').write_text('{}')
        (guest / 'images.tar').write_bytes(b'images')
        piwork = self.root / 'dist/piwork'
        (piwork / 'bin').mkdir(parents=True)
        for name in ('piwork-core', 'piwork-cli'):
            (piwork / 'bin' / name).write_bytes(name.encode())
        (piwork / 'metadata.json').write_text('{"releaseVersion": "0.0.11"}')
        (piwork / 'images.json').write_text('{"agent": {}}')
        qemu = self.root / 'dist/qemu'
        qemu.mkdir()
        (qemu / 'qemu-system-x86_64').write_bytes(b'qemu')
        (qemu / 'dependencies.json').write_text('[]')
        win = self.root / 'dist/qemu-windows'
        win.mkdir()
        (win / 'qemu-system-x86_64.exe').write_bytes(b'qemu.exe')

    def tearDown(self):
        self.temp.cleanup()

    def check(self, kind, lock=None, force=False):
        return components.verify(kind, lock or self.lock, root=self.root,
                                 runner=runner, force=force)

    def test_no_record_is_a_miss(self):
        hit, reason = self.check('kernel')
        self.assertFalse(hit)
        self.assertIn('no component record', reason)

    def test_record_then_hit(self):
        components.write_record('kernel', self.lock, root=self.root, runner=runner)
        hit, reason = self.check('kernel')
        self.assertTrue(hit, reason)

    def test_only_piwork_changes_do_not_invalidate_kernel_or_qemu(self):
        components.write_record('kernel', self.lock, root=self.root, runner=runner)
        components.write_record('qemu', self.lock, root=self.root, runner=runner)
        changed = copy.deepcopy(self.lock)
        changed['piwork']['commit'] = 'b' * 40
        self.assertTrue(self.check('kernel', changed)[0])
        self.assertTrue(self.check('qemu', changed)[0])

    def test_kernel_config_change_invalidates(self):
        components.write_record('kernel', self.lock, root=self.root, runner=runner)
        (self.root / 'guest/kernel/config.fragment').write_text('changed\n')
        hit, reason = self.check('kernel')
        self.assertFalse(hit)
        self.assertIn('inputs changed', reason)

    def test_missing_output_invalidates(self):
        components.write_record('kernel', self.lock, root=self.root, runner=runner)
        (self.root / 'dist/guest/kernel.config').unlink()
        hit, reason = self.check('kernel')
        self.assertFalse(hit)
        self.assertIn('absent', reason)

    def test_corrupt_output_invalidates(self):
        components.write_record('kernel', self.lock, root=self.root, runner=runner)
        (self.root / 'dist/guest/kernel').write_bytes(b'KERNEL')
        hit, reason = self.check('kernel')
        self.assertFalse(hit)
        self.assertIn('digest differs', reason)

    def test_incomplete_record_is_not_trusted(self):
        components.write_record('kernel', self.lock, root=self.root, runner=runner)
        path = components.record_path('kernel', self.root)
        record = json.loads(path.read_text())
        record['outputs'] = {}
        path.write_text(json.dumps(record))
        hit, reason = self.check('kernel')
        self.assertFalse(hit)
        self.assertIn('no outputs', reason)

    def test_non_empty_partial_output_set_is_not_trusted(self):
        components.write_record('kernel', self.lock, root=self.root, runner=runner)
        path = components.record_path('kernel', self.root)
        record = json.loads(path.read_text())
        record['outputs'] = {'guest/kernel': record['outputs']['guest/kernel']}
        path.write_text(json.dumps(record))
        hit, reason = self.check('kernel')
        self.assertFalse(hit)
        self.assertIn('output set changed', reason)

    def test_force_requests_a_rebuild(self):
        components.write_record('kernel', self.lock, root=self.root, runner=runner)
        hit, reason = self.check('kernel', force=True)
        self.assertFalse(hit)
        self.assertIn('full rebuild', reason)

    def test_windows_patch_change_invalidates_qemu_windows(self):
        components.write_record('qemu-windows', self.lock, root=self.root, runner=runner)
        (self.root / 'guest/qemu/pipe-poll.patch').write_text('changed\n')
        hit, reason = self.check('qemu-windows')
        self.assertFalse(hit)
        self.assertIn('inputs changed', reason)

    def test_guest_application_change_forces_new_assembly(self):
        components.write_record('guest', self.lock, root=self.root, runner=runner)
        self.assertTrue(self.check('guest')[0])
        (self.root / 'dist/piwork/bin/piwork-core').write_bytes(b'new core')
        hit, reason = self.check('guest')
        self.assertFalse(hit)
        self.assertIn('inputs changed', reason)

    def test_guest_version_manifest_change_is_not_enough(self):
        components.write_record('guest', self.lock, root=self.root, runner=runner)
        (self.root / 'dist/piwork/metadata.json').write_text('{"releaseVersion": "0.0.12"}')
        hit, reason = self.check('guest')
        self.assertFalse(hit)
        self.assertIn('inputs changed', reason)

    def test_record_refuses_an_incomplete_output_set(self):
        (self.root / 'dist/guest/kernel').unlink()
        with self.assertRaises(components.ComponentError):
            components.write_record('kernel', self.lock, root=self.root, runner=runner)


if __name__ == '__main__':
    unittest.main()
