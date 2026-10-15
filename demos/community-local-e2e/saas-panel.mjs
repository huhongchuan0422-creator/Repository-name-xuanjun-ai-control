// Stage5 offline read-only view. No browser secrets, payments, fetch or grants.
export function presentAmount(minor,currency){
 if(!Number.isSafeInteger(minor)||minor<0)return "UNKNOWN";
 if(currency!=="CNY"&&currency!=="USD")throw Error("INVALID_CURRENCY");
 return (currency==="CNY"?"¥":"$")+(minor/100).toFixed(2);
}
export function safeText(value){
 return value==null?"UNKNOWN":String(value);
}
export function offerCycles(offer){
 const totals={};
 for(const line of Array.isArray(offer.lines)?offer.lines:[]){
  const cycle=safeText(line.cycle),entry=totals[cycle]??{cny:0,usd:0,unknownCNY:false,unknownUSD:false};
  const qty=line.quantity;
  for(const [curr,key] of [["cny","cny_minor"],["usd","usd_minor"]]){
   const unknownKey=curr==="cny"?"unknownCNY":"unknownUSD";
   if(!Number.isSafeInteger(qty)||qty<=0||!Number.isSafeInteger(line[key])||line[key]<0){
    entry[unknownKey]=true;
   } else {
    const subtotal=qty*line[key];
    if(!Number.isSafeInteger(subtotal)||!Number.isSafeInteger(entry[curr]+subtotal)){
     entry[unknownKey]=true;
    } else entry[curr]+=subtotal;
   }
  }
  totals[cycle]=entry;
 }
 return Object.entries(totals).map(([cycle,x])=>cycle+" "+(x.unknownCNY?"UNKNOWN":presentAmount(x.cny,"CNY"))+" / "+(x.unknownUSD?"UNKNOWN":presentAmount(x.usd,"USD"))).join("；");
}
export function modelToView(model){
 if(!model||typeof model!=="object"||Array.isArray(model))throw Error("INVALID_MODEL");
 const modules=Array.isArray(model.modules)?model.modules:[];
 const orders=Array.isArray(model.orders)?model.orders:[];
 const reviews=Array.isArray(model.reviews)?model.reviews:[];
 return {
 modules:modules.map(x=>({title:safeText(x.title),id:safeText(x.id),
   offers:Array.isArray(x.offers)?x.offers.map(o=>safeText(o.offer_id)+" v"+safeText(o.version)+" · "+offerCycles(o)):[],
   active:x.active===true})),
 orders:orders.map(x=>({id:safeText(x.order_id),state:safeText(x.state),
   cny:safeText(x.currency!=="USD"?presentAmount(x.amounts_by_cycle_minor?.MONTH??x.cny_minor,"CNY"):"—"),
   usd:safeText(x.currency!=="CNY"?presentAmount(x.amounts_by_cycle_minor?.MONTH??x.usd_minor,"USD"):"—")})),
 reviews:reviews.map(x=>({kind:safeText(x.kind),state:safeText(x.state)})),
 label:"OFFLINE_ONLY_NO_PAYMENT_NO_ENTITLEMENT"
 };
}
function appendText(doc,el,title,text){
 const p=doc.createElement("p");const strong=doc.createElement("strong");
 strong.textContent=title+": ";p.append(strong,doc.createTextNode(text));el.append(p);
}
export function renderDashboard(doc,model){
 const view=modelToView(model);
 const catalog=doc.getElementById("moduleCatalog");
 const orders=doc.getElementById("orderDetails");
 const queue=doc.getElementById("reviewQueue");
 catalog.replaceChildren();orders.replaceChildren();queue.replaceChildren();
 for(const item of view.modules)appendText(doc,catalog,item.title,item.id+(item.offers.length?" · "+item.offers.join(", "):" · 暂无选配报价")+" · 权益："+(item.active?"有效":"未授权"));
 for(const x of view.orders)appendText(doc,orders,x.id,x.state+" · "+x.cny+" / "+x.usd);
 for(const x of view.reviews)appendText(doc,queue,x.kind,x.state);
 doc.getElementById("quoteDetails").textContent="所有价格须经版本审核；成本未知不等于零。";
 doc.getElementById("entitlementDetails").textContent="未取得权威授权：不自动开通";
 doc.getElementById("renewalDetails").textContent="只读续费计划；不会自动扣款";
 doc.getElementById("recoveryState").textContent=view.label;
 return view;
}
export async function loadDashboard(fetcher,token,now=Math.floor(Date.now()/1000)){
 if(typeof token!=="string"||token.length<32)throw Error("TOKEN_REQUIRED");
 const post=async(operation,params={})=>{
  const response=await fetcher("/offline/saas",{method:"POST",headers:{"Content-Type":"application/json","X-Offline-Token":token},body:JSON.stringify({operation,params,at:now})});
  if(!response.ok)throw Error("OFFLINE_REQUEST_DENIED");
  const body=await response.json();return body.result;
 };
 const modules=(await post("catalog")).modules;
 for(const item of modules){item.offers=(await post("offers",{module_id:item.id})).offers;
  item.active=(await post("entitlement",{module_id:item.id})).active;}
 const orders=(await post("customer_orders")).orders;
 let reviews=[];
 try{const panel=await post("admin_snapshot");reviews=panel.review_tasks}catch(error){if(error.message!=="OFFLINE_REQUEST_DENIED")throw error}
 return {modules,orders,reviews};
}
export async function offlineAction(fetcher,token,operation,params,now=Math.floor(Date.now()/1000)){
 if(typeof token!=="string"||token.length<32)throw Error("TOKEN_REQUIRED");
 if(!["quote","order_prepare","renewal_plan","owner_create_offer","owner_approve_offer"].includes(operation))throw Error("OPERATION_NOT_ALLOWED");
 const response=await fetcher("/offline/saas",{method:"POST",
  headers:{"Content-Type":"application/json","X-Offline-Token":token},
  body:JSON.stringify({operation,params,at:now})});
 if(!response.ok)throw Error("OFFLINE_REQUEST_DENIED");
 const value=await response.json();return value.result;
}
if(typeof document!=="undefined"&&document.getElementById("moduleCatalog")){
 renderDashboard(document,{modules:[],orders:[],reviews:[]});
 let currentQuoteId=null;
 document.getElementById("makeQuote")?.addEventListener("click",async()=>{
  const status=document.getElementById("requestState");
  const token=document.getElementById("offlineToken").value;
  currentQuoteId="q"+crypto.randomUUID().replaceAll("-","");
  const offer=document.getElementById("offerId").value.trim();
  const version=Number(document.getElementById("offerVersion").value);
  try{const q=await offlineAction(fetch,token,"quote",{quote_id:currentQuoteId,offer_id:offer,version,expires_at:Math.floor(Date.now()/1000)+1800});
    document.getElementById("quoteDetails").textContent=JSON.stringify({quote_id:currentQuoteId,amounts_by_cycle:q.totals_by_cycle,settlement_authorized:false},null,2);
    status.textContent="离线报价已冻结；未发生真实支付。";
  }catch{currentQuoteId=null;status.textContent="离线报价失败；请检查方案和权限。";}
 });
 const ownerValue=id=>document.getElementById(id).value.trim();
 const money=id=>{const x=Number(ownerValue(id));if(!Number.isSafeInteger(x)||x<0)throw Error("BAD_MONEY");return x};
 document.getElementById("ownerCreate")?.addEventListener("click",async()=>{
  const state=document.getElementById("ownerStatus");
  try{
   const values={offer_id:ownerValue("ownerOfferId"),version:1,
    module_id:ownerValue("ownerModuleId"),kind:"MONTHLY",
    lines:[{type:"MODULE_FEE",label:"月度功能订阅",cycle:"MONTH",quantity:1,
      cny_minor:money("ownerCny"),usd_minor:money("ownerUsd"),
      cost_cny_minor:money("ownerCostCny"),cost_usd_minor:money("ownerCostUsd")}],
    term_days:30,tenant_scope:null,supplier_payment:"NONE"};
   await offlineAction(fetch,ownerValue("offlineToken"),"owner_create_offer",values);
   state.textContent="已保存离线待审批版本，未发布、未收费。";
  }catch{state.textContent="未保存：请核对Owner身份及价格、成本证据。";}
 });
 document.getElementById("ownerApprove")?.addEventListener("click",async()=>{
  const state=document.getElementById("ownerStatus");
  try{
   await offlineAction(fetch,ownerValue("offlineToken"),"owner_approve_offer",{
    offer_id:ownerValue("ownerOfferId"),version:1,approval_ref:ownerValue("ownerApprovalRef"),
    cost_evidence_ref:ownerValue("ownerCostRef")});
   state.textContent="离线审批已记录；不授权真实交易或生产发布。";
  }catch{state.textContent="审批失败：需要Owner身份、成本完整和有效证据。";}
 });
 document.getElementById("previewRenewal")?.addEventListener("click",async()=>{
  const status=document.getElementById("requestState");
  try{
   const orderId=document.getElementById("renewalOrderId").value.trim();
   const until=Number(document.getElementById("previousExpiry").value);
   if(!Number.isSafeInteger(until)||until<0)throw Error("BAD_TIME");
   const view=await offlineAction(fetch,document.getElementById("offlineToken").value,"renewal_plan",{order_id:orderId,valid_until:until});
   document.getElementById("renewalDetails").textContent=JSON.stringify({
     start:view.proposed_valid_from,end:view.proposed_valid_until,
     no_auto_renewal:!view.automatic_renewal_authorized,
     needs_approval:view.needs_entitlement_approval},null,2);
   status.textContent="续费仅供审阅，不执行扣款。";
  }catch{status.textContent="续费规划不可用：需要有效订单和经核验的确认凭证。";}
 });
 document.getElementById("prepareOrder")?.addEventListener("click",async()=>{
  const status=document.getElementById("requestState");
  if(!currentQuoteId){status.textContent="请先生成离线报价。";return}
  try{const orderId="o"+crypto.randomUUID().replaceAll("-","");
    const o=await offlineAction(fetch,document.getElementById("offlineToken").value,"order_prepare",{order_id:orderId,quote_id:currentQuoteId,currency:"CNY"});
    status.textContent="订单准备成功 "+o.order_id+"；不代表支付成功，也未开通权益。";
  }catch{status.textContent="订单准备失败；未执行付款。";}
 });
 document.getElementById("loadCatalog")?.addEventListener("click",async()=>{
  const token=document.getElementById("offlineToken").value;
  const state=document.getElementById("requestState");
  state.textContent="正在读取本地离线业务数据…";
  try{const model=await loadDashboard(fetch,token);renderDashboard(document,model);state.textContent="仅展示已授权的离线数据；没有支付或权限发放。"}
  catch(error){state.textContent="读取失败：请检查本地访问权限；未执行资金动作。"}
 });
}