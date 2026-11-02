"use strict";
(()=>{
 const main=document.querySelector('main'),nav=document.getElementById('admin-sections');
 if(!main||!nav)return;
 const authorityPanel=document.createElement('section'),authorityHeading=document.createElement('h2'),authorityContent=document.createElement('div');
 authorityPanel.id='community-admin-permissions';authorityHeading.textContent='管理员设置';authorityContent.id='community-admin-permissions-content';authorityPanel.append(authorityHeading,authorityContent);main.append(authorityPanel);
 const sections=Array.from(main.children).filter(el=>el.tagName==='SECTION');
 const result=sections.find(el=>el.querySelector('#result'));
 const panels=sections.filter(el=>el!==result);
 const authorityIndex=panels.indexOf(authorityPanel);
 const home=document.createElement('section');home.className='admin-home';
 const heading=document.createElement('h2');heading.textContent='社区运营工作台';home.append(heading);
 const intro=document.createElement('p');intro.textContent='选择功能查看和处理业务。';home.append(intro);
 const cards=document.createElement('div');cards.className='admin-cards';home.append(cards);
 const back=document.createElement('button');back.type='button';back.className='admin-back';back.textContent='返回工作台';
 main.insertBefore(home,sections[0]);main.insertBefore(back,home);
 // HOME_MOBILE_NAV_BEGIN: move original navigation, never clone authority controls.
 let navigationDisclosure=null;
 const sidebar=document.querySelector('.admin-sidebar');
 if(sidebar&&typeof window.matchMedia==='function'){
  const navigationSummary=document.createElement('summary'),navigationBackdrop=document.createElement('button');navigationDisclosure=document.createElement('details');
  navigationDisclosure.className='admin-navigation-disclosure';navigationSummary.textContent='功能导航';navigationBackdrop.type='button';navigationBackdrop.className='admin-navigation-backdrop';navigationBackdrop.ariaLabel='关闭功能导航';navigationDisclosure.append(navigationSummary,navigationBackdrop);
  for(const node of Array.from(sidebar.children))navigationDisclosure.append(node);
  sidebar.append(navigationDisclosure);const mobileNavigation=window.matchMedia('(max-width:900px)');
  const syncNavigation=()=>{navigationDisclosure.open=!mobileNavigation.matches;};syncNavigation();
  if(typeof mobileNavigation.addEventListener==='function')mobileNavigation.addEventListener('change',syncNavigation);
  navigationBackdrop.onclick=()=>{navigationDisclosure.open=false;};
 }
 // HOME_MOBILE_NAV_END
 const buttons=[];
 const profileForm=document.getElementById('profile');
 const profilePanel=profileForm.closest('section');
 const profileIndex=panels.indexOf(profilePanel);
 profilePanel.classList.add('community-profile-panel');
 const pageTitle=main.querySelector('h1');
 const originalMessage=document.getElementById('message');if(originalMessage){const syncReadMessage=()=>{originalMessage.dataset.genericComplete=['操作完成','记录查询完成'].includes(originalMessage.textContent)?'true':'false';};new MutationObserver(syncReadMessage).observe(originalMessage,{childList:true,characterData:true,subtree:true});syncReadMessage();}
 const account=document.querySelector('.admin-account'),accountRoot=document.getElementById('community-session');
 let accountReady=false;
 if(account&&accountRoot){
  const syncAccount=()=>{const ready=accountRoot.querySelector('select').options.length>0;if(ready&&!accountReady)account.open=false;else if(!ready&&accountReady)account.open=true;accountReady=ready;};
  new MutationObserver(syncAccount).observe(accountRoot,{childList:true,subtree:true});syncAccount();
 }
 const detail=document.createElement('div');detail.className='community-profile-detail';detail.hidden=true;
 const profileHeader=document.createElement('header');profileHeader.className='management-page-header';
 const profileHeaderCopy=document.createElement('div'),profileEyebrow=document.createElement('span'),profileHeading=document.createElement('h3'),profileDescription=document.createElement('p');
 profileEyebrow.className='management-page-eyebrow';profileEyebrow.textContent='社区经营';profileHeading.textContent='社区资料管理';profileDescription.textContent='集中查看社区档案、审核状态和资料版本；编辑入口仅在选中记录后显示。';
 profileHeaderCopy.append(profileEyebrow,profileHeading,profileDescription);profileHeader.append(profileHeaderCopy);
 const profileStats=document.createElement('div');profileStats.className='management-stats';
 const profileStatNodes=new Map();
 for(const [key,label]of [['records','社区档案'],['state','当前状态'],['version','资料版本']]){const card=document.createElement('article'),caption=document.createElement('span'),value=document.createElement('strong'),note=document.createElement('small');card.className='management-stat';caption.textContent=label;value.textContent='—';note.textContent=key==='records'?'等待查询':key==='state'?'未选择记录':'以最新资料为准';card.append(caption,value,note);profileStats.append(card);profileStatNodes.set(key,{value,note});}
 profilePanel.prepend(profileHeader,profileStats);
 const detailTitle=document.createElement('h3');detailTitle.textContent='记录详情';detail.append(detailTitle);
 const fields=document.createElement('dl');detail.append(fields);
 const edit=document.createElement('button');edit.type='button';edit.textContent='编辑资料';
 const reread=document.createElement('button');reread.type='button';reread.textContent='刷新当前记录';
 const toList=document.createElement('button');toList.type='button';toList.textContent='返回记录列表';
 const create=document.createElement('button');create.type='button';create.textContent='登记新社区';
 const submit=document.getElementById('submit'),mine=document.getElementById('mine');
 const editor=document.createElement('aside');editor.className='community-profile-editor';editor.hidden=true;
 const editorHeader=document.createElement('header'),editorTitle=document.createElement('h3'),editorClose=document.createElement('button');editorTitle.textContent='编辑社区资料';editorClose.type='button';editorClose.textContent='关闭编辑';editorHeader.append(editorTitle,editorClose);editor.append(editorHeader,profileForm,submit);
 const actions=document.createElement('div');actions.className='profile-actions';actions.append(mine,create);
 const hint=document.createElement('p');hint.className='profile-hint';hint.textContent='点击“我的社区”查询资料。';
 profilePanel.append(actions,hint,detail);detail.append(edit,reread,toList,editor);
 profileForm.hidden=true;submit.hidden=true;editor.hidden=true;
 let profileRecord=null,activeIndex=null;
 const workspaceRouteNavigation=new Map();
 const profileStateLabel=value=>({DRAFT:'草稿',PENDING:'待审核',CORRECTION:'待补充资料',REJECTED:'已驳回',APPROVED:'已通过',PAUSED:'已暂停'}[value]||String(value));
 function closeProfileEditor(){fields.hidden=false;profileForm.hidden=true;submit.hidden=true;editor.hidden=true;}
 function emptyProfile(message){closeProfileEditor();profileRecord=null;detail.hidden=true;fields.replaceChildren();hint.textContent=message;profileStatNodes.get('records').value.textContent='—';profileStatNodes.get('records').note.textContent='等待查询';profileStatNodes.get('state').value.textContent='—';profileStatNodes.get('state').note.textContent='未选择记录';profileStatNodes.get('version').value.textContent='—';}
 window.communityProfileView=({type,record})=>{
  if(type==='reset'){emptyProfile('请选择查询条件。');return;}
  if(type==='error'){emptyProfile('操作未完成，请刷新后重试。');return;}
  if(type==='list'){detail.hidden=true;closeProfileEditor();if(result)result.hidden=false;hint.textContent='正在查询社区资料…';profileStatNodes.get('records').value.textContent='查询中';profileStatNodes.get('records').note.textContent='正在读取社区资料';return;}
  if(type==='listed'){hint.textContent=record.count?'当前页共 '+record.count+' 条记录。':'当前页没有记录。';profileStatNodes.get('records').value.textContent=String(record.count);profileStatNodes.get('records').note.textContent='当前页记录';return;}
  if(type!=='detail'||activeIndex!==profileIndex)return;
  profileRecord=record;fields.hidden=false;fields.replaceChildren();
  for(const [label,key] of [['社区名称','name'],['社区介绍','description'],['联系人及联系方式','contact'],['状态','state'],['当前版本','version']]){
   const term=document.createElement('dt'),value=document.createElement('dd');term.textContent=label;value.textContent=record[key]===undefined?'暂无数据':key==='state'?profileStateLabel(record[key]):String(record[key]);fields.append(term,value);
  }
  detail.hidden=false;closeProfileEditor();
  edit.disabled=!['DRAFT','CORRECTION','REJECTED'].includes(record.state);
  hint.textContent=edit.disabled?'当前状态仅可查看资料。':'资料已读取，可查看或编辑。';
  profileStatNodes.get('records').value.textContent='1';profileStatNodes.get('records').note.textContent='当前选中档案';profileStatNodes.get('state').value.textContent=profileStateLabel(record.state);profileStatNodes.get('state').note.textContent=edit.disabled?'当前只读':'允许修改资料';profileStatNodes.get('version').value.textContent=record.version===undefined?'—':String(record.version);
  if(result)result.hidden=true;
 };
 edit.addEventListener('click',()=>{if(!profileRecord||edit.disabled)return;fields.hidden=true;editor.hidden=false;profileForm.hidden=false;submit.hidden=true;editorTitle.textContent='编辑社区资料';});
 editorClose.addEventListener('click',closeProfileEditor);
 reread.addEventListener('click',()=>{if(profileRecord)document.getElementById('read').click();});
 toList.addEventListener('click',()=>{detail.hidden=true;closeProfileEditor();if(result)result.hidden=false;hint.textContent='已返回社区列表。';});
 create.addEventListener('click',()=>{document.getElementById('directoryStatus').onchange();profileRecord=null;fields.hidden=true;fields.replaceChildren();detail.hidden=false;editor.hidden=false;profileForm.hidden=false;submit.hidden=true;edit.disabled=true;editorTitle.textContent='登记新社区';hint.textContent='填写社区资料后保存草稿，核对无误再提交审核。';profileStatNodes.get('state').value.textContent='新建草稿';profileStatNodes.get('state').note.textContent='尚未提交审核';profileStatNodes.get('version').value.textContent='—';});

 // Page 19 uses only original status/membership responses. A selected kind is not proof of membership.
 const openPanel=document.getElementById('reference').closest('section'),openIndex=panels.indexOf(openPanel);
 openPanel.classList.add('community-open-panel');
 const openHeader=document.createElement('header');openHeader.className='management-page-header';
 const openHeaderCopy=document.createElement('div'),openEyebrow=document.createElement('span'),openHeading=document.createElement('h3'),openDescription=document.createElement('p');openEyebrow.className='management-page-eyebrow';openEyebrow.textContent='社区经营';openHeading.textContent='社区开通管理';openDescription.textContent='按社区编号查询社区资料、当前关系和成员。';openHeaderCopy.append(openEyebrow,openHeading,openDescription);openHeader.append(openHeaderCopy);
 const openStats=document.createElement('div');openStats.className='management-stats';const openStatNodes=new Map();for(const [key,label,note]of [['record','查询结果','尚未查询'],['relation','当前关系','尚未确认'],['status','社区状态','以最新资料为准']]){const card=document.createElement('article'),caption=document.createElement('span'),value=document.createElement('strong'),small=document.createElement('small');card.className='management-stat';caption.textContent=label;value.textContent='—';small.textContent=note;card.append(caption,value,small);openStats.append(card);openStatNodes.set(key,{value,note:small});}openPanel.prepend(openHeader,openStats);
 const openHint=document.createElement('p');openHint.className='profile-hint';openHint.textContent='输入社区编号，查询您有权查看的社区资料。';
 const openCard=document.createElement('article');openCard.className='community-record-card';openCard.hidden=true;
 const openCardTitle=document.createElement('h3');openCardTitle.textContent='记录列表 · 当前范围';openCard.append(openCardTitle);
 const openSummary=document.createElement('dl');openCard.append(openSummary);
 const openDetails=document.createElement('div');openDetails.className='community-profile-detail';openDetails.hidden=true;
 const openTitle=document.createElement('h3');openTitle.textContent='记录详情';openDetails.append(openTitle);
 const openFields=document.createElement('dl');openDetails.append(openFields);
 const showOpen=document.createElement('button');showOpen.type='button';showOpen.className='open-detail-action';showOpen.textContent='查看社区详情';showOpen.hidden=true;
 const backOpen=document.createElement('button');backOpen.type='button';backOpen.textContent='返回社区记录';
 const refreshOpen=document.createElement('button');refreshOpen.type='button';refreshOpen.textContent='刷新社区资料';
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
 function clearOpen(message){openActions.open=false;openRecord=null;openMembers=false;openCard.hidden=true;showOpen.hidden=true;openDetails.hidden=true;openSummary.replaceChildren();openFields.replaceChildren();openHint.textContent=message;openStatNodes.get('record').value.textContent='—';openStatNodes.get('record').note.textContent='尚未查询';openStatNodes.get('relation').value.textContent='—';openStatNodes.get('relation').note.textContent='尚未确认';openStatNodes.get('status').value.textContent='—';}
 function openPair(target,label,value){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;target.append(dt,dd);}
 // CURRENT_SUBJECT_RELATION_BEGIN
 function currentSubjectRelation(record){
  const r=record?.current_subject_relation;
  if(!r||r.community_id!==record.id)return '当前关系未确认';
  if(r.state==='NOT_APPLICABLE'&&r.kind===null)return '当前账号不适用加入关系';
  if(!['CUSTOMER','MERCHANT'].includes(r.kind))return '当前关系未确认';
  const state={ACTIVE:'已加入当前社区',INACTIVE:'已退出当前社区',NOT_JOINED:'未加入当前社区'}[r.state];
  return state?state+' · '+(r.kind==='CUSTOMER'?'消费者':'商家'):'当前关系未确认';
 }
 // CURRENT_SUBJECT_RELATION_END
 window.communityOpenView=({type,record})=>{
  if(type==='reset'||type==='error'||type==='loading'){clearOpen(type==='error'?'资料未确认，请重新查询。':type==='loading'?'正在查询社区资料…':'请查询社区。');if(activeIndex===openIndex&&result)result.hidden=true;return;}
  if(type==='members'){clearOpen('社区成员');openMembers=true;openStatNodes.get('record').value.textContent='读取中';openStatNodes.get('record').note.textContent='正在查询成员';if(activeIndex===openIndex&&result)result.hidden=false;return;}
  if(type==='members-listed'){if(openMembers&&activeIndex===openIndex){openHint.textContent=record.count?'已读取当前页 '+record.count+' 位成员。':record.has_more?'当前扫描页暂无可见成员，可读取下一页。':'当前页暂无成员。';openStatNodes.get('record').value.textContent=String(record.count);openStatNodes.get('record').note.textContent='当前页社区成员';}return;}
  if(type==='relation'){clearOpen(record.active?'已加入社区，请刷新社区资料。':'已退出社区，请刷新社区资料。');if(activeIndex===openIndex&&result)result.hidden=true;return;}
  if(type!=='status')return;
  clearOpen('资料已读取，可查看详情；'+currentSubjectRelation(record)+'。');openRecord=record;
  openStatNodes.get('record').value.textContent='已读取';openStatNodes.get('record').note.textContent='社区档案';openStatNodes.get('relation').value.textContent=currentSubjectRelation(record).replace('当前关系未确认','未确认').replace('当前工作区角色不适用加入关系','不适用');openStatNodes.get('relation').note.textContent='当前身份';openStatNodes.get('status').value.textContent=profileStateLabel(record.state);openStatNodes.get('status').note.textContent='社区目录状态';
  openPair(openSummary,'社区编号',record.id);openPair(openSummary,'关系类型',currentSubjectRelation(record));openPair(openSummary,'列表说明','点击下方按钮查看完整社区资料。');
  for(const [label,key] of [['社区编号','id'],['社区名称','name'],['社区介绍','description'],['状态','state'],['当前版本','version'],['联系人及联系方式','contact']]){
   if(record[key]===undefined)continue;
   const value=key==='state'?({DRAFT:'草稿',PENDING:'待审核',CORRECTION:'待补充资料',REJECTED:'已驳回',APPROVED:'已通过',PAUSED:'已暂停'}[record[key]]||String(record[key])):String(record[key]);openPair(openFields,label,value);
  }
  openPair(openFields,'本人当前社区关系',currentSubjectRelation(record));
  openCard.hidden=false;showOpen.hidden=false;if(activeIndex===openIndex&&result)result.hidden=true;
 };
 document.getElementById('reference').addEventListener('input',()=>{clearOpen('社区编号已改变，请查询所选社区。');if(activeIndex===openIndex&&result)result.hidden=true;});
 showOpen.addEventListener('click',()=>{if(!openRecord)return;openCard.hidden=true;showOpen.hidden=true;openDetails.hidden=false;});
 backOpen.addEventListener('click',()=>{if(!openRecord)return;openDetails.hidden=true;openCard.hidden=false;showOpen.hidden=false;});
 refreshOpen.addEventListener('click',()=>document.getElementById('read').click());


 // Page20: only original order/verified split observations; never a payment action.
 // COMMUNITY_SNAPSHOT_BEGIN
 const reportPanel=document.getElementById('communityEarnings').closest('section'),reportIndex=panels.indexOf(reportPanel);
 reportPanel.classList.add('community-report-panel');
 const legacyReportCopy=reportPanel.querySelector('p');if(legacyReportCopy)legacyReportCopy.hidden=true;
 const reportQuery=document.createElement('div');reportQuery.className='open-query';
 const reportControls=document.createElement('details'),reportControlTitle=document.createElement('summary');reportControls.className='report-query-controls';reportControls.open=true;reportControlTitle.textContent='查询条件';reportControls.append(reportControlTitle,reportQuery);
 const reportLabel=document.createElement('label');reportLabel.ariaLabel='社区编号';
 const reportReference=document.createElement('input');reportReference.id='reportReference';reportReference.ariaLabel='社区编号';reportReference.placeholder='社区编号';reportLabel.append(reportReference);
 reportReference.addEventListener('input',()=>{document.getElementById('reference').value=reportReference.value;document.getElementById('reference').oninput();});
 const reportKeywordLabel=document.createElement('label');reportKeywordLabel.ariaLabel='关键字';const reportKeyword=document.createElement('input');reportKeyword.type='search';reportKeyword.ariaLabel='关键字';reportKeyword.placeholder='订单号、分账单号、接收方';reportKeywordLabel.append(reportKeyword);
 const reportStatusLabel=document.createElement('label');reportStatusLabel.ariaLabel='处理状态';const reportStatus=document.createElement('select');reportStatus.ariaLabel='处理状态';for(const [value,label]of [['ALL','全部状态'],['PENDING','待处理'],['FINISHED','已完成'],['UNKNOWN','待核实']]){const option=document.createElement('option');option.value=value;option.textContent=label;reportStatus.append(option);}reportStatusLabel.append(reportStatus);
 reportStatus.value='ALL';
 const reportSearch=document.createElement('button');reportSearch.type='button';reportSearch.className='primary-action';reportSearch.textContent='查询';reportSearch.onclick=()=>{if(snapshotKind==='refund')window.communityReadRefunds();else if(snapshotMode==='overview')document.getElementById('communityOrders').click();else document.getElementById('communityEarnings').click();};
 const reportReset=document.createElement('button');reportReset.type='button';reportReset.textContent='重置';reportReset.onclick=()=>{reportKeyword.value='';reportStatus.value='ALL';reportSearch.click();};
 const originalReportActions=[document.getElementById('communityOrders'),document.getElementById('communityEarnings')];for(const action of originalReportActions)action.hidden=true;
 reportQuery.append(reportLabel,reportKeywordLabel,reportStatusLabel,reportSearch,reportReset,...originalReportActions);
 const reportHint=document.createElement('p');reportHint.className='profile-hint';
 const reportCard=document.createElement('article');reportCard.className='community-record-card';
 const reportTitle=document.createElement('h3');reportTitle.textContent='记录列表 · 当前范围';
 const reportSummary=document.createElement('dl');reportCard.append(reportTitle,reportSummary);
 const reportShow=document.createElement('button');reportShow.type='button';reportShow.className='open-detail-action';reportShow.textContent='查看分账详情';reportShow.disabled=true;
 const reportDetail=document.createElement('div');reportDetail.className='community-report-detail';reportDetail.hidden=true;
 const reportRows=document.createElement('div');reportRows.className='report-rows';
 const reportBack=document.createElement('button');reportBack.type='button';reportBack.textContent='返回记录列表';
 reportDetail.append(reportRows,reportBack);
 const reportConfig=document.createElement('details');reportConfig.className='open-actions';
 const configTitle=document.createElement('summary');configTitle.textContent='平台配置社区分账接收关系';reportConfig.append(configTitle);
 for(const key of ['receiverWorkspace','receiverId','receiverVersion'])reportConfig.append(document.getElementById(key).closest('label'));
 reportConfig.append(document.getElementById('bindReceiver'));
 reportConfig.hidden=true;
 const oldConfigTitle=reportPanel.querySelector('h3');if(oldConfigTitle)oldConfigTitle.hidden=true;
 reportPanel.append(reportControls,reportHint,reportCard,reportShow,reportDetail,reportConfig);
 let reportRecord=null,reportViewRevision=0,snapshotMode='overview',snapshotKind='split';
 const snapshotDetail=document.createElement('div');snapshotDetail.className='community-snapshot-detail';snapshotDetail.hidden=true;reportDetail.append(snapshotDetail);
 function syncSnapshotTitle(){if(activeIndex===reportIndex&&pageTitle)pageTitle.textContent=(snapshotMode==='overview'?'订单与结算':snapshotKind==='refund'?'退款管理':'分账明细')+(snapshotMode==='detail'?' · 详情':'');}
 function snapshotList(){snapshotMode='list';reportCard.hidden=true;reportShow.hidden=true;reportDetail.hidden=false;reportRows.hidden=false;snapshotDetail.hidden=true;snapshotDetail.replaceChildren();reportBack.hidden=false;syncSnapshotTitle();}

 const money=(value,currency)=>Number.isSafeInteger(value)&&currency==='CNY'?(value<0?'-':'')+'¥'+Math.floor(Math.abs(value)/100)+'.'+String(Math.abs(value)%100).padStart(2,'0'):'—';
 const reportValue=value=>value===undefined||value===null||value===''?'—':String(value);
 const reportState=value=>({FINISHED:'已完成',SUCCESS:'已完成',REFUNDED:'已退款',PENDING:'待处理',PROCESSING:'处理中',UNCONFIRMED:'待核实',FAILED:'失败',CANCELLED:'已取消'})[value]||reportValue(value);
 function clearReport(message){reportControls.open=true;reportViewRevision++;snapshotDetail.replaceChildren();snapshotDetail.hidden=true;reportRows.hidden=false;reportBack.hidden=false;reportRecord=null;reportHint.textContent=message;reportCard.hidden=snapshotMode==='overview';reportShow.hidden=snapshotMode==='overview';reportShow.disabled=true;reportDetail.hidden=true;reportRows.replaceChildren();reportSummary.replaceChildren();
  for(const pair of [['交易汇总','分账与回退'],['分账明细','当前社区记录'],['退款记录','当前社区退款与回退记录'],['查询状态',message]])openPair(reportSummary,...pair);if(snapshotMode!=='overview')snapshotList();
 }
 window.communityReportView=({type,record})=>{
  if(type==='identity-reset')reportReference.value='';
  if(type==='binding'){clearReport('接收关系已保存，版本 '+reportValue(record.version)+'；仅适用于新分账规则版本，不执行资金操作。');return;}
  if(type!=='listed'){clearReport(type==='loading'?'正在查询…':type==='error'?'未能读取记录，请重试。':'暂无记录');return;}
  clearReport('共 '+record.result.records.length+' 条记录');reportRecord=record;reportControls.open=false;
  const r=record.result,earnings=record.operation==='community_earnings',refunds=record.operation==='community_refunds',revision=reportViewRevision;if(refunds){snapshotKind='refund';snapshotMode='list';}else if(earnings)snapshotKind='split';else snapshotMode='overview';reportSummary.replaceChildren();
  const summaryPairs=earnings?[['分账汇总','当前页金额 '+money(r.page_gross_minor,r.currency)+'；净额 '+money(r.page_net_minor,r.currency)],['分账范围','当前社区分账规则与接收方'],['财务状态',r.finance_status==='UNCONFIRMED'?'待确认':reportValue(r.finance_status)]]:refunds?[['退款汇总','当前页退款/回退 '+money(r.page_returns_minor,r.currency)],['财务状态',r.finance_status==='UNCONFIRMED'?'待确认':reportValue(r.finance_status)]]:[['订单汇总','当前页金额 '+money(r.page_gross_minor,r.currency)],['查询范围',r.totals_scope==='CURRENT_PAGE_ONLY'?'仅当前页':'范围待确认'],['财务状态',r.finance_status==='UNCONFIRMED'?'待确认':reportValue(r.finance_status)]];for(const pair of summaryPairs)openPair(reportSummary,...pair);
  reportShow.textContent=refunds?'查看退款记录':earnings?'查看分账明细':'查看订单';reportShow.disabled=false;reportShow.hidden=false;
  const visibleRecords=r.records.filter(item=>{const keyword=reportKeyword.value.trim().toLowerCase(),raw=JSON.stringify(item).toLowerCase(),state=reportStatus.value,stateValues=Object.values(item||{});const stateMatch=state==='ALL'||state==='PENDING'&&stateValues.some(value=>['PENDING','PROCESSING'].includes(value))||state==='FINISHED'&&stateValues.some(value=>['FINISHED','SUCCESS','REFUNDED'].includes(value))||state==='UNKNOWN'&&stateValues.includes('UNCONFIRMED');return(!keyword||raw.includes(keyword))&&stateMatch;});
  if(!visibleRecords.length){const empty=document.createElement('p');empty.className='report-empty';empty.textContent=r.records.length?'没有符合条件的记录':'暂无记录';reportRows.append(empty);}
  const table=document.createElement('table'),head=document.createElement('thead'),body=document.createElement('tbody'),headRow=document.createElement('tr');table.className='management-data-table';
  const columns=earnings?['订单号','分账单号','接收方','分账金额（元）','回退金额（元）','净额（元）','状态','操作']:refunds?['订单号','退款单号','退款金额（元）','状态','记录时间','操作']:['订单号','商家','门店','订单金额（元）','订单状态','操作'];for(const label of columns){const th=document.createElement('th');th.scope='col';th.textContent=label;headRow.append(th);}head.append(headRow);table.append(head,body);if(visibleRecords.length)reportRows.append(table);
  const openDetail=(item,keys,fieldValue)=>{if(revision!==reportViewRevision||reportRecord!==record)return;snapshotMode='detail';snapshotDetail.replaceChildren();const card=document.createElement('article'),h=document.createElement('h3'),dl=document.createElement('dl'),back=document.createElement('button');card.className='community-record-card';h.textContent=refunds?'退款详情':earnings?'分账详情':'订单详情';card.append(h,dl);for(const [label,key]of keys)openPair(dl,label,fieldValue(key));if(refunds)for(const observation of item.refund_observations||[]){openPair(dl,'退款单号',reportValue(observation.out_refund_no));openPair(dl,'退款金额',money(observation.refund_minor,observation.currency));openPair(dl,'记录时间',Number.isInteger(observation.observed_at)?new Date(observation.observed_at*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'—');openPair(dl,'状态',reportState(observation.finance_status));}back.type='button';back.className='snapshot-detail-action';back.textContent='返回列表';back.onclick=()=>{if(revision===reportViewRevision&&reportRecord===record)snapshotList();};snapshotDetail.append(card,back);snapshotDetail.hidden=false;reportRows.hidden=true;reportBack.hidden=true;syncSnapshotTitle();};
  const addRow=(values,item,keys,fieldValue)=>{const tr=document.createElement('tr');for(const value of values){const td=document.createElement('td');td.textContent=value;tr.append(td);}const action=document.createElement('td'),open=document.createElement('button');open.type='button';open.className='table-row-action';open.textContent='查看';open.onclick=()=>openDetail(item,keys,fieldValue);action.append(open);tr.append(action);body.append(tr);};
  for(const item of visibleRecords){const keys=earnings?[['订单号','reference'],['分账单号','request_id'],['接收方','receiver_id'],['规则编号','rule_id'],['规则版本','rule_version'],['分账金额','received_minor'],['回退金额','returned_minor'],['净额','net_minor'],['渠道状态','provider_state'],['接收方状态','receiver_state'],['状态','finance_status']]:[['订单号','reference'],['商家','merchant_id'],['门店','store_id'],['订单金额','amount_minor'],['订单状态','order_state']];const fieldValue=key=>key.endsWith('_minor')?money(item[key],r.currency):['provider_state','receiver_state','order_state','finance_status'].includes(key)?reportState(item[key]):reportValue(item[key]);if(earnings)addRow([fieldValue('reference'),fieldValue('request_id'),fieldValue('receiver_id'),fieldValue('received_minor'),fieldValue('returned_minor'),fieldValue('net_minor'),reportState(item.finance_status||item.provider_state)],item,keys,fieldValue);else if(refunds){const observations=item.refund_observations?.length?item.refund_observations:[null];for(const observation of observations)addRow([fieldValue('reference'),reportValue(observation?.out_refund_no),money(observation?.refund_minor,observation?.currency),reportState(observation?.finance_status||item.order_state),Number.isInteger(observation?.observed_at)?new Date(observation.observed_at*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'—'],item,keys,fieldValue);}else addRow([fieldValue('reference'),fieldValue('merchant_id'),fieldValue('store_id'),fieldValue('amount_minor'),fieldValue('order_state')],item,keys,fieldValue);}
  if(!earnings&&!refunds){reportCard.hidden=false;reportShow.hidden=false;reportDetail.hidden=true;if(activeIndex===reportIndex&&pageTitle)pageTitle.textContent=reportPanel.querySelector('h2').textContent;}else if(snapshotMode!=='overview')snapshotList();
 };
 reportShow.addEventListener('click',()=>{if(!reportRecord)return;if(['community_earnings','community_refunds'].includes(reportRecord.operation)){snapshotKind=reportRecord.operation==='community_refunds'?'refund':'split';snapshotList();return;}reportCard.hidden=true;reportShow.hidden=true;reportDetail.hidden=false;});
 reportBack.addEventListener('click',()=>{snapshotMode='overview';snapshotDetail.hidden=true;reportRows.hidden=false;reportDetail.hidden=true;reportCard.hidden=false;reportShow.hidden=false;if(activeIndex===reportIndex&&pageTitle)pageTitle.textContent=reportPanel.querySelector('h2').textContent;});
 clearReport('尚未查询，不填充真实结果');
 // COMMUNITY_SNAPSHOT_END

 // Page21: field cards use original scoped promotion responses, never link views as members.
 const promotionPanel=document.getElementById('listPromotions').closest('section'),promotionIndex=panels.indexOf(promotionPanel);
 promotionPanel.classList.add('community-promotion-panel');
 const promotionHeader=document.createElement('header');promotionHeader.className='management-page-header';const promotionHeaderCopy=document.createElement('div'),promotionEyebrow=document.createElement('span'),promotionHeading=document.createElement('h3'),promotionDescription=document.createElement('p');promotionEyebrow.className='management-page-eyebrow';promotionEyebrow.textContent='社区经营';promotionHeading.textContent='社区推广管理';promotionDescription.textContent='查看推广入口、有效状态与已认证去重参与；创建和状态修改仅在操作面板中展开。';promotionHeaderCopy.append(promotionEyebrow,promotionHeading,promotionDescription);promotionHeader.append(promotionHeaderCopy);
 const promotionStats=document.createElement('div');promotionStats.className='management-stats';const promotionStatNodes=new Map();for(const [key,label,note]of [['records','推广记录','尚未查询'],['active','有效推广','当前页统计'],['members','新增成员','已认证去重参与']]){const card=document.createElement('article'),caption=document.createElement('span'),value=document.createElement('strong'),small=document.createElement('small');card.className='management-stat';caption.textContent=label;value.textContent='—';small.textContent=note;card.append(caption,value,small);promotionStats.append(card);promotionStatNodes.set(key,{value,note:small});}promotionPanel.prepend(promotionHeader,promotionStats);
 const promotionQuery=document.createElement('div');promotionQuery.className='open-query';
 const promotionLabel=document.createElement('label');promotionLabel.textContent='社区编号';
 const promotionReference=document.createElement('input');promotionReference.id='promotionReference';promotionLabel.append(promotionReference);
 promotionReference.addEventListener('input',()=>{document.getElementById('reference').value=promotionReference.value;document.getElementById('reference').oninput();});
 promotionQuery.append(promotionLabel,document.getElementById('listPromotions'));
 const promotionHint=document.createElement('p');promotionHint.className='profile-hint';
 const promotionRows=document.createElement('div');promotionRows.className='promotion-records';
 const promotionDetail=document.createElement('div');promotionDetail.className='community-promotion-detail';promotionDetail.hidden=true;
 const promotionFields=document.createElement('dl'),promotionBack=document.createElement('button');promotionBack.type='button';promotionBack.textContent='返回推广记录';
 const promotionDetailHeading=document.createElement('h3');promotionDetailHeading.textContent='记录详情';promotionDetail.append(promotionDetailHeading,promotionFields,promotionBack);
 const promotionActions=document.createElement('details');promotionActions.className='open-actions';
 const promotionSummary=document.createElement('summary');promotionSummary.textContent='创建推广及更新状态';promotionActions.append(promotionSummary);
 for(const key of ['promotionScene','promotionTitle','promotionExpiry','promotionCode','promotionVersion','promotionState'])promotionActions.append(document.getElementById(key).closest('label'));
 promotionActions.append(document.getElementById('createPromotion'),document.getElementById('savePromotionState'));
 const promotionNote=document.createElement('p');promotionNote.className='profile-hint';promotionNote.textContent='请选择社区和推广状态。';promotionActions.append(promotionNote);
 promotionPanel.append(promotionQuery,promotionHint,promotionRows,promotionDetail,promotionActions);
 const expiry=value=>Number.isInteger(value)?new Date(value*1000).toISOString().replace('T',' ').replace('.000Z',' UTC'):'暂无有效时间';
 const promotionValue=(record,key)=>record[key]===undefined?'暂无数据':key==='expires_at'?expiry(record[key]):key==='status'?({ACTIVE:'有效',PAUSED:'已暂停'}[record[key]]||String(record[key])):String(record[key]);
 function clearPromotion(message){promotionActions.open=false;promotionRows.replaceChildren();promotionFields.replaceChildren();promotionRows.hidden=false;promotionDetail.hidden=true;promotionHint.textContent=message;for(const node of promotionStatNodes.values())node.value.textContent='—';promotionStatNodes.get('records').note.textContent='尚未查询';}
 function promotionDetails(record){promotionFields.replaceChildren();for(const [label,key]of [['小程序门店场景','scene'],['推广标题','title'],['到期时间','expires_at'],['推广码','id'],['当前版本','version'],['状态','status'],['新成员','new_members'],['已认证去重参与','authenticated_redemptions']])openPair(promotionFields,label,promotionValue(record,key));promotionRows.hidden=true;promotionDetail.hidden=false;}
 window.communityPromotionView=({type,record})=>{
  if(type==='identity-reset')promotionReference.value='';
  if(type==='saved'){clearPromotion('推广记录已保存。');promotionDetails(record);return;}
  if(type!=='listed'){clearPromotion(type==='loading'?'正在处理…':type==='error'?'操作失败，请重新查询。':'尚未查询推广记录');return;}
  clearPromotion('已读取当前页 '+record.result.records.length+' 条推广记录；统计为已认证去重参与，不是浏览量。');
  promotionStatNodes.get('records').value.textContent=String(record.result.records.length);promotionStatNodes.get('records').note.textContent='当前页记录';promotionStatNodes.get('active').value.textContent=String(record.result.records.filter(item=>item.status==='ACTIVE').length);promotionStatNodes.get('active').note.textContent='当前页有效状态';promotionStatNodes.get('members').value.textContent=String(record.result.records.reduce((sum,item)=>sum+(Number.isSafeInteger(item.new_members)?item.new_members:0),0));promotionStatNodes.get('members').note.textContent='当前页已认证去重';
  if(!record.result.records.length){const empty=document.createElement('p');empty.textContent='当前页没有推广记录；其他页及未读取范围不作推断。';promotionRows.append(empty);}
  for(const item of record.result.records){
   const card=document.createElement('article');card.className='community-record-card';const title=document.createElement('h3');title.textContent='记录列表 · 当前范围';const fields=document.createElement('dl');
   for(const [label,key]of [['小程序门店场景','scene'],['推广标题','title'],['到期时间','expires_at']])openPair(fields,label,promotionValue(item,key));
   openPair(fields,'列表说明','点击下方按钮查看完整资料。');card.append(title,fields);
   const show=document.createElement('button');show.type='button';show.className='open-detail-action';show.textContent='查看推广详情';show.addEventListener('click',()=>{if(record.select(item))promotionDetails(item);});promotionRows.append(card,show);
  }
 };
 promotionBack.addEventListener('click',()=>{promotionDetail.hidden=true;promotionRows.hidden=false;});
 clearPromotion('尚未查询推广记录');

 // Pages22/49: scoped original merchant-name projection; membership never implies payment admission.
 const memberPanel=document.getElementById('communityMerchantMembers'),memberIndex=panels.indexOf(memberPanel);
 memberPanel.classList.add('community-members-panel');
 const memberHeader=document.createElement('header');memberHeader.className='management-page-header';const memberHeaderCopy=document.createElement('div'),memberEyebrow=document.createElement('span'),memberHeading=document.createElement('h3'),memberDescription=document.createElement('p');memberEyebrow.className='management-page-eyebrow';memberEyebrow.textContent='商家管理';memberHeading.textContent='社区商家';memberDescription.textContent='';memberHeaderCopy.append(memberEyebrow,memberHeading,memberDescription);memberHeader.append(memberHeaderCopy);
 const memberStats=document.createElement('div');memberStats.className='management-stats';const memberStatNodes=new Map();for(const [key,label,note]of [['records','社区商家','尚未查询'],['signed','微信签约完成','仅签验查询记录'],['unknown','待核验渠道','不从成员关系推断']]){const card=document.createElement('article'),caption=document.createElement('span'),value=document.createElement('strong'),small=document.createElement('small');card.className='management-stat';caption.textContent=label;value.textContent='—';small.textContent=note;card.append(caption,value,small);memberStats.append(card);memberStatNodes.set(key,{value,note:small});}memberPanel.append(memberHeader,memberStats);
 const memberFilters=document.createElement('div'),memberKeywordLabel=document.createElement('label'),memberKeyword=document.createElement('input'),memberStateLabel=document.createElement('label'),memberState=document.createElement('select');memberFilters.className='management-filter-bar';memberKeyword.type='search';memberKeyword.placeholder='商家名称或账号编号';memberKeywordLabel.textContent='商家关键词';memberKeywordLabel.append(memberKeyword);memberStateLabel.textContent='签约状态';for(const [value,label]of [['ALL','全部状态'],['SIGNED','微信签约完成'],['UNKNOWN','待核验渠道']]){const option=document.createElement('option');option.value=value;option.textContent=label;memberState.append(option);}memberStateLabel.append(memberState);memberFilters.append(memberKeywordLabel,memberStateLabel);memberPanel.append(memberFilters);
 const memberQuery=document.createElement('div');memberQuery.className='open-query';memberQuery.append(document.getElementById('memberCommunityReference').closest('label'),document.getElementById('queryMerchantMembers'));
 const memberHint=document.createElement('p');memberHint.className='profile-hint';
 const memberRows=document.createElement('div');memberRows.className='member-records';
 const memberDetail=document.createElement('div');memberDetail.className='community-member-detail';memberDetail.hidden=true;
 const memberFields=document.createElement('dl'),memberBack=document.createElement('button'),memberRefresh=document.createElement('button');memberBack.type='button';memberBack.textContent='返回社区商家列表';memberRefresh.type='button';memberRefresh.textContent='重新查询当前社区';const memberDetailHeading=document.createElement('h3');memberDetailHeading.textContent='社区商家详情';memberDetail.append(memberDetailHeading,memberFields,memberBack,memberRefresh);
 memberPanel.append(memberQuery,memberHint,memberRows,memberDetail);
 function memberName(item){
  if(item.merchant_name_status==='MATCHED'&&typeof item.merchant_name==='string'&&item.merchant_name)return item.merchant_name;
  if(item.merchant_name_status==='MULTIPLE'&&Array.isArray(item.merchant_names))return '多个门店：'+item.merchant_names.filter(v=>typeof v==='string').join('、');
  return ({NO_PROFILE:'商家资料尚未建立',NO_ADMITTED_MAPPING:'暂无已准入商家资料',MAPPING_UNAVAILABLE:'商家资料当前不可用'}[item.merchant_name_status]||'商家名称未填写');
 }
 function memberWechat(item){
  if(item.wechat_status_source!=='SIGNED_PROVIDER_QUERY')return item.wechat_status_source==='MULTIPLE_MERCHANT_WORKSPACES'?'多个门店，签约状态需分别核验':'签约状态待核验';
  const states={APPLYMENT_STATE_EDITTING:'待完善资料',APPLYMENT_STATE_AUDITING:'微信审核中',APPLYMENT_STATE_REJECTED:'微信已驳回',APPLYMENT_STATE_TO_BE_CONFIRMED:'待确认',APPLYMENT_STATE_TO_BE_SIGNED:'待签约',APPLYMENT_STATE_SIGNING:'签约中',APPLYMENT_STATE_FINISHED:'微信进件签约已完成',APPLYMENT_STATE_CANCELED:'已取消'};
  return states[item.wechat_status]?states[item.wechat_status]:'未核验的渠道状态';
 }
 function clearMembers(message){memberRows.replaceChildren();memberFields.replaceChildren();memberRows.hidden=false;memberDetail.hidden=true;memberHint.textContent=message;for(const node of memberStatNodes.values())node.value.textContent='—';memberStatNodes.get('records').note.textContent='尚未查询';}
 let memberSnapshot=null;function renderMemberSnapshot(){if(memberSnapshot)window.communityMerchantMembersView({type:'listed',record:memberSnapshot,filtered:true});}memberKeyword.addEventListener('input',renderMemberSnapshot);memberState.addEventListener('change',renderMemberSnapshot);
 window.communityMerchantMembersView=({type,record,filtered=false})=>{
  if(type==='identity-reset')document.getElementById('memberCommunityReference').value='';
  if(type!=='listed'){clearMembers(type==='loading'?'正在查询成员关系…':type==='error'?'查询失败，请重试。':'尚未查询成员关系');return;}
  if(!filtered)memberSnapshot=record;const keyword=memberKeyword.value.trim().toLowerCase(),state=memberState.value,visible=record.result.records.filter(item=>(!keyword||[memberName(item),item.user_id].join(' ').toLowerCase().includes(keyword))&&(state==='ALL'||state==='SIGNED'&&item.wechat_status_source==='SIGNED_PROVIDER_QUERY'&&item.wechat_status==='APPLYMENT_STATE_FINISHED'||state==='UNKNOWN'&&item.wechat_status_source!=='SIGNED_PROVIDER_QUERY'));clearMembers('当前筛选显示 '+visible.length+' 家社区关联商家；这里不是管理员或员工账号。');
  memberStatNodes.get('records').value.textContent=String(visible.length);memberStatNodes.get('records').note.textContent='当前筛选商家';memberStatNodes.get('signed').value.textContent=String(visible.filter(item=>item.wechat_status_source==='SIGNED_PROVIDER_QUERY'&&item.wechat_status==='APPLYMENT_STATE_FINISHED').length);memberStatNodes.get('unknown').value.textContent=String(visible.filter(item=>item.wechat_status_source!=='SIGNED_PROVIDER_QUERY').length);
  if(!visible.length){const empty=document.createElement('p');empty.textContent=record.result.has_more?'当前筛选暂无关联商家，仍有下一页可查询。':'当前筛选没有社区关联商家；不补造商家资料。';memberRows.append(empty);}
  for(const item of visible){const card=document.createElement('article');card.className='community-record-card';const title=document.createElement('h3');title.textContent='商家列表 · 当前范围';const fields=document.createElement('dl');
   for(const pair of [['商家名称',memberName(item)],['关系类型','社区关联商家'],['所属范围','当前授权社区 '+record.community_id],['列表说明','点击下方按钮查看本次已读关系详情。']])openPair(fields,...pair);card.append(title,fields);
   const show=document.createElement('button');show.type='button';show.className='open-detail-action';show.textContent='查看社区商家详情';show.addEventListener('click',()=>{if(!record.select())return;memberFields.replaceChildren();for(const pair of [['商家名称',memberName(item)],['商家账号编号',item.user_id],['关系类型','社区关联商家'],['所属范围','当前社区 '+record.community_id],['关系更新时间',Number.isInteger(item.updated_at)?new Date(item.updated_at*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})+' 北京时间':'暂无有效时间'],['微信进件与签约',memberWechat(item)],['渠道记录时间',item.wechat_status_source==='SIGNED_PROVIDER_QUERY'&&Number.isInteger(item.wechat_observed_at)?new Date(item.wechat_observed_at*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})+' 北京时间':'暂无记录']])openPair(memberFields,...pair);memberRows.hidden=true;memberDetail.hidden=false;});memberRows.append(card,show);
  }
 };
 memberBack.addEventListener('click',()=>{memberDetail.hidden=true;memberRows.hidden=false;});memberRefresh.addEventListener('click',()=>document.getElementById('queryMerchantMembers').click());clearMembers('尚未查询成员关系');

 // Insert before select() in the original admin shell. Reuse original controls, not copies.
 const receiverPanel=document.getElementById('receiverRelations'),receiverIndex=panels.indexOf(receiverPanel);
 receiverPanel.classList.add('community-receiver-panel');
 const receiverHint=document.createElement('p');receiverHint.className='profile-hint';
 const receiverRows=document.createElement('div'),receiverDetail=document.createElement('article');receiverRows.className='receiver-records';receiverDetail.className='community-receiver-detail';receiverDetail.hidden=true;
 const receiverFields=document.createElement('dl'),receiverBack=document.createElement('button');receiverBack.type='button';receiverBack.className='platform-order-button';receiverBack.textContent='返回接收关系列表';receiverBack.hidden=true;const receiverDetailTitle=document.createElement('h3');receiverDetailTitle.textContent='记录详情';receiverDetail.append(receiverDetailTitle,receiverFields);
 const receiverActions=document.createElement('details');receiverActions.className='open-actions';const receiverSummary=document.createElement('summary');receiverSummary.textContent='接收关系配置';receiverActions.append(receiverSummary);
 const receiverQueryControls=document.createElement('details'),receiverQuerySummary=document.createElement('summary');receiverQueryControls.className='receiver-query-controls open-actions';receiverQueryControls.open=true;receiverQuerySummary.textContent='查询接收关系';receiverQueryControls.append(receiverQuerySummary);
 const receiverQuery=document.createElement('div');receiverQuery.className='open-query';receiverQuery.append(document.getElementById('receiverCommunityReference').closest('label'),document.getElementById('receiverWorkspace').closest('label'),document.getElementById('listReceiverRelations'));
 receiverActions.append(document.getElementById('receiverId').closest('label'),document.getElementById('receiverVersion').closest('label'),document.getElementById('readReceiverRelation'),document.getElementById('bindReceiver'));
 const receiverNotice=document.createElement('p');receiverNotice.textContent='保存后仅影响新分账规则；不会执行资金操作。';receiverActions.append(receiverNotice);
 receiverQueryControls.append(receiverQuery);reportConfig.hidden=true;receiverPanel.append(receiverHint,receiverRows,document.getElementById('moreReceiverRelations'),receiverDetail,receiverBack,receiverQueryControls,receiverActions);
 const workspaceText=r=>r.provider_workspace_status==='LEGACY_NOT_RECORDED'?'历史记录未保存管理范围':typeof r.provider_workspace==='string'?r.provider_workspace:'未返回';
 const receiverPairs=r=>[['财务管理范围',workspaceText(r)],['本次查询范围',r.requested_provider_workspace||'待确认'],['接收方编号',r.receiver_id],['当前版本',r.version],['适用范围','新分账规则']];
 function syncReceiverTitle(){if(activeIndex===receiverIndex&&pageTitle)pageTitle.textContent=receiverPanel.querySelector('h2').textContent+(receiverDetail.hidden?'':' · 详情');}
 function clearReceiverUi(message){receiverRows.replaceChildren();receiverFields.replaceChildren();receiverDetail.hidden=true;receiverBack.hidden=true;receiverRows.hidden=false;receiverHint.textContent=message;syncReceiverTitle();}
 window.communityReceiverView=({type,record})=>{
  if(type==='identity-reset'||type==='error')receiverActions.open=false;
  if(type==='detail'||type==='saved'){receiverActions.open=false;clearReceiverUi(type==='saved'?'接收关系已保存。':'已读取接收关系。');for(const pair of receiverPairs(record))openPair(receiverFields,...pair);receiverDetail.hidden=false;receiverBack.hidden=false;receiverRows.hidden=true;syncReceiverTitle();return;}
  if(type!=='listed'){if(type==='error'||type==='reset')receiverQueryControls.open=true;clearReceiverUi(type==='error'?'操作失败，请重试。':type==='loading'?'正在查询接收关系…':'尚未查询接收关系');return;}
  receiverQueryControls.open=false;clearReceiverUi('已读取当前扫描页 '+record.result.records.length+' 条；不是全部关系汇总。');
  if(!record.result.records.length){const p=document.createElement('p');p.textContent=record.result.has_more?'本扫描页没有可显示关系，仍有下一页。':'本页没有可显示关系；不自动推定可用初始版本。';receiverRows.append(p);}
  for(const item of record.result.records){const card=document.createElement('article');card.className='community-record-card';const title=document.createElement('h3');title.textContent='记录列表 · 当前范围';const fields=document.createElement('dl');for(const pair of receiverPairs(item))openPair(fields,...pair);card.append(title,fields);const show=document.createElement('button');show.type='button';show.className='open-detail-action';show.textContent='查看接收关系详情';show.addEventListener('click',()=>record.select(item));receiverRows.append(card,show);}
 };
 receiverBack.addEventListener('click',()=>window.communityReceiverReturn());
 clearReceiverUi('尚未查询接收关系');

 // PLATFORM_ORDER_CARDS_BEGIN: original platform_orders only, no provider actions.
 const platformResult=document.getElementById('platformViewResult'),platformPanel=platformResult.closest('section');
 platformPanel.classList.add('platform-orders-panel');
 const orderQuery=document.createElement('details'),orderSummary=document.createElement('summary');orderSummary.textContent='运营查询与筛选';orderQuery.append(orderSummary);
 for(const id of ['platformView','platformOrderStatus'])orderQuery.append(document.getElementById(id).closest('label'));
 orderQuery.append(document.getElementById('readPlatformView'));
 const orderTitle=document.createElement('h3'),orderHint=document.createElement('p'),orderRows=document.createElement('div'),orderDetail=document.createElement('div'),orderBack=document.createElement('button');
 orderTitle.textContent='支付证据';orderRows.className='platform-order-rows';orderDetail.className='platform-order-detail';orderBack.textContent='返回列表';orderBack.type='button';orderBack.className='platform-order-button';
 platformPanel.append(orderTitle,orderHint,orderRows,orderDetail,orderBack,document.getElementById('morePlatformView'),platformResult,orderQuery);
 let orderViewRevision=0;
 function syncOrderPageTitle(){platformPanel.querySelector('h2').hidden=document.getElementById('platformView').value==='platform_orders';orderTitle.hidden=true;if(!pageTitle||activeIndex!==panels.indexOf(platformPanel))return;pageTitle.textContent=document.getElementById('platformView').value==='platform_orders'?orderTitle.textContent:platformPanel.querySelector('h2').textContent;}
 function clearOrderView(message){orderViewRevision++;orderRows.replaceChildren();orderDetail.replaceChildren();orderRows.hidden=false;orderDetail.hidden=true;orderBack.hidden=true;orderTitle.textContent='支付证据';orderHint.textContent=message;platformResult.hidden=false;syncOrderPageTitle();}
 const orderValue=v=>v===undefined||v===null?'暂无数据':String(v);
 function orderFields(r,detail){const scope=r.scope||{};const state=({PENDING:'待处理',SUCCESS:'支付成功',FAILED:'支付失败',CANCELLED:'已取消',REFUNDED:'已退款'}[r.order_state]||'状态待确认'),money=Number.isSafeInteger(r.amount_minor)&&typeof r.currency==='string'&&r.currency?(r.currency==='CNY'?'¥':'')+(r.amount_minor/100).toFixed(2)+' '+r.currency:'金额未返回';const fields=[['订单号',r.reference],['商家',orderValue(scope.merchant_id)],['门店',orderValue(scope.store_id)],['订单金额',money],['订单状态',state],['支付状态',r.payment_evidence?'已核验':'待核验'],['核销状态',r.finance_status==='UNCONFIRMED'?'未确认':r.finance_status]];
  if(detail)fields.push(['租户',orderValue(scope.tenant_id)],['支付证据',r.payment_evidence||'当前未返回已验证支付证据；不据此断言未支付']);return fields;}
 function orderCard(title,fields){const card=document.createElement('article'),h=document.createElement('h3'),dl=document.createElement('dl');card.className='platform-order-card';h.textContent=title;card.append(h);for(const [label,value]of fields){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=orderValue(value);dl.append(dt,dd);}card.append(dl);return card;}
 window.communityPlatformOrdersView=({type,record,current})=>{
  clearOrderView('请选择订单并查询。');
  const orders=type==='listed'||document.getElementById('platformView').value==='platform_orders';orderTitle.hidden=true;orderHint.hidden=!orders;orderRows.hidden=!orders;
  if(type!=='listed')return;
  const revision=orderViewRevision;platformResult.hidden=true;
  orderHint.textContent=record.coverage_complete===false?'部分商家资料暂不可用；当前仅显示可查看订单。':'当前可查看订单。';
  if(!Array.isArray(record.records)){clearOrderView('本次记录格式未确认，请重新读取；不会把错误显示为空列表。');return;}
  if(!record.records.length){orderRows.textContent=record.has_more?'当前扫描页没有可显示订单，仍有下一页。':'当前筛选没有可显示订单。';return;}
  for(const r of record.records){const card=orderCard('记录列表 · 当前范围',orderFields(r,false)),show=document.createElement('button');show.type='button';show.className='platform-order-button';show.textContent='查看支付证据详情';
   show.onclick=()=>{if(revision!==orderViewRevision||!current())return;orderRows.hidden=true;orderDetail.replaceChildren(orderCard('记录详情',orderFields(r,true)));orderDetail.hidden=false;orderBack.hidden=false;orderTitle.textContent='支付证据详情';syncOrderPageTitle();};orderRows.append(card,show);}
  orderBack.onclick=()=>{if(revision!==orderViewRevision||!current())return;orderDetail.replaceChildren();orderDetail.hidden=true;orderRows.hidden=false;orderBack.hidden=true;orderTitle.textContent='支付证据';syncOrderPageTitle();};
 };
 clearOrderView('请选择订单并查询。');
 // PLATFORM_ORDER_CARDS_END

 // PLATFORM_COMMUNITY_REVIEW_BEGIN: original list/status/review only.
 const reviewPanel=document.getElementById('review').closest('section'),reviewIndex=panels.indexOf(reviewPanel);
 reviewPanel.classList.add('platform-review-panel');
 const reviewQuery=document.createElement('details'),reviewSummary=document.createElement('summary');reviewSummary.textContent='社区筛选与查询';reviewQuery.append(reviewSummary,document.getElementById('pending'),document.getElementById('directoryStatus').closest('label'),document.getElementById('listDirectory'));
 const reviewHint=document.createElement('p'),reviewRows=document.createElement('div'),reviewDetail=document.createElement('div'),reviewEditor=document.createElement('div'),reviewBack=document.createElement('button'),reviewEdit=document.createElement('button'),reviewRead=document.createElement('button'),reviewMore=document.createElement('button');
 reviewRows.className='platform-review-rows';reviewDetail.className='platform-review-detail';reviewEditor.className='platform-review-editor';reviewBack.textContent='返回审核列表';reviewEdit.textContent='开始审核';reviewRead.textContent='刷新社区资料';reviewMore.textContent='下一页审核记录';for(const b of [reviewBack,reviewEdit,reviewRead,reviewMore]){b.type='button';b.className='platform-review-button';}
 reviewEditor.append(document.getElementById('decision').closest('label'),document.getElementById('opinion').closest('label'),document.getElementById('review'));
 reviewPanel.append(reviewHint,reviewRows,reviewDetail,reviewEditor,reviewBack,reviewEdit,reviewRead,reviewMore,reviewQuery);
 let reviewSnapshot=null,reviewRecord=null,reviewReadCurrent=null,reviewRevision=0,reviewMode='list';
 const reviewState=s=>({DRAFT:'草稿',PENDING:'待审核',APPROVED:'已通过',CORRECTION:'待补充资料',REJECTED:'已驳回',PAUSED:'已暂停'}[s]||String(s));
 function reviewFields(r,detail){const fields=[['社区状态',reviewState(r.state)],['审核决定',['APPROVED','CORRECTION','REJECTED','PAUSED'].includes(r.state)?reviewState(r.state):'尚未形成审核决定'],['审核意见',r.opinion||'暂无审核意见']];if(detail)fields.push(['社区编号',r.id],['社区名称',r.name],['社区介绍',r.description],['联系人及联系方式',r.contact],['当前版本',r.version]);return fields;}
 function reviewCard(title,record,detail){const card=document.createElement('article'),h=document.createElement('h3'),dl=document.createElement('dl');card.className='community-record-card';h.textContent=title;card.append(h,dl);for(const [label,value]of reviewFields(record,detail)){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value===undefined||value===null?'未填写':String(value);dl.append(dt,dd);}return card;}
 function syncReviewTitle(){if(activeIndex!==reviewIndex)return;reviewPanel.querySelector('h2').hidden=true;if(pageTitle)pageTitle.textContent=reviewMode==='detail'?'社区审核 · 详情':reviewMode==='edit'?'社区审核 · 审核界面':'社区审核';}
 function clearReview(message){reviewRevision++;reviewSnapshot=null;reviewRecord=null;reviewReadCurrent=null;reviewMode='list';reviewRows.replaceChildren();reviewDetail.replaceChildren();reviewEditor.hidden=true;reviewRows.hidden=false;reviewDetail.hidden=true;for(const b of [reviewBack,reviewEdit,reviewRead,reviewMore])b.hidden=true;reviewHint.textContent=message;syncReviewTitle();}
 function showReviewList(){reviewRevision++;const revision=reviewRevision;reviewMode='list';reviewRows.replaceChildren();reviewRows.hidden=false;reviewDetail.hidden=true;reviewEditor.hidden=true;reviewBack.hidden=true;reviewEdit.hidden=true;reviewRead.hidden=true;reviewMore.hidden=!reviewSnapshot?.result.has_more;reviewHint.textContent='当前筛选结果；详情展示最新状态。';if(reviewSnapshot){for(const r of reviewSnapshot.result.records){const open=document.createElement('button');open.textContent='查看审核详情';open.type='button';open.className='platform-review-button';open.onclick=()=>{if(revision!==reviewRevision)return;return reviewSnapshot.select(r);};reviewRows.append(reviewCard('记录列表 · 当前范围',r,false),open);}if(!reviewSnapshot.result.records.length)reviewRows.textContent=reviewSnapshot.result.has_more?'当前页暂无记录，仍可查看下一页。':'当前筛选暂无社区记录。';}syncReviewTitle();}
 reviewMore.onclick=()=>document.getElementById('more').onclick();
 reviewBack.onclick=()=>{if(reviewSnapshot)showReviewList();else clearReview('请重新查询审核列表。');};
 reviewEdit.onclick=()=>{if(!reviewRecord)return;reviewMode='edit';reviewDetail.hidden=true;reviewEditor.hidden=false;reviewEdit.hidden=true;reviewHint.textContent='请选择审核结果并填写审核意见。';syncReviewTitle();};
 reviewRead.onclick=()=>{if(reviewReadCurrent)return reviewReadCurrent();};
 window.communityPlatformReviewView=({type,record})=>{
  if(type==='reset'||type==='error'||type==='loading'){clearReview(type==='error'?'读取或审核未确认，请重新查询。':type==='loading'?'正在读取社区目录…':'请选择状态并查询。');return;}
  if(type==='loading-detail'){reviewRevision++;reviewRecord=null;reviewReadCurrent=null;reviewRows.hidden=true;reviewDetail.replaceChildren();reviewDetail.hidden=true;reviewEditor.hidden=true;reviewEdit.hidden=true;reviewRead.hidden=true;reviewBack.hidden=true;reviewMore.hidden=true;reviewHint.textContent='正在处理社区审核…';return;}
  if(type==='listed'){reviewSnapshot=record;reviewRecord=null;showReviewList();return;}
  if(type==='detail'){reviewRevision++;reviewRecord=record.record;document.getElementById('opinion').value=reviewRecord.opinion||'';reviewReadCurrent=record.read;reviewMode='detail';reviewRows.hidden=true;reviewDetail.replaceChildren(reviewCard('记录详情',reviewRecord,true));reviewDetail.hidden=false;reviewEditor.hidden=true;reviewBack.hidden=false;reviewEdit.hidden=false;reviewRead.hidden=false;reviewMore.hidden=true;reviewHint.textContent='当前申请状态：'+reviewState(reviewRecord.state)+'。';syncReviewTitle();}
 };
 clearReview('请按状态查询社区申请。');
 // PLATFORM_COMMUNITY_REVIEW_END

 // PLATFORM_OPERATIONS_CARDS_BEGIN: original non-order views; orders stay in original31.
 const operationRows=document.createElement('div'),operationDetail=document.createElement('div'),operationHint=document.createElement('p'),operationBack=document.createElement('button'),operationQuery=document.createElement('button'),operationFilters=document.createElement('div'),operationKeywordLabel=document.createElement('label'),operationKeyword=document.createElement('input'),operationTypeLabel=document.createElement('label'),operationType=document.createElement('select');
 operationFilters.className='management-filter-bar';operationKeyword.type='search';operationKeyword.placeholder='订单号、用户、事件或关联对象';operationKeywordLabel.textContent='运营关键词';operationKeywordLabel.append(operationKeyword);operationTypeLabel.textContent='业务视图';for(const [value,label]of [['ALL','全部业务'],['platform_overview','经营总览'],['platform_customers','用户管理'],['platform_audit','审计记录']]){const option=document.createElement('option');option.value=value;option.textContent=label;operationType.append(option);}operationTypeLabel.append(operationType);operationFilters.append(operationKeywordLabel,operationTypeLabel);
 operationRows.className='platform-operation-rows';operationDetail.className='platform-operation-detail';operationBack.textContent='返回运营查询列表';operationQuery.textContent='打开运营查询条件';operationQuery.className='operation-query-action';for(const b of [operationBack,operationQuery]){b.type='button';b.className='platform-order-button';}platformPanel.append(operationFilters,operationHint,operationRows,operationDetail,operationBack,operationQuery);
 let operationRevision=0,operationSnapshot=null,operationMode='list';
 const operationNames={platform_overview:'经营总览',platform_customers:'项目客户',platform_audit:'项目审计'};
 const operationText=v=>v===undefined||v===null?'暂无数据':String(v),operationBool=v=>v===true?'是':v===false?'否':'暂无数据';
 const operationOrderState=value=>({PENDING:'待处理',SUCCESS:'支付成功',FAILED:'支付失败',CANCELLED:'已取消',REFUNDED:'已退款'}[value]||'其他状态');
 const operationProjectRole=value=>({OWNER:'项目所有者',EDITOR:'运营编辑',REVIEWER:'审核人员',VIEWER:'只读成员'}[value]||'角色待确认');
 const operationAuditEvent=value=>({READ:'读取记录',CREATE:'创建记录',UPDATE:'更新记录',DELETE:'删除记录',EMAIL_VERIFIED:'邮箱已验证',MERCHANT_ONBOARDING_REVIEW:'商家入驻审核',COMMUNITY_ORDER_CANCELLED:'社区订单已取消',COMMUNITY_ORDER_RECONCILED:'社区订单已对账',CANCELLED_ORDER_STOCK_RELEASED:'取消订单已释放库存',PROVIDER_BILL_HASH_VERIFIED:'微信账单已核验'}[value]||'业务操作记录');
 const operationFinanceState=value=>({UNCONFIRMED:'未确认',CONFIRMED:'已确认'}[value]||'状态待确认');
 function operationMoney(v,c){return Number.isSafeInteger(v)&&typeof c==='string'&&c?(c==='CNY'?'¥':'')+(v/100).toFixed(2)+(c==='CNY'?'':' '+c):'暂无金额';}
 function operationFields(op,r,detail){if(op==='platform_overview'){const counts=Object.entries(r.order_counts||{}).map(([state,count])=>operationOrderState(state)+'：'+operationText(count)).join('；')||'当前范围无订单';const fields=[['查看数据','经营总览'],['订单状态分布',counts],['准入门店数量',r.admitted_store_count],['已核验支付订单数',r.signed_paid_order_count]];if(detail)fields.push(['支付金额',operationMoney(r.signed_gross_payment_minor,r.currency)],['已退款金额',operationMoney(r.signed_refund_minor,r.currency)],['实收金额',operationMoney(r.signed_net_payment_minor,r.currency)],['待核验订单数',r.unverified_paid_state_count],['财务核销',operationFinanceState(r.finance_status)]);return fields;}
 if(op==='platform_customers'){const fields=[['查看数据','项目客户'],['账户编号',r.user_id],['昵称',r.nickname||'未填写昵称'],['项目角色',operationProjectRole(r.project_role)],['会员关系有效',operationBool(r.membership_active)]];if(detail)fields.push(['账户验证',operationBool(r.verified)],['项目客户编号',r.project_customer_id],['社区归属',r.community_id||'未记录社区归属'],['关联订单数量',r.owned_order_count]);return fields;}
 const fields=[['查看数据','项目审计'],['审计序号',r.id],['业务事件',operationAuditEvent(r.event)],['关联对象',r.object_id]];if(detail)fields.push(['操作账户',r.actor],['发生时间',r.at],['范围说明','仅本项目过滤记录，不代表全局完整链已验证']);return fields;}
 function operationCard(title,fields){const card=document.createElement('article'),h=document.createElement('h3'),dl=document.createElement('dl');card.className='community-record-card';h.textContent=title;card.append(h,dl);for(const [k,v]of fields){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=k;dd.textContent=operationText(v);dl.append(dt,dd);}return card;}
 function syncOperationsTitle(){const active=document.getElementById('platformView').value!=='platform_orders';for(const e of [operationRows,operationHint,operationQuery])e.hidden=!active||operationMode!=='list'&&e===operationRows;operationDetail.hidden=!active||operationMode!=='detail';operationBack.hidden=!active||operationMode==='list';if(active)platformResult.hidden=true;if(activeIndex===panels.indexOf(platformPanel)&&active){platformPanel.querySelector('h2').hidden=true;if(pageTitle)pageTitle.textContent=operationMode==='detail'?'平台运营查询 · 详情':operationMode==='edit'?'平台运营查询 · 查询条件':'平台运营查询';}}
 function clearOperations(){operationRevision++;operationSnapshot=null;operationMode='list';operationRows.replaceChildren();operationDetail.replaceChildren();operationHint.textContent='请选择查询条件。';syncOperationsTitle();}
 function operationsList(){operationRevision++;const revision=operationRevision,s=operationSnapshot;operationMode='list';operationRows.replaceChildren();operationDetail.replaceChildren();if(!s){syncOperationsTitle();return;}const raw=s.operation==='platform_overview'?[s.record]:s.record.records;if(!Array.isArray(raw)){clearOperations();operationHint.textContent='查询失败，请重试。';return;}const keyword=operationKeyword.value.trim().toLowerCase(),records=raw.filter(r=>(!operationType.value||operationType.value==='ALL'||operationType.value===s.operation)&&(!keyword||Object.values(r).map(operationText).join(' ').toLowerCase().includes(keyword)));operationHint.textContent=s.record.coverage_complete===false?'部分商家资料暂不可用；当前仅显示可查看门店。':s.operation==='platform_customers'?'当前项目成员。':s.operation==='platform_audit'?'当前项目操作记录。':'当前可查看门店；支付与财务核销分别记录。';
 for(const r of records){const b=document.createElement('button');b.type='button';b.className='platform-order-button';b.textContent='查看运营记录详情';b.onclick=()=>{if(revision!==operationRevision||!s.current())return;operationMode='detail';operationDetail.replaceChildren(operationCard('记录详情',operationFields(s.operation,r,true)));syncOperationsTitle();};operationRows.append(operationCard('记录列表 · 当前范围',operationFields(s.operation,r,false)),b);}if(!records.length)operationRows.textContent=s.record.has_more?'当前扫描页暂无记录，仍可查询下一页。':'当前查询范围暂无记录。';platformResult.hidden=true;syncOperationsTitle();}
 operationBack.onclick=()=>{if(operationSnapshot?.current())operationsList();else clearOperations();};operationQuery.onclick=()=>{operationMode='edit';orderQuery.open=true;syncOperationsTitle();};
 window.communityPlatformOperationsView=event=>{if(event.type!=='listed'||!operationNames[event.operation]){clearOperations();return;}operationSnapshot=event;operationsList();};
 operationKeyword.addEventListener('input',operationsList);operationType.addEventListener('change',operationsList);
 clearOperations();
 // PLATFORM_OPERATIONS_CARDS_END

 // PLATFORM_MERCHANT_CARDS_BEGIN: original scoped lifecycle, never WeChat signing state.
 const merchantPanel=document.getElementById('platformMerchants').closest('section'),merchantIndex=panels.indexOf(merchantPanel),merchantQuery=document.createElement('details'),merchantSummary=document.createElement('summary');merchantPanel.classList.add('platform-merchant-panel');merchantSummary.textContent='商家查询';merchantQuery.append(merchantSummary,document.getElementById('platformMerchants'));
 const merchantHeader=document.createElement('header');merchantHeader.className='management-page-header';const merchantHeaderCopy=document.createElement('div'),merchantEyebrow=document.createElement('span'),merchantHeading=document.createElement('h3'),merchantDescription=document.createElement('p');merchantEyebrow.className='management-page-eyebrow';merchantEyebrow.textContent='商家管理';merchantHeading.textContent='商家管理';merchantDescription.textContent='管理平台已准入商家的生命周期状态；微信进件、签约、收款与分账状态分别核验。';merchantHeaderCopy.append(merchantEyebrow,merchantHeading,merchantDescription);merchantHeader.append(merchantHeaderCopy);
 const merchantStats=document.createElement('div');merchantStats.className='management-stats';const merchantStatNodes=new Map();for(const [key,label,note]of [['records','准入商家','尚未查询'],['active','正常经营','当前页平台状态'],['restricted','暂停或停用','仅影响新交易']]){const card=document.createElement('article'),caption=document.createElement('span'),value=document.createElement('strong'),small=document.createElement('small');card.className='management-stat';caption.textContent=label;value.textContent='—';small.textContent=note;card.append(caption,value,small);merchantStats.append(card);merchantStatNodes.set(key,{value,note:small});}merchantPanel.append(merchantHeader,merchantStats);
 const merchantRows=document.createElement('div'),merchantDetail=document.createElement('div'),merchantEditor=document.createElement('div'),merchantHint=document.createElement('p'),merchantBack=document.createElement('button'),merchantEdit=document.createElement('button'),merchantRead=document.createElement('button');merchantRows.className='platform-merchant-rows';merchantDetail.className='platform-merchant-detail';merchantEditor.className='platform-merchant-editor';merchantBack.textContent='返回商家列表';merchantEdit.textContent='编辑商家状态';merchantRead.textContent='刷新商家详情';for(const b of [merchantBack,merchantEdit,merchantRead]){b.type='button';b.className='platform-order-button';}
 for(const id of ['platformMerchantWorkspace','platformMerchantVersion','platformMerchantState','platformMerchantReason'])merchantEditor.append(document.getElementById(id).closest('label'));merchantEditor.append(document.getElementById('saveMerchantState'));merchantPanel.append(merchantHint,merchantRows,merchantDetail,merchantEditor,merchantBack,merchantEdit,merchantRead,document.getElementById('moreMerchants'),merchantQuery);
 document.getElementById('merchantRecords').hidden=true;document.getElementById('merchantResult').hidden=true;
 let merchantViewRevision=0,merchantSnapshot=null,merchantItem=null,merchantSavedBase=null,merchantMode='list';
 const merchantState=v=>({ACTIVE:'正常',PAUSED:'暂停新交易',DISABLED:'停用新交易'}[v]||'状态待确认');
 function merchantFields(item,detail){const life=item.lifecycle||{},storeState=({NOT_CREATED:'尚未创建',ACTIVE:'营业中',PAUSED:'已暂停',DISABLED:'已停用'}[item.store_status]||'状态待确认');const fields=[['商家编号',item.workspace],['商家名称',item.name||'未填写'],['经营状态',storeState],['平台状态',merchantState(life.status)],['当前版本',life.version]];if(detail)fields.push(['状态原因',life.reason||'未填写'],['微信进件状态','在商家入驻审核中查询'],['分账状态','在分账配置中查询']);return fields;}
 function syncMerchantTitle(){if(activeIndex!==merchantIndex)return;merchantPanel.querySelector('h2').hidden=true;if(pageTitle)pageTitle.textContent=merchantMode==='detail'?'平台商家管理 · 详情':merchantMode==='edit'?'平台商家管理 · 编辑':'平台商家管理';}
 function clearMerchantView(message){merchantViewRevision++;merchantSnapshot=null;merchantItem=null;merchantSavedBase=null;merchantMode='list';merchantRows.replaceChildren();merchantDetail.replaceChildren();merchantRows.hidden=false;merchantDetail.hidden=true;merchantEditor.hidden=true;merchantBack.hidden=true;merchantEdit.hidden=true;merchantRead.hidden=!document.getElementById('platformMerchantWorkspace').value;merchantHint.textContent=message;for(const node of merchantStatNodes.values())node.value.textContent='—';merchantStatNodes.get('records').note.textContent='尚未查询';syncMerchantTitle();}
 function showMerchantList(){merchantViewRevision++;const revision=merchantViewRevision,s=merchantSnapshot;merchantMode='list';merchantRows.replaceChildren();merchantRows.hidden=false;merchantDetail.hidden=true;merchantEditor.hidden=true;merchantBack.hidden=true;merchantEdit.hidden=true;merchantRead.hidden=true;if(!s){syncMerchantTitle();return;}merchantHint.textContent=s.result.coverage_complete===false?'部分商家资料暂不可用；当前仅显示可查看商家。':'当前商家列表；修改前请刷新详情。';merchantStatNodes.get('records').value.textContent=String(s.result.records.length);merchantStatNodes.get('records').note.textContent='当前页记录';merchantStatNodes.get('active').value.textContent=String(s.result.records.filter(item=>item.lifecycle?.status==='ACTIVE').length);merchantStatNodes.get('restricted').value.textContent=String(s.result.records.filter(item=>['PAUSED','DISABLED'].includes(item.lifecycle?.status)).length);for(const item of s.result.records){const b=document.createElement('button');b.type='button';b.className='platform-order-button';b.textContent='查看商家详情';b.onclick=()=>{if(revision!==merchantViewRevision)return;s.select(item);};merchantRows.append(operationCard('记录列表 · 当前范围',merchantFields(item,false)),b);}if(!s.result.records.length)merchantRows.textContent=s.result.has_more?'当前页无可见商家，仍有下一页。':'当前范围暂无可见商家。';for(const missing of s.result.unavailable_mappings||[]){const note=document.createElement('p');note.textContent=operationText(missing.workspace)+'：商家资料不可用，未读取门店及订单。';merchantRows.append(note);}syncMerchantTitle();}
 function showMerchantDetail(){merchantMode='detail';merchantRows.hidden=true;merchantDetail.replaceChildren(operationCard('记录详情',merchantFields(merchantItem,true)));merchantDetail.hidden=false;merchantEditor.hidden=true;merchantBack.hidden=false;merchantEdit.hidden=false;merchantRead.hidden=false;syncMerchantTitle();}
 merchantBack.onclick=()=>showMerchantList();merchantEdit.onclick=()=>{if(!merchantItem)return;merchantMode='edit';merchantDetail.hidden=true;merchantEditor.hidden=false;merchantEdit.hidden=true;merchantHint.textContent='仅平台管理员可修改；保存后请刷新核对结果。';syncMerchantTitle();};merchantRead.onclick=()=>window.communityReadMerchant();
 window.communityPlatformMerchantView=({type,record})=>{if(type==='reset'||type==='error'){clearMerchantView(record?.message||'查询失败，请重新选择商家。');return;}if(type==='loading'||type==='saving'){merchantViewRevision++;merchantSavedBase=type==='saving'?merchantItem:null;merchantItem=null;merchantMode='list';syncMerchantTitle();merchantDetail.replaceChildren();merchantDetail.hidden=true;merchantEditor.hidden=true;merchantBack.hidden=true;merchantEdit.hidden=true;merchantRead.hidden=true;merchantHint.textContent=type==='saving'?'正在保存商家状态…':'正在查询商家资料…';return;}if(type==='temporary'){merchantHint.textContent='暂时无法读取，请稍后重试。';return;}if(type==='listed'){merchantSnapshot=record;showMerchantList();return;}if(type==='detail'){merchantViewRevision++;merchantItem=record.item;showMerchantDetail();return;}if(type==='saved'){merchantViewRevision++;merchantItem={...(merchantSavedBase||{}),workspace:record.workspace,lifecycle:record.lifecycle};showMerchantDetail();merchantHint.textContent='商家状态已保存，请刷新核对结果。';}};
 clearMerchantView('请选择查询条件。');
 // PLATFORM_MERCHANT_CARDS_END

 // PLATFORM_BRAND_SCOPE_BEGIN: presentation only, no role or permission selection.
 const platformBrand=document.querySelector('.admin-brand'),platformBrandText=platformBrand?.querySelector('strong');
 const platformBrandOriginal=platformBrandText?.textContent,platformBrandSubtitle=platformBrand?.querySelector('.admin-brand-role'),platformBrandSubtitleOriginal=platformBrandSubtitle?.textContent;
 function syncPlatformBrand(index){const selected=[reviewIndex,panels.indexOf(platformPanel),merchantIndex,receiverIndex].includes(index);if(platformBrandText)platformBrandText.textContent=platformBrandOriginal;if(platformBrandSubtitle)platformBrandSubtitle.textContent=selected?'平台管理者后台':platformBrandSubtitleOriginal;}
 // PLATFORM_BRAND_SCOPE_END

 // CUSTOMER_PROFILE_CARDS_BEGIN: original current-user profile and referral actions only.
 const customerForm=document.getElementById('customerProfile'),customerPanel=customerForm.closest('section'),customerIndex=panels.indexOf(customerPanel);customerPanel.classList.add('customer-profile-panel');
 const customerRows=document.createElement('div'),customerDetail=document.createElement('div'),customerHint=document.createElement('p'),customerBack=document.createElement('button'),customerEdit=document.createElement('button'),customerControls=document.createElement('details'),customerSummary=document.createElement('summary'),customerReferral=document.createElement('div');
 customerRows.className='customer-profile-rows';customerDetail.className='customer-profile-detail';customerReferral.className='customer-referral-result';customerBack.textContent='返回个人资料列表';customerEdit.textContent='编辑个人资料';customerControls.className='customer-retained-controls';customerSummary.textContent='推荐关系与通知';customerControls.append(customerSummary);for(const id of ['referralCode','referralInput','bindReferrer','notices']){const e=document.getElementById(id);customerControls.append(id==='referralInput'?e.closest('label'):e);}customerControls.append(customerReferral);for(const b of [customerBack,customerEdit]){b.type='button';b.className='customer-profile-button';}customerPanel.append(customerHint,customerRows,customerDetail,customerBack,customerEdit,customerForm,customerControls);document.getElementById('customerResult').hidden=true;
 let customerSnapshot=null,customerMode='list',customerViewRevision=0;
 function syncCustomerTitle(){if(activeIndex!==customerIndex)return;customerPanel.querySelector('h2').hidden=true;if(pageTitle)pageTitle.textContent=customerMode==='detail'?'个人资料与推荐关系 · 详情':customerMode==='edit'?'个人资料与推荐关系 · 编辑':'个人资料与推荐关系';}
 function customerCard(record,title){const article=document.createElement('article'),h=document.createElement('h3'),dl=document.createElement('dl');article.className='community-record-card';h.textContent=title;article.append(h,dl);for(const [label,key]of [['昵称','nickname'],['联系方式','contact']]){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=record[key]||'未填写';dl.append(dt,dd);}return article;}
 function showCustomerDetail(){if(!customerSnapshot)return;customerMode='detail';customerRows.hidden=true;customerDetail.replaceChildren(customerCard(customerSnapshot,'记录详情'));const scope=document.createElement('details'),summary=document.createElement('summary'),dl=document.createElement('dl');summary.textContent='账户与推荐关系';scope.append(summary,dl);for(const [label,key]of [['账户编号','user_id'],['项目编号','tenant_id'],['客户编号','project_customer_id'],['资料版本','version'],['推荐人账户','referrer_user_id']]){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=customerSnapshot[key]===null&&key==='referrer_user_id'?'暂无推荐人':customerSnapshot[key]===undefined?'暂无数据':String(customerSnapshot[key]);dl.append(dt,dd);}customerDetail.append(scope);customerDetail.hidden=false;customerBack.hidden=false;customerEdit.hidden=false;customerForm.hidden=true;syncCustomerTitle();}
 function showCustomerList(){const revision=++customerViewRevision;customerMode='list';customerRows.replaceChildren();customerRows.hidden=false;customerDetail.replaceChildren();customerDetail.hidden=true;customerBack.hidden=true;customerEdit.hidden=true;customerForm.hidden=true;if(customerSnapshot){const open=document.createElement('button');open.type='button';open.textContent='查看个人资料详情';open.className='customer-profile-button';open.onclick=()=>{if(revision===customerViewRevision)showCustomerDetail();};customerRows.append(customerCard(customerSnapshot,'记录列表 · 当前范围'),open);}syncCustomerTitle();}
 customerBack.onclick=()=>showCustomerList();customerEdit.onclick=()=>{if(!customerSnapshot)return;customerMode='edit';customerRows.hidden=true;customerDetail.hidden=true;customerForm.hidden=false;customerEdit.hidden=true;customerBack.hidden=false;syncCustomerTitle();};
 window.communityCustomerView=({type,record})=>{if(type==='notices'){if(result)result.hidden=false;return;}if(activeIndex===customerIndex&&result)result.hidden=true;customerViewRevision++;customerReferral.replaceChildren();if(type==='listed'||type==='saved'){customerSnapshot=record;showCustomerList();customerHint.textContent=type==='saved'?'个人资料已保存。':'已读取个人资料。';if(type==='saved')showCustomerDetail();return;}customerSnapshot=null;showCustomerList();customerHint.textContent=({reset:'请读取我的资料。',loading:'正在处理个人资料…',error:'操作失败，请重新读取。',unknown:'操作结果未确认，请刷新资料。',code:'已生成推荐码。',bound:'推荐关系已保存。'}[type]||'操作未完成');if(type==='code'||type==='bound'){const dt=document.createElement('p');dt.textContent=type==='code'?'我的推荐码：'+String(record.code):'推荐人账户：'+String(record.referrer_user_id);customerReferral.append(dt);customerControls.open=true;}};
 window.communityCustomerView({type:'reset'});
 // CUSTOMER_PROFILE_CARDS_END

 const navigationHashTargets=new Map([['#customer-profile',customerIndex],['#community-profile',profileIndex],['#community-opening',openIndex],['#community-promotion',promotionIndex],['#merchant-members',memberIndex],['#orders-settlement',reportIndex],['#platform-review',reviewIndex],['#platform-operations',panels.indexOf(platformPanel)],['#merchant-management',merchantIndex],['#admin-settings',authorityIndex],['#split-configuration',receiverIndex]]);
 const navigationHashesByIndex=new Map([...navigationHashTargets].map(([hash,index])=>[index,hash.slice(1)]));

 function select(index,persist=true){
  if(index!==activeIndex&&typeof window.communitySectionChanged==='function')window.communitySectionChanged();
  if(index!==openIndex){openMembers=false;clearOpen('输入社区编号，查询您有权查看的社区资料。');}
  if(activeIndex===profileIndex&&index!==profileIndex)emptyProfile('切换功能后请重新查询社区资料。');
  if(index!==reportIndex)snapshotMode='overview';if(index!==receiverIndex)receiverActions.open=false;activeIndex=index;syncPlatformBrand(index);
  main.classList.toggle('receiver-selected',index===receiverIndex);if(index===receiverIndex)document.getElementById('receiverCommunityReference').value=document.getElementById('reference').value;
  if(pageTitle)pageTitle.hidden=false;
  if(pageTitle)pageTitle.textContent=index===null?'社区运营工作台':panels[index].querySelector('h2').textContent;
  syncOrderPageTitle();syncOperationsTitle();syncReviewTitle();syncMerchantTitle();syncCustomerTitle();syncSnapshotTitle();syncReceiverTitle();
  const compactFinance=index===receiverIndex||index===panels.indexOf(platformPanel);main.classList.toggle('compact-finance-selected',compactFinance);if(pageTitle)main.insertBefore(back,pageTitle);else main.insertBefore(back,home);
  main.classList.toggle('profile-selected',index===profileIndex);
  main.classList.toggle('members-selected',index===memberIndex);if(index===memberIndex)document.getElementById('memberCommunityReference').value=document.getElementById('reference').value;
  main.classList.toggle('promotion-selected',index===promotionIndex);if(index===promotionIndex)promotionReference.value=document.getElementById('reference').value;
  main.classList.toggle('open-selected',index===openIndex);main.classList.toggle('report-selected',index===reportIndex);if(index===reportIndex)reportReference.value=document.getElementById('reference').value;
  // Move, never clone, the original query result so list/detail uses the same cursor and handlers.
  if(index===profileIndex)profilePanel.insertBefore(result,profileQuery);else if(index===openIndex)openPanel.append(result);else if(index===reportIndex)reportPanel.append(result);else if(index===promotionIndex)promotionPanel.append(result);else if(index===memberIndex)memberPanel.append(result);else if(index===reviewIndex)reviewPanel.append(result);else if(result)main.append(result);
  home.hidden=index!==null;back.hidden=index===null;
  panels.forEach((panel,i)=>{panel.hidden=i!==index;});
  // Preserve the original result DOM and business handlers without cloning or rebinding.
  if(result)result.hidden=index===customerIndex||index===merchantIndex||index===panels.indexOf(platformPanel)||index===reviewIndex||index===receiverIndex||index===merchantReviewIndex||index===merchantWorkbenchIndex||index===null||(index===profileIndex&&!detail.hidden)||(index===openIndex&&!openMembers);
  buttons.forEach((button,i)=>{if(i===index)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});
  for(const button of workspaceRouteNavigation.values())button.removeAttribute('aria-current');
  if(index===null)homeButton.setAttribute('aria-current','page');else homeButton.removeAttribute('aria-current');
  const selectedNavigation=index===null?homeButton:buttons[index],selectedGroup=selectedNavigation?.closest?.('details');if(selectedGroup)selectedGroup.open=true;
  snapshotNav.removeAttribute('aria-current');refundNav.removeAttribute('aria-current');
  if(persist){if(index===null)setWorkspaceRoute('');else if(navigationHashesByIndex.has(index))setWorkspaceRoute(navigationHashesByIndex.get(index));}
  if(navigationDisclosure&&window.matchMedia('(max-width:900px)').matches)navigationDisclosure.open=false;
  if(index===null&&typeof syncHomeTitle==='function')syncHomeTitle();
  if(index!==null){const title=panels[index].querySelector('h2');title.tabIndex=-1;title.focus();}
 }
 const navigationGroups=new Map();
 function navigationGroup(key,title){
 if(navigationGroups.has(key))return navigationGroups.get(key);
  const group=document.createElement('details'),heading=document.createElement('summary'),items=document.createElement('div');
  group.className='admin-nav-group';group.dataset.group=key;group.open=key==='core'||key==='community'||key==='trade';heading.textContent=title;items.className='admin-nav-items';group.append(heading,items);nav.append(group);navigationGroups.set(key,{group,items});return navigationGroups.get(key);
 }
 function disabledNavigationGroup(title){const group=document.createElement('details'),heading=document.createElement('summary');group.className='admin-nav-group admin-nav-disabled';heading.textContent=title;heading.setAttribute('aria-disabled','true');heading.addEventListener('click',event=>event.preventDefault());group.append(heading);nav.append(group);return group;}
 const coreNavigation=navigationGroup('core','总览');
 const communityNavigation=navigationGroup('community','社区经营');
 const merchantNavigation=navigationGroup('merchant','商家管理');
 const mallNavigation=navigationGroup('mall','积分商城');
 const tradeNavigation=navigationGroup('trade','交易与分账');
 const marketingNavigation=navigationGroup('marketing','营销管理');
 const platformNavigation=navigationGroup('platform','平台管理');
 const systemNavigation=navigationGroup('system','系统设置');
 const homeButton=document.createElement('button');homeButton.type='button';homeButton.textContent='首页';homeButton.addEventListener('click',()=>select(null));coreNavigation.items.append(homeButton);
 const compactNavigation={
  '个人资料与推荐关系':'个人资料','社区资料':'社区资料','打开社区':'社区开通','平台审核':'社区审核',
  '社区订单、收益与结算观察':'订单与结算','平台运营查询':'运营查询','平台商家管理':'商家管理',
  '社区推广':'社区推广','社区商家成员':'社区商家','平台配置社区分账接收关系':'分账配置',
  '管理员设置':'管理员设置'
 };
 const navigationGroupFor=title=>title==='个人资料与推荐关系'||title==='社区资料'||title==='打开社区'||title==='平台审核'?communityNavigation:
  title==='社区商家成员'||title==='平台商家管理'?merchantNavigation:
  title==='社区订单、收益与结算观察'?tradeNavigation:title==='社区推广'?communityNavigation:
  title==='管理员设置'||title==='平台配置社区分账接收关系'?systemNavigation:platformNavigation;
 panels.forEach((panel,index)=>{
  const title=panel.querySelector('h2').textContent;
  const button=document.createElement('button');button.type='button';button.textContent=compactNavigation[title]||title;button.addEventListener('click',()=>select(index));navigationGroupFor(title).items.append(button);buttons.push(button);

 });
 const merchantReviewPanel=document.createElement('section'),merchantReviewPanelHeading=document.createElement('h2'),merchantReviewFrame=document.createElement('iframe');
 merchantReviewPanel.className='embedded-workspace-panel';merchantReviewPanel.hidden=true;merchantReviewPanelHeading.textContent='商家审核';merchantReviewPanelHeading.className='visually-hidden';merchantReviewFrame.title='商家入驻审核';merchantReviewFrame.loading='lazy';merchantReviewPanel.append(merchantReviewPanelHeading);main.append(merchantReviewPanel);panels.push(merchantReviewPanel);const merchantReviewIndex=panels.indexOf(merchantReviewPanel);
 const merchantWorkbenchPanel=document.createElement('section'),merchantWorkbenchHeading=document.createElement('h2'),merchantWorkbenchFrame=document.createElement('iframe');
 merchantWorkbenchPanel.className='embedded-workspace-panel';merchantWorkbenchPanel.hidden=true;merchantWorkbenchHeading.textContent='商家业务';merchantWorkbenchHeading.className='visually-hidden';merchantWorkbenchFrame.title='商家业务管理';merchantWorkbenchFrame.loading='lazy';merchantWorkbenchPanel.append(merchantWorkbenchHeading,merchantWorkbenchFrame);main.append(merchantWorkbenchPanel);panels.push(merchantWorkbenchPanel);const merchantWorkbenchIndex=panels.indexOf(merchantWorkbenchPanel);
 function setWorkspaceRoute(value){const next=location.pathname+location.search+(value?'#'+value:'');if(location.pathname+location.search+location.hash!==next)history.replaceState(null,'',next);}
 function markWorkspaceNavigation(target){const button=workspaceRouteNavigation.get(target);if(!button)return;button.setAttribute('aria-current','page');const group=button.closest?.('details');if(group)group.open=true;}
 function openMerchantReview(){if(!merchantReviewAllowed())return;if(!merchantReviewFrame.isConnected)merchantReviewPanel.append(merchantReviewFrame);if(merchantReviewFrame.getAttribute('src')!=='/community-preview/merchant/review?embedded=1')merchantReviewFrame.src='/community-preview/merchant/review?embedded=1';select(merchantReviewIndex);markWorkspaceNavigation('merchant-review');setWorkspaceRoute('merchant-review');if(pageTitle){pageTitle.hidden=false;pageTitle.textContent='商家审核';}}
 function openMerchantWorkbench(target,title){merchantWorkbenchFrame.src='/community-preview/merchant/workbench?embedded=1#'+target;select(merchantWorkbenchIndex);markWorkspaceNavigation('merchant-workbench='+target);setWorkspaceRoute('merchant-workbench='+encodeURIComponent(target));if(pageTitle){pageTitle.hidden=false;pageTitle.textContent=title;}}
 function applyWorkspaceRoute(){
  if(location.hash==='#merchant-review'){openMerchantReview();return;}
  if(location.hash==='#split-details'){snapshotNav.click();return;}
  if(location.hash==='#refund-management'){refundNav.click();return;}
  const prefix='#merchant-workbench=';if(!location.hash.startsWith(prefix))return;
  const target=decodeURIComponent(location.hash.slice(prefix.length))||'workbenchMain',labels={workbenchMain:'首页','store-profile':'门店资料','catalog-management':'商品管理','price-stock':'价格与库存','mall-orders':'订单查询','merchant-points':'商家积分','orders-section':'订单与结算','split-records':'分账明细',orderDetails:'退款管理',advertising:'广告管理','split-settings':'分账配置',reconciliation:'对账管理'};
  openMerchantWorkbench(target,labels[target]||'商家业务');
 }
 window.addEventListener('hashchange',applyWorkspaceRoute);queueMicrotask(applyWorkspaceRoute);
 const snapshotNav=document.createElement('button');snapshotNav.type='button';snapshotNav.textContent='分账明细';snapshotNav.addEventListener('click',()=>{const changed=activeIndex===reportIndex&&snapshotKind!=='split';select(reportIndex);if(changed&&typeof window.communitySectionChanged==='function')window.communitySectionChanged();snapshotKind='split';if(reportRecord?.operation!=='community_earnings')clearReport('请选择社区并查询分账明细。');snapshotList();buttons[reportIndex].removeAttribute('aria-current');snapshotNav.setAttribute('aria-current','page');refundNav.removeAttribute('aria-current');const group=snapshotNav.closest?.('details');if(group)group.open=true;setWorkspaceRoute('split-details');});tradeNavigation.items.append(snapshotNav);
 const refundNav=document.createElement('button');refundNav.type='button';refundNav.textContent='退款管理';refundNav.addEventListener('click',()=>{const changed=activeIndex===reportIndex&&snapshotKind!=='refund';select(reportIndex);if(changed&&typeof window.communitySectionChanged==='function')window.communitySectionChanged();snapshotKind='refund';if(reportRecord?.operation!=='community_refunds')clearReport('请选择社区并查询退款记录。');snapshotList();buttons[reportIndex].removeAttribute('aria-current');refundNav.setAttribute('aria-current','page');snapshotNav.removeAttribute('aria-current');const group=refundNav.closest?.('details');if(group)group.open=true;setWorkspaceRoute('refund-management');});tradeNavigation.items.append(refundNav);
 const adNav=document.createElement('button');adNav.type='button';adNav.className='admin-nav-link';adNav.textContent='广告管理';adNav.addEventListener('click',()=>openMerchantWorkbench('advertising','广告管理'));marketingNavigation.items.append(adNav);
 const mallLinks=[['商品管理','catalog-management'],['价格与库存','price-stock'],['订单查询','mall-orders'],['商家积分','merchant-points']].map(([label,target])=>{const link=document.createElement('button');link.type='button';link.className='admin-nav-link';link.textContent=label;link.addEventListener('click',()=>openMerchantWorkbench(target,label));mallNavigation.items.append(link);return link;});
 const splitSettingsNav=document.createElement('button');splitSettingsNav.type='button';splitSettingsNav.className='admin-nav-link';splitSettingsNav.textContent='分账配置';splitSettingsNav.addEventListener('click',()=>openMerchantWorkbench('split-settings','分账配置'));systemNavigation.items.append(splitSettingsNav);
 const merchantReviewNav=document.createElement('button');merchantReviewNav.type='button';merchantReviewNav.className='admin-nav-link';merchantReviewNav.textContent='商家审核';merchantReviewNav.addEventListener('click',openMerchantReview);merchantNavigation.items.prepend(buttons[merchantIndex],merchantReviewNav,buttons[memberIndex]);
 workspaceRouteNavigation.set('merchant-review',merchantReviewNav);workspaceRouteNavigation.set('merchant-workbench=advertising',adNav);workspaceRouteNavigation.set('merchant-workbench=split-settings',splitSettingsNav);
 for(const [index,target]of ['catalog-management','price-stock','mall-orders','merchant-points'].entries())workspaceRouteNavigation.set('merchant-workbench='+target,mallLinks[index]);
 const refreshNavigationGroups=()=>{for(const {group,items}of navigationGroups.values())group.hidden=!Array.from(items.children).some(item=>!item.hidden);};
 // ROLE_HOME_BEGIN: trusted session projection only; navigation never grants authority.
 const homeHero=document.createElement('header'),homeEyebrow=document.createElement('p'),homeHeroTitle=document.createElement('h2'),homeHeroActions=document.createElement('div');
 homeHero.className='admin-home-hero';homeEyebrow.className='admin-home-eyebrow';homeHeroActions.className='admin-home-hero-actions';homeHero.append(homeEyebrow,homeHeroTitle,intro,homeHeroActions);home.insertBefore(homeHero,cards);
 let homeContext=null,homeRevision=0,homeMetricNodes=new Map(),homeTrendNodes=[];
 function merchantReviewAllowed(){return !!homeContext?.reviewer;}
 const platformHome=()=>!!homeContext&&['PLATFORM_OWNER','PLATFORM_REVIEWER'].includes(homeContext.role);
 const platformOwnerHome=()=>!!homeContext&&homeContext.role==='PLATFORM_OWNER';
 const platformReviewerHome=()=>!!homeContext&&homeContext.role==='PLATFORM_REVIEWER';
 const communityHome=()=>!!homeContext&&['CUSTOMER','COMMUNITY_ADMIN','MERCHANT_ADMIN'].includes(homeContext.role);
 const communityManagerHome=()=>!!homeContext&&['COMMUNITY_ADMIN','MERCHANT_ADMIN'].includes(homeContext.role);
 const customerHome=()=>!!homeContext&&homeContext.role==='CUSTOMER';
 const authorityHome=()=>!!homeContext&&!!homeContext.admin;
 const rootAuthority=()=>authorityHome()&&homeContext.admin.kind==='ROOT';
 const directoryCapability=operation=>!homeContext?.admin||homeContext.admin.capabilities.includes('/community/directory#'+operation);
 function syncRoleNavigation(){
  const allowed=new Set();
  if(customerHome()){allowed.add(customerIndex);allowed.add(openIndex);}
  if(communityManagerHome())for(const index of [customerIndex,profileIndex,openIndex,reportIndex,promotionIndex,memberIndex])allowed.add(index);
  if(platformReviewerHome())allowed.add(reviewIndex);
  if(platformOwnerHome())for(const index of [panels.indexOf(platformPanel),merchantIndex])allowed.add(index);
  if(authorityHome())allowed.add(authorityIndex);
  if(rootAuthority())for(const index of [profileIndex,openIndex,reportIndex,panels.indexOf(platformPanel),merchantIndex,promotionIndex,memberIndex])allowed.add(index);
  const operations=new Map([[profileIndex,['mine','status','register','update','submit']],[openIndex,['status','join','leave','members']],[reportIndex,['community_orders','community_earnings','community_refunds']],[promotionIndex,['promotions','promotion_create','promotion_state']],[memberIndex,['members']],[reviewIndex,['list','status','review']],[panels.indexOf(platformPanel),['platform_overview','platform_orders','platform_customers','platform_audit']],[merchantIndex,['platform_merchants','platform_merchant_state']],[receiverIndex,['community_receiver_list','community_receiver_read','community_receiver_bind']]]);
  for(const [index,required]of operations)if(!rootAuthority()&&allowed.has(index)&&!required.some(directoryCapability))allowed.delete(index);
  buttons.forEach((button,index)=>{button.hidden=index===receiverIndex||!allowed.has(index);});
  snapshotNav.hidden=refundNav.hidden=!(rootAuthority()||(communityManagerHome()&&['community_earnings','community_refunds'].some(directoryCapability)));
  adNav.hidden=!(rootAuthority()||communityManagerHome()||platformOwnerHome());
  mallLinks.forEach(link=>{link.hidden=!(rootAuthority()||communityManagerHome()||platformOwnerHome());});
  splitSettingsNav.hidden=!(rootAuthority()||communityManagerHome()||platformOwnerHome());
  merchantReviewNav.hidden=!merchantReviewAllowed();
  if(!merchantReviewAllowed()&&typeof merchantReviewFrame!=='undefined'&&merchantReviewFrame.isConnected){merchantReviewFrame.removeAttribute('src');merchantReviewFrame.remove();if(activeIndex===merchantReviewIndex)select(null);}
  refreshNavigationGroups();
 }
 function syncHomeTitle(){if(activeIndex!==null)return;heading.textContent='首页';heading.hidden=!!pageTitle;homeHeroTitle.textContent='';homeHeroTitle.hidden=true;if(pageTitle){pageTitle.textContent='首页';pageTitle.hidden=false;}if(platformBrandText)platformBrandText.textContent=platformBrandOriginal;if(platformBrandSubtitle)platformBrandSubtitle.textContent=platformHome()?'平台管理者后台':communityHome()?'社区管理者后台':platformBrandSubtitleOriginal;}
 function openPlatformHomeView(operation){select(panels.indexOf(platformPanel));const field=document.getElementById('platformView');field.value=operation;field.onchange();syncOrderPageTitle();syncOperationsTitle();orderQuery.open=true;document.getElementById('readPlatformView').click();}
 function renderHome(){
  const revision=++homeRevision;homeMetricNodes=new Map();homeTrendNodes=[];cards.replaceChildren();cards.className='admin-home-groups';homeHeroActions.replaceChildren();homeEyebrow.textContent=platformHome()?'平台首页':communityHome()?'社区首页':'账户首页';
  intro.textContent='';
  const click=id=>()=>document.getElementById(id).click();
  const panel=index=>()=>select(index);
  const finance=[()=>openMerchantWorkbench('split-records','分账明细'),'查看当前商家分账记录。'];
  function group(title,items){const block=document.createElement('div'),label=document.createElement('h3'),grid=document.createElement('div');block.className='admin-home-group';label.textContent=title;const count=document.createElement('span');count.className='admin-group-count';count.textContent=items.length+' 项';label.append(count);grid.className='admin-cards';block.append(label,grid);cards.append(block);for(const [name,description,action]of items){const card=document.createElement(typeof action==='string'?'a':'button');card.className='admin-card';if(typeof action==='string')card.href=action;else card.type='button';const strong=document.createElement('strong'),desc=document.createElement('span');strong.textContent=name;desc.textContent=description;card.append(strong,desc);if(communityHome()&&title==='社区运营快捷入口'){const actionLabel=document.createElement('span');actionLabel.className='admin-card-action';actionLabel.textContent=({社区商家:'查看社区关联商家',社区订单:'查看社区订单',分账明细:'查看分账明细',退款观察:'查看退款记录'})[name];card.append(actionLabel);}card.addEventListener('click',event=>{if(revision!==homeRevision){event.preventDefault();return;}if(typeof action==='function')action();});grid.append(card);}}
  function metrics(title,items){const block=document.createElement('div'),heading=document.createElement('h3'),grid=document.createElement('div'),refresh=document.createElement('button'),icons={orders:'▤',stores:'⌂',gross:'¥',unverified:'!',returns:'↩',net:'¥',pending_merchants:'✓',daily_transaction_amount:'¥',daily_transaction_count:'↗',daily_split:'⇄',daily_split_count:'≡',daily_refund:'↩',daily_refund_count:'↩',ad_overview:'◉'};block.className='admin-home-group admin-metric-group'+(title==='今日经营数据'?' admin-daily-metrics':'');heading.textContent=title;refresh.type='button';refresh.className='admin-metric-refresh';refresh.textContent='刷新数据';refresh.onclick=()=>{window.communityLoadHomeMetrics?.();window.communityLoadAdminHomeMetrics?.();};heading.append(refresh);grid.className='admin-metrics';for(const [key,label,action]of items){const card=document.createElement(typeof action==='string'?'a':typeof action==='function'?'button':'article'),name=document.createElement('span'),value=document.createElement('strong'),note=document.createElement('small'),icon=document.createElement('i');card.className='admin-metric-card metric-'+key;if(typeof action==='string')card.href=action;else if(typeof action==='function')card.type='button';name.textContent=label;value.textContent='—';note.textContent=action?'点击进入处理':'尚未读取';icon.className='admin-metric-icon';icon.textContent=icons[key]||'·';icon.setAttribute('aria-hidden','true');card.append(name,value,note,icon);card.addEventListener('click',event=>{if(revision!==homeRevision){event.preventDefault();return;}if(typeof action==='function')action();});grid.append(card);homeMetricNodes.set(key,{value,note});}block.append(heading,grid);cards.append(block);}
  function trends(){const block=document.createElement('div'),heading=document.createElement('h3'),grid=document.createElement('div');block.className='admin-home-group admin-analysis-group';heading.textContent='近 7 日趋势分析';grid.className='admin-trend-grid';const add=(title,definitions,unit)=>{const chart=document.createElement('article'),head=document.createElement('header'),name=document.createElement('strong'),legend=document.createElement('div'),plot=document.createElement('div'),empty=document.createElement('p');chart.className='admin-trend-card';name.textContent=title;legend.className='admin-trend-legend';for(const [,label,color]of definitions){const item=document.createElement('span'),dot=document.createElement('i');dot.style.background=color;item.append(dot,label);legend.append(item);}head.append(name,legend);plot.className='admin-trend-plot';empty.className='admin-trend-empty';empty.textContent='近 7 日暂无记录';chart.append(head,plot,empty);grid.append(chart);homeTrendNodes.push({plot,empty,definitions,unit});};add('交易与分账',[[ 'transaction_amount_minor','交易额','#1683e8'],['completed_split_minor','分账额','#2fb344'],['confirmed_refund_minor','退款额','#f59f00']],'money');add('广告表现',[[ 'ad_impression_count','浏览量','#7950f2'],['ad_click_count','点击量','#20c997']],'count');block.append(heading,grid);cards.append(block);}
  if(platformHome())metrics('经营概览',[['orders','订单数量'],['stores','已准入商家'],['gross','已核实交易额'],['unverified','待核实支付状态']]);
  else if(communityManagerHome())metrics('经营概览',[['orders','归属订单'],['gross','已核实分账'],['returns','退款与回退'],['net','当前页净额']]);
  if(authorityHome()&&homeContext.admin.kind==='ROOT')metrics('今日经营数据',[['pending_merchants','待审核商家数',merchantReviewAllowed()?openMerchantReview:null],['daily_transaction_amount','今日交易金额'],['daily_transaction_count','今日交易笔数'],['daily_split','今日分账金额'],['daily_split_count','今日分账笔数'],['daily_refund','今日退款金额'],['daily_refund_count','今日退款笔数'],['ad_overview','今日广告数据',()=>openMerchantWorkbench('advertising','广告管理')]]);
  if(authorityHome()&&homeContext.admin.kind==='ROOT')trends();
  if(communityManagerHome()){
   group('社区运营快捷入口',[
   ['社区商家','查询当前社区的关联商家与已有资料，不是管理员或员工账号。',()=>{select(memberIndex);document.getElementById('queryMerchantMembers').click();}],
   ['社区订单','查看当前社区订单。',()=>{select(reportIndex);document.getElementById('communityOrders').click();}],
   ['分账明细','查看当前社区分账及退款记录。',()=>{snapshotNav.click();document.getElementById('communityEarnings').click();}],
    ['退款记录','逐订单查看退款记录。',()=>{refundNav.click();window.communityReadRefunds();}]
   ]);
   group('经营配置',[
    ['分账配置','查看和维护分账规则。',()=>openMerchantWorkbench('split-settings','分账配置')],
    ['广告管理','管理付款确认页和支付成功页的广告。',()=>openMerchantWorkbench('advertising','广告管理')],
    ['推广管理','管理社区推广入口和有效状态。',panel(promotionIndex)],
    ['社区资料','维护当前社区资料与展示状态。',panel(profileIndex)]
   ]);
   group('更多社区功能',[
    ['个人资料与推荐关系','查看与编辑个人资料和推荐关系。',panel(customerIndex)],
    ['社区资料','查询、查看和编辑社区资料。',panel(profileIndex)],
    ['打开社区','管理社区加入、退出和成员。',panel(openIndex)],
    ['社区订单、收益与结算观察','查看社区订单、收益和结算。',panel(reportIndex)],
    ['社区推广','管理社区推广入口和参与成员。',panel(promotionIndex)]
   ]);
  }else if(customerHome()){
   group('当前账户功能',[
    ['个人资料与推荐关系','查看与编辑个人资料和推荐关系。',panel(customerIndex)],
    ['打开社区','管理社区加入和退出。',panel(openIndex)]
   ]);
  }else if(platformReviewerHome()){
   group('审核工作',[
    ['商家入驻审核','查看并处理商家入驻申请。',openMerchantReview]
   ]);
  }else if(platformOwnerHome()){
   const orders=document.createElement('button'),admission=document.createElement('button');orders.type='button';orders.textContent='进入订单管理';orders.addEventListener('click',()=>{if(revision===homeRevision)openPlatformHomeView('platform_orders');});homeHeroActions.append(orders);if(merchantReviewAllowed()){admission.type='button';admission.textContent='入驻审核';admission.addEventListener('click',()=>{if(revision===homeRevision)openMerchantReview();});homeHeroActions.append(admission);}
   group('订单与交易',[
    ['订单管理','查询订单和支付状态。',()=>openPlatformHomeView('platform_orders')],
    ['支付管理','查看订单支付记录。',()=>openPlatformHomeView('platform_orders')],
    ['退款管理',finance[1],()=>openMerchantWorkbench('orderDetails','退款管理')],['分账明细',finance[1],finance[0]],['对账管理',finance[1],()=>openMerchantWorkbench('reconciliation','对账管理')]
   ]);
   group('入驻与商家',[
    ...(merchantReviewAllowed()?[['商家入驻审核','查看并处理商家入驻申请。',openMerchantReview]]:[]),
    ['平台商家管理','管理已准入商家的经营状态。',panel(merchantIndex)]
   ]);
   group('用户与社区',[
   ['用户管理','查询当前项目客户。',()=>openPlatformHomeView('platform_customers')],
    ['平台运营查询','查看经营总览、客户和操作记录。',()=>openPlatformHomeView('platform_overview')],
    ['广告审核与投放','审核自有广告并管理付款前、付款完成广告位。',()=>openMerchantWorkbench('advertising','广告管理')]
   ]);
   group('账号与日志',[
    ['角色设置','查看角色设置与操作记录。',()=>openPlatformHomeView('platform_audit')],
    ['通知与日志','查看当前项目操作记录。',()=>openPlatformHomeView('platform_audit')]
   ]);
  }
  syncRoleNavigation();
  syncHomeTitle();
  if((platformHome()||communityManagerHome())&&typeof window.communityLoadHomeMetrics==='function')queueMicrotask(()=>{if(revision===homeRevision)window.communityLoadHomeMetrics();});
  if(authorityHome()&&homeContext.admin.kind==='ROOT'&&typeof window.communityLoadAdminHomeMetrics==='function')queueMicrotask(()=>{if(revision===homeRevision)window.communityLoadAdminHomeMetrics();});
 }
 function renderHomeTrends(series){if(!Array.isArray(series)||series.length!==7)return;for(const chart of homeTrendNodes){const values=series.flatMap(day=>chart.definitions.map(([key])=>Number.isSafeInteger(day?.[key])&&day[key]>=0?day[key]:0)),maximum=Math.max(1,...values);chart.plot.replaceChildren();series.forEach(day=>{const column=document.createElement('div'),bars=document.createElement('div'),label=document.createElement('span');column.className='admin-trend-column';bars.className='admin-trend-bars';chart.definitions.forEach(([key,name,color])=>{const raw=Number.isSafeInteger(day?.[key])&&day[key]>=0?day[key]:0,bar=document.createElement('i');bar.style.background=color;bar.style.height=(raw?Math.max(6,Math.round(raw/maximum*100)):2)+'%';bar.title=name+'：'+(chart.unit==='money'?'¥'+(raw/100).toFixed(2):raw);bars.append(bar);});const date=new Date((day.day_start+8*3600)*1000);label.textContent=(date.getUTCMonth()+1)+'/'+date.getUTCDate();column.append(bars,label);chart.plot.append(column);});chart.empty.hidden=values.some(value=>value>0);}}
 window.communityHomeMetrics=record=>{if(!record||typeof record!=='object')return;const money=(value,currency)=>Number.isSafeInteger(value)?'¥'+(value/100).toFixed(2)+(currency?' '+currency:''):'—';const set=(key,value,note='最新数据')=>{const node=homeMetricNodes.get(key);if(!node)return;node.value.textContent=String(value);node.note.textContent=note;};if(record.kind==='platform'){const counts=record.order_counts||{};set('orders',Object.values(counts).reduce((sum,value)=>sum+(Number.isSafeInteger(value)?value:0),0));set('stores',Number.isSafeInteger(record.admitted_store_count)?record.admitted_store_count:'—');set('gross',money(record.signed_gross_payment_minor,record.currency),record.finance_status==='UNCONFIRMED'?'财务核销未确认':'最新数据');set('unverified',Number.isSafeInteger(record.unverified_paid_state_count)?record.unverified_paid_state_count:'—');}else if(record.kind==='community'){set('orders',Number.isSafeInteger(record.order_count)?record.order_count:'—',record.orders_scope||'当前页');set('gross',money(record.page_gross_minor,record.currency),record.finance_status==='UNCONFIRMED'?'财务核销未确认':'当前页');set('returns',money(record.page_returns_minor,record.currency),'当前页');set('net',money(record.page_net_minor,record.currency),record.totals_scope==='CURRENT_PAGE_ONLY'?'仅当前页':'暂无汇总');}else if(record.kind==='daily'){const note=record.finance_status==='UNCONFIRMED'?'今日记录 · 财务未确认':'今日记录',impressions=Number.isSafeInteger(record.ad_impression_count)?record.ad_impression_count:null,clicks=Number.isSafeInteger(record.ad_click_count)?record.ad_click_count:null,rate=impressions===null||clicks===null?'—':impressions?((clicks/impressions)*100).toFixed(2)+'%':'0.00%',activeAds=Number.isSafeInteger(record.active_ad_count)?record.active_ad_count:null;set('pending_merchants',Number.isSafeInteger(record.pending_merchant_count)?record.pending_merchant_count:'—','点击进入审核');set('daily_transaction_amount',money(record.transaction_amount_minor,record.currency),'已验签支付');set('daily_transaction_count',Number.isSafeInteger(record.transaction_count)?record.transaction_count:'—','已验签支付');set('daily_split',money(record.completed_split_minor,record.currency),note);set('daily_split_count',Number.isSafeInteger(record.completed_split_count)?record.completed_split_count:'—','今日已完成');set('daily_refund',money(record.confirmed_refund_minor,record.currency),note);set('daily_refund_count',Number.isSafeInteger(record.confirmed_refund_count)?record.confirmed_refund_count:'—','今日已确认');set('ad_overview',impressions===null?'—':impressions+' 次浏览',(clicks===null?'—':clicks+' 次点击')+' · 点击率 '+rate+' · '+(activeAds===null?'投放数未读取':'投放中 '+activeAds+' 条'));renderHomeTrends(record.daily_series);}};
 window.communityHomeContext=value=>{const role=value&&typeof value.workspace==='string'&&value.workspace&&['CUSTOMER','COMMUNITY_ADMIN','MERCHANT_ADMIN','PLATFORM_REVIEWER','PLATFORM_OWNER'].includes(value.role)?value.role:null;const admin=value?.admin&&['ROOT','DELEGATE'].includes(value.admin.kind)&&Array.isArray(value.admin.capabilities)?{kind:value.admin.kind,capabilities:value.admin.capabilities.filter(x=>typeof x==='string')}:null;homeContext=value&&typeof value.csrf==='string'&&value.csrf&&(role||admin)?{role,workspace:role?value.workspace:null,admin,reviewer:value.reviewer===true}:null;renderHome();const target=navigationHashTargets.get(globalThis.location?.hash);if(Number.isInteger(target)&&buttons[target]&&!buttons[target].hidden)select(target);else applyWorkspaceRoute();};
 renderHome();
 // ROLE_HOME_END

 // ORIGINAL_UI_RESTORATION_BEGIN: presentation only; original handlers remain authoritative.
 const retainedQuery=(panel,node,label)=>{const d=document.createElement('details'),summary=document.createElement('summary');d.className='restored-query';d.open=true;summary.textContent=label;d.append(summary,node);panel.append(d);return d;};
 const profileQuery=retainedQuery(profilePanel,actions,'查询与登记社区');
 const openQueryDisclosure=retainedQuery(openPanel,openQuery,'社区查询');
 const promotionQueryDisclosure=retainedQuery(promotionPanel,promotionQuery,'推广查询');
 const memberQueryDisclosure=retainedQuery(memberPanel,memberQuery,'社区商家查询');
 const customerQuery=retainedQuery(customerPanel,document.getElementById('readProfile'),'个人资料查询');
 const receiverWorkspaceOriginal=document.getElementById('receiverWorkspace').closest('label');
 const receiverEditReturn=document.createElement('button');receiverEditReturn.type='button';receiverEditReturn.textContent='返回接收关系列表';receiverEditReturn.className='restored-primary-return';receiverEditReturn.onclick=()=>{receiverActions.open=false;receiverBack.click();};receiverActions.append(receiverEditReturn);
 operationQuery.classList.add('operation-query-action');reportPanel.append(reportControls);platformPanel.append(orderQuery);customerPanel.insertBefore(customerForm,customerBack);receiverPanel.insertBefore(receiverActions,receiverQueryControls);
 // Move original actions outside the data cards, never clone listeners or permission state.
 const profileSecondary=document.createElement('details'),profileSecondaryTitle=document.createElement('summary');profileSecondary.className='restored-secondary';profileSecondaryTitle.textContent='编辑与刷新';profileSecondary.append(profileSecondaryTitle,edit,reread);profilePanel.append(toList,profileSecondary);
 profilePanel.insertBefore(toList,profileQuery);profilePanel.insertBefore(profileSecondary,profileQuery);
 openPanel.insertBefore(backOpen,openActions);openPanel.insertBefore(refreshOpen,openActions);promotionPanel.insertBefore(promotionBack,promotionActions);memberPanel.insertBefore(memberBack,memberQueryDisclosure);memberPanel.insertBefore(memberRefresh,memberQueryDisclosure);
 for(const button of [toList,backOpen,promotionBack,memberBack])button.classList.add('restored-primary-return');
 refreshNavigationGroups();
 const originalOptionLabels={decision:{APPROVED:'通过',CORRECTION:'要求补充资料',REJECTED:'驳回',PAUSED:'暂停'},directoryStatus:{ALL:'全部',DRAFT:'草稿',PENDING:'待审核',CORRECTION:'待补充资料',REJECTED:'已驳回',APPROVED:'已通过',PAUSED:'已暂停'},platformMerchantState:{ACTIVE:'正常',PAUSED:'暂停新交易',DISABLED:'停用新交易'},promotionState:{ACTIVE:'启用',PAUSED:'暂停'},platformOrderStatus:{ALL:'全部',PENDING:'待处理',SUCCESS:'本地成功状态',FAILED:'失败',CANCELLED:'已取消',REFUNDED:'本地退款状态'}};
 for(const [id,labels]of Object.entries(originalOptionLabels)){for(const option of document.getElementById(id)?.options||[]){if(Object.prototype.hasOwnProperty.call(labels,option.value))option.label=labels[option.value];}}
 for(const button of [reviewRead,merchantRead])button.classList.add('restored-secondary-action');
 const safeText=(node,text)=>{if(node&&node.textContent!==text)node.textContent=text;};
 const safeHidden=(node,value)=>{if(node&&node.hidden!==value)node.hidden=value;};
 let contextualReturn=null;
 function syncRestoredPresentation(){
  contextualReturn=null;main.classList.toggle('restored-specific-status',[profileIndex,openIndex,promotionIndex,memberIndex,reviewIndex,merchantIndex,receiverIndex,panels.indexOf(platformPanel)].includes(activeIndex));if(activeIndex===null)return;
  let title=pageTitle?.textContent;
  const profileEditing=!profileForm.hidden,profileDetailed=!detail.hidden;
  if(activeIndex===profileIndex){title='社区资料'+(profileEditing?' · 编辑':profileDetailed?' · 详情':'');if(profileDetailed)contextualReturn=toList;}
  else if(activeIndex===openIndex){title='社区开通'+(openActions.open?' · 关系操作':!openDetails.hidden?' · 详情':'');if(openActions.open)contextualReturn={click:()=>{openActions.open=false;backOpen.click();}};else if(!openDetails.hidden)contextualReturn=backOpen;}
  else if(activeIndex===promotionIndex){const before=promotionActions.open?promotionQueryDisclosure:promotionActions;const siblings=Array.from(promotionPanel.children);if(siblings.indexOf(promotionBack)!==siblings.indexOf(before)-1)promotionPanel.insertBefore(promotionBack,before);title='社区推广'+(promotionActions.open?' · 编辑':!promotionDetail.hidden?' · 详情':'');if(promotionActions.open)contextualReturn={click:()=>{promotionActions.open=false;promotionBack.click();}};else if(!promotionDetail.hidden)contextualReturn=promotionBack;}
  else if(activeIndex===memberIndex){title='社区商家'+(!memberDetail.hidden?' · 详情':'');if(!memberDetail.hidden)contextualReturn=memberBack;}
  else if(activeIndex===customerIndex&&customerMode!=='list')contextualReturn=customerBack;
  else if(activeIndex===reviewIndex&&reviewMode!=='list')contextualReturn=reviewBack;
  else if(activeIndex===merchantIndex&&merchantMode!=='list')contextualReturn=merchantBack;
  else if(activeIndex===receiverIndex){const editing=receiverActions.open;const destination=editing?receiverActions:receiverQuery;if(receiverWorkspaceOriginal.parentNode!==destination)destination.insertBefore(receiverWorkspaceOriginal,editing?document.getElementById('receiverId').closest('label'):document.getElementById('listReceiverRelations'));title=receiverPanel.querySelector('h2').textContent+(editing?' · 编辑':!receiverDetail.hidden?' · 详情':'');if(editing)contextualReturn={click:()=>{receiverActions.open=false;receiverBack.click();}};else if(!receiverDetail.hidden)contextualReturn=receiverBack;}
  else if(activeIndex===panels.indexOf(platformPanel)){if(document.getElementById('platformView').value==='platform_orders'){if(!orderDetail.hidden)contextualReturn=orderBack;}else if(operationMode!=='list')contextualReturn=operationBack;}
  else if(activeIndex===reportIndex){title=snapshotMode==='overview'?'订单与结算':snapshotKind==='refund'?'退款管理':'分账明细';if(snapshotMode==='detail'){title+=' · 详情';contextualReturn=snapshotDetail.querySelector('.snapshot-detail-action');}}
  safeText(pageTitle,title);safeText(back,contextualReturn?'‹ 返回列表':'‹ 返回工作台');
  safeHidden(toList,!profileDetailed);safeHidden(profileSecondary,!profileDetailed||profileEditing);
  safeHidden(backOpen,openDetails.hidden);safeHidden(refreshOpen,openDetails.hidden);
  safeHidden(promotionBack,promotionDetail.hidden&&!promotionActions.open);safeHidden(memberBack,memberDetail.hidden);safeHidden(memberRefresh,memberDetail.hidden);
  openPanel.classList.toggle('restored-editing',openActions.open);promotionPanel.classList.toggle('restored-editing',promotionActions.open);receiverPanel.classList.toggle('restored-editing',receiverActions.open);
  profilePanel.classList.toggle('restored-profile-editing',profileEditing);platformPanel.classList.toggle('restored-operation-editing',operationMode==='edit'&&document.getElementById('platformView').value!=='platform_orders');
  for(const [panel,query]of [[profilePanel,profileQuery],[openPanel,openQueryDisclosure],[promotionPanel,promotionQueryDisclosure],[memberPanel,memberQueryDisclosure],[customerPanel,customerQuery]])panel.classList.add('restored-canvas');
 }
 // This observes only rendered state, not identity/authorization. It never sends requests.
 const presentationObserver=new MutationObserver(syncRestoredPresentation);presentationObserver.observe(main,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['hidden','open']});
 back.addEventListener('click',()=>{syncRestoredPresentation();if(contextualReturn)contextualReturn.click();else select(null);});select(null,false);syncRestoredPresentation();
 // ORIGINAL_UI_RESTORATION_END

})();
