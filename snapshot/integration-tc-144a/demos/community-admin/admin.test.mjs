import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const code=readFileSync(new URL('./admin.js',import.meta.url),'utf8');
function setup(role='MERCHANT_ADMIN'){
 const elements={},events={};
 for(const id of ['role','notice','merchant','platform','orders','ads','merchantButton','platformButton','merchantApproval','splitApproval','platformResult'])
  elements[id]={value:id==='role'?role:'',hidden:id==='platform',textContent:'',children:[],addEventListener:(key,fn)=>{events[id+':'+key]=fn;},replaceChildren(){this.children=[];},appendChild(node){this.children.push(node);}};
 const document={getElementById:id=>elements[id],addEventListener:(key,fn)=>{events['document:'+key]=fn;},createElement:()=>({children:[],appendChild(x){this.children.push(x);},textContent:''})};
 const ctx=vm.createContext({document,Object,String});vm.runInContext(code,ctx);events['document:DOMContentLoaded']();
 return {elements,click:id=>events[id+':click'](),switchRole:role=>{elements.role.value=role;events['role:change']();}};
}
test('merchant admin views own orders and advertisements',()=>{
 const {elements}=setup();assert.equal(elements.merchant.hidden,false);assert.equal(elements.orders.children.length,2);assert.equal(elements.ads.children.length,2);
});
test('staff can read merchant orders but not manage ads',()=>{
 const {elements}=setup('STORE_STAFF');assert.equal(elements.orders.children.length,2);assert.equal(elements.ads.children.length,0);
});
test('merchant actor denied platform dashboard and approvals',()=>{
 const {elements,click}=setup();click('platformButton');assert.equal(elements.platform.hidden,true);assert.match(elements.notice.textContent,/无权/);
});
test('platform reviewer cannot approve finance splits',()=>{
 const {elements,click}=setup('PLATFORM_REVIEWER');click('platformButton');click('splitApproval');assert.match(elements.platformResult.textContent,/拒绝/);
 click('merchantApproval');assert.match(elements.platformResult.textContent,/未发生实际审批/);
});
test('finance approver cannot approve merchant admission',()=>{
 const {elements,click}=setup('FINANCE_APPROVER');click('platformButton');click('merchantApproval');assert.match(elements.platformResult.textContent,/拒绝/);
 click('splitApproval');assert.match(elements.platformResult.textContent,/未发生实际审批/);
});
test('role switch hides previous dashboard',()=>{
 const {elements,switchRole,click}=setup();switchRole('PLATFORM_REVIEWER');assert.equal(elements.merchant.hidden,true);click('platformButton');assert.equal(elements.platform.hidden,false);
});
test('no direct network, dynamic html, payments or real approval',()=>{
 assert.doesNotMatch(code,/innerHTML|eval\(|fetch\(|XMLHttpRequest|wx\.requestPayment/);
});
