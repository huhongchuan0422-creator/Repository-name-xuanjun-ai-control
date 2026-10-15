// Stage5 offline read-only view. No browser secrets, payments, fetch or grants.
export function presentAmount(minor,currency){
 if(!Number.isSafeInteger(minor)||minor<0)return "UNKNOWN";
 if(currency!=="CNY"&&currency!=="USD")throw Error("INVALID_CURRENCY");
 return (currency==="CNY"?"¥":"$")+(minor/100).toFixed(2);
}
export function safeText(value){
 return value==null?"UNKNOWN":String(value);
}
export function modelToView(model){
 if(!model||typeof model!=="object"||Array.isArray(model))throw Error("INVALID_MODEL");
 const modules=Array.isArray(model.modules)?model.modules:[];
 const orders=Array.isArray(model.orders)?model.orders:[];
 const reviews=Array.isArray(model.reviews)?model.reviews:[];
 return {
 modules:modules.map(x=>({title:safeText(x.title),id:safeText(x.id)})),
 orders:orders.map(x=>({id:safeText(x.order_id),state:safeText(x.state),
   cny:safeText(x.cny_minor===undefined?"UNKNOWN":presentAmount(x.cny_minor,"CNY")),
   usd:safeText(x.usd_minor===undefined?"UNKNOWN":presentAmount(x.usd_minor,"USD"))})),
 reviews:reviews.map(x=>({kind:safeText(x.kind),state:safeText(x.state)})),
 label:"OFFLINE_ONLY_NO_PAYMENT_NO_ENTITLEMENT"
 };
}
function appendText(el,title,text){
 const p=document.createElement("p");const strong=document.createElement("strong");
 strong.textContent=title+": ";p.append(strong,document.createTextNode(text));el.append(p);
}
export function renderDashboard(doc,model){
 const view=modelToView(model);
 const catalog=doc.getElementById("moduleCatalog");
 const orders=doc.getElementById("orderDetails");
 const queue=doc.getElementById("reviewQueue");
 catalog.replaceChildren();orders.replaceChildren();queue.replaceChildren();
 for(const item of view.modules)appendText(catalog,item.title,item.id);
 for(const x of view.orders)appendText(orders,x.id,x.state+" · "+x.cny+" / "+x.usd);
 for(const x of view.reviews)appendText(queue,x.kind,x.state);
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
 let orders=[],reviews=[];
 try{const panel=await post("admin_snapshot");orders=panel.orders;reviews=panel.review_tasks}catch(error){if(error.message!=="OFFLINE_REQUEST_DENIED")throw error}
 return {modules,orders,reviews};
}
if(typeof document!=="undefined"&&document.getElementById("moduleCatalog")){
 renderDashboard(document,{modules:[],orders:[],reviews:[]});
 document.getElementById("loadCatalog")?.addEventListener("click",async()=>{
  const token=document.getElementById("offlineToken").value;
  const state=document.getElementById("requestState");
  state.textContent="正在读取本地离线业务数据…";
  try{const model=await loadDashboard(fetch,token);renderDashboard(document,model);state.textContent="仅展示已授权的离线数据；没有支付或权限发放。"}
  catch(error){state.textContent="读取失败：请检查本地访问权限；未执行资金动作。"}
 });
}