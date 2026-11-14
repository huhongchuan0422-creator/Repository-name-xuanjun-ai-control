import json
import unittest
from task_center_mcp_dispatch_host import dispatch_rpc, validate_config, WRITE_TOOLS
from task_center_mcp_development import DevelopmentHost, ACTIONS, EXTRA

class NoService:
    def __getattr__(self, key):
        raise AssertionError('service access forbidden: '+key)

class ContractClassificationTests(unittest.TestCase):
    def setUp(self):
        self.identity={'tenant_id':'t','principal_id':'alice','project_id':'p','scopes':['task:read']}
        self.actions=[name for name,phase in ACTIONS.items() if phase in (None,'EXECUTOR')]
        row={'tenant_id':'t','principal_id':'alice','project_id':'p','task_id':'task',
             'spec_sha256':'a'*64,'checkpoint_sha256':'b'*64,'contract_sha256':'c'*64,
             'role_id':'executor','role_version':'v1','phase':'EXECUTOR','review_kind':None,
             'authority_identity':{'issuer':'synthetic','subject':'synthetic'},
             'actions':self.actions,'candidate_root':None,'executor_profile':None}
        self.host=DevelopmentHost([row]); self.config=validate_config(None)
    def rpc(self,identity,method,params):
        return dispatch_rpc(NoService(),identity,self.config,
            {'jsonrpc':'2.0','id':1,'method':method,'params':params},False,self.host)
    def contract(self,identity):
        return json.loads(self.rpc(identity,'tools/call',{'name':'task_dispatch_contract','arguments':{}})['result']['content'][0]['text'])
    def test_mixed_visible_classification_and_gates(self):
        listed=[x['name'] for x in self.rpc(self.identity,'tools/list',{})['result']['tools']]
        c=self.contract(self.identity)
        self.assertEqual(listed,c['host_surface']['visible_tools'])
        writes=set(self.actions)-{'task_development_status','task_development_gateway_readback'}
        self.assertEqual(set(c['mutating_orchestration_tools']),writes)
        self.assertNotIn('task_submit',c['mutating_orchestration_tools'])
        self.assertFalse(c['execution_connected'])
        self.assertEqual(c['status'],'SOURCE_CANDIDATE_NOT_WIRED')
        self.assertEqual(c['unknown_effects_policy'],'HOLD_NO_REPLAY')
        self.assertEqual(len(c['unverified_runtime_gates']),5)
        self.assertTrue(c['host_surface']['visibility_is_not_authorization_or_execution_readiness'])
    def test_cross_identity_and_project_do_not_leak(self):
        for key in ('tenant_id','principal_id','project_id'):
            other=dict(self.identity,**{key:'other'})
            names=[x['name'] for x in self.rpc(other,'tools/list',{})['result']['tools']]
            c=self.contract(other)
            self.assertEqual(c['host_surface']['visible_tools'],names)
            self.assertFalse(set(names)&set(self.actions))
            self.assertFalse(c['mutating_orchestration_tools'])
    def test_five_read_only_scope_rejected_before_service_and_write_set_unchanged(self):
        names=['task_development_gateway_candidate','task_development_gateway_test_event',
               'task_development_gateway','task_development_continue_review','task_development_verify_tests']
        self.assertFalse(set(names)&WRITE_TOOLS)
        for name in names:
            args={k:'fixture' for k in ('task_id','attempt_id')+EXTRA[name]}
            args['task_id']='task'
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError,'DEVELOPMENT_OAUTH_SCOPE_REQUIRED'):
                    self.rpc(self.identity,'tools/call',{'name':name,'arguments':args})

if __name__=='__main__': unittest.main()
