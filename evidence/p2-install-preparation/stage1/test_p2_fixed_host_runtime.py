import hashlib
import json
import os
import tempfile
import unittest
import subprocess
import sys
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

    def test_first_install_preflight_does_not_require_uninstalled_release(self):
        release='integration-'+'a'*16
        runtime={'release_directory':release,'services':list(module.ALLOWED_SERVICES),
                 'provisioning':[{'source':'deploy/unit',
                   'target':'/etc/systemd/system/unit.service','source_sha256':'b'*64,
                   'rendered_sha256':'c'*64,'mode':0o644,'owner_uid':0,
                   'group_gid':0,'replacements':{}}]}
        with patch.object(self.runtime,'_authority',return_value=None), \
             patch.object(self.runtime,'_reference',return_value=None), \
             patch.object(module,'_read_regular',side_effect=AssertionError('uninstalled release read')):
            self.assertTrue(self.runtime.preflight(runtime,{'references':[]},{'references':[]}))

    def test_installed_source_hash_mismatch_blocks_all_target_writes(self):
        release='/opt/xuanjun-control-releases/integration-'+'a'*16
        runtime={'release_directory':'integration-'+'a'*16,
                 'provisioning':[{'source':'deploy/unit',
                   'target':'/etc/systemd/system/unit.service','source_sha256':'b'*64,
                   'rendered_sha256':'c'*64,'mode':0o644,'owner_uid':0,
                   'group_gid':0,'replacements':{}}]}
        with patch.object(self.runtime,'_authority',return_value=None), \
             patch.object(module,'_read_regular',return_value=(b'changed',None)), \
             patch.object(self.runtime,'_atomic_target') as write:
            with self.assertRaisesRegex(ValueError,'SOURCE_HASH_MISMATCH'):
                self.runtime.provision(release,runtime)
            write.assert_not_called()

    def test_actual_cli_imports_from_stage1_without_pythonpath(self):
        root=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env=dict(os.environ); env.pop('PYTHONPATH',None)
        result=subprocess.run([sys.executable,'-I','-B',
            os.path.join(root,'scripts','uk-p2-install.py'),'--help'],
            env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.assertEqual(result.returncode,0,result.stderr.decode())

    def _rollback_fixture(self, originals):
        targets = []
        for number, original in enumerate(originals):
            target = os.path.join(self.temp.name, 'target-%d' % number)
            with open(target, 'wb') as stream: stream.write(b'installed')
            os.chmod(target, 0o600)
            info = os.stat(target)
            previous = None
            if original is not None:
                backup = os.path.join(self.transaction, 'target-%d.backup' % number)
                with open(backup, 'wb') as stream: stream.write(original)
                previous = dict(backup=backup, sha256=module._digest_bytes(original),
                                mode=0o600, uid=info.st_uid, gid=info.st_gid)
            targets.append(dict(target=target, previous=previous,
                                rendered_sha256=module._digest_bytes(b'installed'),
                                mode=0o600, uid=info.st_uid, gid=info.st_gid))
        receipt = dict(schema=1, targets=targets, services=[], rollback_complete=True)
        raw = json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode('utf-8')
        with open(self.runtime.receipt_path, 'wb') as stream: stream.write(raw)
        return targets, dict(receipt_sha256=module._digest_bytes(raw))

    def test_changed_new_target_is_not_deleted_during_rollback(self):
        targets, proof = self._rollback_fixture([None])
        with open(targets[0]['target'], 'wb') as stream: stream.write(b'other-owner-change')
        with patch.object(self.runtime, '_authority'), \
             patch.object(module, 'ALLOWED_TARGET_PREFIXES', (self.temp.name + '/',)):
            with self.assertRaisesRegex(ValueError, 'TARGET_CHANGED'):
                self.runtime.restore(proof)
        with open(targets[0]['target'], 'rb') as stream:
            self.assertEqual(stream.read(), b'other-owner-change')
        self.assertEqual(self.commands, [])

    def test_late_corrupt_backup_blocks_all_rollback_writes(self):
        targets, proof = self._rollback_fixture([b'old-first', b'old-second'])
        with open(targets[0]['previous']['backup'], 'wb') as stream: stream.write(b'corrupt')
        with patch.object(self.runtime, '_authority'), \
             patch.object(module, 'ALLOWED_TARGET_PREFIXES', (self.temp.name + '/',)), \
             patch.object(self.runtime, '_atomic_target') as write:
            with self.assertRaisesRegex(ValueError, 'BACKUP_CHANGED'):
                self.runtime.restore(proof)
            write.assert_not_called()
        self.assertEqual(self.commands, [])

    def test_exact_rollback_restores_old_and_removes_only_unchanged_new(self):
        targets, proof = self._rollback_fixture([b'original', None])
        with patch.object(self.runtime, '_authority'), \
             patch.object(module, 'ALLOWED_TARGET_PREFIXES', (self.temp.name + '/',)):
            self.assertEqual(self.runtime.restore(proof)['services_restarted'], False)
        with open(targets[0]['target'], 'rb') as stream:
            self.assertEqual(stream.read(), b'original')
        self.assertFalse(os.path.lexists(targets[1]['target']))
        self.assertEqual(self.commands, [['/usr/bin/systemctl', 'daemon-reload']])


if __name__=='__main__': unittest.main()
