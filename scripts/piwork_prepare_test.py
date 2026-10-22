import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import piwork_release
import piwork_import_test
import piwork_images_test

TAG = piwork_import_test.TAG
VERSION = piwork_import_test.VERSION
BUILD_COMMIT = piwork_import_test.BUILD_COMMIT
RELEASE_COMMIT = piwork_import_test.RELEASE_COMMIT
SOURCE_INPUT_HASH = piwork_import_test.SOURCE_INPUT_HASH
DESKTOP_UI = piwork_import_test.DESKTOP_UI
CONSOLE_UI = piwork_import_test.CONSOLE_UI


def digest(data):
    return hashlib.sha256(data).hexdigest()


def manifest_record(fixture):
    return {'releaseVersion': VERSION, 'releaseId': fixture.release_id,
            'sourceCommit': BUILD_COMMIT, 'sourceInputHash': SOURCE_INPUT_HASH,
            'desktopUIHash': DESKTOP_UI, 'consoleUIHash': CONSOLE_UI,
            'platform': 'linux/amd64', 'state': 'published',
            'images': {role: {'reference': record['reference'], 'imageId': record['imageId']}
                       for role, record in fixture.image_records.items()}}


def build_payloads(fixture, archive, manifest_bytes=None):
    build = {'releaseVersion': VERSION, 'releaseId': fixture.release_id,
             'sourceCommit': BUILD_COMMIT, 'publicationCommit': RELEASE_COMMIT,
             'sourceModified': False, 'sourceInputHash': SOURCE_INPUT_HASH,
             'desktopUIHash': DESKTOP_UI, 'consoleUIHash': CONSOLE_UI,
             'programs': fixture.program_records, 'images': fixture.image_records,
             'archives': [{'name': 'piwork-linux-amd64-%s.tar.gz' % VERSION,
                           'size': len(archive), 'sha256': digest(archive)}]}
    names = piwork_release.asset_names(VERSION)
    manifest = manifest_bytes if manifest_bytes is not None else json.dumps(manifest_record(fixture)).encode()
    payloads = {'archive': archive,
                'releaseBuild': json.dumps(build).encode(),
                'releaseManifest': manifest}
    payloads['sha256sums'] = ''.join(
        '%s  %s\n' % (digest(payloads[key]), names[key])
        for key in ('releaseBuild', 'releaseManifest', 'archive')).encode()
    assets = [{'name': names[key], 'size': len(payloads[key]),
               'digest': 'sha256:' + digest(payloads[key]),
               'browser_download_url': 'https://github.com/pphboy/piwork/releases/download/%s/%s'
                                       % (TAG, names[key])}
              for key in piwork_release.ASSET_KEYS]
    api = {'tag_name': TAG, 'draft': False, 'prerelease': True,
           'html_url': 'https://github.com/pphboy/piwork/releases/tag/' + TAG,
           'assets': assets}
    return build, manifest, payloads, api


def make_lock(fixture, archive):
    _, _, payloads, api = build_payloads(fixture, archive, fixture.manifest_bytes)
    base = {'version': 1, 'piwork': {'url': piwork_release.UPSTREAM_REPO,
                                     'commit': '0' * 40, 'branch': 'main',
                                     'resolvedAt': '2026-01-01T00:00:00+00:00'}}
    return piwork_release.build_official_lock(base, TAG, api, RELEASE_COMMIT, payloads,
                                             fetched_at='2026-01-01T00:00:00+00:00')


class Combined:
    def __init__(self, docker, programs):
        self.docker = docker
        self.programs = programs

    @property
    def calls(self):
        return self.docker.calls

    def __call__(self, args, **kwargs):
        if args[0] == 'docker':
            return self.docker(args, **kwargs)
        if args[0] == 'go' and args[1] == 'version':
            return piwork_images_test.Result(
                0, 'binary: go1.25.5\n\tdep\tgithub.com/example/mod\tv1.0.0\th1:test\n')
        if args[0] == 'go':
            return piwork_images_test.Result(0, json.dumps({'Error': 'simulated download'}))
        return self.programs(args, **kwargs)


class PrepareTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.fixture = piwork_import_test.Fixture()
        self.fixture.manifest_bytes = json.dumps(manifest_record(self.fixture)).encode()
        archive_path = self.fixture.write(self.root / 'input')
        self.archive = archive_path.read_bytes()
        self.lock = make_lock(self.fixture, self.archive)
        self.urls = {asset['url']: self.archive if key == 'archive'
                     else self.payloads()[key]
                     for key, asset in self.lock['piwork']['release']['assets'].items()}

    def tearDown(self):
        self.temp.cleanup()

    def payloads(self):
        _, _, payloads, _ = build_payloads(self.fixture, self.archive, self.fixture.manifest_bytes)
        return payloads

    def opener(self, url):
        return self.urls[url]

    def docker(self):
        return Combined(piwork_images_test.FakeDocker(self.fixture.release()), self.fixture.runner())

    def test_prepare_publishes_a_complete_verifiable_result(self):
        record = piwork_release.prepare_lock(self.lock, root=self.root,
                                             opener=self.opener, runner=self.docker())
        dist = self.root / 'dist'
        self.assertTrue((dist / 'piwork/bin/piwork-core').is_file())
        self.assertTrue((dist / 'piwork/images.json').is_file())
        self.assertTrue((dist / 'piwork/upstream-release/LICENSE').is_file())
        self.assertTrue((dist / 'guest/images.tar').is_file())
        images = json.loads((dist / 'piwork/images.json').read_text())
        self.assertEqual(set(images), set(piwork_release.DEVICE_IMAGES))
        summary = piwork_release.check_prepared(self.lock, root=self.root)
        self.assertEqual(summary['buildCommit'], BUILD_COMMIT)
        self.assertEqual(summary['tag'], TAG)
        self.assertEqual(record['tag'], TAG)

    def test_failed_preparation_keeps_the_previous_input(self):
        piwork_release.prepare_lock(self.lock, root=self.root,
                                    opener=self.opener, runner=self.docker())
        dist = self.root / 'dist'

        def snapshot():
            return {path.relative_to(dist).as_posix(): digest(path.read_bytes())
                    for path in dist.rglob('*') if path.is_file()}

        before = snapshot()

        class FailingSave(piwork_images_test.FakeDocker):
            def __call__(self, args, **kwargs):
                if args[:2] == ['docker', 'save']:
                    return piwork_images_test.Result(1, '', 'simulated write failure')
                return super().__call__(args, **kwargs)

        with self.assertRaises(piwork_release.ReleaseError):
            piwork_release.prepare_lock(self.lock, root=self.root, opener=self.opener,
                                        runner=Combined(FailingSave(self.fixture.release()),
                                                        self.fixture.runner()))
        self.assertEqual(snapshot(), before)
        piwork_release.check_prepared(self.lock, root=self.root)
        self.assertEqual(list(dist.glob('.piwork-prepare-*')), [])

    def test_failure_during_swap_restores_both_outputs(self):
        piwork_release.prepare_lock(self.lock, root=self.root,
                                    opener=self.opener, runner=self.docker())
        dist = self.root / 'dist'

        def snapshot():
            return {path.relative_to(dist).as_posix(): digest(path.read_bytes())
                    for path in dist.rglob('*') if path.is_file() and 'downloads' not in path.parts}

        before = snapshot()
        with mock.patch.object(piwork_release, 'publish_tree',
                               side_effect=RuntimeError('simulated swap failure')), \
             self.assertRaises(RuntimeError):
            piwork_release.prepare_lock(self.lock, root=self.root,
                                        opener=self.opener, runner=self.docker())
        self.assertEqual(snapshot(), before)
        piwork_release.check_prepared(self.lock, root=self.root)

    def test_check_detects_a_modified_output(self):
        piwork_release.prepare_lock(self.lock, root=self.root,
                                    opener=self.opener, runner=self.docker())
        target = self.root / 'dist/piwork/bin/piwork-cli'
        target.write_bytes(target.read_bytes() + b'tampered')
        with self.assertRaises(piwork_release.ReleaseError):
            piwork_release.check_prepared(self.lock, root=self.root)

    def test_check_detects_a_missing_record(self):
        with self.assertRaises(piwork_release.ReleaseError):
            piwork_release.check_prepared(self.lock, root=self.root)

    def test_prepare_requires_official_mode(self):
        source_lock = {'piwork': {'url': piwork_release.UPSTREAM_REPO, 'commit': '0' * 40}}
        with self.assertRaises(piwork_release.ReleaseError):
            piwork_release.prepare_lock(source_lock, root=self.root,
                                        opener=self.opener, runner=self.docker())

    def test_no_registry_push_is_issued(self):
        fake = self.docker()
        piwork_release.prepare_lock(self.lock, root=self.root, opener=self.opener, runner=fake)
        for call in fake.calls:
            self.assertNotEqual(call[:2], ['docker', 'push'])


if __name__ == '__main__':
    unittest.main()
