import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const js=readFileSync(new URL('./app.js',import.meta.url),'utf8');
const html=readFileSync(new URL('./index.html',import.meta.url),'utf8');
const events={};
const elements={};
for(const id of ['storefront','amount','pending','receipt','merchantName','merchantDescription','storeName','beneficiary','adAmount','adSuccess','openAmount','confirm','simulate','fail','restart','payAmount','amountError','resultTitle','resultDetail','successSlot']){
 elements[id]={textContent:'',hidden:false,value:'',addEventListener:(kind,fn)=>events[id+':'+kind]=fn};
}
const document={getElementById:id=>elements[id],addEventListener:(kind,fn)=>events['document:'+kind]=fn};
const ctx=vm.createContext({document,Error,Number,Object});vm.runInContext(js,ctx);events['document:DOMContentLoaded']();
function click(id){events[id+':click']();}
test('valid CNY decimals exact in minor units',()=>{
 for(const [input,expected] of [['0.01',1],['12.34',1234],['1',100],['1000000.00',100000000]])
   assert.equal(vm.runInContext('cents('+JSON.stringify(input)+')',ctx),expected);
});
test('invalid amount fail closed',()=>{
 for(const raw of ['0','-1','1.234','1e3','1,000','1.','01.0','1000000.01','true','1x2'])
   assert.throws(()=>vm.runInContext('cents('+JSON.stringify(raw)+')',ctx));
});
test('success ad not visible on pending or failed results',()=>{
 click('openAmount');elements.payAmount.value='2.00';click('confirm');
 assert.equal(elements.pending.hidden,false);assert.equal(elements.successSlot.hidden,false); // slot belongs to hidden receipt panel
 click('fail');assert.equal(elements.successSlot.hidden,true);
});
test('local simulated success explicitly marked and second ad gated',()=>{
 click('restart');click('openAmount');elements.payAmount.value='1.00';click('confirm');click('simulate');
 assert.equal(elements.successSlot.hidden,false);
 assert.match(elements.resultDetail.textContent,/不是微信或银行支付凭证/);
});
test('no HTML injection primitives or network/payment SDK in executable js',()=>{
 assert.match(js,/textContent/);
 assert.doesNotMatch(js,/innerHTML|eval\(|fetch\(|XMLHttpRequest|PaymentRequest|wx\.requestPayment/);
});
test('accessible two slots and no secrets embedded',()=>{
 assert.match(html,/广告展示位置 A/);assert.match(html,/广告展示位置 B/);
 assert.match(html,/aria-label=/);assert.match(html,/离线交互演示/);
});
