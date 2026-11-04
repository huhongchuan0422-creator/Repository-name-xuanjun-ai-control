"""Original showcase namespace, disposable local metadata; no production writes."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import pr122_showcase_display as display

RECORD={'id':'shiliu-media','title':'拾陆传媒 · 内容运营工作台','summary':'示例数据原型',
        'preview_url':'https://xuanjun-video-studio-20261104.alive-gnat-7824.chatgpt.site',
        'content_kind':'SAMPLE_DATA_PROTOTYPE','public_consent_ref':'fixture-owner-consent',
        'source_project_id':None,'source_ref':'fixture-site-project','listed':True,'preview_access':'UNVERIFIED'}
class DisplayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.base=self.root/'delivery'
        self.patcher=patch.object(display,'BASE',self.base);self.patcher.start();self.addCleanup(self.patcher.stop)
        # Root is the existing controlled operator model. Only sandbox ownership
        # is adapted when these same tests run as an unprivileged Hosted user.
        real=display.trusted;sandbox_uid=os.geteuid()
        if sandbox_uid!=0:
            def trusted(path,**kwargs):
                info=path.lstat()
                if path.is_relative_to(self.root):
                    self.assertFalse(path.is_symlink());self.assertEqual(info.st_uid,sandbox_uid);self.assertFalse(info.st_mode&0o022)
                    if not kwargs.get('directory'):self.assertEqual(info.st_nlink,1)
                    return info
                return real(path,**kwargs)
            p=patch.object(display,'trusted',side_effect=trusted);p.start();self.addCleanup(p.stop)
        p=patch.object(display.os,'geteuid',return_value=0);p.start();self.addCleanup(p.stop)
    def test_read_absent_has_no_writes(self):
        self.assertEqual(display.manage('read')['projection_state'],'ABSENT');self.assertFalse(self.base.exists())
    def test_put_update_unlist_and_restart_keep_history_without_site_build(self):
        sentinel=self.root/'website';sentinel.write_text('confirmed UI')
        display.manage('put',0,RECORD)
        updated={**RECORD,'preview_url':'https://example.org/new-preview'}
        display.manage('put',1,updated);display.manage('unlist',2,identifier=RECORD['id'])
        state=display.manage('read');self.assertEqual(state['revision'],3);self.assertEqual(len(state['history']),3)
        self.assertEqual(json.loads((self.base/'catalog.json').read_bytes())['projects'],[])
        self.assertEqual(state['history'][0]['record']['preview_url'],RECORD['preview_url'])
        self.assertEqual(sentinel.read_text(),'confirmed UI')
    def test_wrong_revision_preserves_all_bytes(self):
        display.manage('put',0,RECORD);before={p.name:p.read_bytes() for p in self.base.iterdir()}
        with self.assertRaisesRegex(ValueError,'DISPLAY_REVISION_CONFLICT'):display.manage('unlist',0,identifier=RECORD['id'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.base.iterdir()})
    def test_non_operator_cannot_create_or_write(self):
        with patch.object(display.os,'geteuid',return_value=1000),self.assertRaisesRegex(ValueError,'PROTECTED_OPERATOR'):display.manage('put',0,RECORD)
        self.assertFalse(self.base.exists())
    def test_manager_cannot_write_task_phase_or_acceptance(self):
        for key in ('phase','delivery','tenant','rbac','accepted'):
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'DISPLAY_FIELDS'):display.validate({**RECORD,key:True})
    def test_unsafe_links_and_missing_public_consent_rejected(self):
        for url in ('javascript:alert(1)','//example.com','https://user:password@example.com','http://example.com','https://example.com/\n'):
            with self.subTest(url=url),self.assertRaises(ValueError):display.validate({**RECORD,'preview_url':url})
        with self.assertRaises(ValueError):display.validate({**RECORD,'public_consent_ref':''})
    def test_interrupted_projection_retains_commit_and_sync_is_not_repeated_mutation(self):
        atomic=display.atomic
        def fail(path,data,mode):
            if path.name=='catalog.json':raise OSError('fixture disk interruption')
            return atomic(path,data,mode)
        with patch.object(display,'atomic',side_effect=fail),self.assertRaisesRegex(RuntimeError,'PROJECTION_PENDING'):display.manage('put',0,RECORD)
        self.assertEqual(display.manage('read')['revision'],1)
        display.manage('sync',1);state=display.manage('read')
        self.assertEqual(state['projection_state'],'CURRENT');self.assertEqual(len(state['history']),1)
    def test_unknown_catalog_and_symlinks_not_overwritten(self):
        self.base.mkdir();path=self.base/'catalog.json';path.write_text('unknown draft');path.chmod(0o644)
        with self.assertRaises((RuntimeError,ValueError)):display.manage('put',0,RECORD)
        self.assertEqual(path.read_text(),'unknown draft');self.assertFalse((self.base/'state.json').exists())
        path.unlink();(self.base/'state.json').symlink_to(self.root/'missing')
        with self.assertRaises((ValueError,FileNotFoundError)):display.manage('put',0,RECORD)
    def test_history_not_exposed_in_public_catalog(self):
        display.manage('put',0,RECORD);catalog=json.loads((self.base/'catalog.json').read_bytes())
        self.assertNotIn('history',catalog);self.assertNotIn('operator_uid',str(catalog))
        self.assertEqual(catalog['projects'][0]['source_project_id'],None)

    def test_sync_does_not_overwrite_unknown_changed_projection(self):
        display.manage('put',0,RECORD)
        path=self.base/'catalog.json';path.write_text('unknown successor draft')
        with self.assertRaisesRegex(ValueError,'UNKNOWN_EXISTING_CATALOG'):display.manage('sync',1)
        self.assertEqual(path.read_text(),'unknown successor draft')
