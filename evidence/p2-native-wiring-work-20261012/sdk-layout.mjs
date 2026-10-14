import path from 'node:path';
const hold=()=>{throw new Error('HOLD_SDK_WORKSPACE_LAYOUT');};
const absolute=value=>typeof value==='string'&&path.isAbsolute(value)&&path.normalize(value)===value&&value!=='/';
const scope=value=>absolute(value)&&/^workspace-[0-9a-f]{32}$/.test(path.basename(value));
/** Only the pinned SDK's two observed layouts; never accept caller mount lists. */
export function sandboxLayout(context,request,sessionKey,backend) {
  const access=request?.sandbox==='read-only'?'ro':request?.sandbox==='workspace-write'?'rw':null;
  if(!access||!absolute(request.workdir)||context?.enabled!==true
    ||context.sessionKey!==sessionKey||context.backendId!==backend
    ||!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(context.runtimeId??'')
    ||context.workspaceAccess!==access||context.agentWorkspaceDir!==request.workdir
    ||context.containerWorkdir!=='/workspace')hold();
  let extra;
  if(access==='ro') {
    if(!scope(context.workspaceDir)||context.workspaceDir===request.workdir
      ||context.skillsWorkspaceDir!==context.workspaceDir)hold();
    extra={Source:context.workspaceDir,Destination:'/workspace',RW:false};
  } else {
    const skills=context.skillsWorkspaceDir;
    if(context.workspaceDir!==request.workdir||!absolute(skills)
      ||path.basename(skills)!=='sandbox-skills'||path.basename(path.dirname(skills))!=='.openclaw'
      ||!scope(path.dirname(path.dirname(skills))))hold();
    extra={Source:path.join(skills,'skills'),Destination:'/workspace/.openclaw/sandbox-skills/skills',RW:false};
  }
  // No ancillary mount may disclose an ancestor, overlap, or sit inside the repository.
  if(extra.Source===request.workdir||extra.Source.startsWith(request.workdir+'/')
    ||request.workdir.startsWith(extra.Source+'/'))hold();
  return {schema:1,session_key:sessionKey,runtime_id:context.runtimeId,backend,
    workspace_access:access,mounts:[{Source:request.workdir,
      Destination:access==='ro'?'/agent':'/workspace',RW:access==='rw'},extra]};
}
export function verifySdkMounts(mounts,layout,workdir,sandbox) {
  const access=sandbox==='read-only'?'ro':sandbox==='workspace-write'?'rw':null;
  if(!access||layout?.schema!==1||layout.workspace_access!==access
    ||!Array.isArray(layout.mounts)||layout.mounts.length!==2
    ||layout.mounts[0].Source!==workdir||layout.mounts[0].RW!==(access==='rw')
    ||layout.mounts[0].Destination!==(access==='ro'?'/agent':'/workspace')
    ||layout.mounts[1].RW!==false||!Array.isArray(mounts)||mounts.length!==2)hold();
  const used=new Set();
  for(const expected of layout.mounts) {
    const index=mounts.findIndex((m,i)=>!used.has(i)&&m.Type==='bind'
      &&m.Source===expected.Source&&m.Destination===expected.Destination&&m.RW===expected.RW);
    if(index<0)hold();
    used.add(index);
  }
  return mounts.find(m=>m.Source===workdir);
}
