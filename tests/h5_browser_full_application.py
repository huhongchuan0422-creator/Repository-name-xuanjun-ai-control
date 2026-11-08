"""Complete synthetic existing application through unchanged H5 UI to both internal reviews.
Provider media IDs are explicitly synthetic references; no real WeChat execute.
"""
import threading,queue,http.server,json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from test_community_mini_region_validation import MiniRegionValidation
from scripts.community_h5 import H5,make_handler
ready=queue.Queue()
def host():
 f=MiniRegionValidation();f.setUp();app,record,profile=f.store_draft('广东省深圳市南山区合成路1号');app=f.complete_platform_materials(app)
 h5=H5(f.fx.gateway,f.onboarding,f.merchant)
 server=http.server.HTTPServer(('127.0.0.1',0),make_handler(h5,Path(__file__).resolve().parents[1]/'clients/community-h5/dist'));ready.put(server)
 try:server.serve_forever(.05)
 finally:server.server_close();f.tearDown()
t=threading.Thread(target=host,daemon=True);t.start();server=ready.get(timeout=20)
try:
 with sync_playwright() as p:
  b=p.chromium.launch(headless=True);page=b.new_page(viewport={'width':390,'height':844});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(f'http://localhost:{server.server_port}/h5/#/pages/merchant-join/index?scene=shop1');page.locator('#email').fill('one@example.org');page.locator('#password').fill('FixturePassword123!');page.locator('#login-panel button').click();page.locator('#login-panel').wait_for(state='hidden');page.wait_for_timeout(500)
  def state():return page.evaluate('()=>{const d=getCurrentPages().at(-1).data;return {step:d.step,status:d.status,pending:d.pending,platform:d.platformState,wechat:d.wechatReviewState,read:d.readState}}')
  print('INITIAL',state(),flush=True)
  for i in range(5):
   print('BUTTONS',page.locator('#app button:visible').all_text_contents(),flush=True)
   next=page.get_by_role('button',name='保存草稿并继续下一项',exact=True)
   if next.count() and next.is_visible():next.click();page.wait_for_timeout(500)
   else:
    submit=page.get_by_role('button',name='提交审核',exact=True)
    if submit.count():submit.first.click();page.wait_for_timeout(600)
    else:break
   print('STEP',state(),flush=True)
  print('FINAL_BODY',page.locator('#app').inner_text(),flush=True);result=state();print('FINAL_STATE',json.dumps(result,ensure_ascii=False),flush=True)
  assert not errors,errors
  assert result['platform'] in ['SUBMITTED','IN_REVIEW'] and result['wechat']=='PENDING_INTERNAL_REVIEW',result
  page.reload();page.locator('#login-panel').wait_for(state='hidden');page.wait_for_timeout(500);result=state();assert result['platform'] in ['SUBMITTED','IN_REVIEW'] and result['wechat']=='PENDING_INTERNAL_REVIEW';print('PASS: complete synthetic application UI reaches both internal reviews and reopens same original statuses; NOT actual WeChat application submission')
  b.close()
finally:server.shutdown();t.join(timeout=5)
