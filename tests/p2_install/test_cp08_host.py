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
import tarfile
import tempfile
import unittest

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
