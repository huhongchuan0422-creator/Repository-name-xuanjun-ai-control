/* Read model adapter only. The caller supplies the original authorized source.
   Missing source is explicit; CI/task success never implies delivery. */
export function projectProjection(snapshot) {
  if(!snapshot)return {connected:false,developing:[],cases:[]};
  if(!Array.isArray(snapshot.projects))throw Error('项目来源格式不符');
  const developing=[],cases=[];
  for(const p of snapshot.projects){
    if(!p||typeof p.id!=='string'||typeof p.title!=='string')throw Error('项目主体缺失');
    // Completion and publication consent are separate original-source facts.
    const delivered=p.delivery?.accepted===true&&p.delivery?.live===true&&
      typeof p.delivery.acceptance_ref==='string'&&p.delivery.acceptance_ref.length>0&&
      typeof p.delivery.release_ref==='string'&&p.delivery.release_ref.length>0;
    if(!delivered){developing.push({id:p.id,title:p.title,phase:p.phase||'待核实',runtime:p.runtime||'UNKNOWN',summary:p.summary,preview_url:p.preview_url,preview_access:p.preview_access,content_kind:p.content_kind,stage_connected:p.stage_connected});continue;}
    if(p.showcase?.approved===true&&p.showcase?.approval_ref&&Array.isArray(p.showcase.assets)){
      const safe=p.showcase.assets.filter(x=>x.public_approved===true&&['image','video','description'].includes(x.kind)&&typeof x.value==='string');
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
  for(const item of display?.projects||[]){
    if(item.listed!==true||!item.public_consent_ref||typeof item.id!=='string'||typeof item.title!=='string'||!item.title||!previewUrl(item.preview_url))throw Error('公开展示记录不完整');
    if(seen.has(item.id))throw Error('重复展示记录');seen.add(item.id);
    const original=sources.get(item.source_project_id);
    projects.push({id:item.id,title:item.title,summary:item.summary||'',preview_url:item.preview_url,
      preview_access:item.preview_access,content_kind:item.content_kind,
      phase:original?.state||'项目阶段尚未接通',runtime:'UNKNOWN',stage_connected:!!original,
      delivery:original?.delivery,showcase:original?.showcase});
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
      stage_connected:true,delivery:p.delivery,showcase:p.showcase});
  }
  return {projects,stage_connected:!!upstream,display_connected:!!display,revision:display?.revision??null};
}
