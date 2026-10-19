import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / 'production/p2_recovery/recovery.py'
spec = importlib.util.spec_from_file_location('recovery', str(MODULE))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keydir = tempfile.TemporaryDirectory(prefix='p2-test-keys-', dir='/root')
        cls.private, cls.public, cls.refs = {}, {}, {}
        for role in sorted(r.ROLES):
            key = cls.keydir.name + '/' + role
            subprocess.check_call(['/usr/bin/openssl','genpkey','-algorithm','RSA',
                '-pkeyopt','rsa_keygen_bits:2048','-out',key], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            os.chmod(key,0o600)
            pub = subprocess.check_output(['/usr/bin/openssl','pkey','-in',key,'-pubout'],
                                          stderr=subprocess.DEVNULL)
            path = key + '.pub'
            with open(path,'wb') as stream: stream.write(pub)
            os.chmod(path,0o600)
            der = r.openssl(['pkey','-pubin','-outform','DER'], pub)
            cls.private[role], cls.public[role] = key, pub
            cls.refs[role] = {'path':path,'sha256':r.sha(pub),'der_sha256':r.sha(der)}

    @classmethod
    def tearDownClass(cls):
        cls.keydir.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='p2-recovery-test-',dir='/root')
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.source = self.write('source.json', b'{"scope":"SYNTHETIC_TEST_ONLY"}\n')
        self.request = {'schema':1,'host':r.HOST,'source_commit':r.SOURCE,'source_tree':r.TREE,
            'recovery_id':'recovery-1','old_authority_id':'old-1','new_authority_id':'new-2',
            'old_epoch':7,'new_epoch':8,'writer_id':'writer-new-2','new_grant_id':'grant-new-2',
            'route':'NEW_AUTHORITY','target_database':'/var/lib/example/new-authority.sqlite3',
            'nonce':'a'*64}
        self.body = {'schema':1,'request_sha256':r.sha(r.canonical(self.request)),
            'issued_utc':100,'expires_utc':200,
            'inventory':{'complete':True,'unknown_writers':[], 'channels':{
                k:{'status':'ISOLATED','source_id':'source-'+k,'receipt_sha256':self.source['sha256']}
                for k in r.CHANNELS}},
            'isolation':{'old_authority_id':'old-1','old_epoch':7,
                'revoked_grants_sha256':'b'*64,'all_old_tokens_rejected':True,
                'enforcement_sha256':'c'*64},
            'history':{'status':'RECONCILED','pending_transactions':[],'unknown_effects':[],
                'disposition_sha256':'d'*64,'old_grants_not_reissued':True,
                'preservation':[{'source_id':'archive-'+x,'sha256':'e'*64,'category':x}
                    for x in ('DATABASE_AND_SIDECARS','BACKUP','EXECUTION_RECEIPTS')]},
            'sources':[self.source],
            'restoration':{'status':'UNRECOVERABLE_WITH_DISPOSITION','snapshot':None}}

    def write(self, name, raw):
        p = self.root+'/'+name
        with open(p,'wb') as stream: stream.write(raw)
        os.chmod(p,0o600)
        return {'path':p,'sha256':r.sha(raw)}

    def signed(self):
        signs = {}
        for role in sorted(r.ROLES):
            out = subprocess.check_output(['/usr/bin/openssl','dgst','-sha256','-sign',self.private[role]],
                                          input=r.canonical(self.body),stderr=subprocess.DEVNULL)
            signs[role] = base64.b64encode(out).decode('ascii')
        return {'body':copy.deepcopy(self.body),'signatures':signs}

    def decide(self):
        return r.decide(self.request,self.signed(),self.public,now=150)

    def test_new_authority_decision_never_initializes(self):
        out=self.decide()
        self.assertEqual(out['state'],'RECOVERY_EVIDENCE_VALIDATED_NOT_ACTIVATED')
        self.assertFalse(out['authority_initialized'])
        self.assertFalse(out['grant_registered'])
        self.assertFalse(out['writer_started'])
        self.assertEqual(os.listdir(self.root),['source.json'])

    def test_missing_signature(self):
        p=self.signed();del p['signatures']['owner']
        with self.assertRaises(r.Hold):r.decide(self.request,p,self.public,150)

    def test_forged_signature(self):
        p=self.signed();p['signatures']['isolation']=p['signatures']['owner']
        with self.assertRaises(r.Hold):r.decide(self.request,p,self.public,150)

    def test_tampered_body(self):
        p=self.signed();p['body']['isolation']['old_epoch']=6
        with self.assertRaises(r.Hold):r.decide(self.request,p,self.public,150)

    def test_expired(self):
        with self.assertRaises(r.Hold):r.decide(self.request,self.signed(),self.public,200)

    def test_future(self):
        with self.assertRaises(r.Hold):r.decide(self.request,self.signed(),self.public,99)

    def test_overlong_evidence(self):
        self.body['expires_utc']=401
        with self.assertRaises(r.Hold):self.decide()

    def test_request_drift(self):
        self.request['writer_id']='other'
        with self.assertRaises(r.Hold):self.decide()

    def test_host_drift(self):
        self.request['host']='other'
        with self.assertRaises(r.Hold):self.decide()

    def test_source_drift(self):
        self.request['source_commit']='0'*40
        with self.assertRaises(r.Hold):self.decide()

    def test_same_authority(self):
        self.request['new_authority_id']='old-1'
        with self.assertRaises(r.Hold):self.decide()

    def test_epoch_not_advanced(self):
        self.request['new_epoch']=7
        with self.assertRaises(r.Hold):self.decide()

    def test_unknown_writer(self):
        self.body['inventory']['unknown_writers']=['external']
        with self.assertRaises(r.Hold):self.decide()

    def test_inventory_not_complete(self):
        self.body['inventory']['complete']=False
        with self.assertRaises(r.Hold):self.decide()

    def test_missing_channel(self):
        del self.body['inventory']['channels']['other_hosts']
        with self.assertRaises(r.Hold):self.decide()

    def test_service_stopped_insufficient(self):
        self.body['inventory']['channels']['systemd']['status']='STOPPED'
        with self.assertRaises(r.Hold):self.decide()

    def test_fence_not_rejected(self):
        self.body['isolation']['all_old_tokens_rejected']=False
        with self.assertRaises(r.Hold):self.decide()

    def test_isolation_wrong_epoch(self):
        self.body['isolation']['old_epoch']=8
        with self.assertRaises(r.Hold):self.decide()

    def test_unknown_effect(self):
        self.body['history']['unknown_effects']=['invoke-unknown']
        with self.assertRaises(r.Hold):self.decide()

    def test_pending_transaction(self):
        self.body['history']['pending_transactions']=['attempt-open']
        with self.assertRaises(r.Hold):self.decide()

    def test_old_grant_replay(self):
        self.body['history']['old_grants_not_reissued']=False
        with self.assertRaises(r.Hold):self.decide()

    def test_missing_backup(self):
        self.body['history']['preservation']=self.body['history']['preservation'][:1]
        with self.assertRaises(r.Hold):self.decide()

    def test_source_file_changed(self):
        with open(self.source['path'],'wb') as stream:stream.write(b'changed')
        with self.assertRaises(r.Hold):self.decide()

    def test_source_symlink(self):
        os.symlink(self.source['path'],self.root+'/link')
        with self.assertRaises(OSError):r.read(self.root+'/link')

    def test_source_permissions(self):
        os.chmod(self.source['path'],0o644)
        with self.assertRaises(r.Hold):self.decide()

    def test_duplicate_json(self):
        with self.assertRaises(r.Hold):r.decode(b'{"a":1,"a":2}')

    def test_nonfinite_json(self):
        with self.assertRaises(r.Hold):r.decode(b'{"a":NaN}')

    def test_wrong_disposition(self):
        self.body['restoration']['status']='NOT_FOUND'
        with self.assertRaises(r.Hold):self.decide()

    def test_checkpoint_idempotent(self):
        out=self.decide()
        self.assertEqual(r.checkpoint(self.root,self.request,out),'COMMITTED_DECISION_NOT_ACTIVATION')
        self.assertEqual(r.checkpoint(self.root,self.request,out),'ALREADY_COMMITTED')

    def test_checkpoint_restart(self):
        out=self.decide();r.checkpoint(self.root,self.request,out)
        runner='import importlib.util,json; s=importlib.util.spec_from_file_location("r",%r); r=importlib.util.module_from_spec(s);s.loader.exec_module(r); print(r.checkpoint(%r,%r,%r))' % (str(MODULE),self.root,self.request,out)
        result=subprocess.check_output([sys.executable,'-I','-B','-S','-c',runner])
        self.assertEqual(result.strip(),b'ALREADY_COMMITTED')

    def test_checkpoint_partial_fsync_failure_not_adopted(self):
        out=self.decide()
        # Create metadata under a different recovery id before fault injection.
        r.checkpoint(self.root,self.request,out)
        self.request['recovery_id']='recovery-2'
        self.body['request_sha256']=r.sha(r.canonical(self.request))
        out=self.decide()
        original=os.fsync
        def fail(fd):
            if stat_is_regular(fd):raise OSError(5,'injected')
            return original(fd)
        with mock.patch.object(r.os,'fsync',side_effect=fail):
            with self.assertRaises(OSError):r.checkpoint(self.root,self.request,out)
        self.assertTrue(os.path.exists(self.root+'/recovery-2.json'))
        with self.assertRaises(r.Hold):r.checkpoint(self.root,self.request,out)

    def test_checkpoint_conflict(self):
        out=self.decide();r.checkpoint(self.root,self.request,out)
        out=copy.deepcopy(out);out['epoch']=99
        with self.assertRaises(r.Hold):r.checkpoint(self.root,self.request,out)

    def test_checkpoint_lock_conflict(self):
        import fcntl
        out=self.decide()
        f=os.open(self.root+'/.recovery.lock',os.O_CREAT|os.O_RDWR,0o600)
        try:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(OSError):r.checkpoint(self.root,self.request,out)
        finally:os.close(f)

    def test_trust_distinct_roles(self):
        trust={'schema':1,'host':r.HOST,'keys':copy.deepcopy(self.refs)}
        trust['keys']['isolation']=trust['keys']['owner']
        ref=self.write('trust.json',r.canonical(trust))
        with self.assertRaises(r.Hold):r.load_trust(ref['path'],ref['sha256'])

    def test_trust_real_public_keys(self):
        ref=self.write('trust.json',r.canonical({'schema':1,'host':r.HOST,'keys':self.refs}))
        self.assertEqual(r.load_trust(ref['path'],ref['sha256']),self.public)

    def test_trust_wrong_pin(self):
        ref=self.write('trust.json',r.canonical({'schema':1,'host':r.HOST,'keys':self.refs}))
        with self.assertRaises(r.Hold):r.load_trust(ref['path'],'0'*64)

    def snapshot(self, consumed=5, unknown=False):
        p=self.root+'/snapshot.sqlite3'
        db=sqlite3.connect(p)
        db.executescript('CREATE TABLE grants(id TEXT PRIMARY KEY,binding TEXT,body TEXT,approval TEXT,consumed INTEGER,terminal INTEGER,writer TEXT,epoch INTEGER,fence INTEGER,expiry INTEGER); CREATE TABLE attempts(id TEXT PRIMARY KEY,grant_id TEXT,ordinal INTEGER,operation TEXT,state TEXT,proof TEXT); CREATE TABLE audit(id INTEGER PRIMARY KEY,grant_id TEXT,event TEXT,at INTEGER,body TEXT);')
        db.execute('INSERT INTO grants VALUES(?,?,?,?,?,?,?,?,?,?)',('g','b','{}','a',consumed,0,'w',7,9,200))
        for ordinal in range(1,consumed+1):
            db.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?)',('a'+str(ordinal),'g',ordinal,'hash','UNKNOWN' if unknown else 'SAFE_CHECKPOINT','p'))
        db.execute('INSERT INTO audit VALUES(1,?,?,?,?)',('g','CONSUME',100,'{}'))
        db.commit();db.close();os.chmod(p,0o600)
        return {'path':p,'sha256':r.sha(Path(p).read_bytes())}

    def test_existing_snapshot_preserves_five_consumptions(self):
        ref=self.snapshot();before=Path(ref['path']).read_bytes()
        self.request['route']='RESTORE_EXISTING'
        self.body['request_sha256']=r.sha(r.canonical(self.request))
        self.body['restoration']={'status':'CONSISTENT_BACKUP_VERIFIED','snapshot':ref}
        out=self.decide()
        self.assertEqual(out['snapshot']['attempts'],5)
        self.assertEqual(before,Path(ref['path']).read_bytes())
        self.assertFalse(out['authority_initialized'])

    def test_existing_snapshot_unknown_rejected(self):
        with self.assertRaises(r.Hold):r.inspect_snapshot(self.snapshot(unknown=True))

    def test_existing_snapshot_sixth_rejected(self):
        with self.assertRaises(r.Hold):r.inspect_snapshot(self.snapshot(consumed=6))

    def test_existing_snapshot_corrupt(self):
        ref=self.write('bad.sqlite3',b'SQLite format 3\x00'+b'x'*100)
        with self.assertRaises(sqlite3.Error):r.inspect_snapshot(ref)

    def test_formal_cli_wrong_host_has_no_writes(self):
        q=subprocess.run([sys.executable,'-I','-B','-S',str(MODULE),'assess',
            '--request','/nonexistent','--request-sha256','a'*64,
            '--evidence','/nonexistent','--evidence-sha256','b'*64,
            '--trust','/nonexistent','--trust-sha256','c'*64],stdout=subprocess.PIPE)
        self.assertEqual(q.returncode,2)
        self.assertIn(b'ISOLATED_UK_ROOT_REQUIRED',q.stdout)
        self.assertFalse(json.loads(q.stdout)['authority_initialized'])


def stat_is_regular(fd):
    import stat
    return stat.S_ISREG(os.fstat(fd).st_mode)


if __name__=='__main__':unittest.main(verbosity=2)
