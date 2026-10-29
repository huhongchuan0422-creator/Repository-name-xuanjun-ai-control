import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const html=readFileSync(new URL('../demos/community-stage/communities.html',import.meta.url),'utf8');
const code=readFileSync(new URL('../demos/community-stage/communities.js',import.meta.url),'utf8');
const merchant=(workspace,status='ACTIVE',version=0)=>({workspace,name:workspace,store_status:'ACTIVE',lifecycle:{status,version,reason:'fixture'}});
const result=(records,cursor=null)=>({records,has_more:cursor!==null,next_cursor:cursor});
function setup(responses,reportHook=true){
 const element=()=>({value:'',textContent:'',hidden:false,disabled:false,children:[],append(x){this.children.push(x);},replaceChildren(...x){this.children=x;}});
 const elements=Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>[m[1],element()]));
 elements.platformOrderStatus.value='ALL';
 const calls=[],pending=[],openEvents=[],reportEvents=[],promotionEvents=[],memberEvents=[];
 const stored=new Map();const localStorage={getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value),removeItem:key=>stored.delete(key)};
 const context=vm.createContext({localStorage,document:{getElementById:id=>elements[id],createElement:element},window:{communityMerchantMembersView:value=>memberEvents.push(value),communityPromotionView:value=>promotionEvents.push(value),communityOpenView:value=>openEvents.push(value),communityReportView:value=>reportEvents.push(value)},fetch:async(url,options)=>{
  calls.push({url,options,body:JSON.parse(options.body)});
  const fixture=responses.shift();assert.ok(fixture,'Unexpected fixture request');
  const reply=()=>({ok:!fixture.error,json:async()=>fixture.error?{error:fixture.error}:{result:fixture.result}});
  if(fixture.delay)return new Promise(resolve=>pending.push(()=>resolve(reply())));
  return reply();
 }});
 if(!reportHook)delete context.window.communityReportView;
 vm.runInContext(code,context);
 const configure=context.window.configureCommunityPortal;
 configure({csrf:'token',workspace:'platform'});
 const click=id=>elements[id].onclick();
 return {elements,calls,pending,configure,click,openEvents,reportEvents,promotionEvents,memberEvents,sectionChanged:context.window.communitySectionChanged};
}

const community=(id,state='APPROVED',version=1)=>({id,name:id,state,version,description:'fixture',contact:'private'});

test('platform denied refresh clears prior result and cursor',async()=>{
 const f=setup([{result:result([{secret:'old'}],4)},{error:'ACCESS_DENIED'}]);f.elements.platformView.value='platform_orders';await f.click('readPlatformView');await f.click('readPlatformView');assert.equal(f.elements.platformViewResult.textContent,'');assert.equal(f.elements.morePlatformView.hidden,true);
});
test('platform late response cannot become a different operation or filter',async()=>{
 const f=setup([{result:result([{secret:'old-orders'}],4),delay:true}]);f.elements.platformView.value='platform_orders';const p=f.click('readPlatformView');f.elements.platformView.value='platform_customers';f.elements.platformView.onchange?.();f.pending.shift()();await p;assert.equal(f.elements.platformViewResult.textContent,'');assert.equal(f.elements.morePlatformView.hidden,true);
});
test('merchant state late result cannot overwrite newly selected workspace',async()=>{
 const f=setup([{result:{version:7,status:'PAUSED'},delay:true}]);f.elements.platformMerchantWorkspace.value='old';f.elements.platformMerchantVersion.value='1';f.elements.platformMerchantState.value='PAUSED';const p=f.click('saveMerchantState');f.elements.platformMerchantWorkspace.value='new';f.elements.platformMerchantWorkspace.oninput?.();f.elements.platformMerchantVersion.value='2';f.pending.shift()();await p;assert.equal(f.elements.platformMerchantVersion.value,'2');assert.equal(f.elements.result.textContent,'');
});
test('merchant state denied action clears prior receipt',async()=>{
 const f=setup([{result:{version:7,status:'PAUSED'}},{error:'ACCESS_DENIED'}]);f.elements.platformMerchantWorkspace.value='old';f.elements.platformMerchantVersion.value='1';f.elements.platformMerchantState.value='PAUSED';await f.click('saveMerchantState');await f.click('saveMerchantState');assert.equal(f.elements.result.textContent,'');
});
test('merchant denied next page clears prior private rows and cursor',async()=>{
 const f=setup([{result:result([merchant('old')],'next')},{error:'ACCESS_DENIED'}]);await f.click('platformMerchants');await f.click('moreMerchants');assert.equal(f.elements.merchantRecords.children.length,0);assert.equal(f.elements.moreMerchants.hidden,true);
});
test('retained merchant selector invalid after refresh or refusal',async()=>{
 for(const second of [{result:result([merchant('new')])},{error:'ACCESS_DENIED'}]){
  const f=setup([{result:result([merchant('old')])},second]);await f.click('platformMerchants');const old=f.elements.merchantRecords.children[0].children[0].onclick;await f.click('platformMerchants');f.elements.platformMerchantWorkspace.value='';f.elements.platformMerchantVersion.value='';old();assert.equal(f.elements.platformMerchantWorkspace.value,'');assert.equal(f.elements.platformMerchantVersion.value,'');
 }
});
