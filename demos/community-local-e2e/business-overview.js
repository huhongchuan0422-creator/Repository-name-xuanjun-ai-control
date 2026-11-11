"use strict";
(()=>{
 const el=id=>document.getElementById(id),button=el("loadOverview");
 if(!button)return;
 const scopeFields=["tenant","merchant","store"];
 let sequence=0;
 function reset(){
  sequence++;
  for(const id of ["overviewOrders","overviewRevenue","overviewAds"])el(id).textContent="";
  el("overviewStatus").textContent="尚未读取";
 }
 for(const id of scopeFields)el(id).addEventListener("input",reset);
 const plain=value=>value&&Object.getPrototypeOf(value)===Object.prototype;
 const keys=(value,wanted)=>plain(value)&&Object.keys(value).length===wanted.length&&wanted.every(key=>Object.hasOwn(value,key));
 const read=async(route,identity)=>{
  const response=await fetch(route,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(identity),cache:"no-store",credentials:"omit",redirect:"error"});
  if(!response||response.status!==200)throw Error("本地模拟服务不可用");
  return response.json();
 };
 button.addEventListener("click",async()=>{
  const ticket=++sequence;
  const identity={tenant_id:el("tenant").value,merchant_id:el("merchant").value,store_id:el("store").value};
  for(const id of ["overviewOrders","overviewRevenue","overviewAds"])el(id).textContent="";
  el("overviewStatus").textContent="正在读取经营概览";
  try{
   if(Object.values(identity).some(value=>typeof value!=="string"||! /^[A-Za-z0-9_-]{1,64}$/.test(value)))throw Error("商家范围无效");
   const [orders,ads]=await Promise.all([read("/demo/orders/summary",identity),read("/demo/ads/list",identity)]);
   if(ticket!==sequence||scopeFields.some((field,index)=>el(field).value!==Object.values(identity)[index]))return;
   const states=["PENDING","SUCCESS","FAILED","CANCELLED","REFUNDED"];
   if(!keys(orders,["counts","order_total_minor","simulation_only","provider_settlement_verified","real_revenue_minor"])||
      orders.simulation_only!==true||orders.provider_settlement_verified!==false||orders.real_revenue_minor!==null||
      !keys(orders.counts,states)||states.some(k=>!Number.isSafeInteger(orders.counts[k])||orders.counts[k]<0)||
      !Number.isSafeInteger(orders.order_total_minor)||orders.order_total_minor<0||
      !keys(ads,["campaigns","has_more","simulation_only","write_permissions"])||
      ads.simulation_only!==true||ads.write_permissions!==false||typeof ads.has_more!=="boolean"||
      !Array.isArray(ads.campaigns)||ads.campaigns.length>50)throw Error("概览数据不可信");
   for(const campaign of ads.campaigns){
    if(!keys(campaign,["id","slot","status","moderation","priority","version"])||
       typeof campaign.id!=="string"||! /^[A-Za-z0-9_-]{1,100}$/.test(campaign.id)||
       !["AD_SLOT_PAYMENT_AMOUNT","AD_SLOT_PAYMENT_SUCCESS"].includes(campaign.slot)||
       !["DRAFT","REVIEW","APPROVED","ACTIVE","PAUSED","REJECTED","ARCHIVED"].includes(campaign.status)||
       !["PENDING","APPROVED","REJECTED"].includes(campaign.moderation)||
       !Number.isSafeInteger(campaign.priority)||!Number.isSafeInteger(campaign.version))throw Error("广告数据不可信");
   }
   el("overviewOrders").textContent=states.map(k=>k+" "+orders.counts[k]).join(" · ");
   el("overviewRevenue").textContent="模拟订单合计 "+orders.order_total_minor+" 分；真实收入：未知";
   el("overviewAds").textContent=ads.campaigns.map(c=>c.id+" / "+c.slot+" / "+c.status+" / 审核 "+c.moderation).join("；")||"暂无广告活动";
   el("overviewStatus").textContent="已读取本门店概览（无真实管理员授权）";
  }catch(error){
   if(ticket!==sequence)return;
   el("overviewStatus").textContent="读取失败："+error.message;
  }
 });
})();
