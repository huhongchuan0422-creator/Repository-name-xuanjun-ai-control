const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const sessionModule=require('./session');
const authModule=require('./customer-auth');

function environment(baseUrl='https://fixture.invalid'){
  const calls=[],nav=[],pages=[],config={baseUrl,payments:false};
  let tokenNo=0;
  const wx={
    login(o){calls.push({kind:'login'});o.success({code:'fixture-code'});},
    request(o){
      calls.push(o);
      if(o.url.endsWith('/mini/login')){tokenNo++;return o.success({statusCode:200,data:{payment_enabled:false,result:{
        session_token:String(tokenNo).repeat(32),expires_at:Math.floor(Date.now()/1000)+3600,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});}
      if(o.url.endsWith('/mini/logout'))return o.success({statusCode:200,data:{payment_enabled:false,result:{logged_out:true}}});
      const op=o.data&&o.data.operation;
      if(op==='commerce.profile_read')return o.success({statusCode:200,data:{payment_enabled:false,result:{
        user_id:'user1',project_customer_id:'customer1',nickname:'',contact:'',version:0}}});
      if(op==='commerce.notices')return o.success({statusCode:200,data:{payment_enabled:false,result:{records:[],has_more:false,next_cursor:null}}});
      if(op==='commerce.profile_update')return o.success({statusCode:200,data:{payment_enabled:false,result:{
        user_id:'user1',project_customer_id:'customer1',nickname:o.data.params.nickname,contact:o.data.params.contact,version:1}}});
      o.fail({errMsg:'unexpected'});
    },
    navigateTo(o){nav.push(o.url);if(o.success)o.success();if(o.complete)o.complete();},
    redirectTo(o){nav.push(o.url);if(o.success)o.success();if(o.complete)o.complete();}
  };
  return {calls,nav,pages,config,wx};
}
function loadPage(path,{baseUrl='https://fixture.invalid',env=null}={}){
  env=env||environment(baseUrl);let definition;
  vm.runInNewContext(fs.readFileSync(__dirname+'/'+path,'utf8'),{
    Page:p=>{definition=p;},wx:env.wx,getApp:()=>({globalData:env.config}),getCurrentPages:()=>env.pages,
    require:p=>p==='../../session'?sessionModule:p==='../../customer-auth'?authModule:
      p==='../../client'?{makeClient:()=>({reset(){},storefront:async()=>({merchant:{name:'fixture'},ads:{}})})}:
      p==='../../payment'?{createPaymentFlow:()=>({reset(){}})}:require(p),encodeURIComponent
  });
  const page={...definition,data:structuredClone(definition.data),setData(patch){Object.assign(this.data,patch);}};
  env.pages.push(page);
  return {page,calls:env.calls,nav:env.nav,config:env.config,wx:env.wx,env};
}

test('native bottom navigation is fixed, safe-area aware, and reserves content space',()=>{
 for(const page of ['home','checkout','profile','merchant','merchant-join']){
  const wxml=fs.readFileSync(__dirname+'/pages/'+page+'/index.wxml','utf8');
  const css=fs.readFileSync(__dirname+'/app.wxss','utf8');assert.match(wxml,/class="xj-nav"/);assert.match(css,/position:fixed/);assert.match(css,/safe-area-inset-bottom/);
  assert.match(wxml,/padding-bottom:180rpx/);
 }
 const checkout=fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8');
 assert.match(checkout,/disabled="{{pending\|\|!sessionReady}}"/);
 assert.match(checkout,/orderDetails&&!detailsCollapsed/);
 assert.match(checkout,/返回本人订单列表/);assert.match(checkout,/bindtap="backToOrderList"/);assert.match(checkout,/bindtap="selectOrder"/);assert.match(checkout,/orderDetails\.lines/);
});
test('app routes customer home/profile while preserving checkout route and checkout links home',()=>{
  const app=JSON.parse(fs.readFileSync(__dirname+'/app.json','utf8'));
  assert.deepEqual(app.pages,['pages/home/index','pages/profile/index','pages/checkout/index','pages/merchant/index','pages/merchant-join/index']);
  const checkout=fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8');
  const script=fs.readFileSync(__dirname+'/pages/checkout/index.js','utf8');
  assert.match(checkout,/bindtap="openCustomerHome"/);
  assert.match(script,/auth.navigate\(this,e.currentTarget.dataset.section/);
  assert.match(fs.readFileSync(__dirname+'/customer-auth.js','utf8'),/home:'\/pages\/home\/index'/);
  assert.match(fs.readFileSync(__dirname+'/app.js','utf8'),/baseUrl: '', token: '', mode: 'WECHAT_LOGIN', payments: false/);
});

test('missing backend is explicit and retry login uses existing session boundary',async()=>{
  const h=loadPage('pages/home/index.js',{baseUrl:''});h.page.scene='shop1';
  await h.page.login();
  assert.equal(h.page.data.authenticated,false);
  assert.match(h.page.data.status,/服务尚未接通/);
  assert.equal(h.calls.length,0);
  h.config.baseUrl='https://fixture.invalid';
  await h.page.retryLogin();
  assert.equal(h.page.data.authenticated,true);
  assert.equal(h.calls.filter(x=>x.kind==='login').length,1);
  h.page.openProfile();
  assert.deepEqual(h.nav,['/pages/profile/index?scene=shop1']);
});

test('profile read and update reuse commerce profile APIs without fabricated fields',async()=>{
  const h=loadPage('pages/profile/index.js');h.page.scene='shop1';
  await h.page.loginAndLoad();
  assert.equal(h.page.data.loaded,true);
  assert.equal(h.page.data.nickname,'');
  assert.equal(h.page.data.contact,'');
  assert.equal(h.page.data.customerId,'customer1');
  h.page.input({currentTarget:{dataset:{field:'nickname'}},detail:{value:'Alice'}});
  h.page.input({currentTarget:{dataset:{field:'contact'}},detail:{value:'alice@example.org'}});
  await h.page.save();
  const business=h.calls.filter(x=>x.data&&x.data.operation);
  assert.deepEqual(business.map(x=>x.data.operation),['commerce.profile_read','commerce.notices','commerce.profile_update']);
  assert.deepEqual(JSON.parse(JSON.stringify(business[1].data.params)),{after_id:''});
  assert.equal(JSON.stringify(business[2].data.params),JSON.stringify({nickname:'Alice',contact:'alice@example.org',expected_version:0}));
  assert.equal(h.page.data.noticesLoaded,true);
  assert.equal(h.page.data.version,1);
});

test('logout clears private profile state and prevents further profile writes',async()=>{
  const h=loadPage('pages/profile/index.js');h.page.scene='shop1';
  await h.page.loginAndLoad();
  await h.page.logout();
  assert.equal(h.page.data.authenticated,false);
  assert.equal(h.page.data.loaded,false);
  assert.equal(h.page.data.nickname,'');
  assert.equal(h.page.data.contact,'');
  const before=h.calls.length;
  await h.page.save();
  assert.equal(h.calls.length,before);
});

test('access denial during update clears private state and requires explicit relogin',async()=>{
  const h=loadPage('pages/profile/index.js');h.page.scene='shop1';
  await h.page.loginAndLoad();
  h.page.setData({nickname:'Alice'});
  h.wx.request=o=>{
    h.calls.push(o);
    if(o.url.endsWith('/mini/login'))return o.success({statusCode:200,data:{payment_enabled:false,result:{
      session_token:'s'.repeat(32),expires_at:Math.floor(Date.now()/1000)+3600,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});
    o.success({statusCode:401,data:{error:'private'}});
  };
  await h.page.save();
  assert.equal(h.page.data.authenticated,false);
  assert.equal(h.page.data.loaded,false);
  assert.equal(h.page.data.nickname,'');
  assert.match(h.page.data.status,/重新登录/);
});


test('missing scene permits explicit identity login and public navigation, never private data',async()=>{
  const h=loadPage('pages/home/index.js');h.page.onLoad({});
  assert.equal(h.page.data.authenticated,false);assert.equal(h.calls.length,0);
  assert.match(h.page.data.status,/未选择门店/);
  await h.page.retryLogin();
  assert.equal(h.page.data.authenticated,true);
  assert.equal(h.calls.filter(x=>x.url&&x.url.endsWith('/mini/api')).length,0);
  assert.equal(h.config.scene,undefined);h.page.openProfile();
  assert.deepEqual(h.nav,['/pages/profile/index']);
  const p=loadPage('pages/profile/index.js');p.page.onLoad({});await p.page.loginAndLoad();
  assert.equal(p.page.data.authenticated,true);assert.equal(p.page.data.loaded,false);
  assert.equal(p.calls.filter(x=>x.url&&x.url.endsWith('/mini/api')).length,0);
});

test('logout from profile revokes retained home and checkout page sessions and private state',async()=>{
  const env=environment();
  const checkout=loadPage('pages/checkout/index.js',{env}).page;
  checkout.scene='shop1';
  checkout.session=sessionModule.createSession(env.wx,env.config.baseUrl);
  await checkout.session.login();
  const oldCheckoutSession=checkout.session;
  checkout.setData({nickname:'Private',profileContact:'secret',userId:'user1',projectCustomerId:'customer1',
    notices:[{id:'a'.repeat(64),message:'private',read:false}],orders:[{reference:'order1'}],commerceEnabled:true});

  const home=loadPage('pages/home/index.js',{env}).page;
  home.onLoad({scene:'shop1'});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(home.data.authenticated,true);

  const profile=loadPage('pages/profile/index.js',{env}).page;
  profile.onLoad({scene:'shop1'});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(profile.data.loaded,true);

  await profile.logout();
  assert.equal(profile.data.authenticated,false);
  assert.equal(home.data.authenticated,false);
  assert.equal(checkout.data.nickname,'');
  assert.equal(checkout.data.profileContact,'');
  assert.equal(checkout.data.userId,'');
  assert.equal(checkout.data.projectCustomerId,'');
  assert.equal(checkout.data.reference,'');
  assert.equal(checkout.data.notices.length,0);
  assert.equal(checkout.data.orders.length,0);
  assert.equal(checkout.session,null);
  await assert.rejects(oldCheckoutSession.transport('shop1',{operation:'community.storefront',params:{}}),/SESSION_EXPIRED/);
});

test('stack revocation makes a late login callback unable to restore authenticated UI',async()=>{
  const env=environment();let loginReply;
  env.wx.request=o=>{
    env.calls.push(o);
    if(o.url.endsWith('/mini/login')){loginReply=o;return;}
    if(o.url.endsWith('/mini/logout'))return o.success({statusCode:200,data:{payment_enabled:false,result:{logged_out:true}}});
  };
  const home=loadPage('pages/home/index.js',{env}).page;
  home.scene='shop1';
  const pending=home.login();
  await Promise.resolve();
  assert.ok(loginReply);
  authModule.revokePages(env.pages,'已退出登录');
  loginReply.success({statusCode:200,data:{payment_enabled:false,result:{
    session_token:'z'.repeat(32),expires_at:Math.floor(Date.now()/1000)+3600,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});
  await pending;
  assert.equal(home.data.authenticated,false);
  assert.match(home.data.status,/退出/);
});


test('profile logout releases pending so explicit relogin is not blocked',async()=>{
  const h=loadPage('pages/profile/index.js');h.page.scene='shop1';
  await h.page.loginAndLoad();
  await h.page.logout();
  assert.equal(h.page.data.pending,false);
  await h.page.retryLogin();
  assert.equal(h.page.data.authenticated,true);
  assert.equal(h.page.data.loaded,true);
});

test('late rejected old logout cannot clear a newer successful home login',async()=>{
  const env=environment();let oldLogout,newLogin;
  env.wx.request=o=>{
    env.calls.push(o);
    if(o.url.endsWith('/mini/login')){
      if(!newLogin)return o.success({statusCode:200,data:{payment_enabled:false,result:{
        session_token:'1'.repeat(32),expires_at:Math.floor(Date.now()/1000)+3600,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});
      newLogin=o;return;
    }
    if(o.url.endsWith('/mini/logout')){oldLogout=o;return;}
  };
  const home=loadPage('pages/home/index.js',{env}).page;home.scene='shop1';
  await home.login();assert.equal(home.data.authenticated,true);
  const old=home.logout();await Promise.resolve();
  assert.ok(oldLogout);assert.equal(home.data.pending,false);
  newLogin=true;
  const fresh=home.retryLogin();await Promise.resolve();
  assert.ok(typeof newLogin==='object');
  newLogin.success({statusCode:200,data:{payment_enabled:false,result:{
    session_token:'2'.repeat(32),expires_at:Math.floor(Date.now()/1000)+3600,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});
  await fresh;assert.equal(home.data.authenticated,true);
  oldLogout.fail({errMsg:'synthetic old logout failure'});await old;
  assert.equal(home.data.authenticated,true);
  assert.equal(home.data.pending,false);
  assert.equal(home.data.status,'客户身份已验证');
});

test('old login finally cannot unlock a replacement login',async()=>{
  const env=environment();const pendingLogins=[];
  env.wx.request=o=>{env.calls.push(o);if(o.url.endsWith('/mini/login')){pendingLogins.push(o);return;}};
  const home=loadPage('pages/home/index.js',{env}).page;home.scene='shop1';
  const first=home.login();await Promise.resolve();assert.equal(home.data.pending,true);
  authModule.revokePages(env.pages,'登录已退出，请重新登录');
  const second=home.login();await Promise.resolve();assert.equal(home.data.pending,true);
  pendingLogins[0].fail({errMsg:'old failure'});await first;
  assert.equal(home.data.pending,true);
  pendingLogins[1].success({statusCode:200,data:{payment_enabled:false,result:{
    session_token:'2'.repeat(32),expires_at:Math.floor(Date.now()/1000)+3600,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});
  await second;
  assert.equal(home.data.authenticated,true);
  assert.equal(home.data.pending,false);
});


test('late rejected profile save cannot revoke a newer successful login',async()=>{
  const h=loadPage('pages/profile/index.js');h.page.scene='shop1';
  await h.page.loginAndLoad();
  let oldSave;
  h.wx.request=o=>{
    h.calls.push(o);
    if(o.url.endsWith('/mini/login'))return o.success({statusCode:200,data:{payment_enabled:false,result:{
      session_token:'9'.repeat(32),expires_at:Math.floor(Date.now()/1000)+3600,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});
    const op=o.data&&o.data.operation;
    if(op==='commerce.profile_read')return o.success({statusCode:200,data:{payment_enabled:false,result:{
      user_id:'user1',project_customer_id:'customer1',nickname:'Fresh',contact:'',version:2}}});
    if(op==='commerce.profile_update'){oldSave=o;return;}
  };
  h.page.setData({nickname:'Old'});
  const stale=h.page.save();await Promise.resolve();assert.ok(oldSave);
  authModule.revokePages(h.env.pages,'登录已退出，请重新登录');
  await h.page.retryLogin();
  assert.equal(h.page.data.authenticated,true);assert.equal(h.page.data.loaded,true);assert.equal(h.page.data.nickname,'Fresh');
  oldSave.success({statusCode:403,data:{error:'old denied'}});await stale;
  assert.equal(h.page.data.authenticated,true);
  assert.equal(h.page.data.loaded,true);
  assert.equal(h.page.data.nickname,'Fresh');
  assert.equal(h.page.data.pending,false);
  assert.equal(h.page.data.status,'本人资料已读取');
});

test('late profile save finally cannot release a newer save request lock',async()=>{
  const h=loadPage('pages/profile/index.js');h.page.scene='shop1';
  await h.page.loginAndLoad();
  const updates=[];let freshVersion=1;
  h.wx.request=o=>{
    h.calls.push(o);
    if(o.url.endsWith('/mini/login'))return o.success({statusCode:200,data:{payment_enabled:false,result:{
      session_token:'8'.repeat(32),expires_at:Math.floor(Date.now()/1000)+3600,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});
    const op=o.data&&o.data.operation;
    if(op==='commerce.profile_read')return o.success({statusCode:200,data:{payment_enabled:false,result:{
      user_id:'user1',project_customer_id:'customer1',nickname:'Fresh',contact:'',version:freshVersion}}});
    if(op==='commerce.profile_update'){updates.push(o);return;}
  };
  h.page.setData({nickname:'Old'});
  const stale=h.page.save();await Promise.resolve();assert.equal(updates.length,1);
  authModule.revokePages(h.env.pages,'登录已退出，请重新登录');
  await h.page.retryLogin();
  h.page.setData({nickname:'Newest'});
  const fresh=h.page.save();await Promise.resolve();assert.equal(updates.length,2);assert.equal(h.page.data.pending,true);
  updates[0].success({statusCode:500,data:{error:'old failure'}});await stale;
  assert.equal(h.page.data.pending,true);
  updates[1].success({statusCode:200,data:{payment_enabled:false,result:{
    user_id:'user1',project_customer_id:'customer1',nickname:'Newest',contact:'',version:2}}});
  await fresh;
  assert.equal(h.page.data.pending,false);
  assert.equal(h.page.data.nickname,'Newest');
  assert.equal(h.page.data.version,2);
  assert.equal(h.page.data.status,'本人资料已保存');
});

test('unavailable login remains unauthenticated and renders a safe customer message',async()=>{
  for(const failure of ['network','server']){
    const h=loadPage('pages/home/index.js');h.page.scene='shop1';
    h.wx.request=o=>failure==='network'?o.fail({errMsg:'private network diagnostic'}):o.success({statusCode:503,data:'private upstream detail'});
    await h.page.login();
    assert.equal(h.page.data.authenticated,false);assert.equal(h.page.data.pending,false);
    assert.match(h.page.data.status,/重试/);
    assert.doesNotMatch(h.page.data.status,/SERVICE_|private|503/);
  }
});

test('consumer store page excludes internal delivery forms and preserves community and orders',()=>{
 const markup=fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8');
 for(const text of ['原客户项目中心','SECRETREF','projectAction','uploadProjectDocument','saveProjectReference'])assert.ok(!markup.includes(text),text);
 for(const text of ['communityAction','reloadProducts','loadOrders'])assert.ok(markup.includes(text),text);
 assert.equal(JSON.parse(fs.readFileSync(__dirname+'/pages/checkout/index.json','utf8')).navigationBarTitleText,'门店与订单');
 assert.ok(!JSON.parse(fs.readFileSync(__dirname+'/app.json','utf8')).window.navigationBarTitleText.includes('模拟'));
});


test('ordinary home exposes public entry and keeps initial login explicit',()=>{
 const h=loadPage('pages/home/index.js');h.page.onLoad({});
 assert.equal(h.page.data.needsScene,true);assert.equal(h.calls.length,0);
 assert.equal(h.config.scene,undefined);assert.equal(h.page.scene,null);
 const wxml=fs.readFileSync(__dirname+'/pages/home/index.wxml','utf8');
 assert.match(wxml,/wx:if="{{!authenticated}}"/);assert.match(wxml,/商家入驻 · 开始办理/);
 assert.doesNotMatch(wxml,/示例门店 A/);
 assert.match(wxml,/wx:if="{{!needsScene}}"/);
});
test('valid home scene retains original login and invalid explicit scene never inherits a store',async()=>{
 const valid=loadPage('pages/home/index.js');valid.page.onLoad({scene:'shop1'});
 await new Promise(r=>setImmediate(r));
 assert.equal(valid.page.data.needsScene,false);assert.equal(valid.page.data.authenticated,true);
 const invalid=loadPage('pages/home/index.js');invalid.config.scene='shop1';
 invalid.page.onLoad({scene:'../bad'});
 assert.equal(invalid.page.data.needsScene,true);assert.equal(invalid.calls.length,0);
});
test('privacy entry invokes only platform contract and handles absent, failed and late callbacks',()=>{
 const h=loadPage('pages/home/index.js');h.page.openPrivacy();
 assert.match(h.page.data.privacyStatus,/暂时无法打开/);
 let options;h.wx.openPrivacyContract=o=>{options=o;};h.page.openPrivacy();
 assert.equal(h.page.data.privacyStatus,'');assert.equal(h.calls.length,0);
 options.fail();assert.match(h.page.data.privacyStatus,/暂时无法打开/);
 h.page.openPrivacy();h.page.onUnload();options.fail();assert.equal(h.page.data.privacyStatus,'');
 assert.equal(h.page.data.authenticated,false);
});

// Regression for the Owner's actual scene-less official preview, not a fixture store.
test('all four public tabs navigate without a scene and repeated navigation has bounded stack',()=>{
 for(const source of ['home','profile','checkout']){
  const h=loadPage('pages/'+source+'/index.js');h.page.onLoad({});
  for(let i=0;i<3;i++)for(const section of ['home','recommendations','orders','profile'])h.page.navigateSection({currentTarget:{dataset:{section}}});
  assert.equal(h.nav.length,12);assert.ok(h.nav.every(url=>!url.includes('scene=')));
  assert.equal(h.calls.filter(x=>x.url&&x.url.endsWith('/mini/api')).length,0);
 }
});
test('public navigation errors surface and caller can retry, arbitrary scan never selects a store',()=>{
 const h=loadPage('pages/home/index.js');h.page.onLoad({});
 h.wx.redirectTo=o=>o.fail({errMsg:'private transport detail'});h.page.openProfile();
 assert.match(h.page.data.status,/页面暂时无法打开/);assert.equal(h.page._navigationPending,false);
 h.wx.scanCode=o=>o.success({result:'https://evil.invalid',path:'pages/other/index?scene=shop1'});h.page.scanStore();
 assert.equal(h.config.scene,undefined);assert.match(h.page.data.status,/有效门店码/);
});

test('recommendations and orders admission buttons navigate without a scene; back helper is exported',async()=>{for(const view of ['recommendations','orders']){const f=loadPage('pages/checkout/index.js');await f.page.onLoad({view});f.page.openMerchantJoin();assert.equal(f.nav.at(-1),'/pages/merchant-join/index');f.page.openMerchant();assert.equal(f.nav.at(-1),'/pages/merchant/index');f.page.goBack();assert.equal(f.nav.at(-1),'/pages/home/index');assert.equal(f.calls.some(c=>c.url&&c.url.endsWith('/mini/api')),false);}assert.equal(typeof authModule.back,'function');});

test('original more-services entry is reachable but never reads private data without a scene',async()=>{const f=loadPage('pages/home/index.js');await f.page.onLoad({});f.page.navigateSection({currentTarget:{dataset:{section:'services'}}});assert.equal(f.nav.at(-1),'/pages/checkout/index?view=services');const c=loadPage('pages/checkout/index.js');await c.page.onLoad({view:'services'});assert.equal(c.page.data.viewMode,'services');assert.equal(c.page.data.sessionReady,false);assert.equal(c.calls.length,0);const wxml=fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8');assert.match(wxml,/viewMode==='services' && !needsScene && sessionReady/);assert.match(wxml,/绑定推荐人/);assert.match(wxml,/我的社区关系/);});

test('visible order list preserves original next-page action rather than stranding it in more services',()=>{const text=fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8').split("viewMode==='orders'")[1].split("viewMode==='services'")[0];assert.match(text,/wx:if="{{ordersMore}}" bindtap="loadOrders" data-more="true"/);});

test('stale current home safely re-enters the new scene instead of same-route short circuit',()=>{const nav=[],page={route:'pages/home/index',scene:'old',_sceneStale:true,data:{activeSection:'home'},setData(p){Object.assign(this.data,p);}};authModule.navigate(page,'home',{redirectTo:o=>nav.push(o.url)},{globalData:{scene:'new'}});assert.deepEqual(nav,['/pages/home/index?scene=new']);assert.equal(page.scene,'old');});
