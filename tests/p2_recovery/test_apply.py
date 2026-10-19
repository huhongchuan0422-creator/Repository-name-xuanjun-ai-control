"""Real RSA/socket/SQLite and original registry/issuer. Synthetic host facts ONLY."""
import base64
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import struct
import subprocess
import sys
import tarfile
import io
import threading
import time
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_recovery as fixtures
r = fixtures.r
CORE = ROOT / 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/attempt5'
sys.path[:0] = [str(CORE/'runtime'), str(CORE/'original'), str(CORE),
    str(CORE.parent/'kit-overlay/helpers'),
    str(ROOT/'evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers')]
import authority_store
import authorization
import receipt_provider
import epoch7_approval
from permit_cycle import policy
from test_authority_store import grant


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem + '_tests', str(path))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


e = module(ROOT/'production/p2_recovery/executor.py')
e.r = r
assembly = module(ROOT/'production/p2_attempt5/assembly.py')
registry = module(ROOT/'production/p2_attempt5/registry.py')


class ApplyTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RecoveryTests.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.RecoveryTests.tearDownClass.__func__)
    write = fixtures.RecoveryTests.write
    signed = fixtures.RecoveryTests.signed

    def setUp(self):
        fixtures.RecoveryTests.setUp(self)
        uname = os.uname()
        self.addCleanup(mock.patch.stopall)
        mock.patch('os.uname', return_value=os.uname_result((uname.sysname, r.HOST,
            uname.release, uname.version, uname.machine))).start()
        for name in ('checkpoint', 'registry', 'db', 'assembly'):
            os.mkdir(self.root+'/'+name, 0o700)
        self.request['new_grant_id'] = 'recovery-new-grant-0002'
        self.request['target_database'] = self.root + '/db/authority.sqlite3'
        self.body['issued_utc'] = int(time.time())-1
        self.body['expires_utc'] = int(time.time())+290
        self.body['request_sha256'] = r.sha(r.canonical(self.request))
        files = {}
        for prefix in ('production/p2_attempt5', 'production/p2_recovery'):
            for p in (ROOT/prefix).glob('*.py'):
                relative = str(p.relative_to(ROOT))
                dest = Path(self.root)/'assembly'/relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.chmod(str(dest.parent), 0o700)
                os.chmod(str(dest.parent.parent), 0o700)
                dest.write_bytes(p.read_bytes())
                os.chmod(str(dest), 0o600)
                files[relative] = r.sha(p.read_bytes())
        mock.patch.object(e, '__file__', self.root+'/assembly/production/p2_recovery/executor.py').start()
        self.manifest = {'schema':1, 'source_commit':'1'*40,'source_tree':'2'*40,
            'inherited_manifest_sha256':'3'*64, 'runtime_source_commit':r.SOURCE,
            'runtime_source_tree':r.TREE, 'files':files}
        m = self.write('assembly/MANIFEST.json', r.canonical(self.manifest))
        self.g = grant()
        self.g.update(grant_id=self.request['new_grant_id'], source_commit='1'*40,
            source_tree='2'*40, manifest_sha256=m['sha256'], target_host=r.HOST,
            recovery_entry='p2_recovery.entry',
            actor_id='fixture-actor', expires_utc=int(time.time())+1000)
        signer = assembly.OpenSSLSigner(self.private['owner'], self.refs['owner']['der_sha256'])
        try:
            provider = receipt_provider.ReceiptProvider(lambda unused: None, signer.modulus,
                                                       65537, 'RECOVERY_SYNTHETIC')
        finally:
            signer.close()
        self.policy = policy()
        wanted = authorization.expected(self.g, provider, self.policy, owner=True)
        body = authorization.OWNER_MARKER + receipt_provider.canonical(wanted).decode('utf-8')
        self.g['approval_body_sha256'] = r.sha(body.encode())
        self.approval = {'id':9000000099, 'user':{'id':authorization.OWNER_ID,
            'login':authorization.OWNER_LOGIN}, 'issue_url':'https://api.github.com/repos/'+
            authorization.REPO+'/issues/17', 'body':body}
        self.cfg = {'schema':1,'database':self.request['target_database'],
            'socket':self.root+'/issuer.sock', 'principal':{'host':r.HOST,
                'actor_id':'fixture-actor','writer_id':self.request['writer_id']},
            'key':self.private['owner'],'public_der_sha256':self.refs['owner']['der_sha256'],
            'issuer':'RECOVERY_SYNTHETIC', 'adapter_path':self.root+'/assembly/production/p2_attempt5/native_adapter.py',
            'adapter_sha256':files['production/p2_attempt5/native_adapter.py'],
            'ledger_directory':self.root+'/db','grant':self.g,'review_id':9000000099,
            'cycle_policy':self.policy,'command_sha256':'4'*64}
        cfg_ref = self.write('config.json', r.canonical(self.cfg))
        subjects = {'issuer':{'issuer':self.cfg['issuer'],'public_der_sha256':self.cfg['public_der_sha256']},
            'adapter':{'path':self.cfg['adapter_path'],'sha256':self.cfg['adapter_sha256']},
            'authority_store':{'database':self.cfg['database']},
            'writer_fence':{'principal':self.cfg['principal']}}
        record = {'schema':1,'registration_id':'recovery-test-registration', 'hostname':r.HOST,
            'config':cfg_ref, 'sources':{}}
        for kind in registry.KINDS:
            record['sources'][kind] = self.write(kind+'.json', registry.canonical({
                'schema':1,'kind':registry.KINDS[kind],'hostname':r.HOST,
                'source_id':'SYNTHETIC_TEST_ONLY-'+kind,'subject':subjects[kind]}))
        record_ref = self.write('record.json', registry.canonical(record))
        self.plan = {'schema':1,'request_sha256':r.sha(r.canonical(self.request)),
            'config':cfg_ref,'registry_record':record_ref,'registry_root':self.root+'/registry',
            'assembly_manifest':m,'assembly_root':self.root+'/assembly','kit_root':self.root+'/kit',
            'loader_sha256':'5'*64,'kit_manifest_sha256':'3'*64,
            'provider_socket':self.root+'/management.sock','checkpoint_root':self.root+'/checkpoint'}
        self.ref = self.write('plan.json', r.canonical(self.plan))
        self.body['sources'].append(self.ref)
        # Only the existing HTTPS worker is replaced. Actual approval parsing,
        # Owner identity, exact body/source/key/policy checks run unchanged.
        mock.patch.object(epoch7_approval, '_run_worker',
            return_value=json.dumps(self.approval).encode()).start()
        self.runtime = {'authority_store':authority_store, 'authorization':authorization,
                        'receipt_provider':receipt_provider}
        self.provider_fault = None
        self.stop = threading.Event()
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.plan['provider_socket'])
        os.chmod(self.plan['provider_socket'], 0o600)
        self.server.listen(8)
        self.server.settimeout(.1)
        self.thread = threading.Thread(target=self.serve)
        self.thread.daemon = True
        self.thread.start()
        self.addCleanup(self.finish_server)

    def finish_server(self):
        self.stop.set()
        self.thread.join(3)
        self.server.close()

    def signatures(self, value):
        return {role:base64.b64encode(subprocess.check_output(['/usr/bin/openssl','dgst',
            '-sha256','-sign',self.private[role]],input=r.canonical(value),
            stderr=subprocess.DEVNULL)).decode('ascii') for role in r.ROLES}

    def serve(self):
        while not self.stop.is_set():
            try: conn, unused = self.server.accept()
            except socket.timeout: continue
            with conn:
                conn.settimeout(2)
                def exact(n):
                    b = b''
                    while len(b)<n:
                        x=conn.recv(n-len(b))
                        if not x:raise IOError('closed')
                        b+=x
                    return b
                try:
                    request = r.decode(exact(struct.unpack('!I',exact(4))[0]))
                    if self.provider_fault == 'disconnect':continue
                    packet = self.signed()
                    packet['body']['issued_utc']=int(time.time())-1
                    packet['body']['expires_utc']=int(time.time())+20
                    packet['signatures']=self.signatures(packet['body'])
                    response = {'schema':1,'probe':request,'issued_utc':int(time.time())-1,
                                'expires_utc':int(time.time())+20,'packet':packet,
                                'reservation':{'old_authority_id':self.request['old_authority_id'],
                                    'authority_id':self.request['new_authority_id'],'epoch':self.request['new_epoch'],
                                    'fence':self.request['new_epoch'],'writer_id':self.request['writer_id'],
                                    'grant_id':self.request['new_grant_id'],'database':self.request['target_database'],
                                    'plan_sha256':self.ref['sha256'],'exclusive':True}}
                    if self.provider_fault == 'numeric':response['reservation']['exclusive']=1
                    if self.provider_fault == 'fence':response['reservation']['fence']-=1
                    if self.provider_fault == 'replay':response['probe']['challenge']='replayed'
                    if self.provider_fault == 'unknown':
                        response['packet']['body']['history']['unknown_effects']=['UNKNOWN']
                        response['packet']['signatures']=self.signatures(response['packet']['body'])
                    raw = r.canonical({'body':response,'signatures':self.signatures(response)})
                    conn.sendall(struct.pack('!I',len(raw))+raw)
                except (OSError,ValueError):pass

    def gate(self):
        return e.RecoveryGate(self.request,self.signed(),self.public,self.ref,registry,assembly)

    def apply(self):
        return e.apply(self.gate(),self.runtime)

    def test_b_apply_registers_without_writer_or_stages(self):
        self.assertEqual(self.apply()['state'],'RECOVERY_APPLIED_NOT_ACTIVATED')
        self.gate().verify()
        db=sqlite3.connect(self.cfg['database'])
        try:
            self.assertEqual(db.execute('SELECT consumed,epoch,fence,expiry FROM grants').fetchall(),[(0,7,7,0)])
        finally:db.close()
        self.assertFalse(os.path.exists(self.cfg['socket']))

    def test_apply_restart_idempotent_and_does_not_reset_quota(self):
        self.apply()
        store=authority_store.AuthorityStore(self.cfg['database'])
        try:
            token=store.lease(self.g,self.request['writer_id'])
            self.assertEqual(token['lease_epoch'],8)
            store.consume(self.g,'attempt-1',1,'a'*64,token)
            store.reconcile(self.g,'attempt-1','NO_WRITE','b'*64,token,lambda *args:True)
        finally:store.close()
        self.assertEqual(self.apply()['state'],'ALREADY_APPLIED_NOT_ACTIVATED')
        store=authority_store.AuthorityStore(self.cfg['database'])
        try:self.assertEqual(store._grant(self.g)[2],1)
        finally:store.close()

    def test_five_attempts_success_terminates_and_restart_does_not_reset(self):
        self.apply();store=authority_store.AuthorityStore(self.cfg['database'])
        try:
            token=store.lease(self.g,self.request['writer_id'])
            for n in range(1,6):
                store.consume(self.g,'attempt-'+str(n),n,'a'*64,token)
                store.reconcile(self.g,'attempt-'+str(n),'SUCCESS' if n==5 else 'NO_WRITE',
                                'b'*64,token,lambda *args:True)
            with self.assertRaises(receipt_provider.Hold):
                store.consume(self.g,'attempt-6',5,'a'*64,token)
        finally:store.close()
        self.apply()
        db=sqlite3.connect(self.cfg['database'])
        self.assertEqual(db.execute('SELECT consumed,terminal FROM grants').fetchone(),(5,1));db.close()

    def test_first_success_stops_remaining_attempts(self):
        self.apply();store=authority_store.AuthorityStore(self.cfg['database'])
        try:
            token=store.lease(self.g,self.request['writer_id'])
            store.consume(self.g,'attempt-1',1,'a'*64,token)
            store.reconcile(self.g,'attempt-1','SUCCESS','b'*64,token,lambda *args:True)
            with self.assertRaises(receipt_provider.Hold):
                store.consume(self.g,'attempt-2',2,'a'*64,token)
        finally:store.close()
        self.apply()
        db=sqlite3.connect(self.cfg['database'])
        self.assertEqual(db.execute('SELECT consumed,terminal FROM grants').fetchone(),(1,1));db.close()

    def test_five_safe_failures_exhaust_quota(self):
        self.apply();store=authority_store.AuthorityStore(self.cfg['database'])
        try:
            token=store.lease(self.g,self.request['writer_id'])
            for n in range(1,6):
                store.consume(self.g,'attempt-'+str(n),n,'a'*64,token)
                store.reconcile(self.g,'attempt-'+str(n),'NO_WRITE','b'*64,token,lambda *args:True)
            with self.assertRaises(receipt_provider.Hold):
                store.consume(self.g,'attempt-6',5,'a'*64,token)
        finally:store.close()
        self.apply()
        db=sqlite3.connect(self.cfg['database'])
        self.assertEqual(db.execute('SELECT consumed FROM grants').fetchone(),(5,));db.close()

    def test_unknown_no_database_created(self):
        self.provider_fault='unknown'
        with self.assertRaises(r.Hold):self.apply()
        self.assertFalse(os.path.lexists(self.cfg['database']))

    def test_reservation_requires_boolean_not_integer(self):
        self.provider_fault='numeric'
        with self.assertRaises(r.Hold):self.apply()
        self.assertFalse(os.path.lexists(self.cfg['database']))

    def test_provider_fence_conflict_rejected(self):
        self.provider_fault='fence'
        with self.assertRaises(r.Hold):self.apply()
        self.assertFalse(os.path.lexists(self.cfg['database']))

    def test_expired_recipe_renews_from_live_provider_without_new_approval(self):
        self.apply()
        original_review=self.cfg['review_id'];original_sha=self.g['approval_body_sha256']
        self.body['issued_utc']=int(time.time())-1000
        self.body['expires_utc']=self.body['issued_utc']+200
        self.gate().verify()
        self.assertEqual(self.apply()['state'],'ALREADY_APPLIED_NOT_ACTIVATED')
        self.assertEqual(self.cfg['review_id'],original_review)
        self.assertEqual(self.g['approval_body_sha256'],original_sha)

    def test_expired_recipe_cannot_bypass_unknown_live_provider(self):
        self.body['issued_utc']=int(time.time())-1000
        self.body['expires_utc']=self.body['issued_utc']+200
        self.provider_fault='unknown'
        with self.assertRaises(r.Hold):self.apply()
        self.assertFalse(os.path.lexists(self.cfg['database']))

    def test_provider_replay_rejected(self):
        self.provider_fault='replay'
        with self.assertRaises(r.Hold):self.apply()

    def test_provider_unknown_disconnect_rejected(self):
        self.provider_fault='disconnect'
        with self.assertRaises(r.Hold):self.apply()

    def test_unsigned_plan_rejected(self):
        self.body['sources'].remove(self.ref)
        with self.assertRaises(r.Hold):self.apply()

    def test_approval_missing_no_authority_created(self):
        with mock.patch.object(epoch7_approval,'_run_worker',side_effect=OSError()):
            with self.assertRaises(OSError):self.apply()
        self.assertFalse(os.path.lexists(self.cfg['database']))

    def test_forged_owner_rejected(self):
        self.approval['user']['id']=1
        with mock.patch.object(epoch7_approval,'_run_worker',return_value=json.dumps(self.approval).encode()):
            with self.assertRaises(receipt_provider.Hold):self.apply()
        self.assertFalse(os.path.lexists(self.cfg['database']))

    def test_existing_target_is_retained(self):
        self.write('db/authority.sqlite3',b'RETAIN_UNKNOWN')
        with self.assertRaises(r.Hold):self.apply()
        self.assertEqual(Path(self.cfg['database']).read_bytes(),b'RETAIN_UNKNOWN')

    def test_sidecar_prevents_initialization(self):
        self.write('db/authority.sqlite3-wal',b'RETAIN_WAL')
        with self.assertRaises(r.Hold):self.apply()
        self.assertFalse(os.path.lexists(self.cfg['database']))

    def test_parallel_apply_lock_refused(self):
        fd=os.open(self.plan['checkpoint_root']+'/.apply.lock',os.O_CREAT|os.O_RDWR,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):self.apply()
            self.assertFalse(os.path.lexists(self.cfg['database']))
        finally:os.close(fd)

    def test_symlink_target_never_followed(self):
        protected=self.write('retained.json',b'RETAIN_ORIGINAL')
        os.symlink(protected['path'],self.cfg['database'])
        with self.assertRaises(r.Hold):self.apply()
        self.assertEqual(Path(protected['path']).read_bytes(),b'RETAIN_ORIGINAL')

    def test_unprotected_target_parent_refused(self):
        os.chmod(self.root+'/db',0o777)
        with self.assertRaises(r.Hold):self.apply()
        self.assertFalse(os.path.lexists(self.cfg['database']))

    def test_partial_output_kept_after_failure_and_not_adopted(self):
        with mock.patch.object(authority_store.AuthorityStore,'register_cycle',side_effect=OSError()):
            with self.assertRaises(OSError):self.apply()
        before=Path(self.cfg['database']).read_bytes()
        with self.assertRaises(r.Hold):self.apply()
        self.assertEqual(Path(self.cfg['database']).read_bytes(),before)

    def test_uncommitted_receipt_does_not_enable_entry(self):
        with mock.patch.object(e,'publish_apply',side_effect=OSError()):
            with self.assertRaises(OSError):self.apply()
        with self.assertRaises((r.Hold,OSError)):self.gate().verify()

    def test_source_change_prevents_execution(self):
        self.apply()
        self.write('assembly/production/p2_recovery/executor.py',b'CHANGED')
        with self.assertRaises(r.Hold):self.gate().verify()

    def test_live_unknown_after_apply_prevents_execution(self):
        self.apply();self.provider_fault='unknown'
        with self.assertRaises(r.Hold):self.gate().verify()

    def test_guard_keeps_driver_identity_and_blocks_native_phase(self):
        self.apply()
        driver=types.SimpleNamespace(check_binding=mock.Mock())
        self.assertIs(e.guarded_driver(driver,self.gate()),driver)
        driver.check_binding()
        self.assertEqual(driver.check_binding.__name__,'check')
        self.provider_fault='unknown'
        with self.assertRaises(r.Hold):driver.check_binding()

    def entry(self):
        entry = types.SimpleNamespace(ProductionIssuer=assembly.ProductionIssuer,
            _assembly=types.SimpleNamespace(UnixTransport=assembly.UnixTransport),
            native_cycle=lambda factory: factory())
        e.install_entry_gates(entry, self.gate())
        return entry

    def test_formal_serve_issuer_real_signed_rpc(self):
        self.apply()
        entry=self.entry()
        signer=assembly.OpenSSLSigner(self.cfg['key'],self.cfg['public_der_sha256'])
        server=None
        try:
            server=entry.ProductionIssuer(self.cfg['database'],self.cfg['socket'],
                self.cfg['principal'],signer,self.cfg['issuer'],lambda *args: None,self.g)
            results=[]
            def client():
                try:
                    p=receipt_provider.ReceiptProvider(entry._assembly.UnixTransport(self.cfg['socket']),
                        signer.modulus,65537,self.cfg['issuer'])
                    results.append(p.request(self.g,'CANDIDATE','verify_fence',{}))
                except Exception as exc:results.append(exc)
            thread=threading.Thread(target=client);thread.start()
            server.serve_one();thread.join(10)
            self.assertFalse(thread.is_alive())
            self.assertEqual(results[0]['status'],'HELD')
            self.assertEqual(results[0]['lease_epoch'],8)
            self.provider_fault='unknown'
            with self.assertRaises(r.Hold):server.service.handle({},self.cfg['principal'])
        finally:
            if server is not None:server.close()
            signer.close()

    def test_formal_run_keeps_native_driver_and_checks_live_gate(self):
        self.apply();entry=self.entry()
        native=types.SimpleNamespace(check_binding=mock.Mock())
        self.assertIs(entry.native_cycle(lambda: native),native)
        native.check_binding()
        self.provider_fault='fence'
        with self.assertRaises(r.Hold):native.check_binding()

    def test_direct_original_entry_rejects_missing_recovery_gate(self):
        bootstrap=module(ROOT/'production/p2_recovery/bootstrap.py')
        m=self.manifest
        values=['serve','--kit-root',self.root+'/kit','--loader-sha256','5'*64,
            '--manifest-sha256','3'*64,'--config',self.plan['config']['path'],
            '--config-sha256',self.plan['config']['sha256'],'--assembly-sha256',
            m['files']['production/p2_attempt5/assembly.py'],'--assembly-manifest',
            self.plan['assembly_manifest']['path'],'--assembly-manifest-sha256',
            self.plan['assembly_manifest']['sha256'],'--registry-root',self.plan['registry_root'],
            '--registry-id','recovery-test-registration','--registry-record-sha256',
            self.plan['registry_record']['sha256']]
        with mock.patch.object(sys,'argv',['entry.py']+values):
            original=bootstrap.load(self.root+'/assembly/production/p2_attempt5/entry.py',
                m['files']['production/p2_attempt5/entry.py'])
            with self.assertRaisesRegex(RuntimeError,'CONTROLLED_RECOVERY_ENTRY_REQUIRED'):
                original.main()

    def test_cross_process_restart_checks_committed_state(self):
        self.apply()
        req=self.write('request.json',r.canonical(self.request))
        packet=self.write('packet.json',r.canonical(self.signed()))
        trust=self.write('trust.json',r.canonical({'schema':1,'host':r.HOST,'keys':self.refs}))
        paths={'root':self.root+'/assembly','request':req,'packet':packet,'trust':trust,'plan':self.ref}
        script="""import importlib.util,json,sys
v=json.loads(sys.argv[1]);base=v['root']+'/production/p2_recovery/'
def load(name):
 s=importlib.util.spec_from_file_location(name,base+name+'.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
b=load('bootstrap');r=load('recovery');e=load('executor');e.r=r
request=r.decode(r.read(v['request']['path'],v['request']['sha256']))
packet=r.decode(r.read(v['packet']['path'],v['packet']['sha256']))
keys=r.load_trust(v['trust']['path'],v['trust']['sha256'])
plan=e.signed_plan(request,packet,v['plan'])
manifest=r.decode(r.read(plan['assembly_manifest']['path'],plan['assembly_manifest']['sha256']))
def original(name):
 relative='production/p2_attempt5/'+name+'.py';return b.load(v['root']+'/'+relative,manifest['files'][relative])
gate=e.RecoveryGate(request,packet,keys,v['plan'],original('registry'),original('assembly'))
gate.verify();print('RESTART_COMMITTED_GATE_PASS')
"""
        result=subprocess.check_output([sys.executable,'-I','-B','-S','-c',script,json.dumps(paths)],
                                       timeout=30,stderr=subprocess.STDOUT)
        self.assertIn(b'RESTART_COMMITTED_GATE_PASS',result)

    def command(self):
        refs={'request':self.write('request.json',r.canonical(self.request)),
              'evidence':self.write('packet.json',r.canonical(self.signed())),
              'trust':self.write('trust.json',r.canonical({'schema':1,'host':r.HOST,'keys':self.refs})),
              'plan':self.ref}
        path=self.root+'/assembly/production/p2_recovery/entry.py'
        args=[path,'apply']
        for name,ref in refs.items():args.extend(['--'+name,ref['path'],'--'+name+'-sha256',ref['sha256']])
        for name,file in [('bootstrap','bootstrap.py'),('recovery-code','recovery.py'),('executor','executor.py')]:
            args.extend(['--'+name+'-sha256',r.sha(Path(self.root+'/assembly/production/p2_recovery/'+file).read_bytes())])
        return args

    def test_formal_cli_unknown_refuses_before_database(self):
        self.provider_fault='unknown'
        out=subprocess.run([sys.executable,'-I','-B','-S']+self.command(),
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        self.assertEqual(out.returncode,2,out.stderr.decode())
        result=json.loads(out.stdout.decode())
        self.assertEqual(result['reason'],'HISTORY_UNRECONCILED')
        self.assertFalse(os.path.lexists(self.cfg['database']))

    def test_formal_cli_apply_real_inherited_kit_and_owner_validation(self):
        builder=module(CORE/'build_kit.py')
        kit,km=builder.build(r.SOURCE,r.TREE)
        manifest_raw=builder.canonical(km)
        self.assertEqual(r.sha(kit),'2fdc934a336414086361764a4a77894a597a51a53c7693420eaed5cefed3e1d3')
        self.assertEqual(r.sha(manifest_raw),'243bc01b1e9c7d2cb302f800556002abcebcfa9f96c298e4275e15d8b1346e1e')
        os.mkdir(self.plan['kit_root'],0o700)
        with tarfile.open(fileobj=io.BytesIO(kit),mode='r:gz') as archive:
            for item in archive.getmembers():
                if not item.isfile():continue
                relative=item.name.split('/',1)[1]
                target=Path(self.plan['kit_root'])/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                current=target.parent
                while str(current).startswith(self.plan['kit_root']):
                    os.chmod(str(current),0o700)
                    if str(current)==self.plan['kit_root']:break
                    current=current.parent
                target.write_bytes(archive.extractfile(item).read());os.chmod(str(target),0o600)
        self.manifest['inherited_manifest_sha256']=r.sha(manifest_raw)
        self.plan['assembly_manifest']=self.write('assembly/MANIFEST.json',r.canonical(self.manifest))
        self.g['manifest_sha256']=self.plan['assembly_manifest']['sha256']
        self.g['kit_sha256']=r.sha(kit)
        signer=assembly.OpenSSLSigner(self.cfg['key'],self.cfg['public_der_sha256'])
        try:p=receipt_provider.ReceiptProvider(lambda unused:None,signer.modulus,65537,self.cfg['issuer'])
        finally:signer.close()
        body=authorization.OWNER_MARKER+receipt_provider.canonical(
            authorization.expected(self.g,p,self.policy,owner=True)).decode('utf-8')
        self.g['approval_body_sha256']=r.sha(body.encode())
        self.approval['body']=body
        self.plan['config']=self.write('config.json',r.canonical(self.cfg))
        rec=r.decode(Path(self.plan['registry_record']['path']).read_bytes())
        rec['config']=self.plan['config']
        self.plan['registry_record']=self.write('record.json',registry.canonical(rec))
        self.plan['loader_sha256']=r.sha(Path(self.plan['kit_root']+'/attempt5/runtime/versioned_entry.py').read_bytes())
        self.plan['kit_manifest_sha256']=r.sha(manifest_raw)
        old=self.ref;self.ref=self.write('plan.json',r.canonical(self.plan))
        self.body['sources'].remove(old);self.body['sources'].append(self.ref)
        argv=self.command()
        # Only the pre-existing HTTPS fetch worker is replaced in this isolated
        # child. Real Kit inventory/imports and exact Owner/body/key validation
        # still execute. No production switch or synthetic Grant is shipped.
        script="""import builtins,base64,json,runpy,sys
raw=base64.b64decode(sys.argv[1]);args=json.loads(sys.argv[2]);original=builtins.__import__
def test_import(name,*pos,**kw):
 m=original(name,*pos,**kw)
 if name=='epoch7_approval':m._run_worker=lambda unused:raw
 return m
builtins.__import__=test_import;sys.argv=args;runpy.run_path(args[0],run_name='__main__')
"""
        out=subprocess.run([sys.executable,'-I','-B','-S','-c',script,
            base64.b64encode(json.dumps(self.approval).encode()).decode(),json.dumps(argv)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
        self.assertEqual(out.returncode,0,out.stdout.decode()+out.stderr.decode())
        self.assertEqual(json.loads(out.stdout.decode())['state'],'RECOVERY_APPLIED_NOT_ACTIVATED')
        self.assertFalse(os.path.lexists(self.cfg['socket']))
        self.gate().verify()

    def test_a_preserves_all_history_revokes_old_grant(self):
        old=self.root+'/old-backup.sqlite3'
        oldg=grant();oldg.update(grant_id='recovery-old-grant-0001',expires_utc=int(time.time())+1000)
        store=authority_store.AuthorityStore(old,initialize=True)
        try:
            store.register(oldg);token=store.lease(oldg,'old-writer')
            store.consume(oldg,'old-attempt',1,'a'*64,token)
            store.reconcile(oldg,'old-attempt','NO_WRITE','b'*64,token,lambda *args:True)
            audit=store.db.execute('SELECT * FROM audit').fetchall()
        finally:store.close()
        before=Path(old).read_bytes()
        self.request['route']='RESTORE_EXISTING'
        self.plan['request_sha256']=r.sha(r.canonical(self.request))
        self.body['request_sha256']=self.plan['request_sha256']
        oldref=self.ref
        self.ref=self.write('plan.json',r.canonical(self.plan))
        self.body['sources'].remove(oldref);self.body['sources'].append(self.ref)
        self.body['restoration']={'status':'CONSISTENT_BACKUP_VERIFIED',
                                 'snapshot':{'path':old,'sha256':r.sha(before)}}
        self.apply()
        self.assertEqual(Path(old).read_bytes(),before)
        store=authority_store.AuthorityStore(self.cfg['database'])
        try:
            self.assertEqual(store.db.execute('SELECT consumed,terminal,expiry FROM grants WHERE id=?',
                ('recovery-old-grant-0001',)).fetchone(),(1,1,0))
            self.assertEqual(store.db.execute('SELECT id,ordinal FROM attempts').fetchall(),[('old-attempt',1)])
            self.assertEqual(store.db.execute('SELECT * FROM audit WHERE id<=?',(len(audit),)).fetchall(),audit)
            with self.assertRaises(receipt_provider.Hold):store.lease(oldg,'old-writer')
            with self.assertRaises(receipt_provider.Hold):store.consume(oldg,'replay',2,'a'*64,token)
        finally:store.close()


if __name__=='__main__':unittest.main(verbosity=2)
