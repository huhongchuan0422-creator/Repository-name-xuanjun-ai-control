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
 const recordButton=el("recordRefundPreview");
 if(recordButton)recordButton.addEventListener("click",async()=>{
  const seq=++version;
  el("refundPreviewAmounts").textContent="";
  el("refundPreviewStatus").textContent="登记本地退款预览中（不执行渠道退款）";
  const ids=["tenant","merchant","store","reference"];
  const values=ids.map(id=>el(id).value);
  const raw=el("refundPreviewValue").value;
  try{
   if(values.some(value=>! /^[A-Za-z0-9_-]{1,64}$/.test(value))||
      !/^[1-9][0-9]{0,8}$/.test(raw)||Number(raw)>100000000)throw Error("预览输入无效");
   const payload={tenant_id:values[0],merchant_id:values[1],store_id:values[2],reference:values[3],
      event_id:"preview_"+crypto.randomUUID().replace(/-/g,""),amount_minor:Number(raw)};
   const response=await fetch("/demo/refunds/record-preview",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(payload),cache:"no-store",credentials:"omit",redirect:"error"});
   if(response.status!==200)throw Error("仅已模拟成功且余额足够的订单允许预览");
   const result=await response.json();
   if(seq!==version||ids.some((id,i)=>el(id).value!==values[i]))return;
   if(!result||typeof result!=="object"||Object.keys(result).length!==5||
      typeof result.recorded!=="boolean"||!Number.isSafeInteger(result.preview_total_minor)||
      result.provider_refund_executed!==false||result.financial_receipt_issued!==false||
      result.simulation_only!==true)throw Error("预览写入证据不可信");
   el("refundPreviewAmounts").textContent="已累计登记 "+result.preview_total_minor+"分（离线预览，不是真实退款）";
   el("refundPreviewStatus").textContent="仅追加模拟预览账本；渠道退款未执行";
  }catch(error){
   if(seq===version)el("refundPreviewStatus").textContent="预览登记失败："+error.message;
  }
 });

})();
