"""Isolated host adapter and DB only; no formal identity or backup."""
import copy, datetime, json, os, time, unittest
from pathlib import Path
from types import SimpleNamespace
from test_handoff_host_delta import HostDelta
from task_delivery_ledger.core import Store, LedgerError, canonical, digest
from task_delivery_ledger.handoffs import SNAPSHOT_FIELDS
from task_center_handoff_ledger import HandoffLedgerBridge
from task_delivery_observer import MetadataReader, Unavailable
from task_center_app import build_handler

class MainChain(HostDelta):
    def setUp(self):
        super().setUp()
        self.now=int(time.time());self.expiry=self.now+3600
        self.host.clock=lambda:self.now
        self.auth.override={'expires_at':self.expiry}
        self.auth.backup={'state':'COMPLETE','missing':[],'cycle_at':self.now-1}
        self.db.execute('UPDATE tasks SET authority_valid_until=?,last_trusted_time=?',(self.expiry,self.now-2));self.db.commit()
        self.auth.assess_ledger_event=lambda binding,event: True  # isolated simulated fact attestation
        self.auth.verify_ledger_event_current=lambda event,host_record: True  # simulated, not production
        self.bridge=HandoffLedgerBridge(self.host,os.path.join(self.tmp.name,'journal'),'tenant-ledger','writer')
        self.snap={k:'ref-'+k for k in SNAPSHOT_FIELDS}
        self.snap.update(commit='a'*40,tree='b'*40,artifact_sha256='c'*64,deploy_refs=['deploy-ref'],pending_operations=['none-ref'],expires_at='2099-01-01T00:00:00Z')
        self.sha=digest(canonical(self.snap));self.stamp=datetime.datetime.fromtimestamp(self.now,datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.expires=datetime.datetime.fromtimestamp(self.expiry,datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    def make(self,action,label,cause,actor):
        value=self.req(action,label,cause);value['snapshot_digest']=self.sha
        if action=='NOMINATE':value['target_ref']='role-carol'
        if action=='VERIFIED':value['alignment_ref']=self.refs['a']['event_id']
        d=dict(handoff_id=value['handoff_id'],handoff_version=1,snapshot_digest=self.sha,actor_ref=actor,role_id='role-'+actor,session_ref='session-'+actor,identity_evidence_ref='identity-'+actor,permission_evidence_ref='permission-'+actor,permission_expires_at=self.expires)
        if action=='PROPOSE':d.update(snapshot_data=self.snap,scope_included=list(SNAPSHOT_FIELDS),scope_excluded=[],scope_authorization_ref='UNKNOWN')
        else:d['proposal_event_id']=self.refs['p']['event_id']
        if action=='NOMINATE':d['target_ref']='role-carol'
        if action=='ALIGNED':d.update(received_event_id=value['causation'],actual_checks=list(SNAPSHOT_FIELDS),unknown_items=[])
        if action=='VERIFIED':d.update(alignment_event_id=value['alignment_ref'],supervision_start_event_id=value['causation'],actual_checks=list(SNAPSHOT_FIELDS),unknown_items=[])
        from task_center_handoff_ledger import PHASES
        e=dict(schema_version=1,sanitization='MANUAL_REDACTED',namespace='tenant-ledger',event_id=value['event_id'],task_id='task-1',attempt_id='attempt-1',idempotency_key=value['event_id'],producer='writer',type=PHASES[action],validity='VERIFIED_NOW',causation=value['causation'],occurred_at=self.stamp,observed_at=self.stamp,source='source-ref',evidence='evidence-ref',result='observed',data=d)
        value['ledger_event']=e
        return value

    def test_transaction_to_non_synthetic_protected_readback_and_recovery(self):
        for action,label,cause,actor in [('PROPOSE','p','NONE','alice'),('NOMINATE','n','p','alice'),('RECEIVE','r','p','bob'),('ALIGNED','a','r','bob'),('SUPERVISION_START','s','n','carol'),('VERIFIED','v','s','carol')]:
            value=self.make(action,label,cause,actor)
            self.assertEqual(self.host.record(actor,value)['state'],'RECORDED')
            self.assertEqual(self.bridge.flush('task-1','attempt-1',value['event_id'])['enqueue'],'APPENDED')
        self.assertEqual(self.bridge.flush('task-1','attempt-1',value['event_id'])['enqueue'],'DUPLICATE')
        reader=MetadataReader(self.bridge.root,'tenant-ledger','writer','tenant-1',ledger_authority=self.bridge)
        result=reader.export('task-1')['handoff']['handoffs']['task-1:'+self.refs['p']['handoff_id']]
        self.assertEqual(result['handoff_status'],'交接完成(范围)')
        cls=build_handler(self.path,b'0123456789abcdef0123456789abcdef','tenant-1','viewer',admin_token='synthetic-admin-1',delivery_ledger_reader=reader)
        def get(admin):
            h=cls.__new__(cls);h.path='/api/admin/delivery-handoff?task_id=task-1';h.command='GET';h.headers={'Host':'localhost:8765'};h.server=SimpleNamespace(server_port=8765)
            if admin:h.headers['X-Test-Admin-Token']='synthetic-admin-1'
            out=[];h._send=lambda status,body,content_type,extra_headers=None:out.append((status,body));h.do_GET();return out[0]
        self.assertEqual(get(False)[0],403);self.assertEqual(get(True)[0],200)
        self.auth.verify_ledger_event_current=lambda event,record:False
        self.assertNotEqual(reader.export('task-1')['handoff']['handoffs']['task-1:'+self.refs['p']['handoff_id']]['handoff_status'],'交接完成(范围)')

    def test_unattested_mismatch_and_tamper_fail_closed(self):
        value=self.make('PROPOSE','p','NONE','alice');event=value['ledger_event']
        with self.assertRaises(LedgerError):Store(os.path.join(self.tmp.name,'other'),'writer').enqueue(event)
        self.auth.assess_ledger_event=lambda binding,event:False
        with self.assertRaises(ValueError):self.host.record('alice',value)
        self.assertEqual(self.db.execute("SELECT count(*) FROM events WHERE kind LIKE 'AUTHENTICATED_HANDOFF_%'").fetchone()[0],0)
        self.auth.assess_ledger_event=lambda binding,event:True
        bad=copy.deepcopy(value);bad['ledger_event']['data']['snapshot_data']['goal_acceptance_ref']='different'
        with self.assertRaises(LedgerError):self.host.record('alice',bad)
        self.host.record('alice',value);self.bridge.flush('task-1','attempt-1',value['event_id'])
        bad=copy.deepcopy(event);bad['evidence']='other-ref'
        with self.assertRaises(LedgerError):Store(self.bridge.root,'writer',authority=self.bridge).enqueue(bad)
        with self.assertRaises(Unavailable):MetadataReader(self.bridge.root,'tenant-ledger','writer','other',ledger_authority=self.bridge)
        # DB commit survives a missing publication; re-publication is idempotent.
        published=Path(self.bridge.root)/'events'/'tenant-ledger'/(event['event_id']+'.json')
        published.unlink()
        self.assertEqual(self.bridge.flush('task-1','attempt-1',event['event_id'])['flush']['appended'],1)
        published.write_bytes(canonical(bad))
        self.assertEqual(self.bridge.flush('task-1','attempt-1',event['event_id'])['flush']['conflict'],1)
        reader=MetadataReader(self.bridge.root,'tenant-ledger','writer','tenant-1',ledger_authority=self.bridge)
        with self.assertRaises(LedgerError):reader.export('task-1')


if __name__=='__main__':unittest.main()
