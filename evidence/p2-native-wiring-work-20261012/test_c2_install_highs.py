from __future__ import print_function
import hashlib
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE=pathlib.Path(os.environ['P2_SOURCE_ROOT'])/'stage1'
sys.path.insert(0,str(SOURCE))
import p2_fixed_host_runtime as mod

class ProbeRuntime(mod.FixedHostRuntime):
    def __init__(self,directory):
        self.directory=directory
        self.receipt_path=os.path.join(directory,'provision.json')
        self.effects=[]
        self.prerequisites=type('P',(object,),{'rollback':lambda s,x:self.effects.append(('prereq',x))})()
    def _authority(self): return True
    def _rollback_plugin(self,runtime,restart): self.effects.append(('plugin',restart))
    def _command(self,command): self.effects.append(('command',tuple(command)))
    def _start_gateway(self): self.effects.append(('start',))
    @staticmethod
    def _atomic_target(path,data,mode,uid,gid): raise AssertionError('target mutation before validation')

def write_receipt(root,target,current,installed=b'installed',old=b'old'):
    backup=os.path.join(root,'target-000.backup')
    pathlib.Path(backup).write_bytes(old)
    pathlib.Path(target).write_bytes(current)
    receipt={'schema':1,'targets':[{'target':target,'previous':{'backup':backup,
        'sha256':hashlib.sha256(old).hexdigest(),'mode':0o600,'uid':os.getuid(),'gid':os.getgid()},
        'rendered_sha256':hashlib.sha256(installed).hexdigest(),
        'mode':0o600,'uid':os.getuid(),'gid':os.getgid()}],
        'services':list(mod.ALLOWED_SERVICES),'rollback_complete':True,
        'prerequisites':{},'plugin':{'id':mod.P2_PLUGIN_ID,'previous':'ABSENT',
        'gateway_service':mod.GATEWAY_SERVICE,'dropin_parent_created':False}}
    raw=json.dumps(receipt,sort_keys=True,separators=(',',':')).encode('utf-8')
    pathlib.Path(os.path.join(root,'provision.json')).write_bytes(raw)
    return {'schema':1,'receipt_sha256':hashlib.sha256(raw).hexdigest(),'rollback_complete':True}

class NativeRuntimeManifestTests(unittest.TestCase):
    def test_all_native_runtime_dependencies_are_manifested(self):
        root=pathlib.Path(os.environ['P2_SOURCE_ROOT'])
        manifest=json.loads((root/'deploy'/'integration-manifest.json').read_text())
        required=set('stage1/'+name for name in (
            'native_pipeline_runtime.py','native_gateway_controller.py',
            'native_github_notifier.py','native_ledger_bridge.py',
            'native_ledger_operations.py','native_peer_identity.py'))
        self.assertTrue(required.issubset(set(manifest['files'])))

class PlanTlsBindingTests(unittest.TestCase):
    def _plan(self):
        import p2_install_entrypoint as entry
        h='a'*64;u='12345678-1234-4234-8234-123456789abc'
        return {'schema':1,'transaction_id':u,
            'artifact':{'root':'/opt/p2','manifest':'/opt/p2/manifest.json',
                'source_commit':'b'*40,'source_tree':'c'*40,'manifest_sha256':h,
                'releases':'/opt/xuanjun-control-releases'},
            'cutover':{},
            'activation':{'release_sha256':h,'config_sha256':h,'binary_sha256':h,
                'ledger_uuid':u,'generation':1,'instance':u,
                'db_path':'/var/lib/xuanjun-development/db.sqlite',
                'ledger_socket':'/run/xuanjun-development/ledger.sock','expected_epoch':0},
            'runtime':{'release_directory':'integration-'+'d'*16,
                'provisioning':[
                    {'target':'/etc/xuanjun-development/p2-native-controller.binding.json'},
                    {'target':'/etc/xuanjun-development/p2-native-ledger-client.json'},
                    {'target':'/etc/systemd/system/xuanjun-uk-openclaw.service.d/20-p2-docker.conf'}],
                'services':['xuanjun-ledger.socket','xuanjun-ledger.service',
                    'xuanjun-github-intake.service','xuanjun-github-intake.timer',
                    'xj-root-broker.socket','xj-root-broker.service',
                    'xuanjun-development-dispatcher.service'],
                'prerequisites':{},
                'plugin':{'id':'xuanjun-p2-native-controller','source':'plugins/p2-native-controller',
                    'binding_file':'/etc/xuanjun-development/p2-native-controller.binding.json',
                    'binding_sha256':h,
                    'ledger_client_config':'/etc/xuanjun-development/p2-native-ledger-client.json',
                    'ledger_client_sha256':h,'gateway_service':'xuanjun-uk-openclaw.service',
                    'openclaw_bin':'/home/xuanjun_dev/.openclaw/bin/openclaw',
                    'service_user':'xuanjun_dev',
                    'docker_dropin':'/etc/systemd/system/xuanjun-uk-openclaw.service.d/20-p2-docker.conf'}},
            'auth':{'mode':'EXISTING_OAUTH_REFERENCE','references':[{
                'path':'/home/xuanjun_dev/.openclaw/agents/developer/agent/openclaw-agent.sqlite',
                'sha256':h,'owner_uid':1002,'mode':0o600}]},
            'tls':{'mode':'NOT_APPLICABLE_NO_NGINX','references':[]}}

    def test_no_nginx_requires_explicit_no_tls_mode(self):
        import p2_install_entrypoint as entry
        plan=self._plan()
        self.assertTrue(entry.validate_plan(plan))
        plan['tls']={'mode':'EXISTING_TLS_REFERENCE','references':[]}
        with self.assertRaises(ValueError):entry.validate_plan(plan)

    def test_nginx_target_requires_real_tls_reference(self):
        import p2_install_entrypoint as entry
        plan=self._plan()
        plan['runtime']['provisioning'].append({'target':'/etc/nginx/conf.d/p2.conf'})
        with self.assertRaises(ValueError):entry.validate_plan(plan)

class RollbackValidationTests(unittest.TestCase):
    def test_target_drift_has_zero_external_effects(self):
        with tempfile.TemporaryDirectory() as root:
            target=os.path.join(root,'target.conf')
            reference=write_receipt(root,target,b'changed')
            runtime=ProbeRuntime(root)
            with patch.object(mod,'ALLOWED_TARGET_PREFIXES',(root+os.sep,)):
                with self.assertRaises(ValueError):
                    runtime.restore(reference)
            self.assertEqual(runtime.effects,[])

    def test_unsafe_target_has_zero_external_effects(self):
        with tempfile.TemporaryDirectory() as root:
            target=os.path.join(root,'target.conf')
            reference=write_receipt(root,target,b'installed')
            runtime=ProbeRuntime(root)
            with self.assertRaises(ValueError):
                runtime.restore(reference)
            self.assertEqual(runtime.effects,[])

if __name__=='__main__':unittest.main(verbosity=2)
