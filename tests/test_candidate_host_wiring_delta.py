"""Existing lifecycle producer -> MCP submit -> host delegation -> HTTP accept."""
import hashlib,json,os,tempfile,threading,unittest
import test_mcp_acceptance_evidence_delta as fixture
import test_task_center_mcp_http as http_fixture
from development_authority_release import lifecycle
from task_center_handoff_host import HostAuthAdapter,HandoffHost
from task_center_app import make_server

class DelegateHost(HostAuthAdapter):
    def __init__(self, identity):self.identity=identity
    def authenticate_and_authorize(self,*args):return self.identity.authenticate_and_authorize(*args)
    def assess_backup(self,binding):return self.identity.assess_backup(binding)
    def assess_provider(self,binding):return self.identity.assess_provider(binding)

class HostWiring(fixture.AcceptanceEvidence):
    def test_lifecycle_producer_digest_to_original_submit_and_host_http(self):
        with tempfile.TemporaryDirectory() as root:
            path=os.path.join(root,'candidate-bundle')
            with open(path,'wb') as out:out.write(self.adapter.content)
            # Isolated synthetic verified receipt; no production signature asserted.
            receipt=lifecycle(root,'apply',path,{'verified':True})
            digest=receipt['state']['active']
            self.assertEqual(digest,hashlib.sha256(self.adapter.content).hexdigest())
            self.assertEqual(lifecycle(root,'inspect')['active_observed'],digest)
            adapter=DelegateHost(self.adapter)
            self.host=HandoffHost(self.h.supervisor.db,'tenant-mcp','formal-fixture',adapter,
                mcp_config=self.config,role_contract=self.contract,candidate_lifecycle_root=root)
            h=self.h
            cid=h.rpc(h.token(principal='developer-1'),'task_submit_candidate',self.fx.args(
                artifact_sha256=digest,checklist_sha256=self.fx.check))['candidate_id']
            for actor in ('qa','security'):
                h.rpc(h.token(principal=actor),'task_review_candidate',self.fx.args(candidate_id=cid,findings=[],passed=True))
            self.handoff(cid)
            if h.f.server.mcp_worker:h.f.server.mcp_worker.stop()
            h.f.server.shutdown();h.f.server.server_close();h.f.thread.join(2)
            import copy
            cfg=copy.deepcopy(self.config);cfg['bindings'][0]['roles']={'developer':cfg['bindings'][0]['roles']['developer']}
            h.f.server=make_server(h.f.db,http_fixture.KEY,'tenant-mcp','owner',port=0,
                model_master_key=h.f.master,identity_provider=h.f.identity,session_store=h.f.sessions,
                outbound_enabled=False,external_origin='https://'+http_fixture.HOST,base_path='/task-center-test/',
                mcp_enabled=True,mcp_model_worker_enabled=False,mcp_dispatch_config=cfg,handoff_host=self.host)
            h.f.thread=threading.Thread(target=h.f.server.serve_forever,daemon=True);h.f.thread.start()
            h.f.base='http://127.0.0.1:%d/task-center-test'%h.f.server.server_port
            token=h.token(principal='acceptor')
            result=h.rpc(token,'task_accept_candidate',self.fx.args(candidate_id=cid))
            self.assertEqual(result['state'],'ACCEPTED')
            detail=json.loads(h.control.db.execute("SELECT detail_json FROM model_audit WHERE action='CANDIDATE_EVIDENCE_BOUND' AND target_id=?",(cid,)).fetchone()[0])
            self.assertEqual(detail['read_location_ref_sha256'],hashlib.sha256(('lifecycle-artifact:'+digest).encode()).hexdigest())

if __name__=='__main__':unittest.main()
