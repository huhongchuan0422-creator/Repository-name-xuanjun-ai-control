'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const originalStore={name:'Original authorized store',description:'Original scene-authorized description',contact:'Fixture contact'};
const publicStore={id:'a'.repeat(64),name:'Public directory store',description:'Published description',storefront_photo:null,photo_state:'NOT_CONNECTED'};
function fixture({scene='shop1',store=originalStore,hold=false,holdPublic=false,denied=false,network=false,unavailable=false,rejected=false,empty=false,publicNetwork=false,directoryNetwork=false,loginDenied=false,publicDenied=false}={}){
  const calls=[],held=[],heldPublic=[],app={globalData:{baseUrl:'https://fixture.invalid',mode:'WECHAT_LOGIN',commerce:true,payments:false,...(scene?{scene}:{})}};let navigation='';
  const reply=(o,result)=>o.success({statusCode:200,data:{payment_enabled:false,result}});
  const storefront=o=>unavailable||rejected?o.success({statusCode:400,data:{error:unavailable?'STOREFRONT_UNAVAILABLE':'INVALID_REQUEST',message:'PRIVATE_DETAIL_NOT_FOR_DISPLAY'}}):reply(o,{merchant:store,ads:{},payment_started:false,provider_settlement_verified:false});
  const wx={login(o){calls.push({operation:'wx.login'});o.success({code:'current-storefront-fixture'});},navigateTo(o){navigation=o.url;o.success?.();o.complete?.();},redirectTo(o){navigation=o.url;o.success?.();o.complete?.();},request(o){
    calls.push({url:o.url,...o.data});
    if(o.url.endsWith('/mini/login')&&loginDenied)return o.success({statusCode:403,data:{error:'ACCESS_DENIED'}});
    if(o.url.endsWith('/mini/login'))return reply(o,{provider:'WECHAT_MINIPROGRAM',payment_enabled:false,session_token:'T'.repeat(32),expires_at:Math.floor(Date.now()/1000)+3600});
    if(o.data.operation==='commerce.products')return reply(o,{products:[],has_more:false,next_cursor:null});
    if(o.data.operation==='community.storefront'){
      if(hold){held.push(o);return;}
      if(denied)return o.success({statusCode:403,data:{error:'fixture denied'}});
      if(network)return o.fail({errMsg:'fixture unavailable'});
      return storefront(o);
    }
    if(o.data.operation==='customer.directory'&&directoryNetwork)return o.fail({errMsg:'synthetic network failure'});
    if(o.data.operation==='customer.directory')return reply(o,{records:empty?[]:[publicStore],categories:[],has_more:false,next_cursor:null,visibility:'CURRENT_AUTHORIZED_PROJECT_TENANT',storefront_photo_supported:false});
    if(o.data.operation==='customer.store'){if(publicDenied)return o.success({statusCode:403,data:{error:'ACCESS_DENIED'}});if(publicNetwork)return o.fail({errMsg:'synthetic network failure'});if(holdPublic){heldPublic.push(o);return;}return reply(o,publicStore);}
    throw Error('UNPLANNED_REQUEST:'+o.data.operation);
  }};
  function page(name='checkout'){
    const filename=path.join(__dirname,'pages',name,'index.js');let definition;
    vm.runInNewContext(fs.readFileSync(filename,'utf8'),{Page:value=>definition=value,require:p=>require(path.resolve(path.dirname(filename),p)),wx,getApp:()=>app,getCurrentPages:()=>[],encodeURIComponent});
    return {...definition,data:structuredClone(definition.data),setData(update,callback){Object.assign(this.data,update);callback?.();}};
  }
  return {app,calls,held,heldPublic,page,get navigation(){return navigation;},deny(){denied=true;},setUnavailable(value){unavailable=value;},setPublicNetwork(value){publicNetwork=value;},setPublicDenied(value){publicDenied=value;},setDirectoryNetwork(value){directoryNetwork=value;},setLoginDenied(value){loginDenied=value;},releasePublic(){for(const o of heldPublic.splice(0))reply(o,publicStore);},release(){const waiting=held.splice(0);for(const o of waiting)storefront(o);},async waitHeld(){for(let n=0;n<30&&!held.length;n++)await tick();assert.ok(held.length,'original storefront request was issued');}};
}
const event=dataset=>({currentTarget:{dataset}});
test('home current-store route reads original scene storefront with one identity and no invented directory id',async()=>{
  const f=fixture(),home=f.page('home');await home.onLoad({scene:'shop1'});home.openStorefront();assert.equal(f.navigation,'/pages/checkout/index?view=store-detail&scene=shop1');home.onUnload();
  const p=f.page();await p.onLoad({scene:'shop1',view:'store-detail'});
  assert.equal(p.data.detailState,'READY');assert.equal(p.data.sceneStorefront.name,originalStore.name);assert.equal(p.data.sceneStorefront.description,originalStore.description);
  assert.deepEqual(Object.keys(p.data.sceneStorefront).sort(),['description','name']);assert.equal(p.data.selectedRecommendation,null);assert.equal(p.data.paymentsEnabled,false);
  assert.equal(f.calls.filter(x=>x.operation==='wx.login').length,1);assert.equal(f.calls.filter(x=>x.operation==='community.storefront').length,1);
  assert.equal(f.calls.find(x=>x.operation==='community.storefront').scene,'shop1');assert.equal(f.calls.filter(x=>/^customer\./.test(x.operation||'')).length,0);
});
test('current-store rejection is failed, not fabricated public or cached storefront success',async()=>{
  const f=fixture({denied:true}),p=f.page();await p.onLoad({scene:'shop1',view:'store-detail'});
  assert.equal(p.data.detailState,'FAILED');assert.equal(p.data.sceneStorefront,null);assert.equal(p.data.selectedRecommendation,null);assert.equal(p.session,null);
});
test('current-store network failure remains failed and does not manufacture an empty success',async()=>{
  const f=fixture({network:true}),p=f.page();await p.onLoad({scene:'shop1',view:'store-detail'});assert.equal(p.data.detailState,'FAILED');assert.equal(p.data.sceneStorefront,null);
});
test('a denied reread removes previously displayed current-store details',async()=>{
  const f=fixture(),p=f.page();await p.onLoad({scene:'shop1',view:'store-detail'});assert.ok(p.data.sceneStorefront);f.deny();await p.loadSceneStorefront();
  assert.equal(p.data.detailState,'FAILED');assert.equal(p.data.sceneStorefront,null);assert.equal(p.data.selectedRecommendation,null);
});
test('malformed original storefront fields never become rendered current-store evidence',async()=>{
  for(const store of [null,[],{}, {name:'missing description'}, {name:'',description:'empty name'}, {name:'type mismatch',description:42}]){
    const f=fixture({store}),p=f.page();await p.onLoad({scene:'shop1',view:'store-detail'});assert.equal(p.data.detailState,'FAILED');assert.equal(p.data.sceneStorefront,null);assert.equal(p.data.selectedRecommendation,null);
  }
});
test('return before late storefront result loads the true directory and cannot restore detail',async()=>{
  const f=fixture({hold:true}),p=f.page(),loading=p.onLoad({scene:'shop1',view:'store-detail'});await f.waitHeld();await p.backRecommendations();
  assert.equal(p.data.directoryState,'READY');assert.equal(p.data.directory[0].id,publicStore.id);f.release();await loading;
  assert.equal(p.data.viewMode,'recommendations');assert.equal(p.data.sceneStorefront,null);assert.equal(p.data.selectedRecommendation,null);assert.equal(f.calls.filter(x=>x.operation==='customer.directory').length,1);
});
test('return to an already loaded directory does not create an extra directory read',async()=>{
  const f=fixture(),p=f.page();await p.onLoad({scene:'shop1',view:'recommendations'});await tick();
  p.setData({viewMode:'store-detail'});await p.loadSceneStorefront();const count=f.calls.filter(x=>x.operation==='customer.directory').length;await p.backRecommendations();
  assert.equal(f.calls.filter(x=>x.operation==='customer.directory').length,count);assert.equal(p.data.sceneStorefront,null);assert.equal(p.data.directory[0].id,publicStore.id);
});
test('public directory detail supersedes a late current-store response without source mixing',async()=>{
  const f=fixture({hold:true}),p=f.page(),loading=p.onLoad({scene:'shop1',view:'store-detail'});await f.waitHeld();await p.backRecommendations();await p.openRecommendation(event({id:publicStore.id}));
  assert.equal(p.data.selectedRecommendation.id,publicStore.id);f.release();await loading;
  assert.equal(p.data.detailState,'READY');assert.equal(p.data.selectedRecommendation.name,publicStore.name);assert.equal(p.data.sceneStorefront,null);
});
test('current-store detail supersedes a late public-directory response without source mixing',async()=>{
  const f=fixture({holdPublic:true}),p=f.page();await p.onLoad({scene:'shop1',view:'recommendations'});await tick();const loading=p.openRecommendation(event({id:publicStore.id}));
  for(let n=0;n<30&&!f.heldPublic.length;n++)await tick();assert.equal(f.heldPublic.length,1);await p.loadSceneStorefront();assert.equal(p.data.sceneStorefront.name,originalStore.name);
  f.releasePublic();await loading;assert.equal(p.data.sceneStorefront.name,originalStore.name);assert.equal(p.data.selectedRecommendation,null);assert.equal(p.data.detailState,'READY');
});
test('unload discards late current-store data',async()=>{
  const f=fixture({hold:true}),p=f.page(),loading=p.onLoad({scene:'shop1',view:'store-detail'});await f.waitHeld();p.onUnload();f.release();await loading;assert.equal(p.data.sceneStorefront,null);assert.equal(p.data.sessionReady,false);
});
test('logout discards late current-store data and clears prior source projection',async()=>{
  const f=fixture({hold:true}),p=f.page(),loading=p.onLoad({scene:'shop1',view:'store-detail'});await f.waitHeld();p.customerSessionRevoked('fixture logout');f.release();await loading;
  assert.equal(p.data.sceneStorefront,null);assert.equal(p.data.selectedRecommendation,null);assert.equal(p.data.sessionReady,false);
});
test('scene change discards late current-store data instead of selecting another merchant',async()=>{
  const f=fixture({hold:true}),p=f.page(),loading=p.onLoad({scene:'shop1',view:'store-detail'});await f.waitHeld();f.app.globalData.scene='shop2';p.onShow();f.release();await loading;
  assert.equal(p.data.sceneStorefront,null);assert.equal(p.data.sessionReady,false);assert.ok(!f.calls.some(x=>x.operation==='community.storefront'&&x.scene==='shop2'));
});
test('missing scene never guesses the first public record as current store',async()=>{
  const f=fixture({scene:''}),p=f.page();await p.onLoad({view:'store-detail'});assert.equal(p.scene,'');assert.equal(p.data.sceneStorefront,null);assert.equal(p.data.selectedRecommendation,null);
  assert.equal(f.calls.filter(x=>x.operation==='community.storefront').length,0);assert.equal(p.data.directory[0].id,publicStore.id);
});
test('fresh page load and successful page revocation clear an existing current-store projection',async()=>{
  const f=fixture(),p=f.page();await p.onLoad({scene:'shop1',view:'store-detail'});assert.ok(p.data.sceneStorefront);
  await p.onLoad({scene:'shop1',view:'recommendations'});assert.equal(p.data.sceneStorefront,null);await tick();p.setData({viewMode:'store-detail'});await p.loadSceneStorefront();assert.ok(p.data.sceneStorefront);
  p.customerSessionRevoked('fixture logout');assert.equal(p.data.sceneStorefront,null);assert.equal(p.data.detailState,'NOT_QUERIED');
});
test('approved WXML keeps current-scene and public detail separate with its current failure action',()=>{
  const text=fs.readFileSync(path.join(__dirname,'pages/checkout/index.wxml'),'utf8');
  assert.ok(text.includes("detailState==='READY'&&selectedRecommendation"));assert.ok(text.includes("detailState==='READY'&&sceneStorefront"));
  assert.ok(text.includes('{{sceneStorefront.name}}'));assert.ok(text.includes('{{sceneStorefront.description}}'));assert.ok(text.includes('店铺资料暂时无法加载，请返回重试。'));
  const detail=text.split("viewMode==='store-detail'")[1].split("viewMode==='orders'")[0];assert.ok(detail.includes('返回店铺列表'));assert.ok(!detail.includes('发起支付'));
});

test('known unavailable current-store stays failed, keeps session and does not invent a merchant',async()=>{
  const f=fixture({unavailable:true}),p=f.page();await p.onLoad({scene:'shop1',view:'store-detail'});
  assert.equal(p.data.detailState,'FAILED');assert.equal(p.data.sceneStorefront,null);assert.equal(p.data.selectedRecommendation,null);
  assert.equal(p.data.sessionReady,true);assert.equal(p.session.isAuthenticated(),true);
  assert.match(p.data.detailError,/当前门店资料暂不可用.*联系项目负责人核对/);assert.doesNotMatch(JSON.stringify(p.data),/PRIVATE_DETAIL_NOT_FOR_DISPLAY/);
  assert.equal(f.calls.filter(x=>x.operation==='community.storefront').length,1);assert.equal(f.calls.filter(x=>/^customer\./.test(x.operation||'')).length,0);
});
test('old generic 400 cannot be presented as a confirmed unavailable profile',async()=>{
  const f=fixture({rejected:true}),p=f.page();await p.onLoad({scene:'shop1',view:'store-detail'});
  assert.equal(p.data.detailState,'FAILED');assert.equal(p.data.sceneStorefront,null);assert.equal(p.data.detailError,'');
  assert.equal(f.calls.filter(x=>x.operation==='community.storefront').length,1);
});
test('typed unavailable reread removes old details and later success clears fixed feedback',async()=>{
  const f=fixture(),p=f.page();await p.onLoad({scene:'shop1',view:'store-detail'});assert.ok(p.data.sceneStorefront);
  f.setUnavailable(true);await p.loadSceneStorefront();assert.equal(p.data.sceneStorefront,null);assert.match(p.data.detailError,/当前门店资料暂不可用/);
  f.setUnavailable(false);await p.loadSceneStorefront();assert.equal(p.data.detailState,'READY');assert.equal(p.data.detailError,'');assert.equal(p.data.sceneStorefront.name,originalStore.name);
});
for(const action of ['back','unload','logout','scene'])test('late unavailable reply cannot restore feedback after '+action,async()=>{
  const f=fixture({hold:true,unavailable:true}),p=f.page(),loading=p.onLoad({scene:'shop1',view:'store-detail'});await f.waitHeld();
  if(action==='back')await p.backRecommendations();
  else if(action==='unload')p.onUnload();
  else if(action==='logout')p.customerSessionRevoked('fixture logout');
  else{f.app.globalData.scene='shop2';p.onShow();}
  f.release();await loading;assert.equal(p.data.detailError,'');assert.equal(p.data.sceneStorefront,null);assert.notEqual(p.data.detailState,'READY');
});
test('public detail after a typed current-store error starts with no stale fixed feedback',async()=>{
  const f=fixture({unavailable:true}),p=f.page();await p.onLoad({scene:'shop1',view:'store-detail'});assert.ok(p.data.detailError);
  await p.backRecommendations();await p.openRecommendation(event({id:publicStore.id}));assert.equal(p.data.detailError,'');assert.equal(p.data.selectedRecommendation.name,publicStore.name);
});
test('detail template renders only fixed safe feedback with the existing generic fallback',()=>{
  const text=fs.readFileSync(path.join(__dirname,'pages/checkout/index.wxml'),'utf8');
  assert.ok(text.includes("{{detailError||'店铺资料暂时无法加载，请返回重试。'}}"));
});

test('scene-less home storefront entry opens real recommendations rather than an unbound detail error',async()=>{
  const f=fixture({scene:''}),home=f.page('home');await home.onLoad({});home.openStorefront();
  assert.equal(f.navigation,'/pages/checkout/index?view=recommendations');home.onUnload();
});
test('scene-less direct detail cold entry settles in actual directory',async()=>{
  const f=fixture({scene:''}),p=f.page();await p.onLoad({view:'store-detail'});
  assert.equal(p.data.viewMode,'recommendations');assert.equal(p.data.directoryState,'READY');
  assert.equal(p.data.detailState,'NOT_QUERIED');assert.equal(p.data.selectedRecommendation,null);assert.equal(p.data.sceneStorefront,null);
  assert.equal(f.calls.filter(x=>x.operation==='community.storefront').length,0);
  assert.equal(f.calls.filter(x=>x.operation==='customer.directory').length,1);
});
test('scene-less real empty directory renders empty state, not failed storefront',async()=>{
  const f=fixture({scene:'',empty:true}),p=f.page();await p.onLoad({view:'store-detail'});p.onShow();
  assert.equal(p.data.viewMode,'recommendations');assert.equal(p.data.directoryState,'READY');assert.equal(p.data.visibleDirectoryCount,0);
  assert.equal(p.data.selectedRecommendation,null);assert.equal(p.data.sceneStorefront,null);
});
test('reviewer without a login session stays signed out and never issues protected reads',async()=>{
  const f=fixture({scene:'',loginDenied:true}),p=f.page();await p.onLoad({view:'store-detail'});
  assert.equal(p.data.viewMode,'recommendations');assert.equal(p.data.sessionReady,false);assert.equal(p.data.directoryState,'NOT_QUERIED');
  assert.equal(f.calls.filter(x=>/^(customer|community)./.test(x.operation||'')).length,0);
  f.setLoginDenied(false);await p.onLoad({view:'recommendations'});assert.equal(p.data.directoryState,'READY');
});
test('public detail retries exact returned id and never substitutes current-scene storefront',async()=>{
  const f=fixture({scene:'',publicNetwork:true}),p=f.page();await p.onLoad({view:'recommendations'});
  await p.openRecommendation(event({id:publicStore.id}));assert.equal(p.data.detailState,'FAILED');assert.equal(p.data.selectedRecommendation,null);
  f.setPublicNetwork(false);await p.retryStoreDetail();assert.equal(p.data.detailState,'READY');assert.equal(p.data.selectedRecommendation.id,publicStore.id);
  assert.equal(f.calls.filter(x=>x.operation==='customer.store').length,2);assert.equal(f.calls.filter(x=>x.operation==='community.storefront').length,0);
});
test('current-scene detail retries original scene after typed unavailability without guessing a list record',async()=>{
  const f=fixture({unavailable:true}),p=f.page();await p.onLoad({scene:'shop1',view:'store-detail'});
  assert.equal(p.data.detailState,'FAILED');f.setUnavailable(false);await p.retryStoreDetail();assert.equal(p.data.detailState,'READY');
  assert.equal(p.data.sceneStorefront.name,originalStore.name);assert.equal(p.data.selectedRecommendation,null);
  assert.equal(f.calls.filter(x=>x.operation==='community.storefront').length,2);assert.equal(f.calls.filter(x=>x.operation==='customer.store').length,0);
});
test('return after failed directory performs real retry instead of retaining an unrecoverable failed list',async()=>{
  const f=fixture({scene:'',directoryNetwork:true}),p=f.page();await p.onLoad({view:'recommendations'});assert.equal(p.data.directoryState,'FAILED');
  p.setData({viewMode:'store-detail',detailState:'FAILED'});f.setDirectoryNetwork(false);await p.backRecommendations();
  assert.equal(p.data.directoryState,'READY');assert.equal(p.data.viewMode,'recommendations');assert.equal(f.calls.filter(x=>x.operation==='customer.directory').length,2);
});
test('invalid scene and unknown detail id never become a default merchant or authorized detail read',async()=>{
  const f=fixture({scene:''}),p=f.page();await p.onLoad({scene:'../invalid',view:'store-detail'});
  assert.equal(p.data.sessionReady,false);assert.equal(p.data.sceneStorefront,null);assert.equal(f.calls.length,0);
  await p.onLoad({view:'recommendations'});const count=f.calls.length;
  for(const id of ['',null,'../invalid','b'.repeat(64)])await p.openRecommendation(event({id}));assert.equal(f.calls.length,count);assert.equal(p.data.selectedRecommendation,null);
});
test('retry button is bound to actual detail retry handler',()=>{
  const text=fs.readFileSync(path.join(__dirname,'pages/checkout/index.wxml'),'utf8');assert.ok(text.includes('bindtap="retryStoreDetail"'));
});
test('revoked public detail retry restores directory identity, never substitutes ambient current store',async()=>{
  const f=fixture({publicDenied:true}),p=f.page();await p.onLoad({scene:'shop1',view:'recommendations'});await tick();
  await p.openRecommendation(event({id:publicStore.id}));assert.equal(p.data.sessionReady,false);
  const originalReads=f.calls.filter(x=>x.operation==='community.storefront').length;
  f.setPublicDenied(false);await p.retryStoreDetail();assert.equal(p.data.viewMode,'recommendations');assert.equal(p.data.directoryState,'READY');
  assert.equal(p.data.sceneStorefront,null);assert.equal(p.data.selectedRecommendation,null);assert.equal(f.calls.filter(x=>x.operation==='community.storefront').length,originalReads+1);
  // The normal recommendations page reads its scene's header, not a rendered store-detail projection.
  assert.equal(p.data.detailState,'NOT_QUERIED');
});
