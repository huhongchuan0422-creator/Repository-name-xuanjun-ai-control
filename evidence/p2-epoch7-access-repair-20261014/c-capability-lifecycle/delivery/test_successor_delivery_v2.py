# Versioned R14 test port; original fixed-version test file is unchanged.
"""Finite local adapter/binding/layout tests; no network or actual host operations.

The tar fixture is synthetic, including its non-production entry. Real preparer
source is checked only at the source/binding boundary; prepare is always mocked.
Local filesystem staging is confined to disposable directories beside this file.
"""
import ast
import base64
import contextlib
import copy
import errno
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import time
import types
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
PREPARATION=Path(os.environ.get('EPOCH7_SUCCESSOR_PREPARATION',str(ROOT/'preparation')))
KIT_LEAF='epoch7-recovery-candidate-r7-claim-lifecycle'
PREP_LEAF='epoch7-preparation-candidate-r7-claim-lifecycle-v2-0bd83e6f'
EXPIRY='2030-01-01T00:00:00Z'

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,str(path))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
m=load(HERE/'epoch7_prepare_successor_delivery.py','successor_delivery_under_test')
x=load(HERE/'extract_epoch7_successor_kit.py','successor_extractor_under_test')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def packed(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode('ascii')+b'\n'
def arguments():return ['--operation','prepare','--admission-expires-at-utc',EXPIRY]
def source():return {'epoch7_prepare_successor.py':b'# synthetic preparation source\n'}
def source_pins(cache=None):return {k:(sha(v),len(v)) for k,v in (source() if cache is None else cache).items()}

def fixture(count=256,mode=None,extra_member=None):
    # Stub entry deliberately never imports candidate runtime or accesses host.
    entry=b'''import json\ndef decode(raw):return json.loads(raw.decode('ascii'))\ndef validate_manifest(value):return value\ndef validate_runtime(manifest,files):return {'files':{str(n):'synthetic' for n in range(107)}}\n'''
    files={'epoch7_recovery_entry.py':entry,'helpers/epoch7_claim_successor.py':b'# synthetic claim source\n'}
    files.update({'payload-%03d.txt'%i:b'synthetic payload\n' for i in range(count-2)})
    manifest={'files':{k:sha(v) for k,v in files.items()},'kit_source_commit':'c'*40,'kit_source_tree':'d'*40,
        'production_resume':mode or 'AUTHENTICATED_CLAIM_SUCCESSOR_APPROVAL_GATED_SINGLE_ATTEMPT',
        'status':'CLAIM_SUCCESSOR_CANDIDATE_REQUIRES_NEW_EXACT_APPROVAL'}
    files['recovery-kit-manifest.json']=packed(manifest)
    return archive(files,extra_member=extra_member),files

def archive(files,extra_member=None,root=KIT_LEAF):
    dirs={root}
    for name in files:
        parts=name.split('/')
        for i in range(1,len(parts)):dirs.add(root+'/'+ '/'.join(parts[:i]))
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w',format=tarfile.USTAR_FORMAT) as tar:
        for name in sorted(dirs):
            row=tarfile.TarInfo(name);row.type=tarfile.DIRTYPE;row.mode=0o700;tar.addfile(row)
        for name,raw in sorted(files.items()):
            row=tarfile.TarInfo(root+'/'+name);row.mode=0o444;row.size=len(raw);tar.addfile(row,io.BytesIO(raw))
        if extra_member is not None:tar.addfile(extra_member)
    compressed=io.BytesIO()
    with gzip.GzipFile(fileobj=compressed,mode='wb',mtime=0) as stream:stream.write(out.getvalue())
    return compressed.getvalue()

RAW,FILES=fixture()
PIN_VALUES={'PINS_BOUND':True,'PUBLICATION_COMMIT':'a'*40,'ARCHIVE_COMMIT':'b'*40,
    'ARCHIVE_SHA':sha(RAW),'ARCHIVE_SIZE':len(RAW),'COMPILER_MANIFEST_SHA':sha(FILES['recovery-kit-manifest.json']),
    'COMPILER_ENTRY_SHA':sha(FILES['epoch7_recovery_entry.py']),'COMPILER_ENTRY_BYTES':len(FILES['epoch7_recovery_entry.py']),
    'COMPILER_SOURCE':'c'*40,'COMPILER_TREE':'d'*40,'SOURCES':source_pins()}
@contextlib.contextmanager
def pins(**replacements):
    with contextlib.ExitStack() as stack:
        for name,value in dict(PIN_VALUES,**replacements).items():stack.enter_context(mock.patch.object(m,name,value))
        yield

def mapped(info):
    row={k:getattr(info,k) for k in dir(info) if k.startswith('st_')};row.update(st_uid=0,st_gid=0)
    return types.SimpleNamespace(**row)
def os_proxy():
    row=types.SimpleNamespace(**{k:getattr(os,k) for k in dir(os) if not k.startswith('__')})
    row.fstat=lambda fd:mapped(os.fstat(fd));row.stat=lambda *a,**kw:mapped(os.stat(*a,**kw))
    row.geteuid=lambda:0;row.getegid=lambda:0;return row

def outputs():
    return [{'path':m.CAND+'/'+prefix+pin[:16]+'.private.json','sha256':pin,'bytes':100}
        for prefix,pin in (('epoch7-lifecycle-approved-plan-','1'*64),('epoch7-lifecycle-resume-inputs-','2'*64),('epoch7-lifecycle-review-packet-','3'*64))]
def completed():
    return {'schema':1,'state':'PREPARED_NOT_ADMITTED','outputs':outputs(),
        'kit_manifest_sha256':m.COMPILER_MANIFEST_SHA,'measured_predecessor_sha256':'4'*64,
        'admission_expires_at_utc':EXPIRY,'final_review':'NEW_EXACT_APPROVAL_REQUIRED',
        'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}

class BindingTests(unittest.TestCase):
    def test_saved_candidate_has_exact_pins_and_real_dependency_publication(self):
        self.assertIs(m.PINS_BOUND,True)
        self.assertEqual(m.PUBLICATION_COMMIT,'6e719dd8f43f2a43c41c6437d91ca29fa2b9cef8')
        self.assertEqual(m.ARCHIVE_COMMIT,'6f6133c1b18f203adcc43f57daaee2d23227c86d')
        expected={'ARCHIVE_SHA': '42d6d98f0fb1b1436f348a4ab70b2a9d91dd02e1ad085f49ecb2eb5c096d4465', 'ARCHIVE_SIZE': 1074452, 'COMPILER_MANIFEST_SHA': '1fd0056e449b0abe1075937dbb60968edd620d560b31c36892a6b89ae7ff7a83', 'COMPILER_ENTRY_SHA': '21a982161bc4cb8ffd7e67e4b9a8e24bf23916df6d78c3dd43376af3cfb34890', 'COMPILER_ENTRY_BYTES': 56593, 'COMPILER_SOURCE': '0bd83e6fb418ae04d4351b1de7eaf11a0325dd80', 'COMPILER_TREE': '5d790e58f9f644985fdf063dfc1466eb9b28e66f', 'SOURCES': {'epoch7_prepare_successor.py': ('0bb8c3bd12aa6f0c1f0a99102aa6cff99375a8225c8dc6ba144c0042a664d6ba', 37771)}}
        for name,value in expected.items():self.assertEqual(getattr(m,name),value,name)

    def test_each_missing_pin_blocks_before_network_host_or_staging(self):
        for name in PIN_VALUES:
            with self.subTest(name=name),pins(**{name:False if name=='PINS_BOUND' else None}), \
                 mock.patch.object(m,'fetch_sources') as fetch,mock.patch.object(m.os,'geteuid') as uid, \
                 mock.patch.object(m,'stage') as stage,mock.patch.object(m,'deliver_status') as status:
                self.assertEqual(m.entrypoint(arguments()),2)
                self.assertEqual(status.call_args[0][0]['failure_label'],'UNBOUND')
            fetch.assert_not_called();uid.assert_not_called();stage.assert_not_called()

    def test_malformed_or_boolean_size_and_pin_values_refuse(self):
        for name,value in (('ARCHIVE_SIZE',True),('ARCHIVE_SIZE',33*1024*1024),('COMPILER_ENTRY_BYTES',True),
                ('ARCHIVE_SHA','z'*64),('COMPILER_TREE','x'*40),('SOURCES',{'wrong.py':('f'*64,1)}),
                ('SOURCES',{'epoch7_prepare_successor.py':('f'*64,True)})):
            with self.subTest(name=name,value=value),pins(**{name:value}),self.assertRaisesRegex(m.Hold,'UNBOUND'):m.bound()

    def test_input_contract_is_read_only_and_complete(self):
        with mock.patch.object(m.os,'open',side_effect=AssertionError('host read')), \
             mock.patch.object(m,'fetch_sources',side_effect=AssertionError('network')),mock.patch.object(m,'deliver_status') as status:
            self.assertEqual(m.entrypoint(['--operation','input-contract']),0)
        row=status.call_args[0][0]
        self.assertEqual(row['state'],'BOUND_REQUIRES_SEPARATE_AUTHORIZATION')
        with mock.patch.object(m,'PINS_BOUND',False),mock.patch.object(m,'PUBLICATION_COMMIT',None),mock.patch.object(m,'ARCHIVE_COMMIT',None),mock.patch.object(m,'deliver_status') as status:
            self.assertEqual(m.entrypoint(['--operation','input-contract']),0)
        self.assertEqual(status.call_args[0][0]['state'],'UNBOUND_NOT_AUTHORIZED')
        self.assertEqual((row['archive_files'],row['source_files'],row['runtime_payloads'],row['business_phases']),(257,256,107,16))
        self.assertEqual(row['preparation_root'],m.CAND+'/'+PREP_LEAF)
        self.assertEqual(row['successor_kit_root'],m.CAND+'/'+m.COMPILER_PARENT_LEAF+'/'+KIT_LEAF)

    def test_extra_cli_pin_path_approval_and_resume_options_refuse(self):
        for flag in ('--approval-id','--archive','--source-commit','--new-root','--resume'):
            with self.subTest(flag=flag),mock.patch.object(m,'deliver_status') as status:
                self.assertEqual(m.entrypoint(arguments()+[flag,'override']),2)
            self.assertEqual(status.call_args[0][0]['failure_label'],'ARGUMENTS')

    def test_source_set_size_and_bytes_are_exact(self):
        with pins():
            self.assertEqual(m.validate_sources(source()),source())
            for value in ({},dict(source(),extra=b'x'),{'epoch7_prepare_successor.py':b'x'}, {'epoch7_prepare_successor.py':source()['epoch7_prepare_successor.py']+b'x'}):
                with self.assertRaises(m.Hold):m.validate_sources(value)

    def test_embedded_extractor_matches_own_shipped_source(self):
        self.assertEqual(m.safe_extractor_bytes(),(HERE/'extract_epoch7_successor_kit.py').read_bytes())
        with mock.patch.object(m,'EXTRACTOR_Z',m.EXTRACTOR_Z+'junk'),self.assertRaises(Exception):m.safe_extractor_bytes()

    def test_real_preparer_bindings_match_and_explicit_unbound_source_refuses(self):
        raw=(PREPARATION/'epoch7_prepare_successor.py').read_bytes()
        cache={'epoch7_prepare_successor.py':raw}
        with mock.patch.object(m.os,'open',side_effect=AssertionError('host read')):
            self.assertEqual(m.preparer(cache).NEW_SOURCE,m.COMPILER_SOURCE)
        tree=ast.parse(raw)
        source=next(row for row in tree.body if isinstance(row,ast.Assign) and
                    isinstance(row.targets[0],ast.Name) and row.targets[0].id=='NEW_SOURCE')
        lines=raw.decode('ascii').splitlines(True);lines[source.lineno-1]='NEW_SOURCE = None\n'
        unbound={'epoch7_prepare_successor.py':''.join(lines).encode('ascii')}
        with mock.patch.object(m,'SOURCES',source_pins(unbound)),mock.patch.object(m.os,'open',side_effect=AssertionError('host read')):
            with self.assertRaises(Exception) as caught:m.preparer(unbound)
        self.assertEqual(caught.exception.args,('SUCCESSOR_ARTIFACT_UNBOUND',))

    def test_bound_preparer_must_match_fixed_dependency_contract(self):
        vals={'CAND':m.CAND,'HOST':m.HOST,'OLD_ROOT':m.KIT_ROOT,'NEW_ROOT':m.COMPILER_ROOT,
            'NEW_KIT_SHA':PIN_VALUES['COMPILER_MANIFEST_SHA'],'NEW_ENTRY_SHA':PIN_VALUES['COMPILER_ENTRY_SHA'],
            'NEW_ENTRY_BYTES':PIN_VALUES['COMPILER_ENTRY_BYTES'],'NEW_SOURCE':'c'*40,'NEW_TREE':'d'*40,'SECONDS':120}
        for change in (None,'NEW_ROOT','OLD_ROOT','NEW_ENTRY_SHA','SECONDS'):
            row=dict(vals)
            if change is not None:row[change]='wrong'
            code=('\n'.join(k+'='+repr(v) for k,v in row.items())+'\ndef require_binding():pass\ndef prepare(*a):pass\ndef budget(*a):pass\ndef cleanup_unknown(e):return False\n').encode('ascii')
            cache={'epoch7_prepare_successor.py':code}
            with self.subTest(change=change),pins(SOURCES=source_pins(cache)):
                if change is None:self.assertEqual(m.preparer(cache).NEW_ROOT,m.COMPILER_ROOT)
                else:
                    with self.assertRaisesRegex(m.Hold,'PREPARER_BINDING'):m.preparer(cache)

class BudgetTests(unittest.TestCase):
    def test_deadline_is_one_shot_with_terminal_monotonic_check(self):
        with mock.patch.object(m.signal,'getitimer',return_value=(0.0,0.0)), \
             mock.patch.object(m.signal,'getsignal',return_value='previous'), \
             mock.patch.object(m.signal,'signal') as handler, \
             mock.patch.object(m.signal,'setitimer') as timer, \
             mock.patch.object(m.time,'monotonic',side_effect=[100.0,101.0]):
            with m.budget(60) as end:self.assertEqual(end,160.0)
        self.assertEqual(timer.call_args_list,[mock.call(m.signal.ITIMER_REAL,60,0),mock.call(m.signal.ITIMER_REAL,0)])
        self.assertEqual(handler.call_args_list[-1],mock.call(m.signal.SIGALRM,'previous'))

    def test_deadline_delayed_callback_is_caught_by_terminal_check(self):
        with mock.patch.object(m.signal,'getitimer',return_value=(0.0,0.0)), \
             mock.patch.object(m.signal,'getsignal',return_value='previous'), \
             mock.patch.object(m.signal,'signal'),mock.patch.object(m.signal,'setitimer'), \
             mock.patch.object(m.time,'monotonic',side_effect=[100.0,161.0]):
            with self.assertRaisesRegex(m.Hold,'DEADLINE'):
                with m.budget(60):pass

    def test_primary_timeout_survives_timer_cleanup_failure(self):
        primary=m.DeadlineError()
        with mock.patch.object(m.signal,'getitimer',return_value=(0.0,0.0)), \
             mock.patch.object(m.signal,'getsignal',return_value='previous'), \
             mock.patch.object(m.signal,'signal') as handler, \
             mock.patch.object(m.signal,'setitimer',side_effect=[None,OSError('private cleanup')]) as timer:
            with self.assertRaises(m.DeadlineError) as caught:
                with m.budget(60):raise primary
        self.assertIs(caught.exception,primary);self.assertTrue(primary.delivery_cleanup_failed)
        self.assertEqual(handler.call_args_list[-1],mock.call(m.signal.SIGALRM,'previous'))
        self.assertEqual(timer.call_args_list[0],mock.call(m.signal.ITIMER_REAL,60,0))

    def test_existing_timer_refuses_without_overriding_handler(self):
        with mock.patch.object(m.signal,'getitimer',return_value=(1.0,0.0)), \
             mock.patch.object(m.signal,'signal') as handler, \
             mock.patch.object(m.signal,'setitimer') as timer:
            with self.assertRaisesRegex(m.Hold,'EXISTING_TIMER'):
                with m.budget(60):pass
        handler.assert_not_called();timer.assert_not_called()


class DownloadTests(unittest.TestCase):
    def response(self,raw,url):
        return types.SimpleNamespace(status=200,geturl=lambda:url,headers={'Content-Length':str(len(raw))},read=mock.Mock(return_value=raw),close=mock.Mock())
    def fetch(self,response,kind):
        opener=types.SimpleNamespace(open=mock.Mock(return_value=response))
        with pins(),mock.patch.object(m.urllib.request,'build_opener',return_value=opener):
            result=(m.fetch_archive if kind=='archive' else m.fetch_sources)(time.monotonic()+10)
        return result,opener
    def test_archive_download_is_exact_bounded_and_closed(self):
        row=self.response(RAW,m.RAW_PREFIX+'b'*40+'/'+m.ARCHIVE_PATH)
        result,opener=self.fetch(row,'archive');self.assertEqual(result,RAW)
        row.read.assert_called_once_with(len(RAW)+1);row.close.assert_called_once_with()
        request=opener.open.call_args[0][0];self.assertEqual(request.get_header('Accept-encoding'),'identity')
        self.assertLessEqual(opener.open.call_args[1]['timeout'],10)
    def test_single_preparer_download_uses_exact_publication_path(self):
        raw=source()['epoch7_prepare_successor.py'];url=m.RAW_PREFIX+'a'*40+'/'+m.PUBLIC_PREFIX+'epoch7_prepare_successor.py'
        row=self.response(raw,url);result,opener=self.fetch(row,'source');self.assertEqual(result,source())
        self.assertEqual(opener.open.call_args[0][0].full_url,url);row.read.assert_called_once_with(len(raw)+1)
    def test_redirect_body_length_encoding_and_status_fail_closed(self):
        for change in ('redirect','body','length','encoding','status','oversize'):
            row=self.response(RAW,m.RAW_PREFIX+'b'*40+'/'+m.ARCHIVE_PATH)
            if change=='redirect':row.geturl=lambda:'https://unapproved.invalid/'
            elif change=='body':row.read.return_value=b'x'+RAW[1:]
            elif change=='length':row.headers['Content-Length']='1'
            elif change=='encoding':row.headers['Content-Encoding']='gzip'
            elif change=='status':row.status=302
            else:row.read.return_value=RAW+b'x'
            with self.subTest(change=change),self.assertRaises(m.Hold):self.fetch(row,'archive')
            row.close.assert_called_once_with()
    def test_primary_download_error_survives_close_failure(self):
        row=self.response(RAW,m.RAW_PREFIX+'b'*40+'/'+m.ARCHIVE_PATH)
        primary=OSError(errno.EIO,'private download');row.read.side_effect=primary;row.close.side_effect=OSError('private close')
        with self.assertRaises(OSError) as caught:self.fetch(row,'archive')
        self.assertIs(caught.exception,primary);self.assertTrue(primary.delivery_cleanup_failed)

class ArchiveBoundaryTests(unittest.TestCase):
    def test_successor_root_modes_counts_and_source_identity_are_exact(self):
        with pins():extractor,entry,files=m.compiler_inputs(RAW)
        self.assertEqual(extractor.ROOT_NAME,KIT_LEAF);self.assertEqual(len(files),257)
        self.assertEqual(entry.__file__,m.COMPILER_ROOT+'/epoch7_recovery_entry.py')
        self.assertEqual(len(files)-1,m.COMPILER_CACHE_COUNT)
    def test_wrong_hash_truncation_and_oversize_refuse_before_extractor(self):
        with pins(),mock.patch.object(m,'safe_extractor_bytes') as parser:
            for raw in (RAW[:-1],b'x'+RAW[1:],RAW+b'x','not bytes'):
                with self.assertRaises(m.Hold):m.compiler_inputs(raw)
            parser.assert_not_called()
    def test_missing_file_extra_member_link_and_wrong_root_refuse(self):
        broken=dict(FILES);broken.pop('payload-000.txt')
        link=tarfile.TarInfo(KIT_LEAF+'/link');link.type=tarfile.SYMTYPE;link.linkname='/private'
        for raw in (archive(broken),archive(FILES,extra_member=link),archive(FILES,root='wrong-root')):
            with self.assertRaises(ValueError):x.inspect_archive(raw,sha(raw),sha(FILES['epoch7_recovery_entry.py']),sha(FILES['recovery-kit-manifest.json']))
    def test_non_successor_composed_mode_refuses(self):
        raw,files=fixture(mode='AUTHENTICATED_APPROVAL_GATED_SINGLE_ATTEMPT')
        with self.assertRaises(ValueError):x.inspect_archive(raw,sha(raw),sha(files['epoch7_recovery_entry.py']),sha(files['recovery-kit-manifest.json']))
    def test_wrong_total_cache_count_refuses(self):
        raw,files=fixture(count=255)
        with pins(ARCHIVE_SHA=sha(raw),ARCHIVE_SIZE=len(raw),COMPILER_MANIFEST_SHA=sha(files['recovery-kit-manifest.json'])),self.assertRaisesRegex(m.Hold,'COMPILER_CACHE'):m.compiler_inputs(raw)
    def test_wrong_source_commit_and_entry_size_refuse(self):
        for key,value in (('COMPILER_SOURCE','e'*40),('COMPILER_TREE','e'*40),('COMPILER_ENTRY_BYTES',1)):
            with self.subTest(key=key),pins(**{key:value}),self.assertRaises(m.Hold):m.compiler_inputs(RAW)
    def test_refused_manifest_cannot_masquerade_as_successor_candidate(self):
        files=dict(FILES);manifest=json.loads(files['recovery-kit-manifest.json'].decode('ascii'))
        manifest.update(production_resume='REFUSED_UNCOMPOSED',status='SOURCE_KIT_GROUNDWORK_NOT_INSTALL_ADMISSION')
        files['recovery-kit-manifest.json']=packed(manifest);raw=archive(files)
        with pins(ARCHIVE_SHA=sha(raw),ARCHIVE_SIZE=len(raw),COMPILER_MANIFEST_SHA=sha(files['recovery-kit-manifest.json'])),self.assertRaisesRegex(m.Hold,'COMPILER_SOURCE'):m.compiler_inputs(raw)

    def test_changed_runtime_payload_count_refuses(self):
        files=dict(FILES);files['epoch7_recovery_entry.py']=files['epoch7_recovery_entry.py'].replace(b'range(107)',b'range(106)')
        manifest=json.loads(files['recovery-kit-manifest.json'].decode('ascii'));manifest['files']['epoch7_recovery_entry.py']=sha(files['epoch7_recovery_entry.py'])
        files['recovery-kit-manifest.json']=packed(manifest);raw=archive(files)
        with pins(ARCHIVE_SHA=sha(raw),ARCHIVE_SIZE=len(raw),COMPILER_MANIFEST_SHA=sha(files['recovery-kit-manifest.json']),COMPILER_ENTRY_SHA=sha(files['epoch7_recovery_entry.py'])),self.assertRaisesRegex(m.Hold,'RUNTIME_SCOPE'):m.compiler_inputs(raw)

    def test_bad_archive_cannot_create_destination(self):
        with mock.patch.object(x.os,'mkdir') as mkdir,self.assertRaises(ValueError):
            x.extract(RAW+b'bad','/does-not-exist/'+KIT_LEAF,sha(RAW),sha(FILES['epoch7_recovery_entry.py']),sha(FILES['recovery-kit-manifest.json']))
        mkdir.assert_not_called()

class LocalStagingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='local-delivery-test-',dir=str(HERE));self.addCleanup(self.temp.cleanup)
        self.parent=Path(self.temp.name);self.proxy=os_proxy()
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        for name,value in (('CAND',str(self.parent)),('PREP_ROOT',str(self.parent/PREP_LEAF)),
                ('COMPILER_PARENT',str(self.parent/m.COMPILER_PARENT_LEAF)),
                ('COMPILER_ROOT',str(self.parent/m.COMPILER_PARENT_LEAF/KIT_LEAF)),('os',self.proxy)):
            self.stack.enter_context(mock.patch.object(m,name,value))
        self.stack.enter_context(pins())
    def stage(self,**kwargs):return m.stage(source(),time.monotonic()+10,**kwargs)
    def test_new_one_file_preparation_and_exact_existing_reuse(self):
        row=self.stage();self.assertEqual(row['state'],'STAGED_EXACT')
        dest=self.parent/PREP_LEAF;self.assertEqual([p.name for p in dest.iterdir()],['epoch7_prepare_successor.py'])
        self.assertEqual(stat.S_IMODE(dest.stat().st_mode),0o700)
        self.assertEqual(stat.S_IMODE((dest/'epoch7_prepare_successor.py').stat().st_mode),0o600)
        with mock.patch.object(self.proxy,'write',side_effect=AssertionError('no write')),mock.patch.object(self.proxy,'mkdir',side_effect=AssertionError('no mkdir')):
            self.assertEqual(self.stage()['state'],'REUSED_EXACT')
    def test_partial_preparation_directory_is_never_repaired(self):
        dest=self.parent/PREP_LEAF;dest.mkdir(mode=0o700)
        with mock.patch.object(self.proxy,'write') as write,mock.patch.object(self.proxy,'mkdir') as mkdir,self.assertRaises(m.Hold):self.stage()
        write.assert_not_called();mkdir.assert_not_called();self.assertEqual(list(dest.iterdir()),[])
    def test_wrong_existing_bytes_modes_and_extra_file_refuse(self):
        self.stage();dest=self.parent/PREP_LEAF;file=dest/'epoch7_prepare_successor.py'
        file.write_bytes(b'wrong')
        with self.assertRaises(m.Hold):self.stage()
        file.write_bytes(source()[file.name]);file.chmod(0o644)
        with self.assertRaises(m.Hold):self.stage()
        file.chmod(0o600);(dest/'extra').write_bytes(b'extra')
        with self.assertRaises(m.Hold):self.stage()
    def test_partial_source_write_is_retained_and_cannot_be_retried_as_repair(self):
        with mock.patch.object(self.proxy,'write',side_effect=OSError(errno.ENOSPC,'private disk')),self.assertRaises(OSError) as caught:self.stage()
        paths=caught.exception.delivery_created_paths
        self.assertEqual(paths,[m.PREP_ROOT,m.PREP_ROOT+'/epoch7_prepare_successor.py'])
        self.assertEqual((self.parent/PREP_LEAF/'epoch7_prepare_successor.py').read_bytes(),b'')
        with mock.patch.object(self.proxy,'write') as write,self.assertRaises(m.Hold):self.stage()
        write.assert_not_called()
    def test_post_prepare_recheck_cannot_create_missing_source_root(self):
        with mock.patch.object(self.proxy,'mkdir') as mkdir,self.assertRaises(m.Hold):self.stage(allow_create=False)
        mkdir.assert_not_called()
    def test_existing_kit_is_verified_without_extraction_or_repair(self):
        (self.parent/m.COMPILER_PARENT_LEAF).mkdir(mode=0o700)
        (self.parent/m.COMPILER_PARENT_LEAF/KIT_LEAF).mkdir(mode=0o700)
        extractor=types.SimpleNamespace(ProtectedDirectory=x.ProtectedDirectory,extract=mock.Mock())
        with mock.patch.object(x,'os',self.proxy),mock.patch.object(m,'verify_compiler',side_effect=m.Hold('COMPILER_RECHECK')),self.assertRaises(m.Hold) as caught:
            m.stage_compiler(RAW,extractor,object(),FILES,time.monotonic()+10)
        extractor.extract.assert_not_called();self.assertEqual(caught.exception.compiler_staging['state'],'VERIFY_EXISTING_FAILED')
    def test_synthetic_kit_extracts_exactly_and_reuse_has_no_writes(self):
        destination=self.parent/m.COMPILER_PARENT_LEAF/KIT_LEAF
        def verified(root,digest):
            self.assertEqual(root,str(destination));self.assertEqual(digest,PIN_VALUES['COMPILER_MANIFEST_SHA'])
            actual={str(p.relative_to(destination)):p.read_bytes() for p in destination.rglob('*') if p.is_file()}
            self.assertEqual(actual,FILES)
            for path in destination.rglob('*'):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o700 if path.is_dir() else 0o444)
            manifest=json.loads(actual.pop('recovery-kit-manifest.json').decode('ascii'))
            return types.SimpleNamespace(cache=actual,manifest=manifest)
        entry=types.SimpleNamespace(verify_kit=verified)
        with mock.patch.object(x,'os',self.proxy):
            result=m.stage_compiler(RAW,x,entry,FILES,time.monotonic()+10)
            self.assertEqual(result['state'],'EXTRACTED_AND_VERIFIED')
            with mock.patch.object(x,'extract',side_effect=AssertionError('no repair')),mock.patch.object(self.proxy,'write',side_effect=AssertionError('no write')):
                result=m.stage_compiler(RAW,x,entry,FILES,time.monotonic()+10)
        self.assertEqual(result['state'],'VERIFIED_EXISTING')

    def test_kit_partial_extraction_is_preserved_and_reported(self):
        def partial(*args):
            (self.parent/m.COMPILER_PARENT_LEAF/KIT_LEAF).mkdir(mode=0o700);raise OSError(errno.ENOSPC,'private disk')
        extractor=types.SimpleNamespace(ProtectedDirectory=x.ProtectedDirectory,extract=mock.Mock(side_effect=partial))
        with mock.patch.object(x,'os',self.proxy),self.assertRaises(OSError) as caught:
            m.stage_compiler(RAW,extractor,object(),FILES,time.monotonic()+10)
        self.assertTrue((self.parent/m.COMPILER_PARENT_LEAF/KIT_LEAF).exists());self.assertTrue(caught.exception.delivery_cleanup_failed)
        self.assertEqual(caught.exception.compiler_staging['state'],'EXTRACTION_ATTEMPTED_NOT_VERIFIED')
    def test_old_siblings_are_not_touched(self):
        markers=[]
        for leaf in ('epoch7-preparation-candidate-r7-resourcebind',
                     'epoch7-recovery-candidate-r7-resourcebind',
                     'epoch7-preparation-candidate-r7-claim-successor',
                     'epoch7-recovery-candidate-r7-claim-successor'):
            old=self.parent/leaf;old.mkdir(mode=0o700)
            marker=old/'original';marker.write_bytes(b'retained');markers.append((marker,marker.stat()))
        self.stage()
        for marker,before in markers:
            self.assertEqual(marker.read_bytes(),b'retained');self.assertEqual(marker.stat(),before)

class FlowTests(unittest.TestCase):
    def invoke(self,fail=None,result_change=None):
        events=[];scope_seconds=[];status=[]
        staged={'state':'STAGED_EXACT','path':m.PREP_ROOT,'files':{k:{'sha256':v[0],'bytes':v[1]} for k,v in source_pins().items()},
            'created_paths':[m.PREP_ROOT,m.PREP_ROOT+'/epoch7_prepare_successor.py']}
        class PrepHold(Exception):pass
        class PrepCleanup(Exception):pass
        @contextlib.contextmanager
        def scope(seconds):
            scope_seconds.append(seconds);yield time.monotonic()+seconds
            if fail=='budget_close' and seconds==120:raise PrepCleanup()
        module=types.SimpleNamespace(SECONDS=120,budget=scope,CleanupError=PrepCleanup,Hold=PrepHold,
            cleanup_unknown=lambda error:isinstance(error,(OSError,PrepCleanup)))
        def event(name,value):
            events.append(name)
            if fail==name:raise OSError(errno.EIO,'private unsafe detail')
            return value
        def prepare(expiry,end):
            result=event('prepare',completed())
            if result_change:result_change(result)
            return result
        module.prepare=mock.Mock(side_effect=prepare)
        with pins(),contextlib.ExitStack() as stack:
            replacements={'budget':scope,'fetch_sources':lambda end:event('download_sources',source()),
                'fetch_archive':lambda end:event('download_archive',RAW),
                'compiler_inputs':lambda raw:event('authenticate_archive',(object(),object(),FILES)),
                'preparer':lambda cache:event('load_preparer',module),
                'stage_compiler':lambda *a:event('stage_kit',m.compiler_summary('EXTRACTED_AND_VERIFIED')),
                'stage':lambda cache,end,allow_create=True:event('stage_preparation' if allow_create else 'recheck_preparation',staged),
                'verify_compiler':lambda *a:event('recheck_kit',None),'deliver_status':lambda value:status.append(value)}
            for name,value in replacements.items():stack.enter_context(mock.patch.object(m,name,value))
            stack.enter_context(mock.patch.object(m.os,'geteuid',return_value=0));stack.enter_context(mock.patch.object(m.os,'getegid',return_value=0))
            stack.enter_context(mock.patch.object(m.socket,'gethostname',return_value=m.HOST))
            stack.enter_context(mock.patch.object(m.sys,'flags',types.SimpleNamespace(isolated=1,no_site=1)))
            stack.enter_context(mock.patch.object(m.sys,'dont_write_bytecode',True))
            code=m.entrypoint(arguments())
        self.assertEqual(len(status),1)
        return code,events,module,status[0],scope_seconds
    def test_whole_archive_precedes_creations_then_exactly_one_prepare(self):
        code,events,module,status,seconds=self.invoke()
        self.assertEqual(code,0);self.assertEqual(events,['download_sources','download_archive','authenticate_archive','load_preparer','stage_kit','stage_preparation','prepare','recheck_preparation','recheck_kit'])
        module.prepare.assert_called_once();self.assertEqual(module.prepare.call_args[0][0],EXPIRY)
        self.assertEqual(seconds,[60,120]);self.assertEqual(status['state'],'PREPARED_NOT_ADMITTED')
    def test_each_preparation_prerequisite_failure_stops_without_retry(self):
        for name in ('download_sources','download_archive','authenticate_archive','load_preparer','stage_kit','stage_preparation'):
            with self.subTest(name=name):
                code,events,module,status,unused=self.invoke(fail=name)
                self.assertEqual(code,2);self.assertEqual(events[-1],name);module.prepare.assert_not_called()
                self.assertNotIn('private unsafe detail',json.dumps(status))
    def test_prepare_failure_is_not_retried_and_preserves_staging(self):
        code,events,module,status,unused=self.invoke(fail='prepare')
        self.assertEqual(code,2);module.prepare.assert_called_once();self.assertEqual(events[-1],'prepare')
        self.assertEqual(len(status['created_paths']),2);self.assertIsNotNone(status['compiler_staging'])
    def test_all_late_failures_retain_three_outputs_and_both_stagings(self):
        for name in ('recheck_preparation','recheck_kit','budget_close'):
            with self.subTest(name=name):
                code,events,module,status,unused=self.invoke(fail=name)
                self.assertEqual(code,2);self.assertEqual(status['completed_outputs'],outputs())
                self.assertEqual(len(status['created_paths']),2);self.assertIsNotNone(status['compiler_staging']);module.prepare.assert_called_once()
    def test_unexpected_result_field_or_authority_claim_refuses(self):
        for change in (lambda row:row.update(private='never echo'),lambda row:row.update(install_admission='GRANTED'),lambda row:row.update(final_review='APPROVED')):
            code,events,module,status,unused=self.invoke(result_change=change)
            self.assertEqual(code,2);self.assertEqual(status['install_admission'],'NOT_GRANTED');self.assertNotIn('never echo',json.dumps(status))
    def test_duplicate_output_kind_refuses_even_with_three_distinct_hashes(self):
        def change(row):
            row['outputs'][1]['path']=m.CAND+'/epoch7-lifecycle-approved-plan-'+'2'*16+'.private.json'
        code,events,module,status,unused=self.invoke(result_change=change)
        self.assertEqual(code,2);self.assertEqual(status['preparation_output_evidence'],'UNKNOWN')
    def test_private_output_metadata_cannot_escape_fixed_parent_or_hash_prefix(self):
        for change in ('parent','hash','size'):
            error=types.SimpleNamespace(preparation_created_paths=[row['path'] for row in outputs()],preparation_outputs=outputs())
            if change=='parent':error.preparation_created_paths[0]='/private/secret'
            elif change=='hash':error.preparation_outputs[0]['sha256']='9'*64
            else:error.preparation_outputs[0]['bytes']=True
            with self.subTest(change=change),self.assertRaises(m.Hold):m.retained_outputs(error)
    def test_preparer_cleanup_classifier_retains_nested_cleanup_uncertainty(self):
        prep=load(PREPARATION/'epoch7_prepare_successor.py','real_unbound_preparer_classifier')
        error=ValueError('private primary');error.__cause__=OSError(errno.EIO,'private cleanup')
        row=m.failure(error,'PREPARE_PRIVATE_PLAN',prep,frozenset())
        self.assertTrue(row['cleanup_unknown']);self.assertNotIn('private',json.dumps(row))

    def test_preparer_unclassified_io_is_conservatively_unknown(self):
        code,events,module,status,unused=self.invoke(fail='prepare')
        self.assertEqual(code,2);self.assertTrue(status['cleanup_unknown'])

    def test_flow_registers_only_fixed_authenticated_public_source_literals(self):
        added={'helpers/epoch7_snapshot.py':b"raise ValueError('PREDECESSOR_PUBLIC_SENTINEL')\n",
            'unknown/private.py':b"raise ValueError('PRIVATE_UNLISTED_SENTINEL')\n"}
        with mock.patch.dict(FILES,added),mock.patch.object(m,'public_labels',wraps=m.public_labels) as labels:
            self.invoke(fail='prepare')
        cache=labels.call_args[0][0]
        self.assertIn('epoch7_prepare_successor.py',cache)
        self.assertIn('helpers/epoch7_snapshot.py',cache)
        self.assertNotIn('unknown/private.py',cache)
        self.assertIn('PREDECESSOR_PUBLIC_SENTINEL',m.public_labels(cache))
        self.assertNotIn('PRIVATE_UNLISTED_SENTINEL',m.public_labels(cache))

    def test_preparer_hold_and_successor_prefix_have_safe_labels_and_source_frames(self):
        class PrepHold(Exception):pass
        prep=types.SimpleNamespace(Hold=PrepHold,cleanup_unknown=lambda error:False)
        raw=b"raise Hold('STATIC_PREP_CODE')\n"
        labels=m.public_labels({'epoch7_prepare_successor.py':raw,'claim':b"code='EXPIRY_FORMAT'\n"})
        try:exec(compile(raw,m.PREP_ROOT+'/epoch7_prepare_successor.py','exec'),{'Hold':PrepHold})
        except PrepHold as error:row=m.failure(error,'PREPARE_PRIVATE_PLAN',prep,labels)
        self.assertEqual(row['failure_label'],'STATIC_PREP_CODE')
        self.assertEqual(row['code_locations'],[{'source':'preparation/epoch7_prepare_successor.py','line':1}])
        row=m.failure(ValueError('CLAIM_SUCCESSOR_EXPIRY_FORMAT'),'PREPARE_PRIVATE_PLAN',prep,labels)
        self.assertEqual(row['failure_label'],'CLAIM_SUCCESSOR_EXPIRY_FORMAT')

    def test_diagnostic_drops_unrecognized_labels_and_private_trace_paths(self):
        error=ValueError('private-secret')
        status=m.failure(error,'PREPARE_PRIVATE_PLAN',None,frozenset())
        self.assertIsNone(status['failure_label']);self.assertEqual(status['code_locations'],[])
        self.assertNotIn('private-secret',json.dumps(status))

if __name__=='__main__':unittest.main(verbosity=2)
