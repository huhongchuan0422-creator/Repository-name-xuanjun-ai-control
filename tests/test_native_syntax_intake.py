import base64
import hashlib
import pathlib
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).parents[1]/'scripts'))
from native_syntax_intake import syntax_receipt


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.value=dict(event='CODE_READY',target_repository='owner/control',
            target_base_sha='a'*40,code_commit='b'*40,task_id='same',
            spec_sha256='c'*64,checkpoint_sha256='d'*64,entry='DOTS')
        self.raw=b'x=1\n';self.mode='100644';self.truncated=False
        self.status='added';self.previous=None;self.reported_head='b'*40
        runtime=lambda path,version,sha:dict(path=path,version=version,sha256=sha*64)
        self.checker=dict(gate_commit='e'*40,
            python=runtime('/usr/bin/python3','Python 3.11.0','4'),
            bash=runtime('/usr/bin/bash','GNU bash 5.2','5'),
            node=runtime('/usr/bin/node','v22.23.3','6'),
            intake_sha256='f'*64,gate_sha256='1'*64,typescript_version='5.7.3',
            typescript_sha256='2'*64)

    def read(self,url,token):
        sha=hashlib.sha1(b'blob '+str(len(self.raw)).encode()+b'\0'+self.raw).hexdigest()
        if '/compare/' in url:
            item=dict(filename='src/a.py',status=self.status,sha=sha)
            if self.previous is not None:item['previous_filename']=self.previous
            return dict(status='ahead',base_commit={'sha':'a'*40},merge_base_commit={'sha':'a'*40},
                        head_commit={'sha':self.reported_head},files=[item])
        if '/git/trees/' in url:return dict(truncated=self.truncated,tree=[dict(path='src/a.py',type='blob',mode=self.mode,sha=sha,size=len(self.raw))])
        return dict(encoding='base64',content=base64.b64encode(self.raw).decode())

    def receipt(self):
        return syntax_receipt(self.value,'owner/control','token',self.read,checker_identity=self.checker)

    def test_exact_code_pass_and_broken_quotes_hold(self):
        self.assertEqual(self.receipt()['state'],'PASS_SYNTAX_NOT_ADMITTED')
        self.raw=b'x="oops\n';self.assertEqual(self.receipt()['state'],'HOLD_SYNTAX_GATE')

    def test_head_commit_mismatch_rejected(self):
        self.reported_head='9'*40
        with self.assertRaises(ValueError):self.receipt()

    def test_rename_source_is_validated(self):
        self.status='renamed';self.previous='../secret.py'
        with self.assertRaises(ValueError):self.receipt()
        self.previous='src/old.py';self.assertEqual(self.receipt()['state'],'PASS_SYNTAX_NOT_ADMITTED')

    def test_symlink_and_truncated_tree_rejected(self):
        self.mode='120000'
        with self.assertRaises(ValueError):self.receipt()
        self.mode='100644';self.truncated=True
        with self.assertRaises(ValueError):self.receipt()

    def test_external_repository_never_fetched(self):
        self.value['target_repository']='other/repo'
        def fail(*args):raise AssertionError('must not fetch')
        self.assertEqual(syntax_receipt(self.value,'owner/control','token',fail,
            checker_identity=self.checker)['state'],'HOLD_TARGET_REPOSITORY_ADMISSION_REQUIRED')

    def test_payload_and_checker_hash_change_receipt(self):
        first=self.receipt()['receipt_sha256'];self.raw=b'x=2\n'
        second=self.receipt()['receipt_sha256'];self.assertNotEqual(first,second)
        self.raw=b'x=1\n';self.checker['gate_commit']='3'*40
        self.assertNotEqual(first,self.receipt()['receipt_sha256'])

    def test_runtime_identity_is_strict_and_bound(self):
        first=self.receipt()['receipt_sha256']
        self.checker['node']=dict(self.checker['node'],version='v22.24.0')
        self.assertNotEqual(first,self.receipt()['receipt_sha256'])
        self.checker['node']=dict(self.checker['node'],sha256='not-a-hash')
        with self.assertRaises(ValueError):self.receipt()


if __name__=='__main__':unittest.main()
