"use strict";
// Intentional offline demonstration. No credential, network request or payment SDK.
const sample=Object.freeze({merchantName:"示例社区商家",description:"商家展示、金额输入与支付状态演示",storeName:"演示门店",
 adAmount:"演示广告：请勿据此付款",adSuccess:"演示广告：感谢体验"});
const el=id=>document.getElementById(id);
const set=(id,value)=>{el(id).textContent=value;}; // Never interpret merchant/ad text as HTML.
let amountMinor=null;
function show(id){for(const name of ["storefront","amount","pending","receipt"]){el(name).hidden=name!==id;}}
function cents(raw){
 if(typeof raw!=="string"||!/^(?:0|[1-9][0-9]{0,6})(?:\.[0-9]{1,2})?$/.test(raw))throw Error("金额格式错误，最多两位小数");
 const [yuan,fen=""]=raw.split(".");
 const n=Number(yuan)*100+Number(fen.padEnd(2,"0"));
 if(!Number.isSafeInteger(n)||n<1||n>100000000)throw Error("金额超出范围");
 return n;
}
function result(ok){
 show("receipt");
 set("resultTitle",ok?"模拟付款成功":"模拟付款失败");
 set("resultDetail",ok?"仅为本地模拟，不是微信或银行支付凭证。":"未付款，不产生收据。");
 el("successSlot").hidden=!ok;
}
function init(){
 set("merchantName",sample.merchantName);set("merchantDescription",sample.description);
 set("storeName",sample.storeName);set("beneficiary","收款主体："+sample.merchantName);
 set("adAmount",sample.adAmount);set("adSuccess",sample.adSuccess);
 el("openAmount").addEventListener("click",()=>show("amount"));
 el("confirm").addEventListener("click",()=>{
   try{amountMinor=cents(el("payAmount").value.trim());set("amountError","");
       show("pending");}catch(err){set("amountError",err.message);}
 });
 el("simulate").addEventListener("click",()=>{if(amountMinor!==null)result(true);});
 el("fail").addEventListener("click",()=>result(false));
 el("restart").addEventListener("click",()=>{amountMinor=null;el("payAmount").value="";show("storefront");});
 show("storefront");
}
document.addEventListener("DOMContentLoaded",init);
