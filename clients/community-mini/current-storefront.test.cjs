'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const originalStore={name:'Original authorized store',description:'Original scene-authorized description',contact:'Fixture contact'};
const publicStore={id:'a'.repeat(64),name:'Public directory store',description:'Published description',storefront_photo:null,photo_state:'NOT_CONNECTED'};
function fixture({scene='shop1',store=originalStore,hold=false,holdPublic=false,denied=false,network=false}={}){
  const calls=[],held=[],heldPublic=[],app={globalData:{baseUrl:'https://fixture.invalid',mode:'WECHAT_LOGIN',commerce:true,payments:false,...(scene?{scene}:{})}};let navigation='';
  const reply=(o,result)=>o.success({statusCode:200,data:{payment_enabled:false,result}});
  const storefront=o=>reply(o,{merchant:store,ads:{},payment_started:false,provider_settlement_verified:false});
  const wx={login(o){calls.push({operation:'wx.login'});o.success({code:'current-storefront-fixture'});},navigateTo(o){navigation=o.url;o.success?.();o.complete?.();},redirectTo(o){navigation=o.url;o.success?.();o.complete?.();},request(o){
    calls.push({url:o.url,...o.data});
    if(o.url.endsWith('/mini/login'))return reply(o,{provider:'WECHAT_MINIPROGRAM',payment_enabled:false,session_token:'T'.repeat(32),expires_at:Math.floor(Date.now()/1000)+3600});
    if(o.data.operation==='commerce.products')return reply(o,{products:[],has_more:false,next_cursor:null});
    if(o.data.operation==='community.storefront'){
      if(hold){held.push(o);return;}
      if(denied)return o.success({statusCode:403,data:{error:'fixture denied'}});
      if(network)return o.fail({errMsg:'fixture unavailable'});
      return storefront(o);
    }
    if(o.data.operation==='customer.directory')return reply(o,{records:[publicStore],categories:[],has_more:false,next_cursor:null,visibility:'CURRENT_AUTHORIZED_PROJECT_TENANT',storefront_photo_supported:false});
    if(o.data.operation==='customer.store'){if(holdPublic){heldPublic.push(o);return;}return reply(o,publicStore);}
    throw Error('UNPLANNED_REQUEST:'+o.data.operation);
  }};
  function page(name='checkout'){
    const filename=path.join(__dirname,'pages',name,'index.js');let definition;
    vm.runInNewContext(fs.readFileSync(filename,'utf8'),{Page:value=>definition=value,require:p=>require(path.resolve(path.dirname(filename),p)),wx,getApp:()=>app,getCurrentPages:()=>[],encodeURIComponent});
    return {...definition,data:structuredClone(definition.data),setData(update,callback){Object.assign(this.data,update);callback?.();}};
  }
  return {app,calls,held,heldPublic,page,get navigation(){return navigation;},deny(){denied=true;},releasePublic(){for(const o of heldPublic.splice(0))reply(o,publicStore);},release(){const waiting=held.splice(0);for(const o of waiting)storefront(o);},async waitHeld(){for(let n=0;n<30&&!held.length;n++)await tick();assert.ok(held.length,'original storefront request was issued');}};
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
test('original WXML keeps current-scene and approved public detail separate with honest failure and payment boundaries',()=>{
  const text=fs.readFileSync(path.join(__dirname,'pages/checkout/index.wxml'),'utf8');
  assert.ok(text.includes("detailState==='READY'&&selectedRecommendation"));assert.ok(text.includes("detailState==='READY'&&sceneStorefront"));
  assert.ok(text.includes('{{sceneStorefront.name}}'));assert.ok(text.includes('{{sceneStorefront.description}}'));assert.ok(text.includes('不代表资质、排名或开通支付'));
  assert.ok(text.includes('店铺资料暂不可用，请返回列表刷新。'));assert.ok(text.includes('虚拟展示，不代表真实已入驻商家，不提供下单或支付。'));
});
