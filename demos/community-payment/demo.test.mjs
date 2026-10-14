import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const js=readFileSync(new URL('./app.js',import.meta.url),'utf8');
const html=readFileSync(new URL('./index.html',import.meta.url),'utf8');
const ids=['storefront','amount','pending','receipt','merchantName','merchantDescription','storeName','beneficiary','adAmount','adSuccess','openAmount','confirm','simulate','fail','restart','payAmount','amountError','resultTitle','resultDetail','successSlot'];
function freshDOM(){
 const events={};const elements={};
 for(const id of ids){
   const opening=html.match(new RegExp('<(?:section|aside)\\b[^>]*\\bid="'+id+'"[^>]*>','i'));
   elements[id]={textContent:'',hidden:opening? /(?:^|\\s)hidden(?:\\s|=|>)/i.test(opening[0]):false,value:'',
     addEventListener:(kind,fn)=>{events[id+':'+kind]=fn;}};
 }
 const document={getElementById:id=>elements[id],addEventListener:(kind,fn)=>{events['document:'+kind]=fn;}};
 const ctx=vm.createContext({document,Error,Number,Object});
 vm.runInContext(js,ctx);events['document:DOMContentLoaded']();
 return {elements,ctx,click:id=>events[id+':click'](), visible:id=>!elements[id].hidden && (id!=='successSlot'||!elements.receipt.hidden)};
}
test('valid CNY decimals exact in minor units',()=>{
 const {ctx}=freshDOM();
 for(const [input,expected] of [['0.01',1],['12.34',1234],['1',100],['1000000.00',100000000]])
  assert.equal(vm.runInContext('cents('+JSON.stringify(input)+')',ctx),expected);
});
test('invalid amount fails closed',()=>{
 const {ctx}=freshDOM();
 for(const raw of ['0','-1','1.234','1e3','1,000','1.','01.0','1000000.01','true','1x2'])
  assert.throws(()=>vm.runInContext('cents('+JSON.stringify(raw)+')',ctx));
});
test('initial HTML visibility and pending suppress receipt/success ad',()=>{
 const {elements,click,visible}=freshDOM();
 assert.equal(elements.successSlot.hidden,true);
 assert.equal(visible('successSlot'),false);
 click('openAmount');elements.payAmount.value='2.00';click('confirm');
 assert.equal(elements.pending.hidden,false);
 assert.equal(elements.receipt.hidden,true);
 assert.equal(visible('successSlot'),false);
});
test('failure result hides success ad',()=>{
 const {elements,click,visible}=freshDOM();
 click('openAmount');elements.payAmount.value='2.00';click('confirm');click('fail');
 assert.equal(elements.receipt.hidden,false);
 assert.equal(elements.successSlot.hidden,true);
 assert.equal(visible('successSlot'),false);
});
test('simulated success labeled and success ad displayed',()=>{
 const {elements,click,visible}=freshDOM();
 click('openAmount');elements.payAmount.value='1.00';click('confirm');click('simulate');
 assert.equal(visible('successSlot'),true);
 assert.match(elements.resultDetail.textContent,/不是微信或银行支付凭证/);
});
test('success to restart to pending and failure never leaks prior success ad',()=>{
 const {elements,click,visible}=freshDOM();
 click('openAmount');elements.payAmount.value='3.00';click('confirm');click('simulate');
 assert.equal(visible('successSlot'),true);
 click('restart');
 assert.equal(elements.storefront.hidden,false);
 assert.equal(elements.receipt.hidden,true);
 assert.equal(visible('successSlot'),false);
 click('openAmount');elements.payAmount.value='4.00';click('confirm');
 assert.equal(elements.pending.hidden,false);
 assert.equal(elements.receipt.hidden,true);
 assert.equal(visible('successSlot'),false);
 click('fail');
 assert.equal(elements.receipt.hidden,false);
 assert.equal(elements.successSlot.hidden,true);
 assert.equal(visible('successSlot'),false);
});
test('no HTML injection primitives or network/payment SDK',()=>{
 assert.match(js,/textContent/);
 assert.doesNotMatch(js,/innerHTML|eval\(|fetch\(|XMLHttpRequest|PaymentRequest|wx\.requestPayment/);
});
test('accessible separate advertisement slots and simulation only',()=>{
 assert.match(html,/广告展示位置 A/);assert.match(html,/广告展示位置 B/);
 assert.match(html,/aria-label=/);assert.match(html,/离线交互演示/);
});
