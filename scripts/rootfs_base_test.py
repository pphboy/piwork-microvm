import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('rootfs_base',pathlib.Path(__file__).with_name('rootfs.py'))
rootfs=importlib.util.module_from_spec(spec)
spec.loader.exec_module(rootfs)

class RootfsBaseTest(unittest.TestCase):
    def test_base_cache_requires_all_inputs_and_exact_label(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)
            (root/'guest/rootfs/files').mkdir(parents=True)
            (root/'build.lock.json').write_text(json.dumps({'guestBaseImage':'base@sha256:1','dockerImage':'docker@sha256:2','debianSnapshot':'date'}))
            (root/'guest/rootfs/Dockerfile').write_text('FROM base')
            (root/'guest/rootfs/files/service').write_text('original')
            with patch.object(rootfs,'ROOT',root):
                first=rootfs.base_fingerprint()
                result=type('Result',(),{'returncode':0,'stdout':first+'\n'})()
                with patch.object(rootfs.subprocess,'run',return_value=result),patch.object(rootfs,'run') as build:
                    rootfs.prepare_base()
                    build.assert_not_called()
                    (root/'guest/rootfs/files/service').write_text('changed')
                    self.assertNotEqual(first,rootfs.base_fingerprint())
                    rootfs.prepare_base()
                    build.assert_called_once()
