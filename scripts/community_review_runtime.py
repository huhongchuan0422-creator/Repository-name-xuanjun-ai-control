"""Loopback-only isolated review using original Center/services and synthetic accounts.

Never imports protected host config, accepts a production data root, deploys,
uses real credentials, or enables provider submissions/payments. This is a
review runner, not an alternative production identity or business implementation.
"""
import argparse,json,sys,time,urllib.parse
from pathlib import Path
from http.server import HTTPServer
ROOT=Path(__file__).resolve().parents[1]

class ReviewRuntime:
    def __init__(self,port=0):
        sys.path.insert(0,str(ROOT))
        sys.path.insert(0,str(ROOT/'tests'))
        from test_community_mini_center_identity import ExistingCenterComposition
        from scripts.community_center_operations import CenterOperations
        from scripts.community_merchant_onboarding import MerchantOnboarding
        from scripts.community_wechat_applyment import WechatApplyment
        from scripts.community_wechat_sp_readonly import PartnerOrderReader
        from scripts.community_center_communities import CenterCommunities
        from scripts.community_commerce import Commerce
        from scripts.community_mini_http import make_handler
        from scripts.community_merchant_store import put_item
        self.fixture=fx=ExistingCenterComposition();fx.setUp()
        try:
            c=fx.center;c.scanner=lambda raw:True  # Explicit isolated test scanner, never a host default.
            consumer,consumer_token=fx.account('review-consumer@example.org')
            community,community_token=fx.account('review-community@example.org')
            for uid in (consumer,community):c.db.execute("INSERT INTO members VALUES('project1',?,'EDITOR',1)",(uid,))
            fx.identity.bind_existing_account(consumer_token,fx.identity.appid,'reviewconsumer')
            c.db.execute("UPDATE members SET role='REVIEWER' WHERE user_id=?",(fx.uid2,))
            self.onboarding=MerchantOnboarding(c,{fx.uid2:'project1'})
            # A synthetic reader exists solely for private draft storage. Every
            # external action is denied; no network credentials are constructed.
            reader=PartnerOrderReader.__new__(PartnerOrderReader)
            reader._mchid='1900000000'
            def deny_provider(*args,**kwargs):raise PermissionError('ISOLATED_PROVIDER_IO_DISABLED')
            reader._fetch=deny_provider
            self.onboarding.wechat_applyment=WechatApplyment(self.onboarding,reader,submission_enabled=False)
            self.operations=CenterOperations(c,fx.stage.api,{'merchant':dict(user_id=fx.uid1,project='project1',project_roles=['OWNER'],principal=fx.stage.merchant)},onboarding=self.onboarding)
            self.onboarding.operations=self.operations
            self.communities=CenterCommunities(c,{
                'community':dict(user_id=community,project='project1',tenant='tenant1',role='COMMUNITY_ADMIN'),
                'platform':dict(user_id=fx.uid2,project='project1',tenant='tenant1',role='PLATFORM_REVIEWER')})
            self.commerce=Commerce(self.operations,fx.identity);self.communities.commerce=self.commerce
            fx.gateway.commerce=self.commerce
            # This override is confined to this temporary fixture composition.
            def exchange(code):
                if code.startswith('review-merchant-'):openid='openid1'
                elif code.startswith('review-consumer-'):openid='reviewconsumer'
                else:raise PermissionError('ISOLATED_REVIEW_CODE_REQUIRED')
                return dict(appid=fx.identity.appid,openid=openid)
            fx.provider.exchange=exchange
            self.accounts={'consumer':'review-consumer@example.org','merchant':'one@example.org','community':'review-community@example.org','platform':'two@example.org'}
            owner=self
            Base=make_handler(fx.gateway,onboarding=self.onboarding,operations=self.operations,communities=self.communities,commerce=self.commerce)
            class Handler(Base):
                def _local(self):
                    expected='127.0.0.1:'+str(self.server.server_port)
                    return self.client_address[0]=='127.0.0.1' and self.headers.get_all('Host')==[expected] and self.headers.get_all('Origin',[]) in ([],['http://'+expected])
                def _asset(self,raw,mime):
                    self.send_response(200)
                    for key,value in [('Content-Type',mime),('Content-Length',str(len(raw))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-eval' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'self'; object-src 'none'; base-uri 'none'")]:self.send_header(key,value)
                    self.end_headers();self.wfile.write(raw)
                def do_GET(self):
                    if not self._local():return self.answer(403,{'error':'LOOPBACK_REVIEW_ONLY'})
                    parsed=urllib.parse.urlsplit(self.path)
                    if parsed.path=='/review/sources':
                        names={'app.wxss','session.js','client.js','payment.js','customer-auth.js','merchant-form.js','merchant-fields.json'}
                        names.update(p.relative_to(ROOT/'clients/community-mini').as_posix() for p in (ROOT/'clients/community-mini/pages').glob('*/index.*') if p.suffix in ('.js','.wxml','.wxss'))
                        return self.answer(200,{'sources':{n:(ROOT/'clients/community-mini'/n).read_text() for n in sorted(names)},'isolated':True})
                    assets={'/':('review-runtime.html','text/html; charset=utf-8'),'/review/native.js':('review-native.js','application/javascript; charset=utf-8')}
                    if parsed.path in assets:
                        name,mime=assets[parsed.path];return self._asset((ROOT/'demos/community-stage'/name).read_bytes(),mime)
                    if parsed.path in ('/community/portal','/merchant/review','/merchant/workbench'):
                        role=urllib.parse.parse_qs(parsed.query).get('role',['platform'])[0]
                        if role not in ('community','platform','merchant'):return self.answer(400,{'error':'EXACT_REVIEW_ROLE_REQUIRED'})
                        filename='communities.html' if parsed.path=='/community/portal' else 'workbench.html' if parsed.path=='/merchant/workbench' else 'onboarding.html'
                        html=(ROOT/'demos/community-stage'/filename).read_text()
                        script=owner.frame_script(role,filename)
                        html=html.replace('</body>','<script>'+script+'</script></body>')
                        return self._asset(html.encode(),'text/html; charset=utf-8')
                    # Only original assets and APIs are forwarded. The original
                    # handler retains its own fixed allowlist and authorization.
                    return super().do_GET()
                def do_POST(self):
                    if not self._local():return self.answer(403,{'error':'LOOPBACK_REVIEW_ONLY'})
                    if self.path=='/review/session':
                        try:
                            if self.headers.get_all('Content-Length') is None or self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length'))!=1:raise ValueError()
                            length=int(self.headers['Content-Length'])
                            if not 0<length<256:raise ValueError()
                            chunks=[];remaining=length;deadline=time.monotonic()+1
                            while remaining:
                                budget=deadline-time.monotonic()
                                if budget<=0:raise ValueError()
                                self.connection.settimeout(budget)
                                chunk=self.rfile.read1(remaining)
                                if not chunk:raise ValueError()
                                chunks.append(chunk);remaining-=len(chunk)
                            body=json.loads(b''.join(chunks))
                            if set(body)!={'role'} or body['role'] not in ('community','platform','merchant'):raise ValueError()
                            result=c.login(owner.accounts[body['role']],'FixturePassword123!')
                            return self.answer(200,dict(result=result,workspace=body['role'],isolated=True))
                        except Exception:return self.answer(400,{'error':'ISOLATED_REVIEW_SESSION_REQUIRED'})
                    # Do not allow any provider IO from this review runner.
                    if self.path=='/mini/payment' or self.path.startswith('/community/provider-actions'):
                        return self.answer(403,{'error':'REAL_PROVIDER_OPERATIONS_DISABLED'})
                    return super().do_POST()
            self.server=HTTPServer(('127.0.0.1',port),Handler)
        except BaseException:fx.tearDown();raise
    @staticmethod
    def frame_script(role,filename):
        # These credentials belong only to the synthetic temporary Center and
        # stay in this frame. Production web-session code is never modified.
        bootstrap="""
window.addEventListener('load',async()=>{
 const role=ROLE;const reply=await fetch('/review/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role})});const context=await reply.json();
 if(!reply.ok||context.isolated!==true)throw Error('隔离会话未建立');
 const session=context.result;const originalFetch=window.fetch.bind(window);
 window.fetch=(url,options={})=>{const target=new URL(url,location.href);if(target.origin!==location.origin)throw Error('隔离预览不访问外部网络');return originalFetch(url,{...options,headers:{...options.headers,'X-Center-Session':session.token,'X-CSRF-Token':session.csrf}});};
 if(window.configureCommunityWorkbench)window.configureCommunityWorkbench({csrf:session.csrf,workspace:role});
 if(window.configureCommunityPortal)window.configureCommunityPortal({csrf:session.csrf,workspace:role});
 if(window.configureCommunityOnboarding)await window.configureCommunityOnboarding({csrf:session.csrf});
 const banner=document.createElement('p');banner.textContent='本地隔离测试库 · 原身份/接口/持久数据 · 微信认证和支付均未启用';banner.style.cssText='background:#fff4d1;padding:12px';document.body.prepend(banner);
 const allSections=[...document.querySelectorAll('main > section')];const allowed=role==='community'?['个人资料与推荐关系','社区资料','打开社区','社区订单、收益与结算观察','社区推广','查询结果']:['平台审核','平台运营查询','平台商家管理','查询结果'];const sections=FILENAME==='communities.html'?allSections.filter(s=>allowed.includes(s.querySelector('h2')?.textContent)):allSections.filter(s=>s.id!=='applicant'&&(!['providerActions','billSection'].includes(s.id)||!s.hidden));allSections.filter(s=>!sections.includes(s)).forEach(s=>s.hidden=true);const navigation=document.createElement('nav');navigation.style.cssText='display:flex;gap:8px;flex-wrap:wrap;padding:12px';document.body.insertBefore(navigation,document.querySelector('main'));
 const result=sections.find(s=>s.querySelector('h2')?.textContent==='查询结果');
 const show=()=>{const index=Number(location.hash.slice(1)||0);sections.forEach((s,i)=>s.hidden=i!==index&&s!==result);};
 sections.filter(s=>s!==result).forEach(s=>{const i=sections.indexOf(s),button=document.createElement('button');button.textContent=s.querySelector('h2')?.textContent||'申请与审核';button.onclick=()=>{location.hash=String(i);show();};navigation.append(button);});window.addEventListener('hashchange',show);show();document.body.dataset.reviewReady='true';
});
"""
        return bootstrap.replace('ROLE',json.dumps(role)).replace('FILENAME',json.dumps(filename))
    def close(self):
        self.server.server_close();self.fixture.tearDown()
    def run(self):
        print(json.dumps(dict(url='http://127.0.0.1:'+str(self.server.server_port),isolated=True,payments=False,temporary_data=True)),flush=True)
        try:self.server.serve_forever(poll_interval=.1)
        finally:self.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args()
    if not 0<=args.port<=65535:parser.error('invalid port')
    ReviewRuntime(args.port).run()

if __name__=='__main__':main()
