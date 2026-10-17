"use strict";
(()=>{
 const get=id=>document.getElementById(id);
 const button=get("loadSplitPreview");
 if(!button)return;
 let serial=0;
 for(const field of ["tenant","merchant","store","reference"])
  get(field).addEventListener("input",()=>{
   serial++;get("splitAmounts").textContent="";get("splitStatus").textContent="尚未计算";
  });
 button.addEventListener("click",async()=>{
  const token=++serial;
  const scope={tenant_id:get("tenant").value,merchant_id:get("merchant").value,
               store_id:get("store").value,reference:get("reference").value};
  get("splitAmounts").textContent="";
  get("splitStatus").textContent="正在计算模拟分账";
  try{
   if(Object.values(scope).some(v=>typeof v!=="string"||!/^[A-Za-z0-9_-]{1,64}$/.test(v)))
    throw Error("范围不合法");
   const response=await fetch("/demo/splits/preview",{method:"POST",headers:{"Content-Type":"application/json"},
     body:JSON.stringify({...scope,shares_bps:{merchant:7000,platform:3000}}),
     credentials:"omit",cache:"no-store",redirect:"error"});
   if(response.status!==200)throw Error("仅支持已完成的模拟订单，且退款预览数据须有效");
   const result=await response.json();
   if(token!==serial)return;
   const expected=["allocations_minor","allocatable_minor","refund_preview_minor","simulation_only",
                   "provider_settlement_verified","provider_split_executed","financial_receipt_issued",
                   "cross_database_atomic_snapshot"];
   if(!result||typeof result!=="object"||Array.isArray(result)||
      Object.keys(result).length!==expected.length||expected.some(k=>!Object.hasOwn(result,k))||
      result.simulation_only!==true||result.provider_settlement_verified!==false||
      result.provider_split_executed!==false||result.financial_receipt_issued!==false||
      result.cross_database_atomic_snapshot!==false||
      !result.allocations_minor||typeof result.allocations_minor!=="object"||
      !Number.isSafeInteger(result.allocatable_minor)||result.allocatable_minor<0||
      !Number.isSafeInteger(result.refund_preview_minor)||result.refund_preview_minor<0||
      !Number.isSafeInteger(result.allocations_minor.merchant)||!Number.isSafeInteger(result.allocations_minor.platform)||
      result.allocations_minor.merchant+result.allocations_minor.platform!==result.allocatable_minor)
       throw Error("模拟分账校验失败");
   get("splitAmounts").textContent="商家："+result.allocations_minor.merchant+"分；平台："+result.allocations_minor.platform+
      "分；退款预览："+result.refund_preview_minor+"分";
   get("splitStatus").textContent="离线分账预览已计算；真实结算未执行";
  }catch(error){
   if(token===serial)get("splitStatus").textContent="计算失败："+error.message;
  }
 });
})();
