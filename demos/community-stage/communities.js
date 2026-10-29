'use strict';
(()=>{
 const registrationKey=workspace=>'community-register-unconfirmed:'+workspace;
 const beginRegistration=()=>{
  if(!auth)throw Error('需要客户中心登录');
  try{
   const key=registrationKey(auth.workspace);
   if(localStorage.getItem(key))throw Error('REGISTRATION_UNCONFIRMED');
   localStorage.setItem(key,'UNKNOWN');
   if(localStorage.getItem(key)!=='UNKNOWN')throw Error('STORAGE_UNAVAILABLE');
   return key;
  }catch(error){throw Error(error.message==='REGISTRATION_UNCONFIRMED'?'登记结果未确认，请先查询我的社区并对账；禁止再次登记':'无法保存登记防重记录，未发送登记请求');}
 };
 const openView=(type,record)=>{if(typeof window.communityOpenView==='function')window.communityOpenView({type,record});};
 const profileView=(type,record)=>{if(typeof window.communityProfileView==='function')window.communityProfileView({type,record});};
 const $=id=>document.getElementById(id);let auth=null,epoch=0,current=null,page=null,busy=false,profileVersion=null,platformPage=null,merchantPage=null,directoryGeneration=0;
 window.configureCommunityPortal=context=>{openView('reset');profileView('reset');epoch++;directoryGeneration++;$('directoryStatus').value='ALL';auth=null;current=null;page=null;busy=false;profileVersion=null;for(const id of ['name','description','contact','reference','opinion','nickname','customerContact','referralInput','receiverWorkspace','receiverId','receiverVersion','platformMerchantWorkspace','platformMerchantVersion','platformMerchantReason','promotionScene','promotionTitle','promotionExpiry','promotionCode','promotionVersion'])$(id).value='';platformPage=null;merchantPage=null;$('merchantRecords').replaceChildren();$('merchantResult').textContent='';$('moreMerchants').hidden=true;$('moreMerchants').disabled=false;$('platformMerchants').disabled=false;$('platformMerchantState').value='ACTIVE';$('morePlatformView').hidden=true;$('platformViewResult').textContent='';$('records').replaceChildren();$('result').textContent='';$('customerResult').textContent='';$('more').hidden=true;if(context&&typeof context.csrf==='string'&&context.csrf&&typeof context.workspace==='string'&&context.workspace)auth={csrf:context.csrf,workspace:context.workspace};$('message').textContent=auth?'已连接原客户中心身份。':'请从客户中心进入已授权社区工作区。';};
 async function call(op,params,t){if(!auth)throw Error('需要客户中心登录');const identity=auth;const response=await fetch('/community/directory',{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',headers:{'Content-Type':'application/json','X-CSRF-Token':identity.csrf},body:JSON.stringify({workspace:identity.workspace,operation:op,params})});const body=await response.json();if(t!==epoch)throw Error('身份已变化');if(!response.ok)throw Error(body.error||'操作未确认，请先查询状态');return body.result;}
 async function action(fn){if(busy)return;const t=epoch,generation=directoryGeneration;busy=true;try{await fn(t);if(t===epoch&&generation===directoryGeneration)$('message').textContent='操作完成';}catch(e){if(t===epoch&&generation===directoryGeneration)$('message').textContent=({ACCESS_DENIED:'无权进行此操作，请确认账户与工作区。',COMMUNITY_PRIVATE:'这条社区资料暂不可查看。'}[e.message]||e.message);}finally{if(t===epoch)busy=false;}}
 function render(r){$('result').textContent=JSON.stringify(r,null,2);if(r.id){current=r;$('reference').value=r.id;$('name').value=r.name||'';$('description').value=r.description||'';$('contact').value=r.contact||'';}}
 const id=()=>$('reference').value.trim();const version=()=>{if(!current||current.id!==id())throw Error('先查询当前社区版本');return current.version;};
 async function list(t,operation,params){if(operation==='members'){$('records').replaceChildren();$('result').textContent='';page=null;$('more').hidden=true;openView('members');}if(operation==='mine')profileView('list');const generation=directoryGeneration,selectedReference=$('reference').value;const r=await call(operation,params,t);if(t!==epoch||generation!==directoryGeneration||(operation==='members'&&selectedReference!==$('reference').value))return;$('records').replaceChildren();for(const item of r.records){const line=document.createElement('article');line.textContent=(item.name||item.user_id||item.reference||item.id)+' '+(item.state||item.kind||item.order_state||item.provider_state||'')+(item.amount_minor!==undefined?' · '+item.amount_minor+'分':'')+(item.net_minor!==undefined?' · 分账净额 '+item.net_minor+'分':'');if(operation==='mine'){line.textContent='';line.className='community-record-card';const title=document.createElement('h3');title.textContent='记录列表 · 当前范围';line.append(title);const fields=document.createElement('dl');for(const [label,key] of [['社区名称','name'],['社区介绍','description'],['联系人及联系方式','contact'],['状态','state']]){const term=document.createElement('dt'),value=document.createElement('dd');term.textContent=label;value.textContent=item[key]===undefined?'当前权限未返回该字段':key==='state'?({DRAFT:'草稿',PENDING:'待审核',CORRECTION:'待补充资料',REJECTED:'已驳回',APPROVED:'已通过',PAUSED:'已暂停'}[item[key]]||String(item[key])):String(item[key]);fields.append(term);fields.append(value);}line.append(fields);}
 if(item.kind&&item.message){line.textContent=item.message;const read=document.createElement('button');read.textContent=item.read?'已读':'标记已读';read.disabled=item.read;read.onclick=()=>action(async n=>{await call('notice_read',{notice_id:item.id},n);if(n===epoch){read.textContent='已读';read.disabled=true;}});line.append(read);}else if(item.id&&item.id.startsWith('cp_')){line.textContent=item.title+' · '+item.id+' · '+item.status+' · 新成员 '+item.new_members+' · 版本 '+item.version;const b=document.createElement('button');b.textContent='选择推广记录';b.onclick=()=>{if(busy)return;$('promotionCode').value=item.id;$('promotionVersion').value=item.version;};line.append(b);}else if(item.id){const button=document.createElement('button');button.textContent=operation==='mine'?'查看详情':'打开';button.onclick=()=>{if(t!==epoch||generation!==directoryGeneration)return;return action(n=>readCommunity(n,item.id));};line.append(button);}$('records').append(line);}$('result').textContent=JSON.stringify({currency:r.currency,page_gross_minor:r.page_gross_minor,page_returns_minor:r.page_returns_minor,page_net_minor:r.page_net_minor,totals_scope:r.totals_scope,finance_status:r.finance_status},null,2);page=r.has_more?{operation,params:{...params,after_id:r.next_cursor}}:null;$('more').hidden=!page;if(operation==='mine')profileView('listed',{count:r.records.length});}
 async function communityResult(t,operation,params){if(operation==='status')openView('loading');const generation=directoryGeneration,selectedReference=$('reference').value;const registration=operation==='register'?beginRegistration():null;try{const r=await call(operation,params,t);if(t===epoch&&generation===directoryGeneration&&selectedReference===$('reference').value){if(registration&&r&&r.id&&Number.isInteger(r.version))localStorage.removeItem(registration);render(r);if(operation==='status')openView('status',r);if(['join','leave'].includes(operation))openView('relation',r);if(['status','update','register','submit'].includes(operation))profileView('detail',r);}}catch(error){if(t===epoch&&generation===directoryGeneration&&['status','join','leave'].includes(operation))openView('error');if(t===epoch&&generation===directoryGeneration&&['status','update','register','submit'].includes(operation)){current=null;page=null;$('records').replaceChildren();$('more').hidden=true;$('result').textContent='';for(const field of ['name','description','contact'])$(field).value='';profileView('error');}throw error;}}
 $('profile').onsubmit=e=>{e.preventDefault();return action(t=>{if(!current&&id())throw Error('先回读当前社区版本；不会将未确认更新转为新登记');const p={name:$('name').value,description:$('description').value,contact:$('contact').value};return communityResult(t,current?'update':'register',current?{...p,community_id:id(),expected_version:version()}:p);});};
 $('submit').onclick=()=>action(t=>communityResult(t,'submit',{community_id:id(),expected_version:version()}));
 async function readCommunity(t,reference){return communityResult(t,'status',{community_id:reference});}
 $('read').onclick=()=>action(t=>readCommunity(t,id()));
 window.communitySectionChanged=()=>{directoryGeneration++;page=null;$('records').replaceChildren();$('result').textContent='';$('more').hidden=true;};
 $('reference').oninput=()=>{directoryGeneration++;current=null;page=null;$('records').replaceChildren();$('result').textContent='';$('more').hidden=true;for(const field of ['name','description','contact'])$(field).value='';profileView('reset');openView('reset');};
 $('mine').onclick=()=>action(async t=>{try{return await list(t,'mine',{});}catch(error){if(t===epoch){$('records').replaceChildren();$('more').hidden=true;profileView('error');}throw error;}});$('pending').onclick=()=>queryDirectory('PENDING');
 function resetDirectory(){openView('reset');directoryGeneration++;current=null;page=null;$('records').replaceChildren();$('result').textContent='';$('more').hidden=true;for(const field of ['reference','name','description','contact','opinion'])$(field).value='';$('message').textContent='筛选已更改，请查询平台社区';}
 function queryDirectory(status){if(busy)return;if(!['ALL','DRAFT','PENDING','CORRECTION','REJECTED','APPROVED','PAUSED'].includes(status))return;$('directoryStatus').value=status;resetDirectory();return action(t=>list(t,'list',{after_id:'',status}));}
 $('directoryStatus').onchange=resetDirectory;
 $('listDirectory').onclick=()=>queryDirectory($('directoryStatus').value);
 for(const op of ['join','leave'])$(op).onclick=()=>action(t=>communityResult(t,op,{community_id:id(),kind:$('kind').value}));
 $('members').onclick=()=>action(t=>list(t,'members',{community_id:id(),after_id:''}));
 $('review').onclick=()=>action(t=>communityResult(t,'review',{community_id:id(),expected_version:version(),decision:$('decision').value,opinion:$('opinion').value}));
 $('more').onclick=()=>action(t=>page&&list(t,page.operation,page.params));
 $('readProfile').onclick=()=>action(async t=>{const r=await call('profile_read',{},t);profileVersion=r.version;$('nickname').value=r.nickname;$('customerContact').value=r.contact;$('customerResult').textContent=JSON.stringify(r,null,2);});
 $('customerProfile').onsubmit=e=>{e.preventDefault();action(async t=>{if(profileVersion===null)throw Error('先读取当前资料');const r=await call('profile_update',{nickname:$('nickname').value,contact:$('customerContact').value,expected_version:profileVersion},t);profileVersion=r.version;$('customerResult').textContent=JSON.stringify(r,null,2);});};
 $('referralCode').onclick=()=>action(async t=>{$('customerResult').textContent=JSON.stringify(await call('referral_code',{},t),null,2);});
 $('bindReferrer').onclick=()=>action(async t=>{$('customerResult').textContent=JSON.stringify(await call('referral_bind',{code:$('referralInput').value},t),null,2);});
 $('notices').onclick=()=>action(t=>list(t,'notices',{after_id:''}));
 $('communityOrders').onclick=()=>action(t=>list(t,'community_orders',{community_id:id(),after_id:''}));
 $('communityEarnings').onclick=()=>action(t=>list(t,'community_earnings',{community_id:id(),after_id:''}));
 $('bindReceiver').onclick=()=>action(async t=>{const r=await call('community_receiver_bind',{community_id:id(),provider_workspace:$('receiverWorkspace').value,receiver_id:$('receiverId').value,expected_version:Number($('receiverVersion').value)},t);if(t===epoch){$('receiverVersion').value=r.version;$('result').textContent=JSON.stringify(r,null,2);}});
 async function merchants(t,afterWorkspace=''){
  if(!afterWorkspace){merchantPage=null;$('merchantRecords').replaceChildren();$('merchantResult').textContent='';$('moreMerchants').hidden=true;}
  $('platformMerchants').disabled=true;$('moreMerchants').disabled=true;
  try{
   const r=await call('platform_merchants',{after_workspace:afterWorkspace},t);if(t!==epoch)return;
   const rows=[];
   for(const item of r.records){
    const line=document.createElement('article'),select=document.createElement('button');
    line.textContent=(item.name||item.workspace)+' · '+item.workspace+' · 平台状态 '+item.lifecycle.status+' · 门店状态 '+item.store_status+' · 版本 '+item.lifecycle.version;
    select.textContent='选择商家';select.onclick=()=>{if(busy||t!==epoch)return;$('platformMerchantWorkspace').value=item.workspace;$('platformMerchantVersion').value=item.lifecycle.version;$('platformMerchantState').value=item.lifecycle.status;$('platformMerchantReason').value=item.lifecycle.reason||'';};
    line.append(select);rows.push(line);
   }
   for(const item of r.unavailable_mappings||[]){const line=document.createElement('article');line.textContent=item.workspace+' · 原商家权限或映射不可用，未读取其门店及订单';rows.push(line);}
   $('merchantRecords').replaceChildren(...rows);
   $('merchantResult').textContent=r.coverage_complete===false?'商家覆盖不完整，共有 '+r.unavailable_mapping_count+' 个原映射不可用；当前记录不代表全部商家。\n'+JSON.stringify(r,null,2):r.records.length?JSON.stringify(r,null,2):'暂无已准入商家';
   merchantPage=r.has_more&&typeof r.next_cursor==='string'&&r.next_cursor>afterWorkspace?r.next_cursor:null;
   $('moreMerchants').hidden=!merchantPage;
  }finally{if(t===epoch){$('platformMerchants').disabled=false;$('moreMerchants').disabled=false;}}
 }
 $('platformMerchants').onclick=()=>action(t=>merchants(t));
 $('moreMerchants').onclick=()=>action(t=>merchantPage&&merchants(t,merchantPage));
 $('saveMerchantState').onclick=()=>action(async t=>{const r=await call('platform_merchant_state',{merchant_workspace:$('platformMerchantWorkspace').value,status:$('platformMerchantState').value,expected_version:Number($('platformMerchantVersion').value),reason:$('platformMerchantReason').value},t);if(t===epoch){$('platformMerchantVersion').value=r.version;$('result').textContent=JSON.stringify(r,null,2);}});
 $('createPromotion').onclick=()=>action(async t=>{const r=await call('promotion_create',{community_id:id(),scene:$('promotionScene').value,title:$('promotionTitle').value,expires_at:Math.floor(new Date($('promotionExpiry').value).getTime()/1000)},t);if(t===epoch){$('promotionCode').value=r.id;$('promotionVersion').value=r.version;$('result').textContent=JSON.stringify(r,null,2);}});
 $('listPromotions').onclick=()=>action(t=>list(t,'promotions',{community_id:id(),after_id:''}));
 $('savePromotionState').onclick=()=>action(async t=>{const r=await call('promotion_state',{community_id:id(),code:$('promotionCode').value,expected_version:Number($('promotionVersion').value),status:$('promotionState').value},t);if(t===epoch){$('promotionVersion').value=r.version;$('result').textContent=JSON.stringify(r,null,2);}});
 async function platformView(t,operation,params){const r=await call(operation,params,t);if(t!==epoch)return;$('platformViewResult').textContent=(r.coverage_complete===false?'部分商家权限或映射不可用；以下仅为可访问门店小计，不能作为完整总额。\n':'')+JSON.stringify(r,null,2);platformPage=r.has_more?{operation,params:{...params,after_id:r.next_cursor}}:null;$('morePlatformView').hidden=!platformPage;}
 $('readPlatformView').onclick=()=>action(t=>{const op=$('platformView').value;const params=op==='platform_overview'?{}:op==='platform_orders'?{after_id:0,status:$('platformOrderStatus').value}:{after_id:op==='platform_audit'?0:''};return platformView(t,op,params);});
 $('morePlatformView').onclick=()=>action(t=>platformPage&&platformView(t,platformPage.operation,platformPage.params));
 window.configureCommunityPortal(null);
 try{
  if(location.hostname==='community-preview.wenwenwenyiyiyi.work'&&location.hash.startsWith('#preview=')){
   const context=JSON.parse(decodeURIComponent(location.hash.slice(9)));
   history.replaceState(null,'',location.pathname);
   window.configureCommunityPortal(context);
  }
 }catch(_){window.configureCommunityPortal(null);}
})();
