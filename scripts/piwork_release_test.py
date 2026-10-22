import copy
import hashlib
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import piwork_release

VERSION = '0.0.11'
TAG = 'v' + VERSION
BUILD_COMMIT = 'a' * 40
RELEASE_COMMIT = 'b' * 40
ARCHIVE = b'official-archive-bytes'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def image(repository, image_id, digest_value, release_id, labels=None):
    return {'reference': 'docker.io/pphboy/%s:%s' % (repository, release_id),
            'imageId': 'sha256:' + image_id * 64, 'platform': 'linux/amd64',
            'protocolLabels': labels or {},
            'digest': 'sha256:' + digest_value * 64,
            'digestReference': 'docker.io/pphboy/%s@sha256:%s' % (repository, digest_value * 64)}


def release_id():
    return VERSION + '-' + BUILD_COMMIT[:12] + '-' + 'd' * 12


def fixture():
    release_id_value = release_id()
    images = {
        'core': image('piwork-core', '1', '2', release_id_value),
        'agent': image('piwork-agentd', '3', '4', release_id_value, {'io.piwork.agent.protocol': 'v2'}),
        'fileHelper': image('piwork-file-helper', '5', '6', release_id_value, {'piwork.file_protocol': '1'}),
        'snapshotHelper': image('piwork-snapshot-helper', '7', '8', release_id_value,
                                {'piwork.snapshot_protocol': '1'}),
    }
    images['packageHelper'] = copy.deepcopy(images['agent'])
    programs = []
    for name in ('piwork-core', 'piwork-cli'):
        programs.append({'program': name, 'version': VERSION, 'commit': BUILD_COMMIT,
                         'modified': False, 'goVersion': 'go1.25.5', 'os': 'linux',
                         'architecture': 'amd64', 'desktopUIHash': 'e' * 64,
                         'consoleUIHash': 'f' * 64})
    archive_name = 'piwork-linux-amd64-%s.tar.gz' % VERSION
    build = {'releaseVersion': VERSION, 'releaseId': release_id_value,
             'sourceCommit': BUILD_COMMIT, 'publicationCommit': RELEASE_COMMIT,
             'sourceModified': False, 'sourceInputHash': 'd' * 64,
             'desktopUIHash': 'e' * 64, 'consoleUIHash': 'f' * 64,
             'programs': programs, 'images': images,
             'archives': [{'name': archive_name, 'size': len(ARCHIVE),
                           'sha256': digest(ARCHIVE)}]}
    manifest = {'releaseVersion': VERSION, 'releaseId': release_id_value,
                'sourceCommit': BUILD_COMMIT, 'sourceInputHash': 'd' * 64,
                'desktopUIHash': 'e' * 64, 'consoleUIHash': 'f' * 64,
                'platform': 'linux/amd64', 'state': 'published',
                'images': {role: {'reference': record['reference'], 'imageId': record['imageId']}
                           for role, record in images.items()}}
    payloads = {'releaseBuild': json.dumps(build).encode(),
                'releaseManifest': json.dumps(manifest).encode(),
                'archive': ARCHIVE}
    sums = ''.join('%s  %s\n' % (digest(payloads[key]), name) for key, name in
                   [('releaseBuild', 'release-build.json'),
                    ('releaseManifest', 'release-manifest.json'),
                    ('archive', archive_name)])
    payloads['sha256sums'] = sums.encode()
    names = piwork_release.asset_names(VERSION)
    api_assets = []
    for key in piwork_release.ASSET_KEYS:
        api_assets.append({'name': names[key], 'size': len(payloads[key]),
                           'digest': 'sha256:' + digest(payloads[key]),
                           'browser_download_url': 'https://github.com/pphboy/piwork/releases/download/%s/%s'
                                                   % (TAG, names[key])})
    api = {'tag_name': TAG, 'draft': False, 'prerelease': True,
           'html_url': 'https://github.com/pphboy/piwork/releases/tag/' + TAG,
           'assets': api_assets}
    lock = {'version': 1, 'piwork': {'url': piwork_release.UPSTREAM_REPO,
                                    'commit': '0' * 40, 'branch': 'main',
                                    'resolvedAt': '2026-10-21T00:00:00+00:00'},
            'go': 'go1.25.5'}
    context = {'build': build, 'manifest': manifest, 'payloads': payloads, 'api': api}
    return lock, context


def resync(context):
    """Re-serialize the metadata payloads after a test mutates a record."""
    payloads = context['payloads']
    payloads['releaseBuild'] = json.dumps(context['build']).encode()
    payloads['releaseManifest'] = json.dumps(context['manifest']).encode()
    names = piwork_release.asset_names(VERSION)
    payloads['sha256sums'] = ''.join(
        '%s  %s\n' % (digest(payloads[key]), name) for key, name in
        [('releaseBuild', names['releaseBuild']),
         ('releaseManifest', names['releaseManifest']),
         ('archive', names['archive'])]).encode()
    for asset in context['api']['assets']:
        for key in piwork_release.ASSET_KEYS:
            if asset['name'] == names[key]:
                asset['size'] = len(payloads[key])
                asset['digest'] = 'sha256:' + digest(payloads[key])


class LockBuildTest(unittest.TestCase):
    def test_consistent_release_is_locked_with_the_build_commit(self):
        lock, context = fixture()
        original = copy.deepcopy(lock)
        updated = piwork_release.build_official_lock(
            lock, TAG, context['api'], RELEASE_COMMIT, context['payloads'],
            fetched_at='2026-10-22T00:00:00+00:00')
        self.assertEqual(lock, original, 'the input lock must not be mutated')
        self.assertEqual(updated['piwork']['inputMode'], 'official-release')
        self.assertEqual(updated['piwork']['commit'], BUILD_COMMIT)
        self.assertNotEqual(updated['piwork']['commit'], RELEASE_COMMIT)
        release = updated['piwork']['release']
        self.assertEqual(release['tag'], TAG)
        self.assertEqual(release['releaseCommit'], RELEASE_COMMIT)
        self.assertEqual(release['tagCommit'], RELEASE_COMMIT)
        self.assertEqual(release['assets']['archive']['sha256'], digest(ARCHIVE))
        self.assertEqual(release['assets']['archive']['size'], len(ARCHIVE))
        self.assertEqual(release['images']['packageHelper'], release['images']['agent'])
        self.assertEqual(release['metadata']['programs'][0]['commit'], BUILD_COMMIT)

    def test_tag_target_must_match_publication_commit(self):
        lock, context = fixture()
        with self.assertRaises(piwork_release.ReleaseError):
            piwork_release.build_official_lock(lock, TAG, context['api'], 'c' * 40,
                                               context['payloads'])

    def test_program_commit_must_be_the_build_commit(self):
        lock, context = fixture()
        context['build']['programs'][0]['commit'] = RELEASE_COMMIT
        resync(context)
        with self.assertRaises(piwork_release.ReleaseError):
            piwork_release.build_official_lock(lock, TAG, context['api'], RELEASE_COMMIT,
                                               context['payloads'])

    def test_ui_hash_mismatch_is_rejected(self):
        lock, context = fixture()
        context['build']['programs'][1]['desktopUIHash'] = '0' * 64
        resync(context)
        with self.assertRaises(piwork_release.ReleaseError):
            piwork_release.build_official_lock(lock, TAG, context['api'], RELEASE_COMMIT,
                                               context['payloads'])

    def test_release_manifest_must_agree_with_build_record(self):
        lock, context = fixture()
        context['manifest']['sourceCommit'] = RELEASE_COMMIT
        resync(context)
        with self.assertRaises(piwork_release.ReleaseError):
            piwork_release.build_official_lock(lock, TAG, context['api'], RELEASE_COMMIT,
                                               context['payloads'])

    def test_archive_digest_must_match_the_locked_bytes(self):
        lock, context = fixture()
        context['build']['archives'][0]['sha256'] = '0' * 64
        resync(context)
        with self.assertRaises(piwork_release.ReleaseError):
            piwork_release.build_official_lock(lock, TAG, context['api'], RELEASE_COMMIT,
                                               context['payloads'])

    def test_sha256sums_must_match_the_locked_bytes(self):
        lock, context = fixture()
        bad = b'0' * 64 + b'  release-build.json\n'
        context['payloads']['sha256sums'] = bad
        for asset in context['api']['assets']:
            if asset['name'] == 'SHA256SUMS':
                asset['size'] = len(bad)
                asset['digest'] = 'sha256:' + digest(bad)
        with self.assertRaises(piwork_release.ReleaseError):
            piwork_release.build_official_lock(lock, TAG, context['api'], RELEASE_COMMIT,
                                               context['payloads'])

    def test_package_helper_must_reuse_the_agent_image(self):
        lock, context = fixture()
        context['build']['images']['packageHelper']['reference'] = \
            'docker.io/pphboy/piwork-package-helper:' + release_id()
        resync(context)
        with self.assertRaises(piwork_release.ReleaseError):
            piwork_release.build_official_lock(lock, TAG, context['api'], RELEASE_COMMIT,
                                               context['payloads'])

    def test_unpublished_release_is_rejected(self):
        lock, context = fixture()
        context['api']['draft'] = True
        with self.assertRaises(piwork_release.ReleaseError):
            piwork_release.build_official_lock(lock, TAG, context['api'], RELEASE_COMMIT,
                                               context['payloads'])

    def test_asset_from_another_repository_is_rejected(self):
        lock, context = fixture()
        context['api']['assets'][0]['browser_download_url'] = \
            'https://example.invalid/piwork-linux-amd64-0.0.11.tar.gz'
        with self.assertRaises(piwork_release.ReleaseError):
            piwork_release.build_official_lock(lock, TAG, context['api'], RELEASE_COMMIT,
                                               context['payloads'])

    def test_lock_for_another_upstream_repository_is_rejected(self):
        lock, context = fixture()
        lock['piwork']['url'] = 'https://example.invalid/fork.git'
        with self.assertRaises(piwork_release.ReleaseError):
            piwork_release.build_official_lock(lock, TAG, context['api'], RELEASE_COMMIT,
                                               context['payloads'])

    def test_release_version_must_match_the_tag(self):
        lock, context = fixture()
        context['build']['releaseVersion'] = '0.0.10'
        resync(context)
        with self.assertRaises(piwork_release.ReleaseError):
            piwork_release.build_official_lock(lock, TAG, context['api'], RELEASE_COMMIT,
                                               context['payloads'])


class TagResolutionTest(unittest.TestCase):
    def test_annotated_tag_prefers_the_dereferenced_commit(self):
        def runner(args, **kwargs):
            class Result:
                returncode = 0
                stdout = ('%s\trefs/tags/%s\n' % ('9' * 40, TAG)
                          + '%s\trefs/tags/%s^{}\n' % (RELEASE_COMMIT, TAG))
                stderr = ''
            return Result()

        self.assertEqual(piwork_release.resolve_tag_commit(TAG, runner=runner), RELEASE_COMMIT)

    def test_missing_tag_is_rejected(self):
        def runner(args, **kwargs):
            class Result:
                returncode = 0
                stdout = ''
                stderr = ''
            return Result()

        with self.assertRaises(piwork_release.ReleaseError):
            piwork_release.resolve_tag_commit(TAG, runner=runner)


if __name__ == '__main__':
    unittest.main()
