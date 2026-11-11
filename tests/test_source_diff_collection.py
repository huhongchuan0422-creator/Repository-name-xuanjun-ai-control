import copy
import os
import subprocess
import tempfile
import unittest
from scripts.source_diff_collection import collect_source_diff
from five_support import load_dependencies

A, B = 'a'*40, 'b'*40

def raw(status=b'M', path=b'scripts/a.py', previous=None, old=b'100644', new=b'100644'):
    oldsha = b'0'*40 if old == b'000000' else b'c'*40
    newsha = b'0'*40 if new == b'000000' else b'd'*40
    return b':'+old+b' '+new+b' '+oldsha+b' '+newsha+b' '+status+b'\0'+(previous+b'\0' if previous else b'')+path+b'\0'

def receipt(data):
    return dict(base_sha=A,head_sha=B,complete=True,raw=data)

class DiffCollectionTests(unittest.TestCase):
    def test_all_supported_statuses(self):
        data=raw(b'A',b'a',old=b'000000')+raw(b'D',b'b',new=b'000000')+raw(b'M',b'c')+raw(b'R100',b'e',b'd')
        result=collect_source_diff(receipt(data),A,B)
        self.assertEqual([x['status'] for x in result['changes']],['added','removed','modified','renamed'])
        self.assertEqual(result['changes'][-1]['previous_path'],'d')
        self.assertFalse(result['execution_granted'])
    def test_truncated(self):
        for value in (b'',raw()[:-1],raw().split(b'\0')[0]+b'\0',raw(b'R100')):
            with self.assertRaises(ValueError):collect_source_diff(receipt(value),A,B)
    def test_special_modes(self):
        for mode in (b'120000',b'160000',b'040000'):
            with self.assertRaisesRegex(ValueError,'SPECIAL_MODE'):collect_source_diff(receipt(raw(new=mode)),A,B)
    def test_unsafe_paths(self):
        for name in (b'../a',b'/a',b'a//b',b'.git/config',b'a b',b'a\nb',b'a\\b',b'\xff'):
            with self.assertRaisesRegex(ValueError,'PATH'):collect_source_diff(receipt(raw(path=name)),A,B)
    def test_status_modes_and_zero_blob(self):
        for data in (raw(b'A'),raw(b'D'),raw(old=b'000000'),raw().replace(b'c'*40,b'0'*40)):
            with self.assertRaises(ValueError):collect_source_diff(receipt(data),A,B)
    def test_unsupported_copy_unmerged_typechange(self):
        for status in (b'C100',b'U',b'T',b'R101',b'R'):
            with self.assertRaises(ValueError):collect_source_diff(receipt(raw(status)),A,B)
    def test_duplicate(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):collect_source_diff(receipt(raw()+raw()),A,B)
    def test_count_bound(self):
        data=b''.join(raw(path=str(i).encode()) for i in range(257))
        with self.assertRaisesRegex(ValueError,'TOO_MANY'):collect_source_diff(receipt(data),A,B)
    def test_bytes_bound(self):
        with self.assertRaisesRegex(ValueError,'BOUNDED'):collect_source_diff(receipt(b'x'*1048576+b'\0'),A,B)
    def test_unbound_incomplete(self):
        for key,value in (('base_sha',B),('head_sha',A),('complete',False)):
            item=receipt(raw());item[key]=value
            with self.assertRaises(ValueError):collect_source_diff(item,A,B)
    def test_actual_git_rename_and_existing_ownership_policy(self):
        checker=load_dependencies()['source_path_ownership'].check_source_paths
        with tempfile.TemporaryDirectory() as root:
            def git(*args):
                env = {k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
                env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null')
                return subprocess.check_output(['git','-c','core.hooksPath=/dev/null','-c','commit.gpgsign=false','-c','diff.renames=true','-c','user.name=Fixture','-c','user.email=fixture@example.invalid']+list(args),cwd=root,env=env)
            git('init','-q');os.mkdir(os.path.join(root,'owned'))
            with open(os.path.join(root,'owned','a.py'),'w') as f:f.write('x = 1\n')
            git('add','.');git('commit','-qm','base');base=git('rev-parse','HEAD').decode().strip()
            git('mv','owned/a.py','owned/b.py');git('commit','-qm','rename');head=git('rev-parse','HEAD').decode().strip()
            data=git('diff','--raw','-z','--no-abbrev','--no-ext-diff','--no-textconv',base,head,'--')
            result=collect_source_diff(dict(base_sha=base,head_sha=head,complete=True,raw=data),base,head)
            self.assertEqual(result['changes'],[dict(status='renamed',path='owned/b.py',previous_path='owned/a.py')])
            snapshot=dict(repository='fixture/repo',revision=1,observed_at=100,complete=True,claims=[dict(claim_id='c1',task_id='T1',writer='DOTS',paths=['owned/'])])
            checked=checker(snapshot,result['changes'],'fixture/repo','T1','DOTS',1,100,base,head)
            self.assertNotEqual(checked['state'],'HOLD')
            snapshot['claims'][0]['paths']=['owned/b.py']
            self.assertEqual(checker(snapshot,result['changes'],'fixture/repo','T1','DOTS',1,100,base,head)['state'],'HOLD')
