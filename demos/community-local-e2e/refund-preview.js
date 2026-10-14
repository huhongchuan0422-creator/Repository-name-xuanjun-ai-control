"use strict";
(()=>{
 const el=id=>document.getElementById(id),button=el("loadRefundPreview");
 if(!button)return;
 let version=0;
 for(const field of ["tenant","merchant","store","reference"])el(field).addEventListener("input",()=>{
  version++;
  el("refundPreviewStatus").textContent="尚未读取";
  el("refundPreviewAmounts").textContent="";
 });
 button.addEventListener("click",async()=>{
  const seq=++version;
  el("refundPreviewAmounts").textContent="";
  el("refundPreviewStatus").textContent="读取本地退款预览中";
  const ids=["tenant","merchant","store","reference"];
  const values=ids.map(id=>el(id).value);
  const payload={tenant_id:values[0],merchant_id:values[1],store_id:values[2],reference:values[3]};
  try{
   if(values.some(v=>! /^[A-Za-z0-9_-]{1,64}$/.test(v)))throw Error("订单范围格式不正确");
   const response=await fetch("/demo/refunds/preview",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload),cache:"no-store",credentials:"omit",redirect:"error"});
   if(response.status!==200)throw Error("模拟退款数据不可用");
   const result=await response.json();
   if(seq!==version||ids.some((id,i)=>el(id).value!==values[i]))return;
   const required=["reference","order_state","order_amount_minor","preview_total_minor","remaining_preview_minor","provider_refund_executed","provider_settlement_verified","simulation_only","financial_receipt_issued"];
   if(!result||typeof result!=="object"||Array.isArray(result)||Object.keys(result).length!==required.length||required.some(key=>!Object.hasOwn(result,key))||
      result.reference!==payload.reference||result.simulation_only!==true||result.provider_refund_executed!==false||
      result.provider_settlement_verified!==false||result.financial_receipt_issued!==false||
      !["PENDING","SUCCESS","FAILED","CANCELLED","REFUNDED"].includes(result.order_state)||
      !Number.isSafeInteger(result.order_amount_minor)||result.order_amount_minor<1||
      !Number.isSafeInteger(result.preview_total_minor)||result.preview_total_minor<0||
      result.preview_total_minor>result.order_amount_minor||
      result.remaining_preview_minor!==result.order_amount_minor-result.preview_total_minor)throw Error("退款预览合同校验失败");
   el("refundPreviewAmounts").textContent="订单 "+result.order_amount_minor+"分；预览退款 "+result.preview_total_minor+"分；余量 "+result.remaining_preview_minor+"分（均为模拟）";
   el("refundPreviewStatus").textContent="已读取只读预览；真实退款未执行";
  }catch(error){
   if(seq!==version)return;
   el("refundPreviewStatus").textContent="读取失败："+error.message;
  }
 });
})();
