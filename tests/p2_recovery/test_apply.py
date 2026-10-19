"""Real RSA/socket/SQLite and original registry/issuer. Synthetic host facts ONLY."""
import base64
import copy
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
                    response = {'schema':1,'probe':request,'issued_utc':int(time.time())-1,
                                'expires_utc':int(time.time())+20,'packet':packet}
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

    def test_unknown_no_database_created(self):
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

    def test_a_preserves_all_history_revokes_old_grant(self):
        old=self.root+'/old-backup.sqlite3'
        oldg=grant();oldg.update(grant_id='old-grant',expires_utc=int(time.time())+1000)
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
                ('old-grant',)).fetchone(),(1,1,0))
            self.assertEqual(store.db.execute('SELECT id,ordinal FROM attempts').fetchall(),[('old-attempt',1)])
            self.assertEqual(store.db.execute('SELECT * FROM audit WHERE id<=?',(len(audit),)).fetchall(),audit)
            with self.assertRaises(receipt_provider.Hold):store.lease(oldg,'old-writer')
            with self.assertRaises(receipt_provider.Hold):store.consume(oldg,'replay',2,'a'*64,token)
        finally:store.close()


if __name__=='__main__':unittest.main(verbosity=2)
