/* Read model adapter only. The caller supplies the original authorized source.
   Missing source is explicit; CI/task success never implies delivery. */
export function projectProjection(snapshot) {
  if(!snapshot)return {connected:false,developing:[],cases:[]};
  if(!Array.isArray(snapshot.projects))throw Error('项目来源格式不符');
  const developing=[],cases=[];
  for(const p of snapshot.projects){
    if(!p||typeof p.id!=='string'||typeof p.title!=='string')throw Error('项目主体缺失');
    // Completion and publication consent are separate original-source facts.
    const delivered=p.source_accepted===true||p.delivery?.accepted===true&&p.delivery?.live===true&&
      typeof p.delivery.acceptance_ref==='string'&&p.delivery.acceptance_ref.length>0&&
      typeof p.delivery.release_ref==='string'&&p.delivery.release_ref.length>0;
    if(!delivered&&p.phase==='ACCEPTED')continue; // Malformed acceptance stays held, never becomes developing.
    if(!delivered){developing.push({id:p.id,title:p.title,phase:p.phase||'待核实',runtime:p.runtime||'UNKNOWN',summary:p.summary,preview_url:p.preview_url,preview_access:p.preview_access,content_kind:p.content_kind,stage_connected:p.stage_connected});continue;}
    if(p.showcase?.approved===true&&p.showcase?.approval_ref&&Array.isArray(p.showcase.assets)){
      const safe=p.showcase.assets.filter(x=>x.public_approved===true&&['image','video','description','link'].includes(x.kind)&&typeof x.value==='string');
      if(safe.length)cases.push({id:p.id,title:p.title,assets:safe});
    }
    // Delivered projects without approved public assets are absent publicly;
    // this projection never deletes private records or feedback history.
  }
  return {connected:true,developing,cases};
}

// Public metadata only. This never asks for a customer session or publishes
// private Center records, and the display manager cannot write task stages.
export function previewUrl(value) {
  if(typeof value!=='string'||/[\s\\\u0000-\u001f]/.test(value))return null;
  try {
    const url=new URL(value,'https://wenwenwenyiyiyi.work');
    if(url.username||url.password||url.protocol!=='https:'||value.startsWith('//'))return null;
    if(value.startsWith('/')&&!value.startsWith('//'))return value;
    return value.startsWith('https://')?url.href:null;
  }catch{return null;}
}
export async function loadPublicDirectory(fetcher=fetch) {
  const get=async path=>{const response=await fetcher(path,{credentials:'omit',cache:'no-store',redirect:'error'});if(!response.ok)throw Error('目录读取失败：'+response.status);return response.json();};
  const [displayResult,stageResult]=await Promise.allSettled([
    get('/showcase/delivery/catalog.json'),get('/showcase/catalog.json')]);
  const display=displayResult.status==='fulfilled'?displayResult.value:null;
  const upstream=stageResult.status==='fulfilled'?stageResult.value:null;
  if(display && (display.schema!==1||display.source!=='SHOWCASE_CONTROLLED_DISPLAY_METADATA'||!Array.isArray(display.projects)))throw Error('展示目录来源格式不符');
  if(upstream && (upstream.schema!==1||!Array.isArray(upstream.projects)))throw Error('原项目目录来源格式不符');
  if(!display)throw Error('受控展示目录尚未接通；未回退到可能已下架的旧列表');
  const sources=new Map((upstream?.projects||[]).filter(p=>p.visibility==='PUBLIC').map(p=>[p.project_id,p]));
  const projects=[],seen=new Set();
  // These are the original compiler's verified, published snapshots, including
  // historical accepted versions. A state string or CI result alone is insufficient.
  const accepted=new Map((upstream?.cases||[]).filter(p=>p.visibility==='PUBLIC'&&p.state==='ACCEPTED'&&
    p.acceptance?.snapshot_sha256===p.snapshot_sha256&&p.acceptance?.project_version===p.version&&
    /^[a-f0-9]{64}$/.test(p.snapshot_sha256||'')&&p.pages?.length&&p.pages.every(page=>page.visibility==='PUBLIC'&&
      /^[a-f0-9]{64}$/.test(page.artifact_sha256||'')&&/^[a-f0-9]{64}$/.test(page.release_artifact_sha256||'')))
    .map(p=>[p.project_id,p]));
  const caseView=(item,original)=>({id:item.id,title:item.title,phase:'ACCEPTED',source_accepted:true,
    showcase:{approved:true,approval_ref:item.public_consent_ref,assets:(item.case_snapshot_sha256===original.snapshot_sha256?item.case_assets||[]:[]).filter(a=>a.public_consent_ref&&
      ['image','video','description','link'].includes(a.kind)&&typeof a.value==='string'&&(a.kind==='description'||previewUrl(a.value)))
      .map(a=>({...a,public_approved:true}))},accepted_version:original.version});

  for(const item of display?.projects||[]){
    if(item.visibility&&item.visibility!=='PUBLIC')throw Error('私有记录不得出现在公开目录');
    if(item.listed!==true||!item.public_consent_ref||typeof item.id!=='string'||typeof item.title!=='string'||!item.title||!previewUrl(item.preview_url))throw Error('公开展示记录不完整');
    if(seen.has(item.id))throw Error('重复展示记录');seen.add(item.id);
    const original=sources.get(item.source_project_id);
    projects.push({id:item.id,title:item.title,summary:item.summary||'',preview_url:item.preview_url,
      preview_access:item.preview_access,content_kind:item.content_kind,
      phase:original?.state||'项目阶段尚未接通',runtime:'UNKNOWN',stage_connected:!!original,
      source_accepted:original?.state==='ACCEPTED'&&accepted.get(item.source_project_id)?.snapshot_sha256===original.snapshot_sha256,
      delivery:original?.delivery,showcase:original?.showcase});
    const completed=accepted.get(item.source_project_id);
    if(completed){const caseItem=caseView(item,completed);const current=projects.at(-1);if(current.source_accepted)Object.assign(current,caseItem);else projects.push({...caseItem,id:item.id+'-accepted-v'+completed.version});}
  }
  // Every approved public project with an existing published page is eligible;
  // explicit managed unlisting overrides automatic discovery, without deletion.
  const managedIds=new Set((display?.projects||[]).map(p=>p.source_project_id));
  // Hidden entries are represented by IDs only, never private metadata.
  for(const id of display?.unlisted_project_ids||[])managedIds.add(id);
  for(const [id,p] of sources){
    if(managedIds.has(id)||seen.has(id))continue;
    const page=(p.pages||[]).find(page=>page.visibility==='PUBLIC'&&previewUrl(page.href));
    if(!page)continue;
    projects.push({id,title:p.title?.zh||p.title?.en||id,summary:p.summary?.zh||'',preview_url:page.href,
      preview_access:'UNVERIFIED',content_kind:'PUBLIC_PROJECT_PREVIEW',phase:p.state||'待核实',runtime:'UNKNOWN',
      stage_connected:true,source_accepted:p.state==='ACCEPTED'&&accepted.get(id)?.snapshot_sha256===p.snapshot_sha256,delivery:p.delivery,showcase:p.showcase});
  }
  return {projects,stage_connected:!!upstream,display_connected:!!display,revision:display?.revision??null};
}

// Shared card rendering for the host and the independent cases route.
export function renderCaseCards(container,cases){
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  container.replaceChildren(...cases.map(p=>{const card=node('article');card.className='card';card.append(node('h3',p.title));
    for(const item of p.assets){
      if(item.kind==='description'){card.append(node('p',item.value));continue;}
      const href=previewUrl(item.value);if(!href)continue;
      if(item.kind==='link'){const a=node('a','查看精选页面 →');a.href=href;a.target='_blank';a.rel='noopener noreferrer';card.append(a);continue;}
      const media=node(item.kind==='video'?'video':'img');media.src=href;media.style.maxWidth='100%';
      if(item.kind==='video'){media.controls=true;media.preload='metadata';}else{media.alt=p.title;media.loading='lazy';}card.append(media);
    }return card;}));
  if(!cases.length)container.append(node('p','暂无获准公开的精选案例。'));
}
