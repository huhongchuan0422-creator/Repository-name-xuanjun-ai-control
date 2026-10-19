"""Real SQLite/RSA control implementation tests; no production isolation claim."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import unittest
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_provider_server as f
r=f.r;e=f.e;s=f.s
c=f.load('control_plane.py');c.r=r;c.e=e

class ControlTests(unittest.TestCase):
    setUpClass=classmethod(f.ProviderTests.setUpClass.__func__)
    tearDownClass=classmethod(f.ProviderTests.tearDownClass.__func__)
    write=f.ProviderTests.write
    signed=f.ProviderTests.signed
    sign=f.ProviderTests.sign
    def setUp(self):
        f.ProviderTests.setUp(self)
        self.trust=self.write('trust.json',r.canonical({'schema':1,'host':r.HOST,'keys':self.refs}))
        inventory={'schema':1,'request_sha256':r.sha(r.canonical(self.request)),
            'channels':{kind:{'status':'ISOLATED','principals':['p2-legacy-principal'],
                             'enforcement':self.source} for kind in r.CHANNELS},'invoke_ids':[]}
        inventory['signatures']=self.sign(inventory)
        self.inventory=inventory
        self.iref=self.write('inventory.json',r.canonical(inventory))
        self.body['sources'].append(self.iref)
        evidence=self.write('evidence.json',r.canonical(self.signed()))
        self.config={'schema':1,'host':r.HOST,'request_sha256':r.sha(r.canonical(self.request)),
            'trust':self.trust,'signing_keys':{role:{'path':path,'sha256':r.sha(Path(path).read_bytes())}
                for role,path in self.private.items()},'evidence':evidence,'inventory':self.iref,
            'invoke_receipts':[],'snapshot':None}
        self.save_config()
    def save_config(self):
        self.cref=self.write('control.json',r.canonical(self.config))
        approval={'config_sha256':self.cref['sha256']}
        approval['signature']=self.sign(approval)['owner']
        self.approval=self.write('control-approval.json',r.canonical(approval))
        self.control=c.ControlPlane(self.journal,self.request,self.public,self.ref,
                                   self.body['restoration'],self.cref)
    def update_evidence(self):
        self.config['evidence']=self.write('evidence.json',r.canonical(self.signed()))
        self.save_config()
    def register(self):self.control.register(self.approval)
    def test_registration_real_keys_and_protected_source(self):
        self.register();self.control.registered()
        self.assertEqual(self.journal.db.execute('SELECT count(*) FROM channel_revocations').fetchone(),(8,))
    def test_provider_backend_native_control_positive(self):
        self.register()
        backend=s.Backend(self.request,self.public,self.ref,self.body['restoration'],
                          self.journal,self.adapter,self.control)
        with mock.patch.object(s,'adapter_query',side_effect=AssertionError('MUST_USE_CONTROL')):
            response=backend.handle(self.probe)
        e.validate_response(self.request,self.probe,response,self.public,self.ref,self.body['restoration'])
        self.assertEqual(self.journal.db.execute('SELECT count(*) FROM reservations').fetchone(),(1,))
    def test_registered_old_epoch_refused(self):
        self.register()
        for epoch in (0,6,7):
            with self.assertRaisesRegex(r.Hold,'OLD_EPOCH_REVOKED'):
                self.control.enforce('old-1',epoch,'any-writer','any-grant')
    def test_new_writer_and_grant_exact(self):
        self.register();self.control.enforce('new-2',8,'writer-new-2','grant-new-2')
        with self.assertRaises(r.Hold):self.control.enforce('new-2',8,'other','grant-new-2')
    def test_unregistered_refused(self):
        with self.assertRaises(r.Hold):self.control.respond(self.probe)
    def test_unsigned_config_refused(self):
        bad=self.write('bad-approval.json',r.canonical({'config_sha256':'0'*64,'signature':'AAAA'}))
        with self.assertRaises(r.Hold):self.control.register(bad)
    def test_private_signer_must_match_real_public_trust(self):
        self.register();refs=copy.deepcopy(self.config['signing_keys'])
        refs['owner']=refs['isolation']
        with self.assertRaises(r.Hold):c.sign({'test':1},refs,self.public)
    def test_no_key_generation(self):
        self.register();before=set(Path(self.root).iterdir());self.control.respond(self.probe)
        self.assertEqual(before,set(Path(self.root).iterdir()))
    def test_external_unknown_refused(self):
        self.body['inventory']['unknown_writers']=['external-unverified']
        self.update_evidence()
        with self.assertRaises(r.Hold):self.register()
    def test_missing_channel_refused(self):
        del self.inventory['channels']['ssh'];self.inventory.pop('signatures')
        self.inventory['signatures']=self.sign(self.inventory)
        self.config['inventory']=self.write('inventory.json',r.canonical(self.inventory))
        self.save_config()
        with self.assertRaises(r.Hold):self.register()
    def test_expired_external_evidence_not_refreshed_by_signer(self):
        self.body['issued_utc']=1;self.body['expires_utc']=100
        self.update_evidence()
        with self.assertRaises(r.Hold):self.register()
    def test_config_change_refused(self):
        self.register();self.write('control.json',b'{}')
        with self.assertRaises(r.Hold):self.control.respond(self.probe)
    def test_restart_keeps_revocation_and_exact_registration(self):
        self.register();self.control.respond(self.probe)
        self.journal.close();self.journal=s.Reservations(self.path);self.addCleanup(self.journal.close)
        self.control=c.ControlPlane(self.journal,self.request,self.public,self.ref,self.body['restoration'],self.cref)
        with self.assertRaises(r.Hold):self.control.enforce('old-1',7,'old','old')
        self.probe['operation']='execution_gate';self.control.respond(self.probe)
    def test_gate_never_initializes_reservation(self):
        self.register();self.probe['operation']='execution_gate'
        with self.assertRaises(r.Hold):self.control.respond(self.probe)
    def test_invocation_actual_rpc_shape_no_dispatch(self):
        calls=[]
        def rpc(endpoint,action,**kw):
            calls.append(action)
            return {'InvocationResult':{'InvokeId':kw['InvokeId'],
                'InstanceId':kw['InstanceId'],'InvocationStatus':'Success'}}
        result=c.invocation_state(rpc,'t-p2-real-shape')
        self.assertEqual(calls,['DescribeInvocationResult'])
        self.assertEqual(result['effects'],'REQUIRES_TRANSACTION_RECEIPT')
    def test_cloud_success_is_not_transaction_reconciled(self):
        self.test_invocation_actual_rpc_shape_no_dispatch()
        self.assertEqual(self.journal.db.execute('SELECT count(*) FROM reservations').fetchone(),(0,))
    def test_cloud_identity_mismatch_refused(self):
        with self.assertRaises(r.Hold):c.invocation_state(lambda *a,**k:{'InvocationResult':{}},'t-p2')
    def test_pending_invoke_requires_signed_transaction_receipt(self):
        self.inventory.pop('signatures');self.inventory['invoke_ids']=['t-p2-pending']
        self.inventory['signatures']=self.sign(self.inventory)
        old=self.iref;self.iref=self.write('inventory.json',r.canonical(self.inventory))
        self.body['sources'].remove(old);self.body['sources'].append(self.iref)
        self.config['inventory']=self.iref;self.update_evidence()
        with self.assertRaisesRegex(r.Hold,'INVOKE_CLOSURE_INCOMPLETE'):self.register()
    def test_registration_fsync_failure_not_accepted_after_restart(self):
        with mock.patch.object(c.os,'fsync',side_effect=OSError('failure')):
            with self.assertRaises(OSError):self.register()
        self.journal.close();self.journal=s.Reservations(self.path);self.addCleanup(self.journal.close)
        self.control=c.ControlPlane(self.journal,self.request,self.public,self.ref,self.body['restoration'],self.cref)
        with self.assertRaises(r.Hold):self.control.registered()
    def test_shared_journal_conflict_rejected_before_signing(self):
        self.register();self.control.respond(self.probe)
        old=self.request['new_grant_id'];self.request['new_grant_id']='different'
        with mock.patch.object(c,'sign',side_effect=AssertionError('NO_SIGN')):
            with self.assertRaises(r.Hold):self.control.respond(self.probe)
        self.request['new_grant_id']=old
    def test_signed_completed_invocation_bound_to_transaction_source(self):
        self.inventory.pop('signatures');self.inventory['invoke_ids']=['t-p2-finished']
        self.inventory['signatures']=self.sign(self.inventory)
        old=self.iref;self.iref=self.write('inventory.json',r.canonical(self.inventory))
        self.body['sources'].remove(old);self.body['sources'].append(self.iref)
        receipt={'request_sha256':self.config['request_sha256'],'invoke_id':'t-p2-finished',
                 'terminal':True,'effects':'RECONCILED','transaction_sha256':self.source['sha256']}
        ref=self.write('invoke-receipt.json',r.canonical({'body':receipt,'signatures':self.sign(receipt)}))
        self.body['sources'].append(ref);self.config['invoke_receipts']=[ref]
        self.config['inventory']=self.iref;self.update_evidence();self.register()
        self.control.respond(self.probe)
    def snapshot(self,state='NO_WRITE'):
        p=self.root+'/consistent.sqlite3';db=sqlite3.connect(p)
        db.executescript('CREATE TABLE grants(id,binding,body,approval,consumed,terminal,writer,epoch,fence,expiry);'
            'CREATE TABLE attempts(id,grant_id,ordinal,operation,state,proof);'
            'CREATE TABLE audit(id,grant_id,event,at,body);')
        db.execute('INSERT INTO grants VALUES(?,?,?,?,?,?,?,?,?,?)',('old-grant','binding','body','approval',1,0,'old',7,7,0))
        db.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?)',('old-attempt','old-grant',1,'operation',state,'a'*64))
        db.execute('INSERT INTO audit VALUES(?,?,?,?,?)',(1,'old-grant','CONSUME',1,'{}'))
        db.commit();db.close();os.chmod(p,0o600)
        return {'path':p,'sha256':r.sha(Path(p).read_bytes())}
    def test_real_sqlite_snapshot_preserves_consumption(self):
        ref=self.snapshot();before=Path(ref['path']).read_bytes()
        result=c.transaction_snapshot(ref)
        self.assertEqual(result['grants'],[('old-grant',1,0)])
        self.assertEqual(result['attempts'][0][2],1)
        self.assertEqual(Path(ref['path']).read_bytes(),before)
    def test_snapshot_unknown_stops(self):
        with self.assertRaises(r.Hold):c.transaction_snapshot(self.snapshot('UNKNOWN'))
    def test_snapshot_hash_refused(self):
        with self.assertRaises(r.Hold):c.transaction_snapshot(self.source)
    def test_source_version_change_refused(self):
        self.request['source_commit']='a'*40
        with self.assertRaises(r.Hold):self.control.facts()
    def test_numeric_true_not_accepted(self):
        self.body['isolation']['all_old_tokens_rejected']=1;self.update_evidence()
        with self.assertRaises(r.Hold):self.register()

if __name__=='__main__':unittest.main(verbosity=2)
