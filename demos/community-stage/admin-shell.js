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

 function select(index){
  if(index!==activeIndex&&typeof window.communitySectionChanged==='function')window.communitySectionChanged();
  if(index!==openIndex){openMembers=false;clearOpen('输入社区编号，查询您有权查看的社区资料。');}
  if(activeIndex===profileIndex&&index!==profileIndex)emptyProfile('切换功能后请重新查询社区资料。');
  activeIndex=index;
  if(pageTitle)pageTitle.textContent=index===null?'社区运营工作台':panels[index].querySelector('h2').textContent;
  main.classList.toggle('profile-selected',index===profileIndex);
  main.classList.toggle('open-selected',index===openIndex);main.classList.toggle('report-selected',index===reportIndex);if(index===reportIndex)reportReference.value=document.getElementById('reference').value;
  // Move, never clone, the original query result so list/detail uses the same cursor and handlers.
  if(index===profileIndex)profilePanel.append(result);else if(index===openIndex)openPanel.append(result);else if(index===reportIndex)reportPanel.append(result);else if(result)main.append(result);
  home.hidden=index!==null;back.hidden=index===null;
  panels.forEach((panel,i)=>{panel.hidden=i!==index;});
  // Preserve the original result DOM and business handlers without cloning or rebinding.
  if(result)result.hidden=index===null||(index===profileIndex&&!detail.hidden)||(index===openIndex&&!openMembers);
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
