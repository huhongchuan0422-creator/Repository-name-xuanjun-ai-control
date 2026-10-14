"use strict";
(()=>{
 const el=id=>document.getElementById(id);
 let token=null, generation=0;
 for(const id of ["tenant","merchant","store","context"])el(id).addEventListener("input",()=>{
  generation++;token=null;el("token").textContent="";el("result").textContent="当前范围已改变";
 });
 function scope(){
  const identity={tenant_id:el("tenant").value,merchant_id:el("merchant").value,store_id:el("store").value,context:el("context").value};
  if(Object.values(identity).some(x=>typeof x!=="string"||!/^[A-Za-z0-9_-]{1,64}$/.test(x)))throw Error("场景输入无效");
  return identity;
 }
 async function call(path,payload){
  const response=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload),cache:"no-store",credentials:"omit",redirect:"error"});
  if(response.status!==200)throw Error("本地场景接口不可用");
  return response.json();
 }
 el("issueQR").addEventListener("click",async()=>{
  const serial=++generation;token=null;el("token").textContent="";
  try{
   const data=await call("/demo/qr/create",scope());
   if(serial!==generation)return;
   if(!data||data.simulation_only!==true||data.provider_payment_started!==false||
      !data.token||typeof data.token.signature!=="string")throw Error("签名格式错误");
   token=data.token;
   el("token").textContent=JSON.stringify({context:token.payload.context,expires:token.payload.expires,signature:token.signature});
   el("result").textContent="已创建本地模拟签名凭证（非微信二维码）";
  }catch(error){if(serial===generation)el("result").textContent="创建失败："+error.message;}
 });
 el("verifyQR").addEventListener("click",async()=>{
  const serial=++generation;
  try{
   if(!token)throw Error("先生成模拟凭证");
   const value=await call("/demo/qr/verify",{...scope(),token});
   if(serial!==generation)return;
   if(value.simulation_only!==true||value.provider_payment_started!==false||typeof value.valid!=="boolean")throw Error("结果格式错误");
   el("result").textContent=value.valid?"签名验证通过（本地模拟）":"签名验证失败";
  }catch(error){if(serial===generation)el("result").textContent="验证失败："+error.message;}
 }); el("checkoutQR").addEventListener("click",async()=>{
  const serial=++generation;
  try{
   if(!token)throw Error("先创建并验证场景凭证");
   const reference=el("reference").value,raw=el("amount").value;
   if(!/^[A-Za-z0-9_-]{1,64}$/.test(reference)||!/^[1-9][0-9]{0,8}$/.test(raw)||
      Number(raw)>100000000)throw Error("订单金额或编号无效");
   const result=await call("/demo/qr/checkout",
     {...scope(),reference,amount_minor:Number(raw),token});
   if(serial!==generation)return;
   if(result.simulation_only!==true||result.provider_settlement_verified!==false||
      result.provider_payment_started!==false||result.state!=="PENDING"||result.reference!==reference)
     throw Error("订单回复不符合模拟合同");
   el("result").textContent="已创建模拟待支付订单 "+reference+"；未启动真实支付";
  }catch(error){if(serial===generation)el("result").textContent="模拟下单失败："+error.message;}
 });

})();
