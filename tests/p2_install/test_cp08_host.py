"""Python3.6.8-compatible transport/host API tests; not UK execution proof."""
import copy
import errno
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from production.p2_install import cp08_evidence as e
s=importlib.util.spec_from_file_location('host_wrapper',str(REPO/'scripts/p2_b3_owner_finalize_20261020.py'))
h=importlib.util.module_from_spec(s);s.loader.exec_module(h)


class Transport(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='p2-cp08-api-');self.root=Path(self.tmp.name)
        for name in ('CP07-committed.json','ledger-config.json','profile.json','runtime-invocation.json','expected-identity.json'):
            (self.root/name).write_bytes(name.encode())
        current=e.snapshot(self.root)
        self.context={'request_sha256':'a'*64,'cp03_sha256':'b'*64,
                      'cp07_sha256':current['files']['CP07-committed.json']['sha256'],'host_path':str(self.root)}
        self.current=current
        self.packet={'schema':1,'producer_sha256':e.PRODUCER_SHA,'probe_sha256':e.PROBE_SHA,
          'context':self.context,'before':copy.deepcopy(current),'after':copy.deepcopy(current),
          'command_sha256':'c'*64,'probe':{'schema':1,'context':dict(self.context,metadata=current['target']),
          'target':'/target','uid':65534,'euid':65534,'gid':65534,'groups':[],'errno':errno.EACCES,
          'before':current['target'],'after':current['target']},
          'container':{'id':'d'*64,'image':e.IMAGE,'user':'65534:65534','network':'none',
            'readonly_root':True,'cap_drop':['ALL'],'security_opt':['no-new-privileges'],
            'running':False,'exit_code':0,'command_sha256':'c'*64,
            'mounts':{'/target':{'source':str(self.root),'readonly':True},
                      '/probe/probe.py':{'readonly':True,'sha256':e.PROBE_SHA}}}}

    def tearDown(self):self.tmp.cleanup()

    def test_transport_fixture_is_structurally_bound(self):
        # Synthetic packet validates only the transport contract. Actual OS and
        # root-owned readonly delivery are exercised by the separate Docker E2E.
        self.assertEqual(e.validate(self.packet,self.context,self.current)['status'],'PASS')

    def test_bare_pass_not_observation(self):
        with self.assertRaisesRegex(ValueError,'OBSERVATION_FIELDS'):
            e.validate({'status':'PASS'},self.context,self.current)

    def test_missing_fixed_mount_unavailable(self):
        self.assertEqual(e.load(self.root,'a'*64,'b'*64)['status'],'UNAVAILABLE')

    def test_wrong_context_and_subject_rejected(self):
        cases=[]
        for key in ('request_sha256','cp03_sha256','cp07_sha256','host_path'):
            p=copy.deepcopy(self.packet);p['context'][key]='wrong';cases.append(p)
        for key,value in [('uid',1002),('euid',0),('gid',1002),('groups',[0])]:
            p=copy.deepcopy(self.packet);p['probe'][key]=value;cases.append(p)
        for p in cases:
            with self.assertRaises(ValueError):e.validate(p,self.context,self.current)

    def test_enoent_or_no_denial_not_pass(self):
        for number in (errno.ENOENT,0,None,'13'):
            p=copy.deepcopy(self.packet);p['probe']['errno']=number
            with self.assertRaisesRegex(ValueError,'OBSERVATION_ERRNO_OR_TARGET'):
                e.validate(p,self.context,self.current)

    def test_wrong_code_or_image_rejected(self):
        for key in ('producer_sha256','probe_sha256'):
            p=copy.deepcopy(self.packet);p[key]='f'*64
            with self.assertRaisesRegex(ValueError,'OBSERVATION_PRODUCER'):
                e.validate(p,self.context,self.current)
        p=copy.deepcopy(self.packet);p['container']['image']='other'
        with self.assertRaises(ValueError):e.validate(p,self.context,self.current)

    def test_inode_replacement_and_side_effect_hold(self):
        p=copy.deepcopy(self.packet);p['after']['target']['ino']+=1
        with self.assertRaisesRegex(ValueError,'SIDE_EFFECT_OR_REPLACEMENT'):
            e.validate(p,self.context,self.current)
        changed=copy.deepcopy(self.current);changed['target']['ino']+=1
        with self.assertRaisesRegex(ValueError,'TARGET_CHANGED'):
            e.validate(self.packet,self.context,changed)

    def test_writable_target_or_container_rejected(self):
        for key,value in [('readonly_root',False),('cap_drop',[]),('network','bridge'),('running',True)]:
            p=copy.deepcopy(self.packet);p['container'][key]=value
            with self.assertRaises(ValueError):e.validate(p,self.context,self.current)
        p=copy.deepcopy(self.packet);p['container']['mounts']['/target']['readonly']=False
        with self.assertRaisesRegex(ValueError,'OBSERVATION_MOUNTS'):e.validate(p,self.context,self.current)

    def test_frozen_producer_and_probe_hashes(self):
        self.assertEqual(e.PROBE_SHA,h.PROBE_SHA)
        self.assertEqual(e.PROBE_SHA,h.digest((REPO/'production/p2_install/cp08_probe.py').read_bytes()))
        self.assertEqual(e.PRODUCER_SHA,h.digest((REPO/'scripts/p2_b3_owner_finalize_20261020.py').read_bytes()))


class HostAPI(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory(prefix='p2-host-api-');self.root=Path(self.tmp.name)
    def tearDown(self):
        # Only new test-owned readonly directories; Python3.6's rmtree does not
        # repair permissions, and cap-drop ALL correctly removes DAC override.
        for p in self.root.rglob('*'):
            if p.is_dir():p.chmod(0o700)
        self.tmp.cleanup()

    def test_exact_python_version_when_required(self):
        if os.environ.get('REQUIRE_PYTHON368')=='1':self.assertEqual(sys.version_info[:3],(3,6,8))

    def test_host_guard_keeps_raw_error_without_server_side_effect(self):
        if os.uname().nodename.split('.')[0]==h.HOST:self.skipTest('never run negative host guard on UK')
        result=subprocess.run([sys.executable,'-I','-B','-S',str(REPO/'scripts/p2_b3_owner_finalize_20261020.py'),
           '--bundle','/not-an-input','--bundle-sha256','a'*64],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.assertEqual(result.returncode,2)
        self.assertEqual(json.loads(result.stdout.decode())['reason'],'UK_ROOT_REQUIRED')
        self.assertIn(b'Traceback',result.stderr)

    def test_real_subprocess_io_and_timeout_36_api(self):
        code,out,err=h.command([sys.executable,'-I','-B','-S','-c','print("api")'],self.root,'python')
        self.assertEqual((code,out,err),(0,b'api\n',b''))
        with self.assertRaisesRegex(ValueError,'COMMAND_TIMEOUT_RETAIN_LOGS'):
            h.command([sys.executable,'-c','import time;time.sleep(2)'],self.root,'deadline',timeout=.05)
        self.assertEqual(len(list(self.root.glob('deadline-*'))),2)

    def test_immutable_publish_preserves_original(self):
        target=self.root/'proof.json';h.publish(target,b'original');before=target.stat()
        h.publish(target,b'original');self.assertEqual(before.st_ino,target.stat().st_ino)
        with self.assertRaisesRegex(ValueError,'IMMUTABLE_CONFLICT'):h.publish(target,b'changed')
        self.assertEqual(target.read_bytes(),b'original')

    def bundle(self,name='safe/file.py',link=False):
        buffer=io.BytesIO()
        with tarfile.open(fileobj=buffer,mode='w:gz') as t:
            info=tarfile.TarInfo(name);info.size=1
            if link:info.type=tarfile.SYMTYPE;info.linkname='/etc/passwd'
            t.addfile(info,io.BytesIO(b'x'))
        raw=buffer.getvalue()
        import base64
        return h.canonical({'schema':1,'tar_bytes':len(raw),'tar_sha256':h.digest(raw),
          'files':{name:{'bytes':1,'sha256':h.digest(b'x')}},'tar_b64':base64.b64encode(raw).decode()})

    def test_safe_extract_and_source_resume_without_overwrite(self):
        raw=self.bundle();stage=self.root/'sources';h.unpack(raw,h.digest(raw),stage)
        self.assertEqual((stage/'safe/file.py').read_bytes(),b'x')
        self.assertEqual((stage/'safe/file.py').stat().st_mode & 0o777,0o444)

    def test_traversal_and_special_members_rejected(self):
        for name,link in [('../outside',False),('/absolute',False),('link',True)]:
            raw=self.bundle(name,link)
            with self.assertRaises(ValueError):h.unpack(raw,h.digest(raw),self.root/('stage-'+str(link)+str(len(name))))

    def test_reused_container_extra_authority_and_shared_namespaces_rejected(self):
        config={'Privileged':False,'CapAdd':None,'Devices':[], 'DeviceRequests':None,
                'PidMode':'','IpcMode':'private','UTSMode':'','UsernsMode':''}
        h.validate_runtime_isolation(config)
        for key,value in [('Privileged',True),('CapAdd',['SYS_ADMIN']),('Devices',[{}]),
                          ('DeviceRequests',[{}]),('PidMode','host'),('IpcMode','host'),
                          ('UTSMode','host'),('UsernsMode','host')]:
            changed=dict(config);changed[key]=value
            with self.assertRaisesRegex(ValueError,'EXTRA_AUTHORITY_OR_NAMESPACE'):
                h.validate_runtime_isolation(changed)

    def test_real_main_umask077_publishes_exact_readable_new_files(self):
        # Exercise main itself, including its umask, lock and unpack path.
        # Only the Docker boundary and host identity are replaced in this unit test.
        base=self.root;state=base/'state';state.mkdir()
        lock=state/'.formal-cli.lock';lock.write_bytes(b'');lock.chmod(0o600)
        wrapper=(REPO/'scripts/p2_b3_owner_finalize_20261020.py').read_bytes()
        buffer=io.BytesIO();name='scripts/p2_b3_owner_finalize_20261020.py'
        with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
            info=tarfile.TarInfo(name);info.size=len(wrapper);archive.addfile(info,io.BytesIO(wrapper))
        import base64
        archive=buffer.getvalue();raw=h.canonical({'schema':1,'tar_bytes':len(archive),
            'tar_sha256':h.digest(archive),'files':{name:{'bytes':len(wrapper),'sha256':h.digest(wrapper)}},
            'tar_b64':base64.b64encode(archive).decode()})
        bundle=base/'bundle.json';bundle.write_bytes(raw)
        untouched=base/'existing';untouched.write_bytes(b'old');untouched.chmod(0o400)
        before=untouched.stat();work=base/'new-work'
        def installed(stage,*args):
            target=stage/name
            self.assertEqual(target.stat().st_mode & 0o777,0o444)
            self.assertEqual(target.read_bytes(),wrapper)
            proof=work/'proof.json';h.publish(proof,b'proof')
            self.assertEqual(proof.stat().st_mode & 0o777,0o444)
            return {'status':'UNIT_DOCKER_BOUNDARY_NOT_EXECUTED'}
        old=os.umask(0o022);os.umask(old)
        try:
            with mock.patch.object(h,'BASE',str(base)),mock.patch.object(h,'INPUT',str(work)),mock.patch.object(h,'HOST',os.uname().nodename.split('.')[0]),mock.patch.object(h.os,'getuid',return_value=0),mock.patch.object(h.os,'geteuid',return_value=0),mock.patch.object(h,'command',return_value=(0,(h.IMAGE+'\n').encode(),b'')),mock.patch.object(h,'install',side_effect=installed),mock.patch.object(h.sys,'argv',['host','--bundle',str(bundle),'--bundle-sha256',h.digest(raw)]):
                self.assertEqual(h.main(),0)
            self.assertEqual(untouched.stat(),before)
            self.assertEqual(untouched.read_bytes(),b'old')
        finally:os.umask(old)

    def test_cp03_real_ten_files_and_reserved_directories(self):
        root=self.root/'cp03';root.mkdir(mode=0o700)
        for name in ('activation','data','run'):(root/name).mkdir(mode=0o700)
        for name in ('active.json','epochs.jsonl','activation.lock'):(root/'activation'/name).write_bytes(b'old')
        (root/'.initialize.lock').write_bytes(b'')
        for name in ('intent.json','binding-config.json','commit-receipt.json'):h.publish(root/name,b'old',0o400)
        real_lstat=h.os.lstat
        def owned(path,*args,**kwargs):
            value=real_lstat(path,*args,**kwargs)
            class Info:
                def __getattr__(self,key):return 1002 if key in ('st_uid','st_gid') else getattr(value,key)
            return Info()
        with mock.patch.object(h.os,'lstat',side_effect=owned):
            first=h.prior_snapshot(root)
            self.assertEqual(sum(v['kind']=='FILE' for v in first.values()),10)
            self.assertEqual(sum(v['kind']=='DIRECTORY' for v in first.values()),3)
            self.assertEqual(first,h.prior_snapshot(root))
            (root/'data/ledger.sqlite3').write_bytes(b'unexpected')
            with self.assertRaisesRegex(ValueError,'RESERVED_DIRECTORY_NOT_EMPTY'):h.prior_snapshot(root)
            (root/'data/ledger.sqlite3').unlink()
            (root/'unknown').write_bytes(b'unknown')
            with self.assertRaisesRegex(ValueError,'CP03_UNKNOWN_ITEM'):h.prior_snapshot(root)

    def test_terminal_chain_rechecked_not_cached_success(self):
        previous='a'*64
        for stage in ('CP04','CP05','CP06','CP07','CP08','CP09'):
            row={'stage':stage,'request_sha256':'b'*64,'previous_receipt_sha256':previous,
                 'status':'PREPARATION_CHECKPOINT_COMMITTED'}
            raw=h.canonical(row);(self.root/(stage+'-committed.json')).write_bytes(raw);previous=h.digest(raw)
        raw=h.canonical({'request_sha256':'b'*64,'last_checkpoint_sha256':previous,
             'status':'PREPARATION_COMMITTED','full_b3_complete':False,'service_started':False})
        path=self.root/'preparation-receipt.json';path.write_bytes(raw)
        reference={'path':str(path),'sha256':h.digest(raw)}
        h.verify_terminal(self.root,'b'*64,'a'*64,reference)
        (self.root/'CP09-committed.json').write_bytes(b'{}')
        with self.assertRaises((ValueError,KeyError)):h.verify_terminal(self.root,'b'*64,'a'*64,reference)


if __name__=='__main__':unittest.main()
