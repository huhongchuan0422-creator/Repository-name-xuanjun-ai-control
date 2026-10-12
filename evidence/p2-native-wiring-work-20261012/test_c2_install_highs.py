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
