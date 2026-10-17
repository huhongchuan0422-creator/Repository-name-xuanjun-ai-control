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
 await f.elements.records.children[0].children[0].onclick();
 f.elements.decision.value='PAUSED';f.elements.opinion.value='Pause reason';await f.click('review');
 assert.deepEqual(f.calls.map(c=>c.body.operation),['list','status','review']);
 assert.deepEqual(f.calls[2].body.params,{community_id:'co_one',expected_version:8,decision:'PAUSED',opinion:'Pause reason'});
 assert.match(f.elements.result.textContent,/PAUSED/);
});
test('filter change discards page selection and late success or error',async()=>{
 for(const delayed of [{result:result([community('late')],'b'.repeat(64)),delay:true},{error:'OLD_ERROR',delay:true}]){
  const f=setup([{result:result([community('old')],'a'.repeat(64))},delayed,{result:result([community('new','PAUSED')])}]);
  await f.click('pending');const oldSelect=f.elements.records.children[0].children[0].onclick;
  const pending=f.click('more');f.elements.directoryStatus.value='PAUSED';f.elements.directoryStatus.onchange();
  assert.equal(f.elements.records.children.length,0);assert.equal(f.elements.more.hidden,true);assert.equal(f.elements.reference.value,'');
  f.pending.shift()();await pending;assert.equal(f.elements.records.children.length,0);assert.doesNotMatch(f.elements.message.textContent,/OLD_ERROR|操作完成/);
  await oldSelect();assert.equal(f.calls.length,2);await f.click('listDirectory');assert.equal(f.calls[2].body.params.status,'PAUSED');
 }
});
test('late selected detail cannot restore cleared revision; identity reset clears filter',async()=>{
 const f=setup([{result:result([community('old')])},{result:community('old','APPROVED',8),delay:true},{result:result([])}]);
 await f.click('pending');const pending=f.elements.records.children[0].children[0].onclick();
 f.elements.directoryStatus.value='PAUSED';f.elements.directoryStatus.onchange();f.pending.shift()();await pending;
 assert.equal(f.elements.reference.value,'');await f.click('review');assert.equal(f.calls.length,2);assert.match(f.elements.message.textContent,/先查询当前社区版本/);
 f.configure({csrf:'next',workspace:'next'});assert.equal(f.elements.directoryStatus.value,'ALL');await f.click('pending');
 assert.equal(f.calls[2].body.params.status,'PENDING');assert.equal(f.calls[2].body.workspace,'next');
});
test('server denial is not treated as empty successful directory',async()=>{
 const f=setup([{error:'COMMUNITY_REVIEWER_REQUIRED'}]);await f.click('listDirectory');assert.equal(f.elements.message.textContent,'COMMUNITY_REVIEWER_REQUIRED');assert.equal(f.elements.more.hidden,true);
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
