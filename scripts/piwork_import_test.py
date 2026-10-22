import hashlib
import io
import json
import pathlib
import struct
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import piwork_release

VERSION = '0.0.11'
TAG = 'v' + VERSION
BUILD_COMMIT = 'a' * 40
RELEASE_COMMIT = 'b' * 40
ROOT_NAME = 'piwork-linux-amd64-' + BUILD_COMMIT[:12]
SOURCE_INPUT_HASH = 'd' * 64
DESKTOP_UI = 'e' * 64
CONSOLE_UI = 'f' * 64


def digest(data):
    return hashlib.sha256(data).hexdigest()


def elf64(machine=62):
    header = bytearray(64)
    header[0:4] = b'\x7fELF'
    header[4] = 2
    header[5] = 1
    header[6] = 1
    struct.pack_into('<H', header, 16, 2)
    struct.pack_into('<H', header, 18, machine)
    struct.pack_into('<Q', header, 32, 0)
    struct.pack_into('<H', header, 54, 56)
    struct.pack_into('<H', header, 56, 0)
    return bytes(header)


def programs():
    return [{'program': name, 'version': VERSION, 'commit': BUILD_COMMIT, 'modified': False,
             'goVersion': 'go1.25.5', 'os': 'linux', 'architecture': 'amd64',
             'desktopUIHash': DESKTOP_UI, 'consoleUIHash': CONSOLE_UI}
            for name in ('piwork-core', 'piwork-cli')]


def images():
    release_id = VERSION + '-' + BUILD_COMMIT[:12] + '-' + SOURCE_INPUT_HASH[:12]

    def record(repository, image_id, digest_value, labels):
        return {'reference': 'docker.io/pphboy/%s:%s' % (repository, release_id),
                'imageId': 'sha256:' + image_id * 64, 'platform': 'linux/amd64',
                'digest': 'sha256:' + digest_value * 64,
                'digestReference': 'docker.io/pphboy/%s@sha256:%s' % (repository, digest_value * 64),
                'protocolLabels': labels}

    result = {
        'core': record('piwork-core', '1', '2', {}),
        'agent': record('piwork-agentd', '3', '4', {'io.piwork.agent.protocol': 'v2'}),
        'fileHelper': record('piwork-file-helper', '5', '6', {'piwork.file_protocol': '1'}),
        'snapshotHelper': record('piwork-snapshot-helper', '7', '8', {'piwork.snapshot_protocol': '1'}),
    }
    result['packageHelper'] = json.loads(json.dumps(result['agent']))
    return result


class Fixture:
    """A minimal but internally consistent official package and release record."""

    def __init__(self):
        self.release_id = VERSION + '-' + BUILD_COMMIT[:12] + '-' + SOURCE_INPUT_HASH[:12]
        self.image_records = images()
        self.program_records = programs()
        self.manifest_bytes = json.dumps({'releaseVersion': VERSION}).encode()
        self.archive = None

    def release(self):
        assets = {key: {'name': key, 'url': 'https://example.invalid/' + key,
                        'size': 1, 'sha256': '0' * 64}
                  for key in piwork_release.ASSET_KEYS}
        assets['releaseManifest']['sha256'] = digest(self.manifest_bytes)
        return {'tag': TAG, 'version': VERSION, 'releaseCommit': RELEASE_COMMIT,
                'metadata': {'sourceCommit': BUILD_COMMIT, 'releaseVersion': VERSION,
                             'releaseId': self.release_id, 'sourceInputHash': SOURCE_INPUT_HASH,
                             'desktopUIHash': DESKTOP_UI, 'consoleUIHash': CONSOLE_UI,
                             'sourceModified': False, 'programs': self.program_records},
                'images': self.image_records,
                'assets': assets}

    def files(self, core_machine=62, help_text=None):
        release = self.release()
        embedded = piwork_release.embedded_images(release).encode()
        release_id = self.release_id
        inputs = {'manifestVersion': 2, 'application': 'unified-linux', 'releaseVersion': VERSION,
                  'sourceCommit': BUILD_COMMIT, 'sourceModified': False,
                  'sourceInputHash': SOURCE_INPUT_HASH, 'desktopUIHash': DESKTOP_UI,
                  'consoleUIHash': CONSOLE_UI, 'platform': 'linux/amd64',
                  'releaseId': release_id,
                  'images': {role: self.image_records[role]['reference']
                             for role in ('core', 'agent', 'fileHelper', 'snapshotHelper')}}
        core = elf64(core_machine) + embedded
        cli = elf64()
        image_lines = []
        for role in ('agent', 'fileHelper', 'snapshotHelper'):
            record = self.image_records[role]
            labels = {'org.opencontainers.image.revision': BUILD_COMMIT,
                      'io.piwork.source.input-sha256': SOURCE_INPUT_HASH,
                      'io.piwork.source.modified': 'false',
                      'org.opencontainers.image.version': VERSION}
            labels.update(record['protocolLabels'])
            image_lines.append({'reference': record['reference'], 'id': record['imageId'],
                                'labels': labels})
        image_programs = [{'program': name, 'version': VERSION, 'commit': BUILD_COMMIT,
                           'modified': False, 'goVersion': 'go1.25.5', 'os': 'linux',
                           'architecture': 'amd64'} for name in piwork_release.IMAGE_PROGRAMS]
        server = {'application': 'unified-linux', 'build': self.program_records[0],
                  'binarySHA256': digest(core), 'optionalPrograms': ['piwork-cli']}
        return {
            'LICENSE': b'license text\n',
            'bin/piwork-core': core,
            'bin/piwork-cli': cli,
            'release-inputs.json': json.dumps(inputs).encode(),
            'release-manifest.json': self.manifest_bytes,
            'server-build.json': json.dumps(server).encode(),
            'programs.ndjson': ('\n'.join(json.dumps(p) for p in self.program_records) + '\n').encode(),
            'images.ndjson': ('\n'.join(json.dumps(r) for r in image_lines) + '\n').encode(),
            'image-programs.ndjson': ('\n'.join(json.dumps(r) for r in image_programs) + '\n').encode(),
            'build-manifest.json': json.dumps({'commit': BUILD_COMMIT}).encode(),
            'go-build-info.txt': b'go build info\n',
        }

    def write(self, directory, **kwargs):
        root = pathlib.Path(directory) / ROOT_NAME
        files = self.files(**kwargs)
        for name, data in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        sums = ''.join('%s  ./%s\n' % (digest(data), name) for name, data in files.items())
        (root / 'SHA256SUMS').write_text(sums)
        archive = pathlib.Path(directory) / 'package.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            tar.add(root, arcname=ROOT_NAME)
        self.archive = archive
        return archive

    def runner(self, program_override=None):
        release = self.release()
        expected = {p['program']: p for p in self.program_records}
        if program_override:
            expected.update(program_override)

        class Result:
            def __init__(self, stdout):
                self.returncode = 0
                self.stdout = stdout
                self.stderr = ''

        def run(args, **kwargs):
            name = pathlib.Path(args[0]).name
            if args[-1] == '--version':
                return Result(json.dumps(expected[name]))
            return Result('  --ui-port PORT\n  --core-port PORT\n  --data-dir DIR\n')

        return run


class ImportTest(unittest.TestCase):
    def test_valid_archive_is_verified_and_staged(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture()
            archive = fixture.write(tmp)
            stage = pathlib.Path(tmp) / 'stage'
            record = piwork_release.stage_import(archive, stage, fixture.release(),
                                                 runner=fixture.runner())
            piwork = stage / 'piwork'
            self.assertTrue((piwork / 'bin/piwork-core').is_file())
            self.assertTrue((piwork / 'bin/piwork-cli').is_file())
            self.assertTrue((piwork / 'metadata.json').is_file())
            self.assertTrue((piwork / 'upstream-release/LICENSE').is_file())
            self.assertTrue((piwork / 'upstream-release/package-SHA256SUMS').is_file())
            self.assertEqual(record['buildCommit'], BUILD_COMMIT)
            self.assertEqual(record['releaseCommit'], RELEASE_COMMIT)
            self.assertEqual(record['checks']['embeddedImages'], 'ok')
            self.assertIn('bin/piwork-core', record['outputs'])
            self.assertNotIn('import.json', record['outputs'])
            for relative, expected in record['outputs'].items():
                path = piwork / relative
                self.assertEqual(path.stat().st_size, expected['size'])
                self.assertEqual(digest(path.read_bytes()), expected['sha256'])

    def test_truncated_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture()
            archive = fixture.write(tmp)
            archive.write_bytes(archive.read_bytes()[:40])
            with self.assertRaises((piwork_release.ReleaseError, tarfile.TarError, EOFError)):
                piwork_release.stage_import(archive, pathlib.Path(tmp) / 'stage',
                                            fixture.release(), runner=fixture.runner())

    def test_path_traversal_member_is_rejected(self):
        self.assert_bad_member('../../evil', tarfile.REGTYPE)

    def test_absolute_member_is_rejected(self):
        self.assert_bad_member('/etc/evil', tarfile.REGTYPE)

    def test_duplicate_member_is_rejected(self):
        self.assert_bad_member(ROOT_NAME + '/LICENSE', tarfile.REGTYPE, duplicate=True)

    def test_link_member_is_rejected(self):
        self.assert_bad_member(ROOT_NAME + '/link', tarfile.SYMTYPE)

    def assert_bad_member(self, name, kind, duplicate=False):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture()
            base = fixture.write(tmp)
            archive = pathlib.Path(tmp) / 'bad.tar.gz'
            with tarfile.open(base) as source, tarfile.open(archive, 'w:gz') as target:
                for member in source:
                    target.addfile(member, source.extractfile(member) if member.isreg() else None)
                info = tarfile.TarInfo(name)
                info.type = kind
                info.linkname = 'target' if kind == tarfile.SYMTYPE else ''
                info.size = 0
                target.addfile(info, io.BytesIO(b''))
                if duplicate:
                    target.addfile(info, io.BytesIO(b''))
            with self.assertRaises(piwork_release.ReleaseError):
                piwork_release.stage_import(archive, pathlib.Path(tmp) / 'stage',
                                            fixture.release(), runner=fixture.runner())

    def test_wrong_platform_elf_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture()
            archive = fixture.write(tmp, core_machine=183)
            with self.assertRaises(piwork_release.ReleaseError):
                piwork_release.stage_import(archive, pathlib.Path(tmp) / 'stage',
                                            fixture.release(), runner=fixture.runner())

    def test_wrong_commit_in_version_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture()
            archive = fixture.write(tmp)
            wrong = {'piwork-core': dict(fixture.program_records[0], commit=RELEASE_COMMIT)}
            with self.assertRaises(piwork_release.ReleaseError):
                piwork_release.stage_import(archive, pathlib.Path(tmp) / 'stage',
                                            fixture.release(),
                                            runner=fixture.runner(program_override=wrong))

    def test_wrong_ui_hash_in_version_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture()
            archive = fixture.write(tmp)
            wrong = {'piwork-cli': dict(fixture.program_records[1], desktopUIHash='0' * 64)}
            with self.assertRaises(piwork_release.ReleaseError):
                piwork_release.stage_import(archive, pathlib.Path(tmp) / 'stage',
                                            fixture.release(),
                                            runner=fixture.runner(program_override=wrong))

    def test_missing_core_flag_in_help_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture()
            archive = fixture.write(tmp)

            class Result:
                returncode = 0
                stdout = '--ui-port --core-port'
                stderr = ''

            def run(args, **kwargs):
                if args[-1] == '--help':
                    return Result()
                return fixture.runner()(args, **kwargs)

            with self.assertRaises(piwork_release.ReleaseError):
                piwork_release.stage_import(archive, pathlib.Path(tmp) / 'stage',
                                            fixture.release(), runner=run)


class PublishTest(unittest.TestCase):
    def test_failure_keeps_the_previous_input_and_writes_no_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture()
            target = pathlib.Path(tmp) / 'piwork'
            good = fixture.write(tmp)
            record = piwork_release.stage_import(good, pathlib.Path(tmp) / 'stage-good',
                                                 fixture.release(), runner=fixture.runner())
            piwork_release.publish_tree(pathlib.Path(tmp) / 'stage-good/piwork', target)
            before = {p.relative_to(target).as_posix(): digest(p.read_bytes())
                      for p in target.rglob('*') if p.is_file()}
            bad = fixture.write(pathlib.Path(tmp) / 'bad', core_machine=183)
            with self.assertRaises(piwork_release.ReleaseError):
                piwork_release.stage_import(bad, pathlib.Path(tmp) / 'stage-bad',
                                            fixture.release(), runner=fixture.runner())
            after = {p.relative_to(target).as_posix(): digest(p.read_bytes())
                     for p in target.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            self.assertTrue((target / 'import.json').is_file())
            self.assertFalse((pathlib.Path(tmp) / 'stage-bad' / 'piwork').exists())

    def test_publish_swaps_in_a_verified_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture()
            target = pathlib.Path(tmp) / 'piwork'
            target.mkdir()
            (target / 'old.txt').write_text('old\n')
            archive = fixture.write(tmp)
            piwork_release.stage_import(archive, pathlib.Path(tmp) / 'stage',
                                        fixture.release(), runner=fixture.runner())
            piwork_release.publish_tree(pathlib.Path(tmp) / 'stage/piwork', target)
            self.assertFalse((target / 'old.txt').exists())
            self.assertTrue((target / 'import.json').is_file())
            self.assertFalse((pathlib.Path(tmp) / 'piwork.previous').exists())


class DownloadCacheTest(unittest.TestCase):
    def test_matching_cache_entry_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = pathlib.Path(tmp)
            data = b'asset-bytes'
            (cache / 'asset').write_bytes(data)

            def opener(url):
                raise AssertionError('cache hit must not download')

            path = piwork_release.download_cached('https://example.invalid/asset', 'asset',
                                                  len(data), digest(data), cache, opener=opener)
            self.assertEqual(path.read_bytes(), data)

    def test_corrupt_cache_entry_is_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = pathlib.Path(tmp)
            (cache / 'asset').write_bytes(b'corrupt')
            data = b'asset-bytes'
            path = piwork_release.download_cached('https://example.invalid/asset', 'asset',
                                                  len(data), digest(data), cache,
                                                  opener=lambda url: data)
            self.assertEqual(path.read_bytes(), data)

    def test_wrong_download_is_rejected_without_publishing(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = pathlib.Path(tmp)
            with self.assertRaises(piwork_release.ReleaseError):
                piwork_release.download_cached('https://example.invalid/asset', 'asset',
                                               4, digest(b'good'), cache,
                                               opener=lambda url: b'evil')
            self.assertFalse((cache / 'asset').exists())
            self.assertEqual(list(cache.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
