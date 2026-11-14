import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from task_center_mcp_dispatch_host import dispatch_rpc, validate_config


class NoService:
    def __getattr__(self, name):
        raise AssertionError('unexpected service access: ' + name)


class HostSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.identity = {'tenant_id':'t', 'principal_id':'u', 'project_id':'p', 'scopes':['task:read']}
        self.config = validate_config({'schema_version':1, 'enabled':True, 'bindings':[
            {'tenant_id':'t', 'principal_id':'u', 'project_id':'p', 'roles':{'r':{
                'role_version':'v1', 'principal_id':'worker', 'provider_id':'provider',
                'model_id':'model', 'connection_id':'connection'}}}]})

    def rpc(self, method, params=None, config=None, identity=None):
        return dispatch_rpc(NoService(), identity or self.identity,
                            self.config if config is None else config,
                            {'id':1, 'method':method, 'params':params or {}}, False)

    def test_surface_matches_actual_list_without_claiming_ready(self):
        listed = [x['name'] for x in self.rpc('tools/list')['result']['tools']]
        result = self.rpc('tools/call', {'name':'task_dispatch_contract', 'arguments':{}})
        contract = json.loads(result['result']['content'][0]['text'])
        self.assertEqual(len(listed), 9)
        self.assertEqual(contract['host_surface']['visible_tools'], listed)
        self.assertEqual(contract['mutating_orchestration_tools'],
                         ['task_assign_role','task_dispatch','task_cancel_dispatch'])
        self.assertTrue(contract['host_surface']['task_submit_is_separate_test_only_entry'])
        self.assertTrue(contract['host_surface']['visibility_is_not_authorization_or_execution_readiness'])
        self.assertFalse(contract['execution_connected'])
        self.assertIn('CURRENT_WRITER_OWNERSHIP', contract['unverified_runtime_gates'])
        with self.assertRaisesRegex(ValueError, 'MCP_DISPATCH_SUBMIT_SCOPE_REQUIRED'):
            self.rpc('tools/call', {'name':'task_dispatch','arguments':{}})

    def test_disabled_or_other_identity_not_advertised(self):
        for config, identity in ((validate_config(None),self.identity),
                                 (self.config,dict(self.identity,project_id='other'))):
            result=self.rpc('tools/call', {'name':'task_dispatch_contract','arguments':{}},config,identity)
            contract=json.loads(result['result']['content'][0]['text'])
            self.assertEqual(contract['mutating_orchestration_tools'],[])
            self.assertEqual(len(contract['host_surface']['visible_tools']),5)

    def test_contract_arguments_still_validated(self):
        with self.assertRaisesRegex(ValueError,'EXACT_MCP_ARGUMENTS_REQUIRED'):
            self.rpc('tools/call', {'name':'task_dispatch_contract','arguments':{'role_id':'r'}})


if __name__ == '__main__': unittest.main()
