"use strict";
(()=>{
 const main=document.querySelector('main'),nav=document.getElementById('admin-sections');
 if(!main||!nav)return;
 const sections=Array.from(main.children).filter(el=>el.tagName==='SECTION');
 const result=sections.find(el=>el.querySelector('#result'));
 const panels=sections.filter(el=>el!==result);
 const home=document.createElement('section');home.className='admin-home';
 const heading=document.createElement('h2');heading.textContent='社区运营工作台';home.append(heading);
 const intro=document.createElement('p');intro.textContent='选择功能查看与处理。业务数据由原账户权限决定，未读取时不展示示例金额或记录。';home.append(intro);
 const cards=document.createElement('div');cards.className='admin-cards';home.append(cards);
 const back=document.createElement('button');back.type='button';back.className='admin-back';back.textContent='返回工作台';
 main.insertBefore(home,sections[0]);main.insertBefore(back,home);
 const buttons=[];
 const profileForm=document.getElementById('profile');
 const profilePanel=profileForm.closest('section');
 const profileIndex=panels.indexOf(profilePanel);
 profilePanel.classList.add('community-profile-panel');
 const pageTitle=main.querySelector('h1');
 const account=document.querySelector('.admin-account'),accountRoot=document.getElementById('community-session');
 let accountReady=false;
 if(account&&accountRoot){
  const syncAccount=()=>{const ready=accountRoot.querySelector('select').options.length>0;if(ready&&!accountReady)account.open=false;else if(!ready&&accountReady)account.open=true;accountReady=ready;};
  new MutationObserver(syncAccount).observe(accountRoot,{childList:true,subtree:true});syncAccount();
 }
 const detail=document.createElement('div');detail.className='community-profile-detail';detail.hidden=true;
 const detailTitle=document.createElement('h3');detailTitle.textContent='社区资料详情';detail.append(detailTitle);
 const fields=document.createElement('dl');detail.append(fields);
 const edit=document.createElement('button');edit.type='button';edit.textContent='编辑资料';
 const reread=document.createElement('button');reread.type='button';reread.textContent='回读当前记录';
 const toList=document.createElement('button');toList.type='button';toList.textContent='返回记录列表';
 const create=document.createElement('button');create.type='button';create.textContent='登记新社区';
 const submit=document.getElementById('submit'),mine=document.getElementById('mine');
 const actions=document.createElement('div');actions.className='profile-actions';actions.append(mine,create);
 const hint=document.createElement('p');hint.className='profile-hint';hint.textContent='尚未读取；点击“我的社区”查询原记录。';
 profilePanel.append(actions,hint,detail);detail.append(edit,reread,toList,profileForm,submit);
 profileForm.hidden=true;submit.hidden=true;
 let profileRecord=null,activeIndex=null;
 function emptyProfile(message){fields.hidden=false;profileRecord=null;detail.hidden=true;profileForm.hidden=true;submit.hidden=true;fields.replaceChildren();hint.textContent=message;}
 window.communityProfileView=({type,record})=>{
  if(type==='reset'){emptyProfile('身份或工作区已变化，请重新查询。');return;}
  if(type==='error'){emptyProfile('本次操作未确认或权限已变化；请回读原记录，不要重复提交。');return;}
  if(type==='list'){detail.hidden=true;profileForm.hidden=true;submit.hidden=true;if(result)result.hidden=false;hint.textContent='查询原社区记录中…';return;}
  if(type==='listed'){hint.textContent=record.count?'已读取当前页 '+record.count+' 条原记录。':'当前页没有记录。';return;}
  if(type!=='detail'||activeIndex!==profileIndex)return;
  profileRecord=record;fields.hidden=false;fields.replaceChildren();
  for(const [label,key] of [['社区名称','name'],['社区介绍','description'],['联系人及联系方式','contact'],['状态','state'],['当前版本','version']]){
   const term=document.createElement('dt'),value=document.createElement('dd');term.textContent=label;value.textContent=record[key]===undefined?'当前权限未返回该字段':key==='state'?({DRAFT:'草稿',PENDING:'待审核',CORRECTION:'待补充资料',REJECTED:'已驳回',APPROVED:'已通过',PAUSED:'已暂停'}[record[key]]||String(record[key])):String(record[key]);fields.append(term,value);
  }
  detail.hidden=false;profileForm.hidden=true;submit.hidden=true;
  edit.disabled=!['DRAFT','CORRECTION','REJECTED'].includes(record.state);
  hint.textContent=edit.disabled?'当前状态仅可查看资料。':'资料已读取，可查看或编辑。';
  if(result)result.hidden=true;
 };
 edit.addEventListener('click',()=>{if(!profileRecord||edit.disabled)return;fields.hidden=true;profileForm.hidden=false;submit.hidden=false;});
 reread.addEventListener('click',()=>{if(profileRecord)document.getElementById('read').click();});
 toList.addEventListener('click',()=>{detail.hidden=true;profileForm.hidden=true;submit.hidden=true;if(result)result.hidden=false;hint.textContent='已返回原列表；需要最新数据时点击“我的社区”。';});
 create.addEventListener('click',()=>{document.getElementById('directoryStatus').onchange();profileRecord=null;fields.hidden=true;fields.replaceChildren();detail.hidden=false;profileForm.hidden=false;submit.hidden=true;edit.disabled=true;hint.textContent='填写社区资料后保存草稿，核对无误再提交审核。';});

 // Page 19 uses only original status/membership responses. A selected kind is not proof of membership.
 const openPanel=document.getElementById('reference').closest('section'),openIndex=panels.indexOf(openPanel);
 openPanel.classList.add('community-open-panel');
 const openHint=document.createElement('p');openHint.className='profile-hint';openHint.textContent='输入社区编号，查询您有权查看的社区资料。';
 const openCard=document.createElement('article');openCard.className='community-record-card';openCard.hidden=true;
 const openCardTitle=document.createElement('h3');openCardTitle.textContent='记录列表 · 当前范围';openCard.append(openCardTitle);
 const openSummary=document.createElement('dl');openCard.append(openSummary);
 const openDetails=document.createElement('div');openDetails.className='community-profile-detail';openDetails.hidden=true;
 const openTitle=document.createElement('h3');openTitle.textContent='社区详情';openDetails.append(openTitle);
 const openFields=document.createElement('dl');openDetails.append(openFields);
 const showOpen=document.createElement('button');showOpen.type='button';showOpen.className='open-detail-action';showOpen.textContent='查看社区详情';showOpen.hidden=true;
 const backOpen=document.createElement('button');backOpen.type='button';backOpen.textContent='返回社区记录';
 const refreshOpen=document.createElement('button');refreshOpen.type='button';refreshOpen.textContent='回读社区资料';
 openDetails.append(backOpen,refreshOpen);openPanel.append(openHint,openCard,showOpen,openDetails);
 const kindNote=document.createElement('p');kindNote.className='profile-hint';kindNote.textContent='选择本次加入或退出的身份，不代表您当前的社区关系。';
 document.getElementById('kind').closest('label').append(kindNote);
 // Keep original IDs/listeners: query first, field card next, optional actions last.
 const openQuery=document.createElement('div');openQuery.className='open-query';
 openQuery.append(document.getElementById('reference').closest('label'),document.getElementById('read'));
 const openActions=document.createElement('details');openActions.className='open-actions';
 const actionsTitle=document.createElement('summary');actionsTitle.textContent='关系与成员操作';openActions.append(actionsTitle);
 const relationButtons=document.createElement('div');relationButtons.className='open-action-buttons';
 relationButtons.append(document.getElementById('join'),document.getElementById('leave'),document.getElementById('members'));
 openActions.append(document.getElementById('kind').closest('label'),relationButtons);
 openPanel.append(openQuery,openHint,openCard,showOpen,openDetails,openActions);
 let openRecord=null,openMembers=false;
 function clearOpen(message){openRecord=null;openMembers=false;openCard.hidden=true;showOpen.hidden=true;openDetails.hidden=true;openSummary.replaceChildren();openFields.replaceChildren();openHint.textContent=message;}
 function openPair(target,label,value){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;target.append(dt,dd);}
 window.communityOpenView=({type,record})=>{
  if(type==='reset'||type==='error'||type==='loading'){clearOpen(type==='error'?'资料未确认或当前无权查看，请重新查询。':type==='loading'?'正在查询社区资料…':'身份或工作区已变化，请重新查询。');if(activeIndex===openIndex&&result)result.hidden=true;return;}
  if(type==='members'){clearOpen('成员查询使用原权限；以下仅为当前页记录。');openMembers=true;if(activeIndex===openIndex&&result)result.hidden=false;return;}
  if(type==='relation'){clearOpen(record.active?'本次加入已获服务端确认；请回读社区资料。':'本次退出已获服务端确认；请回读社区资料。');if(activeIndex===openIndex&&result)result.hidden=true;return;}
  if(type!=='status')return;
  clearOpen('资料已读取，可查看详情；当前社区关系尚未确认。');openRecord=record;
  openPair(openSummary,'社区编号',record.id);openPair(openSummary,'关系类型','当前关系未确认');openPair(openSummary,'列表说明','点击下方按钮查看完整社区资料。');
  for(const [label,key] of [['社区编号','id'],['社区名称','name'],['社区介绍','description'],['状态','state'],['当前版本','version'],['联系人及联系方式','contact']]){
   if(record[key]===undefined)continue;
   const value=key==='state'?({DRAFT:'草稿',PENDING:'待审核',CORRECTION:'待补充资料',REJECTED:'已驳回',APPROVED:'已通过',PAUSED:'已暂停'}[record[key]]||String(record[key])):String(record[key]);openPair(openFields,label,value);
  }
  openCard.hidden=false;showOpen.hidden=false;if(activeIndex===openIndex&&result)result.hidden=true;
 };
 document.getElementById('reference').addEventListener('input',()=>{clearOpen('社区编号已改变，请查询所选社区。');if(activeIndex===openIndex&&result)result.hidden=true;});
 showOpen.addEventListener('click',()=>{if(!openRecord)return;openCard.hidden=true;showOpen.hidden=true;openDetails.hidden=false;});
 backOpen.addEventListener('click',()=>{if(!openRecord)return;openDetails.hidden=true;openCard.hidden=false;showOpen.hidden=false;});
 refreshOpen.addEventListener('click',()=>document.getElementById('read').click());


 // Page20: only original order/verified split observations; never a payment action.
 const reportPanel=document.getElementById('communityEarnings').closest('section'),reportIndex=panels.indexOf(reportPanel);
 reportPanel.classList.add('community-report-panel');
 const reportQuery=document.createElement('div');reportQuery.className='open-query';
 const reportLabel=document.createElement('label');reportLabel.textContent='社区编号';
 const reportReference=document.createElement('input');reportReference.id='reportReference';reportLabel.append(reportReference);
 reportReference.addEventListener('input',()=>{document.getElementById('reference').value=reportReference.value;document.getElementById('reference').oninput();});
 reportQuery.append(reportLabel,document.getElementById('communityOrders'),document.getElementById('communityEarnings'));
 const reportHint=document.createElement('p');reportHint.className='profile-hint';
 const reportCard=document.createElement('article');reportCard.className='community-record-card';
 const reportTitle=document.createElement('h3');reportTitle.textContent='记录列表 · 当前范围';
 const reportSummary=document.createElement('dl');reportCard.append(reportTitle,reportSummary);
 const reportShow=document.createElement('button');reportShow.type='button';reportShow.className='open-detail-action';reportShow.textContent='查看分账快照';reportShow.disabled=true;
 const reportDetail=document.createElement('div');reportDetail.className='community-report-detail';reportDetail.hidden=true;
 const reportRows=document.createElement('div');reportRows.className='report-rows';
 const reportBack=document.createElement('button');reportBack.type='button';reportBack.textContent='返回观察记录';
 reportDetail.append(reportRows,reportBack);
 const reportConfig=document.createElement('details');reportConfig.className='open-actions';
 const configTitle=document.createElement('summary');configTitle.textContent='平台配置社区分账接收关系';reportConfig.append(configTitle);
 for(const key of ['receiverWorkspace','receiverId','receiverVersion'])reportConfig.append(document.getElementById(key).closest('label'));
 reportConfig.append(document.getElementById('bindReceiver'));
 const oldConfigTitle=reportPanel.querySelector('h3');if(oldConfigTitle)oldConfigTitle.hidden=true;
 reportPanel.append(reportQuery,reportHint,reportCard,reportShow,reportDetail,reportConfig);
 let reportRecord=null;
 const money=(value,currency)=>Number.isSafeInteger(value)&&currency==='CNY'?(value<0?'-':'')+'¥'+Math.floor(Math.abs(value)/100)+'.'+String(Math.abs(value)%100).padStart(2,'0')+' CNY':'当前权限未返回有效金额';
 const reportValue=value=>value===undefined?'当前权限未返回该字段':String(value);
 function clearReport(message){reportRecord=null;reportHint.textContent=message;reportCard.hidden=false;reportShow.hidden=false;reportShow.disabled=true;reportDetail.hidden=true;reportRows.replaceChildren();reportSummary.replaceChildren();
  for(const pair of [['社区收益观察','分账与回退分别查看；未确认不表示已到账'],['分账快照','查询当前社区范围的原记录'],['退款观察','只读原订单退款及分账回退观察'],['查询状态',message]])openPair(reportSummary,...pair);
 }
 window.communityReportView=({type,record})=>{
  if(type==='identity-reset')reportReference.value='';
  if(type==='binding'){clearReport('接收关系已保存，版本 '+reportValue(record.version)+'；仅适用于新分账规则版本，不执行资金操作。');return;}
  if(type!=='listed'){clearReport(type==='loading'?'正在读取，尚未确认':type==='error'?'读取失败或无权查看，旧记录已清除':'尚未查询，不填充真实结果');return;}
  clearReport('已读取当前页 '+record.result.records.length+' 条记录；不代表全部记录或到账。');reportRecord=record;
  const r=record.result,earnings=record.operation==='community_earnings';reportSummary.replaceChildren();
  for(const pair of [['社区收益观察','当前页已核实金额 '+money(r.page_gross_minor,r.currency)+'；净额 '+money(r.page_net_minor,r.currency)],['分账快照',earnings?'当前社区的原分账规则版本与接收方观察':'当前社区归属订单；未读取分账快照'],['退款观察','当前页已核实退款/回退 '+money(r.page_returns_minor,r.currency)],['查询状态',(r.totals_scope==='CURRENT_PAGE_ONLY'?'仅当前页':'汇总范围未确认')+' · '+(r.finance_status==='UNCONFIRMED'?'财务核销未确认':'财务状态：'+reportValue(r.finance_status))]])openPair(reportSummary,...pair);
  reportShow.textContent=earnings?'查看分账快照':'查看归属订单';reportShow.disabled=false;
  const heading=document.createElement('h3');heading.textContent=earnings?'当前页分账快照与回退观察':'当前页归属订单';reportRows.append(heading);
  if(!r.records.length){const empty=document.createElement('p');empty.textContent='当前页没有记录；不代表其他页或未接通。';reportRows.append(empty);}
  for(const item of r.records){const row=document.createElement('article');row.className='community-record-card';const fields=document.createElement('dl');
   const keys=earnings?[['原订单','reference'],['分账请求','request_id'],['接收方','receiver_id'],['规则编号','rule_id'],['规则版本','rule_version'],['已核实分账','received_minor'],['已核实回退','returned_minor'],['净额','net_minor'],['渠道状态','provider_state'],['接收方状态','receiver_state'],['财务核销','finance_status']]:[['原订单','reference'],['商家','merchant_id'],['门店','store_id'],['订单金额','amount_minor'],['订单状态','order_state'],['渠道付款已核实','provider_payment_verified']];
   for(const [label,key]of keys)openPair(fields,label,key.endsWith('_minor')?money(item[key],r.currency):key==='finance_status'&&item[key]==='UNCONFIRMED'?'未确认':key==='provider_payment_verified'?item[key]===true?'是（不代表财务核销）':item[key]===false?'否':'未返回':reportValue(item[key]));row.append(fields);reportRows.append(row);
  }
 };
 reportShow.addEventListener('click',()=>{if(!reportRecord)return;reportCard.hidden=true;reportShow.hidden=true;reportDetail.hidden=false;});
 reportBack.addEventListener('click',()=>{if(!reportRecord)return;reportDetail.hidden=true;reportCard.hidden=false;reportShow.hidden=false;});
 clearReport('尚未查询，不填充真实结果');

 // Page21: field cards use original scoped promotion responses, never link views as members.
 const promotionPanel=document.getElementById('listPromotions').closest('section'),promotionIndex=panels.indexOf(promotionPanel);
 promotionPanel.classList.add('community-promotion-panel');
 const promotionQuery=document.createElement('div');promotionQuery.className='open-query';
 const promotionLabel=document.createElement('label');promotionLabel.textContent='社区编号';
 const promotionReference=document.createElement('input');promotionReference.id='promotionReference';promotionLabel.append(promotionReference);
 promotionReference.addEventListener('input',()=>{document.getElementById('reference').value=promotionReference.value;document.getElementById('reference').oninput();});
 promotionQuery.append(promotionLabel,document.getElementById('listPromotions'));
 const promotionHint=document.createElement('p');promotionHint.className='profile-hint';
 const promotionRows=document.createElement('div');promotionRows.className='promotion-records';
 const promotionDetail=document.createElement('div');promotionDetail.className='community-promotion-detail';promotionDetail.hidden=true;
 const promotionFields=document.createElement('dl'),promotionBack=document.createElement('button');promotionBack.type='button';promotionBack.textContent='返回推广记录';
 promotionDetail.append(promotionFields,promotionBack);
 const promotionActions=document.createElement('details');promotionActions.className='open-actions';
 const promotionSummary=document.createElement('summary');promotionSummary.textContent='创建推广及更新状态';promotionActions.append(promotionSummary);
 for(const key of ['promotionScene','promotionTitle','promotionExpiry','promotionCode','promotionVersion','promotionState'])promotionActions.append(document.getElementById(key).closest('label'));
 promotionActions.append(document.getElementById('createPromotion'),document.getElementById('savePromotionState'));
 const promotionNote=document.createElement('p');promotionNote.className='profile-hint';promotionNote.textContent='使用原已通过社区及门店场景；到期时间沿用原90天上限。创建结果未确认时先查询对账，不重复提交同一意图。只统计已登录确认的去重记录，不把浏览计为新成员。';promotionActions.append(promotionNote);
 promotionPanel.append(promotionQuery,promotionHint,promotionRows,promotionDetail,promotionActions);
 const expiry=value=>Number.isInteger(value)?new Date(value*1000).toISOString().replace('T',' ').replace('.000Z',' UTC'):'当前权限未返回有效时间';
 const promotionValue=(record,key)=>record[key]===undefined?'当前权限未返回该字段':key==='expires_at'?expiry(record[key]):key==='status'?({ACTIVE:'有效',PAUSED:'已暂停'}[record[key]]||String(record[key])):String(record[key]);
 function clearPromotion(message){promotionRows.replaceChildren();promotionFields.replaceChildren();promotionRows.hidden=false;promotionDetail.hidden=true;promotionHint.textContent=message;}
 function promotionDetails(record){promotionFields.replaceChildren();for(const [label,key]of [['推广码','id'],['原小程序门店场景','scene'],['推广标题','title'],['到期时间','expires_at'],['状态','status'],['当前版本','version'],['新成员','new_members'],['已认证去重参与','authenticated_redemptions']])openPair(promotionFields,label,promotionValue(record,key));promotionRows.hidden=true;promotionDetail.hidden=false;}
 window.communityPromotionView=({type,record})=>{
  if(type==='identity-reset')promotionReference.value='';
  if(type==='saved'){clearPromotion('服务端已确认本次操作；请查询原推广记录核对最新状态。');promotionDetails(record);return;}
  if(type!=='listed'){clearPromotion(type==='loading'?'正在读取或提交，尚未确认':type==='error'?'结果未确认或无权查看，旧记录已清除；请查询原记录对账。':'尚未查询原推广记录');return;}
  clearPromotion('已读取当前页 '+record.result.records.length+' 条推广记录；统计为已认证去重参与，不是浏览量。');
  if(!record.result.records.length){const empty=document.createElement('p');empty.textContent='当前页没有推广记录；其他页及未读取范围不作推断。';promotionRows.append(empty);}
  for(const item of record.result.records){
   const card=document.createElement('article');card.className='community-record-card';const title=document.createElement('h3');title.textContent='记录列表 · 当前范围';const fields=document.createElement('dl');
   for(const [label,key]of [['原小程序门店场景','scene'],['推广标题','title'],['到期时间','expires_at']])openPair(fields,label,promotionValue(item,key));
   openPair(fields,'列表说明','点击下方按钮查看完整资料；状态以回读结果为准。');card.append(title,fields);
   const show=document.createElement('button');show.type='button';show.className='open-detail-action';show.textContent='查看推广详情';show.addEventListener('click',()=>{if(record.select(item))promotionDetails(item);});promotionRows.append(card,show);
  }
 };
 promotionBack.addEventListener('click',()=>{promotionDetail.hidden=true;promotionRows.hidden=false;});
 clearPromotion('尚未查询原推广记录');

 // Pages22/49: scoped original merchant-name projection; membership never implies payment admission.
 const memberPanel=document.getElementById('communityMerchantMembers'),memberIndex=panels.indexOf(memberPanel);
 memberPanel.classList.add('community-members-panel');
 const memberQuery=document.createElement('div');memberQuery.className='open-query';memberQuery.append(document.getElementById('memberCommunityReference').closest('label'),document.getElementById('queryMerchantMembers'));
 const memberHint=document.createElement('p');memberHint.className='profile-hint';
 const memberRows=document.createElement('div');memberRows.className='member-records';
 const memberDetail=document.createElement('div');memberDetail.className='community-member-detail';memberDetail.hidden=true;
 const memberFields=document.createElement('dl'),memberBack=document.createElement('button'),memberRefresh=document.createElement('button');memberBack.type='button';memberBack.textContent='返回成员列表';memberRefresh.type='button';memberRefresh.textContent='重新查询当前社区';memberDetail.append(memberFields,memberBack,memberRefresh);
 memberPanel.append(memberQuery,memberHint,memberRows,memberDetail);
 function memberName(item){
  if(item.merchant_name_status==='MATCHED'&&typeof item.merchant_name==='string'&&item.merchant_name)return item.merchant_name;
  if(item.merchant_name_status==='MULTIPLE'&&Array.isArray(item.merchant_names))return '多个原门店：'+item.merchant_names.filter(v=>typeof v==='string').join('、');
  return ({NO_PROFILE:'原商家资料尚未建立',NO_ADMITTED_MAPPING:'尚无同项目已准入商家映射',MAPPING_UNAVAILABLE:'原商家映射当前不可用'}[item.merchant_name_status]||'接口未返回商家名称');
 }
 function memberWechat(item){
  if(item.wechat_status_source!=='SIGNED_PROVIDER_QUERY')return item.wechat_status_source==='MULTIPLE_MERCHANT_WORKSPACES'?'多个商家工作区，签约状态需分别核验':'未核验，不能从成员关系推断';
  const states={APPLYMENT_STATE_EDITTING:'待完善资料',APPLYMENT_STATE_AUDITING:'微信审核中',APPLYMENT_STATE_REJECTED:'微信已驳回',APPLYMENT_STATE_TO_BE_CONFIRMED:'待确认',APPLYMENT_STATE_TO_BE_SIGNED:'待签约',APPLYMENT_STATE_SIGNING:'签约中',APPLYMENT_STATE_FINISHED:'微信进件签约已完成',APPLYMENT_STATE_CANCELED:'已取消'};
  return states[item.wechat_status]?states[item.wechat_status]+'（原签验查询记录；收款及分账另行验收）':'未核验的渠道状态';
 }
 function clearMembers(message){memberRows.replaceChildren();memberFields.replaceChildren();memberRows.hidden=false;memberDetail.hidden=true;memberHint.textContent=message;}
 window.communityMerchantMembersView=({type,record})=>{
  if(type==='identity-reset')document.getElementById('memberCommunityReference').value='';
  if(type!=='listed'){clearMembers(type==='loading'?'正在查询原成员关系':type==='error'?'读取失败或无权查看，旧成员记录已清除':'尚未查询原成员关系');return;}
  clearMembers('当前页 '+record.result.records.length+' 条商家成员关系；不是全部成员统计。');
  if(!record.result.records.length){const empty=document.createElement('p');empty.textContent=record.result.has_more?'本扫描页没有商家成员，仍有下一页可查询。':'本页没有商家成员；不补造商家资料。';memberRows.append(empty);}
  for(const item of record.result.records){const card=document.createElement('article');card.className='community-record-card';const title=document.createElement('h3');title.textContent='记录列表 · 当前范围';const fields=document.createElement('dl');
   for(const pair of [['成员名称',memberName(item)],['成员类型','商家成员'],['所属范围','当前授权社区 '+record.community_id],['列表说明','点击下方按钮查看本次已读关系详情。']])openPair(fields,...pair);card.append(title,fields);
   const show=document.createElement('button');show.type='button';show.className='open-detail-action';show.textContent='查看商家成员详情';show.addEventListener('click',()=>{if(!record.select())return;memberFields.replaceChildren();for(const pair of [['成员名称',memberName(item)],['成员编号',item.user_id],['成员类型','商家成员'],['所属范围','当前授权社区 '+record.community_id],['关系更新时间',Number.isInteger(item.updated_at)?new Date(item.updated_at*1000).toISOString().replace('T',' ').replace('.000Z',' UTC'):'接口未返回有效时间'],['微信进件与签约',memberWechat(item)],['渠道记录观测时间',item.wechat_status_source==='SIGNED_PROVIDER_QUERY'&&Number.isInteger(item.wechat_observed_at)?new Date(item.wechat_observed_at*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})+' 北京时间':'尚无签验观测']])openPair(memberFields,...pair);memberRows.hidden=true;memberDetail.hidden=false;});memberRows.append(card,show);
  }
 };
 memberBack.addEventListener('click',()=>{memberDetail.hidden=true;memberRows.hidden=false;});memberRefresh.addEventListener('click',()=>document.getElementById('queryMerchantMembers').click());clearMembers('尚未查询原成员关系');

 // Insert before select() in the original admin shell. Reuse original controls, not copies.
 const receiverPanel=document.getElementById('receiverRelations'),receiverIndex=panels.indexOf(receiverPanel);
 receiverPanel.classList.add('community-receiver-panel');
 const receiverHint=document.createElement('p');receiverHint.className='profile-hint';
 const receiverRows=document.createElement('div'),receiverDetail=document.createElement('div');receiverDetail.className='community-receiver-detail';receiverDetail.hidden=true;
 const receiverFields=document.createElement('dl'),receiverBack=document.createElement('button');receiverBack.type='button';receiverBack.className='platform-order-button';receiverBack.textContent='返回接收关系列表';receiverDetail.append(receiverFields,receiverBack);
 const receiverActions=document.createElement('details');receiverActions.className='open-actions';const receiverSummary=document.createElement('summary');receiverSummary.textContent='原接收关系配置操作';receiverActions.append(receiverSummary);
 const receiverQuery=document.createElement('div');receiverQuery.className='open-query';receiverQuery.append(document.getElementById('receiverCommunityReference').closest('label'),document.getElementById('receiverWorkspace').closest('label'),document.getElementById('listReceiverRelations'));
 receiverActions.append(document.getElementById('receiverId').closest('label'),document.getElementById('receiverVersion').closest('label'),document.getElementById('readReceiverRelation'),document.getElementById('bindReceiver'));
 const receiverNotice=document.createElement('p');receiverNotice.textContent='仅原平台所有者及已授权财务范围可操作；只影响新分账规则版本，不执行资金操作。未知结果先回读关系版本，不重复提交。';receiverActions.append(receiverNotice);
 reportConfig.hidden=true;receiverPanel.append(receiverQuery,receiverHint,receiverRows,document.getElementById('moreReceiverRelations'),receiverDetail,receiverActions);
 const workspaceText=r=>r.provider_workspace_status==='LEGACY_NOT_RECORDED'?'历史记录未保存工作区，不作推断':typeof r.provider_workspace==='string'?r.provider_workspace:'未返回';
 const receiverPairs=r=>[['已授权财务工作区（记录）',workspaceText(r)],['本次已验证查询工作区',r.requested_provider_workspace||'保存回执；请回读核实'],['已准入接收方编号',r.receiver_id],['关系当前版本',r.version],['适用范围','仅新分账规则版本；未执行资金操作']];
 function clearReceiverUi(message){receiverRows.replaceChildren();receiverFields.replaceChildren();receiverDetail.hidden=true;receiverRows.hidden=false;receiverHint.textContent=message;}
 window.communityReceiverView=({type,record})=>{
  if(type==='detail'||type==='saved'){clearReceiverUi(type==='saved'?'保存已获服务端确认，建议回读当前关系版本。':'已回读所选接收关系；并非资金到账凭证。');for(const pair of receiverPairs(record))openPair(receiverFields,...pair);receiverDetail.hidden=false;receiverRows.hidden=true;return;}
  if(type!=='listed'){clearReceiverUi(type==='error'?'读取或保存未确认，旧详情已清除，请核对权限并回读。':type==='loading'?'正在请求原授权关系，尚未确认':'尚未读取原接收关系');return;}
  clearReceiverUi('已读取当前扫描页 '+record.result.records.length+' 条；不是全部关系汇总。');
  if(!record.result.records.length){const p=document.createElement('p');p.textContent=record.result.has_more?'本扫描页没有可显示关系，仍有下一页。':'本页没有可显示关系；不自动推定可用初始版本。';receiverRows.append(p);}
  for(const item of record.result.records){const card=document.createElement('article');card.className='community-record-card';const title=document.createElement('h3');title.textContent='记录列表 · 当前范围';const fields=document.createElement('dl');for(const pair of receiverPairs(item))openPair(fields,...pair);card.append(title,fields);const show=document.createElement('button');show.type='button';show.className='open-detail-action';show.textContent='查看接收关系详情';show.addEventListener('click',()=>record.select(item));receiverRows.append(card,show);}
 };
 receiverBack.addEventListener('click',()=>window.communityReceiverReturn());
 clearReceiverUi('尚未读取原接收关系');

 // PLATFORM_ORDER_CARDS_BEGIN: original platform_orders only, no provider actions.
 const platformResult=document.getElementById('platformViewResult'),platformPanel=platformResult.closest('section');
 platformPanel.classList.add('platform-orders-panel');
 const orderQuery=document.createElement('details'),orderSummary=document.createElement('summary');orderSummary.textContent='原平台运营查询与筛选';orderQuery.append(orderSummary);
 for(const id of ['platformView','platformOrderStatus'])orderQuery.append(document.getElementById(id).closest('label'));
 orderQuery.append(document.getElementById('readPlatformView'));
 const orderTitle=document.createElement('h3'),orderHint=document.createElement('p'),orderRows=document.createElement('div'),orderDetail=document.createElement('div'),orderBack=document.createElement('button');
 orderTitle.textContent='支付证据';orderRows.className='platform-order-rows';orderDetail.className='platform-order-detail';orderBack.textContent='返回原列表';orderBack.type='button';orderBack.className='platform-order-button';
 platformPanel.append(orderQuery,orderTitle,orderHint,orderRows,orderDetail,orderBack,document.getElementById('morePlatformView'),platformResult);
 let orderViewRevision=0;
 function syncOrderPageTitle(){platformPanel.querySelector('h2').hidden=document.getElementById('platformView').value==='platform_orders';orderTitle.hidden=true;if(!pageTitle||activeIndex!==panels.indexOf(platformPanel))return;pageTitle.textContent=document.getElementById('platformView').value==='platform_orders'?orderTitle.textContent:platformPanel.querySelector('h2').textContent;}
 function clearOrderView(message){orderViewRevision++;orderRows.replaceChildren();orderDetail.replaceChildren();orderRows.hidden=false;orderDetail.hidden=true;orderBack.hidden=true;orderTitle.textContent='支付证据';orderHint.textContent=message;platformResult.hidden=false;syncOrderPageTitle();}
 const orderValue=v=>v===undefined||v===null?'原记录未返回':String(v);
 function orderFields(r,detail){const scope=r.scope||{};const money=Number.isSafeInteger(r.amount_minor)&&typeof r.currency==='string'&&r.currency?r.amount_minor+' 最小货币单位 · '+r.currency:'金额或币种未完整返回，不填0或猜币种';const fields=[['订单编号',r.reference],['门店范围',[scope.tenant_id,scope.merchant_id,scope.store_id].map(orderValue).join(' / ')],['金额与币种',money]];
  if(detail)fields.push(['订单状态',r.order_state],['支付核验',r.payment_evidence?'已存证据来源：'+r.payment_evidence:'当前未返回已验证支付证据；不据此断言未支付'],['财务核销',r.finance_status==='UNCONFIRMED'?'未确认':r.finance_status]);return fields;}
 function orderCard(title,fields){const card=document.createElement('article'),h=document.createElement('h3'),dl=document.createElement('dl');card.className='platform-order-card';h.textContent=title;card.append(h);for(const [label,value]of fields){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=orderValue(value);dl.append(dt,dd);}card.append(dl);return card;}
 window.communityPlatformOrdersView=({type,record,current})=>{
  clearOrderView('尚未读取支付证据；打开原查询选择订单观察。');
  const orders=type==='listed'||document.getElementById('platformView').value==='platform_orders';orderTitle.hidden=true;orderHint.hidden=!orders;orderRows.hidden=!orders;
  if(type!=='listed')return;
  const revision=orderViewRevision;platformResult.hidden=true;
  orderHint.textContent=record.coverage_complete===false?'部分原商家权限或映射不可用：'+orderValue(record.unavailable_mapping_count)+' 项；这里只显示可访问门店小计，不代表完整范围。':'当前原授权门店订单；不是到账或财务核销结论。';
  if(!Array.isArray(record.records)){clearOrderView('本次记录格式未确认，请重新读取；不会把错误显示为空列表。');return;}
  if(!record.records.length){orderRows.textContent=record.has_more?'当前扫描页没有可显示订单，仍有下一页。':'当前筛选没有可显示订单。';return;}
  for(const r of record.records){const card=orderCard('记录列表 · 当前范围',orderFields(r,false)),show=document.createElement('button');show.type='button';show.className='platform-order-button';show.textContent='查看支付证据详情';
   show.onclick=()=>{if(revision!==orderViewRevision||!current())return;orderRows.hidden=true;orderDetail.replaceChildren(orderCard('记录详情',orderFields(r,true)));orderDetail.hidden=false;orderBack.hidden=false;orderTitle.textContent='支付证据详情';syncOrderPageTitle();};orderRows.append(card,show);}
  orderBack.onclick=()=>{if(revision!==orderViewRevision||!current())return;orderDetail.replaceChildren();orderDetail.hidden=true;orderRows.hidden=false;orderBack.hidden=true;orderTitle.textContent='支付证据';syncOrderPageTitle();};
 };
 clearOrderView('尚未读取支付证据；打开原查询选择订单观察。');
 // PLATFORM_ORDER_CARDS_END

 // PLATFORM_COMMUNITY_REVIEW_BEGIN: original list/status/review only.
 const reviewPanel=document.getElementById('review').closest('section'),reviewIndex=panels.indexOf(reviewPanel);
 reviewPanel.classList.add('platform-review-panel');
 const reviewQuery=document.createElement('details'),reviewSummary=document.createElement('summary');reviewSummary.textContent='原社区筛选与查询';reviewQuery.append(reviewSummary,document.getElementById('pending'),document.getElementById('directoryStatus').closest('label'),document.getElementById('listDirectory'));
 const reviewHint=document.createElement('p'),reviewRows=document.createElement('div'),reviewDetail=document.createElement('div'),reviewEditor=document.createElement('div'),reviewBack=document.createElement('button'),reviewEdit=document.createElement('button'),reviewRead=document.createElement('button'),reviewMore=document.createElement('button');
 reviewRows.className='platform-review-rows';reviewDetail.className='platform-review-detail';reviewEditor.className='platform-review-editor';reviewBack.textContent='返回审核列表';reviewEdit.textContent='打开原审核界面';reviewRead.textContent='回读当前社区版本';reviewMore.textContent='下一页审核记录';for(const b of [reviewBack,reviewEdit,reviewRead,reviewMore]){b.type='button';b.className='platform-review-button';}
 reviewEditor.append(document.getElementById('decision').closest('label'),document.getElementById('opinion').closest('label'),document.getElementById('review'));
 reviewPanel.append(reviewHint,reviewRows,reviewDetail,reviewEditor,reviewBack,reviewEdit,reviewRead,reviewMore,reviewQuery);
 let reviewSnapshot=null,reviewRecord=null,reviewReadCurrent=null,reviewRevision=0,reviewMode='list';
 const reviewState=s=>({DRAFT:'草稿',PENDING:'待审核',APPROVED:'已通过',CORRECTION:'待补充资料',REJECTED:'已驳回',PAUSED:'已暂停'}[s]||String(s));
 function reviewFields(r,detail){const fields=[['社区状态',reviewState(r.state)],['审核决定',['APPROVED','CORRECTION','REJECTED','PAUSED'].includes(r.state)?reviewState(r.state):'尚未形成审核决定'],['审核意见',r.opinion||'原记录暂无审核意见']];if(detail)fields.push(['社区编号',r.id],['社区名称',r.name],['社区介绍',r.description],['联系人及联系方式',r.contact],['当前版本',r.version]);return fields;}
 function reviewCard(title,record,detail){const card=document.createElement('article'),h=document.createElement('h3'),dl=document.createElement('dl');card.className='community-record-card';h.textContent=title;card.append(h,dl);for(const [label,value]of reviewFields(record,detail)){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value===undefined||value===null?'原权限未返回':String(value);dl.append(dt,dd);}return card;}
 function syncReviewTitle(){if(activeIndex!==reviewIndex)return;reviewPanel.querySelector('h2').hidden=true;if(pageTitle)pageTitle.textContent=reviewMode==='detail'?'平台审核 · 详情':reviewMode==='edit'?'平台审核 · 原操作/审核界面':'平台审核';}
 function clearReview(message){reviewRevision++;reviewSnapshot=null;reviewRecord=null;reviewReadCurrent=null;reviewMode='list';reviewRows.replaceChildren();reviewDetail.replaceChildren();reviewEditor.hidden=true;reviewRows.hidden=false;reviewDetail.hidden=true;for(const b of [reviewBack,reviewEdit,reviewRead,reviewMore])b.hidden=true;reviewHint.textContent=message;syncReviewTitle();}
 function showReviewList(){reviewRevision++;const revision=reviewRevision;reviewMode='list';reviewRows.replaceChildren();reviewRows.hidden=false;reviewDetail.hidden=true;reviewEditor.hidden=true;reviewBack.hidden=true;reviewEdit.hidden=true;reviewRead.hidden=true;reviewMore.hidden=!reviewSnapshot?.result.has_more;reviewHint.textContent='当前原筛选页的查询快照；详情读取最新版本，审核结果以服务端回执和回读为准。';if(reviewSnapshot){for(const r of reviewSnapshot.result.records){const open=document.createElement('button');open.textContent='查看审核详情';open.type='button';open.className='platform-review-button';open.onclick=()=>{if(revision!==reviewRevision)return;return reviewSnapshot.select(r);};reviewRows.append(reviewCard('记录列表 · 当前范围',r,false),open);}if(!reviewSnapshot.result.records.length)reviewRows.textContent=reviewSnapshot.result.has_more?'当前扫描页暂无记录，仍可读取下一页。':'当前筛选暂无社区记录。';}syncReviewTitle();}
 reviewMore.onclick=()=>document.getElementById('more').onclick();
 reviewBack.onclick=()=>{if(reviewSnapshot)showReviewList();else clearReview('请重新查询原筛选列表。');};
 reviewEdit.onclick=()=>{if(!reviewRecord)return;reviewMode='edit';reviewDetail.hidden=false;reviewEditor.hidden=false;reviewEdit.hidden=true;reviewHint.textContent='仅提交所选社区当前版本；必须是原同租户独立审核人。结果未知先回读，不自动重复审核。';syncReviewTitle();};
 reviewRead.onclick=()=>{if(reviewReadCurrent)return reviewReadCurrent();};
 window.communityPlatformReviewView=({type,record})=>{
  if(type==='reset'||type==='error'||type==='loading'){clearReview(type==='error'?'读取或审核未确认；已清除旧资料和成功展示，请回读或重新查询。':type==='loading'?'正在读取原权限社区目录…':'请按原状态查询社区目录。');return;}
  if(type==='loading-detail'){reviewRevision++;reviewRecord=null;reviewReadCurrent=null;reviewRows.hidden=true;reviewDetail.replaceChildren();reviewDetail.hidden=true;reviewEditor.hidden=true;reviewEdit.hidden=true;reviewRead.hidden=true;reviewBack.hidden=true;reviewMore.hidden=true;reviewHint.textContent='正在读取或提交原社区记录，请等待真实回执。';return;}
  if(type==='listed'){reviewSnapshot=record;reviewRecord=null;showReviewList();return;}
  if(type==='detail'){reviewRevision++;reviewRecord=record.record;document.getElementById('opinion').value=reviewRecord.opinion||'';reviewReadCurrent=record.read;reviewMode='detail';reviewRows.hidden=true;reviewDetail.replaceChildren(reviewCard('记录详情',reviewRecord,true));reviewDetail.hidden=false;reviewEditor.hidden=true;reviewBack.hidden=false;reviewEdit.hidden=false;reviewRead.hidden=false;reviewMore.hidden=true;reviewHint.textContent='已读取服务端当前版本；待审核/草稿不代表已通过。编辑和提交沿原独立审核权限。';syncReviewTitle();}
 };
 clearReview('请按原状态查询社区目录。');
 // PLATFORM_COMMUNITY_REVIEW_END

 // PLATFORM_OPERATIONS_CARDS_BEGIN: original non-order views; orders stay in original31.
 const operationRows=document.createElement('div'),operationDetail=document.createElement('div'),operationHint=document.createElement('p'),operationBack=document.createElement('button'),operationQuery=document.createElement('button');
 operationRows.className='platform-operation-rows';operationDetail.className='platform-operation-detail';operationBack.textContent='返回运营查询列表';operationQuery.textContent='打开原运营查询条件';for(const b of [operationBack,operationQuery]){b.type='button';b.className='platform-order-button';}platformPanel.append(operationHint,operationRows,operationDetail,operationBack,operationQuery);
 let operationRevision=0,operationSnapshot=null,operationMode='list';
 const operationNames={platform_overview:'经营总览',platform_customers:'项目客户',platform_audit:'项目审计'};
 const operationText=v=>v===undefined||v===null?'原记录未返回':String(v),operationBool=v=>v===true?'是':v===false?'否':'原记录未返回';
 function operationMoney(v,c){return Number.isSafeInteger(v)&&typeof c==='string'&&c?v+' 最小货币单位 · '+c:'原金额或币种未完整提供';}
 function operationFields(op,r,detail){if(op==='platform_overview'){const counts=Object.entries(r.order_counts||{}).map(([state,count])=>state+'：'+operationText(count)).join('；')||'当前范围无订单';const fields=[['查看数据','经营总览'],['订单状态分布',counts],['准入门店数量',r.admitted_store_count],['已存签验支付订单数',r.signed_paid_order_count]];if(detail)fields.push(['签验支付原额',operationMoney(r.signed_gross_payment_minor,r.currency)],['已核实退款',operationMoney(r.signed_refund_minor,r.currency)],['签验支付净额',operationMoney(r.signed_net_payment_minor,r.currency)],['仅本地终态、未签验数量',r.unverified_paid_state_count],['财务核销',r.finance_status==='UNCONFIRMED'?'未确认':r.finance_status]);return fields;}
 if(op==='platform_customers'){const fields=[['查看数据','原项目客户'],['账户编号',r.user_id],['昵称',r.nickname||'未填写昵称'],['项目角色',r.project_role],['会员关系有效',operationBool(r.membership_active)]];if(detail)fields.push(['账户验证',operationBool(r.verified)],['项目客户编号',r.project_customer_id],['社区归属',r.community_id||'未记录社区归属'],['原关联订单数量',r.owned_order_count]);return fields;}
 const fields=[['查看数据','原项目审计'],['审计序号',r.id],['事件',r.event],['关联对象',r.object_id]];if(detail)fields.push(['操作账户',r.actor],['原始时间戳',r.at],['前序摘要',r.parent],['当前摘要',r.sha],['范围','仅本项目过滤记录，不代表全局完整链已验证']);return fields;}
 function operationCard(title,fields){const card=document.createElement('article'),h=document.createElement('h3'),dl=document.createElement('dl');card.className='community-record-card';h.textContent=title;card.append(h,dl);for(const [k,v]of fields){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=k;dd.textContent=operationText(v);dl.append(dt,dd);}return card;}
 function syncOperationsTitle(){const active=document.getElementById('platformView').value!=='platform_orders';for(const e of [operationRows,operationHint,operationQuery])e.hidden=!active||operationMode!=='list'&&e===operationRows;operationDetail.hidden=!active||operationMode!=='detail';operationBack.hidden=!active||operationMode==='list';if(active)platformResult.hidden=true;if(activeIndex===panels.indexOf(platformPanel)&&active){platformPanel.querySelector('h2').hidden=true;if(pageTitle)pageTitle.textContent=operationMode==='detail'?'平台运营查询 · 详情':operationMode==='edit'?'平台运营查询 · 原查询条件':'平台运营查询';}}
 function clearOperations(){operationRevision++;operationSnapshot=null;operationMode='list';operationRows.replaceChildren();operationDetail.replaceChildren();operationHint.textContent='请打开原查询条件，读取当前角色可访问的运营数据。';syncOperationsTitle();}
 function operationsList(){operationRevision++;const revision=operationRevision,s=operationSnapshot;operationMode='list';operationRows.replaceChildren();operationDetail.replaceChildren();if(!s){syncOperationsTitle();return;}const records=s.operation==='platform_overview'?[s.record]:s.record.records;if(!Array.isArray(records)){clearOperations();operationHint.textContent='返回结构未确认，请重新查询；不显示为空结果。';return;}operationHint.textContent=s.record.coverage_complete===false?'部分原商家映射不可用，仅可访问门店小计；未核销。':s.operation==='platform_customers'?'仅当前原项目成员，不查询全局账户。':s.operation==='platform_audit'?'仅本项目原审计记录；不代表全局完整链验证。':'当前原准入门店范围；签验支付与财务核销分别记录，不能认作到账。';
 for(const r of records){const b=document.createElement('button');b.type='button';b.className='platform-order-button';b.textContent='查看运营记录详情';b.onclick=()=>{if(revision!==operationRevision||!s.current())return;operationMode='detail';operationDetail.replaceChildren(operationCard('记录详情',operationFields(s.operation,r,true)));syncOperationsTitle();};operationRows.append(operationCard('记录列表 · 当前范围',operationFields(s.operation,r,false)),b);}if(!records.length)operationRows.textContent=s.record.has_more?'当前扫描页暂无记录，仍可查询下一页。':'当前查询范围暂无记录。';platformResult.hidden=true;syncOperationsTitle();}
 operationBack.onclick=()=>{if(operationSnapshot?.current())operationsList();else clearOperations();};operationQuery.onclick=()=>{operationMode='edit';orderQuery.open=true;syncOperationsTitle();};
 window.communityPlatformOperationsView=event=>{if(event.type!=='listed'||!operationNames[event.operation]){clearOperations();return;}operationSnapshot=event;operationsList();};
 clearOperations();
 // PLATFORM_OPERATIONS_CARDS_END

 // PLATFORM_MERCHANT_CARDS_BEGIN: original scoped lifecycle, never WeChat signing state.
 const merchantPanel=document.getElementById('platformMerchants').closest('section'),merchantIndex=panels.indexOf(merchantPanel),merchantQuery=document.createElement('details'),merchantSummary=document.createElement('summary');merchantPanel.classList.add('platform-merchant-panel');merchantSummary.textContent='原准入商家查询';merchantQuery.append(merchantSummary,document.getElementById('platformMerchants'));
 const merchantRows=document.createElement('div'),merchantDetail=document.createElement('div'),merchantEditor=document.createElement('div'),merchantHint=document.createElement('p'),merchantBack=document.createElement('button'),merchantEdit=document.createElement('button'),merchantRead=document.createElement('button');merchantRows.className='platform-merchant-rows';merchantDetail.className='platform-merchant-detail';merchantEditor.className='platform-merchant-editor';merchantBack.textContent='返回商家列表';merchantEdit.textContent='打开原商家状态操作';merchantRead.textContent='回读所选商家当前版本';for(const b of [merchantBack,merchantEdit,merchantRead]){b.type='button';b.className='platform-order-button';}
 for(const id of ['platformMerchantWorkspace','platformMerchantVersion','platformMerchantState','platformMerchantReason'])merchantEditor.append(document.getElementById(id).closest('label'));merchantEditor.append(document.getElementById('saveMerchantState'));merchantPanel.append(merchantHint,merchantRows,merchantDetail,merchantEditor,merchantBack,merchantEdit,merchantRead,document.getElementById('moreMerchants'),merchantQuery);
 document.getElementById('merchantRecords').hidden=true;document.getElementById('merchantResult').hidden=true;
 let merchantViewRevision=0,merchantSnapshot=null,merchantItem=null,merchantSavedBase=null,merchantMode='list';
 const merchantState=v=>({ACTIVE:'正常',PAUSED:'暂停新交易',DISABLED:'停用新交易'}[v]||operationText(v));
 function merchantFields(item,detail){const life=item.lifecycle||{};const fields=[['原商家工作区',item.workspace],['当前版本',life.version],['平台状态',merchantState(life.status)]];if(detail)fields.push(['原因',life.reason||'原记录暂无原因'],['门店名称',item.name===undefined?'当前回执未含门店名称，请回读':item.name||'原门店未设置名称'],['门店状态',item.store_status],['状态边界','平台生命周期不是微信进件或签约状态；原已有订单查询与恢复功能保留']);return fields;}
 function syncMerchantTitle(){if(activeIndex!==merchantIndex)return;merchantPanel.querySelector('h2').hidden=true;if(pageTitle)pageTitle.textContent=merchantMode==='detail'?'平台商家管理 · 详情':merchantMode==='edit'?'平台商家管理 · 原操作':'平台商家管理';}
 function clearMerchantView(message){merchantViewRevision++;merchantSnapshot=null;merchantItem=null;merchantSavedBase=null;merchantMode='list';merchantRows.replaceChildren();merchantDetail.replaceChildren();merchantRows.hidden=false;merchantDetail.hidden=true;merchantEditor.hidden=true;merchantBack.hidden=true;merchantEdit.hidden=true;merchantRead.hidden=!document.getElementById('platformMerchantWorkspace').value;merchantHint.textContent=message;syncMerchantTitle();}
 function showMerchantList(){merchantViewRevision++;const revision=merchantViewRevision,s=merchantSnapshot;merchantMode='list';merchantRows.replaceChildren();merchantRows.hidden=false;merchantDetail.hidden=true;merchantEditor.hidden=true;merchantBack.hidden=true;merchantEdit.hidden=true;merchantRead.hidden=true;if(!s){syncMerchantTitle();return;}merchantHint.textContent=s.result.coverage_complete===false?'部分原映射不可用；只显示当前可访问商家，不代表全部商家。':'当前原准入商家查询快照；变更前按原分页边界回读版本。';for(const item of s.result.records){const b=document.createElement('button');b.type='button';b.className='platform-order-button';b.textContent='查看商家详情';b.onclick=()=>{if(revision!==merchantViewRevision)return;s.select(item);};merchantRows.append(operationCard('记录列表 · 当前范围',merchantFields(item,false)),b);}if(!s.result.records.length)merchantRows.textContent=s.result.has_more?'当前扫描页无可见商家，仍有下一页。':'当前范围暂无可见商家。';for(const missing of s.result.unavailable_mappings||[]){const note=document.createElement('p');note.textContent=operationText(missing.workspace)+'：原映射不可用，未读取其门店及订单。';merchantRows.append(note);}syncMerchantTitle();}
 function showMerchantDetail(){merchantMode='detail';merchantRows.hidden=true;merchantDetail.replaceChildren(operationCard('记录详情',merchantFields(merchantItem,true)));merchantDetail.hidden=false;merchantEditor.hidden=true;merchantBack.hidden=false;merchantEdit.hidden=false;merchantRead.hidden=false;syncMerchantTitle();}
 merchantBack.onclick=()=>showMerchantList();merchantEdit.onclick=()=>{if(!merchantItem)return;merchantMode='edit';merchantEditor.hidden=false;merchantEdit.hidden=true;merchantHint.textContent='仅原平台OWNER可修改；精确当前版本CAS，结果未知先回读，不自动重复变更。';syncMerchantTitle();};merchantRead.onclick=()=>window.communityReadMerchant();
 window.communityPlatformMerchantView=({type,record})=>{if(type==='reset'||type==='error'){clearMerchantView(record?.message||'结果未确认或权限拒绝，已清旧资料；先回读所选商家或重新查询。');return;}if(type==='loading'||type==='saving'){merchantViewRevision++;merchantSavedBase=type==='saving'?merchantItem:null;merchantItem=null;merchantMode='list';syncMerchantTitle();merchantDetail.replaceChildren();merchantDetail.hidden=true;merchantEditor.hidden=true;merchantBack.hidden=true;merchantEdit.hidden=true;merchantRead.hidden=true;merchantHint.textContent=type==='saving'?'正在提交原商家状态，请等待真实回执。':'正在查询原商家记录；旧列表仅供只读，不可据此修改。';return;}if(type==='temporary'){merchantHint.textContent='暂时无法读取；保留上一页只读记录及重试游标，必须重新查询成功后才能选择。';return;}if(type==='listed'){merchantSnapshot=record;showMerchantList();return;}if(type==='detail'){merchantViewRevision++;merchantItem=record.item;showMerchantDetail();return;}if(type==='saved'){merchantViewRevision++;merchantItem={...(merchantSavedBase||{}),workspace:record.workspace,lifecycle:record.lifecycle};showMerchantDetail();merchantHint.textContent='原状态变更已有回执；请回读当前原分页记录核对，未改变微信签约状态。';}};
 clearMerchantView('请查询原准入商家记录。');
 // PLATFORM_MERCHANT_CARDS_END

 // PLATFORM_BRAND_SCOPE_BEGIN: presentation only, no role or permission selection.
 const platformBrand=document.querySelector('.admin-brand'),platformBrandText=platformBrand&&Array.from(platformBrand.childNodes).find(n=>n.nodeType===3&&n.textContent.includes('社区服务'));
 const platformBrandOriginal=platformBrandText?.textContent,platformBrandSubtitle=platformBrand?.querySelector('span'),platformBrandSubtitleOriginal=platformBrandSubtitle?.textContent;
 function syncPlatformBrand(index){const selected=[reviewIndex,panels.indexOf(platformPanel),merchantIndex,receiverIndex].includes(index);if(platformBrandText)platformBrandText.textContent=selected?'社区服务 · 平台':platformBrandOriginal;if(platformBrandSubtitle)platformBrandSubtitle.textContent=selected?'平台管理工作台':platformBrandSubtitleOriginal;}
 // PLATFORM_BRAND_SCOPE_END

 function select(index){
  if(index!==activeIndex&&typeof window.communitySectionChanged==='function')window.communitySectionChanged();
  if(index!==openIndex){openMembers=false;clearOpen('输入社区编号，查询您有权查看的社区资料。');}
  if(activeIndex===profileIndex&&index!==profileIndex)emptyProfile('切换功能后请重新查询社区资料。');
  activeIndex=index;syncPlatformBrand(index);
  main.classList.toggle('receiver-selected',index===receiverIndex);if(index===receiverIndex)document.getElementById('receiverCommunityReference').value=document.getElementById('reference').value;
  if(pageTitle)pageTitle.textContent=index===null?'社区运营工作台':panels[index].querySelector('h2').textContent;
  syncOrderPageTitle();syncOperationsTitle();syncReviewTitle();syncMerchantTitle();
  main.classList.toggle('profile-selected',index===profileIndex);
  main.classList.toggle('members-selected',index===memberIndex);if(index===memberIndex)document.getElementById('memberCommunityReference').value=document.getElementById('reference').value;
  main.classList.toggle('promotion-selected',index===promotionIndex);if(index===promotionIndex)promotionReference.value=document.getElementById('reference').value;
  main.classList.toggle('open-selected',index===openIndex);main.classList.toggle('report-selected',index===reportIndex);if(index===reportIndex)reportReference.value=document.getElementById('reference').value;
  // Move, never clone, the original query result so list/detail uses the same cursor and handlers.
  if(index===profileIndex)profilePanel.append(result);else if(index===openIndex)openPanel.append(result);else if(index===reportIndex)reportPanel.append(result);else if(index===promotionIndex)promotionPanel.append(result);else if(index===memberIndex)memberPanel.append(result);else if(index===reviewIndex)reviewPanel.append(result);else if(result)main.append(result);
  home.hidden=index!==null;back.hidden=index===null;
  panels.forEach((panel,i)=>{panel.hidden=i!==index;});
  // Preserve the original result DOM and business handlers without cloning or rebinding.
  if(result)result.hidden=index===merchantIndex||index===panels.indexOf(platformPanel)||index===reviewIndex||index===receiverIndex||index===null||(index===profileIndex&&!detail.hidden)||(index===openIndex&&!openMembers);
  buttons.forEach((button,i)=>{if(i===index)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});
  if(index!==null){const title=panels[index].querySelector('h2');title.tabIndex=-1;title.focus();}
 }
 const homeButton=document.createElement('button');homeButton.type='button';homeButton.textContent='工作台首页';homeButton.addEventListener('click',()=>select(null));nav.append(homeButton);
 panels.forEach((panel,index)=>{
  const title=panel.querySelector('h2').textContent;
  const button=document.createElement('button');button.type='button';button.textContent=title;button.addEventListener('click',()=>select(index));nav.append(button);buttons.push(button);
  const card=document.createElement('button');card.type='button';card.className='admin-card';
  const strong=document.createElement('strong');strong.textContent=title;const description=document.createElement('span');description.textContent='打开原业务模块 · 按当前角色权限';card.append(strong,description);card.addEventListener('click',()=>select(index));cards.append(card);
 });
 back.addEventListener('click',()=>select(null));select(null);
})();
