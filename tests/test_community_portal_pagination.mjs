import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const html=readFileSync(new URL('../demos/community-stage/communities.html',import.meta.url),'utf8');
const code=readFileSync(new URL('../demos/community-stage/communities.js',import.meta.url),'utf8');
const merchant=(workspace,status='ACTIVE',version=0)=>({workspace,name:workspace,store_status:'ACTIVE',lifecycle:{status,version,reason:'fixture'}});
const result=(records,cursor=null)=>({records,has_more:cursor!==null,next_cursor:cursor});
function setup(responses){
 const element=()=>({value:'',textContent:'',hidden:false,disabled:false,children:[],append(x){this.children.push(x);},replaceChildren(...x){this.children=x;}});
 const elements=Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>[m[1],element()]));
 elements.platformOrderStatus.value='ALL';
 const calls=[],pending=[];
 const context=vm.createContext({document:{getElementById:id=>elements[id],createElement:element},window:{},fetch:async(url,options)=>{
  calls.push({url,options,body:JSON.parse(options.body)});
  const fixture=responses.shift();assert.ok(fixture,'Unexpected fixture request');
  const reply=()=>({ok:!fixture.error,json:async()=>fixture.error?{error:fixture.error}:{result:fixture.result}});
  if(fixture.delay)return new Promise(resolve=>pending.push(()=>resolve(reply())));
  return reply();
 }});
 vm.runInContext(code,context);
 const configure=context.window.configureCommunityPortal;
 configure({csrf:'token',workspace:'platform'});
 const click=id=>elements[id].onclick();
 return {elements,calls,pending,configure,click};
}

test('real HTML contains unique pagination targets',()=>{
 const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);
 assert.equal(new Set(ids).size,ids.length);
 for(const id of ['merchantRecords','merchantResult','moreMerchants'])assert.ok(ids.includes(id));
});

test('50-row first page, next page, row selection and refresh use merchant cursor',async()=>{
 const first=Array.from({length:50},(_,i)=>merchant(`merchant-${String(i).padStart(2,'0')}`));
 const f=setup([{result:result(first,'merchant-49')},{result:result([merchant('merchant-50','PAUSED',7)])},{result:result([])}]);
 await f.click('platformMerchants');assert.equal(f.elements.merchantRecords.children.length,50);assert.equal(f.elements.moreMerchants.hidden,false);
 await f.click('moreMerchants');assert.equal(f.elements.merchantRecords.children.length,1);assert.equal(f.elements.moreMerchants.hidden,true);
 f.elements.merchantRecords.children[0].children[0].onclick();
 assert.equal(f.elements.platformMerchantWorkspace.value,'merchant-50');assert.equal(f.elements.platformMerchantVersion.value,7);assert.equal(f.elements.platformMerchantState.value,'PAUSED');
 await f.click('platformMerchants');assert.equal(f.elements.merchantRecords.children.length,0);assert.equal(f.elements.merchantResult.textContent,'暂无已准入商家');
 assert.deepEqual(f.calls.map(c=>c.body.params),[{after_workspace:''},{after_workspace:'merchant-49'},{after_workspace:''}]);
 for(const c of f.calls){assert.equal(c.url,'/community/directory');assert.equal(c.options.credentials,'same-origin');assert.equal(c.options.redirect,'error');assert.equal(c.options.cache,'no-store');assert.equal(c.options.headers['X-CSRF-Token'],'token');assert.equal(c.body.workspace,'platform');assert.equal(c.body.operation,'platform_merchants');}
});

test('community, platform operations and merchant paginators remain independent',async()=>{
 const f=setup([{result:result([merchant('a')],'a')},{result:result([{id:'c',name:'community'}],'c')},{result:result([{id:4}],4)},{result:result([merchant('b')])},{result:result([])},{result:result([])}]);
 await f.click('platformMerchants');await f.click('mine');f.elements.platformView.value='platform_orders';await f.click('readPlatformView');await f.click('moreMerchants');
 assert.equal(f.elements.more.hidden,false);assert.equal(f.elements.morePlatformView.hidden,false);const card=f.elements.records.children[0];assert.equal(card.children[0].textContent,'记录列表 · 当前范围');
 const fields=card.children[1].children.map(x=>x.textContent);assert.deepEqual(fields,['社区名称','community','社区介绍','当前权限未返回该字段','联系人及联系方式','当前权限未返回该字段','状态','当前权限未返回该字段']);assert.equal(card.children[2].textContent,'查看详情');
 await f.click('more');await f.click('morePlatformView');
 assert.deepEqual(f.calls.map(c=>[c.body.operation,c.body.params]),[['platform_merchants',{after_workspace:''}],['mine',{}],['platform_orders',{after_id:0,status:'ALL'}],['platform_merchants',{after_workspace:'a'}],['mine',{after_id:'c'}],['platform_orders',{after_id:4,status:'ALL'}]]);
});

test('identity reset clears private rows and fields and late old response cannot repopulate',async()=>{
 const f=setup([{result:result([merchant('old','PAUSED',3)],'old')},{result:result([merchant('late')],'late'),delay:true},{result:result([merchant('new')])}]);
 await f.click('platformMerchants');const oldSelect=f.elements.merchantRecords.children[0].children[0].onclick;oldSelect();
 const oldRequest=f.click('moreMerchants');assert.equal(f.pending.length,1);
 f.configure({csrf:'new-token',workspace:'new-platform'});
 assert.equal(f.elements.merchantRecords.children.length,0);assert.equal(f.elements.merchantResult.textContent,'');assert.equal(f.elements.moreMerchants.hidden,true);
 for(const id of ['platformMerchantWorkspace','platformMerchantVersion','platformMerchantReason'])assert.equal(f.elements[id].value,'');
 assert.equal(f.elements.platformMerchantState.value,'ACTIVE');
 await f.click('platformMerchants');f.pending.shift()();await oldRequest;
 assert.match(f.elements.merchantRecords.children[0].textContent,/new/);assert.doesNotMatch(f.elements.merchantResult.textContent,/old|late/);assert.equal(f.elements.moreMerchants.hidden,true);
 oldSelect();assert.equal(f.elements.platformMerchantWorkspace.value,'');
 assert.equal(f.calls[2].body.workspace,'new-platform');assert.equal(f.calls[2].options.headers['X-CSRF-Token'],'new-token');assert.deepEqual(f.calls[2].body.params,{after_workspace:''});
 f.configure(null);await f.click('platformMerchants');assert.equal(f.elements.message.textContent,'需要客户中心登录');assert.equal(f.calls.length,3);
});

test('repeated pending clicks do not fetch twice; failed next page retains retry cursor',async()=>{
 const f=setup([{result:result([merchant('a')],'a')},{error:'TEMPORARY_UNAVAILABLE',delay:true},{result:result([merchant('b')])}]);
 await f.click('platformMerchants');const oldSelect=f.elements.merchantRecords.children[0].children[0].onclick;oldSelect();const request=f.click('moreMerchants');assert.equal(f.elements.moreMerchants.disabled,true);
 await f.click('moreMerchants');await f.click('platformMerchants');assert.equal(f.calls.length,2);
 f.pending.shift()();await request;assert.equal(f.elements.message.textContent,'TEMPORARY_UNAVAILABLE');assert.equal(f.elements.moreMerchants.disabled,false);assert.equal(f.elements.moreMerchants.hidden,false);
 assert.match(f.elements.merchantRecords.children[0].textContent,/a/);for(const id of ['platformMerchantWorkspace','platformMerchantVersion','platformMerchantReason'])assert.equal(f.elements[id].value,'');oldSelect();assert.equal(f.elements.platformMerchantWorkspace.value,'');
 await f.click('moreMerchants');assert.deepEqual(f.calls[2].body.params,{after_workspace:'a'});assert.match(f.elements.merchantRecords.children[0].textContent,/b/);
});

test('denied refresh discards previous rows and pagination',async()=>{
 const f=setup([{result:result([merchant('a')],'a')},{error:'PLATFORM_MERCHANT_OPERATOR_REQUIRED'}]);
 await f.click('platformMerchants');await f.click('platformMerchants');assert.equal(f.elements.message.textContent,'PLATFORM_MERCHANT_OPERATOR_REQUIRED');assert.equal(f.elements.merchantRecords.children.length,0);assert.equal(f.elements.moreMerchants.hidden,true);assert.equal(f.elements.platformMerchants.disabled,false);
});

test('empty or non-progressing cursor never offers another page; names are text only',async()=>{
 const f=setup([{result:result([merchant('<img src=x onerror=alert(1)>')],'')},{result:result([merchant('a')],'a')},{result:result([merchant('a')],'a')}]);
 await f.click('platformMerchants');assert.equal(f.elements.moreMerchants.hidden,true);assert.match(f.elements.merchantRecords.children[0].textContent,/<img/);assert.equal(f.elements.merchantRecords.children[0].children.length,1);
 await f.click('platformMerchants');assert.equal(f.elements.moreMerchants.hidden,false);await f.click('moreMerchants');assert.equal(f.elements.moreMerchants.hidden,true);
});
