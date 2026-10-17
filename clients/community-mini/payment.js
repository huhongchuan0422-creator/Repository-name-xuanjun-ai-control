'use strict';
/* Only an explicit payer tap invokes wx.requestPayment. SDK success is no proof. */
function createPaymentFlow(wx,transport) {
 let generation=0,busy=false;
 const referenceOK=ref=>typeof ref==='string'&&/^[A-Za-z0-9_-]{1,64}$/.test(ref);
 const query=async(ref,ticket)=>{
  const r=await transport('query',ref);
  if(ticket!==generation)throw Error('STALE_PAYMENT');
  if(!r||r.reference!==ref||r.provider_signature_verified!==true||r.provider_settlement_verified!==false||
      r.financial_receipt_issued!==false||r.entitlement_granted!==false||r.finance_status!=='UNCONFIRMED'||
      !Number.isSafeInteger(r.amount_minor)||r.amount_minor<1||r.currency!=='CNY'||
      !['SUCCESS','REFUND','NOTPAY','CLOSED','REVOKED','USERPAYING','PAYERROR'].includes(r.provider_state))throw Error('UNTRUSTED_PAYMENT_QUERY');
  return r;
 };
 return {
  reset(){generation++;},
  async query(ref){if(!referenceOK(ref))throw Error('INVALID_REFERENCE');return query(ref,generation);},
  async pay(ref,recover=false){
   if(!referenceOK(ref)||typeof recover!=='boolean')throw Error('INVALID_REFERENCE');
   if(busy)throw Error('PAYMENT_IN_PROGRESS');busy=true;const ticket=generation;
   try {
    const p=await transport(recover?'recover':'prepare',ref);
    if(ticket!==generation)throw Error('STALE_PAYMENT');
    if(!p||typeof p.timeStamp!=='string'||typeof p.nonceStr!=='string'||typeof p.package!=='string'||p.signType!=='RSA'||!/^\d{1,12}$/.test(p.timeStamp)||! /^[A-Za-z0-9_-]{1,128}$/.test(p.nonceStr)||
       !/^prepay_id=[A-Za-z0-9_-]{1,128}$/.test(p.package)||typeof p.paySign!=='string'||
       !/^[A-Za-z0-9+/]+={0,2}$/.test(p.paySign)||p.payment_status!=='AWAITING_PAYER_CONFIRMATION'||
       p.provider_settlement_verified!==false)throw Error('UNTRUSTED_PREPAY');
    await new Promise(resolve=>wx.requestPayment({timeStamp:p.timeStamp,nonceStr:p.nonceStr,package:p.package,
      signType:'RSA',paySign:p.paySign,success:()=>resolve(),fail:()=>resolve()}));
    if(ticket!==generation)throw Error('STALE_PAYMENT');
    // Even cancellation or an SDK timeout can race a completed provider payment.
    return await query(ref,ticket);
   } finally {busy=false;}
  }
 };
}
module.exports={createPaymentFlow};
