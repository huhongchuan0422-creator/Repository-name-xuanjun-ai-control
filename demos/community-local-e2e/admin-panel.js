"use strict";
(()=>{
 const el=id=>document.getElementById(id);
 const cap=el("adminCapability"), status=el("adminStatus");
 if(!cap||!status)return;
 const scope=()=>{
  const id={tenant_id:el("tenant").value,merchant_id:el("merchant").value,store_id:el("store").value};
  if(Object.values(id).some(v=>! /^[A-Za-z0-9_-]{1,64}$/.test(v)))throw Error("门店范围不合法");
  return id;
 };
 const version=id=>{
  const n=Number(el(id).value);
  if(!Number.isSafeInteger(n)||n<1)throw Error("版本必须为正整数");
  return n;
 };
 const call=async(path,operation)=>{
  const secret=cap.value;
  if(secret.length<32)throw Error("缺少有效本地能力令牌");
  const response=await fetch(path,{method:"POST",headers:{
    "Content-Type":"application/json","X-Local-Admin-Capability":secret
  },body:JSON.stringify({identity:scope(),operation}),credentials:"omit",
    cache:"no-store",redirect:"error"});
  if(response.status!==200)throw Error(response.status===403?"没有当前操作权限":"操作拒绝或版本冲突");
  const data=await response.json();
  if(!data||data.simulation_only!==true||data.provider_settlement_verified!==false||
      data.admin_command_executed!==true||!data.result)throw Error("本地管理响应不可信");
  return data.result;
 };
 const bind=(id,action)=>{
  const button=el(id);
  if(!button)return;
  button.addEventListener("click",async()=>{
   status.textContent="模拟管理操作处理中";
   try{
    const result=await action();
    status.textContent="本地模拟操作完成："+JSON.stringify(result);
   }catch(error){status.textContent="操作未完成："+error.message;}
  });
 };
 bind("saveProfile",()=>call("/demo/admin/profile",{
  record:{name:el("editName").value,description:"Offline demo shop",
          contact:"Offline only",status:"ACTIVE"},expected_version:version("editVersion")
 }));
 bind("saveItem",()=>call("/demo/admin/item",{
  item:{id:el("itemId").value,name:el("itemName").value,status:"ACTIVE",sort:0}
 }));
 bind("createAd",()=>{
  const now=Math.floor(Date.now()/1000);
  return call("/demo/admin/campaign/create",{record:{
   id:el("adId").value,slot:"AD_SLOT_PAYMENT_AMOUNT",
   starts_at:now-120,ends_at:now+86400,title:el("adTitle").value,
   target_url:el("adUrl").value,priority:10
  }});
 });
 bind("submitAd",()=>call("/demo/admin/campaign/state",{
  campaign_id:el("adId").value,state:"REVIEW",expected_version:version("adVersion")
 }));
 bind("approveAdState",()=>call("/demo/admin/campaign/state",{
  campaign_id:el("adId").value,state:"APPROVED",expected_version:version("adVersion")
 }));
 bind("activateAd",()=>call("/demo/admin/campaign/state",{
  campaign_id:el("adId").value,state:"ACTIVE",expected_version:version("adVersion")
 }));
 bind("approveCreative",()=>call("/demo/admin/campaign/review",{
  campaign_id:el("reviewAdId").value,approved:true,expected_version:version("reviewVersion")
 }));
 bind("rejectCreative",()=>call("/demo/admin/campaign/review",{
  campaign_id:el("reviewAdId").value,approved:false,expected_version:version("reviewVersion")
 }));
 cap.addEventListener("input",()=>{status.textContent="本地能力令牌已变更";});
})();
