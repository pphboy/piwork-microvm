import copy
import hashlib
import importlib.util
import json
import pathlib
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('libslirp_source', HERE / 'libslirp-source.py')
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)
PATCH = HERE.parent / 'guest/qemu/libslirp-hostfwd-backlog.patch'
SOCKET = ('/* synthetic context */\n' * 848 + '''        (haddr->sa_family == AF_INET6 && slirp_socket_set_v6only(s, (flags & SS_HOSTFWD_V6ONLY) != 0) < 0) ||
        (slirp_socket_set_fast_reuse(s) < 0) ||
        (bind(s, haddr, haddrlen) < 0) ||
        (listen(s, 1) < 0)) {
        int tmperrno = errno; /* Don't clobber the real reason we failed */
        if (s >= 0) {
            closesocket(s);
''')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SourceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.patch = self.root / 'guest/qemu/libslirp-hostfwd-backlog.patch'
        self.patch.parent.mkdir(parents=True)
        shutil.copyfile(PATCH, self.patch)
        self.patch_config = {'file': str(self.patch.relative_to(self.root)), 'sha256': sha(self.patch)}
        self.qemu = self.root / 'qemu'
        self.repo = self.qemu / 'subprojects/slirp'
        (self.repo / 'src').mkdir(parents=True)
        (self.repo / 'src/socket.c').write_text(SOCKET)
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        subprocess.run(['git', '-C', str(self.repo), 'add', 'src/socket.c'], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture'], check=True)
        revision = subprocess.check_output(['git', '-C', str(self.repo), 'rev-parse', 'HEAD'], text=True).strip()
        self.config = {'url': 'https://example.invalid/libslirp.git', 'revision': revision, 'patches': [self.patch_config]}
        (self.qemu / 'subprojects/slirp.wrap').write_text('[wrap-git]\nurl = '+self.config['url']+'\nrevision = '+revision+'\n')

    def tearDown(self):
        self.temp.cleanup()

    def test_windows_apply_and_repeat_are_exact(self):
        source.prepare_windows(self.qemu, self.config, self.root)
        self.assertIn('listen(s, (flags & SS_HOSTFWD) ? 128 : 1)', (self.repo / 'src/socket.c').read_text())
        source.prepare_windows(self.qemu, self.config, self.root)

    def test_windows_rejects_wrong_lock_and_unexpected_changes(self):
        wrong = copy.deepcopy(self.config); wrong['revision'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'wrap'):
            source.prepare_windows(self.qemu, wrong, self.root)
        (self.qemu / 'subprojects/slirp.wrap').write_text('[wrap-git]\nurl = '+wrong['url']+'\nrevision = '+wrong['revision']+'\n')
        with self.assertRaisesRegex(ValueError, 'checkout revision'):
            source.prepare_windows(self.qemu, wrong, self.root)
        (self.qemu / 'subprojects/slirp.wrap').write_text('[wrap-git]\nurl = '+self.config['url']+'\nrevision = '+self.config['revision']+'\n')
        source.prepare_windows(self.qemu, self.config, self.root)
        with (self.repo / 'src/socket.c').open('a') as f:
            f.write('unexpected edit\n')
        with self.assertRaisesRegex(ValueError, 'unexpected modifications'):
            source.prepare_windows(self.qemu, self.config, self.root)

    def test_windows_rejects_bad_patch_and_untracked_input(self):
        self.patch.write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            source.prepare_windows(self.qemu, self.config, self.root)
        shutil.copyfile(PATCH, self.patch)
        (self.repo / 'unexpected.txt').write_text('not locked')
        with self.assertRaisesRegex(ValueError, 'unexpected modifications'):
            source.prepare_windows(self.qemu, self.config, self.root)

    def test_linux_download_rejects_changed_source_bytes(self):
        mirror = self.root / 'mirror'; mirror.mkdir()
        (mirror / 'source.dsc').write_bytes(b'original')
        config = {'sourceBase': mirror.as_uri() + '/', 'files': [{'file': 'source.dsc', 'sha256': sha(mirror / 'source.dsc')}]}
        dest = source.fetch_locked(config, self.root / 'downloads')
        self.assertEqual((dest / 'source.dsc').read_bytes(), b'original')
        (dest / 'source.dsc').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            source.fetch_locked(config, dest)

    def test_linux_patch_applies_inside_a_parent_git_worktree_and_detects_dirt(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        downloads = self.root / 'fixture-downloads'; downloads.mkdir()
        (downloads / 'source.dsc').write_text('synthetic')
        config = {'files': [{'file': 'source.dsc'}], 'patches': [self.patch_config]}
        real_run = source.run
        def run(*args, cwd=None):
            if args[0] == 'dpkg-source':
                extracted = pathlib.Path(args[-1]); (extracted / 'src').mkdir(parents=True)
                (extracted / 'src/socket.c').write_text(SOCKET)
                return ''
            return real_run(*args, cwd=cwd)
        with mock.patch.object(source, 'fetch_locked', return_value=downloads), mock.patch.object(source, 'run', side_effect=run):
            prepared = source.prepare_linux(config, self.root)
            self.assertIn('listen(s, (flags & SS_HOSTFWD) ? 128 : 1)', (prepared / 'src/socket.c').read_text())
            self.assertEqual(source.prepare_linux(config, self.root), prepared)
            with (prepared / 'src/socket.c').open('a') as stream: stream.write('unexpected edit\n')
            with self.assertRaisesRegex(ValueError, 'unexpected modifications'):
                source.prepare_linux(config, self.root)


if __name__ == '__main__':
    unittest.main()
