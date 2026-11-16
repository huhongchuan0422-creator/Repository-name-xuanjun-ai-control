import json
import pathlib
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from task_center_mcp import RemoteTaskCenterMCP, REMOTE_TOOLS

class NoExecutionService:
    def __getattr__(self, name):
        raise AssertionError('No service or model calls allowed: ' + name)

class DispatchContractTests(unittest.TestCase):
    def setUp(self):
        self.mcp = RemoteTaskCenterMCP(NoExecutionService())

    def test_contract_has_no_execution_or_grants(self):
        result = self.mcp.call('task_dispatch_contract', {})
        self.assertFalse(result['execution_connected'])
        self.assertFalse(result['model_text_is_execution_authority'])
        self.assertFalse(result['new_registry_queue_or_writer'])
        self.assertEqual(result['mutating_orchestration_tools'], [])
        self.assertEqual(result['unknown_effects_policy'], 'HOLD_NO_REPLAY')
        self.assertIn('DURABLE_DEPENDENCY_ACK', result['required_bindings'])

    def test_schema_and_rpc_match(self):
        listed = self.mcp.rpc({'id':1,'method':'tools/list'})['result']['tools']
        self.assertEqual(listed, list(REMOTE_TOOLS))
        self.assertEqual(len(listed), 5)
        result = self.mcp.rpc({'id':2,'method':'tools/call','params':{
            'name':'task_dispatch_contract','arguments':{}}})
        self.assertEqual(json.loads(result['result']['content'][0]['text'])['status'],
                         'SOURCE_CANDIDATE_NOT_WIRED')

    def test_extra_authority_and_identity_rejected_before_service(self):
        for name in ('task_dispatch_contract','task_capabilities','task_get','task_query_result'):
            for key in ('tenant_id','principal_id','role_id','shell','path','allow_paid'):
                with self.subTest(name=name,key=key):
                    with self.assertRaises(ValueError):
                        self.mcp.call(name, {'task_id':'a',key:'override'})

    def test_invalid_submit_rejected_before_service(self):
        valid={'project_id':'p','task_type':'TEXT_CLASSIFICATION','input_text':'hi',
               'idempotency_key':'i','connection_id':'c','max_output_tokens':1}
        for key,value in [('task_type','DEVELOPMENT'),('max_output_tokens',True),
                          ('max_output_tokens',129),('max_output_tokens',0),
                          ('input_text','x'*4001),('input_text',42),
                          ('project_id',''),('allow_paid',True)]:
            with self.subTest(key=key,value=str(value)[:30]):
                with self.assertRaises(ValueError):
                    self.mcp.call('task_submit',dict(valid, **{key:value}))

    def test_missing_and_nonobject_arguments_rejected(self):
        for args in ({}, [], 'x', {'task_id':None}):
            with self.assertRaises(ValueError): self.mcp.call('task_get',args)

    def test_contract_is_not_mutable_shared_authority(self):
        a=self.mcp.call('task_dispatch_contract',{})
        a['execution_connected']=True
        a['required_bindings'].clear()
        b=self.mcp.call('task_dispatch_contract',{})
        self.assertFalse(b['execution_connected'])
        self.assertTrue(b['required_bindings'])

    def test_unwired_tools_cannot_dispatch(self):
        for name in ('task_assign_role','task_dispatch','task_schedule','task_cancel'):
            with self.assertRaisesRegex(ValueError,'UNKNOWN_MCP_TOOL'):
                self.mcp.call(name,{})

if __name__=='__main__': unittest.main()
