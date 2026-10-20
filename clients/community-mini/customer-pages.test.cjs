const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const sessionModule=require('./session');

function loadPage(path,{baseUrl='https://fixture.invalid'}={}){
  let definition;const calls=[],nav=[],config={baseUrl,payments:false};
  const wx={
    login(o){calls.push({kind:'login'});o.success({code:'fixture-code'});},
    request(o){
      calls.push(o);
      if(o.url.endsWith('/mini/login'))return o.success({statusCode:200,data:{payment_enabled:false,result:{
        session_token:'s'.repeat(32),expires_at:Math.floor(Date.now()/1000)+3600,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});
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
  vm.runInNewContext(fs.readFileSync(__dirname+'/'+path,'utf8'),{
    Page:p=>{definition=p;},wx,getApp:()=>({globalData:config}),
    require:p=>p==='../../session'?sessionModule:require(p),encodeURIComponent
  });
  const page={...definition,data:structuredClone(definition.data),setData(patch){Object.assign(this.data,patch);}};
  return {page,calls,nav,config,wx};
}

test('app routes customer home/profile while preserving checkout route and checkout links home',()=>{
  const app=JSON.parse(fs.readFileSync(__dirname+'/app.json','utf8'));
  assert.deepEqual(app.pages,['pages/home/index','pages/profile/index','pages/checkout/index']);
  const checkout=fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8');
  const script=fs.readFileSync(__dirname+'/pages/checkout/index.js','utf8');
  assert.match(checkout,/bindtap="openCustomerHome"/);
  assert.match(script,/pages\/home\/index\?scene=/);
  assert.match(fs.readFileSync(__dirname+'/app.js','utf8'),/baseUrl: '', token: '', mode: 'WECHAT_LOGIN', payments: false/);
});

test('missing backend is explicit and retry login uses existing session boundary',async()=>{
  const h=loadPage('pages/home/index.js',{baseUrl:''});h.page.scene='shop1';
  await h.page.login();
  assert.equal(h.page.data.authenticated,false);
  assert.match(h.page.data.status,/未配置业务后端/);
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
