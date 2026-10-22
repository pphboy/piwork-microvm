import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import source


def lock_with(**piwork):
    base = {'url': 'https://example.invalid/piwork.git', 'commit': 'b' * 40,
            'branch': 'main', 'resolvedAt': '2026-01-01T00:00:00+00:00'}
    base.update(piwork)
    return {'piwork': base}


OFFICIAL = lock_with(inputMode='official-release',
                     release={'tag': 'v0.0.11', 'releaseCommit': 'c' * 40})


class InputModeTest(unittest.TestCase):
    def test_lock_without_mode_is_source(self):
        self.assertEqual(source.input_mode(lock_with()), 'source')

    def test_explicit_source_mode(self):
        self.assertEqual(source.input_mode(lock_with(inputMode='source')), 'source')

    def test_official_mode_exposes_release_record(self):
        self.assertEqual(source.input_mode(OFFICIAL), 'official-release')
        self.assertEqual(source.official_release(OFFICIAL)['tag'], 'v0.0.11')

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(source.LockError):
            source.input_mode(lock_with(inputMode='binary'))

    def test_official_mode_requires_release_record(self):
        with self.assertRaises(source.LockError):
            source.official_release(lock_with(inputMode='official-release'))

    def test_source_mode_has_no_release_record(self):
        with self.assertRaises(source.LockError):
            source.official_release(lock_with())


class RefreshLockTest(unittest.TestCase):
    def test_source_refresh_updates_the_source_commit(self):
        lock = lock_with()
        calls = []

        def runner(*args):
            calls.append(args)
            return 'ref: refs/heads/main\tHEAD\n' + 'a' * 40 + '\tHEAD\n'

        updated = source.refresh_lock(lock, runner=runner)
        self.assertEqual(updated['piwork']['commit'], 'a' * 40)
        self.assertEqual(updated['piwork']['branch'], 'main')
        self.assertEqual(len(calls), 1)

    def test_official_refresh_is_refused_without_network(self):
        def runner(*args):
            raise AssertionError('official mode must not query the remote')

        with self.assertRaises(source.LockError):
            source.refresh_lock(OFFICIAL, runner=runner)


class VerifySourceTest(unittest.TestCase):
    def make_repo(self, root):
        repo = root / 'piwork'
        repo.mkdir()
        git = ['git', '-c', 'user.name=test', '-c', 'user.email=test@example.invalid']
        subprocess.run(git + ['init', '--quiet'], cwd=repo, check=True)
        (repo / 'file.txt').write_text('content\n')
        subprocess.run(git + ['add', 'file.txt'], cwd=repo, check=True)
        subprocess.run(git + ['commit', '--quiet', '-m', 'initial'], cwd=repo, check=True)
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
        subprocess.run(['git', 'remote', 'add', 'origin', 'https://example.invalid/piwork.git'],
                       cwd=repo, check=True)
        return repo, commit

    def test_clean_copy_is_bound_to_the_actual_build_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, commit = self.make_repo(pathlib.Path(tmp))
            lock = lock_with(commit=commit)
            metadata = source.verify(repo, lock=lock)
            self.assertEqual(metadata['commit'], commit)
            self.assertFalse(metadata['modified'])

    def test_dirty_copy_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, commit = self.make_repo(pathlib.Path(tmp))
            (repo / 'file.txt').write_text('changed\n')
            with self.assertRaises(SystemExit):
                source.verify(repo, lock=lock_with(commit=commit))

    def test_official_source_copy_uses_build_commit_not_release_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, commit = self.make_repo(pathlib.Path(tmp))
            lock = {'piwork': {'url': 'https://example.invalid/piwork.git', 'commit': commit,
                               'branch': 'main', 'resolvedAt': 'now',
                               'inputMode': 'official-release',
                               'release': {'tag': 'v0.0.11', 'releaseCommit': 'c' * 40}}}
            self.assertEqual(source.verify(repo, lock=lock)['commit'], commit)


if __name__ == '__main__':
    unittest.main()
