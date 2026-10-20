"""Source preparation tests only. Never accepted as OpenClaw loader/CP11 proof."""
import importlib.util,json,os,shutil,tarfile,tempfile,unittest
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('b5',str(REPO/'production/p2_install/b5_inputs.py'))
b5=importlib.util.module_from_spec(spec);spec.loader.exec_module(b5)
class Inputs(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.plugin=self.base/'plugin';shutil.copytree(REPO/b5.PLUGIN_PATH,self.plugin)
    def tearDown(self):self.temp.cleanup()
    def test_exact_original_archive_and_immutable_reference(self):
        out=self.base/'version';one=b5.prepare(self.plugin,out)
        with tarfile.open(out/one['package']) as tar:
            self.assertEqual(set(tar.getnames()),set(b5.PINS))
            for member in tar:
                self.assertTrue(member.isfile());self.assertEqual(member.mode,0o444)
                self.assertEqual(b5.sha(tar.extractfile(member).read()),b5.PINS[member.name])
        before={p.name:(p.read_bytes(),p.stat().st_ino) for p in out.iterdir()}
        self.assertEqual(one,b5.prepare(self.plugin,out))
        self.assertEqual(before,{p.name:(p.read_bytes(),p.stat().st_ino) for p in out.iterdir()})
    def test_bad_plugin_digest_cannot_publish(self):
        (self.plugin/'plugin.mjs').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'B5_SOURCE_SHA'):b5.prepare(self.plugin,self.base/'out')
        self.assertFalse((self.base/'out').exists())
    def test_symlink_and_unknown_member_rejected(self):
        source=self.plugin/'plugin.mjs';source.unlink();source.symlink_to(REPO/b5.PLUGIN_PATH/'plugin.mjs')
        with self.assertRaises(OSError):b5.plugin_files(self.plugin)
        source.unlink();shutil.copyfile(REPO/b5.PLUGIN_PATH/'plugin.mjs',source)
        (self.plugin/'extra.mjs').write_bytes(b'new')
        with self.assertRaisesRegex(ValueError,'EXACT_MEMBERS'):b5.plugin_files(self.plugin)
    def test_partial_output_retained_not_overwritten(self):
        out=self.base/'out';one=b5.prepare(self.plugin,out);target=out/one['package'];target.write_bytes(b'partial')
        with self.assertRaisesRegex(ValueError,'IMMUTABLE_INPUT_CONFLICT'):b5.prepare(self.plugin,out)
        self.assertEqual(target.read_bytes(),b'partial')
    def test_no_success_from_source_or_compatible_node(self):
        report=b5.capabilities();self.assertEqual(report['cp11_acceptance'],'NOT_EXECUTED')
        self.assertEqual(report['actual_registration'],'NOT_EXECUTED')
        self.assertEqual(report['safe_function']['state'],'UNAVAILABLE')
        for version in ('v24.16.0','24.21.0','26.1.0','27.0.0'):self.assertTrue(b5.node_engine_compatible(version))
        for version in ('24.15.9','25.0.0','26.0.9','bad','24.21.0-extra'):self.assertFalse(b5.node_engine_compatible(version))
    def test_later_failure_keeps_original_version(self):
        original=self.base/'v1';b5.prepare(self.plugin,original);before={p.name:p.read_bytes() for p in original.iterdir()}
        (self.plugin/'host.mjs').write_bytes(b'broken')
        with self.assertRaises(ValueError):b5.prepare(self.plugin,self.base/'v2')
        self.assertEqual(before,{p.name:p.read_bytes() for p in original.iterdir()})
if __name__=='__main__':unittest.main()
