"use strict";
/* Local demo only. Identity/roles are mock data, not an authentication mechanism. */
const DEMO=Object.freeze({scope:Object.freeze({tenant_id:"t1",merchant_id:"m1",store_id:"s1"}),orders:Object.freeze([{id:"demo1",scope:"t1/m1/s1",state:"PENDING",amount_minor:1250},{id:"demo2",scope:"t1/m1/s1",state:"SUCCESS",amount_minor:2300}]),ads:Object.freeze([{id:"ad1",scope:"t1/m1/s1",slot:"AD_SLOT_PAYMENT_AMOUNT",state:"DRAFT"},{id:"ad2",scope:"t1/m1/s1",slot:"AD_SLOT_PAYMENT_SUCCESS",state:"ACTIVE"}])});
const el=id=>document.getElementById(id);
const put=(id,value)=>{el(id).textContent=value;};
const td=(tr,value)=>{const cell=document.createElement("td");cell.textContent=String(value);tr.appendChild(cell);};
function table(id,rows,columns){const target=el(id);target.replaceChildren();for(const row of rows){const tr=document.createElement("tr");for(const col of columns)td(tr,row[col]);target.appendChild(tr);}}
function view(mode){
 const role=el("role").value;
 const merchant=mode==="merchant"&&(role==="MERCHANT_ADMIN"||role==="STORE_STAFF");
 const platform=mode==="platform"&&(role==="PLATFORM_REVIEWER"||role==="FINANCE_APPROVER");
 el("merchant").hidden=!merchant;el("platform").hidden=!platform;
 if(!merchant&&!platform){put("notice","当前演示角色无权进入此后台");return;}
 put("notice",mode==="merchant"?"正在查看本商家模拟数据":"平台模拟审核模式");
 if(merchant){
  const scope="t1/m1/s1";table("orders",DEMO.orders.filter(x=>x.scope===scope).map(x=>({id:x.id,state:x.state,amount:(x.amount_minor/100).toFixed(2)})),["id","state","amount"]);
  table("ads",role==="MERCHANT_ADMIN"?DEMO.ads.filter(x=>x.scope===scope):[],["id","slot","state"]);
 }
}
function approval(action){
 const role=el("role").value;const allowed=action==="MERCHANT_APPROVAL"?role==="PLATFORM_REVIEWER":role==="FINANCE_APPROVER";
 put("platformResult",allowed?"仅模拟：角色允许发起"+action+"；未发生实际审批或资金变更。":"拒绝：角色职责不匹配。");
}
function init(){
 el("merchantButton").addEventListener("click",()=>view("merchant"));
 el("platformButton").addEventListener("click",()=>view("platform"));
 el("role").addEventListener("change",()=>{el("merchant").hidden=true;el("platform").hidden=true;put("notice","角色变化，请重新选择入口");put("platformResult","");});
 el("merchantApproval").addEventListener("click",()=>approval("MERCHANT_APPROVAL"));
 el("splitApproval").addEventListener("click",()=>approval("SPLIT_APPROVAL"));
 view("merchant");
}
document.addEventListener("DOMContentLoaded",init);
