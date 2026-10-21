"""Synthetic protected plans only; no real host, DB body or provider access."""
import copy,hashlib,json,os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from scripts import community_connection_collect as collector

ROOT=Path(__file__).resolve().parents[1]


class CommunityFixedCollectors(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path.home())
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.paths={}
        for key in sorted(collector.STORES):
            path=self.root/(key+'.sqlite')
            path.write_bytes(b'SYNTHETIC_DATABASE_BODY_MUST_NOT_BE_READ')
            path.chmod(0o600);self.paths[key]=str(path)
        self.config=dict(version=1,appid='wx1d5f8873eaea5392',https_origin='https://uk.wenwenwenyiyiyi.work',
            scenes={'shop1':{'project':'synthetic-project','principal':'synthetic-customer'}},stores=self.paths)
        self.file=self.root/'host-config.json'
        self.write()
        self.plan=dict(schema=1,project=collector.PROJECT,service_uid=os.geteuid(),
            config_path=str(self.file),config_sha256=hashlib.sha256(self.file.read_bytes()).hexdigest(),
            scene_sha256=hashlib.sha256(collector.canonical(self.config['scenes'])).hexdigest(),stores=self.paths)
        self.host=patch.object(collector.os,'uname',return_value=SimpleNamespace(nodename=collector.HOST))
        self.host.start();self.addCleanup(self.host.stop)

    def write(self):
        self.file.write_text(json.dumps(self.config));self.file.chmod(0o600)

    def test_reads_only_config_and_returns_metadata_without_claiming_runtime_or_history(self):
        original_read=os.read
        allowed=self.file.stat().st_ino
        def guarded(fd,count):
            self.assertEqual(os.fstat(fd).st_ino,allowed,'business database body read')
            self.assertLessEqual(count,65537)
            return original_read(fd,count)
        before=set(self.root.iterdir())
        with patch.object(collector.os,'read',side_effect=guarded):
            report=collector.runtime_metadata(self.plan)
        self.assertEqual(set(report['stores']),collector.STORES)
        self.assertEqual(before,set(self.root.iterdir()))
        for key in ('history_verified','identity_verified','runtime_verified','database_contents_read',
                    'initialization_performed','production_acceptance'):
            self.assertIs(report[key],False)
        text=json.dumps(report)
        self.assertNotIn(str(self.root),text)
        self.assertNotIn('synthetic-project',text)
        self.assertNotIn('SYNTHETIC_DATABASE_BODY',text)

    def test_missing_paths_are_not_created_and_wrong_hash_or_mapping_refused(self):
        for kind in ('missing','sha','scene','mapping','extra'):
            plan=copy.deepcopy(self.plan)
            if kind=='missing':plan['stores']['orders']=str(self.root/'absent.sqlite')
            elif kind=='sha':plan['config_sha256']='0'*64
            elif kind=='scene':plan['scene_sha256']='0'*64
            elif kind=='mapping':plan['stores'].pop('ads')
            else:plan['command']='not accepted'
            with self.subTest(kind=kind),self.assertRaises((ValueError,OSError)):
                collector.runtime_metadata(plan)
        self.assertFalse((self.root/'absent.sqlite').exists())

    def test_metadata_checks_do_not_require_distinct_files_for_legacy_aliases(self):
        self.paths['modules']=self.paths['quotes']
        self.config['stores']=self.paths;self.write()
        self.plan['config_sha256']=hashlib.sha256(self.file.read_bytes()).hexdigest()
        report=collector.runtime_metadata(self.plan)
        self.assertEqual(report['stores']['modules']['ino'],report['stores']['quotes']['ino'])

    def test_symlink_public_file_and_oversize_config_refused(self):
        path=Path(self.paths['orders']);old=path.read_bytes()
        path.unlink();path.symlink_to(self.file)
        with self.assertRaises((ValueError,OSError)):collector.runtime_metadata(self.plan)
        path.unlink();path.write_bytes(old);path.chmod(0o644)
        with self.assertRaises(ValueError):collector.runtime_metadata(self.plan)
        path.chmod(0o600)
        self.file.write_bytes(b'x'*65537)
        with self.assertRaisesRegex(ValueError,'BUDGET'):collector.runtime_metadata(self.plan)

    def test_wrong_host_and_untrusted_paths_refused_before_content_read(self):
        with (patch.object(collector.os,'uname',return_value=SimpleNamespace(nodename='wrong-host')),
              patch.object(collector,'read_absolute',side_effect=AssertionError('NO_READ'))):
            with self.assertRaisesRegex(ValueError,'UK_HOST_REQUIRED'):collector.runtime_metadata(self.plan)
        for path in ('relative.json','/a/../b','//a/b','/'):
            plan=dict(self.plan,config_path=path)
            with self.subTest(path=path),self.assertRaises(ValueError):collector.runtime_metadata(plan)

    def test_fixed_health_calls_original_reader_with_only_uk_profile(self):
        expected={'status':'BACKEND_NOT_READY'}
        with patch.object(collector,'check',return_value=expected) as call:
            self.assertIs(collector.health(),expected)
        call.assert_called_once_with(profile='uk-path-candidate')

    def test_input_manifest_is_exact_and_is_not_a_site_approval(self):
        value=json.loads((ROOT/'deploy/community-preview/connection-inputs.json').read_text())
        self.assertEqual(value['state'],'DRAFT_INPUTS_PINNED_NOT_ENROLLED')
        self.assertIs(value['dispatch_authorized'],False)
        self.assertIsNone(value['source_root_ref'])
        self.assertIsNone(value['authenticated_recipient'])
        for item in value['files']:
            raw=(ROOT/item['path']).read_bytes()
            self.assertEqual(len(raw),item['bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(),item['sha256'])


if __name__=='__main__':unittest.main()
