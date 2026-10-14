import copy
import json
import os
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

import epoch7_resource_observer as r
import epoch7_exact_access as a
import epoch7_delta as d


class ResourceTests(unittest.TestCase):
    def setUp(self):
        base=str(pathlib.Path(__import__('epoch7_protected_fs').__file__).resolve().parent/'fixtures')
        self.root=tempfile.mkdtemp(prefix='resource-',dir=base)
        os.chmod(self.root,0o700);os.mkdir(self.root+'/private',0o700)
        self.raw=b'{"allowed":{"state":"READY"},"secret":"never emitted"}\n'
        pathlib.Path(self.root+'/private/data.json').write_bytes(self.raw);os.chmod(self.root+'/private/data.json',0o600)
        directory={'uid':os.geteuid(),'gid':os.getegid(),'mode':0o700,
                   'access_acl':'user::rwx\ngroup::---\nother::---\n','default_acl':''}
        self.reader=r.ResourceReader({'/':[directory],'/private':[directory]},mock.Mock(),self.root)
        self.reader.start()
        self.spec={'path':'/private/data.json','kind':'FILE','uid':os.geteuid(),'gid':os.getegid(),
                   'mode':0o600,'sha256':r.sha(self.raw),'access_acl':'user::rw-\ngroup::---\nother::---\n'}
    def tearDown(self):shutil.rmtree(self.root)
    def test_actual_file_projection_emits_hash_not_private_bytes(self):
        result=self.reader.observe(self.spec)
        self.assertEqual(result,self.spec)
        self.assertNotIn('never emitted',json.dumps(result))
    def test_unknown_byte_or_mode_change_refused(self):
        pathlib.Path(self.root+'/private/data.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'SPEC_DRIFT'):self.reader.observe(self.spec)
    def test_json_projection_uses_only_explicit_fields(self):
        spec=dict(self.spec,kind='JSON_PROJECTION',fields=[['allowed','state']],
                  sha256=d.digest([{'path':['allowed','state'],'value':'READY'}]))
        self.assertEqual(self.reader.observe(spec),spec)
    def test_optional_projection_distinguishes_absent_and_null(self):
        spec=dict(self.spec,kind='JSON_OPTIONAL_PROJECTION',fields=[['future']],
                  sha256=d.digest([{'path':['future'],'found':False,'value':None}]))
        self.assertEqual(self.reader.observe(spec),spec)
        pathlib.Path(self.root+'/private/data.json').write_bytes(b'{"future":null}')
        with self.assertRaisesRegex(ValueError,'SPEC_DRIFT'):self.reader.observe(spec)
    def test_symlink_or_hardlink_refused(self):
        os.link(self.root+'/private/data.json',self.root+'/private/other')
        with self.assertRaisesRegex(ValueError,'FILE_BOUND'):self.reader.observe(self.spec)
    def test_unreviewed_ancestor_access_refused(self):
        os.chmod(self.root+'/private',0o755)
        with self.assertRaisesRegex(ValueError,'ANCESTOR_DRIFT'):self.reader.observe(self.spec)
    def test_actual_absence_and_mask_observations(self):
        value={'path':'/private/missing','kind':'ABSENT'}
        self.assertEqual(self.reader.observe(value),value)
        os.symlink('/dev/null',self.root+'/private/mask')
        value={'path':'/private/mask','kind':'MASK','uid':os.geteuid(),'gid':os.getegid(),'link':'/dev/null'}
        self.assertEqual(self.reader.observe(value),value)
    def test_directory_future_inode_not_required_but_known_anchor_enforced(self):
        spec={'path':'/private','kind':'DIRECTORY','uid':os.geteuid(),'gid':os.getegid(),'mode':0o700,
              'access_acl':'user::rwx\ngroup::---\nother::---\n','default_acl':''}
        self.assertEqual(self.reader.observe(spec),spec)
        spec.update(dev=123,ino=456)
        with self.assertRaisesRegex(ValueError,'SPEC_DRIFT'):self.reader.observe(spec)
    def test_tree_inventory_rejects_smoke_bytecode_or_any_extra_file(self):
        expected={'/private/data.json':r.sha(self.raw)}
        spec={'path':'/private','kind':'TREE_INVENTORY','sha256':d.digest(expected)}
        self.assertEqual(self.reader.observe(spec),spec)
        pathlib.Path(self.root+'/private/unexpected.pyc').write_bytes(b'cache')
        with self.assertRaisesRegex(ValueError,'SPEC_DRIFT'):self.reader.observe(spec)
    def test_retained_symlink_hash_is_measured_without_following(self):
        os.symlink('../private/data.json',self.root+'/private/cert-link')
        spec={'path':'/private/cert-link','kind':'LINK','uid':os.geteuid(),'gid':os.getegid(),
              'sha256':r.sha(b'../private/data.json')}
        self.assertEqual(self.reader.observe(spec),spec)
        os.unlink(self.root+'/private/cert-link');os.symlink('/etc/shadow',self.root+'/private/cert-link')
        with self.assertRaisesRegex(ValueError,'SPEC_DRIFT'):self.reader.observe(spec)
    def test_actual_runtime_journal_requires_real_context_without_pinning_future_raw_hash(self):
        self.reader.authority.context={'context_sha256':'a'*64}
        raw={'context_sha256':'a'*64,'state':'REOPENED','unpredictable_ctime':123}
        pathlib.Path(self.root+'/private/data.json').write_bytes(d.canonical(raw))
        spec=dict(self.spec,kind='JSON_CONTEXT_PROJECTION',fields=[['state']],
                  sha256=d.digest([{'path':['state'],'value':'REOPENED'}]))
        self.assertEqual(self.reader.observe(spec),spec)
        raw['context_sha256']='b'*64;pathlib.Path(self.root+'/private/data.json').write_bytes(d.canonical(raw))
        with self.assertRaisesRegex(ValueError,'JOURNAL_CONTEXT'):self.reader.observe(spec)
    def test_actual_inner_journal_requires_complete_approval_binding(self):
        self.reader.authority.binding={'review_id':7000000001,'approval_body_sha256':'a'*64}
        value={'schema':1,'name':'data.json','transaction_id':d.TX,'binding':self.reader.authority.binding,
               'state':{'stage':'DONE','observed_after':{'ino':987}}}
        pathlib.Path(self.root+'/private/data.json').write_bytes(d.canonical(value))
        spec=dict(self.spec,kind='JSON_BOUND_PROJECTION',fields=[['state','stage']],
                  sha256=d.digest([{'path':['state','stage'],'value':'DONE'}]))
        self.assertEqual(self.reader.observe(spec),spec)
        value['binding']={'review_id':6170703284};pathlib.Path(self.root+'/private/data.json').write_bytes(d.canonical(value))
        with self.assertRaisesRegex(ValueError,'JOURNAL_BINDING'):self.reader.observe(spec)
    def test_sandbox_projection_ignores_only_frozen_stable_fields(self):
        from p2_sandbox_profile import stable
        raw={'agents':{'entries':{}},'meta':{'lastTouchedAt':'first'}}
        pathlib.Path(self.root+'/private/data.json').write_bytes(d.canonical(raw))
        spec=dict(self.spec,kind='SANDBOX_STABLE',sha256=d.digest(stable(d.canonical(raw))))
        with mock.patch.object(r.snap,'PROFILE','/private/data.json'):
            self.assertEqual(self.reader.observe(spec),spec)
            raw['meta']['lastTouchedAt']='second';pathlib.Path(self.root+'/private/data.json').write_bytes(d.canonical(raw))
            self.assertEqual(self.reader.observe(spec),spec)
            raw['agents']['unsafe']=True;pathlib.Path(self.root+'/private/data.json').write_bytes(d.canonical(raw))
            with self.assertRaisesRegex(ValueError,'SPEC_DRIFT'):self.reader.observe(spec)
    def reference(self):
        path=self.root+'/private/elf';raw=b'\x7fELFfixture bytes'
        pathlib.Path(path).write_bytes(raw);os.chmod(path,0o755)
        os.symlink('elf',self.root+'/private/interpreter')
        return {'reference_path':'/private/interpreter',
            'links':[{'path':'/private/interpreter','link':'elf','metadata':r.fs.metadata(os.lstat(self.root+'/private/interpreter'))}],
            'final':{'path':'/private/elf','sha256':r.sha(raw),'format':'ELF',
                     'metadata':dict(r.fs.metadata(os.lstat(path)),kind='FILE',sha256=r.sha(raw))}}
    def test_actual_executable_alias_and_final_identity_are_both_verified(self):
        proof=self.reference();self.assertTrue(self.reader.executable_reference(proof))
        os.unlink(self.root+'/private/interpreter');os.symlink('data.json',self.root+'/private/interpreter')
        with self.assertRaisesRegex(ValueError,'ALIAS_DRIFT'):self.reader.executable_reference(proof)
    def test_same_executable_bytes_with_new_inode_refuse(self):
        proof=self.reference();raw=pathlib.Path(self.root+'/private/elf').read_bytes()
        pathlib.Path(self.root+'/private/new').write_bytes(raw);os.chmod(self.root+'/private/new',0o755)
        os.replace(self.root+'/private/new',self.root+'/private/elf')
        with self.assertRaisesRegex(ValueError,'FINAL_IDENTITY'):self.reader.executable_reference(proof)
    def test_reference_loop_or_detached_final_path_refuses(self):
        proof=self.reference();proof['final']['path']='/private/data.json'
        with self.assertRaisesRegex(ValueError,'CANONICAL_ELF'):self.reader.executable_reference(proof)

    def test_shared_guard_deadline_is_never_extended(self):
        self.reader.guard_deadline=1;self.reader.start()
        self.assertEqual(self.reader.deadline,1)
        with self.assertRaisesRegex(ValueError,'TOTAL_DEADLINE'):self.reader.observe(self.spec)

if __name__=='__main__':unittest.main()
