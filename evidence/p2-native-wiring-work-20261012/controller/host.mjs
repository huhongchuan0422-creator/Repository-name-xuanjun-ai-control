import {CanonicalLedgerStore} from './ledger.mjs';
import {ContainerObserver} from './workspace.mjs';

const hold=reason=>{throw new Error('HOLD_'+reason);};
/** Concrete adapters using Gateway's injected SDK and pinned context resolver. */
export function createHostBindings(api,settings,resolveSandboxContext) {
  if(typeof resolveSandboxContext!=='function')hold('SANDBOX_CONTEXT_EXPORT');
  const store=new CanonicalLedgerStore(settings.ledger);
  const boundary=new ContainerObserver(settings.engine);
  const agentId=settings.agentId;
  if(agentId!=='main')hold('AGENT_POLICY');
  const config=()=>api.config;
  const eligibility=(runtime,request)=>{
    const cfg=config();
    if(!cfg||typeof runtime.agent?.resolveCliBackendDispatchEligibility!=='function')hold('DISPATCH_ELIGIBILITY_UNAVAILABLE');
    return runtime.agent.resolveCliBackendDispatchEligibility({config:cfg,agentId,
      agentDir:runtime.agent.resolveAgentDir(cfg,agentId),workspaceDir:request.workdir,
      provider:request.provider,model:request.model});
  };
  const prepare=async(runtime,{request,sessionKey})=>{
    const cfg=config();
    const authority=runtime.sandbox.resolveWorkspaceAuthority({config:cfg,agentId,sessionKey,
      workspaceDir:request.workdir,modelProvider:request.provider,modelId:request.model});
    if(authority?.sandboxed!==true||authority.confinementError)hold('SANDBOX_AUTHORITY');
    const context=await resolveSandboxContext({config:cfg,agentId,sessionKey,
      workspaceDir:request.workdir,requireCurrentConfig:true,
      assertCurrent:()=>{if(!store.guard(request))hold('PREPARE_LEASE');}});
    if(context?.enabled!==true||context.sessionKey!==sessionKey||context.workspaceDir!==request.workdir
      ||context.backendId!==settings.engine.backend||typeof context.runtimeId!=='string'
      ||context.workspaceAccess!==(request.sandbox==='read-only'?'ro':'rw'))hold('SANDBOX_CONTEXT_BINDING');
    return {backend:context.backendId,name:context.runtimeId};
  };
  const collectResult=async(runtime,record)=>{
    if(record.phase!=='TERMINAL'||record.observation?.state!=='completed')hold('RUN_NOT_COMPLETED');
    const entry=await runtime.agent.session.getSessionEntry({sessionKey:record.session_key,agentId,readConsistency:'latest'});
    if(entry?.sessionId!==record.receipt.session_id)hold('RESULT_SESSION');
    if(record.runtime?.provider!=='openai'||record.runtime.model!=='gpt-5.6-sol')hold('RESULT_RUNTIME_MODEL');
    const response=await runtime.subagent.getSessionMessages({sessionKey:record.session_key,limit:200});
    if(!Array.isArray(response?.messages))hold('TRANSCRIPT_UNAVAILABLE');
    const messages=response.messages.filter(m=>m?.role==='assistant');
    const final=messages.at(-1);
    // Model identity is transport metadata, never text authored by the model.
    if(!final||messages.some(m=>m.provider!=='openai'||m.model!=='gpt-5.6-sol')
      ||!['stop','end_turn'].includes(final.stopReason)||!Array.isArray(final.content))hold('TRANSCRIPT_MODEL_OR_COMPLETION');
    const output=final.content.filter(c=>c.type==='text'&&typeof c.text==='string').map(c=>c.text).join('\n');
    if(Buffer.byteLength(output)>65536)hold('RESULT_LIMIT');
    return {status:'COMPLETED',turn_completed:true,provider:final.provider,model:final.model,
      requested_model:record.request.model,model_verified:true,real_execution:true,
      simulated:false,output};
  };
  const preflight=async runtime=>{
    // Physical provision and active canonical claim are checked at admission.
    // Preflight cannot manufacture an active task to obtain a green flag.
    if(!runtime.subagent?.run||!runtime.subagent.waitForRun||!runtime.sandbox?.resolveWorkspaceAuthority
      ||!runtime.agent?.session?.getSessionEntry)hold('GATEWAY_SDK');
    const observed=store.call('preflight',null);
    const cfg=config(),selected=cfg?.agents?.defaults?.model;
    const profile=cfg?.auth?.profiles?.[settings.authProfileId];
    if(selected?.primary!=='openai/gpt-5.6-sol'||!Array.isArray(selected.fallbacks)
      ||selected.fallbacks.length||profile?.provider!=='openai'||profile.mode!=='oauth')hold('OAUTH_MODEL_POLICY');
    const request={workdir:settings.workspaceRoot,provider:'openai',model:'gpt-5.6-sol'};
    if(eligibility(runtime,request))hold('OAUTH_CLI_DISPATCH_BYPASS');
    const authority=runtime.sandbox.resolveWorkspaceAuthority({config:cfg,agentId,
      sessionKey:'agent:main:xuanjun-p2:verify-only',workspaceDir:settings.workspaceRoot,
      modelProvider:'openai',modelId:'gpt-5.6-sol'});
    if(authority?.sandboxed!==true||authority.confinementError)hold('SANDBOX_AUTHORITY');
    const version=(await boundary.command(['version','--format','{{.Server.Version}}'])).trim();
    if(!version||version.length>64)hold('ENGINE_UNAVAILABLE');
    if(observed.canonical_existing!==true||observed.outbox_existing!==true)hold('CANONICAL_PREFLIGHT');
    return {ready:true,canonical_existing:true,outbox_existing:true,isolation_enforced:true};
  };
  return {store,boundary,eligibility,prepare,collectResult,preflight,
    verifyLease:(task,request,now)=>task.state==='RUNNING'&&Number.isFinite(task.lease_until)&&task.lease_until*1000>now,
    commitGuard:request=>store.guard(request)};
}
