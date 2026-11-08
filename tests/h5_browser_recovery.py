"""Local synthetic existing-account browser acceptance; no production action."""
import threading,queue,http.server,json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from test_community_mini_merchant import SameMiniMerchant
from scripts.community_h5 import H5,make_handler
from scripts.community_commerce import Commerce
ready=queue.Queue()
def host():
 f=SameMiniMerchant();f.setUp();f.fx.gateway.commerce=Commerce(f.operations,f.fx.identity)
 h=H5(f.fx.gateway,f.onboarding,f.service)
 server=http.server.HTTPServer(('127.0.0.1',0),make_handler(h,Path(__file__).resolve().parents[1]/'clients/community-h5/dist'))
 ready.put(server)
 try:server.serve_forever(.05)
 finally:server.server_close();f.tearDown()
t=threading.Thread(target=host,daemon=True);t.start();server=ready.get(timeout=10)
try:
 with sync_playwright() as p:
  b=p.chromium.launch(headless=True);page=b.new_page(viewport={'width':390,'height':844});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(f'http://localhost:{server.server_port}/h5/#/pages/home/index?scene=shop1')
  page.locator('#email').fill('one@example.org');page.locator('#password').fill('FixturePassword123!');page.locator('#login-panel button').click()
  page.locator('#login-panel').wait_for(state='hidden')
  report=[]
  for name in ['home','profile','checkout','merchant','merchant-join']:
   page.evaluate("name=>{location.hash='/pages/'+name+'/index?scene=shop1'}",name);page.wait_for_timeout(500)
   report.append({'page':name,'text':page.locator('#app').inner_text()[:180],'js_errors':errors[:]})
  print(json.dumps(report,ensure_ascii=False,indent=2));assert not errors,errors
  assert page.evaluate('H5_SESSION.isAuthenticated()'),page.locator('#h5-message').inner_text()
  draft=page.locator('#app input').first;draft.fill('SYNTHETIC-DRAFT')
  assert draft.input_value()=='SYNTHETIC-DRAFT'
  print('DRAFT_STATE',page.evaluate('()=>getCurrentPages().at(-1).profile'))
  page.evaluate("()=>{location.hash='/pages/profile/index?scene=shop1'}");page.wait_for_timeout(150)
  page.go_back();page.wait_for_timeout(150)
  print('BACK_STATE',page.url,page.locator('#app input').first.input_value(),page.evaluate('()=>getCurrentPages().at(-1).profile'))
  assert page.locator('#app input').first.input_value()=='SYNTHETIC-DRAFT','Draft was lost across navigation'
  print('PASS: real login, five source pages, native input, history back draft restoration')
  page.locator('#h5-privacy').click();page.get_by_role('dialog').wait_for(state='visible');assert 'DRAFT_NOT_FOR_SIGNATURE' in page.get_by_role('dialog').inner_text();page.get_by_role('button',name='关闭',exact=True).click();page.get_by_role('dialog').wait_for(state='detached');print('PASS: original privacy draft visible, clearly not effective, no consent submission')
  page.screenshot(path=str(Path(__file__).resolve().parents[2]/'h5-merchant-join.png'),full_page=True)
  page.locator('#h5-logout').click();page.locator('#login-panel').wait_for(state='visible');assert page.locator('#app').inner_text()==''
  page.locator('#email').fill('two@example.org');page.locator('#password').fill('FixturePassword123!');page.locator('#login-panel button').click();page.locator('#login-panel').wait_for(state='hidden');page.wait_for_timeout(250);assert page.locator('#app input').first.input_value()=='';assert 'SYNTHETIC-DRAFT' not in page.locator('#app').inner_text();print('PASS: real logout and second account does not inherit draft or cached page')
  field=page.locator('#app input').first;field.focus();page.evaluate("()=>{const p=getCurrentPages().at(-1);p.setData({'materialGroups[0].fields[0].value':'PROGRAMMATIC-CORRECTION'})}");assert field.input_value()=='';page.locator('#h5-privacy').focus();expect(field).to_have_value('PROGRAMMATIC-CORRECTION');print('PASS: focused input defers programmatic correction until blur')
  b.close()
finally:server.shutdown();t.join(timeout=3)
