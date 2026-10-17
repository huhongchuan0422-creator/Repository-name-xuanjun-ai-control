'use strict';
(()=>{
 const $=id=>document.getElementById(id);let epoch=0,config=null,busy=false,profileVersion=null,orderCursor=null,orderAfter='',reportCursor=null,reportWindow=null,adCursor=null;
 const clear=()=>{for(const id of ['orders','items','ads','report','summary','finance'])$(id).replaceChildren();for(const f of document.querySelectorAll('form'))f.reset();profileVersion=null;orderCursor=null;orderAfter='';reportCursor=null;reportWindow=null;$('moreOrders').hidden=true;$('moreReport').hidden=true;$('moreAds').hidden=true;adCursor=null;};
 const status=message=>{$('notice').textContent=message;};
 window.configureCommunityWorkbench=value=>{
  epoch++;config=value&&typeof value.csrf==='string'&&value.csrf&&/^[A-Za-z0-9_-]{1,64}$/.test(value.workspace)?{csrf:value.csrf,workspace:value.workspace}:null;
  clear();busy=false;for(const b of document.querySelectorAll('button'))b.disabled=!config;status(config?'工作台已连接当前客户中心身份':'请从客户中心登录并打开授权工作台');
 };
 const call=async(op,params,ticket)=>{
  const auth=config;if(!auth)throw Error('请从客户中心打开工作台');
  const response=await fetch('/community/operations',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':auth.csrf},credentials:'same-origin',cache:'no-store',redirect:'error',body:JSON.stringify({workspace:auth.workspace,operation:'community.'+op,params})});
  if(ticket!==epoch)throw Error('身份已变化');
  const data=await response.json();if(ticket!==epoch)throw Error('身份已变化');
  if(!response.ok)throw Error(response.status===403?'当前账号无此权限，或入驻需重新核验':'操作失败或结果未知，请刷新确认后再操作');
  return data.result;
 };
 const action=async fn=>{if(busy||!config)return;busy=true;const ticket=epoch;for(const b of document.querySelectorAll('button'))b.disabled=true;
  try{await fn(ticket);if(ticket===epoch)status('操作完成');}catch(e){if(ticket===epoch)status(e.message);}finally{if(ticket===epoch){busy=false;for(const b of document.querySelectorAll('button'))b.disabled=false;}}};
 const button=(label,fn)=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.addEventListener('click',()=>action(fn));return b;};
 const article=(id,text)=>{const a=document.createElement('article');a.textContent=text;$(id).append(a);return a;};
 const pageParams=after=>({limit:50,after_id:after,status:$('orderStatus').value});
 async function orders(ticket,after=''){
  const params=pageParams(after),result=await call('orders_page',params,ticket);if(ticket!==epoch)return;orderAfter=after;$('orders').replaceChildren();
  for(const o of result.orders){const tr=document.createElement('tr');for(const k of ['reference','amount_minor','currency','state']){const td=document.createElement('td');td.textContent=String(o[k]);tr.append(td);}$('orders').append(tr);}
  orderCursor=result.next_cursor;$('moreOrders').hidden=!result.has_more;
 }
 $('loadOrders').onclick=()=>action(async t=>{await orders(t);const s=await call('summary',{},t);if(t===epoch)$('summary').textContent='模拟订单总额（分）：'+s.order_total_minor+'；各状态数量：'+JSON.stringify(s.counts);});
 $('moreOrders').onclick=()=>action(t=>orders(t,orderCursor));
 $('orderStatus').onchange=()=>{epoch++;busy=false;orderAfter='';orderCursor=null;$('orders').replaceChildren();$('summary').replaceChildren();$('moreOrders').hidden=true;for(const b of document.querySelectorAll('button'))b.disabled=!config;};
 $('exportOrders').onclick=()=>action(async t=>{const r=await call('orders_export',pageParams(orderAfter),t);if(t!==epoch)return;const url=URL.createObjectURL(new Blob(['\ufeff',r.csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=r.filename;a.click();URL.revokeObjectURL(url);});
 async function settings(t){const r=await call('merchant_settings',{},t);if(t!==epoch)return;profileVersion=r.profile?.version??null;if(r.profile){for(const k of ['name','description','contact'])$(k).value=r.profile[k];$('profileStatus').value=r.profile.status;}$('items').replaceChildren();for(const item of r.items){const a=article('items',item.id+' · '+item.name+' · '+item.status);a.append(button('编辑',async()=>{$('itemId').value=item.id;$('itemName').value=item.name;$('itemSort').value=item.sort;$('itemStatus').value=item.status;}));}}
 $('loadSettings').onclick=()=>action(settings);
 $('profileForm').onsubmit=e=>{e.preventDefault();action(async t=>{await call('profile',{record:{name:$('name').value,description:$('description').value,contact:$('contact').value,status:$('profileStatus').value},expected_version:profileVersion},t);await settings(t);});};
 $('itemForm').onsubmit=e=>{e.preventDefault();action(async t=>{await call('item',{item:{id:$('itemId').value,name:$('itemName').value,status:$('itemStatus').value,sort:Number($('itemSort').value)}},t);await settings(t);});};
 async function ads(t,after=''){const r=await call('ads_page',{limit:50,after_id:after},t);if(t!==epoch)return;$('ads').replaceChildren();adCursor=r.next_cursor;$('moreAds').hidden=!r.has_more;for(const c of r.campaigns){const a=article('ads',c.id+' · '+c.slot+' · '+c.status+' · 审核 '+c.moderation+' · 版本 '+c.version);for(const state of ({DRAFT:['REVIEW'],REVIEW:c.moderation==='APPROVED'?['APPROVED']:c.moderation==='REJECTED'?['REJECTED']:[],APPROVED:['ACTIVE','ARCHIVED'],ACTIVE:['PAUSED','ARCHIVED'],PAUSED:['ACTIVE','ARCHIVED'],REJECTED:['REVIEW','ARCHIVED'],ARCHIVED:[]}[c.status]||[]))a.append(button(state,async n=>{await call('ad_state',{campaign_id:c.id,state,expected_version:c.version},n);await ads(n);}));if(['REVIEW','APPROVED','PAUSED'].includes(c.status))for(const approved of [true,false])a.append(button(approved?'平台审核通过':'平台审核驳回',async n=>{await call('ad_review',{campaign_id:c.id,approved,expected_version:c.version},n);await ads(n);}));}}
 $('loadAds').onclick=()=>action(ads);$('moreAds').onclick=()=>action(t=>ads(t,adCursor));
 const seconds=id=>Math.floor(new Date($(id).value).getTime()/1000);
 $('adForm').onsubmit=e=>{e.preventDefault();action(async t=>{await call('ad_create',{record:{id:$('adId').value,title:$('adTitle').value,target_url:$('adUrl').value,slot:$('adSlot').value,starts_at:seconds('adStart'),ends_at:seconds('adEnd'),priority:Number($('adPriority').value)}},t);await ads(t);});};
 async function report(t,after=''){const window=after?reportWindow:{starts_at:seconds('reportStart'),ends_at:seconds('reportEnd')};const r=await call('ad_report',{...window,limit:50,after_id:after},t);if(t!==epoch)return;reportWindow=window;$('report').replaceChildren();for(const c of r.campaigns)article('report',c.id+' · 展示 '+c.impressions+' · 点击 '+c.clicks+' · 点击率 '+(c.click_rate===null?'无展示基数':(c.click_rate*100).toFixed(2)+'%'));reportCursor=r.next_cursor;$('moreReport').hidden=!r.has_more;}
 $('loadReport').onclick=()=>action(t=>report(t));$('moreReport').onclick=()=>action(t=>report(t,reportCursor));
 $('reconcile').onclick=()=>action(async t=>{const r=await call('reconciliation',{},t);if(t===epoch)$('finance').textContent=JSON.stringify(r,null,2);});
 window.configureCommunityWorkbench(null);
})();
