"use strict";
const get=id=>document.getElementById(id);
const text=(id,value)=>{get(id).textContent=String(value);};
let counter=0;
function input(){
 const scope={tenant_id:get("tenant").value,merchant_id:get("merchant").value,store_id:get("store").value};
 const reference=get("reference").value;
 const amount=Number(get("amount").value);
 if(Object.values(scope).some(x=>!/^[A-Za-z0-9_-]{1,64}$/.test(x))||!/^[A-Za-z0-9_-]{1,64}$/.test(reference)||!/^[1-9][0-9]{0,8}$/.test(get("amount").value)||!Number.isSafeInteger(amount)||amount>100000000)throw Error("输入无效");
 return {...scope,reference,amount_minor:amount};
}
async function request(path,payload){
 const response=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload),credentials:"omit",cache:"no-store",redirect:"error"});
 if(response.status!==200)throw Error("模拟接口拒绝请求："+response.status);
 const data=await response.json();
 if(!data||typeof data!=="object"||Array.isArray(data)||data.provider_settlement_verified===true)throw Error("模拟结果格式错误");
 return data;
}
async function action(kind){
 text("error","");
 try{
  const order=input();let result;
  if(kind==="create"){
   result=await request("/demo/orders",order);
   if(result.reference!==order.reference||result.state!=="PENDING")throw Error("订单返回不匹配");
   get("successAd").hidden=true;
  }else if(kind==="query"||kind==="merchantQuery"){
   const {amount_minor,...identity}=order;
   result=await request("/demo/orders/state",identity);
   if(result.amount_minor!==amount_minor||result.currency!=="CNY"||!["PENDING","SUCCESS","FAILED","CANCELLED"].includes(result.state))throw Error("订单状态不匹配");
  }else{
   const event_id="local_event_"+(++counter),transaction_id="local_tx_"+counter;
   result=await request("/demo/orders/simulate",{...order,event_id,transaction_id,target:kind==="complete"?"SUCCESS":"FAILED"});
   if(result.state!==(kind==="complete"?"SUCCESS":"FAILED"))throw Error("事件状态不匹配");
  }
  if(kind==="merchantQuery")text("merchantResult","模拟商家订单："+JSON.stringify(result));
  else text("status","本地模拟状态："+result.state+"（非微信支付凭证）");
  // Success-slot only for explicit local simulated outcome, never a provider receipt.
  get("successAd").hidden=kind!=="complete";
 }catch(e){get("successAd").hidden=true;text("error",e.message);}
}
for(const kind of ["create","query","complete","fail","merchantQuery"]){
 document.getElementById(kind).addEventListener("click",()=>action(kind));
}
