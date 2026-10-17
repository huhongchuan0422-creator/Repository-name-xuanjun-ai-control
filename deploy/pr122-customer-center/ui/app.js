'use strict';
const base='/customer/center/api/';let csrf=sessionStorage.getItem('xj_csrf')||'',project='',role='',viewGeneration=0;
const statusLabels={ARCHIVED:'已归档',PENDING:'待发送',ACCEPTED:'渠道已受理',UNKNOWN:'结果待确认',FAILED:'发送失败'};
const channelLabels={WEB:'网页项目沟通',WEB_AI:'网页AI客服',TELEGRAM:'Telegram客服',FEISHU:'飞书客服'};
const $=id=>document.getElementById(id),states={NOT_STARTED:'未开始',PARTIAL:'部分提交',SUBMITTED:'已提交',IN_REVIEW:'审核中',NEEDS_CORRECTION:'需要补正',ACCEPTED:'已通过'};
function node(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
function notice(text){$('notice').textContent=text;}
async function api(op,body){const generation=viewGeneration,authOperation=['login','register','verify','request_reset','reset','logout'].includes(op);const r=await fetch(base+op,{credentials:'same-origin',method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-CSRF-Token':csrf}:{},body:body?JSON.stringify(body):undefined,cache:'no-store'});const d=await r.json();if(!authOperation&&generation!==viewGeneration){const error=new Error('页面状态已更新，请重新打开项目。');error.stale=true;throw error;}if(!r.ok){const error=new Error(d.error||'请求未完成');error.status=r.status;if((r.status===401||r.status===403)&&op!=='me'&&!authOperation)clearProject(false);throw error;}return d;}
function form(id,fn){$(id).addEventListener('submit',async e=>{e.preventDefault();const button=e.submitter;if(button?.disabled)return;if(button)button.disabled=true;try{await fn(Object.fromEntries(new FormData(e.target)));}catch(err){notice(err.message);}finally{if(button)button.disabled=false;}});}
function clearProject(clearNavigation=true){
 viewGeneration++;project='';role='';$('project').hidden=true;
 for(const id of ['project-title','overall','materials','messages','pending-links','change-list','bind-help','invite-result'])$(id).replaceChildren();
 if(clearNavigation){$('projects').replaceChildren();$('channel-status').replaceChildren();}
 $('private-previews')?.replaceChildren();$('privacy-tools')?.replaceChildren();
 for(const id of ['message','bind','invite','revoke','accept'])$(id).reset();
}
function clearSession(){csrf='';sessionStorage.removeItem('xj_csrf');clearProject();$('auth').hidden=false;$('workspace').hidden=true;$('logout').hidden=true;}
async function start(){
 clearProject();const generation=viewGeneration;$('workspace').hidden=true;
 try{const d=await api('me');$('auth').hidden=true;$('workspace').hidden=false;$('logout').hidden=false;for(const p of d.projects){const b=node('button',p.title);b.addEventListener('click',()=>openProject(p));$('projects').append(b);}if(!d.projects.length)$('projects').append(node('p','尚无已授权项目。请联系项目负责人核实合同关系，或登录接受专属邀请。'));$('channel-status').replaceChildren(...['web_ai','telegram','feishu'].map(k=>{const v=d.channels[k];const name={web_ai:'网页AI客服',telegram:'Telegram客服',feishu:'飞书客服'}[k];return node('p',name+'：'+(v.state==='PENDING_CONNECTION'?'待接通':'已配置，待验收'));}));
 }catch(error){
  if(error.stale||generation!==viewGeneration)return;
  if(error.status===401||error.status===403){clearSession();}
  else{$('auth').hidden=false;$('logout').hidden=!csrf;notice('暂时无法确认登录状态，请刷新重试。'+error.message);}
 }
}
async function authAction(id,valid,fn){const button=$(id);if(button.disabled||!valid())return;button.disabled=true;try{await fn();}catch(error){notice(error.message);}finally{button.disabled=false;}}
form('login',async d=>{const r=await api('login',d);csrf=r.csrf;sessionStorage.setItem('xj_csrf',csrf);$('login').elements.password.value='';notice('已登录');await start();});
$('register').addEventListener('click',()=>authAction('register',()=>$('login').reportValidity(),async()=>{await api('register',Object.fromEntries(new FormData($('login'))));$('login').elements.password.value='';notice('请查看验证邮箱。邮箱服务未接通时不会开放注册。');}));
$('reset-request').addEventListener('click',()=>authAction('reset-request',()=>$('login').elements.email.reportValidity(),async()=>{await api('request_reset',{email:$('login').elements.email.value});notice('如该邮箱已注册，请查看重置邮件。');}));
form('verification',async d=>{await api('verify',d);notice('邮箱已验证，请登录。');$('verification').reset();});
form('reset',async d=>{await api('reset',d);clearSession();$('reset').reset();notice('密码已重置，旧会话已撤销。');await start();});
$('logout').addEventListener('click',()=>authAction('logout',()=>true,async()=>{await api('logout',{});clearSession();window.location.reload();}));
async function openProject(p){clearProject(false);const generation=viewGeneration;project=p.id;role=p.role;$('project').hidden=false;$('project-title').textContent=p.title;$('members').hidden=role!=='OWNER';await refresh();if(generation!==viewGeneration)return;await refreshChanges();if(generation!==viewGeneration)return;await refreshPreviews();}
async function refresh(){try{const d=await api('checklist/'+encodeURIComponent(project));$('overall').textContent='整体状态：'+states[d.overall]+' · 清单版本 '+d.requirements_revision;$('materials').replaceChildren();for(const item of d.items)renderItem(item);const m=await api('messages/'+encodeURIComponent(project));$('messages').replaceChildren(...m.messages.map(x=>node('p',(channelLabels[x.channel]||'项目沟通')+' · '+(statusLabels[x.status]||'待确认')+'\n'+x.body)));const evidence=node('a','下载本项目沟通记录与校验摘要');evidence.href=base+'evidence/'+encodeURIComponent(project);evidence.download='project-message-evidence.json';$('messages').append(evidence,node('p','记录仅作沟通留证；本地摘要不是公证或独立时间戳，未确认的政策信息保留待核实。'));const privacy=node('button','隐私告知与个人申请');privacy.type='button';privacy.onclick=openPrivacy;$('messages').append(privacy);const pending=await api('pending_links/'+encodeURIComponent(project));$('pending-links').replaceChildren(...pending.links.map(x=>{const div=node('div');div.append(node('p','确认绑定 '+x.channel+'：'+x.subject));const b=node('button','确认这是我的渠道账号');b.onclick=async()=>{try{await api('confirm_link',{project,challenge_id:x.id});notice('绑定已确认');await refresh();}catch(e){notice(e.message);}};div.append(b);return div;}));}catch(e){notice(e.message);}}
function renderItem(item){const card=node('article');card.className='card';card.append(node('h3',item.title),node('p',states[item.state]+(item.needs_reverification?' · 已到期，需复核':'')),node('p',item.purpose));const details=node('details'),summary=node('summary','准备方法与审核历史');details.append(summary);for(const [key,label] of Object.entries({identity_requirements:'身份与资质',instructions:'操作指引',minimum_permissions:'最小权限',fees:'费用',verified_at:'核验日期',valid_until:'有效期'}))details.append(node('p',label+'：'+(typeof item[key]==='object'?JSON.stringify(item[key]):String(item[key]??'待核实'))));if(item.official_url){const a=node('a','前往官方申请入口');a.href=item.official_url;a.target='_blank';a.rel='noopener noreferrer';details.append(a);}for(const v of item.versions){details.append(node('p','版本 '+v.seq+' · '+v.kind+(v.details.reason?' · '+v.details.reason:'')));if(v.details.object_id){const a=node('a','下载此版本材料');a.href=base+'download/'+encodeURIComponent(project)+'/'+encodeURIComponent(v.details.object_id);details.append(a);}}card.append(details);
 const editable=['OWNER','EDITOR'].includes(role)&&!['SUBMITTED','IN_REVIEW'].includes(item.state);
 if(item.submission_type==='PRIVATE_DOCUMENT'&&editable){const f=node('form'),label=node('label','选择 PDF、PNG 或 JPEG（最大5MB；不要上传密钥）'),input=node('input');input.type='file';input.accept='.pdf,.png,.jpg,.jpeg';input.required=true;label.append(input);const b=node('button','保存为新版本');f.append(label,b);f.onsubmit=async e=>{e.preventDefault();b.disabled=true;try{const file=input.files[0];if(!file||file.size>5000000)throw new Error('请选择5MB以内的材料');const a=new Uint8Array(await file.arrayBuffer());let s='';for(let i=0;i<a.length;i+=8192)s+=String.fromCharCode(...a.subarray(i,i+8192));await api('save',{project,item:item.id,revision:item.revision,kind:'DOCUMENT',content:btoa(s),expires:item.valid_until||null});notice('新版本已保存，原通过版仍保留。');await refresh();}catch(err){notice(err.message);}finally{b.disabled=false;}};card.append(f);}else if(item.submission_type!=='PRIVATE_DOCUMENT')card.append(node('p','使用 '+item.submission_type+' 专用授权入口。未接通前不接受明文凭据。'));
 const actions=[];if(editable&&['PARTIAL','NEEDS_CORRECTION'].includes(item.state))actions.push(['submit','提交审核']);if(role==='REVIEWER'&&item.state==='SUBMITTED')actions.push(['begin_review','开始审核']);if(role==='REVIEWER'&&item.state==='IN_REVIEW')actions.push(['approve','通过'],['request_changes','要求补正']);for(const [action,label] of actions){const b=node('button',label);b.onclick=async()=>{let reason='';if(action==='approve'||action==='request_changes'){reason=window.prompt('请输入审核依据或补正要求');if(!reason)return;}b.disabled=true;try{await api('transition',{project,item:item.id,revision:item.revision,action,reason});await refresh();}catch(e){notice(e.message);}finally{b.disabled=false;}};card.append(b);} $('materials').append(card);}
$('refresh').onclick=refresh;
form('message',async d=>{const r=await api(d.channel==='WEB'?'message':'send',d.channel==='WEB'?{project,body:d.body}:{project,...d});notice('消息状态：'+(statusLabels[r.status]||'待确认'));$('message').elements.body.value='';await refresh();});
form('bind',async d=>{const r=await api('bind',{project,...d});$('bind-help').textContent='请在所选官方客服私聊发送 /bind '+r.challenge+'，然后返回本页刷新并确认账号。5分钟有效。';});
for(const [id,channel] of [['unlink-telegram','TELEGRAM'],['unlink-feishu','FEISHU']])$(id).onclick=async()=>{try{await api('unlink',{project,channel});notice('已解绑');await refresh();}catch(e){notice(e.message);}};
form('invite',async d=>{const r=await api('invite',{project,...d});$('invite-result').textContent='邀请验证码（10分钟有效）：'+r.invitation+'。请通过双方确认的渠道交给受邀成员。';});
form('accept',async d=>{await api('accept_invite',d);$('accept').reset();notice('已加入项目');await start();});
form('revoke',async d=>{await api('revoke',{project,...d});notice('项目权限及渠道已撤销');});
async function refreshChanges(){
 try{const data=await api('changes/'+encodeURIComponent(project));$('change-list').replaceChildren();
 for(const item of data.cases){const events=item.events;if(events[0].kind!=='REQUEST')continue;
  const card=node('article');card.className='card';const request=events[0].payload,last=events[events.length-1];
  card.append(node('h3','页面整改意见'),node('p',request.request));const location=node('details');location.append(node('summary','查看页面与版本记录'),node('p',request.page),node('p',request.page_sha256));card.append(location);
  const labels={REQUESTED:'待评估',NEEDS_EVIDENCE:'待补齐证据',QUOTED:'待客户确认报价',FREE_APPROVED:'评估为免费整改',CUSTOMER_CONFIRMED:'客户已确认',DISPUTED:'客户有异议'};
  card.append(node('p',labels[last.payload.state]||'处理中'));
  const assessment=[...events].reverse().find(e=>e.kind==='ASSESSMENT');
  if(assessment){const a=assessment.payload;card.append(node('p','预计工作量：'+a.estimated_minutes+'分钟'),node('p',a.explanation));
   if(a.state==='NEEDS_EVIDENCE'||!a.totals){card.append(node('p','费用待核实，尚未形成报价。'));}else{
   const table=node('table'),head=node('tr');for(const title of ['整改项目','人民币','美元'])head.append(node('th',title));table.append(head);
   for(const line of a.lines){const row=node('tr');row.append(node('td',line.description),node('td','¥'+(line.cny_minor/100).toFixed(2)),node('td','US$'+(line.usd_minor/100).toFixed(2)));table.append(row);}card.append(table);
   card.append(node('p','合计：¥'+(a.totals.cny_minor/100).toFixed(2)+' / US$'+(a.totals.usd_minor/100).toFixed(2)));
   }
   for(const e of a.evidence){const d=node('details');d.append(node('summary','查看此前确认的需求与证据'));d.append(node('p',e.requirement),node('p','确认时间：'+new Date(e.confirmed_at*1000).toISOString()),node('p','确认主体：'+e.actor),node('p','证据编号：'+e.event_id),node('p','证据SHA256：'+e.sha256),node('p','合同文档SHA256：'+(e.document_sha256||'未核验')),node('p','合同版本SHA256：'+(e.version_sha256||'未核验')),node('p','权威来源：'+(e.source_ref||'未核验')));card.append(d);}
  }
  if(role==='OWNER'&&last.kind==='ASSESSMENT'&&['QUOTED','FREE_APPROVED'].includes(last.payload.state)){
   for(const [action,label] of [['CONFIRM','确认本次范围与费用'],['DISPUTE','提出异议']]){const b=node('button',label);b.type='button';b.addEventListener('click',async()=>{try{await api('change_respond',{project,case:item.id,revision:last.seq,action,reason:label});await refreshChanges();}catch(e){notice(e.message);}});card.append(b);}
  }$('change-list').append(card);
 }if(!$('change-list').children.length)$('change-list').append(node('p','暂无整改意见和费用。'));
 }catch(e){notice(e.message);}
}
window.addEventListener('pageshow',event=>{if(event.persisted)start();});
start();

async function refreshPreviews(){
 let section=$('private-previews');if(!section){section=node('section');section.id='private-previews';$('project').prepend(section);}section.replaceChildren(node('h3','项目预览与验收'));if(role!=='OWNER'){section.append(node('p','当前角色没有客户验收权限。'));return;}
 try{const d=await api('previews/'+encodeURIComponent(project));for(const page of d.pages){const a=node('a','查看 '+page.path);a.href=page.url;const row=node('p');row.append(a);section.append(row);}if(!d.pages.length)section.append(node('p','尚无已审核、已接入的私有预览版本。'));}catch(error){if(error.stale)return;section.append(node('p','私有预览尚未接通，请勿在公共演示提交私有资料。'));}
}


// Loaded only after the customer asks; receipts are requester-private.
async function openPrivacy(){
 const pid=project,generation=viewGeneration;let section=$('privacy-tools');
 if(!section){section=node('section');section.id='privacy-tools';$('project').append(section);}section.replaceChildren();
 try{
  const data=await api('privacy/'+encodeURIComponent(pid));if(generation!==viewGeneration)return;
  section.append(node('h3','隐私告知与个人申请'),node('p','这里仅记录您的选择和申请，不会自动更正或删除资料；合规结论及实际处理以核实结果为准。'));
  const policy=data.policy||{};
  section.append(node('p',policy.notice_text||'当前告知内容尚未提供，不能记录已阅。'),node('p','告知版本：'+(policy.notice_version||'待核实')),
   node('p','保存规则：'+(policy.retention_policy||'待核实')+' · 期限依据：'+(policy.retention_period_ref||'待核实')));
  if(policy.notice_text&&policy.notice_ref&&policy.notice_sha256&&policy.consent_version&&policy.consent_scope){
   for(const [decision,label] of [['ACKNOWLEDGED','记录已阅此版本'],['DECLINED','记录暂不认可']]){
    const b=node('button',label);b.type='button';let key;
    b.onclick=async()=>{if(b.disabled)return;b.disabled=true;key ||= crypto.randomUUID();try{
     await api('privacy_acknowledge',{project:pid,policy_ref:policy.notice_ref,notice_sha256:policy.notice_sha256,decision,idempotency_key:key});
     notice('您的选择已留存；这不是法律合规认定。');if(generation===viewGeneration)await openPrivacy();
    }catch(e){notice(e.message);}finally{b.disabled=false;}};section.append(b);
   }
  }
  function requestForm(kind,requestId=null,revision=0){
   const f=node('form'),select=node('select'),text=node('textarea'),label=node('label','说明（请勿填写密码或密钥）'),submit=node('button',requestId?'提交补充说明':'提交个人申请');
   for(const [value,title] of [['QUERY','查询与说明'],['CORRECTION','更正申请'],['DELETION','删除申请']]){const o=node('option',title);o.value=value;select.append(o);}select.value=kind||'QUERY';select.disabled=!!requestId;
   text.required=true;text.maxLength=4000;label.append(text);f.append(select,label,submit);let key;
   f.onsubmit=async e=>{e.preventDefault();if(submit.disabled||!text.reportValidity())return;submit.disabled=true;key ||= crypto.randomUUID();try{
    await api('privacy_request',{project:pid,kind:select.value,text:text.value,idempotency_key:key,request_id:requestId,expected_revision:revision});
    notice('申请已收件，尚未执行更正或删除。');if(generation===viewGeneration)await openPrivacy();
   }catch(error){notice(error.message);}finally{submit.disabled=false;}};
   return f;
  }
  section.append(requestForm());
  const latest=new Map();
  for(const r of data.receipts||[]){
   if(r.type==='REQUEST')latest.set(r.request_id,r);
   else section.append(node('p','告知选择：'+(r.decision==='ACKNOWLEDGED'?'已记录已阅':'已记录暂不认可')+' · '+new Date(r.server_received_at*1000).toISOString()));
  }
  for(const r of latest.values()){
   const box=node('details');box.append(node('summary','个人申请 '+r.request_id+' · 版本 '+r.revision),node('p',r.text),node('p','已收件；此记录本身不表示已处理。'));
   const processing=(data.processing||[]).find(p=>p.request_id===r.request_id);
   if(processing)box.append(node('p','处理报告：'+({RECEIVED:'已收件',UNDER_REVIEW:'核实中',NEEDS_INFORMATION:'待补充',CLOSED:'处理方报告已结束',UNKNOWN:'待核实'}[processing.status]||'待核实')));
   box.append(requestForm(r.kind,r.request_id,r.revision));section.append(box);
  }
 }catch(error){if(!error.stale&&generation===viewGeneration)section.replaceChildren(node('p',error.message));}
}
