
"use strict";
const names={overview:"经营概览",orders:"订单管理",catalog:"商品与服务",ads:"广告管理",split:"分账记录",refund:"退款管理",settings:"门店设置"};
const buttons=[...document.querySelectorAll(".nav button")];
function show(id){if(!Object.prototype.hasOwnProperty.call(names,id))return;document.querySelectorAll(".section").forEach(x=>x.classList.toggle("active",x.id===id));buttons.forEach(x=>{if(x.dataset.view===id)x.setAttribute("aria-current","page");else x.removeAttribute("aria-current")});document.getElementById("heading").textContent=names[id];}
buttons.forEach(x=>x.addEventListener("click",()=>show(x.dataset.view)));
document.querySelectorAll("[data-jump]").forEach(x=>x.addEventListener("click",()=>show(x.dataset.jump)));
const merchants=[{"id":"grocer","name":"云汇邻里便利店","kind":"便利零售","hours":"08:00—22:00","orders":[["DEMO-G101","生活补给套餐","¥39.90","模拟完成","今天 10:16"],["DEMO-G102","早餐组合","¥12.00","模拟待处理","今天 10:08"],["DEMO-G103","家庭日用品","¥58.00","模拟完成","今天 09:20"]],"products":[["生活补给套餐","¥39.90","展示中"],["早餐组合","¥12.00","展示中"],["家庭日用品","¥58.00","展示中"]]},{"id":"cafe","name":"云汇街角咖啡","kind":"餐饮饮品","hours":"09:00—21:00","orders":[["DEMO-C101","拿铁双人套餐","¥46.00","模拟完成","今天 10:30"],["DEMO-C102","美式咖啡","¥18.00","模拟已取消","今天 10:10"],["DEMO-C103","下午茶套餐","¥68.00","模拟待处理","今天 09:40"]],"products":[["拿铁双人套餐","¥46.00","展示中"],["美式咖啡","¥18.00","展示中"],["下午茶套餐","¥68.00","展示中"]]},{"id":"home","name":"云汇便民家政","kind":"生活服务","hours":"09:00—18:00","orders":[["DEMO-H101","日常保洁预约","¥129.00","模拟完成","今天 11:00"],["DEMO-H102","家电清洁预约","¥89.00","模拟待处理","今天 10:20"],["DEMO-H103","整理收纳预约","¥159.00","模拟已取消","今天 09:00"]],"products":[["日常保洁预约","¥129.00","展示中"],["家电清洁预约","¥89.00","展示中"],["整理收纳预约","¥159.00","展示中"]]}];
let orders=[];
function renderOrders(){const filter=document.getElementById("orderFilter").value.trim().toLocaleLowerCase();const tbody=document.getElementById("orderRows");tbody.replaceChildren();const matches=orders.filter(x=>x.some(v=>v.toLocaleLowerCase().includes(filter)));for(const order of matches){const tr=document.createElement("tr");for(const cell of order){const td=document.createElement("td");td.textContent=cell;tr.appendChild(td)}tbody.appendChild(tr)}document.getElementById("orderEmpty").hidden=matches.length>0;}
document.getElementById("orderFilter").addEventListener("input",renderOrders);document.getElementById("clearFilter").addEventListener("click",()=>{document.getElementById("orderFilter").value="";renderOrders()});renderOrders();
document.getElementById("refundPreview").addEventListener("click",()=>{const id=document.getElementById("refundId").value.trim();const raw=document.getElementById("refundAmount").value.trim();const result=document.getElementById("actionResult");if(!/^DEMO-[A-Za-z0-9-]{1,35}$/.test(id)||!/^(?:0|[1-9]\d{0,8})(?:\.\d{1,2})?$/.test(raw)||Number(raw)<=0){result.textContent="请输入有效模拟订单号与正数金额（最多两位小数）。";return}result.textContent="仅预览：申请→审核→渠道结果确认→财务对账。未发起退款、未更改订单、未生成真实回执。";});

function cells(table,rows){const body=document.querySelector(table+" tbody");body.replaceChildren();for(const row of rows){const tr=document.createElement("tr");for(const value of row){const td=document.createElement("td");td.textContent=value;tr.appendChild(td)}body.appendChild(tr)}}
function selectMerchant(){
const m=merchants.find(x=>x.id===document.getElementById("merchantSelect").value);if(!m)return;
orders=m.orders;document.getElementById("orderFilter").value="";
document.getElementById("merchantIdentity").textContent=m.name+" · 模拟商家 / 模拟门店A";
document.getElementById("merchantSummary").textContent=m.kind+" · "+m.name+"（模拟商家）";
document.getElementById("settingsName").textContent=m.name+" · 模拟商家";
document.getElementById("settingsHours").textContent="模拟营业时间："+m.hours;
document.getElementById("metricOrders").textContent=String(orders.length);
const cents=o=>Math.round(Number(o[2].replace("¥",""))*100);
const done=orders.filter(o=>o[3]==="模拟完成");
document.getElementById("metricRevenue").textContent="¥"+(done.reduce((s,o)=>s+cents(o),0)/100).toFixed(2);
document.getElementById("metricPending").textContent=String(orders.filter(o=>o[3]==="模拟待处理").length);
cells("#catalog",m.products.map(p=>[...p,"模拟商品 / 非真实报价"]));
cells("#split",done.map(o=>{const total=cents(o),community=Math.floor(total*16/100),platform=Math.floor(total*12/100);return[o[0],"¥"+((total-community-platform)/100).toFixed(2),"¥"+(community/100).toFixed(2),"¥"+(platform/100).toFixed(2),"未接入真实结算"]}));
document.getElementById("refundId").value=orders[0][0];
document.getElementById("actionResult").textContent="";renderOrders();
}
document.getElementById("merchantSelect").addEventListener("change",selectMerchant);selectMerchant();
