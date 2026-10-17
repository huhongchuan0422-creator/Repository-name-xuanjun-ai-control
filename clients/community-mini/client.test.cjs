const {test}=require('node:test');
const assert=require('node:assert/strict');
const {makeClient}=require('./client');
function fixture(transform=x=>x) {
 const calls=[];
 const transport=async body=>{
  calls.push(body);
  let result;
  if(body.operation==='community.qr')result={token:{payload:{},signature:'signed'}};
  else if(body.operation==='community.checkout')result={reference:'order1',state:'PENDING',provider_payment_started:false,provider_settlement_verified:false};
  else result={simulation_only:true,provider_settlement_verified:false,financial_receipt_issued:false,finance_effect:'NONE',
   order:{reference:'order1',state:'SUCCESS',provider_settlement_verified:false},payment_state:'MOCK_PAID_SIMULATED',ads:{AD_SLOT_PAYMENT_SUCCESS:{title:'模拟广告'}}};
  return {offline_only:true,result:transform(result)};
 };
 return {client:makeClient(transport),calls};
}
test('QR -> original pending order -> explicitly simulated receipt',async()=>{
 const {client,calls}=fixture();await client.checkout('101','order1');
 assert.equal((await client.receipt()).payment_state,'MOCK_PAID_SIMULATED');
 assert.deepEqual(calls.map(x=>x.operation),['community.qr','community.checkout','community.receipt']);
 assert.ok(calls.every(x=>!('tenant_id' in x.params)&&!('paid' in x.params)));
});
test('amount validation happens before any request',async()=>{
 const {client,calls}=fixture();
 for(const a of ['0','-1','1.2','1e2','100000001',' 10'])await assert.rejects(client.checkout(a,'order1'));
 assert.equal(calls.length,0);
});
test('client never accepts verified real receipt',async()=>{
 const {client}=fixture(r=>r.order?{...r,provider_settlement_verified:true}:r);
 await client.checkout('101','order1');await assert.rejects(client.receipt(),/UNTRUSTED_RECEIPT/);
});
test('success creative rejected on pending server order',async()=>{
 const {client}=fixture(r=>r.order?{...r,order:{...r.order,state:'PENDING'}}:r);
 await client.checkout('101','order1');await assert.rejects(client.receipt(),/UNTRUSTED_SUCCESS_AD/);
});
test('reset clears receipt and rejects late async checkout',async()=>{
 let resume; const client=makeClient(()=>new Promise(r=>{resume=r;}));
 const pending=client.checkout('101','order1');client.reset();resume({offline_only:true,result:{token:{}}});
 await assert.rejects(pending,/STALE_CHECKOUT/);await assert.rejects(client.receipt(),/CHECKOUT_REQUIRED/);
});
test('cannot poll before creating an order',async()=>{
 await assert.rejects(fixture().client.receipt(),/CHECKOUT_REQUIRED/);
});
