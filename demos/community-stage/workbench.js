'use strict';
(()=>{
 const $=id=>document.getElementById(id);let epoch=0,config=null,busy=false,profileVersion=null,orderCursor=null,orderAfter='',reportCursor=null,reportWindow=null,adCursor=null,itemCursor=null;
 let financialPage=null,financialPages=new Map(),providerSelection=0,refundPage=null,refundSelection=0,detailSelection=0,staffPage=null,activeAction=null;
 const clear=()=>{for(const id of ['orders','items','ads','report','summary','finance','orderDetail','refundResult','splitResult','providerReceivers','providerActionResult','priceResult','refundApplicationResult','staffResult','storeList','storeResult','billResult','refundApplications','orderLines','staffRecords'])$(id).replaceChildren();for(const f of document.querySelectorAll('form'))f.reset();$('providerOrder').value='';$('providerRequest').value='';$('providerActions').hidden=true;clearStaffSelection();staffPage=null;$('moreStaff').hidden=true;profileVersion=null;orderCursor=null;orderAfter='';reportCursor=null;reportWindow=null;$('moreOrders').hidden=true;$('moreReport').hidden=true;$('moreAds').hidden=true;adCursor=null;itemCursor=null;$('moreItems').hidden=true;financialPage=null;financialPages.clear();providerSelection++;$('financialMore').hidden=true;billPage=null;billAuditPage=null;refundPage=null;clearRefundSelection();clearOrderLines();$('refundApplicationDecision').value='APPROVED';detailSelection++;$('moreRefundApplications').hidden=true;$('moreBill').hidden=true;$('moreBillAudit').hidden=true;};
 const status=message=>{$('notice').textContent=message;};
 window.configureCommunityWorkbench=value=>{
  epoch++;config=value&&typeof value.csrf==='string'&&value.csrf&&/^[A-Za-z0-9_-]{1,64}$/.test(value.workspace)?{csrf:value.csrf,workspace:value.workspace,providerWorkspace:typeof value.providerWorkspace==='string'&&/^[A-Za-z0-9_-]{1,64}$/.test(value.providerWorkspace)?value.providerWorkspace:null,merchantBillWorkspace:typeof value.merchantBillWorkspace==='string'&&/^[A-Za-z0-9_-]{1,64}$/.test(value.merchantBillWorkspace)?value.merchantBillWorkspace:null}:null;
  clear();clearObservation();$('providerActions').hidden=!config?.providerWorkspace;$('billSection').hidden=!(config?.providerWorkspace||config?.merchantBillWorkspace);$('billScope').value=config?.providerWorkspace?'STORE':'MERCHANT';busy=false;for(const b of document.querySelectorAll('button'))b.disabled=!config;status(config?'工作台已连接当前客户中心身份':'请从客户中心登录并打开授权工作台');
 };
 const call=async(op,params,ticket)=>{
  const auth=config;if(!auth)throw Error('请从客户中心打开工作台');
  const response=await fetch('/community/operations',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':auth.csrf},credentials:'same-origin',cache:'no-store',redirect:'error',body:JSON.stringify({workspace:auth.workspace,operation:'community.'+op,params})});
  if(ticket!==epoch)throw Error('身份已变化');
  const data=await response.json();if(ticket!==epoch)throw Error('身份已变化');
  if(!response.ok)throw Error(response.status===403?'当前账号无此权限，或入驻需重新核验':'操作失败或结果未知，请刷新确认后再操作');
  return data.result;
 };
 const action=async(fn,context=null)=>{if(busy||!config)return;busy=true;const ticket=epoch,task={context};activeAction=task;for(const b of document.querySelectorAll('button'))b.disabled=true;
  try{await fn(ticket);if(ticket===epoch&&activeAction===task)status('操作完成');}catch(e){if(ticket===epoch&&activeAction===task)status(e.message);}finally{if(ticket===epoch&&activeAction===task){activeAction=null;busy=false;for(const b of document.querySelectorAll('button'))b.disabled=false;}}};
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
 async function settings(t,after=''){const r=await call('merchant_settings',after?{after_id:after}:{},t);if(t!==epoch)return;if(!after){profileVersion=r.profile?.version??null;if(r.profile){for(const k of ['name','description','contact'])$(k).value=r.profile[k];$('profileStatus').value=r.profile.status;}$('items').replaceChildren();}for(const item of r.items){const a=article('items',item.id+' · '+item.name+' · '+item.status);a.append(button('编辑',async()=>{$('itemId').value=item.id;$('itemName').value=item.name;$('itemSort').value=item.sort;$('itemStatus').value=item.status;}));}itemCursor=r.has_more?r.next_cursor:null;$('moreItems').hidden=!itemCursor;}
 $('loadSettings').onclick=()=>action(t=>settings(t));
 $('moreItems').onclick=()=>action(t=>itemCursor&&settings(t,itemCursor));
 $('profileForm').onsubmit=e=>{e.preventDefault();action(async t=>{await call('profile',{record:{name:$('name').value,description:$('description').value,contact:$('contact').value,status:$('profileStatus').value},expected_version:profileVersion},t);await settings(t);});};
 $('itemForm').onsubmit=e=>{e.preventDefault();action(async t=>{await call('item',{item:{id:$('itemId').value,name:$('itemName').value,status:$('itemStatus').value,sort:Number($('itemSort').value)}},t);await settings(t);});};
 async function ads(t,after=''){const r=await call('ads_page',{limit:50,after_id:after},t);if(t!==epoch)return;$('ads').replaceChildren();adCursor=r.next_cursor;$('moreAds').hidden=!r.has_more;for(const c of r.campaigns){const a=article('ads',c.id+' · '+c.slot+' · '+c.status+' · 审核 '+c.moderation+' · 版本 '+c.version);for(const state of ({DRAFT:['REVIEW'],REVIEW:c.moderation==='APPROVED'?['APPROVED']:c.moderation==='REJECTED'?['REJECTED']:[],APPROVED:['ACTIVE','ARCHIVED'],ACTIVE:['PAUSED','ARCHIVED'],PAUSED:['ACTIVE','ARCHIVED'],REJECTED:['REVIEW','ARCHIVED'],ARCHIVED:[]}[c.status]||[]))a.append(button(state,async n=>{await call('ad_state',{campaign_id:c.id,state,expected_version:c.version},n);await ads(n);}));if(['REVIEW','APPROVED','PAUSED'].includes(c.status))for(const approved of [true,false])a.append(button(approved?'平台审核通过':'平台审核驳回',async n=>{await call('ad_review',{campaign_id:c.id,approved,expected_version:c.version},n);await ads(n);}));}}
 $('loadAds').onclick=()=>action(ads);$('moreAds').onclick=()=>action(t=>ads(t,adCursor));
 const seconds=id=>Math.floor(new Date($(id).value).getTime()/1000);
 $('adForm').onsubmit=e=>{e.preventDefault();action(async t=>{await call('ad_create',{record:{id:$('adId').value,title:$('adTitle').value,target_url:$('adUrl').value,slot:$('adSlot').value,starts_at:seconds('adStart'),ends_at:seconds('adEnd'),priority:Number($('adPriority').value)}},t);await ads(t);});};
 async function report(t,after=''){const window=after?reportWindow:{starts_at:seconds('reportStart'),ends_at:seconds('reportEnd')};const r=await call('ad_report',{...window,limit:50,after_id:after},t);if(t!==epoch)return;reportWindow=window;$('report').replaceChildren();for(const c of r.campaigns)article('report',c.id+' · 展示 '+c.impressions+' · 点击 '+c.clicks+' · 点击率 '+(c.click_rate===null?'无展示基数':(c.click_rate*100).toFixed(2)+'%'));reportCursor=r.next_cursor;$('moreReport').hidden=!r.has_more;}
 $('loadReport').onclick=()=>action(t=>report(t));$('moreReport').onclick=()=>action(t=>report(t,reportCursor));
 async function detail(t){const selection=++detailSelection;clearOrderLines();const reference=$('detailReference').value;const r=await call('order_detail',{reference},t);if(t!==epoch||selection!==detailSelection||reference!==$('detailReference').value)return;$('orderDetail').textContent=JSON.stringify(r,null,2);$('refundResult').replaceChildren();$('splitResult').replaceChildren();await orderLines(t,reference,selection);}
 $('detailForm').onsubmit=e=>{e.preventDefault();action(detail);};
 $('detailReference').oninput=()=>{detailSelection++;clearOrderLines();$('orderDetail').replaceChildren();$('refundResult').replaceChildren();$('splitResult').replaceChildren();};
 $('refundForm').onsubmit=e=>{e.preventDefault();action(async t=>{const reference=$('detailReference').value;if(!/^[A-Za-z0-9_-]{1,64}$/.test(reference))throw Error('先输入订单编号');const r=await call('refund_record',{reference,event_id:$('refundEvent').value,amount_minor:Number($('refundAmount').value)},t);if(reference!==$('detailReference').value)return;await detail(t);if(t===epoch&&reference===$('detailReference').value)$('refundResult').textContent='退款预审已记录，未执行微信退款。'+JSON.stringify(r);});};
 $('splitForm').onsubmit=e=>{e.preventDefault();action(async t=>{const shares=Object.create(null);const lines=$('splitShares').value.trim().split(/\n/);if(lines.length>20)throw Error('接收方过多');for(const line of lines){const parts=line.split(',').map(s=>s.trim());if(parts.length!==2||!parts[0]||Object.hasOwn(shares,parts[0])||!/^\d+$/.test(parts[1]))throw Error('接收方格式错误或重复');shares[parts[0]]=Number(parts[1]);}const reference=$('detailReference').value;const r=await call('split_preview',{reference,shares_bps:shares},t);if(t!==epoch||reference!==$('detailReference').value)return;$('splitResult').replaceChildren();article('splitResult','可分配金额（分）：'+r.allocatable_minor+'；退款预审（分）：'+r.refund_preview_minor);for(const [name,amount] of Object.entries(r.allocations_minor))article('splitResult',name+'：'+amount+' 分');});};
 $('reconcile').onclick=()=>action(async t=>{const r=await call('reconciliation',{},t);if(t===epoch)$('finance').textContent=JSON.stringify(r,null,2);});
 let observationRevision=0;
 const financialTitle={REFUND:'退款观察',SPLIT:'分账请求',RETURN:'分账回退',RECONCILIATION:'对账记录与异常'};
 function clearObservation(){
  observationRevision++;
  $('financialObservation').hidden=true;$('financialObservationList').replaceChildren();$('financialObservationDetail').replaceChildren();
  $('financialObservationTitle').textContent='';$('financialObservationScope').textContent='';$('financialObservationDetail').hidden=true;$('financialObservationBack').hidden=true;$('financialObservationList').hidden=false;$('providerActionResult').hidden=false;
 }
 const observedText=value=>value===undefined||value===null?'原记录未返回':String(value);
 const minorText=(amount,currency)=>Number.isSafeInteger(amount)?String(amount)+' 最小货币单位'+(typeof currency==='string'&&currency?' · '+currency:'（原记录未返回币种）'):'摘要未提供金额，不以订单金额代替';
 function observationFields(kind,r,detail){
  const fields=kind==='RECONCILIATION'?[['订单引用',r.reference],['观察状态',r.status],['本地订单状态',r.local_order_state],['服务商状态',r.provider_state]]:
   [['分组',financialTitle[kind]],['请求编号',r.request_id],['关联订单',r.reference],['请求状态',r.status]];
  if(detail){
   if(kind==='RECONCILIATION')fields.push(['原订单金额',minorText(r.original_amount_minor,r.currency)],['已确认本地退款',minorText(r.confirmed_local_refunds_minor,r.currency)],['异常条目',Array.isArray(r.anomalies)?r.anomalies.length?r.anomalies.join('；'):'原观察未报告异常':'原记录未返回'],['范围',r.coverage==='ORDER_OBSERVATIONS_ONLY'?'仅订单观察，不是全量日账单':r.coverage],['日账单核对',r.daily_bill_reconciled===true?'原记录标记已核对':r.daily_bill_reconciled===false?'未完成':'原记录未返回'],['财务核销',r.finance_status==='UNCONFIRMED'?'未确认':r.finance_status]);
   else{if(kind==='RETURN')fields.push(['接收方编号',r.receiver_id]);fields.push(['服务商响应',r.provider_response_verified===true?'响应已验证；不等于到账或财务核销':r.provider_response_verified===false?'未验证':'原记录未返回'],['金额信息',minorText(r.amount_minor,r.currency)],['财务核销',r.finance_status==='UNCONFIRMED'?'未确认':r.finance_status],['自动重试','此观察界面不提供资金重试操作']);}
  }
  return fields;
 }
 function observationCard(title,fields){const card=document.createElement('article');card.className='financial-record-card';const heading=document.createElement('h4');heading.textContent=title;card.append(heading);const dl=document.createElement('dl');for(const [label,value]of fields){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=observedText(value);dl.append(dt,dd);}card.append(dl);return card;}
 function showObservations(kind,records,result){
  clearObservation();const ticket=epoch,selection=providerSelection,view=observationRevision;
  $('financialObservation').hidden=false;$('providerActionResult').hidden=true;$('financialObservationTitle').textContent=financialTitle[kind];
  $('financialObservationScope').textContent=kind==='RECONCILIATION'?'原订单既有观察快照；不是日账单、到账或财务核销结论。':'当前权限本页记录；财务核销未确认。分账回退与消费者退款分别显示。';
  if(!records.length){$('financialObservationList').textContent=result.has_more?'当前页没有可见记录，仍有下一页可读取。':'当前范围没有可见记录。';return;}
  for(const r of records){const card=observationCard('记录列表 · 当前范围',observationFields(kind,r,false)),open=document.createElement('button');open.className='financial-wide';open.textContent='查看详情';open.onclick=()=>{if(busy||ticket!==epoch||selection!==providerSelection||view!==observationRevision)return;$('financialObservationList').hidden=true;$('financialObservationDetail').replaceChildren(observationCard('记录详情',observationFields(kind,r,true)));$('financialObservationDetail').hidden=false;$('financialObservationTitle').textContent=financialTitle[kind]+'详情';$('financialObservationBack').hidden=false;};$('financialObservationList').append(card,open);}
  $('financialObservationBack').onclick=()=>{if(ticket!==epoch||selection!==providerSelection||view!==observationRevision)return;$('financialObservationDetail').replaceChildren();$('financialObservationDetail').hidden=true;$('financialObservationList').hidden=false;$('financialObservationBack').hidden=true;$('financialObservationTitle').textContent=financialTitle[kind];};
 }
 function clearProviderResult(){ $('providerActionResult').replaceChildren();clearObservation(); }
 function clearFinancialPages(){financialPage=null;financialPages.clear();$('financialMore').hidden=true;}
 let providerSelectionKey='';
 function providerChanged(){
  const key=JSON.stringify([$ ('providerOrder').value,$('providerRequest').value,$('financialKind').value]);
  if(key===providerSelectionKey)return;providerSelectionKey=key;providerSelection++;clearProviderResult();
  financialPage=financialPages.get($('financialKind').value)||null;$('financialMore').hidden=!financialPage;
  // Do not unlock an in-flight funds action or create a new request identifier.
 }
 for(const id of ['providerOrder','providerRequest','financialKind']){$(id).oninput=providerChanged;$(id).onchange=providerChanged;}
 async function providerAction(t,operation,params,current=()=>true){
  providerChanged();const selection=providerSelection,valid=()=>t===epoch&&selection===providerSelection&&current();
  if(!valid())throw Error('当前选择已变化');clearProviderResult();
  const context=config;if(!context?.providerWorkspace)throw Error('当前账号未配置财务处理工作台');
  try{
   const response=await fetch('/community/provider-actions',{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',headers:{'Content-Type':'application/json','X-CSRF-Token':context.csrf},body:JSON.stringify({workspace:context.providerWorkspace,operation,params})});
   if(!valid())throw Error('当前选择已变化');
   if(!response.ok)throw Error('请求未确认，请保留原申请编号并查询，不要重复提交');
   const data=await response.json();if(!valid())throw Error('当前选择已变化');
   if(!data||!Object.prototype.hasOwnProperty.call(data,'result'))throw Error('响应未确认，请按原编号查询，不要重复提交');
   if(!operation.startsWith('bill_'))$('providerActionResult').textContent=JSON.stringify(data.result,null,2);if(operation==='reconciliation_read'&&data.result&&typeof data.result==='object')showObservations('RECONCILIATION',[data.result],data.result);return data.result;
  }catch(error){if(valid()){clearProviderResult();clearFinancialPages();}throw Error(valid()?'请求未确认，请保留原申请编号并查询，不要重复提交':'当前选择已变化');}
 }
 const providerReference=()=>({reference:$('providerOrder').value,request_id:$('providerRequest').value});
 $('newProviderRequest').onclick=()=>{if(busy)return;$('providerRequest').value='pa_'+crypto.randomUUID().replaceAll('-','');providerChanged();};
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
 async function commerce(t,operation,params){if(t!==epoch)throw Error('身份已变化');const auth=config;if(!auth)throw Error('客户中心登录已失效');const response=await fetch('/community/commerce',{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',headers:{'Content-Type':'application/json','X-CSRF-Token':auth.csrf},body:JSON.stringify({workspace:auth.workspace,operation,params})});const data=await response.json();if(t!==epoch)throw Error('身份已变化');if(!response.ok)throw Error('操作未确认，请读取原记录核对；不要重复提交。');if(operation.startsWith('price_'))$('priceResult').textContent=JSON.stringify(data.result,null,2);return data.result;}
 $('priceForm').onsubmit=e=>{e.preventDefault();action(async t=>{const r=await commerce(t,'price_set',{item_id:$('priceItem').value,expected_revision:Number($('priceRevision').value),unit_minor:Number($('priceUnit').value),stock:Number($('priceStock').value),enabled:$('priceEnabled').checked});if(t===epoch)$('priceRevision').value=r.revision;});};
 $('readPrice').onclick=()=>action(async t=>{const r=await commerce(t,'price_read',{item_id:$('priceItem').value});if(t!==epoch)return;$('priceRevision').value=r?.revision||0;if(r){$('priceUnit').value=r.unit_minor;$('priceStock').value=r.stock;$('priceEnabled').checked=r.enabled;}});
 function clearRefundSelection(){refundSelection++;$('refundApplicationId').value='';$('refundApplicationRevision').value='';$('refundApplicationOpinion').value='';$('refundApplicationResult').replaceChildren();}
 async function refundApplications(t,after_id=''){
  clearRefundSelection();refundPage=null;$('moreRefundApplications').hidden=true;$('refundApplications').replaceChildren();
  const r=await commerce(t,'refund_applications',{after_id});if(t!==epoch)return;
  for(const record of r.records){const a=article('refundApplications',record.application_id+' · '+record.reference+' · '+record.amount_minor+' 分 · '+record.status+' · '+record.reason);a.append(button('读取原申请',async n=>{clearRefundSelection();$('refundApplicationId').value=record.application_id;await readRefundApplication(n);}));}
  refundPage=r.has_more?r.next_cursor:null;$('moreRefundApplications').hidden=!refundPage;
  if(!r.records.length)$('refundApplications').textContent=r.has_more?'本页暂未找到退款申请，仍有记录待查，请点击下一页。':'已到末页，本页没有退款申请。';
 }
 $('loadRefundApplications').onclick=()=>action(t=>refundApplications(t));
 $('moreRefundApplications').onclick=()=>action(t=>refundPage&&refundApplications(t,refundPage));
 $('refundApplicationId').oninput=()=>{refundSelection++;$('refundApplicationRevision').value='';$('refundApplicationResult').replaceChildren();$('refundApplicationOpinion').value='';};
 async function readRefundApplication(t){const id=$('refundApplicationId').value,selection=++refundSelection;$('refundApplicationResult').replaceChildren();$('refundApplicationRevision').value='';const r=await commerce(t,'refund_application_read',{application_id:id});if(t!==epoch||selection!==refundSelection||id!==$('refundApplicationId').value)return;$('refundApplicationRevision').value=r.revision;$('refundApplicationResult').textContent=JSON.stringify(r,null,2);}
 $('readRefundApplication').onclick=()=>action(readRefundApplication);
 $('decideRefundApplication').onclick=()=>action(async t=>{
  const id=$('refundApplicationId').value,selection=refundSelection,revision=Number($('refundApplicationRevision').value);if(!Number.isSafeInteger(revision)||revision<1)throw Error('先读取原申请及当前修订号');
  $('refundApplicationResult').textContent='审核结果待核对；结果未知时请读取原申请，不要重复提交。';
  const r=await commerce(t,'refund_decide',{application_id:id,expected_revision:revision,decision:$('refundApplicationDecision').value,opinion:$('refundApplicationOpinion').value});
  if(t===epoch&&selection===refundSelection&&id===$('refundApplicationId').value){$('refundApplicationRevision').value=r.revision;$('refundApplicationResult').textContent='仅保存审核决定，未执行退款。\n'+JSON.stringify(r,null,2);}
 });
 $('executeRefundApplication').onclick=()=>action(t=>providerAction(t,'execute_refund_application',{application_id:$('refundApplicationId').value}));
 $('queryRefundApplication').onclick=()=>action(t=>providerAction(t,'query_refund_application',{application_id:$('refundApplicationId').value}));
 $('splitReturnForm').onsubmit=e=>{e.preventDefault();action(t=>providerAction(t,'split_return',{...providerReference(),receiver_id:$('returnReceiver').value,amount_minor:Number($('returnAmount').value),description:$('returnDescription').value}));};
 $('querySplitReturn').onclick=()=>action(t=>providerAction(t,'query_split_return',providerReference()));
 $('statusSplitReturn').onclick=()=>action(t=>providerAction(t,'status_split_return',providerReference()));
 $('staffInviteForm').onsubmit=e=>{e.preventDefault();action(async t=>{const r=await call('staff_invite',{email:$('staffEmail').value,project_role:$('staffProjectRole').value},t);if(t===epoch)$('staffResult').textContent=JSON.stringify(r,null,2);});};
 $('staffGrantForm').onsubmit=e=>{e.preventDefault();action(async t=>{const operations=[];if($('staffOrders').checked)operations.push('community.orders');if($('staffOrderPages').checked)operations.push('community.orders_page');if($('staffOrderDetail').checked)operations.push('community.order_detail');if($('staffSummary').checked)operations.push('community.summary');if($('staffSettings').checked)operations.push('community.merchant_settings');const user_id=$('staffUser').value;await staffMutation(t,'staff_grant',{user_id,operations});});};
 const staffPermissions={staffOrders:'community.orders',staffOrderPages:'community.orders_page',staffOrderDetail:'community.order_detail',staffSummary:'community.summary',staffSettings:'community.merchant_settings'};
 function clearStaffSelection(){$('staffUser').value='';$('staffWorkspace').value='';$('staffSelected').textContent='';for(const id of Object.keys(staffPermissions))$(id).checked=false;}
 async function staffList(t,after_id=''){
  clearStaffSelection();$('staffResult').replaceChildren();$('staffRecords').replaceChildren();staffPage=null;$('moreStaff').hidden=true;
  const r=await call('staff_list',{after_id},t);if(t!==epoch)return;
  for(const record of r.records){const a=article('staffRecords',record.user_id+' · '+record.workspace+' · '+(record.active?'有效':'已撤销')+' · '+record.operations.join('、'));
   a.append(button('选择员工',async n=>{if(n!==epoch)return;clearStaffSelection();$('staffUser').value=record.user_id;$('staffWorkspace').value=record.workspace;$('staffSelected').textContent=record.active?'当前门店授权有效':'当前门店授权已撤销；保存权限会重新授权';for(const [id,operation]of Object.entries(staffPermissions))$(id).checked=record.operations.includes(operation);}));
  }
  staffPage=r.has_more?r.next_cursor:null;$('moreStaff').hidden=!staffPage;
  if(!r.records.length)$('staffRecords').textContent=r.has_more?'本页没有当前门店员工，仍有记录待查，请点击下一页。':'已到末页，本页没有当前门店员工。';
 }
 $('staffList').onclick=()=>action(t=>staffList(t));
 $('moreStaff').onclick=()=>action(t=>staffPage&&staffList(t,staffPage));
 async function staffMutation(t,operation,params){
  clearStaffSelection();$('staffRecords').replaceChildren();staffPage=null;$('moreStaff').hidden=true;
  $('staffResult').textContent='权限变更结果待确认，请重新读取门店员工核对，不要重复提交。';
  const r=await call(operation,params,t);if(t!==epoch)return;
  $('staffResult').textContent='权限变更已记录，请重新读取门店员工确认当前状态。\n'+JSON.stringify(r,null,2);
 }
 $('staffRemove').onclick=()=>action(t=>staffMutation(t,'staff_remove',{workspace:$('staffWorkspace').value}));
 async function fundsPage(t,kind,after_id=''){
  providerChanged();const selection=providerSelection,current=()=>selection===providerSelection&&kind===$('financialKind').value;
  financialPages.delete(kind);financialPage=null;$('financialMore').hidden=true;
  const r=await providerAction(t,'financial_records',{kind,after_id},current);if(t!==epoch||!current())return;
  if(!r||!Array.isArray(r.records)||typeof r.has_more!=='boolean'||r.has_more&&(typeof r.next_cursor!=='string'||!r.next_cursor||r.next_cursor===after_id)){clearProviderResult();clearFinancialPages();throw Error('财务列表响应未确认，请重新读取');}
  showObservations(kind,r.records,r);financialPage=r.has_more?{kind,after_id:r.next_cursor}:null;
  if(financialPage)financialPages.set(kind,financialPage);$('financialMore').hidden=!financialPage;
 }
 $('financialRecords').onclick=()=>action(t=>fundsPage(t,$('financialKind').value));
 $('financialMore').onclick=()=>action(t=>financialPage&&financialPage.kind===$('financialKind').value&&fundsPage(t,financialPage.kind,financialPage.after_id));
 $('reconcileOrder').onclick=()=>action(t=>providerAction(t,'reconcile_order',{reference:$('providerOrder').value}));
 $('readReconciliation').onclick=()=>action(t=>providerAction(t,'reconciliation_read',{reference:$('providerOrder').value}));
 $('listStores').onclick=()=>action(async t=>{const r=await call('stores',{},t);if(t!==epoch)return;$('storeList').replaceChildren();for(const store of r.stores){const a=document.createElement('article');a.textContent=(store.profile?.name||'尚未创建资料')+' · '+store.workspace;const b=document.createElement('button');b.textContent='编辑资料';b.onclick=()=>{if(busy)return;$('storeWorkspace').value=store.workspace;$('storeName').value=store.profile?.name||'';$('storeDescription').value=store.profile?.description||'';$('storeContact').value=store.profile?.contact||'';$('storeState').value=store.profile?.status||'PAUSED';$('storeVersion').value=store.profile?.version||'';};a.append(b);$('storeList').append(a);}});
 $('storeForm').onsubmit=e=>{e.preventDefault();action(async t=>{const r=await call('store_save',{store_workspace:$('storeWorkspace').value,record:{name:$('storeName').value,description:$('storeDescription').value,contact:$('storeContact').value,status:$('storeState').value},expected_version:$('storeVersion').value?Number($('storeVersion').value):null},t);if(t===epoch){$('storeVersion').value=r.version;$('storeResult').textContent=JSON.stringify(r,null,2);}});};
 function clearOrderLines(){$('orderLines').replaceChildren();$('completionRevision').value='';$('completionNote').value='';}
 async function orderLines(t,reference,selection){
  try{const r=await commerce(t,'order_lines',{reference});if(t!==epoch||selection!==detailSelection||reference!==$('detailReference').value)return;
   $('orderLines').replaceChildren();for(const line of r.lines||[])article('orderLines',line.item_id+' · '+line.name+' · 数量 '+line.quantity+' · 冻结单价 '+line.unit_minor+' 分 · 小计 '+line.subtotal_minor+' 分 · 商品版本 '+line.revision);
   const revision=r.fulfillment_revision??0;article('orderLines','原篮子金额 '+r.amount_minor+' 分 · 履约 '+(r.fulfillment_state||'尚未完成')+' · 修订号 '+revision);$('completionRevision').value=revision;$('completionNote').value=r.completion_note||'';
  }catch(error){if(t===epoch&&selection===detailSelection&&reference===$('detailReference').value){clearOrderLines();$('orderLines').textContent='未取得原篮子商品快照；普通金额订单没有可补造的商品明细。请核对原订单或权限。';}}
 }
 $('readOrderLines').onclick=()=>action(t=>{const selection=++detailSelection;clearOrderLines();return orderLines(t,$('detailReference').value,selection);});
 $('completeOrder').onclick=()=>action(async t=>{const reference=$('detailReference').value,selection=detailSelection;if($('completionRevision').value==='')throw Error('先读取原篮子商品快照和履约修订号');const r=await commerce(t,'order_complete',{reference,expected_revision:Number($('completionRevision').value),note:$('completionNote').value});if(t===epoch&&selection===detailSelection&&reference===$('detailReference').value){$('completionRevision').value=r.fulfillment_revision;await orderLines(t,reference,selection);}});
 let billPage=null,billAuditPage=null,billSelection=0;
 function billParams(){return {kind:$('billKind').value,bill_date:$('billDate').value};}
 const billSelectionValue=()=>({...billParams(),scope:$('billScope').value});
 let billSelectionKey=JSON.stringify(billSelectionValue());
 function billChanged(){
  const key=JSON.stringify(billSelectionValue());if(key===billSelectionKey)return;
  billSelectionKey=key;billSelection++;billPage=null;billAuditPage=null;
  $('billResult').replaceChildren();$('moreBill').hidden=true;$('moreBillAudit').hidden=true;
  // Changing a bill selection may release only its read request, never an
  // unrelated funds action. Its late completion cannot unlock a newer action.
  if(activeAction?.context==='bill'){activeAction=null;busy=false;for(const b of document.querySelectorAll('button'))b.disabled=!config;}
  if(config&&!activeAction)status('账单选择已变化，请重新读取或核对');
 }
 for(const id of ['billKind','billDate','billScope']){$(id).oninput=billChanged;$(id).onchange=billChanged;}
 const billCurrent=(t,selection,params)=>t===epoch&&selection===billSelection&&params.kind===$('billKind').value&&params.bill_date===$('billDate').value;
 const billRun=fn=>{billChanged();return action(t=>fn(t,billSelection),'bill');};
 async function billAction(t,operation,params,selection){
  const scope=$('billScope').value,current=()=>billCurrent(t,selection,params)&&scope===$('billScope').value;
  const context=config,merchant=scope==='MERCHANT';
  if(scope!=='STORE'&&!merchant)throw Error('账单范围无效');
  const workspace=merchant?context?.merchantBillWorkspace:context?.providerWorkspace;
  if(!workspace)throw Error(merchant?'当前账号未获整商户账单只读授权':'当前账号未获门店财务授权');
  if(!current())throw Error('当前选择已变化');
  const response=await fetch(merchant?'/community/merchant-bills':'/community/provider-actions',{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',headers:{'Content-Type':'application/json','X-CSRF-Token':context.csrf},body:JSON.stringify({workspace,operation,params})});
  if(!current())throw Error('当前选择已变化');
  const clearCurrentBill=()=>{if(current()){$('billResult').replaceChildren();billPage=null;billAuditPage=null;$('moreBill').hidden=true;$('moreBillAudit').hidden=true;}};
  if(!response.ok){clearCurrentBill();throw Error('账单读取未确认，权限可能已变化，请重新读取');}
  let data;try{data=await response.json();}catch(e){clearCurrentBill();throw Error('账单响应无法读取，请重新核对');}
  if(!current())throw Error('当前选择已变化');
  if(!data||typeof data.result!=='object'||!data.result||Array.isArray(data.result)){clearCurrentBill();throw Error('账单响应无法读取，请重新核对');}
  const result=data.result;$('billResult').textContent=JSON.stringify(result,null,2);
  return result;
 }
 $('fetchBill').onclick=()=>billRun((t,s)=>billAction(t,'bill_fetch',billParams(),s));
 async function billRows(t,params,offset,selection){
  const result=await billAction(t,'bill_rows',{...params,offset},selection);
  if(!billCurrent(t,selection,params))return;
  billPage=result.has_more?{params,offset:result.next_offset}:null;
  $('moreBill').hidden=!billPage;
 }
 $('readBill').onclick=()=>billRun((t,s)=>billRows(t,billParams(),0,s));
 $('moreBill').onclick=()=>billRun((t,s)=>billPage&&billRows(t,billPage.params,billPage.offset,s));
 $('reconcileBill').onclick=()=>billRun((t,s)=>billAction(t,'bill_reconcile',billParams(),s));
 async function billAudit(t,params,after_id='',selection){
  const result=await billAction(t,'bill_audit',{...params,after_id},selection);
  if(!billCurrent(t,selection,params))return;
  billAuditPage=result.has_more?{params,after_id:result.next_cursor}:null;
  $('moreBillAudit').hidden=!billAuditPage;
 }
 $('billAudit').onclick=()=>billRun((t,s)=>billAudit(t,billParams(),'',s));
 $('moreBillAudit').onclick=()=>billRun((t,s)=>billAuditPage&&billAudit(t,billAuditPage.params,billAuditPage.after_id,s));
 window.configureCommunityWorkbench(null);
 try{
  if(location.hostname==='community-preview.wenwenwenyiyiyi.work'&&location.hash.startsWith('#preview=')){
   const context=JSON.parse(decodeURIComponent(location.hash.slice(9)));
   history.replaceState(null,'',location.pathname);
   window.configureCommunityWorkbench(context);
  }
 }catch(_){window.configureCommunityWorkbench(null);}
})();
