import io
import json
import pathlib
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import piwork_licenses

CORE_INFO = """{binary}: go1.25.5
\tpath\tpiwork/cmd/piwork-core
\tmod\tpiwork\t(devel)
\tdep\tgithub.com/example/present\tv1.0.0\th1:present
\tdep\tgithub.com/example/missing\tv2.0.0\th1:missing
"""

STATUS = """Package: base-files
Version: 12.4

Package: no-docs
Version: 1.0
"""


class Result:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeRunner:
    def __init__(self, module_dir, export_tar):
        self.module_dir = module_dir
        self.export_tar = export_tar
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        if args[:2] == ['go', 'version']:
            return Result(0, CORE_INFO.format(binary=args[2]))
        if args[:3] == ['go', 'mod', 'download']:
            target = args[4]
            if target.startswith('github.com/example/present@'):
                return Result(0, json.dumps({'Path': 'github.com/example/present',
                                             'Version': 'v1.0.0', 'Dir': str(self.module_dir)}))
            return Result(0, json.dumps({'Path': target, 'Error': 'module not found'}))
        if args[:2] == ['docker', 'create']:
            return Result(0, 'container-id\n')
        if args[:2] == ['docker', 'export']:
            pathlib.Path(args[3]).write_bytes(self.export_tar.read_bytes())
            return Result()
        if args[:2] == ['docker', 'rm']:
            return Result()
        return Result(1, '', 'unexpected: ' + ' '.join(args))


def image_export(tmp):
    members = {
        'usr/local/LICENSE': b'node license\n',
        'usr/local/lib/node_modules/npm/LICENSE': b'npm license\n',
        'usr/share/doc/base-files/copyright': b'debian copyright\n',
        'usr/local/bin/piwork-service-mcp': b'not a binary\n',
        'var/lib/dpkg/status': STATUS.encode(),
    }
    path = pathlib.Path(tmp) / 'export.tar'
    with tarfile.open(path, 'w:') as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        evil = tarfile.TarInfo('../escape')
        evil.size = 0
        tar.addfile(evil, io.BytesIO(b''))
    return path


class CollectTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.module = self.root / 'module'
        self.module.mkdir()
        (self.module / 'LICENSE').write_text('module license\n')
        (self.module / 'README.md').write_text('not a license\n')
        (self.root / 'bin').mkdir()
        (self.root / 'bin/piwork-core').write_bytes(b'core')
        (self.root / 'bin/piwork-cli').write_bytes(b'cli')
        upstream = self.root / 'upstream-release'
        upstream.mkdir()
        (upstream / 'LICENSE').write_text('official license\n')
        self.runner = FakeRunner(self.module, image_export(self.root))
        self.images = {role: 'docker.io/pphboy/%s:tag' % role
                       for role in piwork_licenses.IMAGE_ROLES}

    def tearDown(self):
        self.temp.cleanup()

    def test_go_module_texts_and_gaps_are_indexed(self):
        out = self.root / 'licenses'
        summary = piwork_licenses.collect(self.root / 'bin', out, self.images, runner=self.runner)
        self.assertEqual(summary['goModules']['total'], 2)
        self.assertEqual(summary['goModules']['absent'], 1)
        self.assertTrue((out / 'go-modules/github.com_example_present/LICENSE').is_file())
        modules = json.loads((out / 'go-modules/INDEX.json').read_text())['modules']
        missing = next(m for m in modules if m['module'] == 'github.com/example/missing')
        self.assertFalse(missing['present'])
        self.assertIn('module not found', missing['reason'])
        self.assertTrue((out / 'official/LICENSE').is_file())

    def test_image_texts_and_debian_gaps_are_indexed(self):
        out = self.root / 'licenses'
        piwork_licenses.collect(self.root / 'bin', out, self.images, runner=self.runner)
        agent = json.loads((out / 'images/agent/INDEX.json').read_text())
        self.assertEqual(agent['reference'], self.images['agent'])
        packages = {p['package']: p for p in agent['debianPackages']}
        self.assertTrue(packages['base-files']['present'])
        self.assertFalse(packages['no-docs']['present'])
        self.assertIn('no /usr/share/doc/no-docs/copyright', packages['no-docs']['reason'])
        self.assertEqual(agent['absentDebianLicenses'], 1)
        self.assertTrue((out / 'images/agent/usr/local/LICENSE').is_file())
        self.assertTrue((out / 'images/agent/usr/local/lib/node_modules/npm/LICENSE').is_file())

    def test_unsafe_image_member_is_ignored(self):
        out = self.root / 'licenses'
        piwork_licenses.collect(self.root / 'bin', out, self.images, runner=self.runner)
        self.assertFalse((self.root / 'escape').exists())
        self.assertFalse((out / 'images/agent/../escape').exists())

    def test_helper_module_identity_is_included(self):
        out = self.root / 'licenses'
        piwork_licenses.collect(self.root / 'bin', out, self.images, runner=self.runner)
        agent = json.loads((out / 'images/agent/INDEX.json').read_text())
        modules = {m['path'] for m in agent['helperModules']}
        self.assertIn('github.com/example/present', modules)


if __name__ == '__main__':
    unittest.main()
