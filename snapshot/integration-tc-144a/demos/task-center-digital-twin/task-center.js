(function(){'use strict';
function el(id){return document.getElementById(id);}
function esc(v){return String(v==null?'UNKNOWN':v).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function cookie(name){var prefix=name+'=';return document.cookie.split(';').map(function(x){return x.trim();}).filter(function(x){return x.indexOf(prefix)===0;}).map(function(x){return decodeURIComponent(x.slice(prefix.length));})[0]||'';}
function load(){fetch('api/public-projection',{cache:'no-store',credentials:'same-origin'}).then(function(r){return r.json().then(function(x){if(!r.ok)throw Error(x.error||('HTTP '+r.status));return x;});}).then(function(p){paint(p);}).catch(function(e){el('dataMode').textContent='加载失败';el('app').innerHTML='<p class="empty">数据加载失败：'+esc(e.message)+'</p>';});}
function paint(p){el('dataMode').textContent=esc(p.mode)+' · '+esc(p.production_status)+' · 观察 '+esc(p.observed_at);
var boards=(p.boards||[]).map(function(b){return '<div class="card board-card"><h3>'+esc(b.board_id)+'</h3><div class="metric">'+esc(b.task_count)+'</div><div class="meta">活跃 '+esc(b.active_count)+' · 阻塞 '+esc(b.blocked_count)+'</div><span class="status '+esc(b.health)+'">'+esc(b.health)+'</span></div>';}).join('');
el('app').innerHTML='<section class="grid">'+(boards||'<p class="empty">暂无板块数据。</p>')+'</section>';}
// The full workbench uses the existing admin-only twin projection.
fetch('api/session',{cache:'no-store',credentials:'same-origin'}).then(function(r){if(!r.ok)throw Error('session unavailable');return r.json();}).then(function(s){if(Array.isArray(s.roles)&&s.roles.indexOf('TASK_CENTER_ADMIN')!==-1)el('researchEntry').hidden=false;}).catch(function(){});
el('reload').onclick=load;
el('logout').onclick=function(){fetch('api/session/logout',{method:'POST',credentials:'same-origin',headers:{'X-CSRF-Token':cookie('xuanjun_task_center_csrf')}}).then(function(r){return r.json().catch(function(){return {};}).then(function(x){if(r.ok||r.status===401){location.replace('login.html');return;}throw Error(x.error||('HTTP '+r.status));});}).catch(function(e){el('dataMode').textContent='退出未成功：'+e.message;});};
load();})();
