"""Portable local fixtures only; no real host, network or recovery effects."""
import copy
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import stat
import sys
import tarfile
import tempfile
import types
import unittest
from unittest import mock

import epoch7_recovery_entry as e
import build_epoch7_kit as b

HERE = pathlib.Path(__file__).resolve().parent
OWNERS = tuple(sorted(set(((0, 0), (os.geteuid(), os.getegid())))))


def raw(value): return b.canonical(value)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(HERE))
        self.base = pathlib.Path(self.temp.name)
        self.source = self.base / 'source'; self.source.mkdir(mode=0o700)
        self.map = {'schema': 1, 'runtime_source_commit': '1' * 40, 'runtime_source_tree': '2' * 40,
                    'kit_source_commit': '3' * 40, 'kit_source_tree': '4' * 40,
                    'files': {}, 'modules': {'sample': 'helpers/sample.py'},
                    'test_suites': {'alpha': {'tests': ['tests/alpha/test_same.py'],
                        'imports': {'test_same': 'tests/alpha/test_same.py'},
                        'enabled': True, 'reason': 'SYNTHETIC'},
                        'beta': {'tests': ['tests/beta/test_same.py'],
                        'imports': {'test_same': 'tests/beta/test_same.py'},
                        'enabled': True, 'reason': 'SYNTHETIC'}}}
        self.data = {e.ENTRY: b'# synthetic entry fixture\n', 'helpers/sample.py': b'VALUE = 42\n',
            'tests/alpha/test_same.py': b'import unittest\nclass A(unittest.TestCase):\n def test_a(self): self.assertTrue(True)\n',
            'tests/beta/test_same.py': b'import unittest\nclass B(unittest.TestCase):\n def test_b(self): self.assertTrue(True)\n'}
        runtime = {'files': {'stage1/module%03d.py' % i: e.sha(b'# runtime fixture\n') for i in range(107)}}
        for path in runtime['files']:
            self.data[e.RUNTIME + path] = b'# runtime fixture\n'
            self.map['modules'][path.split('/')[-1][:-3]] = e.RUNTIME + path
        manifest = raw(runtime)
        self.map['runtime_manifest_sha256'] = e.sha(manifest)
        self.data[e.RUNTIME + 'deploy/integration-manifest.json'] = manifest
        self.data[e.RUNTIME + 'tools/p2-package-freeze.py'] = b'# tool fixture\n'
        self.data[e.RUNTIME + 'P2_PACKAGE_PROVENANCE.json'] = raw({
            'schema':2, 'source_commit':self.map['runtime_source_commit'], 'source_tree':self.map['runtime_source_tree'],
            'runtime_manifest_sha256':self.map['runtime_manifest_sha256'],
            'runtime_manifest_path':'deploy/integration-manifest.json','runtime_files':runtime['files'],
            'verifier_path':'tools/p2-package-freeze.py',
            'verifier_sha256':e.sha(self.data[e.RUNTIME+'tools/p2-package-freeze.py'])})
        for path, data in self.data.items():
            source = self.source / path
            source.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            source.write_bytes(data)
            self.map['files'][path] = {'source': path, 'sha256': e.sha(data)}
        self.output = self.base / 'output'

    def tearDown(self): self.temp.cleanup()

    def build(self, output=None):
        return b.build(str(self.source), self.map, str(output or self.output), OWNERS)

    def verified(self):
        receipt = self.build()
        self.root = self.output / b.ROOT_NAME
        return e._verify(str(self.root), receipt['kit_manifest_sha256'], OWNERS)

    def rewrite(self, path, data):
        path.chmod(0o600); path.write_bytes(data)

    def test_deterministic_archive_and_receipt(self):
        first = self.build(); second = self.build(self.base / 'second')
        self.assertEqual(first, second)
        self.assertEqual((self.output / b.ARCHIVE).read_bytes(), (self.base / 'second' / b.ARCHIVE).read_bytes())
        self.assertNotIn(str(self.base), (self.output / 'kit-receipt.json').read_text())

    def test_ustar_unrepresentable_basename_refused_before_output(self):
        name='helpers/'+'x'*101+'.txt';data=b'synthetic bounded path fixture\n'
        (self.source/name).write_bytes(data)
        self.map['files'][name]={'source':name,'sha256':e.sha(data)}
        with self.assertRaises(ValueError):self.build()
        self.assertFalse(self.output.exists())

    def test_tar_metadata_and_no_implicit_extras(self):
        (self.source / 'private-plan.json').write_bytes(b'private synthetic sentinel')
        self.build()
        with tarfile.open(str(self.output / b.ARCHIVE)) as archive:
            self.assertFalse(any('private' in row.name for row in archive))
            for row in archive:
                self.assertEqual((row.uid,row.gid,row.mtime), (0,0,0))
                self.assertEqual(row.mode, 0o700 if row.isdir() else 0o444)
                self.assertTrue(row.isfile() or row.isdir())

    def test_exact_cache_without_import(self):
        kit = self.verified()
        self.assertEqual(kit.cache['helpers/sample.py'], b'VALUE = 42\n')
        self.assertNotIn('sample', sys.modules)
        self.assertEqual(kit.report()['install_admission'], 'NOT_GRANTED')

    def test_changed_source_rejected_before_output(self):
        (self.source / 'helpers/sample.py').write_bytes(b'CHANGED=1\n')
        with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'): self.build()
        self.assertFalse(self.output.exists())

    def test_syntax_failure_prevents_output(self):
        path='helpers/sample.py';data=b'invalid python !'
        (self.source/path).write_bytes(data);self.map['files'][path]['sha256']=e.sha(data)
        with self.assertRaises(SyntaxError): self.build()
        self.assertFalse(self.output.exists())

    def test_zero_write_is_bounded_failure(self):
        with mock.patch.object(b.os,'write',return_value=0) as write:
            with self.assertRaisesRegex(ValueError,'OUTPUT_SHORT_WRITE'):self.build()
            self.assertEqual(write.call_count,1)

    def test_existing_output_refused(self):
        self.output.mkdir()
        (self.output/'sentinel').write_text('keep')
        with self.assertRaises(FileExistsError):self.build()
        self.assertEqual((self.output/'sentinel').read_text(),'keep')

    def test_contradictory_source_provenance_rejected_before_output(self):
        name=e.RUNTIME+'P2_PACKAGE_PROVENANCE.json'
        value=json.loads(self.data[name].decode());value['source_commit']='9'*40
        data=raw(value);(self.source/name).write_bytes(data)
        self.map['files'][name]['sha256']=e.sha(data)
        with self.assertRaisesRegex(ValueError,'PROVENANCE_LINKAGE'):self.build()
        self.assertFalse(self.output.exists())

    def test_contradictory_verifier_provenance_rejected_before_output(self):
        name=e.RUNTIME+'P2_PACKAGE_PROVENANCE.json'
        value=json.loads(self.data[name].decode());value['verifier_sha256']='9'*64
        data=raw(value);(self.source/name).write_bytes(data)
        self.map['files'][name]['sha256']=e.sha(data)
        with self.assertRaisesRegex(ValueError,'PROVENANCE_LINKAGE'):self.build()

    def test_loader_rejects_coherently_rehashed_contradictory_provenance(self):
        kit=self.verified();name=e.RUNTIME+'P2_PACKAGE_PROVENANCE.json'
        value=json.loads((self.root/name).read_text());value['source_tree']='9'*40
        data=raw(value);self.rewrite(self.root/name,data)
        manifest=copy.deepcopy(kit.manifest);manifest['files'][name]=e.sha(data)
        manifest_raw=raw(manifest);self.rewrite(self.root/e.MANIFEST,manifest_raw)
        with self.assertRaisesRegex(ValueError,'PROVENANCE_LINKAGE'):
            e._verify(str(self.root),e.sha(manifest_raw),OWNERS)

    def test_source_symlink_refused(self):
        path=self.source/'helpers/sample.py';path.unlink();path.symlink_to('../tests/alpha/test_same.py')
        with self.assertRaises((OSError, ValueError)):self.build()

    def test_source_hardlink_refused(self):
        os.link(str(self.source/'helpers/sample.py'),str(self.source/'second.py'))
        with self.assertRaisesRegex(ValueError,'FILE_AUTHORITY'):self.build()

    def test_source_parent_symlink_refused(self):
        (self.source/'helpers').rename(self.source/'elsewhere')
        (self.source/'helpers').symlink_to('elsewhere')
        with self.assertRaises(OSError):self.build()

    def test_untrusted_ancestry_rejected(self):
        self.source.chmod(0o777)
        with self.assertRaisesRegex(ValueError,'UNTRUSTED_AUTHORITY'):self.build()

    def test_wrong_owner_rejected(self):
        with self.assertRaisesRegex(ValueError,'UNTRUSTED_AUTHORITY'):
            e.DescriptorTree(str(self.source), ((12345,12345),))

    def test_extra_helper_rejected(self):
        kit=self.verified();(self.root/'helpers/rogue.py').write_bytes(b'raise RuntimeError()')
        with self.assertRaisesRegex(ValueError,'EXTRA_OR_MISSING'):e._verify(str(self.root),kit.digest,OWNERS)

    def test_extra_empty_directory_rejected(self):
        kit=self.verified();(self.root/'extra').mkdir()
        with self.assertRaisesRegex(ValueError,'EXTRA_OR_MISSING'):e._verify(str(self.root),kit.digest,OWNERS)

    def test_bytecode_directory_rejected(self):
        kit=self.verified();(self.root/'helpers/__pycache__').mkdir()
        with self.assertRaisesRegex(ValueError,'BYTECODE'):e._verify(str(self.root),kit.digest,OWNERS)

    def test_bytecode_file_rejected(self):
        kit=self.verified();(self.root/'helpers/sample.pyc').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError,'BYTECODE'):e._verify(str(self.root),kit.digest,OWNERS)

    def test_missing_runtime_rejected(self):
        kit=self.verified();(self.root/e.RUNTIME/'stage1/module000.py').unlink()
        with self.assertRaisesRegex(ValueError,'EXTRA_OR_MISSING'):e._verify(str(self.root),kit.digest,OWNERS)

    def test_changed_helper_rejected(self):
        kit=self.verified();self.rewrite(self.root/'helpers/sample.py',b'raise RuntimeError()\n')
        with self.assertRaisesRegex(ValueError,'FILE_CHANGED'):e._verify(str(self.root),kit.digest,OWNERS)

    def test_changed_manifest_rejected(self):
        kit=self.verified();path=self.root/e.MANIFEST;self.rewrite(path,path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'MANIFEST_CHANGED'):e._verify(str(self.root),kit.digest,OWNERS)

    def test_loader_symlink_rejected(self):
        kit=self.verified();p=self.root/'helpers/sample.py';p.unlink();p.symlink_to('../tests/alpha/test_same.py')
        with self.assertRaisesRegex(ValueError,'NONREGULAR_CONTENT'):e._verify(str(self.root),kit.digest,OWNERS)

    def test_loader_fifo_rejected_without_blocking(self):
        kit=self.verified();p=self.root/'helpers/sample.py';p.unlink();os.mkfifo(str(p))
        with self.assertRaisesRegex(ValueError,'NONREGULAR_CONTENT'):e._verify(str(self.root),kit.digest,OWNERS)

    def test_path_traversal_denied(self):
        for name in ('../x','/x','a/../b','a//b','a/./b','x\\y','x\x00y'):
            with self.assertRaises(ValueError):e.relative(name)

    def test_duplicate_json_keys_denied(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE_JSON'):e.decode(b'{"schema":1,"schema":1}')

    def test_private_input_explicitly_denied(self):
        self.map['files']['helpers/sample.py']['source']='compiled-plan.private.json'
        with self.assertRaisesRegex(ValueError,'PRIVATE_INPUT'):self.build()

    def test_runtime_hash_pin_is_explicit_not_old_checkpoint(self):
        kit=self.verified();self.assertEqual(kit.report()['runtime_manifest_sha256'],self.map['runtime_manifest_sha256'])

    def test_incomplete_resume_refused_before_verification_or_import(self):
        flags=types.SimpleNamespace(isolated=1,no_site=1)
        with mock.patch.object(e.sys,'flags',flags),mock.patch.object(e.sys,'dont_write_bytecode',True),mock.patch.object(e,'verify_kit') as verify:
            with self.assertRaisesRegex(ValueError,'RESUME_INPUTS_REQUIRED'):
                e.main(['--operation','resume','--kit-manifest-sha256','a'*64])
            verify.assert_not_called()

    def test_observation_requires_output(self):
        with mock.patch.object(e.sys,'flags',types.SimpleNamespace(isolated=1,no_site=1)),mock.patch.object(e.sys,'dont_write_bytecode',True):
            with self.assertRaisesRegex(ValueError,'OBSERVATION_OUTPUT_SCOPE'):
                e.main(['--operation','observe-only','--kit-manifest-sha256','a'*64])

    def test_read_inplace_mutation_detected(self):
        target=self.source/'helpers/sample.py';original=os.read;changed=[False]
        def raced(fd,n):
            data=original(fd,n)
            if data==b'VALUE = 42\n' and not changed[0]:
                changed[0]=True;target.write_bytes(b'VALUE = 43\n')
            return data
        with mock.patch.object(e.os,'read',side_effect=raced):
            with self.assertRaisesRegex(ValueError,'READ_RACE'):self.build()

    def test_read_path_replacement_detected(self):
        target=self.source/'helpers/sample.py';original=os.read;changed=[False]
        def raced(fd,n):
            data=original(fd,n)
            if data==b'VALUE = 42\n' and not changed[0]:
                changed[0]=True;target.unlink();target.write_bytes(data)
            return data
        with mock.patch.object(e.os,'read',side_effect=raced):
            with self.assertRaisesRegex(ValueError,'READ_RACE|FILE_AUTHORITY'):self.build()

    def test_parent_rename_detected(self):
        with e.DescriptorTree(str(self.source),OWNERS) as tree:
            tree.read('helpers/sample.py')
            (self.source/'helpers').rename(self.source/'moved')
            (self.source/'helpers').mkdir()
            with self.assertRaisesRegex(ValueError,'ANCESTRY'):tree.recheck()

    def test_import_uses_cached_bytes_after_disk_mutation(self):
        kit=self.verified();self.rewrite(self.root/'helpers/sample.py',b'raise RuntimeError("UNVERIFIED")\n')
        loader=e.CachedSources(kit.root,kit.cache,{'sample':'helpers/sample.py'},[])
        spec=loader.find_spec('sample');module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.VALUE,42);self.assertIsNone(module.__cached__)

    def test_unknown_import_cannot_reopen_kit_path(self):
        kit=self.verified();loader=e.CachedSources(kit.root,kit.cache,{},[])
        with self.assertRaisesRegex(ImportError,'UNDECLARED_IMPORT'):loader.find_spec('rogue')

    def test_missing_module_uses_standard_platform_probe_exception(self):
        loader=e.CachedSources(str(self.base),{}, {},[])
        with self.assertRaises(ModuleNotFoundError) as caught:loader.find_spec('msvcrt')
        self.assertEqual(caught.exception.name,'msvcrt')

    def test_import_package_traversal_cannot_extend_bootstrap_path(self):
        trusted=self.base/'stdlib';trusted.mkdir()
        loader=e.CachedSources(str(self.base),{}, {},[str(trusted)])
        with mock.patch.object(e.importlib.machinery.PathFinder,'find_spec') as find:
            with self.assertRaisesRegex(ValueError,'UNTRUSTED_IMPORT_PATH'):
                loader.find_spec('package.rogue',[str(trusted)+'/../outside'])
            find.assert_not_called()

    def test_import_package_symlink_cannot_escape_bootstrap_path(self):
        trusted=self.base/'stdlib';trusted.mkdir();outside=self.base/'outside';outside.mkdir()
        (trusted/'alias').symlink_to(outside,target_is_directory=True)
        loader=e.CachedSources(str(self.base),{}, {},[str(trusted)])
        with mock.patch.object(e.importlib.machinery.PathFinder,'find_spec') as find:
            with self.assertRaisesRegex(ValueError,'UNTRUSTED_IMPORT_PATH'):
                loader.find_spec('package.rogue',[str(trusted/'alias')])
            find.assert_not_called()

    def test_suite_name_collision_has_distinct_bytes(self):
        kit=self.verified()
        for suite,wanted in [('alpha','A'),('beta','B')]:
            loader=e.CachedSources(kit.root,kit.cache,kit.manifest['test_suites'][suite]['imports'],[])
            module=types.ModuleType('test_same');loader.exec_module(module)
            self.assertTrue(hasattr(module,wanted))

    def test_nonportable_suite_has_no_partial_test_run(self):
        kit=self.verified();kit.manifest['test_suites']['beta']['enabled']=False
        with self.assertRaisesRegex(ValueError,'NONPORTABLE'):kit.tests(['alpha','beta'])

    def test_authority_checked_again_after_read(self):
        target=self.source/'helpers/sample.py';original=os.read;changed=[False]
        def raced(fd,n):
            data=original(fd,n)
            if data==b'VALUE = 42\n' and not changed[0]:changed[0]=True;target.chmod(0o666)
            return data
        with mock.patch.object(e.os,'read',side_effect=raced):
            with self.assertRaisesRegex(ValueError,'UNTRUSTED_AUTHORITY'):self.build()


class ExtractionTests(unittest.TestCase):
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown
    build = Fixture.build

    def prepare(self):
        import extract_epoch7_kit as x
        receipt=self.build();raw=(self.output/b.ARCHIVE).read_bytes()
        pins=(receipt['archive_sha256'],receipt['entry_sha256'],receipt['kit_manifest_sha256'])
        return x,receipt,raw,pins

    def repack(self, x, raw, change):
        import gzip
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
            rows=[(row,archive.extractfile(row).read() if row.isfile() else None) for row in archive]
        change(rows)
        output=io.BytesIO()
        with gzip.GzipFile(filename='',mode='wb',fileobj=output,mtime=0) as zipped:
            with tarfile.open(fileobj=zipped,mode='w',format=tarfile.PAX_FORMAT) as archive:
                for row,data in rows:archive.addfile(row,io.BytesIO(data) if data is not None else None)
        return output.getvalue()

    def test_extract_matches_verified_sources(self):
        x,r,data,pins=self.prepare();dest=self.base/b.ROOT_NAME
        result=x.extract(data,str(dest),*pins,owners=OWNERS)
        kit=e._verify(str(dest),r['kit_manifest_sha256'],OWNERS)
        self.assertEqual(result['files'],len(kit.cache)+1)

    def test_actual_runtime_long_unit_paths_roundtrip_without_extensions(self):
        # Exact two path names from the real107-file package; only the unit
        # payloads here are synthetic. The full real package roundtrip is also
        # mandatory in run_published_kit_ci, after bootstrap tests complete.
        manifest_name=e.RUNTIME+'deploy/integration-manifest.json'
        provenance_name=e.RUNTIME+'P2_PACKAGE_PROVENANCE.json'
        runtime=json.loads((self.source/manifest_name).read_text())
        paths=[]
        for index,role in ((105,'callback'),(106,'dashboard')):
            old='stage1/module%03d.py'%index
            target='deploy/uk-owner-workbench/xuanjun-uk-owner-'+role+'.service'
            name=e.RUNTIME+target;data=('[Unit]\nDescription=synthetic '+role+'\n').encode('ascii')
            self.assertGreater(len(b.ROOT_NAME+'/'+name),100)
            (self.source/(e.RUNTIME+old)).unlink()
            del self.map['files'][e.RUNTIME+old];del self.map['modules']['module%03d'%index]
            del runtime['files'][old];runtime['files'][target]=e.sha(data)
            (self.source/name).parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            (self.source/name).write_bytes(data)
            self.map['files'][name]={'source':name,'sha256':e.sha(data)};paths.append(name)
        manifest_raw=raw(runtime);self.map['runtime_manifest_sha256']=e.sha(manifest_raw)
        provenance=json.loads((self.source/provenance_name).read_text())
        provenance.update(runtime_files=runtime['files'],runtime_manifest_sha256=e.sha(manifest_raw))
        for name,data in ((manifest_name,manifest_raw),(provenance_name,raw(provenance))):
            (self.source/name).write_bytes(data);self.map['files'][name]['sha256']=e.sha(data)
        x,receipt,data,pins=self.prepare()
        with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
            self.assertTrue(all(not member.pax_headers for member in archive.getmembers()))
            self.assertTrue(all(archive.getmember(b.ROOT_NAME+'/'+name).isfile() for name in paths))
        destination=self.base/b.ROOT_NAME;x.extract(data,str(destination),*pins,owners=OWNERS)
        kit=e._verify(str(destination),receipt['kit_manifest_sha256'],OWNERS)
        for name in paths:self.assertEqual(kit.cache[name],(self.source/name).read_bytes())

    def test_pax_path_extension_remains_refused(self):
        x,receipt,data,pins=self.prepare()
        def change(rows):rows[-1][0].pax_headers={'path':rows[-1][0].name}
        data=self.repack(x,data,change)
        with self.assertRaisesRegex(ValueError,'ARCHIVE_METADATA'):
            x.inspect_archive(data,x.sha(data),*pins[1:])

    def test_archive_hash_checked_before_tar_processing(self):
        x,r,data,pins=self.prepare()
        with mock.patch.object(x.tarfile,'open') as tar:
            with self.assertRaisesRegex(ValueError,'ARCHIVE_HASH'):x.inspect_archive(data,'0'*64,*pins[1:])
            tar.assert_not_called()

    def test_duplicate_members_rejected(self):
        x,r,data,pins=self.prepare();data=self.repack(x,data,lambda rows:rows.append(rows[-1]))
        with self.assertRaisesRegex(ValueError,'DUPLICATE_MEMBER'):x.inspect_archive(data,x.sha(data),*pins[1:])

    def test_symlink_member_rejected(self):
        x,r,data,pins=self.prepare()
        def change(rows):
            row=tarfile.TarInfo(b.ROOT_NAME+'/helpers/link');row.type=tarfile.SYMTYPE
            row.linkname='/etc/shadow';row.uid=row.gid=row.mtime=0;row.uname=row.gname='root';row.mode=0o444
            rows.append((row,None))
        data=self.repack(x,data,change)
        with self.assertRaisesRegex(ValueError,'FILE_TYPE_OR_BOUND'):x.inspect_archive(data,x.sha(data),*pins[1:])

    def test_traversal_member_rejected(self):
        x,r,data,pins=self.prepare()
        def change(rows):rows[-1][0].name=b.ROOT_NAME+'/../escape'
        data=self.repack(x,data,change)
        with self.assertRaisesRegex(ValueError,'PATH'):x.inspect_archive(data,x.sha(data),*pins[1:])

    def test_entry_hash_is_independently_required(self):
        x,r,data,pins=self.prepare()
        with self.assertRaisesRegex(ValueError,'ENTRY_OR_MANIFEST_HASH'):x.inspect_archive(data,pins[0],'0'*64,pins[2])

    def test_extra_file_rejected_even_under_verified_archive_hash(self):
        x,r,data,pins=self.prepare()
        def change(rows):
            row=tarfile.TarInfo(b.ROOT_NAME+'/rogue.py');row.uid=row.gid=row.mtime=0
            row.uname=row.gname='root';row.mode=0o444;row.size=1;rows.append((row,b'x'))
        data=self.repack(x,data,change)
        with self.assertRaisesRegex(ValueError,'MANIFEST_SCOPE'):x.inspect_archive(data,x.sha(data),*pins[1:])

    def test_empty_extra_directory_rejected(self):
        x,r,data,pins=self.prepare()
        def change(rows):
            row=tarfile.TarInfo(b.ROOT_NAME+'/extra');row.type=tarfile.DIRTYPE
            row.uid=row.gid=row.mtime=0;row.uname=row.gname='root';row.mode=0o700;rows.append((row,None))
        data=self.repack(x,data,change)
        with self.assertRaisesRegex(ValueError,'EXTRA_OR_MISSING_DIRECTORY'):x.inspect_archive(data,x.sha(data),*pins[1:])

    def test_exact_r2_root_and_old_root_refused(self):
        x,r,data,pins=self.prepare()
        self.assertEqual(x.ROOT_NAME,b.ROOT_NAME)
        self.assertEqual(b.ROOT_NAME,'epoch7-recovery-candidate-r2')
        with self.assertRaisesRegex(ValueError,'ABSOLUTE_EXACT_OUTPUT'):
            x.extract(data,str(self.base/'epoch7-recovery-candidate'),*pins,owners=OWNERS)
        self.assertFalse((self.base/'epoch7-recovery-candidate').exists())

    def test_existing_destination_not_overwritten(self):
        x,r,data,pins=self.prepare();dest=self.base/b.ROOT_NAME;dest.mkdir()
        with self.assertRaises(FileExistsError):x.extract(data,str(dest),*pins,owners=OWNERS)

    def test_output_symlink_parent_refused(self):
        x,r,data,pins=self.prepare();(self.base/'alias').symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(OSError):x.extract(data,str(self.base/'alias'/b.ROOT_NAME),*pins,owners=OWNERS)

    def test_protected_archive_reader(self):
        x,r,data,pins=self.prepare()
        self.assertEqual(x.read_archive(str(self.output/b.ARCHIVE),OWNERS),data)

    def test_nonzero_tar_trailer_rejected(self):
        import gzip
        x,r,data,pins=self.prepare()
        expanded=gzip.decompress(data)+b'UNENUMERATED TRAILER'
        sink=io.BytesIO()
        with gzip.GzipFile(filename='',mode='wb',fileobj=sink,mtime=0) as stream:stream.write(expanded)
        data=sink.getvalue()
        with self.assertRaisesRegex(ValueError,'TRAILING_TAR_CONTENT'):x.inspect_archive(data,x.sha(data),*pins[1:])

    def test_archive_source_symlink_refused(self):
        x,r,data,pins=self.prepare();(self.base/'archive').symlink_to(self.output/b.ARCHIVE)
        with self.assertRaises(OSError):x.read_archive(str(self.base/'archive'),OWNERS)

class CompositionTests(unittest.TestCase):
    def setUp(self):
        import contextlib
        self.output='/fixed/candidate/epoch7-observation-'+'a'*16+'.private.json'
        self.root='/fixed/candidate/epoch7-recovery-candidate-r2'
        self.observer=mock.Mock()
        self.observer.c=types.SimpleNamespace(CAND='/fixed/candidate',path=lambda value:None)
        @contextlib.contextmanager
        def parent(unused):yield (123,'output')
        self.observer.ObservationReader.return_value.parent=parent
        self.observer.persist_private.return_value='c'*64
        sources=('stage1/ledger_service.py','stage1/ledger_server_identity.py','stage1/activation_control.py')
        cache={'helpers/probe_driver.py':b'driver','helpers/probe_helpers.py':b'helper',
               'helpers/node_sqlite_probe.py':b'node helper'}
        for name in sources:cache[e.RUNTIME+name]=name.encode()
        manifest={'runtime_manifest_sha256':'d'*64,'modules':{
            'observe_epoch7':'helpers/observe_epoch7.py','probe_driver':'helpers/probe_driver.py',
            'probe_helpers':'helpers/probe_helpers.py','node_sqlite_probe':'helpers/node_sqlite_probe.py'}}
        self.kit=e.VerifiedKit(self.root,manifest,cache,'e'*64)
        self.driver=mock.Mock()
        self.node=mock.Mock()
        self.driver.CANDIDATE_SOURCES=sources;self.driver.CASES=list(range(8))
        self.driver.canonical=lambda value:json.dumps(value,sort_keys=True,separators=(',',':')).encode()
        self.driver.compile_policy.return_value={'nonce':'a'*32,
            'node_sqlite':{'node':{'fixture':True},'probe_input_sha256':'6'*64}}
        self.driver.execute_reviewed_probe.return_value={'resume_authority':False,'failure':None,
            'cases':[{} for unused in range(8)],'cleanup':[{'status':'STOPPED_AND_EMPTY'}],
            'node_sqlite':{'synthetic':'observed'}}
        self.value={'kind':'EPOCH7_OBSERVATION_ONLY_UNREVIEWED','snapshot_sha256':'1'*64,
            'policy_sha256':'2'*64,'private_sentinel':'NEVER_PUBLIC','probe_metadata':{
                'ingredient_state':'COMPLETE_UNREVIEWED','ingredients':{'synthetic':'only'},
                'candidate_source_evidence':{'root':self.root+'/xuanjun-p2-package',
                    'runtime_manifest_sha256':'d'*64,'candidate_sources':{
                        name:e.sha(cache[e.RUNTIME+name]) for name in sources}}}}
        self.observer.observe_host.return_value=self.value
        self.patches=[mock.patch.object(self.kit,'imports',return_value=contextlib.ExitStack()),
            mock.patch.object(e.importlib,'import_module',side_effect=lambda name:{'observe_epoch7':self.observer,
                'probe_driver':self.driver,'node_sqlite_probe':self.node}[name]),
            mock.patch.object(e.os,'stat',side_effect=FileNotFoundError),
            mock.patch.object(e,'_verify',return_value=self.kit)]
        for patch in self.patches:patch.start()
    def tearDown(self):
        for patch in reversed(self.patches):patch.stop()
    def run_probe(self):return self.kit.observe(self.output,'a'*32,True)

    def test_observe_only_cannot_execute_probe(self):
        result=self.kit.observe(self.output)
        self.driver.execute_reviewed_probe.assert_not_called()
        self.assertEqual(result['probe_stage'],'NOT_REQUESTED')
        self.assertNotIn('NEVER_PUBLIC',json.dumps(result))
        self.observer.observe_host.assert_called_once_with(candidate_root=self.root+'/xuanjun-p2-package')

    def test_explicit_probe_compiles_cached_hashes_and_newline_policy_hash(self):
        result=self.run_probe();self.assertTrue(result['success'])
        offline=self.driver.compile_policy.call_args[0][1]
        self.assertEqual(offline['driver_sha256'],e.sha(b'driver'))
        self.assertIs(offline['node_sqlite_reviewed'],True)
        args=self.driver.execute_reviewed_probe.call_args[0]
        self.assertEqual(args[1],e.sha(self.driver.canonical(args[0])+b'\n'))
        self.assertEqual(args[2:],(self.root+'/xuanjun-p2-package',b'helper',True))
        self.assertFalse(self.value['finite_probe']['operator_acknowledgement_is_external_approval_proof'])
        self.node.validate_node_sqlite_proof.assert_called_once_with({'synthetic':'observed'},
            {'fixture':True},args[1],'6'*64)

    def test_node_binding_uses_original_observation_before_attempt_attachment(self):
        observed=[];policy=self.driver.compile_policy.return_value
        def compile_policy(ingredients,offline,observation):
            observed.append(copy.deepcopy(observation));return policy
        self.driver.compile_policy.side_effect=compile_policy
        self.assertTrue(self.run_probe()['success'])
        self.assertNotIn('finite_probe',observed[0]);self.assertEqual(observed[0]['snapshot_sha256'],'1'*64)

    def test_invalid_node_proof_preserves_result_and_reports_attempted_hold(self):
        self.node.validate_node_sqlite_proof.side_effect=ValueError('NODE_SQLITE_PROOF_NOT_VERIFIED')
        result=self.run_probe();self.assertFalse(result['success']);self.assertEqual(result['probe_stage'],'HOLD_AFTER_ATTEMPT')
        self.assertEqual(self.value['finite_probe']['result']['node_sqlite'],{'synthetic':'observed'})

    def test_missing_authenticated_node_helper_blocks_before_probe(self):
        del self.kit.manifest['modules']['node_sqlite_probe']
        self.assertFalse(self.run_probe()['success']);self.driver.execute_reviewed_probe.assert_not_called()

    def test_missing_acknowledgement_refused_before_import(self):
        with self.assertRaisesRegex(ValueError,'EXPLICIT_REVIEWED_PROBE_SCOPE'):
            self.kit.observe(self.output,'a'*32,False)
        self.kit.imports.assert_not_called()

    def test_snapshot_hold_blocks_probe_but_persists_observation(self):
        self.value['kind']='EPOCH7_OBSERVATION_ONLY_HOLD';result=self.run_probe()
        self.driver.execute_reviewed_probe.assert_not_called()
        self.assertEqual(result['probe_stage'],'HOLD_NOT_EXECUTED')
        self.assertEqual(self.value['finite_probe']['failure_code'],'EPOCH7_KIT_PROBE_REFUSED_ON_SNAPSHOT_HOLD')
        self.observer.persist_private.assert_called_once_with(self.output,self.value)

    def test_incomplete_ingredients_cannot_probe(self):
        self.value['probe_metadata']['ingredient_state']='INCOMPLETE';result=self.run_probe()
        self.driver.execute_reviewed_probe.assert_not_called();self.assertFalse(result['success'])

    def test_staged_source_mismatch_cannot_probe(self):
        self.value['probe_metadata']['candidate_source_evidence']['candidate_sources']['stage1/ledger_service.py']='0'*64
        result=self.run_probe();self.driver.execute_reviewed_probe.assert_not_called()
        self.assertFalse(result['success'])

    def test_existing_output_blocks_observation_and_probe(self):
        with mock.patch.object(e.os,'stat',return_value=object()):
            with self.assertRaisesRegex(ValueError,'OUTPUT_EXISTS'):self.run_probe()
        self.observer.observe_host.assert_not_called();self.driver.execute_reviewed_probe.assert_not_called()

    def test_old_root_blocks_new_observation_before_host_read(self):
        self.kit.root='/fixed/candidate/epoch7-recovery-candidate'
        with self.assertRaisesRegex(ValueError,'EXACT_STAGED_KIT'):self.run_probe()
        self.observer.observe_host.assert_not_called()

    def test_lexical_root_alias_blocks_new_observation(self):
        self.kit.root='/fixed/candidate/../candidate/epoch7-recovery-candidate-r2'
        with self.assertRaisesRegex(ValueError,'EXACT_STAGED_KIT'):self.run_probe()
        self.observer.observe_host.assert_not_called()

    def test_wrong_staging_root_blocks_observation(self):
        self.kit.root='/other/epoch7-recovery-candidate-r2'
        with self.assertRaisesRegex(ValueError,'EXACT_STAGED_KIT'):self.run_probe()
        self.observer.observe_host.assert_not_called()

    def test_changed_kit_before_probe_preserves_hold(self):
        with mock.patch.object(e,'_verify',side_effect=ValueError('KIT_CHANGED')):result=self.run_probe()
        self.driver.execute_reviewed_probe.assert_not_called()
        self.assertEqual(result['probe_stage'],'HOLD_NOT_EXECUTED')

    def test_probe_exception_keeps_observation_private_and_uncertain(self):
        self.driver.execute_reviewed_probe.side_effect=RuntimeError('private sentinel')
        result=self.run_probe();self.assertEqual(result['probe_stage'],'HOLD_AFTER_ATTEMPT')
        self.assertNotIn('private sentinel',json.dumps(self.value))
        self.observer.persist_private.assert_called_once()

    def test_probe_result_failure_not_reported_as_success(self):
        self.driver.execute_reviewed_probe.return_value['failure']='synthetic rejected case'
        result=self.run_probe();self.assertFalse(result['success'])
        self.assertEqual(result['probe_stage'],'RESULT_RECORDED')

    def test_unknown_cleanup_not_reported_as_success(self):
        self.driver.execute_reviewed_probe.return_value['cleanup']=[{'status':'UNKNOWN'}]
        self.assertFalse(self.run_probe()['success'])

    def test_residual_socket_not_reported_as_success(self):
        self.driver.execute_reviewed_probe.return_value['cleanup']=[{'socket':'RETAINED_REMOVE_ON_STOP_NOT_CONFIRMED'}]
        self.assertFalse(self.run_probe()['success'])

    def test_exception_string_is_never_inspected(self):
        class SecretError(Exception):
            def __str__(self): raise AssertionError('must not inspect')
            def __repr__(self): raise AssertionError('must not inspect')
        self.driver.execute_reviewed_probe.side_effect=SecretError()
        result=self.run_probe()
        self.assertEqual(result['probe_stage'],'HOLD_AFTER_ATTEMPT')
        self.assertEqual(self.value['finite_probe']['failure_code'],'PROBE_RESULT_UNAVAILABLE')

    def test_invalid_public_digest_refused_before_probe(self):
        self.value['snapshot_sha256']='private sentinel'
        with self.assertRaisesRegex(ValueError,'PUBLIC_DIGEST'):self.run_probe()
        self.driver.execute_reviewed_probe.assert_not_called()

    def test_cli_probe_flag_forbidden_in_observe_only(self):
        with mock.patch.object(e.sys,'flags',types.SimpleNamespace(isolated=1,no_site=1)),mock.patch.object(e.sys,'dont_write_bytecode',True):
            with self.assertRaisesRegex(ValueError,'PROBE_SCOPE_ONLY'):
                e.main(['--operation','observe-only','--kit-manifest-sha256','a'*64,
                        '--output',self.output,'--execute-reviewed-probe'])


class HostedRunnerTests(unittest.TestCase):
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown
    build = Fixture.build

    def runnable(self, required_helpers=True):
        import run_epoch7_offline as runner
        entry=(HERE/e.ENTRY).read_bytes()
        (self.source/e.ENTRY).write_bytes(entry);self.map['files'][e.ENTRY]['sha256']=e.sha(entry)
        self.map['test_suites']={}
        for name in list(self.map['files']):
            if name.startswith('tests/'):del self.map['files'][name]
        for name in runner.PORTABLE_SUITES:
            target='tests/'+name+'/test_same.py'
            data=b'import unittest\nclass Fixture(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n'
            p=self.source/target;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            self.map['files'][target]={'source':target,'sha256':e.sha(data)}
            self.map['test_suites'][name]={'enabled':True,'reason':'SYNTHETIC_ONLY',
                'tests':[target],'imports':{'test_same':target}}
        if required_helpers:
            for name in runner.REQUIRED_HELPERS:
                target='helpers/'+name+'.py';data=b'# synthetic pure helper\n'
                (self.source/target).write_bytes(data)
                self.map['files'][target]={'source':target,'sha256':e.sha(data)}
                self.map['modules'][name]=target
        receipt=self.build();root=str(self.output/b.ROOT_NAME)
        return runner,root,receipt

    def invoke(self, runner, root, receipt, commit='3'*40):
        with mock.patch.object(runner.sys,'flags',types.SimpleNamespace(isolated=1,no_site=1,verbose=0,optimize=0)), \
             mock.patch.object(runner.sys,'dont_write_bytecode',True), \
             mock.patch.object(runner.sys,'path',[p for p in sys.path if p]):
            return runner.run(root,receipt['entry_sha256'],receipt['kit_manifest_sha256'],commit,'4'*40)

    def test_unprivileged_runner_executes_all_exact_suites_without_host_mode(self):
        runner,root,receipt=self.runnable()
        result=self.invoke(runner,root,receipt)
        self.assertTrue(result['success']);self.assertEqual(len(result['suites']),25)
        self.assertEqual(len(runner.PORTABLE_SUITES),25)
        self.assertIn('owner_prerequisite',runner.PORTABLE_SUITES)
        self.assertIn('epoch7_owner_prerequisite',runner.REQUIRED_HELPERS)
        self.assertIn('epoch7_python_identity',runner.REQUIRED_HELPERS)
        self.assertEqual(result['isolated_probe'],'NOT_RUN')
        self.assertEqual(result['host_observation'],'NOT_RUN')
        self.assertEqual(result['production_acceptance'],'NOT_VERIFIED')

    def replace_one_suite(self, root, receipt, raw_test):
        manifest_path=pathlib.Path(root)/e.MANIFEST;value=json.loads(manifest_path.read_text())
        target=value['test_suites']['access_plan']['tests'][0]
        path=pathlib.Path(root)/target;path.chmod(0o600);path.write_bytes(raw_test)
        value['files'][target]=e.sha(raw_test);data=raw(value)
        manifest_path.chmod(0o600);manifest_path.write_bytes(data)
        receipt['kit_manifest_sha256']=e.sha(data)

    def test_required_portable_skip_is_not_complete_pass(self):
        runner,root,receipt=self.runnable()
        self.replace_one_suite(root,receipt,b'import unittest\n@unittest.skip("unsupported fixture")\nclass T(unittest.TestCase):\n def test_x(self): pass\n')
        result=self.invoke(runner,root,receipt)
        self.assertFalse(result['success']);self.assertFalse(result['portable_tests_complete'])
        self.assertEqual(sum(row['skipped'] for row in result['suites']),1)

    def test_empty_required_suite_is_not_complete_pass(self):
        runner,root,receipt=self.runnable()
        self.replace_one_suite(root,receipt,b'# no tests\n')
        result=self.invoke(runner,root,receipt)
        self.assertFalse(result['success']);self.assertFalse(result['portable_tests_complete'])

    def test_missing_required_helper_refused(self):
        runner,root,receipt=self.runnable(False)
        with self.assertRaisesRegex(ValueError,'REQUIRED_HELPERS_MISSING'):self.invoke(runner,root,receipt)

    def test_disabled_required_suite_refused(self):
        runner,root,receipt=self.runnable()
        path=pathlib.Path(root)/e.MANIFEST;value=json.loads(path.read_text())
        value['test_suites']['approval']['enabled']=False;data=raw(value)
        path.chmod(0o600);path.write_bytes(data);receipt['kit_manifest_sha256']=e.sha(data)
        with self.assertRaisesRegex(ValueError,'EXACT_PORTABLE_SUITE_SET'):self.invoke(runner,root,receipt)

    def replace_manifest(self, root, receipt, value):
        path=pathlib.Path(root)/e.MANIFEST;data=raw(value)
        path.chmod(0o600);path.write_bytes(data);receipt['kit_manifest_sha256']=e.sha(data)

    def missing_one_required_helper(self, name):
        runner,root,receipt=self.runnable()
        value=json.loads((pathlib.Path(root)/e.MANIFEST).read_text())
        target=value['modules'].pop(name);del value['files'][target]
        (pathlib.Path(root)/target).unlink()
        self.replace_manifest(root,receipt,value)
        with self.assertRaisesRegex(ValueError,'REQUIRED_HELPERS_MISSING'):self.invoke(runner,root,receipt)

    def test_missing_owner_prerequisite_helper_refused(self):
        self.missing_one_required_helper('epoch7_owner_prerequisite')

    def test_missing_python_identity_helper_refused(self):
        self.missing_one_required_helper('epoch7_python_identity')

    def test_missing_prerequisite_suite_refused(self):
        runner,root,receipt=self.runnable()
        value=json.loads((pathlib.Path(root)/e.MANIFEST).read_text())
        del value['test_suites']['owner_prerequisite']
        self.replace_manifest(root,receipt,value)
        with self.assertRaisesRegex(ValueError,'EXACT_PORTABLE_SUITE_SET'):self.invoke(runner,root,receipt)

    def test_disabled_prerequisite_suite_refused(self):
        runner,root,receipt=self.runnable()
        value=json.loads((pathlib.Path(root)/e.MANIFEST).read_text())
        value['test_suites']['owner_prerequisite']['enabled']=False
        self.replace_manifest(root,receipt,value)
        with self.assertRaisesRegex(ValueError,'EXACT_PORTABLE_SUITE_SET'):self.invoke(runner,root,receipt)

    def test_extra_enabled_suite_refused(self):
        runner,root,receipt=self.runnable()
        value=json.loads((pathlib.Path(root)/e.MANIFEST).read_text())
        target='tests/unreviewed/test_extra.py';data=b'import unittest\nclass T(unittest.TestCase):\n def test_x(self): pass\n'
        path=pathlib.Path(root)/target;path.parent.mkdir(mode=0o700);path.write_bytes(data)
        value['files'][target]=e.sha(data)
        value['test_suites']['unreviewed']={'enabled':True,'reason':'SYNTHETIC_UNREVIEWED',
            'tests':[target],'imports':{'test_extra':target}}
        self.replace_manifest(root,receipt,value)
        with self.assertRaisesRegex(ValueError,'EXACT_PORTABLE_SUITE_SET'):self.invoke(runner,root,receipt)

    def test_helper_source_commit_is_distinct_and_required(self):
        runner,root,receipt=self.runnable()
        with self.assertRaisesRegex(ValueError,'KIT_SOURCE_BINDING'):
            self.invoke(runner,root,receipt,commit=self.map['runtime_source_commit'])

    def test_wrong_entry_hash_refused_before_exec(self):
        runner,root,receipt=self.runnable();receipt['entry_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'ENTRY_HASH'):self.invoke(runner,root,receipt)

    def test_hosted_runner_refuses_root(self):
        import run_epoch7_offline as runner
        with mock.patch.object(runner.os,'geteuid',return_value=0):
            with self.assertRaisesRegex(ValueError,'UNPRIVILEGED'):
                runner.run('/unused','a'*64,'b'*64,'c'*40,'d'*40)

    def test_bootstrap_entry_symlink_refused(self):
        import run_epoch7_offline as runner
        link=self.base/'alias.py';link.symlink_to(self.source/e.ENTRY)
        with self.assertRaises(OSError):runner.bootstrap_entry(str(link),OWNERS)


class DisposableWorkspaceTests(unittest.TestCase):
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown
    build = Fixture.build
    verified = Fixture.verified

    def test_copy_is_byte_identical_and_original_never_gains_fixtures(self):
        kit=self.verified()
        with kit.test_workspace() as workspace:
            path=workspace.root
            self.assertNotEqual(path,kit.root);self.assertEqual(workspace.cache,kit.cache)
            self.assertTrue(os.path.isdir(path+'/helpers/fixtures'))
            self.assertFalse(os.path.exists(kit.root+'/helpers/fixtures'))
        self.assertFalse(os.path.exists(path));e._verify(kit.root,kit.digest,OWNERS)

    def test_leaked_fixture_refuses_and_disposable_copy_is_removed(self):
        kit=self.verified();path=None
        with self.assertRaises(OSError):
            with kit.test_workspace() as workspace:
                path=workspace.root
                pathlib.Path(path+'/helpers/fixtures/leftover').write_bytes(b'fixture')
        self.assertFalse(os.path.exists(path));e._verify(kit.root,kit.digest,OWNERS)

    def test_source_mutation_in_copy_refuses_without_affecting_original(self):
        kit=self.verified();path=None
        with self.assertRaisesRegex(ValueError,'FILE_CHANGED'):
            with kit.test_workspace() as workspace:
                path=workspace.root;source=pathlib.Path(path+'/helpers/sample.py')
                source.chmod(0o600);source.write_bytes(b'changed')
        self.assertFalse(os.path.exists(path));e._verify(kit.root,kit.digest,OWNERS)

    def test_zero_write_fails_without_loop_or_leftover_directory(self):
        kit=self.verified();before=set(self.output.iterdir())
        with mock.patch.object(e.os,'write',return_value=0):
            with self.assertRaisesRegex(ValueError,'WORKSPACE_SHORT_WRITE'):
                with kit.test_workspace():pass
        self.assertEqual(set(self.output.iterdir()),before)

    def test_test_exception_still_reverifies_original(self):
        kit=self.verified();original=e._verify
        with mock.patch.object(kit,'_execute_tests',side_effect=RuntimeError('fixture')), \
             mock.patch.object(e,'_verify',wraps=original) as verify:
            with self.assertRaises(RuntimeError):kit.tests(['alpha'])
        verify.assert_called_once_with(kit.root,kit.digest,kit.owners)


class PublicServiceFixtureTests(unittest.TestCase):
    def fixture(self):
        value={'runtime_manifest_sha256':'a'*64,'runtime_source_commit':'b'*40,'runtime_source_tree':'c'*40}
        cache={e.RUNTIME+'deploy/integration-manifest.json':b'{}\n'}
        fixture=dict(value,schema=1,kind='PUBLIC_CURRENT_RUNTIME_SERVICE_TEST_FIXTURE',
            host_evidence='NONE_SYNTHETIC_TESTS_ONLY',production_admission=False,
            runtime_manifest_raw='{}\n',units={})
        for target,source in e.PUBLIC_SERVICE_UNITS.items():
            template='[Unit]\nDescription=@@ARTIFACT_SHA256@@\n'
            cache[e.RUNTIME+source]=template.encode()
            fixture['units'][target]={'source':source,'source_sha256':e.sha(template.encode()),
                'template':template,'rendered':template.replace('@@ARTIFACT_SHA256@@','a'*64)}
        return value,cache,fixture

    def check(self,value,cache,fixture):
        cache[e.PUBLIC_SERVICE_FIXTURE]=raw(fixture)
        e.validate_public_service_fixture(value,cache)

    def test_only_public_runtime_derived_fixture_is_accepted(self):
        self.check(*self.fixture())

    def test_extra_private_field_or_unbound_template_is_rejected(self):
        for mutation in ('extra','template','rendered','commit','unit'):
            value,cache,fixture=self.fixture();row=next(iter(fixture['units'].values()))
            if mutation=='extra':fixture['private_value']='synthetic secret'
            elif mutation=='template':row['template']+='unbound text'
            elif mutation=='rendered':row['rendered']+='unbound text'
            elif mutation=='commit':fixture['runtime_source_commit']='d'*40
            else:fixture['units']['/unreviewed']=row
            with self.assertRaisesRegex(ValueError,'PUBLIC_FIXTURE'):self.check(value,cache,fixture)

    def test_builder_allows_only_one_exact_public_fixture_location(self):
        fixture=Fixture();fixture.setUp()
        try:
            source='p2-epoch7-repair/sequence-candidate/fixtures/public-service-units.json'
            fixture.map['files'][e.PUBLIC_SERVICE_FIXTURE]={'source':source,'sha256':'a'*64}
            b.validate_input(fixture.map)
            fixture.map['files'][e.PUBLIC_SERVICE_FIXTURE]['source']='evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/'+e.PUBLIC_SERVICE_FIXTURE
            b.validate_input(fixture.map)
            fixture.map['files'][e.PUBLIC_SERVICE_FIXTURE]['source']=source.replace('public-service-units','other')
            with self.assertRaisesRegex(ValueError,'PRIVATE_INPUT'):b.validate_input(fixture.map)
        finally:fixture.tearDown()


class PublicOpenclawFixtureTests(unittest.TestCase):
    def fixture(self):
        import base64
        files = {'source%02d.mjs' % i: {'sha256': e.sha(b'public fixture'),
            'content_base64': base64.b64encode(b'public fixture').decode('ascii')} for i in range(31)}
        value = {'schema': 1, 'fixture_scope': 'OFFICIAL_SOURCE_BYTES_ONLY_NOT_UK_EVIDENCE',
            'version': '2026.9.9', 'upstream_commit': 'bcfc88812a35243893585dbeca87ca41b48272ca',
            'npm_tar_sha256': 'a46df5fc5e4d73837d5b3eeebc286e64a85dffc429c30f3a07f6398e2a9423f7',
            'files': files}
        source = '\n'.join(name + ' = ' + repr(data) for name, data in (
            ('VERSION', value['version']), ('UPSTREAM', value['upstream_commit']),
            ('TARBALL', value['npm_tar_sha256']), ('SOURCE_HASHES', {k: v['sha256'] for k, v in files.items()})))
        return value, {'helpers/epoch7_openclaw_recipe.py': source.encode('ascii'),
            e.PUBLIC_OPENCLAW_LICENSE: b'synthetic license', e.PUBLIC_OPENCLAW_NOTICES: b'synthetic notices'}

    def check(self, value, cache):
        original = e.sha
        def synthetic_notice_sha(data):
            if data == b'synthetic license': return '73571b25326281d369087f469842c02444fe39faaecebda4d82ed21ff3a1c29d'
            if data == b'synthetic notices': return 'c1d1bbc550feee74853eba104e347341569cbbbe37a9f77659993ca0766277d5'
            return original(data)
        cache[e.PUBLIC_OPENCLAW_FIXTURE] = raw(value)
        # This is a synthetic validator unit test, not evidence of official bytes.
        with mock.patch.object(e, 'sha', side_effect=synthetic_notice_sha):
            e.validate_public_openclaw_fixture(cache)

    def test_literal_profile_checked_without_helper_execution(self):
        value, cache = self.fixture()
        cache['helpers/epoch7_openclaw_recipe.py'] += b'\nraise AssertionError("must not execute")\n'
        self.check(value, cache)

    def test_source_set_hash_bytes_and_private_extras_refused(self):
        for change in ('extra', 'missing', 'sha', 'bytes', 'private', 'version', 'row'):
            value, cache = self.fixture(); name = sorted(value['files'])[0]
            if change == 'extra': value['files']['extra'] = value['files'][name]
            elif change == 'missing': del value['files'][name]
            elif change == 'sha': value['files'][name]['sha256'] = '0' * 64
            elif change == 'bytes': value['files'][name]['content_base64'] = 'ZGlmZmVyZW50'
            elif change == 'private': value['host_evidence'] = 'forbidden'
            elif change == 'version': value['version'] = 'unreviewed'
            else: value['files'][name]['path'] = '/private'
            with self.subTest(change=change), self.assertRaises(ValueError): self.check(value, cache)

    def test_missing_or_changed_license_and_notices_refused(self):
        for path in (e.PUBLIC_OPENCLAW_LICENSE, e.PUBLIC_OPENCLAW_NOTICES):
            for missing in (True, False):
                value, cache = self.fixture()
                if missing: del cache[path]
                else: cache[path] = b'changed notice'
                with self.assertRaisesRegex(ValueError, 'PUBLIC_OPENCLAW'): self.check(value, cache)

    def test_nonliteral_duplicate_or_wrong_official_pins_refused(self):
        for extra in (b'\nVERSION = "other"\n', b'\nSOURCE_HASHES = dict()\n'):
            value, cache = self.fixture(); cache['helpers/epoch7_openclaw_recipe.py'] += extra
            with self.assertRaises(ValueError): self.check(value, cache)
        value, cache = self.fixture()
        cache['helpers/epoch7_openclaw_recipe.py'] = cache['helpers/epoch7_openclaw_recipe.py'].replace(
            b'2026.9.9', b'2026.9.8')
        with self.assertRaises(ValueError): self.check(value, cache)

    def test_source_bytes_are_bounded_and_base64_is_canonical(self):
        import base64
        value, cache = self.fixture(); name = sorted(value['files'])[0]
        value['files'][name]['content_base64'] += '\n'
        with self.assertRaises(ValueError): self.check(value, cache)
        value, cache = self.fixture()
        value['files'][name]['content_base64'] = 'A' * (2 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, 'SOURCE_ROW'): self.check(value, cache)

    def test_builder_only_accepts_exact_public_fixture_source_pairs(self):
        fixture = Fixture(); fixture.setUp()
        try:
            for target in (e.PUBLIC_OPENCLAW_FIXTURE, e.PUBLIC_OPENCLAW_LICENSE, e.PUBLIC_OPENCLAW_NOTICES):
                fixture.map['files'][target] = {'source': e.PUBLIC_FIXTURE_SOURCES[target], 'sha256': 'a' * 64}
                b.validate_input(fixture.map)
                fixture.map['files'][target]['source'] = 'evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/' + target
                b.validate_input(fixture.map)
                fixture.map['files'][target]['source'] = 'p2-epoch7-repair/sequence-candidate/fixtures/other.json'
                with self.assertRaisesRegex(ValueError, 'PRIVATE_INPUT'): b.validate_input(fixture.map)
                del fixture.map['files'][target]
        finally: fixture.tearDown()


class PublicDirectOpenclawFixtureTests(unittest.TestCase):
    def fixture(self):
        import base64
        base=PublicOpenclawFixtureTests();value,cache=base.fixture()
        content=b'x'*1461
        direct={'extends':'openclaw-source-profile.json','fixture_scope':value['fixture_scope'],
            'npm_tar_sha256':value['npm_tar_sha256'],'files':{e.PUBLIC_OPENCLAW_DIRECT_PATH:
            {'sha256':e.PUBLIC_OPENCLAW_DIRECT_SHA,'content_base64':base64.b64encode(content).decode('ascii')}}}
        cache['helpers/epoch7_openclaw_recipe.py']+=(
            '\nDIRECT_SOURCE_HASHES=dict(SOURCE_HASHES,**'+repr({e.PUBLIC_OPENCLAW_DIRECT_PATH:e.PUBLIC_OPENCLAW_DIRECT_SHA})+')\n').encode()
        cache[e.PUBLIC_OPENCLAW_DIRECT_FIXTURE]=raw(direct)
        return base,value,cache,direct,content
    def check(self,base,value,cache,direct,content):
        original=e.sha
        def synthetic(data):return e.PUBLIC_OPENCLAW_DIRECT_SHA if data==content else original(data)
        cache[e.PUBLIC_OPENCLAW_DIRECT_FIXTURE]=raw(direct)
        with mock.patch.object(e,'sha',side_effect=synthetic):base.check(value,cache)
    def test_exact_literal_extension_does_not_execute_recipe(self):
        base,value,cache,direct,content=self.fixture()
        cache['helpers/epoch7_openclaw_recipe.py']+=b'\nraise RuntimeError("do not execute")\n'
        self.check(base,value,cache,direct,content)
    def test_wrong_extension_schema_or_path_or_hash_or_bytes_refused(self):
        for variant in ('extra','wrong_path','wrong_sha','wrong_bytes','short','extends','tar','scope'):
            base,value,cache,direct,content=self.fixture();row=direct['files'][e.PUBLIC_OPENCLAW_DIRECT_PATH]
            if variant=='extra':direct['private']='forbidden'
            elif variant=='wrong_path':direct['files']={'other.js':row}
            elif variant=='wrong_sha':row['sha256']='0'*64
            elif variant=='wrong_bytes':row['content_base64']='eQ=='*487
            elif variant=='short':row['content_base64']='eA=='
            elif variant=='extends':direct['extends']='other.json'
            elif variant=='tar':direct['npm_tar_sha256']='0'*64
            else:direct['fixture_scope']='HOST_EVIDENCE'
            with self.subTest(variant=variant),self.assertRaises(ValueError):self.check(base,value,cache,direct,content)
    def test_missing_or_nonliteral_recipe_extension_refused(self):
        for text in ('','DIRECT_SOURCE_HASHES=dict()','DIRECT_SOURCE_HASHES=dict(SOURCE_HASHES,**{ "wrong": "0" })'):
            base,value,cache,direct,content=self.fixture()
            cache['helpers/epoch7_openclaw_recipe.py']=cache['helpers/epoch7_openclaw_recipe.py'].split(b'\nDIRECT_SOURCE_HASHES')[0]+b'\n'+text.encode()
            with self.assertRaises(ValueError):self.check(base,value,cache,direct,content)
    def test_direct_without_base_fixture_refused(self):
        base,value,cache,direct,content=self.fixture();del cache[e.PUBLIC_OPENCLAW_LICENSE]
        with self.assertRaisesRegex(ValueError,'COMPLETE_SET'):self.check(base,value,cache,direct,content)
    def test_builder_allows_only_exact_public_extension_path(self):
        fixture=Fixture();fixture.setUp()
        try:
            fixture.map['files'][e.PUBLIC_OPENCLAW_DIRECT_FIXTURE]={'source':e.PUBLIC_FIXTURE_SOURCES[e.PUBLIC_OPENCLAW_DIRECT_FIXTURE],'sha256':'a'*64}
            b.validate_input(fixture.map)
            fixture.map['files'][e.PUBLIC_OPENCLAW_DIRECT_FIXTURE]['source']='p2-epoch7-repair/sequence-candidate/fixtures/unreviewed.json'
            with self.assertRaisesRegex(ValueError,'PRIVATE_INPUT'):b.validate_input(fixture.map)
        finally:fixture.tearDown()


class ImportClosureTests(unittest.TestCase):
    def analyze(self, source, enabled=True):
        import audit_epoch7_imports as audit
        cache={'helpers/a.py':b'import os\n','tests/x/test_a.py':source}
        return audit.analyze(cache,{'a':'helpers/a.py'},{'x':{'tests':['tests/x/test_a.py'],
            'imports':{'test_a':'tests/x/test_a.py'},'enabled':enabled}}, {'os','hashlib'})

    def test_running_interpreter_stdlib_includes_source_build_extensions(self):
        import audit_epoch7_imports as audit
        self.assertTrue({'os','math','select','fcntl','unittest'} <= audit.standard_roots())

    def test_runtime_scripts_are_in_full_map_closure(self):
        import audit_epoch7_imports as audit
        result=audit.analyze({'xuanjun-p2-package/scripts/tool.py':b'def main():\n import missing_script_helper\n'}, {}, {}, set())
        self.assertFalse(result['success']);self.assertEqual(result['missing'][0]['scope'],'bootstrap_scripts')

    def test_function_local_missing_import_is_required_failure(self):
        result=self.analyze(b'def later():\n import missing_helper\n')
        self.assertFalse(result['success']);self.assertEqual(result['missing'][0]['name'],'missing_helper')

    def test_shared_test_fixture_transitive_import_is_checked_in_consuming_suite(self):
        import audit_epoch7_imports as audit
        cache = {'tests/x/test_a.py': b'import test_shared\n',
                 'tests/y/test_shared.py': b'def fixture():\n import test_missing\n'}
        suites = {'x': {'enabled': True, 'tests': ['tests/x/test_a.py'], 'imports': {
            'test_a': 'tests/x/test_a.py', 'test_shared': 'tests/y/test_shared.py'}}}
        result = audit.analyze(cache, {}, suites, set())
        self.assertFalse(result['success'])
        self.assertEqual([(r['scope'], r['name']) for r in result['missing']], [('x', 'test_missing')])

    def test_literal_dynamic_import_checked_without_executing(self):
        result=self.analyze(b'raise AssertionError("never execute")\ndef later():\n return __import__("a")\n')
        self.assertTrue(result['success']);self.assertEqual(result['references'][-1]['resolution'],'candidate')

    def test_disabled_suite_missing_dependencies_are_reported_separately(self):
        result=self.analyze(b'from private_fixture import value\n',False)
        self.assertTrue(result['success']);self.assertFalse(result['missing'][0]['required'])

    def test_nonliteral_import_and_direct_loader_need_explicit_review(self):
        result=self.analyze(b'def later(name):\n __import__(name)\n exec(name)\n')
        self.assertEqual(len(result['source_loading_review']),2)
        self.assertEqual(result['candidate_execution'],'NOT_RUN')


class ProtectedProbeReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(HERE)); self.addCleanup(self.temp.cleanup)
        self.parent = pathlib.Path(self.temp.name)
        patch = mock.patch.object(e, 'PROBE_RECEIPT_PARENT', str(self.parent)); patch.start(); self.addCleanup(patch.stop)
        self.nonce = 'a' * 32; self.directory = self.parent / ('xj-p2-proof-' + self.nonce)
        self.directory.mkdir(mode=0o700)
        self.path = self.directory / 'created-receipt.json'
        self.data = b'{"synthetic":"protected receipt bytes"}\n'
        self.path.write_bytes(self.data); self.path.chmod(0o600)
        info = self.path.stat()
        self.metadata = {'dev':info.st_dev,'ino':info.st_ino,'mode':stat.S_IMODE(info.st_mode),
            'uid':info.st_uid,'gid':info.st_gid,'nlink':info.st_nlink,'size':info.st_size,
            'mtime_ns':info.st_mtime_ns,'ctime_ns':info.st_ctime_ns}
        self.receipt = {'path':str(self.path),'sha256':e.sha(self.data),'metadata':self.metadata}
        self.observation = {'finite_probe':{'nonce':self.nonce,'result':{'created_receipt':self.receipt}}}
        self.kit = e.VerifiedKit(str(self.parent/'unused'),
            {'modules':{'node_sqlite_probe':'helpers/node_sqlite_probe.py'}},{},'b'*64,OWNERS)
        self.helper = mock.Mock(); self.helper.authenticate_receipt_binding.return_value = {'proof':'synthetic private detail'}

    def check(self):
        with mock.patch.object(e.importlib,'import_module',return_value=self.helper) as load:
            result = self.kit._authenticate_probe_receipt(self.observation)
            load.assert_called_once_with('node_sqlite_probe')
            return result

    def test_actual_descriptor_read_passes_exact_bytes_metadata_and_observation(self):
        result = self.check()
        self.helper.authenticate_receipt_binding.assert_called_once_with(self.data,self.metadata,self.observation)
        self.assertEqual(result['receipt_sha256'],e.sha(self.data))
        self.assertNotIn('synthetic private detail',json.dumps(result))

    def test_receipt_module_and_fixed_nonce_path_required_before_open(self):
        for change in ('module','nonce','path'):
            with mock.patch.object(e,'DescriptorTree') as tree:
                if change == 'module': self.kit.manifest['modules'] = {}
                elif change == 'nonce': self.observation['finite_probe']['nonce'] = '../outside'
                else: self.receipt['path'] = '/outside/created-receipt.json'
                with self.assertRaises(ValueError): self.check()
                tree.assert_not_called()
            self.kit.manifest['modules'] = {'node_sqlite_probe':'helpers/node_sqlite_probe.py'}
            self.observation['finite_probe']['nonce'] = self.nonce
        self.helper.authenticate_receipt_binding.assert_not_called()

    def test_symlink_and_hardlink_refused_before_authentication(self):
        other = self.parent/'other'; other.write_bytes(self.data); other.chmod(0o600)
        self.path.unlink(); self.path.symlink_to(other)
        with self.assertRaises((ValueError,OSError)): self.check()
        self.path.unlink(); os.link(str(other),str(self.path))
        with self.assertRaisesRegex(ValueError,'FILE_AUTHORITY'): self.check()
        self.helper.authenticate_receipt_binding.assert_not_called()

    def test_nonprivate_mode_and_untrusted_owner_refused(self):
        self.path.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'PRIVATE_FILE_MODE'): self.check()
        self.path.chmod(0o600); self.kit.owners = ((987654,987654),)
        with self.assertRaisesRegex(ValueError,'UNTRUSTED_AUTHORITY'): self.check()
        self.helper.authenticate_receipt_binding.assert_not_called()

    def test_receipt_bound_checked_before_read(self):
        with self.path.open('wb') as stream: stream.truncate(e.MAX_PROBE_RECEIPT+1)
        with mock.patch.object(e.os,'read') as read:
            with self.assertRaisesRegex(ValueError,'FILE_BOUND'): self.check()
            read.assert_not_called()

    def test_hash_or_typed_metadata_change_refused(self):
        self.receipt['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError,'PROBE_RECEIPT_CHANGED'): self.check()
        self.receipt['sha256'] = e.sha(self.data); self.metadata['nlink'] = True
        with self.assertRaisesRegex(ValueError,'PROBE_RECEIPT_CHANGED'): self.check()
        self.helper.authenticate_receipt_binding.assert_not_called()

    def test_receipt_replacement_during_read_refused(self):
        original = os.read; changed = [False]
        def raced(fd, maximum):
            data = original(fd, maximum)
            if data == self.data and not changed[0]:
                changed[0] = True; self.path.unlink(); self.path.write_bytes(data); self.path.chmod(0o600)
            return data
        with mock.patch.object(e.os,'read',side_effect=raced):
            with self.assertRaisesRegex(ValueError,'READ_RACE|FILE_AUTHORITY'): self.check()
        self.helper.authenticate_receipt_binding.assert_not_called()

    def test_pure_receipt_authentication_rejection_is_not_overridden(self):
        self.helper.authenticate_receipt_binding.side_effect = ValueError('INVALID_RECEIPT_EVENT')
        with self.assertRaisesRegex(ValueError,'INVALID_RECEIPT_EVENT'): self.check()


class ResumeInputTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=str(HERE));self.parent=pathlib.Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.patch=mock.patch.object(e,'CANDIDATE_PARENT',str(self.parent));self.patch.start();self.addCleanup(self.patch.stop)
        self.private={name:' {"synthetic":"保留"}\n\n' for name in e.PRIVATE_RAW_FIELDS}
        self.private.update(observation={'approved_snapshot':'fixed'},compiled={'rendered_targets':{}},
            additive_deltas=[],identity_payloads={path:'{"identity":"fixture"}\n' for path in e.IDENTITY_PATHS},
            activate_retained_renewal_timer=False)
        self.contract={name:{'synthetic':name} for name in ('host_contract','resource_observer','live_controls')}
        self.plan_path=self.parent/('epoch7-approved-plan-'+'a'*16+'.private.json')
        self.seed_path=self.parent/('epoch7-resume-inputs-'+'b'*16+'.private.json')
        self.write_inputs()
        manifest={'production_resume':e.RESUME_COMPOSED,'runtime_source_commit':'1'*40,
            'runtime_source_tree':'2'*40,'runtime_manifest_sha256':'3'*64}
        sources={'stage1/a.py':e.sha(b'a'),'scripts/uk-integration-install.py':e.sha(b'installer')}
        cache={e.RUNTIME+'deploy/integration-manifest.json':raw({'files':sources}),
            e.RUNTIME+'stage1/a.py':b'a',e.RUNTIME+'scripts/uk-integration-install.py':b'installer'}
        self.kit=e.VerifiedKit(str(self.parent)+'/epoch7-recovery-candidate-r2',manifest,cache,'4'*64,OWNERS)
        self.factory=mock.Mock();self.factory.INPUTS=e.PRIVATE_SEED_FIELDS|e.CACHE_SEED_FIELDS
        self.factory.DERIVED_INPUTS=frozenset();self.factory.compiled_bytes.side_effect=lambda value:dict(value)
        self.factory.prepare_host_inputs.return_value={'state':'COMPILED_NOT_ADMITTED','unresolved':[],
            'install_admission':False,'inputs':{'compiled_fixture':True}}
        self.factory.compile_host_contract.return_value=self.contract
        class Hold(RuntimeError):
            def __init__(self,state):self.state=state
        class Interrupted(KeyboardInterrupt):
            def __init__(self,state):self.state=state
        class Exited(SystemExit):
            def __init__(self,state):self.state=state
        self.sequence=mock.Mock(RecoveryHold=Hold,RecoveryInterrupted=Interrupted,RecoveryExited=Exited)
        self.sequence.PHASES=('synthetic_phase',)
        self.sequence.packed.side_effect=raw
        self.state={'stage':'COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE','production_acceptance':'PENDING',
            'admission':'ADMITTED','completed':['synthetic_phase'],'synthetic_private':'DO_NOT_PRINT'}
        self.sequence.resume_once.return_value=self.state
        self.in_scope=False;self.scope_entries=0
        import contextlib
        @contextlib.contextmanager
        def scope():
            self.assertFalse(self.in_scope);self.in_scope=True;self.scope_entries+=1
            try:yield
            finally:self.in_scope=False
        self.scope=scope
        # Boundary-mock composition tests; receipt filesystem/authentication is
        # separately exercised by ProtectedProbeReceiptTests and helper tests.
        self.receipt = mock.Mock(return_value={'receipt_sha256':'6'*64})
        patch = mock.patch.object(self.kit, '_authenticate_probe_receipt', self.receipt)
        patch.start(); self.addCleanup(patch.stop)

    def write_inputs(self):
        self.plan_raw=raw(self.contract);self.seed_raw=raw({'schema':1,'seed':self.private})
        self.plan_path.write_bytes(self.plan_raw);self.seed_path.write_bytes(self.seed_raw)
        self.plan_path.chmod(0o600);self.seed_path.chmod(0o600)

    def args(self):return (str(self.plan_path),e.sha(self.plan_raw),str(self.seed_path),e.sha(self.seed_raw))

    def read(self):return self.kit._private_resume_inputs(*self.args())

    def run_resume(self):
        def module(name):
            self.assertTrue(self.in_scope)
            return {'epoch7_host_factory':self.factory,'epoch7_recovery_sequence':self.sequence}[name]
        with mock.patch.object(e.os,'geteuid',return_value=0),mock.patch.object(e.os,'uname',return_value=types.SimpleNamespace(nodename=e.FIXED_HOST)),\
             mock.patch.object(self.kit,'imports',self.scope),mock.patch.object(e.importlib,'import_module',side_effect=module),\
             mock.patch.object(e,'_verify',return_value=self.kit):
            return self.kit.resume(*(self.args()+(999999999,'5'*64)))

    def test_private_utf8_bytes_preserved_exactly(self):
        _,_,private=self.read();seed=self.kit._hydrate_seed(private,self.factory)
        for name in e.PRIVATE_RAW_FIELDS:self.assertEqual(seed[name],self.private[name].encode('utf-8'))
        for name in e.IDENTITY_PATHS:self.assertEqual(seed['identity_payloads'][name],self.private['identity_payloads'][name].encode('utf-8'))
        self.assertEqual(seed['installer_source'],b'installer');self.assertEqual(len(seed['source_payloads']),2)
        self.assertEqual(seed['kit_manifest_sha256'],self.kit.digest)
        self.assertEqual(seed['observation'],self.private['observation'])

    def test_seed_rejects_every_cache_override(self):
        for name in e.CACHE_SEED_FIELDS:
            bad=dict(self.private);bad[name]='override'
            with self.assertRaisesRegex(ValueError,'PRIVATE_SEED_SCHEMA'):self.kit._hydrate_seed(bad,self.factory)

    def test_seed_rejects_generic_bytes_or_paths(self):
        for value in ({'path':'/etc/shadow'},{'bytes':'abc'},['abc'],None):
            bad=dict(self.private);bad['native_before']=value
            with self.assertRaisesRegex(ValueError,'PRIVATE_RAW_UTF8_REQUIRED'):self.kit._hydrate_seed(bad,self.factory)

    def test_private_symlink_refused(self):
        other=self.parent/'other';other.write_bytes(self.seed_raw);self.seed_path.unlink();self.seed_path.symlink_to(other)
        with self.assertRaises(OSError):self.read()

    def test_private_hardlink_refused(self):
        os.link(str(self.seed_path),str(self.parent/'alias'))
        with self.assertRaisesRegex(ValueError,'FILE_AUTHORITY'):self.read()

    def test_private_permissions_refused(self):
        self.seed_path.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'PRIVATE_FILE_MODE'):self.read()

    def test_private_owner_refused(self):
        self.kit.owners=((987654,987654),)
        with self.assertRaisesRegex(ValueError,'UNTRUSTED_AUTHORITY'):self.read()

    def test_private_plan_bound_checked_before_read(self):
        with self.plan_path.open('wb') as stream:stream.truncate(2*1024*1024+1)
        with mock.patch.object(e.os,'read') as read:
            with self.assertRaisesRegex(ValueError,'FILE_BOUND'):self.read()
            read.assert_not_called()

    def test_large_private_seed_does_not_relax_public_file_bound(self):
        self.seed_raw=b' '*(e.MAX_FILE+1)+self.seed_raw;self.seed_path.write_bytes(self.seed_raw)
        self.assertEqual(self.read()[2],self.private)
        with e.DescriptorTree(str(self.parent),OWNERS) as tree:
            with self.assertRaisesRegex(ValueError,'FILE_AUTHORITY'):tree.read(self.seed_path.name)

    def test_private_seed_above64mib_refused_before_read(self):
        with self.seed_path.open('wb') as stream:stream.truncate(e.MAX_PRIVATE_SEED+1)
        with e.DescriptorTree(str(self.parent),OWNERS) as tree,mock.patch.object(e.os,'read') as read:
            with self.assertRaisesRegex(ValueError,'FILE_AUTHORITY'):
                tree.read(self.seed_path.name,e.MAX_PRIVATE_SEED,private=True)
            read.assert_not_called()

    def test_private_hash_change_refused(self):
        self.seed_path.write_bytes(self.seed_raw+b' ')
        with self.assertRaisesRegex(ValueError,'PRIVATE_INPUT_CHANGED'):self.read()

    def test_private_parent_and_basename_are_fixed(self):
        values=list(self.args());values[0]=str(self.parent/'arbitrary.json')
        with self.assertRaisesRegex(ValueError,'PRIVATE_INPUT_PATH'):self.kit._private_resume_inputs(*values)

    def test_old_manifest_refuses_before_private_reads(self):
        self.kit.manifest['production_resume']=e.RESUME_REFUSED
        with mock.patch.object(self.kit,'_private_resume_inputs') as read:
            with self.assertRaisesRegex(ValueError,'RESUME_REFUSED_UNCOMPOSED'):self.run_resume()
            read.assert_not_called()

    def test_success_chain_once_inside_one_import_scope(self):
        self.sequence.resume_once.side_effect=lambda driver:(self.assertTrue(self.in_scope),self.state)[1]
        result=self.run_resume()
        self.assertTrue(result['success']);self.assertEqual(result['stage'],'COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE')
        self.assertEqual(self.scope_entries,1);self.assertFalse(self.in_scope)
        self.factory.prepare_host_inputs.assert_called_once();self.factory.compile_host_contract.assert_called_once()
        self.factory.assemble_host_driver.assert_called_once_with(self.plan_raw,{'compiled_fixture':True},999999999,'5'*64)
        self.sequence.resume_once.assert_called_once_with(self.factory.assemble_host_driver.return_value)
        self.assertEqual(self.receipt.call_count, 2)
        self.assertNotIn('DO_NOT_PRINT',json.dumps(result));self.assertEqual(result['production_acceptance'],'PENDING')

    def test_receipt_authentication_failure_prevents_preparation_and_effects(self):
        self.receipt.side_effect=ValueError('synthetic private receipt detail')
        result=self.run_resume();self.assertFalse(result['success'])
        self.factory.prepare_host_inputs.assert_not_called();self.factory.assemble_host_driver.assert_not_called()
        self.sequence.resume_once.assert_not_called();self.assertNotIn('private receipt',json.dumps(result))

    def test_changed_protected_receipt_before_assembly_prevents_attempt(self):
        self.receipt.side_effect=[{'receipt_sha256':'6'*64},{'receipt_sha256':'7'*64}]
        result=self.run_resume();self.assertFalse(result['success'])
        self.factory.assemble_host_driver.assert_not_called();self.sequence.resume_once.assert_not_called()

    def test_compiler_hold_never_assembles_or_resumes(self):
        self.factory.prepare_host_inputs.return_value={'state':'HOLD','unresolved':['fixture'],'inputs':None,'install_admission':False}
        result=self.run_resume();self.assertFalse(result['success']);self.assertEqual(result['production_resume'],'NOT_EXECUTED')
        self.factory.assemble_host_driver.assert_not_called();self.sequence.resume_once.assert_not_called()

    def test_approved_components_mismatch_never_assembles(self):
        self.factory.compile_host_contract.return_value=dict(self.contract,host_contract={'changed':True})
        result=self.run_resume();self.assertFalse(result['success'])
        self.factory.assemble_host_driver.assert_not_called();self.sequence.resume_once.assert_not_called()

    def test_private_change_during_compilation_prevents_assembly(self):
        prepared=self.factory.prepare_host_inputs.return_value
        def prepare(seed):
            self.seed_path.write_bytes(self.seed_raw+b' ')
            return prepared
        self.factory.prepare_host_inputs.side_effect=prepare
        result=self.run_resume();self.assertFalse(result['success']);self.factory.assemble_host_driver.assert_not_called()
        self.sequence.resume_once.assert_not_called()

    def test_approved_boolean_integer_confusion_is_rejected(self):
        self.contract['host_contract']={'typed':True};self.write_inputs()
        self.factory.compile_host_contract.return_value=dict(self.contract,host_contract={'typed':1})
        result=self.run_resume();self.assertFalse(result['success']);self.factory.assemble_host_driver.assert_not_called()

    def test_incomplete_coordinator_completion_is_unknown(self):
        self.sequence.resume_once.return_value=dict(self.state,completed=[])
        result=self.run_resume();self.assertFalse(result['success'])
        self.assertEqual(result['stage'],'COORDINATOR_OUTCOME_UNKNOWN')

    def test_invalid_or_consumed_review_assembly_failure_has_no_coordinator(self):
        self.factory.assemble_host_driver.side_effect=ValueError('synthetic private detail')
        result=self.run_resume();self.assertFalse(result['success']);self.sequence.resume_once.assert_not_called()
        self.assertNotIn('synthetic private detail',json.dumps(result))

    def test_coordinator_hold_and_interrupt_preserve_outcome(self):
        for error,stage,code in ((self.sequence.RecoveryHold,'COORDINATOR_HOLD',2),
            (self.sequence.RecoveryInterrupted,'INTERRUPTED_HOLD',130),(self.sequence.RecoveryExited,'COORDINATOR_HOLD',2)):
            self.sequence.resume_once.side_effect=error(dict(self.state,admission='UNKNOWN'))
            result=self.run_resume();self.assertFalse(result['success']);self.assertEqual(result['stage'],stage)
            self.assertEqual(result['exit_code'],code);self.assertEqual(result['install_admission'],'UNKNOWN')
            self.assertIn('coordinator_state_sha256',result)

    def test_unexpected_error_after_attempt_is_unknown_and_not_retried(self):
        self.sequence.resume_once.side_effect=RuntimeError('PRIVATE_SENTINEL')
        result=self.run_resume();self.assertFalse(result['success']);self.sequence.resume_once.assert_called_once()
        self.assertEqual(result['production_resume'],'COORDINATOR_OUTCOME_UNKNOWN');self.assertNotIn('PRIVATE_SENTINEL',json.dumps(result))

    def test_mode_builder_manifest_and_extractor_match(self):
        fixture=Fixture();fixture.setUp()
        try:
            fixture.map['production_resume']=e.RESUME_COMPOSED
            for name in e.COMPOSITION_MODULES:
                path='helpers/'+name+'.py';data=b'# composition fixture\n'
                (fixture.source/path).write_bytes(data);fixture.map['files'][path]={'source':path,'sha256':e.sha(data)}
                fixture.map['modules'][name]=path
            old=e.RUNTIME+'stage1/module106.py';new=e.RUNTIME+'scripts/uk-integration-install.py'
            data=fixture.data[old];(fixture.source/new).parent.mkdir();(fixture.source/new).write_bytes(data)
            fixture.map['files'][new]={'source':new,'sha256':e.sha(data)}
            del fixture.map['files'][old];del fixture.map['modules']['module106']
            rp=e.RUNTIME+'deploy/integration-manifest.json';runtime=e.decode(fixture.data[rp]);del runtime['files']['stage1/module106.py']
            runtime['files']['scripts/uk-integration-install.py']=e.sha(data);newraw=raw(runtime)
            (fixture.source/rp).write_bytes(newraw);fixture.map['files'][rp]['sha256']=e.sha(newraw);fixture.map['runtime_manifest_sha256']=e.sha(newraw)
            pp=e.RUNTIME+'P2_PACKAGE_PROVENANCE.json';proof=e.decode(fixture.data[pp]);proof.update(runtime_files=runtime['files'],runtime_manifest_sha256=e.sha(newraw))
            (fixture.source/pp).write_bytes(raw(proof));fixture.map['files'][pp]['sha256']=e.sha(raw(proof))
            receipt=fixture.build();kit=e._verify(str(fixture.output/b.ROOT_NAME),receipt['kit_manifest_sha256'],OWNERS)
            self.assertEqual(receipt['production_resume'],e.RESUME_COMPOSED)
            self.assertEqual(kit.report()['production_resume'],e.RESUME_COMPOSED)
            import extract_epoch7_kit as extract
            archive=(fixture.output/b.ARCHIVE).read_bytes()
            extract.inspect_archive(archive,receipt['archive_sha256'],receipt['entry_sha256'],receipt['kit_manifest_sha256'])
        finally:fixture.tearDown()


class PublishedCITests(unittest.TestCase):
    def setUp(self):
        import run_published_kit_ci as ci
        self.ci=ci
        self.index={'schema':1,'kind':'EPOCH7_EXPLICIT_PUBLIC_SOURCE_INDEX','runtime_source_commit':ci.RUNTIME_COMMIT,
            'runtime_source_tree':ci.RUNTIME_TREE,'runtime_manifest_sha256':ci.RUNTIME_MANIFEST,
            'production_resume':e.RESUME_COMPOSED,'modules':{},'test_suites':{},
            'files':{e.ENTRY:{'source':ci.PREFIX+'/'+e.ENTRY,'sha256':'a'*64}},
            'tools':{name:{'source':ci.PREFIX+'/tools/'+name,'sha256':'b'*64} for name in ci.REQUIRED_TOOLS}}

    def test_exact_index_has_no_generated_helper_commit_or_self_reference(self):
        self.assertIs(self.ci.validate_index(self.index),self.index)
        for name in ('kit_source_commit','kit_source_tree','self_sha256'):
            value=copy.deepcopy(self.index);value[name]='a'*40
            with self.assertRaisesRegex(ValueError,'INDEX_SCHEMA'):self.ci.validate_index(value)

    def test_required_tools_cannot_be_omitted(self):
        for name in self.ci.REQUIRED_TOOLS:
            value=copy.deepcopy(self.index);del value['tools'][name]
            with self.assertRaisesRegex(ValueError,'INDEX_FILE_SCOPE'):self.ci.validate_index(value)

    def test_runtime_pin_changes_are_not_adopted(self):
        for name in ('runtime_source_commit','runtime_source_tree','runtime_manifest_sha256'):
            value=copy.deepcopy(self.index);value[name]='0'*len(value[name])
            with self.assertRaisesRegex(ValueError,'FIXED_RUNTIME_PROVENANCE'):self.ci.validate_index(value)

    def test_published_paths_must_be_exact(self):
        for path in ('../escape','/etc/shadow','elsewhere/'+e.ENTRY,self.ci.PREFIX+'/tools/'+e.ENTRY):
            value=copy.deepcopy(self.index);value['files'][e.ENTRY]['source']=path
            with self.assertRaises(ValueError):self.ci.validate_index(value)

    def test_index_cannot_supply_runtime_rows_or_arbitrary_host_evidence(self):
        for target in ('xuanjun-p2-package/stage1/a.py','host-evidence.json'):
            value=copy.deepcopy(self.index);value['files'][target]={'source':self.ci.PREFIX+'/'+target,'sha256':'c'*64}
            with self.assertRaisesRegex(ValueError,'INDEX_PUBLIC_KIT_SCOPE'):self.ci.validate_index(value)

    def test_git_blob_size_precedes_content_read(self):
        with mock.patch.object(self.ci,'git',return_value=b'11\n') as git:
            with self.assertRaisesRegex(ValueError,'GIT_BLOB_BOUND'):self.ci.git_blob('/fixture','a'*40,'a.py',10)
            self.assertEqual(git.call_count,1)
        with mock.patch.object(self.ci,'git',side_effect=[b'3\n',b'abc']):
            self.assertEqual(self.ci.git_blob('/fixture','a'*40,'a.py',10),b'abc')

    def test_git_blob_short_content_rejected(self):
        with mock.patch.object(self.ci,'git',side_effect=[b'3\n',b'ab']):
            with self.assertRaisesRegex(ValueError,'GIT_BLOB_SIZE'):self.ci.git_blob('/fixture','a'*40,'a.py',10)

    def test_shared_overall_time_budget_cannot_reset_per_command(self):
        with mock.patch.object(self.ci,'DEADLINE',10),mock.patch.object(self.ci.time,'monotonic',return_value=9):
            self.assertEqual(self.ci.remaining(15),1)
        with mock.patch.object(self.ci,'DEADLINE',10),mock.patch.object(self.ci.time,'monotonic',return_value=11):
            with self.assertRaisesRegex(ValueError,'OVERALL_TIME_BOUND'):self.ci.remaining(15)

    def child(self,code,timeout=2,limit=4096):
        with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
            result=self.ci.bounded_child([sys.executable,'-I','-B','-S','-c',code],str(HERE),
                dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),out,err,timeout,limit,limit)
            out.seek(0);return result,out.read()

    def test_actual_local_child_success_and_nonzero_are_preserved(self):
        self.assertEqual(self.child('print("fixture")'),(0,b'fixture\n'))
        self.assertEqual(self.child('import sys;sys.exit(7)')[0],7)

    def test_actual_local_child_timeout_is_bounded(self):
        import time
        before=time.monotonic()
        with self.assertRaisesRegex(ValueError,'COMMAND_TIME_BOUND'):self.child('import time;time.sleep(30)',0.05)
        self.assertLess(time.monotonic()-before,3)

    def test_actual_local_child_output_is_capped(self):
        with self.assertRaisesRegex(ValueError,'COMMAND_OUTPUT_BOUND'):self.child('print("x"*10000)',limit=32)

    def test_group_is_signalled_before_own_leader_is_reaped(self):
        events=[];process=mock.Mock(pid=123)
        process.wait.side_effect=lambda **unused:(events.append('reap'),0)[1]
        with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err,\
             mock.patch.object(self.ci.subprocess,'Popen',return_value=process),\
             mock.patch.object(self.ci.os,'waitid',return_value=object()),\
             mock.patch.object(self.ci.os,'getpgid',return_value=123),mock.patch.object(self.ci.os,'getsid',return_value=123),\
             mock.patch.object(self.ci.os,'killpg',side_effect=lambda *unused:events.append('signal')):
            self.assertEqual(self.ci.bounded_child(['fixture'],'/fixture',{},out,err,1,32,32),0)
        self.assertEqual(events,['signal','reap']);process.wait.assert_called_once_with(timeout=2)
        process.poll.assert_not_called();process.communicate.assert_not_called()

    def test_unknown_group_never_signalled_or_reported_success(self):
        process=mock.Mock(pid=123);process.wait.return_value=0
        with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err,\
             mock.patch.object(self.ci.subprocess,'Popen',return_value=process),\
             mock.patch.object(self.ci.os,'waitid',return_value=object()),\
             mock.patch.object(self.ci.os,'getpgid',return_value=999),mock.patch.object(self.ci.os,'killpg') as signal_group:
            with self.assertRaisesRegex(ValueError,'COMMAND_CLEANUP_UNKNOWN'):
                self.ci.bounded_child(['fixture'],'/fixture',{},out,err,1,32,32)
            signal_group.assert_not_called();process.wait.assert_called_once_with(timeout=2)

    def test_lost_child_ownership_never_signals_reused_pgid(self):
        process=mock.Mock(pid=123);process.wait.return_value=0
        with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err,\
             mock.patch.object(self.ci.subprocess,'Popen',return_value=process),\
             mock.patch.object(self.ci.os,'waitid',side_effect=[object(),ChildProcessError()]),\
             mock.patch.object(self.ci.os,'getpgid') as group,mock.patch.object(self.ci.os,'killpg') as signal_group:
            with self.assertRaises(ChildProcessError):self.ci.bounded_child(['fixture'],'/fixture',{},out,err,1,32,32)
            group.assert_not_called();signal_group.assert_not_called();process.wait.assert_called_once_with(timeout=2)

    def test_signal_failure_still_reaps_and_never_succeeds(self):
        process=mock.Mock(pid=123);process.wait.return_value=0
        with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err,\
             mock.patch.object(self.ci.subprocess,'Popen',return_value=process),\
             mock.patch.object(self.ci.os,'waitid',return_value=object()),\
             mock.patch.object(self.ci.os,'getpgid',return_value=123),mock.patch.object(self.ci.os,'getsid',return_value=123),\
             mock.patch.object(self.ci.os,'killpg',side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):self.ci.bounded_child(['fixture'],'/fixture',{},out,err,1,32,32)
            process.wait.assert_called_once_with(timeout=2)

    def test_failure_report_retains_static_code_and_hides_external_text(self):
        public=self.ci.failure_report(ValueError('EPOCH7_PUBLISHED_CI_RUNTIME_GIT_MISMATCH'))
        self.assertEqual(public['error_code'],'EPOCH7_PUBLISHED_CI_RUNTIME_GIT_MISMATCH')
        private=self.ci.failure_report(ValueError('synthetic-private-path-or-output'))
        self.assertIsNone(private['error_code']);self.assertNotIn('synthetic-private',json.dumps(private))

    def test_zero_write_fails_without_loop(self):
        with tempfile.TemporaryDirectory(dir=str(HERE)) as root,mock.patch.object(self.ci.os,'write',return_value=0) as write:
            with self.assertRaisesRegex(ValueError,'SHORT_WRITE'):self.ci.write_exclusive(root+'/file',b'x')
            self.assertEqual(write.call_count,1)

    def test_generator_builds_twice_extracts_and_runs_real_runner_with_mock_git_fixture(self):
        # Synthetic 107-file package and dummy suites only. This proves the CI
        # orchestration, not candidate tests, real Git provenance or admission.
        fixture=HostedRunnerTests();fixture.setUp()
        try:
            runner,unused,receipt=fixture.runnable()
            repo=fixture.base/'published-fixture';repo.mkdir(mode=0o700)
            index={key:fixture.map[key] for key in ('modules','test_suites','runtime_source_commit',
                'runtime_source_tree','runtime_manifest_sha256')}
            index.update(schema=1,kind='EPOCH7_EXPLICIT_PUBLIC_SOURCE_INDEX',production_resume=e.RESUME_REFUSED,files={},tools={})
            for target,row in fixture.map['files'].items():
                source=(self.ci.RUNTIME+'/'+target[len(e.RUNTIME):] if target.startswith(e.RUNTIME)
                        else self.ci.PREFIX+'/'+target)
                data=(fixture.source/row['source']).read_bytes();path=repo/source
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
                if not target.startswith(e.RUNTIME):index['files'][target]={'source':source,'sha256':e.sha(data)}
            for name in self.ci.REQUIRED_TOOLS:
                source=self.ci.PREFIX+'/tools/'+name;data=(HERE/name).read_bytes();path=repo/source
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
                index['tools'][name]={'source':source,'sha256':e.sha(data)}
            index_path=self.ci.PREFIX+'/public-source-index.json';(repo/index_path).write_bytes(raw(index))
            temp=fixture.base/'runner-temp';temp.mkdir(mode=0o700)
            def git(repo_path,args,maximum=0):
                if args==['rev-parse','--verify','HEAD']:return ('3'*40+'\n').encode()
                if args==['rev-parse','--verify','HEAD^{tree}']:return ('4'*40+'\n').encode()
                self.assertEqual(args[0],'cat-file');self.assertTrue(args[-1].startswith('3'*40+':'))
                data=(repo/args[-1].split(':',1)[1]).read_bytes()
                return (str(len(data))+'\n').encode() if args[1]=='-s' else data
            with mock.patch.object(self.ci,'git',side_effect=git),\
                 mock.patch.object(self.ci,'run_bootstrap_tests',return_value={'success':True,'kind':'SYNTHETIC_RECURSION_BOUNDARY_ONLY'}) as bootstrap,\
                 mock.patch.object(self.ci,'RUNTIME_COMMIT',fixture.map['runtime_source_commit']),\
                 mock.patch.object(self.ci,'RUNTIME_TREE',fixture.map['runtime_source_tree']),\
                 mock.patch.object(self.ci,'RUNTIME_MANIFEST',fixture.map['runtime_manifest_sha256']),\
                 mock.patch.object(sys,'flags',types.SimpleNamespace(isolated=1,no_site=1,verbose=0,optimize=0)),\
                 mock.patch.object(sys,'dont_write_bytecode',True),mock.patch.dict(os.environ,{'RUNNER_TEMP':str(temp)}),\
                 mock.patch.dict(sys.modules):
                for name in ('epoch7_recovery_entry','build_epoch7_kit','audit_epoch7_imports','extract_epoch7_kit'):
                    sys.modules.pop(name,None)
                result=self.ci.generate(str(repo),index_path,self.ci.RUNTIME,str(temp/'run'),'3'*40)
            self.assertTrue(result['success']);self.assertTrue(result['reproducible_build'])
            bootstrap.assert_called_once()
            self.assertTrue(result['verified_archive_roundtrip']);self.assertEqual(result['test_exit_code'],0)
            self.assertEqual(sum(row['tests'] for row in result['tests']['suites']),len(runner.PORTABLE_SUITES))
            self.assertTrue((temp/'run/ci-summary.json').is_file())
        finally:
            self.ci.DEADLINE=None
            fixture.tearDown()


if __name__=='__main__':unittest.main()
