"""Chromium client epoch test with deliberately delayed synthetic transport.

Backend authentication/storage is covered by the real-HTTP admission journeys.
This fixture tests whether a late old response can repopulate a new login view.
"""
import json
import unittest
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
from scripts.community_merchant_onboarding import MerchantOnboarding

class AdmissionClientEpoch(unittest.TestCase):
    @contextmanager
    def page(self,init):
        root=Path(__file__).resolve().parents[1]/'demos'/'community-stage'
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                page=browser.new_page();page.add_init_script(init)
                def serve(route):
                    path=urlsplit(route.request.url).path
                    name={'/merchant/join':'onboarding.html','/merchant/onboarding.js':'onboarding.js','/merchant/onboarding.css':'onboarding.css'}.get(path)
                    if name:
                        route.fulfill(status=200,body=(root/name).read_bytes(),content_type='text/html' if name.endswith('html') else 'text/css' if name.endswith('css') else 'application/javascript')
                    else:route.fulfill(status=404,body='')
                page.route('**/*',serve);page.goto('http://127.0.0.1:19876/merchant/join')
                expect(page.locator('#status')).to_contain_text('请先登录')
                yield page
            finally:browser.close()
    def application(self):
        old={'application':'ma_'+'a'*32,'revision':1,'status':'DRAFT','reviewer_note':None,
             'fields':{'legal_name':'Previous private customer','store_name':'Previous private merchant',
                       'address':'Previous private address','contact':'Previous private contact'},
             'entity_type':'ENTERPRISE','category':'GENERAL','delegated':False,'required_materials':[],
             'materials':{},'opening_state':'NOT_APPROVED','opening_workspaces':[]}
        return old
    def test_late_old_account_response_never_repopulates_new_account_view(self):
        old=self.application()
        init='''const fixtureCatalog=CATALOG,oldApplication=OLD;
          const reply=(result,status=200)=>new Response(JSON.stringify({result,payment_enabled:false}),{status,headers:{'Content-Type':'application/json'}});
          window.fetch=async(url,options)=>{
            const body=JSON.parse(options.body),credential=options.headers['X-CSRF-Token'];
            if(body.operation==='catalog')return reply(fixtureCatalog);
            if(!credential)return reply({},403);
            if(credential==='old-session')return new Promise(resolve=>{window.releaseOld=()=>resolve(reply({applications:[oldApplication],next_cursor:null}));});
            return reply({applications:[],next_cursor:null});
          };'''.replace('CATALOG',json.dumps(MerchantOnboarding.catalog(),ensure_ascii=False)).replace('OLD',json.dumps(old))
        with self.page(init) as page:
            page.evaluate("window.oldRun=window.configureCommunityOnboarding({csrf:'old-session'});true")
            page.wait_for_function('typeof window.releaseOld === "function"')
            page.evaluate("window.configureCommunityOnboarding({csrf:'new-session'})")
            expect(page.locator('#status')).to_contain_text('尚无申请')
            page.evaluate('window.releaseOld();window.oldRun')
            expect(page.locator('#statusFilter')).to_be_enabled()
            self.assertNotIn('Previous private',page.locator('body').text_content())
            expect(page.locator('#detail')).to_be_hidden();expect(page.locator('#legal_name')).to_have_value('')
            self.assertEqual(page.locator('#mine button').count(),0)
    def test_account_switch_during_file_read_does_not_upload_old_private_file(self):
        old=self.application();old['required_materials']=['business_license']
        new=dict(old,application='ma_'+'b'*32,fields=dict(old['fields'],store_name='New account merchant'))
        init='''const fixtureCatalog=CATALOG,oldApplication=OLD,newApplication=NEW;
          const reply=(result,status=200)=>new Response(JSON.stringify({result,payment_enabled:false}),{status,headers:{'Content-Type':'application/json'}});
          window.uploadCalls=[];
          window.fetch=async(url,options)=>{
            const body=JSON.parse(options.body),credential=options.headers['X-CSRF-Token'];
            if(body.operation==='catalog')return reply(fixtureCatalog);
            if(!credential)return reply({},403);
            if(body.operation==='upload'){window.uploadCalls.push({credential,body});return reply(newApplication);}
            return reply({applications:[credential==='old-session'?oldApplication:newApplication],next_cursor:null});
          };
          File.prototype.arrayBuffer=function(){return new Promise(resolve=>{window.releaseFile=()=>resolve(new TextEncoder().encode('%PDF-old private document').buffer);});};
        '''.replace('CATALOG',json.dumps(MerchantOnboarding.catalog(),ensure_ascii=False)).replace('OLD',json.dumps(old)).replace('NEW',json.dumps(new))
        with self.page(init) as page:
            page.evaluate("window.configureCommunityOnboarding({csrf:'old-session'})")
            row=page.locator('[data-kind=business_license]')
            row.locator('input[type=file]').set_input_files({'name':'private.pdf','mimeType':'application/pdf','buffer':b'%PDF-private fixture'})
            row.get_by_role('button',name='上传资料',exact=True).click()
            page.wait_for_function('typeof window.releaseFile === "function"')
            page.evaluate("window.configureCommunityOnboarding({csrf:'new-session'})")
            expect(page.locator('#applicationTitle')).to_have_text('New account merchant')
            page.evaluate('window.releaseFile()')
            # Let the delayed file promise and its UI continuation fully drain.
            page.evaluate('()=>new Promise(resolve=>setTimeout(resolve,0))')
            self.assertEqual(page.evaluate('window.uploadCalls'),[])
            expect(page.locator('#applicationTitle')).to_have_text('New account merchant')

if __name__=='__main__':unittest.main()
