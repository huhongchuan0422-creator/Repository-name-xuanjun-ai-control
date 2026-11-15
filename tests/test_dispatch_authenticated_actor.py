import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_mcp_dispatch_host as host
from task_center_mcp_dispatch_host import dispatch_rpc, validate_config


class AuthenticatedActorCheckpoint(unittest.TestCase):
    def setUp(self):
        self.h = host.HostHTTPTests(methodName='test_http_assign_then_worker_off_rejects_dispatch')
        self.h.setUp()

    def tearDown(self):
        self.h.tearDown()

    def test_http_assignment_audits_real_subject_and_cancel_does_not_escalate(self):
        h=self.h
        token=h.token()
        attempt={'task_id':'demo-b','attempt_id':'attempt-b','role_id':'developer'}
        h.rpc(token,'task_assign_role',attempt)
        row=h.control.db.execute("SELECT principal_id FROM model_audit WHERE action='ROLE_ASSIGNED' AND target_id='demo-b' ORDER BY observed_at DESC LIMIT 1").fetchone()
        self.assertEqual(row['principal_id'],'owner-1')
        queued=h.control.queue_request('demo-b','developer',[{'role':'user','content':'fixture'}],
            'actor-checkpoint',16,'fixture-connection',expected_attempt_id='attempt-b',expected_project_id='project-mcp')
        req={'task_id':'demo-b','attempt_id':'attempt-b','request_id':queued['request_id']}
        with self.assertRaises(HTTPError) as caught:
            h.rpc(token,'task_cancel_dispatch',req)
        self.assertEqual(caught.exception.code,400)
        from task_center_mcp import RegisteredTaskDispatchMCP
        from model_orchestration import ModelControl
        actor=h.gateway.tenants.issue('tenant-mcp','owner-1')
        control=ModelControl(h.gateway,actor,h.f.master)
        facade=RegisteredTaskDispatchMCP(control,'project-mcp',host.config()['bindings'][0]['roles'])
        with self.assertRaisesRegex(ValueError,'MODEL_ADMIN_REQUIRED'):
            facade.call('task_cancel_dispatch',req)
        self.assertEqual(h.rpc(token,'task_dispatch_status',req)['request_state'],'QUEUED')
        self.assertEqual(host.fixture.ModelFixture.calls,0)

    def test_host_service_identity_mismatch_rejected_before_open(self):
        class Service:
            tenant_id='tenant-mcp'; principal_id='other'; project_id='project-mcp'
            def _open(self): raise AssertionError('must not open')
        identity={'tenant_id':'tenant-mcp','principal_id':'owner-1','project_id':'project-mcp','scopes':['task:submit']}
        call={'id':1,'method':'tools/call','params':{'name':'task_assign_role','arguments':{}}}
        with self.assertRaisesRegex(ValueError,'MCP_DISPATCH_IDENTITY_MISMATCH'):
            dispatch_rpc(Service(),identity,validate_config(host.config()),call,False)

if __name__ == '__main__': unittest.main()
