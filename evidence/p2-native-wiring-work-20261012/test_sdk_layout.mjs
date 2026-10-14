import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const root=process.env.P2_SOURCE_ROOT;
if(!root)throw Error('P2_SOURCE_ROOT_REQUIRED');
const base=root+'/plugins/p2-native-controller/';
const {sandboxLayout,verifySdkMounts}=await import(pathToFileURL(base+'sdk-layout.mjs'));
const {createHostBindings}=await import(pathToFileURL(base+'host.mjs'));
const {digest}=await import(pathToFileURL(base+'canonical.mjs'));
let checks=0;
const check=fn=>{fn();checks++;};
const session='agent:platform-engineer:xuanjun-p2:'+'a'.repeat(64);
const request={sandbox:'read-only',workdir:'/snapshots/repo'};
const scratch='/private/sandbox-workspaces/workspace-'+'b'.repeat(32);
const context={enabled:true,sessionKey:session,backendId:'docker',runtimeId:'fixture-unit',
  workspaceAccess:'ro',agentWorkspaceDir:request.workdir,workspaceDir:scratch,
  skillsWorkspaceDir:scratch,containerWorkdir:'/workspace'};
const ro=sandboxLayout(context,request,session,'docker');
const mounts=ro.mounts.map(m=>({...m,Type:'bind'}));
check(()=>assert.equal(verifySdkMounts(mounts,ro,request.workdir,'read-only').Destination,'/agent'));
check(()=>assert.equal(verifySdkMounts([...mounts].reverse(),ro,request.workdir,'read-only').RW,false));
for(const patch of [{agentWorkspaceDir:'/wrong'},{workspaceDir:request.workdir},
  {skillsWorkspaceDir:'/wrong'},{workspaceAccess:'rw'},{sessionKey:'wrong'},
  {runtimeId:'../unit'},{backendId:'podman'},{containerWorkdir:'/else'},
  {workspaceDir:'/private',skillsWorkspaceDir:'/private'},
  {workspaceDir:scratch+'/..',skillsWorkspaceDir:scratch+'/..'}])
  check(()=>assert.throws(()=>sandboxLayout({...context,...patch},request,session,'docker'),/HOLD_/));
for(const changed of [[{...mounts[0],RW:true},mounts[1]],
  [mounts[0],{...mounts[1],RW:true}],
  [mounts[0],{...mounts[1],Source:scratch+'/child'}],
  [{...mounts[0],Destination:'/workspace'},mounts[1]],
  [mounts[0],{...mounts[1],Type:'volume'}],
  [...mounts,{Type:'bind',Source:'/credentials',Destination:'/leak',RW:false}],
  [mounts[0],mounts[0]],[mounts[0]]])
  check(()=>assert.throws(()=>verifySdkMounts(changed,ro,request.workdir,'read-only'),/HOLD_/));
const rwRequest={...request,sandbox:'workspace-write'};
const rwContext={...context,workspaceAccess:'rw',workspaceDir:request.workdir,
  skillsWorkspaceDir:'/private/state/sandbox/skills-workspaces/workspace-'+'c'.repeat(32)+'/.openclaw/sandbox-skills'};
const rw=sandboxLayout(rwContext,rwRequest,session,'docker');
check(()=>assert.equal(verifySdkMounts(rw.mounts.map(m=>({...m,Type:'bind'})),rw,request.workdir,'workspace-write').RW,true));
check(()=>assert.throws(()=>sandboxLayout({...rwContext,skillsWorkspaceDir:'/credentials'},rwRequest,session,'docker'),/HOLD_/));
check(()=>assert.throws(()=>sandboxLayout(context,{...request,workdir:'/private'},session,'docker'),/HOLD_/));
const runtime={config:{current:()=>({})},sandbox:{
  resolveWorkspaceAuthority:()=>({sandboxed:true,workspaceAccess:'ro'}),
  prepareWorkspaceAuthority:async()=>({sandboxed:true,workspaceAccess:'ro'})}};
let live=context;
const bindings=createHostBindings({runtime},{agentIds:{'workspace-write':'developer','read-only':'platform-engineer'},
  engine:{backend:'docker',binary:'/usr/bin/docker'},
  ledger:{python:'/usr/bin/python3',bridge:'/bridge',config:'/config',files:{'/bridge':'a','/config':'b'}}},async()=>live);
bindings.store.guard=()=>true;
const unit=await bindings.prepare(runtime,{request,sessionKey:session});
check(()=>assert.deepEqual(unit.sdk_layout,ro));
const placement={sandbox_runtime_id:unit.name};
let saved={phase:'RUNNING',idempotency_key:'a'.repeat(64),session_key:session,agent_id:'platform-engineer',request,unit,placement,
  receipt:{run_id:'fixture-run',placement_digest:digest(placement)}};
bindings.store.call=()=>({native_execution:saved});
bindings.boundary.inspect=async()=>({active:true,process_alive:true});
bindings.boundary.attestSnapshot=async()=>({namespace_sha256:'d'.repeat(64)});
assert.equal((await bindings.verifyWorkerPlacement(runtime,{request,unit,sessionKey:session,source:{manifest_sha256:'f'.repeat(64)}})).verified,true);checks++;
assert.equal(await bindings.beforeToolCall({toolName:'read',params:{},runId:'fixture-run'},{sessionKey:session}),undefined);checks++;
assert.equal((await bindings.beforeToolCall({toolName:'write',params:{},runId:'fixture-run'},{sessionKey:session})).block,true);checks++;
live={...context,workspaceDir:scratch.replace(/b/g,'e'),skillsWorkspaceDir:scratch.replace(/b/g,'e')};
assert.equal((await bindings.beforeToolCall({toolName:'read',params:{},runId:'fixture-run'},{sessionKey:session})).block,true);checks++;
assert.equal(await bindings.verifyWorkerPlacement(runtime,{request,unit,sessionKey:session,source:{}}),null);checks++;
live=context;
saved={...saved,unit:{...unit,sdk_layout:undefined}};
assert.equal((await bindings.beforeToolCall({toolName:'read',params:{},runId:'fixture-run'},{sessionKey:session})).block,true);checks++;
assert.equal((await bindings.beforeToolCall({toolName:'read',params:{},runId:'wrong-run'},{sessionKey:session})).block,true);checks++;
console.log('SDK_LAYOUT_REGRESSIONS='+checks+' PASS; MODEL_CALLS=0; INSTALL=NO');
