"use strict";
(()=>{
 const get=id=>document.getElementById(id),button=get("loadReconciliation");
 if(!button)return;
 const fields=["tenant","merchant","store"];
 let ticket=0;
 for(const f of fields)get(f).addEventListener("input",()=>{
  ticket++;get("reconciliationAmounts").textContent="";
  get("reconciliationStatus").textContent="尚未读取";
 });
 button.addEventListener("click",async()=>{
  const current=++ticket;
  get("reconciliationAmounts").textContent="";
  get("reconciliationStatus").textContent="正在读取离线模拟对账";
  const scope={tenant_id:get("tenant").value,merchant_id:get("merchant").value,store_id:get("store").value};
  try{
   if(Object.values(scope).some(v=>typeof v!=="string"||!/^[A-Za-z0-9_-]{1,64}$/.test(v)))throw Error("范围无效");
   const response=await fetch("/demo/reconciliation/preview",{method:"POST",headers:{"Content-Type":"application/json"},
       body:JSON.stringify(scope),credentials:"omit",cache:"no-store",redirect:"error"});
   if(response.status!==200)throw Error("模拟对账资料不可用或不完整");
   const data=await response.json();
   if(current!==ticket||fields.some((f,i)=>get(f).value!==Object.values(scope)[i]))return;
   const allowed=["simulated_success_order_count","simulated_success_total_minor",
    "refund_preview_total_minor","simulated_net_minor","provider_settlement_minor",
    "provider_reconciliation_status","cross_database_atomic_snapshot",
    "simulation_only","financial_receipt_issued"];
   if(!data||typeof data!=="object"||Array.isArray(data)||Object.keys(data).length!==allowed.length||
      allowed.some(k=>!Object.hasOwn(data,k))||
      data.simulation_only!==true||data.financial_receipt_issued!==false||
      data.cross_database_atomic_snapshot!==false||data.provider_settlement_minor!==null||
      data.provider_reconciliation_status!=="UNKNOWN"||
      !Number.isSafeInteger(data.simulated_success_order_count)||data.simulated_success_order_count<0||
      !Number.isSafeInteger(data.simulated_success_total_minor)||data.simulated_success_total_minor<0||
      !Number.isSafeInteger(data.refund_preview_total_minor)||data.refund_preview_total_minor<0||
      data.simulated_net_minor!==data.simulated_success_total_minor-data.refund_preview_total_minor)
     throw Error("对账数据违反离线合同");
   get("reconciliationAmounts").textContent="模拟SUCCESS订单："+data.simulated_success_order_count+
     "；模拟订单总额："+data.simulated_success_total_minor+
     "分；退款预览："+data.refund_preview_total_minor+
     "分；模拟净额："+data.simulated_net_minor+
     "分；渠道实收：UNKNOWN";
   get("reconciliationStatus").textContent="离线对账预览完成，真实渠道对账UNKNOWN";
  }catch(error){
   if(current===ticket)get("reconciliationStatus").textContent="对账预览拒绝："+error.message;
  }
 });
})();
