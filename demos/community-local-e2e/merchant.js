"use strict";
const el=id=>document.getElementById(id);
const fields=["tenant","merchant","store","reference"];
let requestVersion=0;
const text=(id,value)=>{el(id).textContent=String(value);};
function clear(){
 requestVersion++;
 for(const id of ["amount","currency","state","transaction"])text(id,"—");
 text("verified","否");text("status","尚未查询");text("error","");
}
for(const id of fields)el(id).addEventListener("input",clear);
el("load").addEventListener("click",async()=>{
 const token=++requestVersion;
 clear(); // A new query must not display a prior order while awaiting response.
 const current=requestVersion, scope={
  tenant_id:el("tenant").value,merchant_id:el("merchant").value,
  store_id:el("store").value,reference:el("reference").value
 };
 try{
  if(Object.values(scope).some(x=>typeof x!=="string"||!/^[A-Za-z0-9_-]{1,64}$/.test(x)))throw Error("订单范围格式不正确");
  const result=await fetch("/demo/orders/state",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(scope),credentials:"omit",redirect:"error",cache:"no-store"});
  if(result.status!==200)throw Error("订单不可用");
  const data=await result.json();
  if(data===null||typeof data!=="object"||Array.isArray(data)||
    Object.keys(data).sort().join(",")!=="amount_minor,currency,provider_settlement_verified,provider_transaction_id,state"||
    !Number.isSafeInteger(data.amount_minor)||data.amount_minor<1||
    data.currency!=="CNY"||!["PENDING","SUCCESS","FAILED","CANCELLED","REFUNDED"].includes(data.state)||
    data.provider_settlement_verified!==false||
    !(data.provider_transaction_id===null||typeof data.provider_transaction_id==="string"&&/^[A-Za-z0-9_-]{1,64}$/.test(data.provider_transaction_id)))
    throw Error("模拟订单响应不可信");
  if(current!==requestVersion)return;
  text("amount",data.amount_minor);text("currency",data.currency);
  text("state",data.state+"（仅模拟）");
  text("transaction",data.provider_transaction_id||"—");
  text("verified","否");
  text("status","当前模拟订单已读取");
 }catch(e){if(current!==requestVersion)return;text("error",e.message);}
});
