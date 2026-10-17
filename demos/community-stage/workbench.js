'use strict';
(()=>{
 const $=id=>document.getElementById(id);let epoch=0,config=null,busy=false,profileVersion=null,orderCursor=null,orderAfter='',reportCursor=null,reportWindow=null,adCursor=null;
 let financialPage=null;
 const clear=()=>{for(const id of ['orders','items','ads','report','summary','finance','orderDetail','refundResult','splitResult','providerReceivers','providerActionResult','priceResult','refundApplicationResult','staffResult','storeList','storeResult','billResult'])$(id).replaceChildren();for(const f of document.querySelectorAll('form'))f.reset();$('providerOrder').value='';$('providerRequest').value='';$('providerActions').hidden=true;profileVersion=null;orderCursor=null;orderAfter='';reportCursor=null;reportWindow=null;$('moreOrders').hidden=true;$('moreReport').hidden=true;$('moreAds').hidden=true;adCursor=null;financialPage=null;$('financialMore').hidden=true;billPage=null;billAuditPage=null;$('moreBill').hidden=true;$('moreBillAudit').hidden=true;};
 const status=message=>{$('notice').textContent=message;};
 window.configureCommunityWorkbench=value=>{
  epoch++;config=value&&typeof value.csrf==='string'&&value.csrf&&/^[A-Za-z0-9_-]{1,64}$/.test(value.workspace)?{csrf:value.csrf,workspace:value.workspace,providerWorkspace:typeof value.providerWorkspace==='string'&&/^[A-Za-z0-9_-]{1,64}$/.test(value.providerWorkspace)?value.providerWorkspace:null}:null;
  clear();$('providerActions').hidden=!config?.providerWorkspace;$('billSection').hidden=!config?.providerWorkspace;busy=false;for(const b of document.querySelectorAll('button'))b.disabled=!config;status(config?'工作台已连接当前客户中心身份':'请从客户中心登录并打开授权工作台');
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
  for(const o of result.orders){const tr=document.createElement('tr');for(const k of ['reference','amount_minor','currency','state']){const td=document.createElement('td');td.textContent=String(o[k]);tr.append(td);}const td=document.createElement('td');td.append(button('查看详情',async n=>{$('detailReference').value=o.reference;await detail(n);}));tr.append(td);$('orders').append(tr);}
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
 async function detail(t){const reference=$('detailReference').value;const r=await call('order_detail',{reference},t);if(t!==epoch||reference!==$('detailReference').value)return;$('orderDetail').textContent=JSON.stringify(r,null,2);$('refundResult').replaceChildren();$('splitResult').replaceChildren();}
 $('detailForm').onsubmit=e=>{e.preventDefault();action(detail);};
 $('detailReference').oninput=()=>{$('orderDetail').replaceChildren();$('refundResult').replaceChildren();$('splitResult').replaceChildren();};
 $('refundForm').onsubmit=e=>{e.preventDefault();action(async t=>{const reference=$('detailReference').value;if(!/^[A-Za-z0-9_-]{1,64}$/.test(reference))throw Error('先输入订单编号');const r=await call('refund_record',{reference,event_id:$('refundEvent').value,amount_minor:Number($('refundAmount').value)},t);if(reference!==$('detailReference').value)return;await detail(t);if(t===epoch&&reference===$('detailReference').value)$('refundResult').textContent='退款预审已记录，未执行微信退款。'+JSON.stringify(r);});};
 $('splitForm').onsubmit=e=>{e.preventDefault();action(async t=>{const shares=Object.create(null);const lines=$('splitShares').value.trim().split(/\n/);if(lines.length>20)throw Error('接收方过多');for(const line of lines){const parts=line.split(',').map(s=>s.trim());if(parts.length!==2||!parts[0]||Object.hasOwn(shares,parts[0])||!/^\d+$/.test(parts[1]))throw Error('接收方格式错误或重复');shares[parts[0]]=Number(parts[1]);}const reference=$('detailReference').value;const r=await call('split_preview',{reference,shares_bps:shares},t);if(t!==epoch||reference!==$('detailReference').value)return;$('splitResult').replaceChildren();article('splitResult','可分配金额（分）：'+r.allocatable_minor+'；退款预审（分）：'+r.refund_preview_minor);for(const [name,amount] of Object.entries(r.allocations_minor))article('splitResult',name+'：'+amount+' 分');});};
 $('reconcile').onclick=()=>action(async t=>{const r=await call('reconciliation',{},t);if(t===epoch)$('finance').textContent=JSON.stringify(r,null,2);});
 async function providerAction(t,operation,params){const context=config;if(!context?.providerWorkspace)throw Error('当前账号未配置财务处理工作台');const response=await fetch('/community/provider-actions',{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',headers:{'Content-Type':'application/json','X-CSRF-Token':context.csrf},body:JSON.stringify({workspace:context.providerWorkspace,operation,params})});if(t!==epoch)throw Error('身份已变化');const data=await response.json();if(t!==epoch)throw Error('身份已变化');if(!response.ok)throw Error('请求未确认，请保留原申请编号并查询，不要重复提交');$('providerActionResult').textContent=JSON.stringify(data.result,null,2);return data.result;}
 const providerReference=()=>({reference:$('providerOrder').value,request_id:$('providerRequest').value});
 $('newProviderRequest').onclick=()=>{if(busy)return;$('providerRequest').value='pa_'+crypto.randomUUID().replaceAll('-','');$('providerActionResult').replaceChildren();};
 $('providerRefundForm').onsubmit=e=>{e.preventDefault();action(t=>providerAction(t,'refund',{...providerReference(),amount_minor:Number($('providerRefundAmount').value),reason:$('providerRefundReason').value}));};
 $('queryProviderRefund').onclick=()=>action(t=>providerAction(t,'query_refund',providerReference()));$('statusProviderRefund').onclick=()=>action(t=>providerAction(t,'status_refund',providerReference()));
 $('loadReceivers').onclick=()=>action(async t=>{const r=await providerAction(t,'receivers',{});if(t!==epoch)return;$('providerReceivers').replaceChildren();for(const receiver of r.receivers){const label=document.createElement('label');label.textContent=receiver.label+' · '+receiver.id+'（分）';const input=document.createElement('input');input.type='number';input.min='0';input.step='1';input.value='0';input.dataset.receiver=receiver.id;label.append(input);$('providerReceivers').append(label);}});
 $('providerSplitForm').onsubmit=e=>{e.preventDefault();action(t=>{const allocations=Object.fromEntries([...$('providerReceivers').querySelectorAll('input')].filter(input=>Number(input.value)>0).map(input=>[input.dataset.receiver,Number(input.value)]));return providerAction(t,'split',{...providerReference(),allocations,description:$('providerSplitDescription').value,unfreeze_unsplit:$('unfreezeUnsplit').checked});});};
 $('queryProviderSplit').onclick=()=>action(t=>providerAction(t,'query_split',providerReference()));$('statusProviderSplit').onclick=()=>action(t=>providerAction(t,'status_split',providerReference()));
 $('ruleForm').onsubmit=e=>{e.preventDefault();action(t=>{const shares=Object.create(null);for(const line of $('ruleShares').value.trim().split(/\n/)){const parts=line.split(',').map(s=>s.trim());if(parts.length!==2||!parts[0]||Object.hasOwn(shares,parts[0])||!/^\d+$/.test(parts[1]))throw Error('规则格式错误');shares[parts[0]]=Number(parts[1]);}return providerAction(t,'rule_create',{rule_id:$('ruleId').value,version:Number($('ruleVersion').value),shares_bps:shares,description:$('ruleDescription').value,unfreeze_unsplit:$('ruleUnfreeze').checked});});};
 $('activeRule').onclick=()=>action(async t=>{const r=await providerAction(t,'rule_active',{});if(t===epoch)$('ruleRevision').value=r?.revision||0;});
 $('activateRule').onclick=()=>action(t=>providerAction(t,'rule_activate',{rule_id:$('ruleId').value,version:Number($('ruleVersion').value),expected_revision:Number($('ruleRevision').value)}));
 $('freezeRule').onclick=()=>action(t=>providerAction(t,'rule_freeze',{reference:$('providerOrder').value}));
 $('snapshotRule').onclick=()=>action(t=>providerAction(t,'rule_snapshot',{reference:$('providerOrder').value}));
 $('executeRule').onclick=()=>action(t=>providerAction(t,'split_by_rule',providerReference()));
 async function commerce(t,operation,params){const auth=config;if(!auth)throw Error('客户中心登录已失效');const response=await fetch('/community/commerce',{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',headers:{'Content-Type':'application/json','X-CSRF-Token':auth.csrf},body:JSON.stringify({workspace:auth.workspace,operation,params})});const data=await response.json();if(t!==epoch)throw Error('身份已变化');if(!response.ok)throw Error('价格保存未确认，请读取最新版本后核对');$('priceResult').textContent=JSON.stringify(data.result,null,2);return data.result;}
 $('priceForm').onsubmit=e=>{e.preventDefault();action(async t=>{const r=await commerce(t,'price_set',{item_id:$('priceItem').value,expected_revision:Number($('priceRevision').value),unit_minor:Number($('priceUnit').value),stock:Number($('priceStock').value),enabled:$('priceEnabled').checked});if(t===epoch)$('priceRevision').value=r.revision;});};
 $('readPrice').onclick=()=>action(async t=>{const r=await commerce(t,'price_read',{item_id:$('priceItem').value});if(t!==epoch)return;$('priceRevision').value=r?.revision||0;if(r){$('priceUnit').value=r.unit_minor;$('priceStock').value=r.stock;$('priceEnabled').checked=r.enabled;}});
 $('readRefundApplication').onclick=()=>action(async t=>{const r=await commerce(t,'refund_application_read',{application_id:$('refundApplicationId').value});if(t===epoch){$('refundApplicationRevision').value=r.revision;$('refundApplicationResult').textContent=JSON.stringify(r,null,2);}});
 $('decideRefundApplication').onclick=()=>action(async t=>{const r=await commerce(t,'refund_decide',{application_id:$('refundApplicationId').value,expected_revision:Number($('refundApplicationRevision').value),decision:$('refundApplicationDecision').value,opinion:$('refundApplicationOpinion').value});if(t===epoch){$('refundApplicationRevision').value=r.revision;$('refundApplicationResult').textContent=JSON.stringify(r,null,2);}});
 $('executeRefundApplication').onclick=()=>action(t=>providerAction(t,'execute_refund_application',{application_id:$('refundApplicationId').value}));
 $('queryRefundApplication').onclick=()=>action(t=>providerAction(t,'query_refund_application',{application_id:$('refundApplicationId').value}));
 $('splitReturnForm').onsubmit=e=>{e.preventDefault();action(t=>providerAction(t,'split_return',{...providerReference(),receiver_id:$('returnReceiver').value,amount_minor:Number($('returnAmount').value),description:$('returnDescription').value}));};
 $('querySplitReturn').onclick=()=>action(t=>providerAction(t,'query_split_return',providerReference()));
 $('statusSplitReturn').onclick=()=>action(t=>providerAction(t,'status_split_return',providerReference()));
 $('staffInviteForm').onsubmit=e=>{e.preventDefault();action(async t=>{const r=await call('staff_invite',{email:$('staffEmail').value,project_role:$('staffProjectRole').value},t);if(t===epoch)$('staffResult').textContent=JSON.stringify(r,null,2);});};
 $('staffGrantForm').onsubmit=e=>{e.preventDefault();action(async t=>{const operations=[];if($('staffOrders').checked)operations.push('community.orders','community.orders_page','community.order_detail');if($('staffSummary').checked)operations.push('community.summary');if($('staffSettings').checked)operations.push('community.merchant_settings');const r=await call('staff_grant',{user_id:$('staffUser').value,operations},t);if(t===epoch)$('staffResult').textContent=JSON.stringify(r,null,2);});};
 $('staffList').onclick=()=>action(async t=>{const r=await call('staff_list',{after_id:''},t);if(t===epoch)$('staffResult').textContent=JSON.stringify(r,null,2);});
 $('staffRemove').onclick=()=>action(async t=>{const r=await call('staff_remove',{workspace:$('staffWorkspace').value},t);if(t===epoch)$('staffResult').textContent=JSON.stringify(r,null,2);});
 async function fundsPage(t,kind,after_id=''){const r=await providerAction(t,'financial_records',{kind,after_id});if(t!==epoch)return;financialPage=r.has_more?{kind,after_id:r.next_cursor}:null;$('financialMore').hidden=!financialPage;}
 $('financialRecords').onclick=()=>action(t=>fundsPage(t,$('financialKind').value));
 $('financialMore').onclick=()=>action(t=>financialPage&&fundsPage(t,financialPage.kind,financialPage.after_id));
 $('reconcileOrder').onclick=()=>action(t=>providerAction(t,'reconcile_order',{reference:$('providerOrder').value}));
 $('readReconciliation').onclick=()=>action(t=>providerAction(t,'reconciliation_read',{reference:$('providerOrder').value}));
 $('listStores').onclick=()=>action(async t=>{const r=await call('stores',{},t);if(t!==epoch)return;$('storeList').replaceChildren();for(const store of r.stores){const a=document.createElement('article');a.textContent=(store.profile?.name||'尚未创建资料')+' · '+store.workspace;const b=document.createElement('button');b.textContent='编辑资料';b.onclick=()=>{if(busy)return;$('storeWorkspace').value=store.workspace;$('storeName').value=store.profile?.name||'';$('storeDescription').value=store.profile?.description||'';$('storeContact').value=store.profile?.contact||'';$('storeState').value=store.profile?.status||'PAUSED';$('storeVersion').value=store.profile?.version||'';};a.append(b);$('storeList').append(a);}});
 $('storeForm').onsubmit=e=>{e.preventDefault();action(async t=>{const r=await call('store_save',{store_workspace:$('storeWorkspace').value,record:{name:$('storeName').value,description:$('storeDescription').value,contact:$('storeContact').value,status:$('storeState').value},expected_version:$('storeVersion').value?Number($('storeVersion').value):null},t);if(t===epoch){$('storeVersion').value=r.version;$('storeResult').textContent=JSON.stringify(r,null,2);}});};
 $('completeOrder').onclick=()=>action(async t=>{const r=await commerce(t,'order_complete',{reference:$('detailReference').value,expected_revision:Number($('completionRevision').value),note:$('completionNote').value});if(t===epoch)$('completionRevision').value=r.fulfillment_revision;});
 let billPage=null,billAuditPage=null;
 function billParams(){return {kind:$('billKind').value,bill_date:$('billDate').value};}
 async function billAction(t,operation,params){
  const result=await providerAction(t,operation,params);
  if(t===epoch)$('billResult').textContent=JSON.stringify(result,null,2);
  return result;
 }
 $('fetchBill').onclick=()=>action(t=>billAction(t,'bill_fetch',billParams()));
 async function billRows(t,params,offset){
  const result=await billAction(t,'bill_rows',{...params,offset});
  if(t!==epoch)return;
  billPage=result.has_more?{params,offset:result.next_offset}:null;
  $('moreBill').hidden=!billPage;
 }
 $('readBill').onclick=()=>action(t=>billRows(t,billParams(),0));
 $('moreBill').onclick=()=>action(t=>billPage&&billRows(t,billPage.params,billPage.offset));
 $('reconcileBill').onclick=()=>action(t=>billAction(t,'bill_reconcile',billParams()));
 async function billAudit(t,params,after_id=''){
  const result=await billAction(t,'bill_audit',{...params,after_id});
  if(t!==epoch)return;
  billAuditPage=result.has_more?{params,after_id:result.next_cursor}:null;
  $('moreBillAudit').hidden=!billAuditPage;
 }
 $('billAudit').onclick=()=>action(t=>billAudit(t,billParams()));
 $('moreBillAudit').onclick=()=>action(t=>billAuditPage&&billAudit(t,billAuditPage.params,billAuditPage.after_id));
 window.configureCommunityWorkbench(null);
})();
