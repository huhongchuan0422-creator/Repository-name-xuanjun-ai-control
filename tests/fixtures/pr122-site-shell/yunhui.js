(()=>{
'use strict';
const english=document.documentElement.lang.toLowerCase().startsWith('en');
const text=english?{open:'Contact us',title:'Talk about your business',desc:'Choose a contact channel.',close:'Close contact panel',tg:'Open Telegram',tgDesc:'Continue with XuanJunAI_ServiceBot.',feishu:'Feishu',pending:'Integration in progress',note:'The Feishu public entry will be available after verification.'}:{open:'联系玄钧',title:'聊聊你的业务需求',desc:'选择合适的沟通方式。',close:'关闭联系面板',tg:'进入 Telegram',tgDesc:'通过官方机器人继续沟通。',feishu:'飞书',pending:'正在接入',note:'飞书公开客服入口将在验证完成后提供。'};
const launcher=document.createElement('div');launcher.className='contact-launcher';launcher.innerHTML=`<button class="contact-open" type="button" aria-expanded="false" aria-controls="contact-panel">${text.open}</button><section class="contact-panel" id="contact-panel" hidden aria-label="${text.title}"><div class="contact-panel-head"><h2>${text.title}</h2><button type="button" class="contact-close" aria-label="${text.close}">×</button></div><p>${text.desc}</p><a class="contact-option" data-telegram-entry href="https://t.me/XuanJunAI_ServiceBot" rel="noopener"><b>${text.tg}</b><span>${text.tgDesc}</span></a><div class="contact-option pending"><b>${text.feishu}</b><span>${text.pending}</span></div><p class="fineprint">${text.note}</p></section>`;document.body.append(launcher);
const panel=launcher.querySelector('section'),opener=launcher.querySelector('.contact-open'),closer=launcher.querySelector('.contact-close');
function closeContact(){panel.hidden=true;opener.setAttribute('aria-expanded','false');}
opener.addEventListener('click',()=>{panel.hidden=!panel.hidden;opener.setAttribute('aria-expanded',String(!panel.hidden));if(!panel.hidden)closer.focus();});closer.addEventListener('click',()=>{closeContact();opener.focus();});
const qs=new URLSearchParams(location.search),raw=(qs.get('ref')||'').trim().toUpperCase();
const ref=/^[A-Z0-9][A-Z0-9_-]{2,39}$/.test(raw)?raw:'';
if(ref)document.querySelectorAll('[data-telegram-entry]').forEach(a=>a.href='https://t.me/XuanJunAI_ServiceBot?start='+encodeURIComponent(ref));
document.querySelectorAll('[data-preserve-route-context]').forEach(a=>{const u=new URL(a.href,location.origin);if(ref)u.searchParams.set('ref',ref);['utm_source','utm_medium','utm_campaign','utm_content','utm_term'].forEach(k=>{const v=qs.get(k);if(v&&v.length<=120)u.searchParams.set(k,v);});u.hash=location.hash;a.href=u.pathname+u.search+u.hash;});
const mobile=document.querySelector('.mobile-toggle'),nav=document.querySelector('.primary-nav'),language=document.querySelector('.language'),langButton=language?.querySelector('button');
function closeMenus(except){document.querySelectorAll('.nav-group.open,.language.open').forEach(group=>{if(group===except)return;group.classList.remove('open');group.querySelector('button')?.setAttribute('aria-expanded','false');});}
function toggle(group,button){const next=!group.classList.contains('open');closeMenus(group);group.classList.toggle('open',next);button.setAttribute('aria-expanded',String(next));}
if(mobile&&nav)mobile.addEventListener('click',()=>{const open=mobile.getAttribute('aria-expanded')==='true';mobile.setAttribute('aria-expanded',String(!open));nav.classList.toggle('open',!open);});
document.querySelectorAll('.nav-group>button').forEach(button=>button.addEventListener('click',()=>toggle(button.closest('.nav-group'),button)));
langButton?.addEventListener('click',()=>toggle(language,langButton));
document.addEventListener('click',event=>{if(!event.target.closest('.nav-group,.language'))closeMenus();});
document.addEventListener('keydown',event=>{if(event.key==='Escape'){const active=document.activeElement;const group=active?.closest('.nav-group,.language');closeMenus();if(group)group.querySelector('button')?.focus();nav?.classList.remove('open');mobile?.setAttribute('aria-expanded','false');if(!panel.hidden){closeContact();opener.focus();}}});
})();
(()=>{
 const input=document.querySelector('#site-search');if(!input)return;
 const english=document.documentElement.lang.startsWith('en'),results=document.querySelector('#search-results'),status=document.querySelector('#search-status');
 let records=[];
 function render(){const q=input.value.trim().toLocaleLowerCase();const found=records.filter(x=>!q||(x.title+' '+x.description).toLocaleLowerCase().includes(q));results.replaceChildren();found.forEach(x=>{const a=document.createElement('a');a.href=x.url;const strong=document.createElement('strong');strong.textContent=x.title;const p=document.createElement('p');p.textContent=x.description;a.append(strong,p);results.append(a);});status.textContent=english?`${found.length} results`:`找到 ${found.length} 项`;}
 input.addEventListener('input',render);
 fetch('/search-index.json',{cache:'no-cache'}).then(r=>{if(!r.ok)throw new Error('search unavailable');return r.json();}).then(data=>{records=data[english?'en':'zh-cn']||[];render();}).catch(()=>{status.textContent=english?'Search is unavailable. Please use navigation categories.':'搜索暂时不可用，请通过导航分类查找。';});
})();
