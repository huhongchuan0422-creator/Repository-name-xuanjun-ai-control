import copy
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import p2_prerequisites as module


def plan():
    groups={name:1003+i for i,name in enumerate(sorted(module.GROUPS))}
    users={name:dict(uid=1103+i,gid=groups[name],
        home='/var/lib/xuanjun-development/'+name,
        groups=[] if name=='xj_codex_worker' else ['xuanjun-control-db'])
        for i,name in enumerate(sorted(module.USERS))}
    return dict(schema=1,groups=groups,users=users,binaries=[],directories=[dict(
        path='/var/lib/xuanjun-development',uid=0,gid=0,mode=0o755)])


class Tests(unittest.TestCase):
    def test_private_groups_and_paths_cannot_expand_authority(self):
        original=plan();self.assertTrue(module.validate(original))
        for change in ('uid','group','path','worker_groups','mode'):
            p=copy.deepcopy(original)
            if change=='uid':p['users']['xj_codex_worker']['uid']=0
            if change=='group':p['groups']['docker']=1234
            if change=='path':p['directories'][0]['path']='/etc/sudoers.d'
            if change=='worker_groups':p['users']['xj_codex_worker']['groups']=['xuanjun-control-db']
            if change=='mode':p['directories'][0]['mode']=0o777
            with self.assertRaises(ValueError):module.validate(p)

    def test_authority_directories_cannot_be_owned_by_worker(self):
        p=plan();p['directories'][0]['uid']=p['users']['xj_codex_worker']['uid']
        with self.assertRaisesRegex(ValueError,'ROOT_OWNED'):module.validate(p)

    def test_credentials_cannot_be_declared_as_runtime_binary(self):
        p=plan();p['binaries']=[dict(source='/home/xuanjun_dev/.codex/auth.json',
            target='/opt/xuanjun-runtime/codex-0.160.0/codex',sha256='a'*64)]
        with self.assertRaisesRegex(ValueError,'PINNED_CODE_BINARY'):module.validate(p)

    def test_uid_collision_prevents_all_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            obj=module.Prerequisites(d)
            with patch.object(obj,'authority'),patch.object(obj,'command') as command, \
                 patch('p2_prerequisites.grp.getgrnam',side_effect=KeyError), \
                 patch('p2_prerequisites.grp.getgrgid',side_effect=KeyError), \
                 patch('p2_prerequisites.pwd.getpwnam',side_effect=KeyError), \
                 patch('p2_prerequisites.pwd.getpwuid',return_value=object()):
                with self.assertRaisesRegex(ValueError,'UID_ALREADY_ALLOCATED'):
                    obj.preflight(plan())
                command.assert_not_called()
            self.assertFalse(os.path.exists(obj.path))

    def test_unreviewed_group_member_prevents_bootstrap(self):
        with tempfile.TemporaryDirectory() as d:
            p=plan();obj=module.Prerequisites(d)
            def group(name):return SimpleNamespace(gr_gid=p['groups'][name],gr_mem=['root'])
            with patch.object(obj,'authority'),patch('p2_prerequisites.grp.getgrnam',side_effect=group):
                with self.assertRaisesRegex(ValueError,'UNREVIEWED_GROUP_MEMBERS'):
                    obj.preflight(p)

    def test_binary_hash_is_bounded_and_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            p=d+'/codex'
            with open(p,'wb') as f:f.write(b'approved executable')
            h,info=module.file_hash(p)
            self.assertEqual(len(h),64)
            os.symlink(p,d+'/link')
            with self.assertRaises(OSError):module.file_hash(d+'/link')

    def test_failed_external_effect_is_journaled_and_cannot_be_blindly_rolled_back(self):
        with tempfile.TemporaryDirectory() as d:
            obj=module.Prerequisites(d);p=plan()
            def fail(args):
                with open(obj.path) as f:receipt=json.load(f)
                self.assertEqual(receipt['actions'][-1]['state'],'INTENT')
                raise RuntimeError('unknown command outcome')
            with patch.object(obj,'preflight',return_value=True), \
                 patch('p2_prerequisites.grp.getgrnam',side_effect=KeyError), \
                 patch.object(obj,'command',side_effect=fail):
                with self.assertRaises(RuntimeError):obj.apply(p)
            with patch.object(obj,'authority'),patch.object(obj,'command') as command:
                with self.assertRaisesRegex(ValueError,'UNKNOWN_PREREQUISITE_EFFECT'):
                    obj.rollback(p)
                command.assert_not_called()

    def test_existing_journal_prevents_replay(self):
        with tempfile.TemporaryDirectory() as d:
            obj=module.Prerequisites(d)
            with open(obj.path,'w') as f:f.write('{}')
            with patch.object(obj,'authority'):
                with self.assertRaisesRegex(ValueError,'EXISTING_PREREQUISITE_JOURNAL'):
                    obj.preflight(plan())


if __name__=='__main__':unittest.main()
