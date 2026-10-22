import io
import json
import pathlib
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import piwork_release

VERSION = '0.0.11'
BUILD_COMMIT = 'a' * 40
SOURCE_INPUT_HASH = 'd' * 64
RELEASE_ID = VERSION + '-' + BUILD_COMMIT[:12] + '-' + SOURCE_INPUT_HASH[:12]


def release_record():
    def image(repository, image_id, digest_value, labels):
        return {'reference': 'docker.io/pphboy/%s:%s' % (repository, RELEASE_ID),
                'imageId': 'sha256:' + image_id * 64, 'platform': 'linux/amd64',
                'digest': 'sha256:' + digest_value * 64,
                'digestReference': 'docker.io/pphboy/%s@sha256:%s' % (repository, digest_value * 64),
                'protocolLabels': labels}

    images = {
        'core': image('piwork-core', '1', '2', {}),
        'agent': image('piwork-agentd', '3', '4', {'io.piwork.agent.protocol': 'v2',
                                                   'io.piwork.package-helper.contract': '2'}),
        'fileHelper': image('piwork-file-helper', '5', '6', {'piwork.file_protocol': '1'}),
        'snapshotHelper': image('piwork-snapshot-helper', '7', '8', {'piwork.snapshot_protocol': '1'}),
    }
    images['packageHelper'] = json.loads(json.dumps(images['agent']))
    return {'tag': 'v' + VERSION, 'version': VERSION, 'releaseCommit': 'b' * 40,
            'metadata': {'releaseId': RELEASE_ID, 'releaseVersion': VERSION,
                         'sourceCommit': BUILD_COMMIT, 'sourceInputHash': SOURCE_INPUT_HASH,
                         'desktopUIHash': 'e' * 64, 'consoleUIHash': 'f' * 64,
                         'sourceModified': False},
            'images': images,
            'assets': {'releaseManifest': {'sha256': '0' * 64}}}


class Result:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeDocker:
    """Record local images and answer inspect/pull/tag/save/run like the CLI."""

    def __init__(self, release, helper_version=VERSION, pull_id_override=None):
        self.release = release
        self.calls = []
        self.helper_version = helper_version
        self.pull_id_override = pull_id_override or {}
        self.records = {}
        self.by_reference = {}
        for role in piwork_release.DEVICE_IMAGES:
            record = release['images'][role]
            meta = release['metadata']
            labels = {'org.opencontainers.image.revision': meta['sourceCommit'],
                      'io.piwork.source.input-sha256': meta['sourceInputHash'],
                      'io.piwork.source.modified': 'false',
                      'org.opencontainers.image.version': meta['releaseVersion']}
            if role == 'agent':
                labels['io.piwork.agent.variant'] = 'production'
            labels.update(record['protocolLabels'])
            value = {'Id': record['imageId'], 'Os': 'linux', 'Architecture': 'amd64',
                     'RepoDigests': [record['digestReference']],
                     'Config': {'Labels': labels}}
            self.records[record['digestReference']] = value
            self.by_reference[record['reference']] = value
        self.initial = {key: dict(value) for key, value in self.records.items()}

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        if args[:2] == ['docker', 'image'] and args[2] == 'inspect':
            reference = args[3]
            value = self.records.get(reference) or self.by_reference.get(reference)
            if value is None:
                return Result(1, '', 'No such image: ' + reference)
            return Result(0, json.dumps([value]))
        if args[:2] == ['docker', 'pull']:
            digest_reference = args[-1]
            for role, record in self.release['images'].items():
                if record['digestReference'] == digest_reference:
                    value = dict(self.initial[digest_reference])
                    override = self.pull_id_override.get(role)
                    if override:
                        value['Id'] = override
                    self.records[digest_reference] = value
                    return Result()
            return Result(1, '', 'not found')
        if args[:2] == ['docker', 'tag']:
            source, target = args[2], args[3]
            self.by_reference[target] = self.records[source]
            return Result()
        if args[:2] == ['docker', 'save']:
            archive = pathlib.Path(args[3])
            references = args[4:]
            manifest = [{'RepoTags': [reference],
                         'Config': self.by_reference[reference]['Id'].removeprefix('sha256:') + '.json'}
                        for reference in references]
            with tarfile.open(archive, 'w:') as tar:
                payload = json.dumps(manifest).encode()
                info = tarfile.TarInfo('manifest.json')
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
            return Result()
        if args[:2] == ['docker', 'create']:
            return Result(0, 'container-id')
        if args[:2] == ['docker', 'export']:
            archive = pathlib.Path(args[3])
            with tarfile.open(archive, 'w:') as tar:
                members = {'usr/local/LICENSE': b'node license\n',
                           'var/lib/dpkg/status': b'Package: base-files\nVersion: 12\n'}
                for name, data in members.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
            return Result()
        if args[:2] == ['docker', 'rm']:
            return Result()
        if args[:2] == ['docker', 'run']:
            entrypoint = args[args.index('--entrypoint') + 1]
            program = pathlib.Path(entrypoint).name
            reported = {'program': program, 'version': self.helper_version,
                        'commit': BUILD_COMMIT, 'modified': False,
                        'goVersion': 'go1.25.5', 'os': 'linux', 'architecture': 'amd64'}
            return Result(0, json.dumps(reported))
        return Result(1, '', 'unexpected command: ' + ' '.join(args))


class PrepareImagesTest(unittest.TestCase):
    def test_three_production_images_are_saved_and_core_is_absent(self):
        release = release_record()
        fake = FakeDocker(release)
        with tempfile.TemporaryDirectory() as tmp:
            archive = pathlib.Path(tmp) / 'images.tar'
            result = piwork_release.prepare_images(release, archive, runner=fake)
            self.assertEqual(set(result['images']), set(piwork_release.DEVICE_IMAGES))
            self.assertEqual(result['packageHelper']['reference'], result['images']['agent']['reference'])
            self.assertNotIn('core', result['images'])
            save = next(call for call in fake.calls if call[:2] == ['docker', 'save'])
            self.assertEqual(save[4:], [release['images'][role]['reference']
                                        for role in piwork_release.DEVICE_IMAGES])
            self.assertEqual(archive.stat().st_size, result['archive']['size'])
            self.assertEqual(piwork_release.sha256_file(archive), result['archive']['sha256'])
            for call in fake.calls:
                self.assertNotIn(release['images']['core']['reference'], call)
                self.assertNotIn(release['images']['core']['digestReference'], call)

    def test_wrong_pulled_image_id_is_rejected(self):
        release = release_record()
        fake = FakeDocker(release, pull_id_override={'agent': 'sha256:' + '9' * 64})
        fake.records.pop(release['images']['agent']['digestReference'])
        fake.by_reference.pop(release['images']['agent']['reference'], None)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(piwork_release.ReleaseError):
                piwork_release.prepare_images(release, pathlib.Path(tmp) / 'images.tar', runner=fake)

    def test_wrong_protocol_label_is_rejected(self):
        release = release_record()
        fake = FakeDocker(release)
        record = release['images']['fileHelper']
        fake.records[record['digestReference']]['Config']['Labels']['piwork.file_protocol'] = '2'
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(piwork_release.ReleaseError):
                piwork_release.prepare_images(release, pathlib.Path(tmp) / 'images.tar', runner=fake)

    def test_conflicting_local_tag_is_not_replaced(self):
        release = release_record()
        fake = FakeDocker(release)
        record = release['images']['snapshotHelper']
        fake.by_reference[record['reference']] = dict(fake.records[record['digestReference']],
                                                      Id='sha256:' + '0' * 64)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(piwork_release.ReleaseError):
                piwork_release.prepare_images(release, pathlib.Path(tmp) / 'images.tar', runner=fake)
        self.assertNotIn(['docker', 'tag', record['digestReference'], record['reference']],
                         fake.calls)

    def test_wrong_helper_version_is_rejected(self):
        release = release_record()
        fake = FakeDocker(release, helper_version='0.0.10')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(piwork_release.ReleaseError):
                piwork_release.prepare_images(release, pathlib.Path(tmp) / 'images.tar', runner=fake)

    def test_helper_probes_are_isolated_and_cover_all_four_programs(self):
        release = release_record()
        fake = FakeDocker(release)
        with tempfile.TemporaryDirectory() as tmp:
            result = piwork_release.prepare_images(release, pathlib.Path(tmp) / 'images.tar', runner=fake)
            self.assertEqual(set(result['helperPrograms']), set(piwork_release.IMAGE_PROGRAMS))
            runs = [call for call in fake.calls if call[:2] == ['docker', 'run']]
            self.assertEqual(len(runs), 4)
            for call in runs:
                self.assertIn('--network=none', call)
                self.assertIn('--pull=never', call)
                self.assertIn('--rm', call)

    def test_saved_archive_must_match_the_locked_references(self):
        release = release_record()
        fake = FakeDocker(release)
        original = fake.by_reference

        class Broken(FakeDocker):
            def __call__(self, args, **kwargs):
                if args[:2] == ['docker', 'save']:
                    archive = pathlib.Path(args[3])
                    manifest = [{'RepoTags': [release['images']['agent']['reference']],
                                 'Config': '0' * 64 + '.json'}]
                    with tarfile.open(archive, 'w:') as tar:
                        payload = json.dumps(manifest).encode()
                        info = tarfile.TarInfo('manifest.json')
                        info.size = len(payload)
                        tar.addfile(info, io.BytesIO(payload))
                    return Result()
                return super().__call__(args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(piwork_release.ReleaseError):
                piwork_release.prepare_images(release, pathlib.Path(tmp) / 'images.tar', runner=Broken(release))


if __name__ == '__main__':
    unittest.main()
