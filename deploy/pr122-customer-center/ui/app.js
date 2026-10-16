'use strict';
const base='/customer/center/api/';let csrf=sessionStorage.getItem('xj_csrf')||'',project='',role='';
const statusLabels={ARCHIVED:'已归档',PENDING:'待发送',ACCEPTED:'渠道已受理',UNKNOWN:'结果待确认',FAILED:'发送失败'};
const channelLabels={WEB:'网页项目沟通',WEB_AI:'网页AI客服',TELEGRAM:'Telegram客服',FEISHU:'飞书客服'};
const $=id=>document.getElementById(id),states={NOT_STARTED:'未开始',PARTIAL:'部分提交',SUBMITTED:'已提交',IN_REVIEW:'审核中',NEEDS_CORRECTION:'需要补正',ACCEPTED:'已通过'};
function node(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
function notice(text){$('notice').textContent=text;}
async function api(op,body){const r=await fetch(base+op,{credentials:'same-origin',method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-CSRF-Token':csrf}:{},body:body?JSON.stringify(body):undefined,cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.error||'请求未完成');return d;}
function form(id,fn){$(id).addEventListener('submit',async e=>{e.preventDefault();const button=e.submitter;if(button)button.disabled=true;try{await fn(Object.fromEntries(new FormData(e.target)));}catch(err){notice(err.message);}finally{if(button)button.disabled=false;}});}
async function start(){try{const d=await api('me');$('auth').hidden=true;$('workspace').hidden=false;$('logout').hidden=false;$('projects').replaceChildren();for(const p of d.projects){const b=node('button',p.title);b.addEventListener('click',()=>openProject(p));$('projects').append(b);}if(!d.projects.length)$('projects').append(node('p','尚无已授权项目。请联系项目负责人核实合同关系，或登录接受专属邀请。'));$('channel-status').replaceChildren(...['web_ai','telegram','feishu'].map(k=>{const v=d.channels[k];const name={web_ai:'网页AI客服',telegram:'Telegram客服',feishu:'飞书客服'}[k];return node('p',name+'：'+(v.state==='PENDING_CONNECTION'?'待接通':'已配置，待验收'));}));}catch{$('auth').hidden=false;$('workspace').hidden=true;$('logout').hidden=true;}}
form('login',async d=>{const r=await api('login',d);csrf=r.csrf;sessionStorage.setItem('xj_csrf',csrf);$('login').elements.password.value='';notice('已登录');await start();});
$('register').addEventListener('click',async()=>{try{await api('register',Object.fromEntries(new FormData($('login'))));notice('请查看验证邮箱。邮箱服务未接通时不会开放注册。');}catch(e){notice(e.message);}});
$('reset-request').addEventListener('click',async()=>{try{await api('request_reset',{email:$('login').elements.email.value});notice('请查看验证邮箱。');}catch(e){notice(e.message);}});
form('verification',async d=>{await api('verify',d);notice('邮箱已验证，请登录。');$('verification').reset();});
form('reset',async d=>{await api('reset',d);sessionStorage.removeItem('xj_csrf');csrf='';$('reset').reset();notice('密码已重置，旧会话已撤销。');await start();});
$('logout').addEventListener('click',async()=>{try{await api('logout',{});sessionStorage.removeItem('xj_csrf');csrf='';project='';window.location.reload();}catch(e){notice(e.message);}});
async function openProject(p){project=p.id;role=p.role;$('project').hidden=false;$('project-title').textContent=p.title;$('members').hidden=role!=='OWNER';await refresh();await refreshChanges();}
async function refresh(){try{const d=await api('checklist/'+encodeURIComponent(project));$('overall').textContent='整体状态：'+states[d.overall]+' · 清单版本 '+d.requirements_revision;$('materials').replaceChildren();for(const item of d.items)renderItem(item);const m=await api('messages/'+encodeURIComponent(project));$('messages').replaceChildren(...m.messages.map(x=>node('p',(channelLabels[x.channel]||'项目沟通')+' · '+(statusLabels[x.status]||'待确认')+'\n'+x.body)));const pending=await api('pending_links/'+encodeURIComponent(project));$('pending-links').replaceChildren(...pending.links.map(x=>{const div=node('div');div.append(node('p','确认绑定 '+x.channel+'：'+x.subject));const b=node('button','确认这是我的渠道账号');b.onclick=async()=>{try{await api('confirm_link',{project,challenge_id:x.id});notice('绑定已确认');await refresh();}catch(e){notice(e.message);}};div.append(b);return div;}));}catch(e){notice(e.message);}}
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
  card.append(node('h3',request.page),node('p',request.request),node('p','页面版本：'+request.page_sha256));
  const labels={REQUESTED:'待评估',NEEDS_EVIDENCE:'待补齐证据',QUOTED:'待客户确认报价',FREE_APPROVED:'评估为免费整改',CUSTOMER_CONFIRMED:'客户已确认',DISPUTED:'客户有异议'};
  card.append(node('p',labels[last.payload.state]||'处理中'));
  const assessment=[...events].reverse().find(e=>e.kind==='ASSESSMENT');
  if(assessment){const a=assessment.payload;card.append(node('p','预计工作量：'+a.estimated_minutes+'分钟'),node('p',a.explanation));
   const table=node('table'),head=node('tr');for(const title of ['整改项目','人民币','美元'])head.append(node('th',title));table.append(head);
   for(const line of a.lines){const row=node('tr');row.append(node('td',line.description),node('td','¥'+(line.cny_minor/100).toFixed(2)),node('td','US$'+(line.usd_minor/100).toFixed(2)));table.append(row);}card.append(table);
   card.append(node('p','合计：¥'+(a.totals.cny_minor/100).toFixed(2)+' / US$'+(a.totals.usd_minor/100).toFixed(2)));
   for(const e of a.evidence){const d=node('details');d.append(node('summary','查看此前确认的需求与证据'));d.append(node('p',e.requirement),node('p','确认时间：'+new Date(e.confirmed_at*1000).toISOString()),node('p','确认主体：'+e.actor),node('p','证据编号：'+e.event_id),node('p','证据SHA256：'+e.sha256));card.append(d);}
  }
  if(role==='OWNER'&&last.kind==='ASSESSMENT'&&['QUOTED','FREE_APPROVED'].includes(last.payload.state)){
   for(const [action,label] of [['CONFIRM','确认本次范围与费用'],['DISPUTE','提出异议']]){const b=node('button',label);b.type='button';b.addEventListener('click',async()=>{try{await api('change_respond',{project,case:item.id,revision:last.seq,action,reason:label});await refreshChanges();}catch(e){notice(e.message);}});card.append(b);}
  }$('change-list').append(card);
 }if(!$('change-list').children.length)$('change-list').append(node('p','暂无整改意见和费用。'));
 }catch(e){notice(e.message);}
}
form('change-request',async d=>{await api('change_submit',{project,...d});$('change-request').reset();notice('整改意见已归档，待工作量及范围评估。');await refreshChanges();});
start();
