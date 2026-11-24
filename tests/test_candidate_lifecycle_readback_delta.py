"""Local existing lifecycle -> original MCP acceptance; simulated identity/backup."""
import hashlib, os, tempfile, unittest
import test_mcp_acceptance_evidence_delta as fixture
from development_authority_release import lifecycle
from task_center_candidate_readback import LifecycleCandidateReadback

class CandidateLifecycleReadback(fixture.AcceptanceEvidence):
    def setUp(self):
        super().setUp()
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=os.path.join(self.tmp.name,'bundle')
        with open(self.path,'wb') as f:f.write(self.adapter.content)
        # Existing lifecycle producer path; fixture receipt, no signature claim.
        lifecycle(self.tmp.name,'apply',self.path,{'verified':True})
        self.adapter.assess_candidate_bundle=LifecycleCandidateReadback(self.h.supervisor.db,'tenant-mcp',self.tmp.name)
    def test_missing_handoff_and_unreadable_artifact_fail_closed(self):
        # Same fail-closed boundaries as the inherited fixture test; only the
        # unreadable-artifact injection is moved to the real lifecycle store
        # this class installed in place of the simulated bundle bytes.
        cid=self.make_candidate();self.handoff(cid)
        digest=hashlib.sha256(self.adapter.content).hexdigest()
        path=os.path.join(self.tmp.name,'artifacts',digest)
        with open(path,'wb') as f:f.write(b'different-bytes')
        with self.assertRaisesRegex(ValueError,'CANDIDATE_BUNDLE_READBACK_REQUIRED'):self.call(cid)
        with open(path,'wb') as f:f.write(self.adapter.content)
        self.h.control.db.execute("DELETE FROM events WHERE event_id=?",('handoff-contract:'+self.adapter.event,));self.h.control.db.commit()
        with self.assertRaisesRegex(ValueError,'CANDIDATE_HANDOFF_RECEIPTS_REQUIRED'):self.call(cid)
        self.assertEqual(self.h.supervisor._task('demo-b')['state'],'STARTED')
    def test_original_rpc_reads_existing_lifecycle_artifact(self):
        cid=self.make_candidate();self.handoff(cid)
        # Restart the original HTTP app with this host-injected adapter.
        import threading
        from task_center_app import make_server
        import test_task_center_mcp_http as http_fixture
        h=self.h
        if h.f.server.mcp_worker:h.f.server.mcp_worker.stop()
        h.f.server.shutdown();h.f.server.server_close();h.f.thread.join(2)
        import copy
        cfg=copy.deepcopy(self.config)
        cfg['bindings'][0]['roles']={'developer':cfg['bindings'][0]['roles']['developer']}
        h.f.server=make_server(h.f.db,http_fixture.KEY,'tenant-mcp','owner',port=0,
          model_master_key=h.f.master,identity_provider=h.f.identity,session_store=h.f.sessions,
          outbound_enabled=False,external_origin='https://'+http_fixture.HOST,base_path='/task-center-test/',
          mcp_enabled=True,mcp_model_worker_enabled=False,mcp_dispatch_config=cfg,handoff_host=self.host)
        h.f.thread=threading.Thread(target=h.f.server.serve_forever,daemon=True);h.f.thread.start()
        h.f.base='http://127.0.0.1:%d/task-center-test'%h.f.server.server_port
        token=h.token(principal='acceptor')
        result=h.rpc(token,'task_accept_candidate',self.fx.args(candidate_id=cid))
        self.assertEqual(result['state'],'ACCEPTED')
        self.assertTrue(h.rpc(token,'task_accept_candidate',self.fx.args(candidate_id=cid))['duplicate'])
        digest=hashlib.sha256(self.adapter.content).hexdigest()
        row=self.h.control.db.execute("SELECT detail_json FROM model_audit WHERE action='CANDIDATE_EVIDENCE_BOUND' AND target_id=?",(cid,)).fetchone()
        import json
        self.assertEqual(json.loads(row[0])['read_location_ref_sha256'],hashlib.sha256(('lifecycle-artifact:'+digest).encode()).hexdigest())
    def test_changed_artifact_does_not_complete(self):
        cid=self.make_candidate();self.handoff(cid)
        digest=hashlib.sha256(self.adapter.content).hexdigest()
        with open(os.path.join(self.tmp.name,'artifacts',digest),'wb') as f:f.write(b'changed')
        with self.assertRaisesRegex(ValueError,'CANDIDATE_BUNDLE_READBACK_REQUIRED'):self.call(cid)
        self.assertEqual(self.h.supervisor._task('demo-b')['state'],'STARTED')
