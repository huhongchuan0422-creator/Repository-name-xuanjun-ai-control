"""Original store staff discovery, exact delegated permissions, and browser flow."""
import pathlib
import queue
import shutil
import subprocess
import threading
import unittest
import test_community_center_operations as fixture
from scripts.pr122_customer_core import canonical

ROOT=pathlib.Path(__file__).resolve().parents[1]


def staff_call(fx, operation, params, workspace='merchant', web=None):
    return fx.call(fx.body(workspace=workspace,operation='community.'+operation,params=params),web=web)


def prepare_staff(fx):
    result=staff_call(fx,'staff_grant',dict(user_id=fx.fx.uid2,operations=['community.orders_page','community.summary']))
    staff_call(fx,'staff_remove',dict(workspace=result['workspace']))
    c=fx.fx.center
    original_scope=fx.operations.grants['merchant']['scope']
    with c.tx():
        for index in range(55):
            key='staff_'+format(index,'040x')
            value=dict(user_id=fx.fx.uid2,scope=dict(original_scope,store_id='other_store'),
                parent_workspace='other_store',delegated_by=fx.fx.uid1,operations=['community.orders'])
            c.db.execute("INSERT INTO links VALUES('COMMUNITY_STAFF_GRANT',?,?,?,?,1)",
                (key,fx.fx.uid2,'project1',c.encrypt(canonical(value),'community-staff:'+key)))
    return result['workspace']


class WorkbenchStaffContracts(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.ExistingCenterOperations();self.fx.setUp();self.workspace=prepare_staff(self.fx)
    def tearDown(self):self.fx.tearDown()
    def test_sparse_page_filters_store_and_preserves_inactive_permissions(self):
        first=staff_call(self.fx,'staff_list',dict(after_id=''))
        self.assertEqual(first['records'],[]);self.assertTrue(first['has_more'])
        second=staff_call(self.fx,'staff_list',dict(after_id=first['next_cursor']))
        self.assertFalse(second['has_more']);self.assertEqual(len(second['records']),1)
        record=second['records'][0];self.assertEqual(record['workspace'],self.workspace)
        self.assertFalse(record['active']);self.assertEqual(record['operations'],['community.orders_page','community.summary'])
    def test_nonowner_and_revoked_membership_cannot_list_or_remove(self):
        for operation,params in [('staff_list',dict(after_id='')),('staff_remove',dict(workspace=self.workspace))]:
            with self.assertRaises(PermissionError):staff_call(self.fx,operation,params,workspace='staff')
            with self.assertRaises(PermissionError):staff_call(self.fx,operation,params,web=self.fx.other)
        self.fx.fx.center.db.execute("UPDATE members SET role='EDITOR' WHERE user_id=?",(self.fx.fx.uid1,))
        with self.assertRaises(PermissionError):staff_call(self.fx,'staff_list',dict(after_id=''))
        self.fx.fx.center.db.execute("UPDATE members SET role='OWNER' WHERE user_id=?",(self.fx.fx.uid1,))
        self.fx.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.fx.uid1,))
        with self.assertRaises(PermissionError):staff_call(self.fx,'staff_list',dict(after_id=''))
    def test_dom_contract(self):
        node=shutil.which('node')
        if not node:self.skipTest('Node unavailable')
        subprocess.run([node,str(ROOT/'tests/community_workbench_staff_dom.cjs'),str(ROOT/'demos/community-stage/workbench.js'),str(ROOT/'demos/community-stage/workbench.html')],check=True,timeout=30)


class WorkbenchStaffBrowser(unittest.TestCase):
    def test_staff_sparse_page_selection_and_explicit_actions(self):
        from playwright.sync_api import sync_playwright,expect
        from scripts.community_mini_http import serve
        ready=queue.Queue()
        def host():
            fx=server=None
            try:
                fx=fixture.ExistingCenterOperations();fx.setUp();workspace=prepare_staff(fx)
                server=serve(fx.fx.gateway,operations=fx.operations);ready.put((server,fx.web,fx.fx.uid2,workspace));server.serve_forever(poll_interval=.05)
            except BaseException as error:ready.put(error)
            finally:
                if server:server.server_close()
                if fx:fx.tearDown()
        thread=threading.Thread(target=host,daemon=True);thread.start();state=ready.get(timeout=15)
        if isinstance(state,BaseException):raise state
        server,web,uid,workspace=state
        try:
            with sync_playwright() as p:
                executable=next((shutil.which(name) for name in ('google-chrome','google-chrome-stable','chromium','chromium-browser') if shutil.which(name)),None)
                options=dict(headless=True,chromium_sandbox=True)
                if executable:options['executable_path']=executable
                browser=p.chromium.launch(**options)
                try:
                    context=browser.new_context(extra_http_headers={'X-Center-Session':web['token']});page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto('http://127.0.0.1:'+str(server.server_port)+'/merchant/workbench')
                    page.evaluate('csrf=>configureCommunityWorkbench({csrf,workspace:"merchant"})',web['csrf'])
                    page.locator('#staffList').click();expect(page.locator('#staffRecords')).to_contain_text('仍有记录待查');expect(page.locator('#moreStaff')).to_be_visible()
                    page.locator('#moreStaff').click();expect(page.locator('#staffRecords article')).to_have_count(1);expect(page.locator('#staffRecords')).to_contain_text('已撤销')
                    page.locator('#staffRecords button').click();expect(page.locator('#staffUser')).to_have_value(uid);expect(page.locator('#staffWorkspace')).to_have_value(workspace)
                    expect(page.locator('#staffOrderPages')).to_be_checked();expect(page.locator('#staffSummary')).to_be_checked();expect(page.locator('#staffOrders')).not_to_be_checked();expect(page.locator('#staffOrderDetail')).not_to_be_checked()
                    page.locator('#staffGrantForm button').click();expect(page.locator('#staffResult')).to_contain_text('community.orders_page');expect(page.locator('#staffSelected')).to_be_empty();expect(page.locator('#staffRecords')).to_be_empty();expect(page.locator('#staffWorkspace')).to_have_value('')
                    page.locator('#staffList').click();page.locator('#moreStaff').click();expect(page.locator('#staffRecords')).to_contain_text('有效');page.locator('#staffRecords button').click()
                    page.locator('#staffRemove').click();expect(page.locator('#staffResult')).to_contain_text('false');expect(page.locator('#staffSelected')).to_be_empty();expect(page.locator('#staffRecords')).to_be_empty();expect(page.locator('#staffResult')).to_contain_text('重新读取')
                    page.evaluate('csrf=>configureCommunityWorkbench({csrf,workspace:"staff"})',web['csrf']);expect(page.locator('#staffWorkspace')).to_have_value('');expect(page.locator('#staffRecords')).to_be_empty()
                    page.locator('#staffList').click();expect(page.locator('#notice')).to_contain_text('无此权限');expect(page.locator('#staffRecords')).to_be_empty()
                    page.evaluate('configureCommunityWorkbench(null)');expect(page.locator('#moreStaff')).to_be_hidden();expect(page.locator('#staffList')).to_be_disabled();self.assertFalse(errors)
                finally:browser.close()
        finally:server.shutdown();thread.join(timeout=10)


if __name__=='__main__':unittest.main()
