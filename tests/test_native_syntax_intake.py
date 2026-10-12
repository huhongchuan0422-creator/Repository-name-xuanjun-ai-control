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

    def read(self,url,token):
        sha=hashlib.sha1(b'blob '+str(len(self.raw)).encode()+b'\0'+self.raw).hexdigest()
        if '/compare/' in url:return dict(status='ahead',base_commit={'sha':'a'*40},merge_base_commit={'sha':'a'*40},commits=[{'sha':'b'*40}],files=[dict(filename='src/a.py',status='added',sha=sha)])
        if '/git/trees/' in url:return dict(truncated=self.truncated,tree=[dict(path='src/a.py',type='blob',mode=self.mode,sha=sha,size=len(self.raw))])
        return dict(encoding='base64',content=base64.b64encode(self.raw).decode())

    def test_exact_code_pass_and_broken_quotes_hold(self):
        self.assertEqual(syntax_receipt(self.value,'owner/control','token',self.read)['state'],'PASS_SYNTAX_NOT_ADMITTED')
        self.raw=b'x="oops\n'
        self.assertEqual(syntax_receipt(self.value,'owner/control','token',self.read)['state'],'HOLD_SYNTAX_GATE')

    def test_symlink_and_truncated_tree_rejected(self):
        self.mode='120000'
        with self.assertRaises(ValueError):syntax_receipt(self.value,'owner/control','token',self.read)
        self.mode='100644';self.truncated=True
        with self.assertRaises(ValueError):syntax_receipt(self.value,'owner/control','token',self.read)

    def test_external_repository_never_fetched(self):
        self.value['target_repository']='other/repo'
        def fail(*args):raise AssertionError('must not fetch')
        self.assertEqual(syntax_receipt(self.value,'owner/control','token',fail)['state'],'HOLD_TARGET_REPOSITORY_ADMISSION_REQUIRED')

    def test_payload_hash_change(self):
        first=syntax_receipt(self.value,'owner/control','token',self.read)['receipt_sha256']
        self.raw=b'x=2\n'
        self.assertNotEqual(first,syntax_receipt(self.value,'owner/control','token',self.read)['receipt_sha256'])

    def test_wrong_head_and_protected_rename(self):
        for mode in ('head','rename'):
            def read(url,token):
                value=self.read(url,token)
                if '/compare/' in url:
                    if mode=='head':value['commits'][-1]['sha']='f'*40
                    else:value['files'][0].update(status='renamed',previous_filename='secrets.json')
                return value
            with self.assertRaises(ValueError):syntax_receipt(self.value,'owner/control','token',read)


if __name__=='__main__':unittest.main()
