"""Browser upload and manual OCR review against synthetic existing Center/pinned original OCR."""
import threading,queue,http.server,json,io
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright,expect
from test_community_h5_ocr import H5Ocr
from scripts.community_h5 import make_handler
ready=queue.Queue()
def host():
 H5Ocr.setUpClass();fx=H5Ocr();fx.setUp();fx.fx.fx.fx.center.scanner=lambda data:True
 server=http.server.HTTPServer(('127.0.0.1',0),make_handler(fx.h5,Path(__file__).resolve().parents[1]/'clients/community-h5/dist'));ready.put((server,fx))
 try:server.serve_forever(.05)
 finally:server.server_close();fx.tearDown();H5Ocr.tearDownClass()
t=threading.Thread(target=host,daemon=True);t.start();server,fixture=ready.get(timeout=15)
try:
 with sync_playwright() as p:
  b=p.chromium.launch(headless=True);page=b.new_page(viewport={'width':390,'height':844});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('response',lambda r:print('HTTP_ERROR',r.url,r.status,(lambda d:(d.get('operation'),d.get('params',{}).get('operation'),d.get('params',{}).get('action')))(r.request.post_data_json or {}),r.text(),flush=True) if r.status>=400 else None)
  page.goto(f'http://localhost:{server.server_port}/h5/#/pages/merchant-join/index?scene=shop1');page.locator('#email').fill('one@example.org');page.locator('#password').fill('FixturePassword123!');page.locator('#login-panel button').click();page.locator('#login-panel').wait_for(state='hidden')
  upload=page.locator('button.upload-choice[data-kind="business_license"]');expect(upload).to_be_enabled()
  buf=io.BytesIO();Image.new('RGB',(320,180),'white').save(buf,format='PNG')
  with page.expect_file_chooser() as event:upload.click()
  event.value.set_files({'name':'synthetic-license.png','mimeType':'image/png','buffer':buf.getvalue()})
  page.wait_for_timeout(1800);print('AFTER_UPLOAD',page.locator('body').inner_text(),flush=True)
  confirm=page.get_by_role('button',name='确认已核对',exact=True);expect(confirm).to_be_visible(timeout=20000)
  print('UPLOADED',page.locator('#app').inner_text()[:1600])
  confirm.click();save=page.get_by_role('button',name='保存已核对资料（仅填空白，不覆盖已有内容）',exact=True);expect(save).to_be_visible(timeout=15000);save.click();page.wait_for_timeout(600)
  print('SAVED',page.locator('#app').inner_text()[:1600]);assert not errors,errors
  # Read-only observation of original page state, never used to bypass controls.
  state=page.evaluate('()=>({profile:getCurrentPages().at(-1).profile,status:getCurrentPages().at(-1).data.status,ocrStatus:getCurrentPages().at(-1).data.ocrStatus})');print(json.dumps(state,ensure_ascii=False));assert state['profile']['subject_info']['business_license_info']['merchant_name']=='SYNTHETIC ONLY'
  before=fixture.inferences;page.reload();expect(page.get_by_role('button',name='确认已核对',exact=True)).to_be_visible(timeout=15000)
  page.get_by_role('button',name='确认已核对',exact=True).click();expect(page.get_by_role('button',name='保存已核对资料（仅填空白，不覆盖已有内容）',exact=True)).to_be_visible(timeout=15000)
  page.get_by_role('button',name='保存已核对资料（仅填空白，不覆盖已有内容）',exact=True).click();page.wait_for_timeout(500)
  assert fixture.inferences==before,'Recovery unexpectedly reran inference'
  assert page.evaluate("()=>getCurrentPages().at(-1).profile.subject_info.business_license_info.merchant_name")=='SYNTHETIC ONLY'
  assert not errors,errors;print('PASS: real file chooser upload, OCR submit, manual confirm/writeback, browser reload recovery, confirm/reapply without reinference')
  b.close()
finally:server.shutdown();t.join(timeout=5)
