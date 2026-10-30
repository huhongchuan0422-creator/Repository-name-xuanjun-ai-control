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
    if(!delivered){developing.push({id:p.id,title:p.title,phase:p.phase||'待核实',runtime:p.runtime||'UNKNOWN'});continue;}
    if(p.showcase?.approved===true&&p.showcase?.approval_ref&&Array.isArray(p.showcase.assets)){
      const safe=p.showcase.assets.filter(x=>x.public_approved===true&&['image','video','description'].includes(x.kind)&&typeof x.value==='string');
      if(safe.length)cases.push({id:p.id,title:p.title,assets:safe});
    }
    // Delivered projects without approved public assets are absent publicly;
    // this projection never deletes private records or feedback history.
  }
  return {connected:true,developing,cases};
}
