import copy
import importlib.util
import os
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
if 'P2_FEISHU_INTEGRATION_ROOT' not in os.environ:
    raise unittest.SkipTest('Overlaid package absent: install gate NOT_RUN')
ROOT=pathlib.Path(os.environ['P2_FEISHU_INTEGRATION_ROOT'])
sys.path.insert(0,str(ROOT/'stage1'))
spec=importlib.util.spec_from_file_location('feishu_fixed_host_runtime',str(ROOT/'stage1/p2_fixed_host_runtime.py'))
runtime_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime_module)


class InstallGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.runtime=runtime_module.FixedHostRuntime(self.tmp.name)
        self.runtime._authority=lambda:None
        self.runtime.prerequisites.preflight=lambda value:None
        self.runtime._plugin_present=lambda value:False
        self.runtime._reference=lambda value:None
        self.commands=[]
        self.runtime.run=lambda command,**kwargs:self.commands.append(command) or types.SimpleNamespace(returncode=0)
        plugin={'gateway_service':runtime_module.GATEWAY_SERVICE,'id':runtime_module.P2_PLUGIN_ID,
            'binding_file':'/etc/xuanjun-development/p2-native-binding.json','binding_sha256':'a'*64,
            'ledger_client_config':'/etc/xuanjun-development/p2-native-client.json','ledger_client_sha256':'a'*64,
            'docker_dropin':'/etc/systemd/system/xuanjun-uk-openclaw.service.d/p2.conf',
            'gateway_relay_config':'/etc/xuanjun-development/p2-gateway-relay.json','gateway_relay_sha256':'a'*64}
        def binding(target):return {'source':'deploy/fixture.template','target':target,'source_sha256':'a'*64,
            'rendered_sha256':'a'*64,'mode':0o640,'owner_uid':0,'group_gid':42,'replacements':{}}
        targets=[plugin[key] for key in ('binding_file','ledger_client_config','docker_dropin','gateway_relay_config')]
        owner=binding('/etc/xuanjun-development/p2-owner-feishu-binding.json')
        owner.update({'source':'deploy/p2-owner-feishu-binding.json.template',
            'replacements':{'@@CHAT_ID@@':'oc_fixture','@@APP_ID@@':'cli_fixture','@@PACKAGE_SHA256@@':'a'*64}})
        self.plan={'services':runtime_module.ALLOWED_SERVICES,'prerequisites':{},'plugin':plugin,
            'provisioning':[binding(target) for target in targets]+[owner],'release_directory':'fixture'}
        self.auth={'references':[{'path':'/home/xuanjun_dev/.openclaw/openclaw.json','owner_uid':42,'mode':0o600}]}

    def preflight(self):
        with patch.object(runtime_module.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=42,pw_gid=42)):
            return self.runtime.preflight(self.plan,self.auth,{'references':[]})

    def test_protected_receiver_and_existing_profile_required(self):
        self.assertTrue(self.preflight())
        self.plan['provisioning'].pop();self.commands.clear()
        with self.assertRaisesRegex(ValueError,'OWNER_FEISHU_PROVISIONING_REQUIRED'):self.preflight()
        self.assertEqual(self.commands,[])

    def test_wrong_receiver_hash_mode_owner_rejected_before_commands(self):
        original=copy.deepcopy(self.plan['provisioning'][-1])
        for field,value in [('mode',0o644),('owner_uid',42),('group_gid',99)]:
            self.plan['provisioning'][-1]=copy.deepcopy(original)
            self.plan['provisioning'][-1][field]=value
            with self.assertRaises(ValueError):self.preflight()
        self.plan['provisioning'][-1]=copy.deepcopy(original)
        self.plan['provisioning'][-1]['replacements']['@@CHAT_ID@@']='oc_fixture"injection'
        with self.assertRaises(ValueError):self.preflight()
        self.assertEqual(self.commands,[])

    def test_missing_or_nonprivate_credential_reference_rejected(self):
        self.auth['references']=[]
        with self.assertRaisesRegex(ValueError,'OWNER_FEISHU_EXISTING_PROFILE_REFERENCE_REQUIRED'):self.preflight()
        self.assertEqual(self.commands,[])

    def test_wrong_active_package_rejected_before_service_start(self):
        with patch('owner_feishu_https.installed_binding',return_value={'package_sha256':'a'*64}):
            with self.assertRaisesRegex(ValueError,'OWNER_FEISHU_ACTIVE_PACKAGE_MISMATCH'):
                self.runtime.activate(self.plan,{'state':'ACTIVE','release_sha256':'b'*64})
        self.assertEqual(self.commands,[])

    def test_public_template_is_valid_json(self):
        import json
        value=json.loads((ROOT/'deploy/p2-owner-feishu-binding.json.template').read_text())
        self.assertEqual(set(value),{'chat_id','app_id','package_sha256'})
