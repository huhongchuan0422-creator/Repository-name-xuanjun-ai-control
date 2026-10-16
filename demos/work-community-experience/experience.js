"use strict";
(()=>{
const $=id=>document.getElementById(id);
// Consumer navigation belongs to the consumer only. Device layout is responsive.
let ready=false,pending=false,busy=false,created=false,payRequested=false;
$('reference').value='mobile_'+crypto.randomUUID().replace(/-/g,'');
function screen(){const target=location.hash.slice(1)||'home';const valid=['home','store','checkout','result','orders'].includes(target)?target:'home';document.querySelectorAll('[data-screen]').forEach(s=>s.hidden=s.dataset.screen!==valid);document.querySelectorAll('.bottom-nav a').forEach(a=>{if(a.hash==='#'+valid)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});}
window.addEventListener('hashchange',screen);screen();
function buttons(){$('startOrder').disabled=!ready||busy||created;$('payOrder').disabled=!ready||busy||!pending;$('query').disabled=!ready||busy||!created;$('loadStorefront').disabled=!ready;}
function amount(){const value=$('yuan').value.trim();if(!/^(?:0|[1-9][0-9]{0,6})(?:\.[0-9]{1,2})?$/.test(value))throw Error('请输入最多两位小数的金额');const [whole,decimal='']=value.split('.');const minor=Number(whole)*100+Number(decimal.padEnd(2,'0'));if(!Number.isSafeInteger(minor)||minor<1||minor>100000000)throw Error('金额须在0.01至1,000,000元之间');return String(minor);}
$('yuan').addEventListener('input',()=>{pending=false;created=false;busy=false;payRequested=false;$('amount').value='';$('amount').dispatchEvent(new Event('input'));$('error').textContent='';$('resultSummary').textContent='金额已更改，请创建新的体验订单';$('reference').value='mobile_'+crypto.randomUUID().replace(/-/g,'');buttons();});
$('startOrder').addEventListener('click',()=>{try{$('amount').value=amount();$('amount').dispatchEvent(new Event('input'));$('error').textContent='';busy=true;buttons();$('create').click();}catch(e){$('error').textContent=e.message;}});
$('payOrder').addEventListener('click',()=>{if(!pending||busy||!ready)return;busy=true;payRequested=true;buttons();$('complete').click();});
new MutationObserver(()=>{const state=$('status').textContent;if(state.includes('：PENDING')){created=true;pending=true;busy=false;$('resultTitle').textContent='等待模拟付款';}else if(state.includes('：SUCCESS')){created=true;pending=false;busy=false;$('resultTitle').textContent='模拟付款已完成';$('resultSummary').textContent='仅模拟成功，不代表真实收款或结算。';$('orderNumber').textContent=$('reference').value;$('orderAmount').textContent='¥'+(Number($('amount').value)/100).toFixed(2);if(payRequested){payRequested=false;location.hash='result';}}else if(/：(?:FAILED|CANCELLED|REFUNDED)/.test(state)){pending=false;busy=false;created=true;$('resultTitle').textContent='当前订单尚未完成';$('resultSummary').textContent=state;}buttons();}).observe($('status'),{childList:true,subtree:true,characterData:true});
new MutationObserver(()=>{if($('error').textContent){busy=false;pending=false;payRequested=false;buttons();}}).observe($('error'),{childList:true,subtree:true,characterData:true});
buttons();fetch('/_preview/community-api/session',{credentials:'same-origin',cache:'no-store',redirect:'error'}).then(async r=>{if(r.status!==200)throw Error();const d=await r.json();if(d.simulation_only!==true||d.provider_connected!==false)throw Error();ready=true;$('sessionState').textContent='隔离模拟会话已就绪 · 无真实资金';buttons();}).catch(()=>{$('sessionState').textContent='交互服务暂不可用，请稍后重试；不会显示付款成功。';ready=false;buttons();});
})();
