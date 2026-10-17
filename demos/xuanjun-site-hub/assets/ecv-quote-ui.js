"use strict";
(() => {
 const form=document.getElementById('ecvQuote');if(!form)return;
 const en=document.documentElement.lang.startsWith('en');
 const result=document.getElementById('quoteResult');
 const holdings=document.getElementById('ecvUnits');
 // Permit valid fractional points even when older HTML specified step=1.
 holdings.step='any';
 const cents=id=>{const raw=document.getElementById(id).value.trim();if(!/^\d+(?:\.\d{1,2})?$/.test(raw))return NaN;const [whole,fraction='']=raw.split('.');const n=BigInt(whole)*100n+BigInt(fraction.padEnd(2,'0'));return n<=BigInt(Number.MAX_SAFE_INTEGER)?Number(n):NaN;};
 form.addEventListener('submit',event=>{
  event.preventDefault();
  try{
   const kind=document.getElementById('serviceKind').value;
   // Internal costs are never collected or disclosed in the public estimator.
   const x=calculateQuote({listPriceCents:cents('listPrice'),ecvUnits:holdings.value.trim(),creditCents:cents('credit'),directCostCents:null,kind});
   const money=n=>(n/100).toFixed(2), cap=kind==='custom'?50:90;
   const fee=en?(kind==='custom'?`Pay ${x.discountPercent}% of the development quote; discounted development fee: CNY ${money(x.discountedCents)}`:`Eligible in-house service fee: CNY ${money(x.discountedCents)}`):(kind==='custom'?`开发折扣：${x.discountPercent/10}折；折后开发费：¥${money(x.discountedCents)}`:`合格自营服务费：¥${money(x.discountedCents)}`);
   result.textContent=fee+(en?`; service credit: CNY ${money(x.creditUsedCents)} (cap ${cap}%); estimated amount due: CNY ${money(x.cashDueCents)}; third-party fees are separate; estimate only, not a payment or commission settlement`:`；本次专项抵扣：¥${money(x.creditUsedCents)}（上限${cap}%）；预计实付：¥${money(x.cashDueCents)}；第三方费用另计；仅为费用估算，不作付款或佣金结算`);
  }catch(_){result.textContent=en?'Enter valid nonnegative amounts with at most two decimal places and nonnegative Yunhui Ecosystem Rights points (decimals allowed).':'请输入有效非负金额（最多两位小数）及非负云汇生态权益点数（可含小数，如10.5点权益值）。';}
 });
})();

