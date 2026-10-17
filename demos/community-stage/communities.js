'use strict';
(()=>{
 const $=id=>document.getElementById(id);let auth=null,epoch=0,current=null,page=null,busy=false,profileVersion=null,platformPage=null,merchantPage=null;
 window.configureCommunityPortal=context=>{epoch++;auth=null;current=null;page=null;busy=false;profileVersion=null;for(const id of ['name','description','contact','reference','opinion','nickname','customerContact','referralInput','receiverWorkspace','receiverId','receiverVersion','platformMerchantWorkspace','platformMerchantVersion','platformMerchantReason','promotionScene','promotionTitle','promotionExpiry','promotionCode','promotionVersion'])$(id).value='';platformPage=null;merchantPage=null;$('merchantRecords').replaceChildren();$('merchantResult').textContent='';$('moreMerchants').hidden=true;$('moreMerchants').disabled=false;$('platformMerchants').disabled=false;$('platformMerchantState').value='ACTIVE';$('morePlatformView').hidden=true;$('platformViewResult').textContent='';$('records').replaceChildren();$('result').textContent='';$('customerResult').textContent='';$('more').hidden=true;if(context&&typeof context.csrf==='string'&&context.csrf&&typeof context.workspace==='string'&&context.workspace)auth={csrf:context.csrf,workspace:context.workspace};$('message').textContent=auth?'已连接原客户中心身份。':'请从客户中心进入已授权社区工作区。';};
 async function call(op,params,t){if(!auth)throw Error('需要客户中心登录');const identity=auth;const response=await fetch('/community/directory',{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',headers:{'Content-Type':'application/json','X-CSRF-Token':identity.csrf},body:JSON.stringify({workspace:identity.workspace,operation:op,params})});const body=await response.json();if(t!==epoch)throw Error('身份已变化');if(!response.ok)throw Error(body.error||'操作未确认，请先查询状态');return body.result;}
 async function action(fn){if(busy)return;const t=epoch;busy=true;try{await fn(t);if(t===epoch)$('message').textContent='操作完成';}catch(e){if(t===epoch)$('message').textContent=e.message;}finally{if(t===epoch)busy=false;}}
 function render(r){$('result').textContent=JSON.stringify(r,null,2);if(r.id){current=r;$('reference').value=r.id;$('name').value=r.name||'';$('description').value=r.description||'';$('contact').value=r.contact||'';}}
 const id=()=>$('reference').value.trim();const version=()=>{if(!current||current.id!==id())throw Error('先查询当前社区版本');return current.version;};
 async function list(t,operation,params){const r=await call(operation,params,t);if(t!==epoch)return;$('records').replaceChildren();for(const item of r.records){const line=document.createElement('article');line.textContent=(item.name||item.user_id||item.reference||item.id)+' '+(item.state||item.kind||item.order_state||item.provider_state||'')+(item.amount_minor!==undefined?' · '+item.amount_minor+'分':'')+(item.net_minor!==undefined?' · 分账净额 '+item.net_minor+'分':'');if(item.kind&&item.message){line.textContent=item.message;const read=document.createElement('button');read.textContent=item.read?'已读':'标记已读';read.disabled=item.read;read.onclick=()=>action(async n=>{await call('notice_read',{notice_id:item.id},n);if(n===epoch){read.textContent='已读';read.disabled=true;}});line.append(read);}else if(item.id&&item.id.startsWith('cp_')){line.textContent=item.title+' · '+item.id+' · '+item.status+' · 新成员 '+item.new_members+' · 版本 '+item.version;const b=document.createElement('button');b.textContent='选择推广记录';b.onclick=()=>{if(busy)return;$('promotionCode').value=item.id;$('promotionVersion').value=item.version;};line.append(b);}else if(item.id){const button=document.createElement('button');button.textContent='打开';button.onclick=()=>action(async n=>render(await call('status',{community_id:item.id},n)));line.append(button);}$('records').append(line);}$('result').textContent=JSON.stringify({currency:r.currency,page_gross_minor:r.page_gross_minor,page_returns_minor:r.page_returns_minor,page_net_minor:r.page_net_minor,totals_scope:r.totals_scope,finance_status:r.finance_status},null,2);page=r.has_more?{operation,params:{...params,after_id:r.next_cursor}}:null;$('more').hidden=!page;}
 $('profile').onsubmit=e=>{e.preventDefault();action(async t=>{const p={name:$('name').value,description:$('description').value,contact:$('contact').value};render(await call(current?'update':'register',current?{...p,community_id:id(),expected_version:version()}:p,t));});};
 $('submit').onclick=()=>action(async t=>render(await call('submit',{community_id:id(),expected_version:version()},t)));
 $('read').onclick=()=>action(async t=>render(await call('status',{community_id:id()},t)));
 $('mine').onclick=()=>action(t=>list(t,'mine',{}));$('pending').onclick=()=>action(t=>list(t,'list',{after_id:'',status:'PENDING'}));
 for(const op of ['join','leave'])$(op).onclick=()=>action(async t=>render(await call(op,{community_id:id(),kind:$('kind').value},t)));
 $('members').onclick=()=>action(t=>list(t,'members',{community_id:id(),after_id:''}));
 $('review').onclick=()=>action(async t=>render(await call('review',{community_id:id(),expected_version:version(),decision:$('decision').value,opinion:$('opinion').value},t)));
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
   $('merchantRecords').replaceChildren(...rows);
   $('merchantResult').textContent=r.records.length?JSON.stringify(r,null,2):'暂无已准入商家';
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
 async function platformView(t,operation,params){const r=await call(operation,params,t);if(t!==epoch)return;$('platformViewResult').textContent=JSON.stringify(r,null,2);platformPage=r.has_more?{operation,params:{...params,after_id:r.next_cursor}}:null;$('morePlatformView').hidden=!platformPage;}
 $('readPlatformView').onclick=()=>action(t=>{const op=$('platformView').value;const params=op==='platform_overview'?{}:op==='platform_orders'?{after_id:0,status:$('platformOrderStatus').value}:{after_id:op==='platform_audit'?0:''};return platformView(t,op,params);});
 $('morePlatformView').onclick=()=>action(t=>platformPage&&platformView(t,platformPage.operation,platformPage.params));
 window.configureCommunityPortal(null);
})();
