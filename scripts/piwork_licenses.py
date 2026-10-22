#!/usr/bin/env python3
"""Collect readable license texts for the imported Piwork binaries and images.

The official archive ships only its root LICENSE, and the production images
carry Node, npm, Yarn, Debian packages and Go helper binaries. Nothing here is
optional in the index: a component whose text cannot be extracted is recorded
as a gap instead of being dropped.
"""
import argparse
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
LICENSE_NAME = re.compile(r'^(licen[cs]e|copying|copyright|notice|patents)', re.IGNORECASE)
MAX_LICENSE_SIZE = 2 * 1024 * 1024
MAX_IMAGE_FILES = 5000
MAX_IMAGE_BYTES = 64 * 1024 * 1024
IMAGE_ROLES = ('agent', 'fileHelper', 'snapshotHelper')


class LicenseError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise LicenseError(message)


def sha256_file(path):
    with pathlib.Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def docker(args, runner=subprocess.run):
    result = runner(['docker', *[str(arg) for arg in args]], capture_output=True, text=True)
    require(result.returncode == 0,
            'docker %s failed: %s' % (' '.join(str(arg) for arg in args),
                                      (result.stderr or '').strip()))
    return result.stdout.strip()


def module_dependencies(binary, runner=subprocess.run):
    """Read the module versions embedded by `go build` from a shipped binary."""
    result = runner(['go', 'version', '-m', str(binary)], capture_output=True, text=True)
    require(result.returncode == 0, 'cannot read module identity from ' + str(binary))
    dependencies = []
    for line in result.stdout.splitlines():
        fields = line.strip().split('\t')
        if len(fields) >= 3 and fields[0] == 'dep':
            dependencies.append({'path': fields[1], 'version': fields[2],
                                 'sum': fields[3] if len(fields) > 3 else None,
                                 'usedBy': [pathlib.Path(binary).name]})
    return dependencies


def license_texts(directory):
    directory = pathlib.Path(directory)
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.iterdir()
                  if path.is_file() and LICENSE_NAME.match(path.name)
                  and path.stat().st_size <= MAX_LICENSE_SIZE)


def slug(module):
    return module.replace('/', '_').replace('@', '_')


def collect_module_licenses(dependencies, out, runner=subprocess.run):
    """Download each embedded module and index its root license text."""
    merged = {}
    for dependency in dependencies:
        key = (dependency['path'], dependency['version'])
        record = merged.setdefault(key, {'module': dependency['path'],
                                         'version': dependency['version'],
                                         'sum': dependency['sum'], 'usedBy': []})
        for name in dependency.get('usedBy', []):
            if name not in record['usedBy']:
                record['usedBy'].append(name)
    index = []
    for (path, version), record in sorted(merged.items()):
        result = runner(['go', 'mod', 'download', '-json', '%s@%s' % (path, version)],
                        capture_output=True, text=True)
        reason = None
        files = []
        if result.returncode != 0:
            reason = 'go mod download failed'
        else:
            try:
                downloaded = json.loads(result.stdout)
            except json.JSONDecodeError:
                downloaded = {}
                reason = 'go mod download did not report JSON'
            if not reason and downloaded.get('Error'):
                reason = str(downloaded['Error'])
            directory = downloaded.get('Dir')
            if not reason and directory:
                for source in license_texts(directory):
                    target = pathlib.Path(out) / 'go-modules' / slug(path) / source.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    files.append(str(target.name))
            elif not reason:
                reason = 'module directory is unavailable'
        record.update({'present': bool(files), 'files': files,
                       'reason': None if files else (reason or 'no license text at the module root')})
        index.append(record)
    write_json(pathlib.Path(out) / 'go-modules/INDEX.json',
               {'modules': index, 'absent': sum(1 for record in index if not record['present'])})
    return index


def safe_member_name(name):
    return (isinstance(name, str) and name and not name.startswith('/')
            and '\\' not in name and '..' not in name.split('/'))


def debian_packages(status_bytes):
    packages = []
    current = {}
    for line in status_bytes.decode('utf-8', 'replace').splitlines() + ['']:
        if not line.strip():
            if current.get('Package'):
                packages.append((current['Package'], current.get('Version', '')))
            current = {}
            continue
        if line[:1] in (' ', '\t'):
            continue
        key, _, value = line.partition(':')
        current[key] = value.strip()
    return packages


def export_image(reference, export_path, runner=subprocess.run):
    container = docker(['create', reference], runner=runner)
    try:
        docker(['export', '-o', export_path, container], runner=runner)
    finally:
        runner(['docker', 'rm', '-f', container], capture_output=True, text=True)
    return export_path


def collect_image_licenses(role, reference, out, runner=subprocess.run, workdir=None):
    """Extract license texts and helper identities without booting a Guest."""
    workdir = pathlib.Path(workdir or tempfile.mkdtemp(prefix='piwork-image-'))
    workdir.mkdir(parents=True, exist_ok=True)
    export_path = workdir / (role + '.tar')
    binaries = workdir / (role + '-bin')
    binaries.mkdir(parents=True, exist_ok=True)
    target = pathlib.Path(out) / 'images' / role
    files, total = {}, 0
    status = None
    helper_binaries = {}
    modules = []
    try:
        export_image(reference, export_path, runner=runner)
        with tarfile.open(export_path, 'r:') as tar:
            for member in tar:
                if not safe_member_name(member.name) or not member.isfile():
                    continue
                relative = member.name[2:] if member.name.startswith('./') else member.name
                if relative == 'var/lib/dpkg/status':
                    status = tar.extractfile(member).read()
                    continue
                name = pathlib.Path(relative).name
                if (relative.startswith('usr/local/bin/piwork-') and name in
                        ('piwork-service-mcp', 'piwork-package-helper',
                         'piwork-file-helper', 'piwork-snapshot-helper')):
                    source = tar.extractfile(member)
                    target_binary = binaries / name
                    target_binary.write_bytes(source.read())
                    target_binary.chmod(0o755)
                    helper_binaries[name] = target_binary
                    continue
                if not LICENSE_NAME.match(name) or member.size > MAX_LICENSE_SIZE:
                    continue
                if len(files) >= MAX_IMAGE_FILES or total + member.size > MAX_IMAGE_BYTES:
                    continue
                data = tar.extractfile(member).read()
                files[relative] = data
                total += len(data)
        for name, path in sorted(helper_binaries.items()):
            try:
                modules.extend(module_dependencies(path, runner=runner))
            except LicenseError:
                modules.append({'path': name, 'version': 'unknown', 'sum': None, 'usedBy': [name]})
    finally:
        export_path.unlink(missing_ok=True)
        shutil.rmtree(binaries, ignore_errors=True)
    for relative, data in files.items():
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    packages = []
    if status is not None:
        extracted = set(files)
        for package, version in debian_packages(status):
            relative = 'usr/share/doc/%s/copyright' % package
            packages.append({'package': package, 'version': version,
                             'present': relative in extracted, 'path': relative,
                             'reason': None if relative in extracted
                             else 'no /usr/share/doc/%s/copyright in the image' % package})
    image_index = {'role': role, 'reference': reference,
                   'licenseFiles': len(files), 'licenseBytes': total,
                   'helperLicenseIndex': '../../go-modules/INDEX.json',
                   'debianPackages': packages,
                   'absentDebianLicenses': sum(1 for p in packages if not p['present']),
                   'helperModules': modules}
    write_json(target / 'INDEX.json', image_index)
    return image_index


def collect(bin_dir, out, images, runner=subprocess.run, workdir=None):
    """Build the full readable license and source index for an official import."""
    out = pathlib.Path(out)
    staging = pathlib.Path(tempfile.mkdtemp(prefix='piwork-licenses-',
                                            dir=out.parent if out.parent.exists() else None))
    try:
        official = staging / 'official'
        official.mkdir(parents=True)
        upstream = pathlib.Path(bin_dir).parent / 'upstream-release'
        for name in ('LICENSE', 'package-SHA256SUMS', 'go-build-info.txt'):
            source = upstream / name
            if source.is_file():
                shutil.copyfile(source, official / name)
        image_indexes = {}
        for role in IMAGE_ROLES:
            image_indexes[role] = collect_image_licenses(role, images[role], staging,
                                                         runner=runner, workdir=workdir)
        dependencies = []
        binaries = {}
        for name in ('piwork-core', 'piwork-cli'):
            binary = pathlib.Path(bin_dir) / name
            require(binary.is_file(), 'missing imported binary ' + str(binary))
            binaries[name] = {'sha256': sha256_file(binary), 'size': binary.stat().st_size}
            dependencies.extend(module_dependencies(binary, runner=runner))
        for index in image_indexes.values():
            dependencies.extend(index['helperModules'])
        modules = collect_module_licenses(dependencies, staging, runner=runner)
        summary = {'source': 'official-release', 'binaries': binaries,
                   'goModules': {'total': len(modules),
                                 'absent': sum(1 for m in modules if not m['present']),
                                 'index': (staging / 'go-modules/INDEX.json')
                                 .relative_to(staging).as_posix()},
                   'images': {role: {'reference': index['reference'],
                                     'licenseFiles': index['licenseFiles'],
                                     'absentDebianLicenses': index['absentDebianLicenses'],
                                     'index': 'images/%s/INDEX.json' % role}
                              for role, index in image_indexes.items()}}
        write_json(staging / 'index.json', summary)
        if out.exists():
            shutil.rmtree(out)
        staging.rename(out)
        return summary
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin-dir', default=str(ROOT / 'dist/piwork/bin'))
    parser.add_argument('--out', default=str(ROOT / 'dist/piwork/upstream-release/licenses'))
    parser.add_argument('--images-json', default=str(ROOT / 'dist/piwork/images.json'))
    args = parser.parse_args()
    images = {role: record['reference'] for role, record in
              json.loads(pathlib.Path(args.images_json).read_text()).items()}
    summary = collect(args.bin_dir, args.out, images)
    print('licenses:', args.out, 'go modules:', summary['goModules']['total'],
          'absent:', summary['goModules']['absent'],
          'images:', ', '.join(summary['images']))


if __name__ == '__main__':
    try:
        main()
    except LicenseError as err:
        print('piwork-licenses: ' + str(err), file=sys.stderr)
        sys.exit(1)
