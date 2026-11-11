"use strict";
(()=>{
 const get=id=>document.getElementById(id),btn=get("listOrders");
 if(!btn)return;
 let serial=0;
 function reset(){serial++;get("orderList").textContent="";get("listStatus").textContent="尚未读取";}
 for(const id of ["tenant","merchant","store"])get(id).addEventListener("input",reset);
 btn.addEventListener("click",async()=>{
  const seq=++serial;
  get("orderList").textContent="";get("listStatus").textContent="查询本地订单中";
  const id={tenant_id:get("tenant").value,merchant_id:get("merchant").value,store_id:get("store").value};
  try{
   if(Object.values(id).some(v=>typeof v!=="string"||! /^[A-Za-z0-9_-]{1,64}$/.test(v)))throw Error("范围无效");
   const response=await fetch("/demo/orders/list",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(id),credentials:"omit",cache:"no-store",redirect:"error"});
   if(response.status!==200)throw Error("订单读取失败");
   const result=await response.json();
   if(seq!==serial)return;
   if(result.simulation_only!==true||result.provider_settlement_verified!==false||!Array.isArray(result.orders)||result.orders.length>50)throw Error("模拟数据验证失败");
   for(const row of result.orders){
    if(!row||typeof row.reference!=="string"||! /^[A-Za-z0-9_-]{1,64}$/.test(row.reference)||
       !Number.isSafeInteger(row.amount_minor)||row.amount_minor<1||row.currency!=="CNY"||
       !["PENDING","SUCCESS","FAILED","CANCELLED","REFUNDED"].includes(row.state))throw Error("订单字段不可信");
   }
   get("orderList").textContent=result.orders.map(row=>row.reference+" · "+row.amount_minor+"分 · "+row.state+"（模拟）").join("\n");
   get("listStatus").textContent="已读取 "+result.orders.length+" 条本地模拟订单";
  }catch(err){if(seq===serial)get("listStatus").textContent="读取失败："+err.message;}
 });
})();
