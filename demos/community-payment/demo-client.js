"use strict";
/* Explicit opt-in loopback SIMULATION ONLY. Never point at real payment systems. */
const BASE="http://127.0.0.1:18791";
const ROUTES=Object.freeze({create:"/demo/orders",state:"/demo/orders/state",simulate:"/demo/orders/simulate"});
const ID=/^[A-Za-z0-9_-]{1,64}$/;
function validateScope(scope){
 if(!scope||Object.keys(scope).sort().join()!=="merchant_id,store_id,tenant_id"||
    Object.values(scope).some(v=>typeof v!=="string"||!ID.test(v)))throw Error("INVALID_SCOPE");
 return {...scope};
}
function validateAmount(value){if(!Number.isSafeInteger(value)||value<1||value>100000000)throw Error("INVALID_AMOUNT");return value;}
function id(v){if(typeof v!=="string"||!ID.test(v))throw Error("INVALID_ID");return v;}
function makeDemoClient(transport){
 if(typeof transport!=="function")throw Error("TRANSPORT_REQUIRED");
 async function post(kind,body){
  const path=ROUTES[kind];if(!path)throw Error("INVALID_ROUTE");
  const response=await transport(BASE+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body),redirect:"error",credentials:"omit",cache:"no-store"});
  if(!response||response.status!==200)throw Error("DEMO_REQUEST_FAILED");
  const data=await response.json();
  if(!data||typeof data!=="object"||Array.isArray(data))throw Error("INVALID_DEMO_RESPONSE");
  const keys=Object.keys(data);
  const isBool=x=>typeof x==="boolean";
  if("provider_settlement_verified" in data && data.provider_settlement_verified!==false)
    throw Error("UNTRUSTED_SETTLEMENT");
  if(kind==="create"){
    if(data.reference!==body.reference || data.state!=="PENDING" ||
       data.provider_payment_started!==false || keys.some(k=>!["reference","state","provider_payment_started"].includes(k)))
      throw Error("INVALID_DEMO_RESPONSE");
  }else if(kind==="state"){
    if(!Number.isSafeInteger(data.amount_minor)||data.amount_minor<1||data.amount_minor>100000000||
       data.currency!=="CNY" || !["PENDING","SUCCESS","FAILED","CANCELLED","REFUNDED"].includes(data.state)||
       !("provider_settlement_verified" in data) || data.provider_settlement_verified!==false ||
       !(data.provider_transaction_id===null || (typeof data.provider_transaction_id==="string" && ID.test(data.provider_transaction_id))))
      throw Error("INVALID_DEMO_RESPONSE");
  }else if(kind==="simulate"){
    if(data.state!==body.target || !isBool(data.duplicate)||
       (data.provider_settlement_verified!==undefined && data.provider_settlement_verified!==false) ||
       keys.some(k=>!["state","duplicate","provider_settlement_verified"].includes(k)))
       throw Error("INVALID_DEMO_RESPONSE");
  }
  return data;
 }
 return Object.freeze({
  create(scope,reference,amountMinor){return post("create",{...validateScope(scope),reference:id(reference),amount_minor:validateAmount(amountMinor)});},
  state(scope,reference){return post("state",{...validateScope(scope),reference:id(reference)});},
  simulate(scope,reference,eventId,target,transactionId,amountMinor){
   if(!["SUCCESS","FAILED","CANCELLED"].includes(target))throw Error("INVALID_SIMULATION_STATUS");
   return post("simulate",{...validateScope(scope),reference:id(reference),event_id:id(eventId),
      target,transaction_id:id(transactionId),amount_minor:validateAmount(amountMinor)});
  }
 });
}
if(typeof module!=="undefined")module.exports={makeDemoClient,validateScope,validateAmount};
