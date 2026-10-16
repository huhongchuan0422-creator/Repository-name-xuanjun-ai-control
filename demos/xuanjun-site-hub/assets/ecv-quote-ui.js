"use strict";
(() => {
 const form=document.getElementById('ecvQuote');if(!form)return;
 const en=document.documentElement.lang.startsWith('en');
 const result=document.getElementById('quoteResult');
 const cents=id=>{const raw=document.getElementById(id).value.trim();if(!/^\d+(?:\.\d{1,2})?$/.test(raw))return NaN;const [whole,fraction='']=raw.split('.');const n=BigInt(whole)*100n+BigInt(fraction.padEnd(2,'0'));return n<=BigInt(Number.MAX_SAFE_INTEGER)?Number(n):NaN;};
 form.addEventListener('submit',event=>{
  event.preventDefault();
  try{
   const kind=document.getElementById('serviceKind').value;
   // Internal costs are never collected or disclosed in the public estimator.
   const x=calculateQuote({listPriceCents:cents('listPrice'),ecvUnits:Number(document.getElementById('ecvUnits').value),creditCents:cents('credit'),directCostCents:null,kind});
   const money=n=>(n/100).toFixed(2), cap=kind==='custom'?50:90;
   result.textContent=en?`Pay ${x.discountPercent}% of list price; discounted fee: CNY ${money(x.discountedCents)}; service credit: CNY ${money(x.creditUsedCents)} (cap ${cap}%); estimated amount due: CNY ${money(x.cashDueCents)}; estimate only, not a payment or commission settlement`:`开发折扣：${x.discountPercent/10}折；折后开发费：¥${money(x.discountedCents)}；本次专项抵扣：¥${money(x.creditUsedCents)}（上限${cap}%）；预计实付：¥${money(x.cashDueCents)}；仅为费用估算，不作付款或佣金结算`;
  }catch(_){result.textContent=en?'Enter valid nonnegative amounts with at most two decimal places and whole Yunhui Ecosystem Rights units.':'请输入有效非负金额（最多两位小数）及整数份云汇生态权益。';}
 });
})();
