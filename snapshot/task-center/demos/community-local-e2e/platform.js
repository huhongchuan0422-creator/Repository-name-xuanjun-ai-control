"use strict";
const el=id=>document.getElementById(id);
const fields=["tenant","merchant","store","reference"];
let version=0;
function out(id,value){el(id).textContent=String(value);}
function reset(){version++;out("state","—");out("amount","—");out("verified","否");out("status","未核查");out("error","");}
for(const id of fields)el(id).addEventListener("input",reset);
el("inspect").addEventListener("click",async()=>{
 reset();const token=version;
 const scope={tenant_id:el("tenant").value,merchant_id:el("merchant").value,store_id:el("store").value,reference:el("reference").value};
 try{
  if(Object.values(scope).some(v=>typeof v!=="string"||!/^[A-Za-z0-9_-]{1,64}$/.test(v)))throw Error("无效订单范围");
  const response=await fetch("/demo/orders/state",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(scope),credentials:"omit",cache:"no-store",redirect:"error"});
  if(response.status!==200)throw Error("模拟订单不存在或接口不可用");
  const data=await response.json();
  if(!data||typeof data!=="object"||Array.isArray(data)||
     Object.keys(data).sort().join(",")!=="amount_minor,currency,provider_settlement_verified,provider_transaction_id,state"||
     !Number.isSafeInteger(data.amount_minor)||data.amount_minor<1||data.currency!=="CNY"||
     !["PENDING","SUCCESS","FAILED","CANCELLED","REFUNDED"].includes(data.state)||
     data.provider_settlement_verified!==false||
     !(data.provider_transaction_id===null||typeof data.provider_transaction_id==="string"&&/^[A-Za-z0-9_-]{1,64}$/.test(data.provider_transaction_id)))
     throw Error("模拟响应不可信");
  if(token!==version)return;
  out("state",data.state+"（模拟）");out("amount",data.amount_minor);
  out("verified","否");out("status","模拟核查完成");
 }catch(e){if(token!==version)return;out("error",e.message);}
});
