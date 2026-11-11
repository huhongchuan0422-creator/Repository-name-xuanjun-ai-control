"use strict";
(()=>{
 const el=id=>document.getElementById(id);
 const button=el("loadCatalog")||el("inspectCatalog");
 if(!button)return;
 let version=0;
 const clear=()=>{
   version++;
   for(const id of ["catalogName","catalogItems","catalogAd"])el(id).textContent="";
   el("catalogStatus").textContent="尚未读取";
 };
 for(const id of ["tenant","merchant","store"])el(id).addEventListener("input",clear);
 button.addEventListener("click",async()=>{
   const v=++version;
   clear();
   const current=version;
   const scope={tenant_id:el("tenant").value,merchant_id:el("merchant").value,store_id:el("store").value};
   try{
     for(const field of Object.values(scope)){
       if(typeof field!=="string"||!field||field.length>64)throw Error("无效门店范围");
     }
     const response=await fetch("/demo/storefront",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(scope),credentials:"omit",cache:"no-store"});
     if(response.status!==200)throw Error("门店接口不可用");
     const value=await response.json();
     if(current!==version)return;
     if(value.simulation_only!==true||value.provider_settlement_verified!==false||
       value.escape_text_required!==true||!value.merchant||
       !Array.isArray(value.products)||!value.ads||
       value.ads.AD_SLOT_PAYMENT_SUCCESS!==null)throw Error("模拟数据不可信");
     const amount=value.ads.AD_SLOT_PAYMENT_AMOUNT;
     if(typeof value.merchant.name!=="string"||
       value.products.some(item=>typeof item.name!=="string")||
       (amount!==null&&(!amount||typeof amount.title!=="string"||
        amount.slot!=="AD_SLOT_PAYMENT_AMOUNT")))throw Error("格式错误");
     el("catalogName").textContent=value.merchant.name;
     el("catalogItems").textContent=value.products.map(item=>item.name).join("；");
     el("catalogAd").textContent=amount===null?"无金额页广告":"金额页审核广告："+amount.title;
     el("catalogStatus").textContent="本地演示数据，非真实商家管理权限";
   }catch(error){
     if(current!==version)return;
     el("catalogStatus").textContent="读取失败："+error.message;
   }
 });
})();
