import hashlib
import os
import tempfile
import unittest
from unittest.mock import patch

import p2_fixed_host_runtime as module


class Result(object):
    returncode=0


class FixedRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.transaction=os.path.join(self.temp.name,'transaction'); os.mkdir(self.transaction,0o700)
        self.commands=[]
        self.runtime=module.FixedHostRuntime(self.transaction,self._run)

    def _run(self,command,**unused): self.commands.append(command); return Result()

    def test_reference_checks_hash_owner_and_private_mode(self):
        path=os.path.join(self.temp.name,'auth');
        with open(path,'wb') as stream: stream.write(b'oauth')
        os.chmod(path,0o600); info=os.stat(path)
        value={'path':path,'sha256':hashlib.sha256(b'oauth').hexdigest(),
               'owner_uid':info.st_uid,'mode':0o600}
        self.runtime._reference(value)
        for key,replacement in (('sha256','0'*64),('mode',0o644),('owner_uid',info.st_uid+1)):
            broken=dict(value); broken[key]=replacement
            with self.assertRaisesRegex(ValueError,'IDENTITY_MISMATCH'):
                self.runtime._reference(broken)

    def test_render_requires_complete_tokens_and_exact_hash(self):
        rendered=b'x=value\n'
        binding={'replacements':{'@@VALUE@@':'value'},
                 'rendered_sha256':hashlib.sha256(rendered).hexdigest()}
        self.assertEqual(self.runtime._render(b'x=@@VALUE@@\n',binding),rendered)
        broken=dict(binding); broken['replacements']={}
        with self.assertRaisesRegex(ValueError,'UNRESOLVED'):
            self.runtime._render(b'x=@@VALUE@@\n',broken)

    def test_service_order_is_fixed_and_rollback_never_restarts(self):
        with patch.object(self.runtime,'_authority',return_value=None):
            self.runtime.stop_new({'services':list(module.ALLOWED_SERVICES)})
        stopped=[command[-1] for command in self.commands]
        self.assertEqual(stopped,list(reversed(module.ALLOWED_SERVICES)))
        self.assertTrue(all(command[1]=='stop' for command in self.commands))

    def test_binding_rejects_escape_duplicate_authority_and_writable_mode(self):
        release='/opt/xuanjun-control-releases/integration-'+'a'*16
        base={'source':'deploy/unit','target':'/etc/systemd/system/unit.service',
              'source_sha256':'b'*64,'rendered_sha256':'c'*64,'mode':0o644,
              'owner_uid':0,'group_gid':0,'replacements':{}}
        self.runtime._binding(base,release)
        mutations=(('source','../escape'),('target','/tmp/unit'),('mode',0o666))
        for key,replacement in mutations:
            broken=dict(base); broken[key]=replacement
            with self.assertRaisesRegex(ValueError,'INVALID_PROVISIONING_BINDING'):
                self.runtime._binding(broken,release)


if __name__=='__main__': unittest.main()
