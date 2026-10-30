'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function fixture(){
  const source=fs.readFileSync(path.resolve(__dirname,'../../demos/community-stage/review-native.js'),'utf8');
  const start=source.indexOf(' function getNativeApp(){'),end=source.indexOf(' function pathFor(',start);assert.ok(start>0&&end>start);
  const clears=[],sessions=new WeakMap(),wx={},context={nativeApp:null,nativeIdentity:'',identity:{value:'consumer'},wx,location:{origin:'http://127.0.0.1:4321'},cache:{'session.js':{exports:{getSharedSession(actualWx,config){assert.equal(actualWx,wx);if(!sessions.has(config))sessions.set(config,{clear(){clears.push(config);}});return sessions.get(config);}}}}};
  vm.createContext(context);vm.runInContext(source.slice(start,end)+'\nthis.getApp=getNativeApp;',context);
  assert.ok(source.includes('wx,getNativeApp,()=>page?[page]:[]'));
  return {context,clears,getApp:()=>context.getApp()};
}
test('review adapter supplies one app/globalData identity throughout native navigation',()=>{
  const f=fixture(),first=f.getApp();first.globalData.scene='shop1';assert.equal(f.getApp(),first);assert.equal(f.getApp().globalData,first.globalData);assert.equal(f.getApp().globalData.scene,'shop1');assert.equal(f.clears.length,0);
  assert.equal(first.globalData.baseUrl,'http://127.0.0.1:4321');assert.equal(first.globalData.payments,false);assert.equal(first.globalData.mode,'WECHAT_LOGIN');
});
test('consumer-to-merchant switch clears old session and never reuses its app configuration',()=>{
  const f=fixture(),consumer=f.getApp();consumer.globalData.scene='consumer-only';f.context.identity.value='merchant';const merchant=f.getApp();assert.notEqual(merchant,consumer);assert.equal(f.clears.length,1);assert.equal(f.clears[0],consumer.globalData);assert.equal(merchant.globalData.scene,undefined);assert.equal(f.getApp(),merchant);assert.equal(f.clears.length,1);
});
test('returning to consumer creates a fresh scope and clears merchant session without token persistence',()=>{
  const f=fixture(),first=f.getApp();f.context.identity.value='merchant';const merchant=f.getApp();f.context.identity.value='consumer';const returned=f.getApp();assert.notEqual(returned,first);assert.notEqual(returned,merchant);assert.equal(f.clears.length,2);assert.equal(f.clears[1],merchant.globalData);assert.deepEqual(Object.keys(returned.globalData).sort(),['baseUrl','commerce','mode','payments']);
});
// Exercise the unchanged adapter loader/navigation and real Page/session code.
// Only DOM rendering is replaced by a state recorder; this is not browser proof.
function navigationFixture({holdLogin=false,holdProfile=false}={}){
  const root=__dirname,source=fs.readFileSync(path.resolve(root,'../../demos/community-stage/review-native.js'),'utf8'),sources={};
  function collect(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){const full=path.join(dir,entry.name);if(entry.isDirectory())collect(full);else if(/\.(js|json|wxml|wxss)$/.test(entry.name)&&!entry.name.includes('.test.'))sources[path.relative(root,full).replace(/\\/g,'/')]=fs.readFileSync(full,'utf8');}}
  collect(root);
  const calls=[],held=[],renders=[],terminal={},context={sources,cache:{},page:null,route:'',ready:true,nativeApp:null,nativeIdentity:'',identity:{value:'consumer'},location:{origin:'http://127.0.0.1:4321',hash:'#/pages/home/index?scene=shop1'},URL,structuredClone,Date,console,screen:{classList:{remove(){}}},frame:{classList:{add(){}}},document:{getElementById(){return terminal;},body:{dataset:{}}},openFrame(){throw Error('UNEXPECTED_WEB_FRAME');}};
  const reply=(o,result)=>o.success({statusCode:200,data:{payment_enabled:false,result}});
  const loginReply=o=>reply(o,{provider:'WECHAT_MINIPROGRAM',payment_enabled:false,session_token:(o.data.code==='merchant'?'M':'C').repeat(32),expires_at:Math.floor(Date.now()/1000)+3600});
  context.wx={login(o){calls.push({operation:'wx.login',identity:context.identity.value});o.success({code:context.identity.value});},request(o){
    calls.push({url:o.url,...o.data,credential:o.header['X-Community-Session']});
    if(o.url.endsWith('/mini/login')){if(holdLogin&&o.data.code==='consumer'){held.push(o);return;}return loginReply(o);}
    if(o.data.operation==='commerce.profile_read'&&holdProfile){held.push(o);return;}
    if(o.url.endsWith('/mini/merchant')&&o.data.operation==='workspaces')return reply(o,{workspaces:[],permissions:{}});
    throw Error('UNPLANNED_NATIVE_ADAPTER_REQUEST:'+o.data.operation);
  }};
  context.render=()=>renders.push({route:context.route,state:context.page?structuredClone(context.page.data):null});
  const functions=source.slice(source.indexOf(' function getNativeApp(){'),source.indexOf(' const wx={'));
  const navigation=source.slice(source.indexOf(' async function navigate(){'),source.indexOf(' function openFrame('));
  vm.createContext(context);vm.runInContext(functions+'\n'+navigation+'\nthis.runNavigation=navigate;',context);
  return {context,calls,held,renders,async waitHeld(){for(let n=0;n<30&&!held.length;n++)await new Promise(resolve=>setImmediate(resolve));assert.ok(held.length);},releaseLogin(){for(const o of held.splice(0))loginReply(o);},releaseProfile(){for(const o of held.splice(0))reply(o,{user_id:'old-user',project_customer_id:'old-customer',nickname:'OLD_PRIVATE_RESPONSE',contact:'old-private-contact',version:1});}};
}
test('actual adapter navigation unloads old Page and old delayed login cannot restore or render into merchant identity',async()=>{
  const f=navigationFixture({holdLogin:true}),c=f.context,oldNavigation=c.runNavigation();await f.waitHeld();const oldPage=c.page,oldSession=oldPage.session;
  c.identity.value='merchant';c.location.hash='#/pages/merchant/index?scene=shop1';await c.runNavigation();const merchantPage=c.page;const renderStart=f.renders.length;
  assert.equal(oldPage._dead,true);assert.equal(oldPage.session,null);assert.notEqual(merchantPage.session,oldSession);assert.equal(oldSession.isAuthenticated(),false);
  f.releaseLogin();await oldNavigation;
  assert.equal(c.page,merchantPage);assert.equal(oldPage.data.authenticated,false);assert.equal(c.route,'pages/merchant/index');
  assert.ok(f.renders.slice(renderStart).every(r=>r.route==='pages/merchant/index'&&!r.state.authenticated));
  const merchantRead=f.calls.find(x=>x.operation==='workspaces');assert.equal(merchantRead.credential,'M'.repeat(32));
});
test('actual adapter navigation clears old authenticated session and drops late private profile response after identity switch',async()=>{
  const f=navigationFixture({holdProfile:true}),c=f.context;await c.runNavigation();assert.equal(c.page.data.authenticated,true);
  c.location.hash='#/pages/profile/index?scene=shop1';const oldNavigation=c.runNavigation();await f.waitHeld();const oldPage=c.page,oldSession=oldPage.session;
  c.identity.value='merchant';c.location.hash='#/pages/merchant/index?scene=shop1';await c.runNavigation();const merchantPage=c.page;const renderStart=f.renders.length;
  assert.equal(oldPage._dead,true);assert.equal(oldPage.session,null);assert.equal(oldSession.isAuthenticated(),false);
  f.releaseProfile();await oldNavigation;
  assert.equal(c.page,merchantPage);assert.equal(oldPage.data.nickname,'');assert.ok(f.renders.slice(renderStart).every(r=>!JSON.stringify(r).includes('OLD_PRIVATE_RESPONSE')));
  assert.equal(f.calls.filter(x=>x.operation==='wx.login'&&x.identity==='consumer').length,1);assert.equal(f.calls.find(x=>x.operation==='workspaces').credential,'M'.repeat(32));
});
