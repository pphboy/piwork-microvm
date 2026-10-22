#!/usr/bin/env python3
"""Lock, import and check the official Piwork release input.

Only `lock --tag <tag>` changes the locked release input. Normal builds consume
an existing lock and never resolve `latest` or refresh a tag implicitly.
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

import piwork_licenses

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / 'build.lock.json'
UPSTREAM_REPO = 'https://github.com/pphboy/piwork.git'
API_ROOT = 'https://api.github.com/repos/pphboy/piwork'
ASSET_KEYS = ('archive', 'releaseBuild', 'releaseManifest', 'sha256sums')
IMAGE_ROLES = ('core', 'agent', 'fileHelper', 'snapshotHelper', 'packageHelper')
DEVICE_IMAGES = ('agent', 'fileHelper', 'snapshotHelper')
IMAGE_PROGRAMS = ('piwork-service-mcp', 'piwork-package-helper', 'piwork-file-helper', 'piwork-snapshot-helper')
PACKAGE_REQUIRED = ('LICENSE', 'bin/piwork-core', 'bin/piwork-cli',
                    'release-inputs.json', 'release-manifest.json', 'server-build.json',
                    'programs.ndjson', 'images.ndjson', 'image-programs.ndjson',
                    'build-manifest.json')
CORE_FLAGS = ('--ui-port', '--core-port', '--data-dir')
MAX_MEMBER_SIZE = 512 * 1024 * 1024
MAX_TOTAL_SIZE = 2 * 1024 * 1024 * 1024
SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
COMMIT_RE = re.compile(r'^[0-9a-f]{40}$')


class ReleaseError(Exception):
    """The official release record is missing, inconsistent or unverifiable."""


def require(condition, message):
    if not condition:
        raise ReleaseError(message)


def read_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, json.JSONDecodeError) as err:
        raise ReleaseError('cannot read %s: %s' % (path, err))


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    with pathlib.Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write_json_atomic(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + '.', suffix='.part', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    except BaseException:
        pathlib.Path(temp).unlink(missing_ok=True)
        raise


def parse_sha256sums(text):
    """Parse the standard `sha256  name` listing; reject malformed lines."""
    entries = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        require(len(parts) == 2, 'malformed SHA256SUMS line: %r' % line)
        digest, name = parts[0].lower(), parts[1].lstrip('*')
        require(SHA256_RE.match(digest) is not None, 'malformed SHA256SUMS digest: %r' % line)
        require(name not in entries, 'duplicate SHA256SUMS entry: ' + name)
        entries[name] = digest
    return entries


def asset_names(version):
    return {
        'archive': 'piwork-linux-amd64-%s.tar.gz' % version,
        'releaseBuild': 'release-build.json',
        'releaseManifest': 'release-manifest.json',
        'sha256sums': 'SHA256SUMS',
    }


def verify_image_identity(role, record, release_id):
    require(isinstance(record, dict), 'image record %s is missing' % role)
    require(record.get('platform') == 'linux/amd64', 'image %s is not linux/amd64' % role)
    reference = record.get('reference', '')
    require(reference.endswith(':' + release_id), 'image %s reference is not tagged %s' % (role, release_id))
    require(SHA256_RE.match(record.get('imageId', '').removeprefix('sha256:')) is not None,
            'image %s imageId is malformed' % role)
    require(SHA256_RE.match(record.get('digest', '').removeprefix('sha256:')) is not None,
            'image %s digest is malformed' % role)
    require(record.get('digestReference', '').endswith(record['digest']),
            'image %s digestReference does not carry its digest' % role)


def validate_release_metadata(release, tag, tag_commit, payloads, names):
    """Cross-check the release API, tag, program records and asset bytes."""
    version = tag[1:] if tag.startswith('v') else tag
    require(release.get('tag_name') == tag, 'release tag_name does not match ' + tag)
    require(release.get('draft') is False, 'release is still a draft')
    require(str(release.get('html_url', '')).startswith(
        'https://github.com/pphboy/piwork/releases/tag/'), 'release does not come from the official repository')
    assets = {asset.get('name'): asset for asset in release.get('assets', [])}
    for asset in assets.values():
        require(str(asset.get('browser_download_url', '')).startswith(
            'https://github.com/pphboy/piwork/releases/download/%s/' % tag),
            'asset does not come from the official release: %s' % asset.get('name'))
    build = json.loads(payloads['releaseBuild'].decode('utf-8-sig'))
    manifest = json.loads(payloads['releaseManifest'].decode('utf-8-sig'))
    sums = parse_sha256sums(payloads['sha256sums'].decode('utf-8-sig'))

    for key, name in names.items():
        asset = assets.get(name)
        require(asset is not None, 'release asset is missing: ' + name)
        digest = sha256_bytes(payloads[key])
        require(asset.get('size') == len(payloads[key]), 'asset size differs for ' + name)
        require(asset.get('digest') == 'sha256:' + digest, 'asset digest differs for ' + name)

    # Since 0.0.12 the official v2 build asset carries nativePrograms and
    # tag references; complete registry identities live in release-manifest.
    # Normalize only our in-memory view. Keep the downloaded bytes untouched.
    native_v2 = build.get('manifestVersion') == 2 and 'nativePrograms' in build
    program_sha256 = {}
    if native_v2:
        require(manifest.get('manifestVersion') == 2, 'native v2 requires a v2 release-manifest')
        require(manifest.get('sourceModified') is False, 'release-manifest marks source modified')
        native = build['nativePrograms']
        require(isinstance(native, dict), 'nativePrograms is not an object')
        programs = []
        for name in ('piwork-core', 'piwork-cli'):
            record = native.get(name)
            require(isinstance(record, dict) and isinstance(record.get('build'), dict),
                    'native program record is missing: ' + name)
            require(record['build'].get('program') == name, 'native program name differs: ' + name)
            require(SHA256_RE.match(record.get('sha256', '')) is not None,
                    'native program sha256 is malformed: ' + name)
            programs.append(record['build'])
            program_sha256[name] = record['sha256']
        images = manifest.get('images', {})
        for role in ('core',) + DEVICE_IMAGES:
            require(isinstance(images.get(role), dict), 'release-manifest image is missing: ' + role)
            require(build.get('images', {}).get(role) == images[role].get('reference'),
                    'release-build image reference differs: ' + role)
        build = dict(build, programs=programs, images=images)
        # The release asset no longer states a separate publication commit.
        # Resolve the official git tag independently, never infer it from main.
        if 'publicationCommit' not in build:
            build['publicationCommit'] = tag_commit

    require(build.get('releaseVersion') == version, 'release-build version differs from tag')
    release_id = build.get('releaseId', '')
    require(release_id.startswith(version + '-'), 'releaseId does not carry the release version')
    source_commit = build.get('sourceCommit', '')
    publication_commit = build.get('publicationCommit', '')
    require(COMMIT_RE.match(source_commit) is not None, 'sourceCommit is not a full commit')
    require(COMMIT_RE.match(publication_commit) is not None, 'publicationCommit is not a full commit')
    require(publication_commit == tag_commit, 'tag target differs from publicationCommit')
    require(build.get('sourceModified') is False, 'release was built from a modified source tree')
    require(SHA256_RE.match(build.get('sourceInputHash', '')) is not None, 'sourceInputHash is malformed')

    for field in ('desktopUIHash', 'consoleUIHash'):
        require(SHA256_RE.match(build.get(field, '')) is not None, field + ' is malformed')

    programs = {p.get('program'): p for p in build.get('programs', [])}
    for name in ('piwork-core', 'piwork-cli'):
        program = programs.get(name)
        require(program is not None, 'program record is missing: ' + name)
        require(program.get('version') == version, name + ' version differs from tag')
        require(program.get('commit') == source_commit, name + ' commit is not the actual build commit')
        require(program.get('modified') is False, name + ' is marked modified')
        require((program.get('os'), program.get('architecture')) == ('linux', 'amd64'),
                name + ' is not a linux/amd64 program')
        for field in ('desktopUIHash', 'consoleUIHash'):
            require(program.get(field) == build.get(field), name + ' ' + field + ' differs')

    require(manifest.get('releaseVersion') == version, 'release-manifest version differs from tag')
    require(manifest.get('releaseId') == release_id, 'release-manifest releaseId differs')
    require(manifest.get('sourceCommit') == source_commit, 'release-manifest sourceCommit differs')
    require(manifest.get('sourceInputHash') == build.get('sourceInputHash'), 'release-manifest input hash differs')
    for field in ('desktopUIHash', 'consoleUIHash'):
        require(manifest.get(field) == build.get(field), 'release-manifest ' + field + ' differs')
    require(manifest.get('platform') == 'linux/amd64', 'release-manifest platform differs')
    require(manifest.get('state') == 'published', 'release-manifest is not published')

    images = build.get('images')
    require(isinstance(images, dict), 'release-build images record is missing')
    for role in IMAGE_ROLES:
        verify_image_identity(role, images.get(role), release_id)
    for role in ('agent', 'fileHelper', 'snapshotHelper', 'packageHelper'):
        require(images[role]['reference'] == manifest.get('images', {}).get(role, {}).get('reference'),
                'image reference differs between release records: ' + role)
        require(images[role]['imageId'] == manifest['images'][role].get('imageId'),
                'imageId differs between release records: ' + role)
    for field in ('reference', 'imageId', 'digest'):
        require(images['packageHelper'][field] == images['agent'][field],
                'package-helper must reuse the Agent image (' + field + ')')

    if not native_v2:
        archives = {entry.get('name'): entry for entry in build.get('archives', [])}
        archive = archives.get(names['archive'])
        require(archive is not None, 'release-build does not describe ' + names['archive'])
        archive_digest = sha256_bytes(payloads['archive'])
        require(archive.get('size') == len(payloads['archive']), 'archive size differs from release-build')
        require(archive.get('sha256') == archive_digest, 'archive sha256 differs from release-build')
    # Both formats also bind all external bytes to the GitHub asset digest and
    # SHA256SUMS; native v2 additionally locks each actual executable digest.

    for key in ('releaseBuild', 'releaseManifest', 'archive'):
        require(sums.get(names[key]) == sha256_bytes(payloads[key]), 'SHA256SUMS differs for ' + names[key])

    return {'version': version, 'releaseId': release_id, 'build': build,
            'manifest': manifest, 'images': images, 'sums': sums,
            'programSHA256': program_sha256, 'metadataFormat': 'native-v2' if native_v2 else 'legacy'}


def build_official_lock(lock, tag, release, tag_commit, payloads, fetched_at=None):
    """Return a new lock binding the official release; never mutates `lock`."""
    version = tag[1:] if tag.startswith('v') else tag
    names = asset_names(version)
    require(lock.get('piwork', {}).get('url') == UPSTREAM_REPO,
            'build.lock.json does not pin the official Piwork repository')
    checked = validate_release_metadata(release, tag, tag_commit, payloads, names)
    assets = {a.get('name'): a for a in release.get('assets', [])}
    updated = json.loads(json.dumps(lock))
    piwork = updated.setdefault('piwork', {})
    piwork['inputMode'] = 'official-release'
    piwork['commit'] = checked['build']['sourceCommit']
    piwork['resolvedAt'] = fetched_at or datetime.datetime.now(datetime.timezone.utc).isoformat()
    piwork['release'] = {
        'tag': tag,
        'version': checked['version'],
        'prerelease': bool(release.get('prerelease')),
        'releaseCommit': checked['build']['publicationCommit'],
        'tagCommit': tag_commit,
        'resolvedAt': piwork['resolvedAt'],
        'assets': {
            key: {'name': names[key],
                  'url': assets[names[key]]['browser_download_url'],
                  'size': len(payloads[key]),
                  'sha256': sha256_bytes(payloads[key])}
            for key in ASSET_KEYS
        },
        'metadata': {
            'releaseId': checked['releaseId'],
            'releaseVersion': checked['version'],
            'sourceCommit': checked['build']['sourceCommit'],
            'publicationCommit': checked['build']['publicationCommit'],
            'sourceInputHash': checked['build']['sourceInputHash'],
            'desktopUIHash': checked['build']['desktopUIHash'],
            'consoleUIHash': checked['build']['consoleUIHash'],
            'sourceModified': checked['build']['sourceModified'],
            'programs': checked['build']['programs'],
            'programSHA256': checked['programSHA256'],
            'metadataFormat': checked['metadataFormat'],
            'publicationCommitBasis': 'official-git-tag' if 'publicationCommit' not in
                json.loads(payloads['releaseBuild']) else 'release-build',
        },
        'images': checked['images'],
    }
    return updated


def resolve_tag_commit(tag, runner=None):
    """Resolve an annotated tag to the commit it points at."""
    runner = runner or subprocess.run
    result = runner(['git', 'ls-remote', UPSTREAM_REPO, 'refs/tags/' + tag, 'refs/tags/' + tag + '^{}'],
                    capture_output=True, text=True)
    if result.returncode != 0:
        raise ReleaseError('cannot resolve tag %s: %s' % (tag, result.stderr.strip()))
    lines = {}
    for line in result.stdout.splitlines():
        commit, _, ref = line.partition('\t')
        lines[ref.strip()] = commit.strip()
    commit = lines.get('refs/tags/' + tag + '^{}') or lines.get('refs/tags/' + tag)
    require(commit is not None, 'tag %s does not exist upstream' % tag)
    require(COMMIT_RE.match(commit) is not None, 'tag %s did not resolve to a full commit' % tag)
    return commit


def download(url, timeout=300):
    request = urllib.request.Request(url, headers={'User-Agent': 'piwork-microvm-build'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_release(tag, opener=download, cache_dir=None):
    """Download the locked assets for `tag` and return the lock-ready payloads."""
    api = json.loads(opener(API_ROOT + '/releases/tags/' + tag).decode('utf-8'))
    version = tag[1:] if tag.startswith('v') else tag
    names = asset_names(version)
    assets = {a.get('name'): a for a in api.get('assets', [])}
    payloads = {}
    for key, name in names.items():
        require(name in assets, 'release asset is missing: ' + name)
        asset = assets[name]
        digest = str(asset.get('digest', '')).removeprefix('sha256:')
        if cache_dir and SHA256_RE.match(digest):
            payloads[key] = download_cached(asset['browser_download_url'], name, asset['size'],
                                            digest, cache_dir, opener=opener).read_bytes()
        else:
            payloads[key] = opener(asset['browser_download_url'])
    return api, resolve_tag_commit(tag), payloads


def download_cached(url, name, size, digest, cache_dir, opener=download):
    """Download once, keyed by the locked digest; never reuse a mismatched cache entry."""
    cache_dir = pathlib.Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / name
    if target.is_file() and target.stat().st_size == size and sha256_file(target) == digest:
        return target
    data = opener(url)
    require(len(data) == size, 'downloaded size differs for ' + name)
    require(sha256_bytes(data) == digest, 'downloaded digest differs for ' + name)
    part = target.with_name(target.name + '.part')
    try:
        part.write_bytes(data)
        os.replace(part, target)
    finally:
        part.unlink(missing_ok=True)
    return target


def package_root(release):
    commit = release['metadata']['sourceCommit']
    return 'piwork-linux-amd64-' + commit[:12]


def safe_extract(archive, dest, expected_root):
    """Extract only regular files/directories under one expected root.

    Rejects absolute or escaping paths, duplicate targets, links and special
    files before anything is written.
    """
    members, seen, total = [], set(), 0
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar:
            name = member.name
            require(isinstance(name, str) and name, 'archive member has no name')
            require(not name.startswith('/') and '\\' not in name,
                    'archive member has an absolute or non-portable path: %r' % name)
            parts = [part for part in name.split('/') if part not in ('', '.')]
            require(parts and '..' not in parts, 'archive member escapes the extraction root: %r' % name)
            require(parts[0] == expected_root,
                    'archive member is outside %s: %r' % (expected_root, name))
            require(member.type in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE),
                    'archive member is not a regular file or directory: %r' % name)
            require(member.mode & 0o7000 == 0, 'archive member has setuid/setgid/sticky bits: %r' % name)
            normalized = '/'.join(parts)
            require(normalized not in seen, 'archive member is duplicated: %r' % normalized)
            seen.add(normalized)
            if member.isreg():
                require(0 <= member.size <= MAX_MEMBER_SIZE,
                        'archive member is too large: %r' % normalized)
                total += member.size
                require(total <= MAX_TOTAL_SIZE, 'archive expands beyond the import limit')
            members.append(member)
    require(members, 'archive is empty')
    dest = pathlib.Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, 'r:gz') as tar:
        tar.extractall(dest, members=members, filter='data')
    return dest / expected_root


def elf_identity(path):
    """Statically linked Linux amd64 ELF with no interpreter or dynamic section."""
    data = pathlib.Path(path).read_bytes()
    require(data[:4] == b'\x7fELF', '%s is not an ELF file' % path)
    require(data[4] == 2 and data[5] == 1, '%s is not a 64-bit little-endian ELF' % path)
    elf_type, machine = struct.unpack_from('<HH', data, 16)
    require(elf_type in (2, 3), '%s is not an executable ELF' % path)
    require(machine == 62, '%s is not an x86-64 ELF' % path)
    phoff = struct.unpack_from('<Q', data, 32)[0]
    phentsize = struct.unpack_from('<H', data, 54)[0]
    phnum = struct.unpack_from('<H', data, 56)[0]
    require(phentsize >= 56, '%s has malformed program headers' % path)
    for index in range(phnum):
        offset = phoff + index * phentsize
        require(offset + 4 <= len(data), '%s has truncated program headers' % path)
        p_type = struct.unpack_from('<I', data, offset)[0]
        require(p_type != 3, '%s requests an ELF interpreter' % path)
        require(p_type != 2, '%s has a dynamic section' % path)
    return {'machine': 'x86-64', 'type': elf_type, 'size': len(data)}


def clean_environment(home):
    return {'PATH': '/usr/bin:/bin', 'HOME': str(home), 'TMPDIR': str(home),
            'XDG_CONFIG_HOME': str(home), 'XDG_DATA_HOME': str(home),
            'XDG_CACHE_HOME': str(home), 'LC_ALL': 'C'}


def run_program(path, argument, runner=subprocess.run):
    with tempfile.TemporaryDirectory() as home:
        result = runner([str(path), argument], capture_output=True, text=True,
                        timeout=120, env=clean_environment(home), cwd=home)
    require(result.returncode == 0, '%s %s failed: %s'
            % (path, argument, (result.stderr or '').strip()))
    return result


def program_identity(path, expected, runner=subprocess.run):
    """Run the program's own `--version` and compare every identity field."""
    result = run_program(path, '--version', runner=runner)
    try:
        reported = json.loads(result.stdout)
    except json.JSONDecodeError as err:
        raise ReleaseError('%s --version did not report JSON: %s' % (path, err))
    require(isinstance(reported, dict), '%s --version did not report an object' % path)
    for field in ('program', 'version', 'commit', 'modified', 'os', 'architecture',
                  'goVersion', 'desktopUIHash', 'consoleUIHash'):
        require(reported.get(field) == expected.get(field),
                '%s reports %s=%r, lock says %r'
                % (path, field, reported.get(field), expected.get(field)))
    return reported


def embedded_images(release):
    """The exact encoded image reference set the official Core carries."""
    values = {role: release['images'][role]['reference']
              for role in ('agent', 'packageHelper', 'fileHelper', 'snapshotHelper')}
    return base64.b64encode(json.dumps(values, separators=(',', ':')).encode()).decode().rstrip('=')


def verify_embedded_images(core, release):
    encoded = embedded_images(release).encode()
    require(encoded in pathlib.Path(core).read_bytes(),
            'Core does not embed the locked production image references')


def parse_ndjson(path):
    records = []
    for line in pathlib.Path(path).read_text(encoding='utf-8').splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def verify_package_sums(root, sums_path):
    entries = parse_sha256sums(pathlib.Path(sums_path).read_text(encoding='utf-8'))
    require(entries, 'package SHA256SUMS is empty')
    for name, digest in entries.items():
        relative = name[2:] if name.startswith('./') else name
        require(relative and '..' not in relative.split('/'), 'package checksum escapes the root: ' + name)
        target = pathlib.Path(root) / relative
        require(target.is_file(), 'package checksum lists a missing file: ' + relative)
        require(sha256_file(target) == digest, 'package checksum differs: ' + relative)
    for required in PACKAGE_REQUIRED:
        require(required in {name[2:] if name.startswith('./') else name for name in entries},
                'package SHA256SUMS does not list ' + required)
    return len(entries)


def verify_package(root, release, runner=subprocess.run):
    root = pathlib.Path(root)
    require((root / 'SHA256SUMS').is_file(), 'official package is missing SHA256SUMS')
    for name in PACKAGE_REQUIRED:
        require((root / name).is_file(), 'official package is missing ' + name)
    summed = verify_package_sums(root, root / 'SHA256SUMS')
    meta = release['metadata']
    build_commit = meta['sourceCommit']
    version = meta['releaseVersion']

    require(sha256_file(root / 'release-manifest.json') == release['assets']['releaseManifest']['sha256'],
            'packaged release-manifest.json differs from the locked asset')

    inputs = read_json(root / 'release-inputs.json')
    for field, expected in (('sourceCommit', build_commit), ('releaseVersion', version),
                            ('sourceInputHash', meta['sourceInputHash']),
                            ('desktopUIHash', meta['desktopUIHash']),
                            ('consoleUIHash', meta['consoleUIHash']),
                            ('releaseId', meta['releaseId'])):
        require(inputs.get(field) == expected, 'release-inputs %s differs' % field)
    require(inputs.get('sourceModified') is False, 'release-inputs marks the source modified')
    require(inputs.get('platform') == 'linux/amd64', 'release-inputs platform differs')
    for role in ('core',) + DEVICE_IMAGES:
        require(inputs.get('images', {}).get(role) == release['images'][role]['reference'],
                'release-inputs image reference differs: ' + role)

    core_record = next((p for p in meta['programs'] if p.get('program') == 'piwork-core'), None)
    require(core_record is not None, 'lock has no piwork-core program record')
    server = read_json(root / 'server-build.json')
    require(server.get('build') == core_record, 'server-build identity differs from the lock')
    require(server.get('binarySHA256') == sha256_file(root / 'bin/piwork-core'),
            'server-build binarySHA256 differs from the packaged Core')

    programs = parse_ndjson(root / 'programs.ndjson')
    require({p.get('program'): p for p in programs} ==
            {p.get('program'): p for p in meta['programs']},
            'programs.ndjson differs from the lock')

    image_records = parse_ndjson(root / 'images.ndjson')
    by_reference = {record.get('reference'): record for record in image_records}
    for role in DEVICE_IMAGES:
        expected = release['images'][role]
        record = by_reference.get(expected['reference'])
        require(record is not None, 'images.ndjson is missing ' + role)
        require(record.get('id') == expected['imageId'], 'images.ndjson image ID differs: ' + role)
        labels = record.get('labels', {})
        for key, value in (('org.opencontainers.image.revision', build_commit),
                           ('io.piwork.source.input-sha256', meta['sourceInputHash']),
                           ('io.piwork.source.modified', 'false'),
                           ('org.opencontainers.image.version', version)):
            require(labels.get(key) == value, 'images.ndjson label differs for %s: %s' % (role, key))
        for key, value in expected.get('protocolLabels', {}).items():
            require(labels.get(key) == value, 'images.ndjson protocol label differs for %s: %s' % (role, key))

    image_programs = {p.get('program'): p for p in parse_ndjson(root / 'image-programs.ndjson')}
    require(set(image_programs) == set(IMAGE_PROGRAMS),
            'image-programs.ndjson does not list the expected helper programs')
    for name, record in image_programs.items():
        require((record.get('version'), record.get('commit'), record.get('modified'),
                 record.get('os'), record.get('architecture')) ==
                (version, build_commit, False, 'linux', 'amd64'),
                'image program identity differs: ' + name)

    build_manifest = read_json(root / 'build-manifest.json')
    require(build_manifest.get('commit') == build_commit, 'build-manifest commit differs')

    identities = {}
    for name in ('piwork-core', 'piwork-cli'):
        expected = next((p for p in meta['programs'] if p.get('program') == name), None)
        require(expected is not None, 'lock has no program record for ' + name)
        path = root / 'bin' / name
        expected_sha = meta.get('programSHA256', {}).get(name)
        if expected_sha:
            require(sha256_file(path) == expected_sha, 'native program sha256 differs: ' + name)
        identities[name] = elf_identity(path)
        program_identity(path, expected, runner=runner)
    core_help = run_program(root / 'bin/piwork-core', '--help', runner=runner)
    for flag in CORE_FLAGS:
        require(flag in core_help.stdout, 'Core help does not expose ' + flag)
    verify_embedded_images(root / 'bin/piwork-core', release)
    return {'packageChecksums': summed, 'programs': sorted(identities),
            'programIdentity': 'ok', 'embeddedImages': 'ok'}


def tree_records(directory, prefix=''):
    records = {}
    for path in sorted(pathlib.Path(directory).rglob('*')):
        if path.is_file():
            relative = (prefix + path.relative_to(directory).as_posix()).strip('/')
            records[relative] = {'size': path.stat().st_size, 'sha256': sha256_file(path)}
    return records


def stage_import(archive, stage, release, runner=subprocess.run):
    """Verify the archive completely, then build a staging tree from it."""
    stage = pathlib.Path(stage)
    require(not stage.exists(), 'staging directory already exists: ' + str(stage))
    stage.mkdir(parents=True)
    root = safe_extract(archive, stage / 'unpack', package_root(release))
    checks = verify_package(root, release, runner=runner)

    piwork = stage / 'piwork'
    (piwork / 'bin').mkdir(parents=True)
    for name in ('piwork-core', 'piwork-cli'):
        shutil.copyfile(root / 'bin' / name, piwork / 'bin' / name)
        (piwork / 'bin' / name).chmod(0o755)
    upstream = piwork / 'upstream-release'
    upstream.mkdir()
    for name in ('LICENSE', 'release-inputs.json', 'release-manifest.json', 'server-build.json',
                 'programs.ndjson', 'images.ndjson', 'image-programs.ndjson',
                 'build-manifest.json', 'go-build-info.txt'):
        source = root / name
        if source.is_file():
            shutil.copyfile(source, upstream / name)
    shutil.copyfile(root / 'SHA256SUMS', upstream / 'package-SHA256SUMS')
    metadata = read_json(root / 'release-inputs.json')
    metadata['importedFrom'] = {
        'inputMode': 'official-release',
        'tag': release['tag'],
        'releaseCommit': release['releaseCommit'],
        'archive': release['assets']['archive'],
    }
    write_json_atomic(piwork / 'metadata.json', metadata)
    write_json_atomic(piwork / 'build-mode.json', {
        'inputMode': 'official-release', 'tag': release['tag'],
        'commit': release['metadata']['sourceCommit']})
    record = {
        'recordVersion': 1,
        'inputMode': 'official-release',
        'tag': release['tag'],
        'version': release['version'],
        'buildCommit': release['metadata']['sourceCommit'],
        'releaseCommit': release['releaseCommit'],
        'assets': {key: release['assets'][key] for key in ASSET_KEYS},
        'metadata': release['metadata'],
        'images': release['images'],
        'checks': checks,
        'outputs': tree_records(piwork),
    }
    write_json_atomic(piwork / 'import.json', record)
    return record


def publish_tree(staging, target):
    """Swap a fully verified staging tree into place; the previous tree survives failure."""
    staging = pathlib.Path(staging)
    target = pathlib.Path(target)
    require(staging.is_dir(), 'staging tree is missing: ' + str(staging))
    backup = target.with_name(target.name + '.previous')
    if backup.exists():
        shutil.rmtree(backup)
    moved_previous = False
    if target.exists():
        os.rename(target, backup)
        moved_previous = True
    try:
        os.rename(staging, target)
    except BaseException:
        if moved_previous:
            os.rename(backup, target)
        raise
    if moved_previous:
        shutil.rmtree(backup, ignore_errors=True)


def load_lock(path=LOCK_PATH):
    return read_json(path)


def docker(args, runner=subprocess.run, **kwargs):
    result = runner(['docker', *[str(arg) for arg in args]], capture_output=True, text=True, **kwargs)
    require(result.returncode == 0, 'docker %s failed: %s'
            % (' '.join(str(arg) for arg in args), (result.stderr or '').strip()))
    return result.stdout.strip()


def inspect_image(reference, runner=subprocess.run):
    raw = docker(['image', 'inspect', reference], runner=runner)
    try:
        records = json.loads(raw)
    except json.JSONDecodeError as err:
        raise ReleaseError('docker image inspect did not return JSON: %s' % err)
    require(isinstance(records, list) and len(records) == 1,
            'docker image inspect returned an unexpected record for ' + reference)
    return records[0]


def verify_image_metadata(role, record, release, actual):
    """Check the pulled image against the locked digest, ID, platform and labels."""
    meta = release['metadata']
    require(actual.get('Id') == record['imageId'],
            'image %s ID is %r, lock says %r' % (role, actual.get('Id'), record['imageId']))
    require((actual.get('Os'), actual.get('Architecture')) == ('linux', 'amd64'),
            'image %s is not linux/amd64' % role)
    require(normalize_reference(record['digestReference']) in
            {normalize_reference(reference) for reference in actual.get('RepoDigests') or []},
            'image %s does not carry the locked digest reference' % role)
    labels = (actual.get('Config') or {}).get('Labels') or {}
    expected = {'org.opencontainers.image.revision': meta['sourceCommit'],
                'io.piwork.source.input-sha256': meta['sourceInputHash'],
                'io.piwork.source.modified': 'false',
                'org.opencontainers.image.version': meta['releaseVersion']}
    if role == 'agent':
        expected['io.piwork.agent.variant'] = 'production'
    expected.update(record.get('protocolLabels', {}))
    for key, value in expected.items():
        require(labels.get(key) == value,
                'image %s label %s is %r, expected %r' % (role, key, labels.get(key), value))


def ensure_image(role, record, release, runner=subprocess.run):
    """Pull by digest, verify, and keep the official tag without clobbering a conflict."""
    digest_reference = record['digestReference']
    try:
        inspect_image(digest_reference, runner=runner)
    except ReleaseError:
        docker(['pull', '--platform', 'linux/amd64', digest_reference], runner=runner)
    verify_image_metadata(role, record, release, inspect_image(digest_reference, runner=runner))
    reference = record['reference']
    try:
        tagged = inspect_image(reference, runner=runner)
    except ReleaseError:
        docker(['tag', digest_reference, reference], runner=runner)
        tagged = inspect_image(reference, runner=runner)
    require(tagged.get('Id') == record['imageId'],
            'local tag %s already points at another image; refusing to replace it' % reference)
    return {'role': role, 'reference': reference, 'id': record['imageId'],
            'digestReference': digest_reference}


def probe_helper_versions(release, runner=subprocess.run):
    """Ask each shipped helper for its identity in an isolated, networkless container."""
    meta = release['metadata']
    images = release['images']
    targets = [('piwork-service-mcp', images['agent']['reference']),
               ('piwork-package-helper', images['agent']['reference']),
               ('piwork-file-helper', images['fileHelper']['reference']),
               ('piwork-snapshot-helper', images['snapshotHelper']['reference'])]
    probed = {}
    for program, reference in targets:
        result = runner(['docker', 'run', '--rm', '--pull=never', '--network=none',
                         '--entrypoint', '/usr/local/bin/' + program, reference, '--version'],
                        capture_output=True, text=True)
        require(result.returncode == 0, 'helper %s --version failed: %s'
                % (program, (result.stderr or '').strip()))
        try:
            reported = json.loads(result.stdout)
        except json.JSONDecodeError as err:
            raise ReleaseError('helper %s did not report JSON: %s' % (program, err))
        for field, expected in (('program', program), ('version', meta['releaseVersion']),
                                ('commit', meta['sourceCommit']), ('modified', False),
                                ('os', 'linux'), ('architecture', 'amd64')):
            require(reported.get(field) == expected,
                    'helper %s reports %s=%r, expected %r'
                    % (program, field, reported.get(field), expected))
        probed[program] = reported
    return probed


def normalize_reference(reference):
    """Docker drops the docker.io/ prefix from saved tags and RepoDigests."""
    return str(reference).removeprefix('docker.io/').removeprefix('index.docker.io/')


def docker_save_records(archive):
    """Read docker save's manifest and return normalized reference -> config digest."""
    with tarfile.open(archive, 'r:') as tar:
        raw = tar.extractfile('manifest.json')
        require(raw is not None, 'images archive has no manifest.json')
        manifest = json.loads(raw.read())
    records = {}
    for entry in manifest:
        config = str(entry.get('Config', ''))
        if config.startswith('blobs/sha256/'):
            config = config[len('blobs/sha256/'):]
        elif config.endswith('.json'):
            config = config[:-len('.json')]
        require(SHA256_RE.match(config) is not None, 'images archive has a malformed config name')
        for tag in entry.get('RepoTags') or []:
            tag = normalize_reference(tag)
            require(tag not in records, 'images archive repeats reference ' + tag)
            records[tag] = config
    return records


def prepare_images(release, images_tar, runner=subprocess.run):
    """Fetch the three production images by digest and write the Guest archive."""
    records = {}
    for role in DEVICE_IMAGES:
        records[role] = ensure_image(role, release['images'][role], release, runner=runner)
    programs = probe_helper_versions(release, runner=runner)
    references = [records[role]['reference'] for role in DEVICE_IMAGES]
    images_tar = pathlib.Path(images_tar)
    images_tar.parent.mkdir(parents=True, exist_ok=True)
    part = images_tar.with_name(images_tar.name + '.part')
    try:
        docker(['save', '-o', part, *references], runner=runner)
        saved = docker_save_records(part)
        require(set(saved) == {normalize_reference(reference) for reference in references},
                'images archive does not carry the locked references')
        for role in DEVICE_IMAGES:
            expected = release['images'][role]['imageId'].removeprefix('sha256:')
            require(saved[normalize_reference(records[role]['reference'])] == expected,
                    'images archive config differs for ' + role)
        os.replace(part, images_tar)
    finally:
        part.unlink(missing_ok=True)
    return {'images': {role: {'reference': records[role]['reference'], 'id': records[role]['id']}
                       for role in DEVICE_IMAGES},
            'packageHelper': records['agent'],
            'archive': {'path': str(images_tar), 'size': images_tar.stat().st_size,
                        'sha256': sha256_file(images_tar)},
            'helperPrograms': programs}


def official_input_payloads(lock, root, opener=download):
    """Fetch or reuse the locked assets and recheck every cross-reference."""
    release = lock['piwork']['release']
    version = release['version']
    names = asset_names(version)
    cache = pathlib.Path(root) / 'dist/downloads/piwork-release'
    payloads = {}
    for key in ASSET_KEYS:
        asset = release['assets'][key]
        payloads[key] = download_cached(asset['url'], asset['name'], asset['size'],
                                        asset['sha256'], cache, opener=opener).read_bytes()
    api = {'tag_name': release['tag'], 'draft': False,
           'prerelease': bool(release.get('prerelease')),
           'html_url': 'https://github.com/pphboy/piwork/releases/tag/' + release['tag'],
           'assets': [{'name': asset['name'], 'size': asset['size'],
                       'digest': 'sha256:' + asset['sha256'],
                       'browser_download_url': asset['url']}
                      for asset in release['assets'].values()]}
    checked = validate_release_metadata(api, release['tag'], release['releaseCommit'],
                                        payloads, names)
    require(checked['images'] == release['images'], 'release images differ from the lock')
    require(checked['build']['programs'] == release['metadata']['programs'],
            'release programs differ from the lock')
    return version, payloads


def prepare_lock(lock=None, root=ROOT, opener=download, runner=subprocess.run):
    """Verify and import the locked official release into dist/, without publishing remotely."""
    lock = lock or load_lock(root / 'build.lock.json')
    require(lock.get('piwork', {}).get('inputMode') == 'official-release',
            'prepare requires inputMode official-release')
    release = lock['piwork']['release']
    dist = pathlib.Path(root) / 'dist'
    dist.mkdir(parents=True, exist_ok=True)
    version, payloads = official_input_payloads(lock, root, opener=opener)

    stage = pathlib.Path(tempfile.mkdtemp(prefix='.piwork-prepare-', dir=dist))
    published = False
    images_backup = None
    try:
        archive = stage / release['assets']['archive']['name']
        archive.write_bytes(payloads['archive'])
        record = stage_import(archive, stage / 'import', release, runner=runner)
        piwork_stage = stage / 'import/piwork'
        images = prepare_images(release, stage / 'guest/images.tar', runner=runner)
        images['archive']['path'] = 'dist/guest/images.tar'
        write_json_atomic(piwork_stage / 'images.json', images['images'])
        license_index = piwork_licenses.collect(
            piwork_stage / 'bin', piwork_stage / 'upstream-release/licenses',
            {role: images['images'][role]['reference'] for role in DEVICE_IMAGES},
            runner=runner, workdir=stage / 'licenses-work')
        record['licenseIndex'] = license_index
        record['imagesPreparation'] = {'helperPrograms': images['helperPrograms'],
                                       'packageHelper': images['packageHelper']}
        record['guestOutputs'] = {'guest/images.tar': images['archive']}
        record['outputs'] = {key: value for key, value in tree_records(piwork_stage).items()
                             if key != 'import.json'}
        write_json_atomic(piwork_stage / 'import.json', record)

        piwork_target = dist / 'piwork'
        images_target = dist / 'guest/images.tar'
        images_target.parent.mkdir(parents=True, exist_ok=True)
        try:
            if images_target.exists():
                images_backup = images_target.with_name(images_target.name + '.previous')
                if images_backup.exists():
                    images_backup.unlink()
                os.replace(images_target, images_backup)
            os.replace(stage / 'guest/images.tar', images_target)
            publish_tree(piwork_stage, piwork_target)
        except BaseException:
            images_target.unlink(missing_ok=True)
            if images_backup is not None and images_backup.exists():
                os.replace(images_backup, images_target)
            raise
        if images_backup is not None:
            images_backup.unlink(missing_ok=True)
        published = True
        return record
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def check_prepared(lock=None, root=ROOT):
    """Read-only verification of the recorded preparation result against the lock."""
    lock = lock or load_lock(root / 'build.lock.json')
    require(lock.get('piwork', {}).get('inputMode') == 'official-release',
            'check requires inputMode official-release')
    release = lock['piwork']['release']
    dist = pathlib.Path(root) / 'dist'
    record = read_json(dist / 'piwork/import.json')
    require(record.get('tag') == release['tag'], 'prepared tag differs from the lock')
    require(record.get('buildCommit') == release['metadata']['sourceCommit'],
            'prepared build commit differs from the lock')
    require(record.get('releaseCommit') == release['releaseCommit'],
            'prepared release commit differs from the lock')
    for key in ASSET_KEYS:
        require(record.get('assets', {}).get(key, {}).get('sha256') ==
                release['assets'][key]['sha256'], 'prepared asset differs: ' + key)
    for role, expected in release['images'].items():
        require(record.get('images', {}).get(role, {}).get('imageId') == expected['imageId'],
                'prepared image differs: ' + role)
    outputs = record.get('outputs') or {}
    require(outputs, 'preparation record has no outputs')
    for relative, expected in outputs.items():
        target = dist / 'piwork' / relative
        require(target.is_file(), 'recorded output is missing: ' + relative)
        require(target.stat().st_size == expected['size'], 'output size differs: ' + relative)
        require(sha256_file(target) == expected['sha256'], 'output digest differs: ' + relative)
    guest = (record.get('guestOutputs') or {}).get('guest/images.tar')
    require(guest is not None, 'preparation record has no Guest image archive')
    images_tar = dist / 'guest/images.tar'
    require(images_tar.is_file(), 'Guest image archive is missing')
    require(images_tar.stat().st_size == guest['size'], 'Guest image archive size differs')
    require(sha256_file(images_tar) == guest['sha256'], 'Guest image archive digest differs')
    metadata = read_json(dist / 'piwork/metadata.json')
    require(metadata.get('sourceCommit') == release['metadata']['sourceCommit'],
            'metadata.json source commit differs')
    return {'tag': record['tag'], 'buildCommit': record['buildCommit'],
            'releaseCommit': record['releaseCommit'], 'outputs': len(outputs),
            'imagesTar': guest}


def cmd_prepare(args):
    lock = load_lock(args.lock)
    record = prepare_lock(lock, root=ROOT)
    print('Prepared %s: %d outputs, build commit %s'
          % (record['tag'], len(record['outputs']), record['buildCommit']))


def cmd_check(args):
    summary = check_prepared(load_lock(args.lock), root=ROOT)
    print(json.dumps(summary, indent=2))
    print('Preparation matches the lock.')


def cmd_lock(args):
    lock = load_lock(args.lock)
    api, tag_commit, payloads = fetch_release(args.tag, cache_dir=args.cache_dir)
    updated = build_official_lock(lock, args.tag, api, tag_commit, payloads)
    write_json_atomic(args.lock, updated)
    release = updated['piwork']['release']
    print('Locked %s: build commit %s, release commit %s, %d assets'
          % (args.tag, updated['piwork']['commit'], release['releaseCommit'], len(release['assets'])))
    print('Wrote', args.lock)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    lock = sub.add_parser('lock', help='explicitly replace the official release input')
    lock.add_argument('--tag', required=True, help='official release tag, for example v0.0.11')
    lock.add_argument('--lock', default=str(LOCK_PATH))
    lock.add_argument('--cache-dir', default=str(ROOT / 'dist/downloads/piwork-release'),
                      help='digest-keyed download cache')
    lock.set_defaults(func=cmd_lock)
    prepare = sub.add_parser('prepare', help='verify and import the locked official release')
    prepare.add_argument('--lock', default=str(LOCK_PATH))
    prepare.set_defaults(func=cmd_prepare)
    check = sub.add_parser('check', help='verify preparation outputs without writing or fetching')
    check.add_argument('--lock', default=str(LOCK_PATH))
    check.set_defaults(func=cmd_check)
    args = p.parse_args()
    try:
        args.func(args)
    except ReleaseError as err:
        print('piwork-release: ' + str(err), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
