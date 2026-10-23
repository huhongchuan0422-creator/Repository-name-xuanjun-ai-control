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
      if(op==='commerce.profile_update')return o.success({statusCode:200,data:{payment_enabled:false,result:{
        user_id:'user1',project_customer_id:'customer1',nickname:o.data.params.nickname,contact:o.data.params.contact,version:1}}});
      o.fail({errMsg:'unexpected'});
    },
    navigateTo(o){nav.push(o.url);}
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
  assert.match(wxml,/position:fixed/);assert.match(wxml,/safe-area-inset-bottom/);
  assert.match(wxml,/padding-bottom:180rpx/);
 }
 const checkout=fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8');
 assert.match(checkout,/disabled="{{pending\|\|!sessionReady}}"/);
 assert.match(checkout,/orderDetails&&!detailsCollapsed/);
 assert.match(checkout,/返回订单列表/);assert.match(checkout,/重新显示所选订单详情/);
});
test('app routes customer home/profile while preserving checkout route and checkout links home',()=>{
  const app=JSON.parse(fs.readFileSync(__dirname+'/app.json','utf8'));
  assert.deepEqual(app.pages,['pages/home/index','pages/profile/index','pages/checkout/index','pages/merchant/index','pages/merchant-join/index']);
  const checkout=fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8');
  const script=fs.readFileSync(__dirname+'/pages/checkout/index.js','utf8');
  assert.match(checkout,/bindtap="openCustomerHome"/);
  assert.ok(script.includes("const url=section==='home'?'/pages/home/index':'/pages/profile/index';"));
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
  assert.deepEqual(business.map(x=>x.data.operation),['commerce.profile_read','commerce.profile_update']);
  assert.equal(JSON.stringify(business[1].data.params),JSON.stringify({nickname:'Alice',contact:'alice@example.org',expected_version:0}));
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


test('missing scene cold start and retry stay not-ready without false authentication',async()=>{
  const h=loadPage('pages/home/index.js');
  h.page.onLoad({});
  assert.equal(h.page.data.authenticated,false);
  assert.match(h.page.data.status,/缺少门店场景/);
  const before=h.calls.length;
  await h.page.retryLogin();
  assert.equal(h.page.data.authenticated,false);
  assert.match(h.page.data.status,/缺少门店场景/);
  assert.equal(h.calls.length,before);
  h.page.openProfile();
  assert.equal(h.nav.length,0);
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
