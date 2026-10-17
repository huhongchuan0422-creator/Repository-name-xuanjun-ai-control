"""Platform filters and lifecycle reuse original encrypted directory and ACL."""
import subprocess
import unittest
from pathlib import Path
import test_community_directory_pagination as fixtures

class DirectoryFilter(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.CommunityDirectoryPagination();self.f.setUp()
    def tearDown(self):self.f.doCleanups()
    def call(self,operation,params,reviewer=True):
        return self.f.call(params,workspace='reviewer' if reviewer else 'community',web=self.f.other if reviewer else self.f.web,operation=operation)
    def test_original_approved_pause_resume_uses_latest_revision(self):
        cid=next(iter(self.f.owned));g=self.f.grants['community'];old=self.f.directory.read(g,cid)
        with self.f.c.tx():self.f.directory.write(g,dict(old,state='APPROVED'),old)
        found=[];cursor=''
        while True:
            page=self.call('list',dict(after_id=cursor,status='APPROVED'));found.extend(page['records'])
            if not page['has_more']:break
            cursor=page['next_cursor']
        self.assertEqual([r['id'] for r in found],[cid])
        current=self.call('status',dict(community_id=cid))
        paused=self.call('review',dict(community_id=cid,expected_version=current['version'],decision='PAUSED',opinion='Synthetic pause'))
        self.assertEqual(paused['state'],'PAUSED')
        with self.assertRaises(ValueError):self.call('review',dict(community_id=cid,expected_version=current['version'],decision='APPROVED',opinion='stale'))
        current=self.call('status',dict(community_id=cid))
        restored=self.call('review',dict(community_id=cid,expected_version=current['version'],decision='APPROVED',opinion='Synthetic resume'))
        self.assertEqual(restored['state'],'APPROVED')
    def test_all_filters_original_enumeration_and_nonplatform_denial(self):
        for status in ('ALL','DRAFT','PENDING','CORRECTION','REJECTED','APPROVED','PAUSED'):
            result=self.call('list',dict(after_id='',status=status))
            self.assertLessEqual(len(result['records']),50)
            if status!='ALL':self.assertTrue(all(r['state']==status for r in result['records']))
            with self.assertRaises(PermissionError):self.call('list',dict(after_id='',status=status),False)
        with self.assertRaises(ValueError):self.call('list',dict(after_id='',status='NEW_RULE'))
    def test_revoked_reviewer_cannot_continue_page(self):
        first=self.call('list',dict(after_id='',status='ALL'))
        self.f.c.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.f.fx.uid2,));self.f.c.db.commit()
        with self.assertRaises(PermissionError):self.call('list',dict(after_id=first['next_cursor'],status='ALL'))

class DirectoryFilterDOM(unittest.TestCase):
    def test_javascript_contracts(self):
        p=subprocess.run(['node','--test',str(Path(__file__).with_suffix('.mjs'))],capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)

if __name__=='__main__':unittest.main()
