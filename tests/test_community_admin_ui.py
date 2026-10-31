"""Real Chromium UI behavior with explicitly synthetic HTTP responses.
Not original backend/device/production identity acceptance.
"""
import json, unittest, os
from pathlib import Path
from playwright.sync_api import sync_playwright
JS=Path(__file__).parents[1]/'demos/community-stage/web-session.js'
HTML='''<!doctype html><html><body><section id="community-session"><form><input name="email"><input name="password" type="password"><button>登录</button></form><p role="status"></p><select></select><button data-logout>退出</button></section><script src="/web-session.js"></script></body></html>'''
class UI(unittest.TestCase):
 def test_root_pagination_create_and_clear_password(self):
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True,**({'executable_path':os.environ['COMMUNITY_UI_CHROMIUM_PATH']} if os.environ.get('COMMUNITY_UI_CHROMIUM_PATH') else {}))
   try:
    page=browser.new_page();requests=[];errors=[];page.on('pageerror',lambda e:errors.append(type(e).__name__))
    page.add_init_script("sessionStorage.setItem('community-original-csrf','fixture-csrf')")
    def route(r):
     url=r.request.url
     if url.endswith('/web-session.js'):return r.fulfill(content_type='text/javascript',body=JS.read_text())
     if r.request.method=='GET':return r.fulfill(content_type='text/html',body=HTML)
     body=r.request.post_data_json
     if url.endswith('/session/check'):result=dict(user_id='root',workspaces=[],reviewer=False,community_admin=dict(kind='ROOT'))
     else:
      operation=body['operation'];params=body['params']
      if operation=='catalog':result=dict(capabilities=['/community/operations#read'],workspace_scopes=['/community/operations#store1'])
      elif operation=='list':
       if params['after_uid']=='':result=dict(records=[dict(uid='fixture_root',kind='ROOT',active=True,revision=1,capabilities=[],workspace_scopes=[])],has_more=True,next_cursor='fixture_root')
       else:result=dict(records=[dict(uid='fixture_child_51',kind='DELEGATE',active=True,revision=1,capabilities=['/community/operations#read'],workspace_scopes=['/community/operations#store1'])],has_more=False,next_cursor=None)
      elif operation=='create':
       # Assert internally; never print/store a secret value in output.
       self.assertEqual(params['password'],'synthetic-password-123');requests.append(dict(operation=operation,password_present=bool(params['password'])));result=dict(uid='new_fixture')
      else:result={}
     return r.fulfill(content_type='application/json',body=json.dumps(dict(result=result)))
    page.route('**/*',route)
    page.goto('https://fixture.invalid/community-preview/merchant/workbench')
    page.get_by_role('button',name='刷新管理员与权限').click()
    page.get_by_role('button',name='加载下一页管理员').click()
    page.get_by_text('fixture_child_51 · DELEGATE').wait_for()
    page.get_by_label('新管理员登录邮箱').fill('child@test.invalid');page.get_by_label('新管理员初始密码').fill('synthetic-password-123')
    form=page.locator('form').nth(1)
    for checkbox in form.locator('input[type=checkbox]').all():checkbox.check()
    page.get_by_role('button',name='创建受限管理员').click()
    page.wait_for_function("document.querySelector('[aria-label=新管理员初始密码]').value === ''")
    self.assertEqual(requests,[dict(operation='create',password_present=True)]);self.assertEqual(errors,[])
   finally:browser.close()
if __name__=='__main__':unittest.main()
