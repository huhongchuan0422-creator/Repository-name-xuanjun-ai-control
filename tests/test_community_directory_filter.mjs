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
 const calls=[],pending=[],openEvents=[],reportEvents=[];
 const stored=new Map();const localStorage={getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value),removeItem:key=>stored.delete(key)};
 const context=vm.createContext({localStorage,document:{getElementById:id=>elements[id],createElement:element},window:{communityOpenView:value=>openEvents.push(value),communityReportView:value=>reportEvents.push(value)},fetch:async(url,options)=>{
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
 return {elements,calls,pending,configure,click,openEvents,reportEvents,sectionChanged:context.window.communitySectionChanged};
}

const community=(id,state='APPROVED',version=1)=>({id,name:id,state,version,description:'fixture',contact:'private'});
test('all original statuses use exact API filter and preserve sparse-page cursor',async()=>{
 const f=setup([{result:result([],'a'.repeat(64))},{result:result([community('co_one')])}]);
 f.elements.directoryStatus.value='APPROVED';await f.click('listDirectory');
 assert.equal(f.elements.more.hidden,false);assert.equal(f.elements.records.children.length,0);
 await f.click('more');assert.deepEqual(f.calls.map(c=>c.body.params),[{after_id:'',status:'APPROVED'},{after_id:'a'.repeat(64),status:'APPROVED'}]);
 for(const status of ['ALL','DRAFT','PENDING','CORRECTION','REJECTED','APPROVED','PAUSED'])assert.ok(html.includes('<option>'+status+'</option>'));
});
test('opening a listed community reads current revision before original review',async()=>{
 const f=setup([{result:result([community('co_one','APPROVED',1)])},{result:community('co_one','APPROVED',8)},{result:community('co_one','PAUSED',9)}]);
 f.elements.directoryStatus.value='APPROVED';await f.click('listDirectory');
 await f.elements.records.children[0].children.find(x=>typeof x.onclick==='function').onclick();
 f.elements.decision.value='PAUSED';f.elements.opinion.value='Pause reason';await f.click('review');
 assert.deepEqual(f.calls.map(c=>c.body.operation),['list','status','review']);
 assert.deepEqual(f.calls[2].body.params,{community_id:'co_one',expected_version:8,decision:'PAUSED',opinion:'Pause reason'});
 assert.match(f.elements.result.textContent,/PAUSED/);
});
test('filter change discards page selection and late success or error',async()=>{
 for(const delayed of [{result:result([community('late')],'b'.repeat(64)),delay:true},{error:'OLD_ERROR',delay:true}]){
  const f=setup([{result:result([community('old')],'a'.repeat(64))},delayed,{result:result([community('new','PAUSED')])}]);
  await f.click('pending');const oldSelect=f.elements.records.children[0].children.find(x=>typeof x.onclick==='function').onclick;
  const pending=f.click('more');f.elements.directoryStatus.value='PAUSED';f.elements.directoryStatus.onchange();
  assert.equal(f.elements.records.children.length,0);assert.equal(f.elements.more.hidden,true);assert.equal(f.elements.reference.value,'');
  f.pending.shift()();await pending;assert.equal(f.elements.records.children.length,0);assert.doesNotMatch(f.elements.message.textContent,/OLD_ERROR|操作完成/);
  await oldSelect();assert.equal(f.calls.length,2);await f.click('listDirectory');assert.equal(f.calls[2].body.params.status,'PAUSED');
 }
});
test('late selected detail cannot restore cleared revision; identity reset clears filter',async()=>{
 const f=setup([{result:result([community('old')])},{result:community('old','APPROVED',8),delay:true},{result:result([])}]);
 await f.click('pending');const pending=f.elements.records.children[0].children.find(x=>typeof x.onclick==='function').onclick();
 f.elements.directoryStatus.value='PAUSED';f.elements.directoryStatus.onchange();f.pending.shift()();await pending;
 assert.equal(f.elements.reference.value,'');await f.click('review');assert.equal(f.calls.length,2);assert.match(f.elements.message.textContent,/先查询当前社区版本/);
 f.configure({csrf:'next',workspace:'next'});assert.equal(f.elements.directoryStatus.value,'ALL');await f.click('pending');
 assert.equal(f.calls[2].body.params.status,'PENDING');assert.equal(f.calls[2].body.workspace,'next');
});
test('server denial is not treated as empty successful directory',async()=>{
 const f=setup([{error:'COMMUNITY_REVIEWER_REQUIRED'}]);await f.click('listDirectory');assert.equal(f.elements.message.textContent,'COMMUNITY_REVIEWER_REQUIRED');assert.equal(f.elements.more.hidden,true);
});

test('unavailable merchant mappings and partial totals are explicit without editable private rows',async()=>{
 const incomplete={records:[],has_more:true,next_cursor:'revoked_050',coverage_complete:false,
  unavailable_mapping_count:61,unavailable_mappings:[{workspace:'revoked_001',status:'UNAVAILABLE'}]};
 const f=setup([{result:incomplete},{result:{coverage_complete:false,totals_scope:'ACCESSIBLE_STORE_SUBTOTAL',signed_gross_payment_minor:101}}]);
 await f.click('platformMerchants');
 assert.match(f.elements.merchantResult.textContent,/覆盖不完整/);
 assert.match(f.elements.merchantRecords.children[0].textContent,/不可用/);
 assert.equal(f.elements.merchantRecords.children[0].children.length,0);
 assert.equal(f.elements.moreMerchants.hidden,false);
 f.elements.platformView.value='platform_overview';await f.click('readPlatformView');
 assert.match(f.elements.platformViewResult.textContent,/可访问门店小计/);
 assert.match(f.elements.platformViewResult.textContent,/不能作为完整总额/);
});

test('submit, save and membership late results cannot restore cleared community context',async()=>{
 for(const operation of ['submit','update','register','join','leave']){
  for(const failed of [false,true]){
   const replies=operation==='register'?[]:[{result:community('old','DRAFT',3)}];
   replies.push(failed?{error:'OLD_MUTATION_ERROR',delay:true}:{result:community('old','PENDING',4),delay:true});
   const f=setup(replies);
   if(operation!=='register'){f.elements.reference.value='old';await f.click('read');}
   f.elements.name.value='Old draft';f.elements.description.value='Old description';f.elements.contact.value='Old contact';f.elements.kind.value='CUSTOMER';
   const pending=['update','register'].includes(operation)?f.elements.profile.onsubmit({preventDefault(){}}):f.click(operation);
   f.elements.directoryStatus.value='PAUSED';f.elements.directoryStatus.onchange();
   f.elements.directoryStatus.value='ALL';f.elements.directoryStatus.onchange();
   f.pending.shift()();await pending;
   for(const id of ['reference','name','description','contact'])assert.equal(f.elements[id].value,'',operation+' '+id);
   assert.equal(f.elements.result.textContent,'');assert.doesNotMatch(f.elements.message.textContent,/OLD_MUTATION_ERROR|操作完成/);
   const count=f.calls.length;await f.click('submit');assert.equal(f.calls.length,count);assert.match(f.elements.message.textContent,/先查询当前社区版本/);
  }
 }
});

test('manually changing selected reference prevents old mutation receipt replacing it',async()=>{
 const f=setup([{result:community('old','DRAFT',3)},{result:community('old','PENDING',4),delay:true}]);
 f.elements.reference.value='old';await f.click('read');const pending=f.click('submit');
 f.elements.reference.value='other';f.pending.shift()();await pending;
 assert.equal(f.elements.reference.value,'other');const count=f.calls.length;await f.click('submit');assert.equal(f.calls.length,count);
});

test('profile mine detail update reread use original APIs and latest version',async()=>{
 const f=setup([{result:result([community('co_one','DRAFT',1)])},{result:community('co_one','DRAFT',7)},{result:community('co_one','DRAFT',8)},{result:community('co_one','DRAFT',8)}]);
 await f.click('mine');await f.elements.records.children[0].children.find(x=>typeof x.onclick==='function').onclick();
 f.elements.name.value='Revised';f.elements.description.value='Original API';f.elements.contact.value='Contact';
 await f.elements.profile.onsubmit({preventDefault(){}});await f.click('read');
 assert.deepEqual(f.calls.map(c=>c.body.operation),['mine','status','update','status']);
 assert.equal(f.calls[2].body.params.expected_version,7);
 assert.equal(f.calls[2].body.params.name,'Revised');
 assert.equal(f.elements.reference.value,'co_one');
});
test('profile denied reread clears private detail and blocks stale update',async()=>{
 const f=setup([{result:community('co_one','DRAFT',7)},{error:'COMMUNITY_PRIVATE'}]);
 f.elements.reference.value='co_one';await f.click('read');await f.click('read');
 assert.equal(f.elements.result.textContent,'');assert.equal(f.elements.contact.value,'');
 await f.elements.profile.onsubmit({preventDefault(){}});assert.equal(f.calls.length,2);assert.match(f.elements.message.textContent,/先回读/);
});

 test('register UNKNOWN persists a guard and cannot POST again after mine or identity reset',async()=>{
 const f=setup([{error:'UNKNOWN'},{result:result([])}]);
 f.elements.name.value='New';f.elements.contact.value='Contact';await f.elements.profile.onsubmit({preventDefault(){}});
 await f.elements.profile.onsubmit({preventDefault(){}});await f.click('mine');f.configure({csrf:'next',workspace:'platform'});
 await f.elements.profile.onsubmit({preventDefault(){}});
 assert.deepEqual(f.calls.map(c=>c.body.operation),['register','mine']);assert.match(f.elements.message.textContent,/对账/);
 });
 test('denied detail removes private list rows and cursor',async()=>{
 const f=setup([{result:result([community('co_one','DRAFT')],'a'.repeat(64))},{error:'COMMUNITY_PRIVATE'}]);
 await f.click('mine');await f.elements.records.children[0].children.find(x=>typeof x.onclick==='function').onclick();
 assert.equal(f.elements.records.children.length,0);assert.equal(f.elements.more.hidden,true);assert.equal(f.elements.result.textContent,'');
 });

 test('open community emits only actual status and clears denied or reset views',async()=>{
 const f=setup([{result:community('co_one','DRAFT',1)},{error:'COMMUNITY_PRIVATE'}]);
 f.elements.reference.value='co_one';await f.click('read');
 const actual=f.openEvents.find(x=>x.type==='status');assert.equal(actual.record.id,'co_one');assert.equal(actual.record.kind,undefined);
 await f.click('read');assert.equal(f.openEvents.at(-1).type,'error');assert.equal(f.elements.records.children.length,0);
 f.configure({csrf:'next',workspace:'other'});assert.equal(f.openEvents.at(-1).type,'reset');
 });
 test('open community late result cannot be displayed after filter or identity change',async()=>{
 const f=setup([{result:community('co_old'),delay:true}]);f.elements.reference.value='co_old';const pending=f.click('read');
 f.elements.directoryStatus.onchange();f.pending.shift()();await pending;
 assert.equal(f.openEvents.filter(x=>x.type==='status').length,0);assert.equal(f.elements.result.textContent,'');
 });

 test('members denial cannot expose prior mine rows or retain pagination',async()=>{
 const f=setup([{result:result([community('co_private')],'a'.repeat(64))},{error:'ACCESS_DENIED'}]);
 await f.click('mine');f.elements.reference.value='co_private';await f.click('members');
 assert.equal(f.elements.records.children.length,0);assert.equal(f.elements.more.hidden,true);assert.equal(f.elements.result.textContent,'');
 });
 test('members late response is discarded when selected reference changes',async()=>{
 for(const inputEvent of [false,true]){
  const f=setup([{result:result([{user_id:'old-member',kind:'CUSTOMER'}]),delay:true}]);
  f.elements.reference.value='co_old';const pending=f.click('members');f.elements.reference.value='co_new';if(inputEvent)f.elements.reference.oninput();
  f.pending.shift()();await pending;assert.equal(f.elements.records.children.length,0);assert.equal(f.elements.more.hidden,true);
 }
 });

 test('section navigation invalidates late shared member results and cursor',async()=>{
 const f=setup([{result:result([{user_id:'old-member',kind:'CUSTOMER'}],'b'.repeat(64)),delay:true}]);
 f.elements.reference.value='co_old';const pending=f.click('members');f.sectionChanged();f.pending.shift()();await pending;
 assert.equal(f.elements.records.children.length,0);assert.equal(f.elements.more.hidden,true);assert.doesNotMatch(f.elements.message.textContent,/操作完成/);
 });

 test('page20 report refresh denial must clear previous private rows and cursor',async()=>{
 const f=setup([{result:result([{reference:'private-order',net_minor:123}], 'a'.repeat(64))},{error:'ACCESS_DENIED'}]);
 f.elements.reference.value='co_one';await f.click('communityEarnings');await f.click('communityEarnings');
 assert.equal(f.elements.records.children.length,0);assert.equal(f.elements.more.hidden,true);assert.equal(f.elements.result.textContent,'');
 });
 test('page20 delayed result must bind the selected community even without input event',async()=>{
 const f=setup([{result:result([{reference:'old-private-order'}]),delay:true}]);
 f.elements.reference.value='co_old';const pending=f.click('communityOrders');f.elements.reference.value='co_new';
 f.pending.shift()();await pending;assert.equal(f.elements.records.children.length,0);
 });

 test('page20 preserves actual page amounts, finance state and same query cursor',async()=>{
 const first={...result([{reference:'order_a',net_minor:123}],'a'.repeat(64)),currency:'CNY',page_gross_minor:150,page_returns_minor:27,page_net_minor:123,totals_scope:'CURRENT_PAGE_ONLY',finance_status:'UNCONFIRMED'};
 const f=setup([{result:first},{result:{...first,records:[],has_more:false,next_cursor:null}}]);f.elements.reference.value='co_one';await f.click('communityEarnings');
 const e=f.reportEvents.find(x=>x.type==='listed');assert.equal(e.record.community_id,'co_one');assert.deepEqual(e.record.result,first);
 await f.click('more');assert.deepEqual(f.calls[1].body.params,{community_id:'co_one',after_id:'a'.repeat(64)});assert.equal(f.elements.more.hidden,true);
 });
 test('page20 permission failure is error rather than fake empty or zero success',async()=>{
 const f=setup([{error:'ACCESS_DENIED'}]);f.elements.reference.value='co_one';await f.click('communityOrders');assert.equal(f.reportEvents.at(-1).type,'error');assert.equal(f.reportEvents.some(x=>x.type==='listed'),false);
 });

 test('page20 receiver bind late success does not describe a different selected community',async()=>{
 const f=setup([{result:{version:7},delay:true}]);f.elements.reference.value='co_old';const pending=f.click('bindReceiver');f.elements.reference.value='co_new';f.elements.reference.oninput();f.pending.shift()();await pending;
 assert.notEqual(f.elements.receiverVersion.value,7);assert.equal(f.reportEvents.some(x=>x.type==='binding'),false);assert.equal(f.elements.result.textContent,'');
 });
 test('page20 bind failure clears old successful receipt and identity reset signals visible filter clear',async()=>{
 const f=setup([{result:{version:7}},{error:'ACCESS_DENIED'}]);f.elements.reference.value='co_one';await f.click('bindReceiver');assert.equal(f.reportEvents.at(-1).type,'binding');await f.click('bindReceiver');assert.equal(f.reportEvents.at(-1).type,'error');assert.equal(f.elements.result.textContent,'');
 f.configure({csrf:'next',workspace:'next'});assert.equal(f.reportEvents.at(-1).type,'identity-reset');
 });

 test('original standalone portal without admin shell retains real order record rows',async()=>{
 const f=setup([{result:result([{reference:'original_order',amount_minor:101,order_state:'PENDING'}])}],false);f.elements.reference.value='co_one';await f.click('communityOrders');
 assert.equal(f.elements.records.children.length,1);assert.match(f.elements.records.children[0].textContent,/original_order.*101分/);
 });
