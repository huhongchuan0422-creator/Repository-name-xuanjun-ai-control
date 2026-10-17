'use strict';
(()=>{
 const $=id=>document.getElementById(id);let generation=0,context='mini';
 const reset=()=>{generation++;$('after').textContent='';$('before').textContent='';$('merchant').textContent='';$('state').textContent='';$('output').textContent='';};
 for(const id of ['token','reference','amount'])$(id).addEventListener('input',reset);
 const call=async(operation,params={})=>{
  const response=await fetch('/offline/saas',{method:'POST',headers:{'Content-Type':'application/json','X-Offline-Token':$('token').value},body:JSON.stringify({operation,params,at:0}),credentials:'omit',cache:'no-store',redirect:'error'});
  if(response.status!==200)throw Error('请求被拒绝或数据不可用');
  const value=await response.json();if(value.offline_only!==true||!value.result)throw Error('响应不可信');return value.result;
 };
 const bind=(id,operation)=>$(id).addEventListener('click',async()=>{
  const ticket=++generation;$('output').textContent='';try{const result=await call(operation);if(ticket===generation)$('output').textContent=JSON.stringify(result,null,2);}catch(e){if(ticket===generation)$('state').textContent=e.message;}
 });
 for(const [id,op]of Object.entries({orders:'community.orders',ads:'community.ads',reconciliation:'community.reconciliation',catalog:'catalog',customerOrders:'customer_orders',health:'health_detail'}))bind(id,op);
 for(const button of document.querySelectorAll('[data-view]'))button.addEventListener('click',async()=>{
  reset();const ticket=generation;context=button.dataset.view==='h5'?'official_h5':'mini';$('view').textContent=button.textContent;
  try{const s=await call('community.storefront');if(ticket!==generation)return;$('merchant').textContent=s.merchant.name;$('before').textContent=s.ads.AD_SLOT_PAYMENT_AMOUNT?s.ads.AD_SLOT_PAYMENT_AMOUNT.title:'';}catch(e){if(ticket===generation)$('state').textContent=e.message;}
 });
 $('checkout').addEventListener('click',async()=>{
  const ticket=++generation;$('after').textContent='';
  try{
   const reference=$('reference').value,raw=$('amount').value;
   if(!/^[A-Za-z0-9_-]{1,64}$/.test(reference)||!/^[1-9][0-9]{0,8}$/.test(raw)||Number(raw)>100000000)throw Error('金额或订单编号无效');
   const {token}=await call('community.qr',{context});if(ticket!==generation)return;
   const r=await call('community.checkout',{context,token,reference,amount_minor:Number(raw)});if(ticket!==generation)return;
   if(r.state!=='PENDING'||r.provider_payment_started!==false||r.provider_settlement_verified!==false)throw Error('订单状态不可信');
   $('state').textContent='模拟待支付；未发起微信扣款';
  }catch(e){if(ticket===generation)$('state').textContent=e.message;}
 });
 $('receipt').addEventListener('click',async()=>{
  const ticket=++generation;$('after').textContent='';
  try{const r=await call('community.receipt',{reference:$('reference').value});if(ticket!==generation)return;
   if(r.simulation_only!==true||r.provider_settlement_verified!==false||r.financial_receipt_issued!==false||r.finance_effect!=='NONE')throw Error('收据状态不可信');
   const ad=r.ads.AD_SLOT_PAYMENT_SUCCESS;
   if(ad&&(r.payment_state!=='MOCK_PAID_SIMULATED'||r.order.state!=='SUCCESS'))throw Error('成功广告状态不可信');
   $('state').textContent=r.payment_state+'（模拟）';$('after').textContent=ad?ad.title:'';
  }catch(e){if(ticket===generation)$('state').textContent=e.message;}
 });
})();
