"use strict";
const get=id=>document.getElementById(id);
const text=(id,value)=>{get(id).textContent=String(value);};
const fields=["tenant","merchant","store","reference","amount"];
let generation=0, requestSerial=0, storefrontSerial=0, activeKey=null;
function input(){
 const scope={tenant_id:get("tenant").value,merchant_id:get("merchant").value,store_id:get("store").value};
 const reference=get("reference").value,raw=get("amount").value,amount=Number(raw);
 if(Object.values(scope).some(x=>!/^[A-Za-z0-9_-]{1,64}$/.test(x))||!/^[A-Za-z0-9_-]{1,64}$/.test(reference)||
    !/^[1-9][0-9]{0,8}$/.test(raw)||!Number.isSafeInteger(amount)||amount>100000000)throw Error("输入无效");
 return {...scope,reference,amount_minor:amount};
}
const key=o=>JSON.stringify([o.tenant_id,o.merchant_id,o.store_id,o.reference,o.amount_minor]);
function clear(){
 storefrontSerial++;
 text("storefrontName","");text("storefrontProducts","");text("storefrontStatus","尚未加载门店");
 text("adAmount","金额页广告位：当前无广告（模拟）");
 generation++;activeKey=null;
 get("successAd").hidden=true;
 text("status","未核实当前订单");text("merchantResult","");
}
function current(token,requestToken,order){return token===generation && requestToken===requestSerial && activeKey===key(order) && key(input())===activeKey;}
async function request(path,payload){
 const response=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload),credentials:"omit",cache:"no-store",redirect:"error"});
 if(!response||response.status!==200)throw Error("模拟接口请求失败");
 const data=await response.json();
 if(!data||typeof data!=="object"||Array.isArray(data)||Object.getPrototypeOf(data)!==Object.prototype||
    data.provider_settlement_verified===true)throw Error("模拟结果格式错误");
 return data;
}
const exact=(data,allowed,required=allowed)=>Object.keys(data).every(k=>allowed.includes(k))&&required.every(k=>Object.hasOwn(data,k));
function validate(kind,data,order){
 if(kind==="create"){
  if(!exact(data,["reference","state","provider_payment_started"])||data.reference!==order.reference||
     data.state!=="PENDING"||data.provider_payment_started!==false)throw Error("订单返回不匹配");
 }else if(kind==="query"||kind==="merchantQuery"){
  if(!exact(data,["amount_minor","currency","state","provider_transaction_id","provider_settlement_verified"])||
     !Number.isSafeInteger(data.amount_minor)||data.amount_minor!==order.amount_minor||data.currency!=="CNY"||
     !["PENDING","SUCCESS","FAILED","CANCELLED","REFUNDED"].includes(data.state)||
     data.provider_settlement_verified!==false||
     !(data.provider_transaction_id===null||typeof data.provider_transaction_id==="string"&&/^[A-Za-z0-9_-]{1,64}$/.test(data.provider_transaction_id)))
     throw Error("订单状态不匹配");
 }else{
  const expected=kind==="complete"?"SUCCESS":"FAILED";
  if(!exact(data,["state","duplicate","provider_settlement_verified"],["state","duplicate"])||
     data.state!==expected||typeof data.duplicate!=="boolean"||
     data.provider_settlement_verified!==undefined&&data.provider_settlement_verified!==false)
     throw Error("模拟事件返回不匹配");
 }
}
async function action(kind){
 get("successAd").hidden=true;
 text("error","");
 let order,token;
 const requestToken=++requestSerial;
 try{
  order=input();
  if(kind!=="create" && activeKey!==key(order))throw Error("请先创建当前订单");
  if(kind==="create"){clear();activeKey=key(order);}
  token=generation;
  let path,payload;
  if(kind==="create"){path="/demo/orders";payload=order;}
  else if(kind==="query"||kind==="merchantQuery"){
   path="/demo/orders/state";const {amount_minor,...identity}=order;payload=identity;
  }else{
   path="/demo/orders/simulate";
   const eventNonce=crypto.randomUUID().replace(/-/g,"");
   const transactionNonce=crypto.randomUUID().replace(/-/g,"");
   payload={...order,event_id:"local_event_"+eventNonce,transaction_id:"local_tx_"+transactionNonce,
      target:kind==="complete"?"SUCCESS":"FAILED"};
  }
  const data=await request(path,payload);
  if(!current(token,requestToken,order))return;
  validate(kind,data,order);
  if(kind==="merchantQuery")text("merchantResult","模拟订单："+JSON.stringify(data));
  else text("status","本地模拟状态："+data.state+"（非真实支付凭证）");
  get("successAd").hidden=kind!=="complete";
 }catch(e){
  if(requestToken!==requestSerial || token!==undefined && order && (token!==generation || activeKey!==key(order)))return;
  get("successAd").hidden=true;text("error",e.message);
 }
}
for(const name of fields)get(name).addEventListener("input",clear);
for(const kind of ["create","query","complete","fail","merchantQuery"])
 get(kind).addEventListener("click",()=>action(kind));

function validStorefront(data){
 const slots=["AD_SLOT_PAYMENT_AMOUNT","AD_SLOT_PAYMENT_SUCCESS"];
 if(!exact(data,["merchant","products","ads","simulation_only","provider_settlement_verified","escape_text_required"])||
    data.simulation_only!==true||data.provider_settlement_verified!==false||data.escape_text_required!==true||
    !data.merchant||typeof data.merchant!=="object"||Array.isArray(data.merchant)||
    !exact(data.merchant,["name","description","contact"])||
    Object.values(data.merchant).some(x=>typeof x!=="string"||x.length>2048)||
    !Array.isArray(data.products)||data.products.length>100||
    data.products.some(x=>!x||typeof x!=="object"||Array.isArray(x)||!exact(x,["id","name","sort"])||
      typeof x.id!=="string"||typeof x.name!=="string"||!Number.isInteger(x.sort))||
    !data.ads||typeof data.ads!=="object"||Array.isArray(data.ads)||!exact(data.ads,slots)||
    data.ads[slots[1]]!==null)throw Error("门店返回数据不可信");
 const ad=data.ads[slots[0]];
 if(ad!==null && (!ad||typeof ad!=="object"||Array.isArray(ad)||
    !exact(ad,["id","title","url","slot"])||
    ad.slot!==slots[0]||typeof ad.title!=="string"||typeof ad.id!=="string"||
    typeof ad.url!=="string"||ad.url.includes("\\")||/\s/.test(ad.url)||!/^https:\/\/[A-Za-z0-9.-]+(?:[:]\d+)?(?:\/[^\s]*)?$/.test(ad.url)))
    throw Error("广告返回数据不可信");
 return ad;
}
async function loadStorefront(){
 const token=++storefrontSerial;
 text("storefrontStatus","正在读取本地模拟门店");
 text("storefrontName","");text("storefrontProducts","");
 text("adAmount","金额页广告位：当前无广告（模拟）");
 const identity={tenant_id:get("tenant").value,merchant_id:get("merchant").value,store_id:get("store").value};
 try{
  if(Object.values(identity).some(x=>!/^[A-Za-z0-9_-]{1,64}$/.test(x)))throw Error("门店范围格式不正确");
  const data=await request("/demo/storefront",identity);
  if(token!==storefrontSerial || identity.tenant_id!==get("tenant").value||
     identity.merchant_id!==get("merchant").value||identity.store_id!==get("store").value)return;
  const ad=validStorefront(data);
  // Never use innerHTML or a remote image/link; textContent is a safe preview.
  text("storefrontName",data.merchant.name);
  text("storefrontProducts",data.products.map(x=>x.name).join("；"));
  if(ad!==null)text("adAmount","金额页审核广告："+ad.title);
  text("storefrontStatus","已加载本地模拟门店");
 }catch(e){
  if(token!==storefrontSerial)return;
  text("storefrontStatus","门店尚不可用："+e.message);
 }
}
get("loadStorefront").addEventListener("click",loadStorefront);
