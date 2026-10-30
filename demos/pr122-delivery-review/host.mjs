import {FeedbackClient} from './feedback-client.mjs';
import {projectProjection} from './project-projection.mjs';
const $=id=>document.getElementById(id),client=new FeedbackClient();let generation=0,bindings=null,current=null;
const node=(t,s)=>{const n=document.createElement(t);if(s!==undefined)n.textContent=s;return n;};
function catalog(){generation++;current=null;$('review').hidden=true;$('catalog').hidden=false;location.hash='developing';}
function openDemo(){generation++;$('catalog').hidden=true;$('review').hidden=false;$('template').src='community-next/#recommendations';location.hash='review';}
$('open-demo').onclick=openDemo;$('return-projects').onclick=catalog;
function fit(){const f=$('template'),d=f.contentDocument;if(!d?.body)return;f.style.height='1px';f.style.height=(Math.max(d.documentElement.scrollHeight,d.body.scrollHeight)+4)+'px';}
$('desktop-view').onclick=()=>{$('template').style.width='100%';requestAnimationFrame(fit);};
$('phone-view').onclick=()=>{$('template').style.width='390px';requestAnimationFrame(fit);};
addEventListener('hashchange',()=>{if(location.hash!=='#review'&&!$('review').hidden)catalog();});
async function sync(){
  const g=++generation;current=null;$('saved-feedback').hidden=true;
  const frame=$('template'),doc=frame.contentDocument,win=frame.contentWindow;if(!doc)return;
  requestAnimationFrame(fit);
  // Map host-only navigation in this isolated copy at runtime. Frozen files
  // remain byte-identical. No missing comparison page is invented.
  for(const a of doc.querySelectorAll('a[href*="website-original"]')){a.removeAttribute('href');a.textContent='现行UI对照原件尚未接入';a.setAttribute('aria-disabled','true');}
  const root=doc.querySelector('.review-header a');if(root){root.onclick=e=>{e.preventDefault();catalog();};root.textContent='← 开发中项目';}
  const view=(win.location.pathname.includes('/join/')?'join/':'')+(win.location.hash.slice(1)||'home');
  if(!bindings)return;
  const b=await bindings(view);if(g!==generation||!b)return;
  current={...b,view};$('saved-feedback').hidden=false;$('submit-feedback').disabled=false;$('feedback-status').textContent='正在核对本页历史…';
  try {const rows=await client.read(b);if(g!==generation)return;
    $('feedback-history').replaceChildren(...rows.map(c=>node('p',c.events[0].payload.request)));
    $('feedback-status').textContent=rows.length?'已读取本页原归档记录。':'本页尚无已归档意见。';
  }catch(e){if(g===generation){current=null;$('feedback-status').textContent='本页权限或版本尚未核实：'+e.message;$('submit-feedback').disabled=true;}}
}
$('template').onload=()=>{const win=$('template').contentWindow;win.addEventListener('hashchange',sync);win.document.querySelector('#scenario')?.addEventListener('change',sync);sync().catch(e=>$('feedback-status').textContent=e.message);};
$('submit-feedback').onclick=async()=>{
  if(!current)return;const b=current,g=generation,button=$('submit-feedback');if(button.disabled)return;
  button.disabled=true;try {
    const text=$('template').contentDocument.querySelector('#comment')?.value||'';
    const r=await client.submit(b,text);if(g!==generation)return;
    $('feedback-status').textContent=r.state==='SAVED'?'意见已归档，编号：'+r.id:'结果待确认；保留草稿，再次点击只核对原记录，不重复发送。';
    if(r.state==='SAVED')await sync();
  }catch(e){if(g===generation)$('feedback-status').textContent=e.message;}
  finally{button.disabled=false;}
};
// Existing host integration calls this with its authorized server projection
// and version registry. No public URL, query parameter or demo selector can
// assert a project's authority or claim real delivery.
export async function connectReviewHost({snapshotProvider,bindingProvider}) {
  bindings=bindingProvider||null;
  try {const data=projectProjection(await snapshotProvider());
    $('source-status').textContent=data.connected?'已读取原项目阶段；运行状态与交付验收分别显示。':'任务中心阶段尚未接通。';
    $('project-cards').replaceChildren(...data.developing.map(p=>{const a=node('article');a.className='card';a.append(node('h3',p.title),node('p',p.phase+' · '+p.runtime));return a;}));
    $('case-cards').replaceChildren(...data.cases.map(p=>{const a=node('article');a.className='card';a.append(node('h3',p.title));for(const item of p.assets){
      if(item.kind==='description'){a.append(node('p',item.value));continue;}
      // The source must supply explicitly public same-origin assets; private
      // account/project routes are never republished as case media.
      if(!/^\/showcase\/public\/[A-Za-z0-9/_\-.]+$/.test(item.value)||item.value.includes('..'))continue;
      const media=node(item.kind==='video'?'video':'img');media.src=item.value;if(item.kind==='video')media.controls=true;else media.alt=p.title;a.append(media);
    }return a;}));
    if(!data.cases.length)$('case-cards').append(node('p','暂无获准公开的精选案例。'));
  }catch(e){$('source-status').textContent='项目阶段暂未核实，未使用演示状态代替实际进度。';}
}
if(location.hash==='#review')openDemo();
