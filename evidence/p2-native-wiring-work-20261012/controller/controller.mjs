import { createHash } from 'node:crypto';
import { canonical } from './canonical.mjs';
import { strictJson } from './strict-json.mjs';
import { verifySnapshot } from './workspace.mjs';

const fields=['task_id','spec_hash','lease','fence','epoch','generation','instance'];
const hold=reason=>{throw new Error('HOLD_'+reason);};
/** Gateway-owned handler. Bindings must be installed host adapters, never RPC params. */
export class NativeController {
  constructor({store,boundary,prepare,eligibility,collectResult,verifyLease,commitGuard,verifyWorkerPlacement,releaseWorkerPlacement,clock=Date.now}) {
    for(const fn of [prepare,eligibility,collectResult,verifyLease,commitGuard,verifyWorkerPlacement,releaseWorkerPlacement]) if(typeof fn!=='function')hold('HOST_BINDING_MISSING');
    this.store=store;this.boundary=boundary;this.prepare=prepare;
    this.eligibility=eligibility;this.collectResult=collectResult;
    this.verifyLease=verifyLease;this.commitGuard=commitGuard;this.verifyWorkerPlacement=verifyWorkerPlacement;this.releaseWorkerPlacement=releaseWorkerPlacement;this.clock=clock;
  }
  async current(request) {
    const observed=await this.store.read(request);
    if(fields.some(k=>observed.task[k]!==request[k]) || !await this.verifyLease(observed.task,request,this.clock()))hold('LEASE_OR_FENCE');
    return observed;
  }
  async admit(raw,key,runtime) {
    if(typeof raw!=='string'||Buffer.byteLength(raw)>262144 || !/^[0-9a-f]{64}$/.test(key??'')
      || createHash('sha256').update(raw).digest('hex')!==key)hold('REQUEST_HASH');
    const request=strictJson(raw,262144);
    if(request.provider!=='openai'||request.model!=='gpt-5.6-sol'
      || !['workspace-write','read-only'].includes(request.sandbox)
      || typeof request.prompt!=='string'||!Number.isSafeInteger(request.timeout_seconds)
      || request.timeout_seconds<1||request.timeout_seconds>3600)hold('REQUEST_POLICY');
    let observed=await this.current(request);
    const requestContract={spec_hash:request.spec_hash,workdir:request.workdir,sandbox:request.sandbox,
      provider:request.provider,model:request.model,prompt:request.prompt,timeout_seconds:request.timeout_seconds};
    if(!observed.task.request_contract
      ||canonical(observed.task.request_contract)!==canonical(requestContract))hold('REQUEST_CONTRACT');
    let previous=[];
    if(observed.task.native_execution) {
      const saved=observed.task.native_execution;
      if(saved.idempotency_key===key && canonical(saved.request)===canonical(request)) {
        if(!saved.admission||!['ADMITTED','LAUNCH_INTENT','RUNNING','TERMINAL'].includes(saved.phase))
          hold('EFFECT_RECONCILIATION_REQUIRED');
        return saved.admission;
      }
      if(saved.phase!=='TERMINAL'||!saved.report||saved.observation?.descendants_exited!==true
        ||saved.observation?.unit_active!==false||saved.observation?.process_alive!==false)hold('EXISTING_EXECUTION_REQUIRES_RECONCILIATION');
      previous=[...(saved.previous_receipts||[]),saved.report];
      if(previous.length>8)hold('EXECUTION_HISTORY_LIMIT');
    }
    if(await this.eligibility(runtime,request))hold('CLI_DISPATCH_BYPASS');
    const source=await verifySnapshot(observed.task.source_manifest,request.workdir);
    const sessionKey='agent:main:xuanjun-p2:'+key;
    // Persist intent before provisioning any physical execution boundary.
    observed=await this.store.replace(observed,{...observed.task,native_execution:{
      phase:'PROVISIONING',request,idempotency_key:key,session_key:sessionKey,source,previous_receipts:previous}});
    const unit=await this.prepare(runtime,{request,sessionKey,source,idempotencyKey:key});
    const bound=await this.boundary.bind(unit,request.workdir,[],request.sandbox);
    if(typeof this.boundary.attestSnapshot!=='function')hold('NAMESPACE_ATTESTATION_UNAVAILABLE');
    const namespace_attestation=await this.boundary.attestSnapshot(bound,source);
    if(!namespace_attestation||!/^[0-9a-f]{64}$/.test(namespace_attestation.namespace_sha256??''))
      hold('NAMESPACE_ATTESTATION');
    const admission={request,idempotency_key:key,isolation_enforced:true};
    const latest=await this.current(request);
    if(latest.task.native_execution?.phase!=='PROVISIONING'||latest.task.native_execution.idempotency_key!==key)hold('PROVISIONING_CAS');
    await this.store.replace(latest,{...latest.task,native_execution:{...latest.task.native_execution,
      phase:'ADMITTED',unit:bound,namespace_attestation,admission}});
    return admission;
  }
  async record(receipt,cleanup=false) {
    const binding=receipt.binding||receipt.request;
    const observed=await (cleanup?this.store.receipt(binding):this.store.read(binding)),record=observed.task.native_execution;
    if(!record||record.idempotency_key!==receipt.idempotency_key)hold('RECEIPT_UNKNOWN');
    const isAdmission=receipt?.request&&canonical(record.admission)===canonical(receipt);
    if(record.receipt&&!isAdmission&&canonical(record.receipt)!==canonical(receipt))hold('RECEIPT_MISMATCH');
    return {observed,record};
  }
  async launch(admission,runtime) {
    const {observed,record}=await this.record(admission);
    await this.current(record.request);
    if(canonical(record.admission)!==canonical(admission))hold('LAUNCH_REPLAY_FORBIDDEN');
    if(record.receipt && ['RUNNING','TERMINAL'].includes(record.phase))return record.receipt;
    if(record.phase==='LAUNCH_INTENT')hold('LAUNCH_EFFECT_UNKNOWN');
    if(record.phase!=='ADMITTED')hold('LAUNCH_REPLAY_FORBIDDEN');
    await verifySnapshot(observed.task.source_manifest,record.request.workdir);
    const boundary=await this.boundary.inspect(record.unit);
    if(!boundary.active||!boundary.process_alive)hold('BOUNDARY_NOT_ACTIVE');
    if(await this.eligibility(runtime,record.request))hold('CLI_DISPATCH_BYPASS');
    const executionBinding={admission:record.admission,idempotency_key:record.idempotency_key,
      session_key:record.session_key,unit:record.unit,source:record.source,request:record.request,
      namespace_attestation:record.namespace_attestation};
    const executionBindingDigest=createHash('sha256').update(canonical(executionBinding)).digest('hex');
    const placement=await this.verifyWorkerPlacement(runtime,{request:record.request,unit:record.unit,sessionKey:record.session_key,source:record.source});
    const requestDigest=createHash('sha256').update(canonical(record.request)).digest('hex');
    if(!placement || placement.verified!==true
      ||placement.session_key!==record.session_key
      ||placement.unit_backend!==record.unit.backend
      ||placement.unit_id!==record.unit.id
      ||placement.cgroup!==record.unit.cgroup
      ||placement.source_manifest_sha256!==record.source.manifest_sha256
      ||placement.request_sha256!==requestDigest
      ||placement.sandbox_runtime_id!==record.unit.name
      ||placement.namespace_sha256!==record.namespace_attestation?.namespace_sha256)
      hold('WORKER_PLACEMENT_UNVERIFIED');
    const latest=await this.current(record.request);
    const latestRecord=latest.task.native_execution;
    if(latestRecord?.phase!=='ADMITTED')hold('LAUNCH_STALE_ADMISSION');
    const latestBinding={admission:latestRecord.admission,idempotency_key:latestRecord.idempotency_key,
      session_key:latestRecord.session_key,unit:latestRecord.unit,source:latestRecord.source,
      request:latestRecord.request,namespace_attestation:latestRecord.namespace_attestation};
    if(createHash('sha256').update(canonical(latestBinding)).digest('hex')!==executionBindingDigest)
      hold('LAUNCH_EXECUTION_BINDING_CHANGED');
    const postSource=await verifySnapshot(latest.task.source_manifest,latestRecord.request.workdir);
    if(canonical(postSource)!==canonical(latestRecord.source))hold('LAUNCH_SOURCE_CHANGED');
    const postNamespace=await this.boundary.attestSnapshot(latestRecord.unit,postSource);
    if(!postNamespace
      ||postNamespace.namespace_sha256!==latestRecord.namespace_attestation?.namespace_sha256)
      hold('LAUNCH_NAMESPACE_CHANGED');
    const intentObserved=await this.store.replace(latest,{...latest.task,native_execution:{
      ...latestRecord,phase:'LAUNCH_INTENT',placement,execution_binding_sha256:executionBindingDigest}});
    return this.dispatchLaunch(intentObserved.task.native_execution,runtime);
  }
  async dispatchLaunch(record,runtime) {
    const request=record.request;
    const result=await runtime.subagent.run({sessionKey:record.session_key,message:request.prompt,
      provider:request.provider,model:request.model,cwd:request.workdir,
      idempotencyKey:record.idempotency_key,deliver:false,
      assertCurrent:()=>{const proof=this.commitGuard(request); if(proof!==true)hold('COMMIT_LEASE_OR_FENCE');}});
    return this.persistLaunch(record,result,runtime);
  }
  async persistLaunch(record,result,runtime) {
    if(!result?.runId||result.sessionKey!==record.session_key)hold('LAUNCH_UNKNOWN');
    const entry=await runtime.agent.session.getSessionEntry({sessionKey:record.session_key,agentId:'main',readConsistency:'latest'});
    if(!entry?.sessionId)hold('SESSION_ID_UNKNOWN');
    const receipt={binding:Object.fromEntries(fields.map(k=>[k,record.request[k]])),idempotency_key:record.idempotency_key,run_id:result.runId,session_id:entry.sessionId,execution_unit_id:record.unit.backend+':'+record.unit.id,placement_digest:createHash('sha256').update(canonical(record.placement)).digest('hex')};
    const latest=await this.current(record.request);
    const current=latest.task.native_execution;
    if(current?.receipt) {
      if(canonical(current.receipt)!==canonical(receipt)||!['RUNNING','TERMINAL'].includes(current.phase))hold('LAUNCH_CAS');
      return current.receipt;
    }
    if(current?.phase!=='LAUNCH_INTENT'||current.idempotency_key!==record.idempotency_key)hold('LAUNCH_CAS');
    await this.store.replace(latest,{...latest.task,native_execution:{...current,phase:'RUNNING',receipt,runtime:result.runtime}});
    return receipt;
  }
  async inspect(receipt,runtime) {
    const {observed,record}=await this.record(receipt);
    if(!record.receipt)hold('LAUNCH_EFFECT_UNKNOWN');
    if(record.phase==='TERMINAL'&&record.observation)return record.observation;
    const status=await runtime.subagent.waitForRun({runId:receipt.run_id,timeoutMs:1});
    if(!['ok','error','pending','timeout'].includes(status?.status))hold('RUN_STATE_UNKNOWN');
    let unit=await this.boundary.inspect(record.unit);
    const terminal=['ok','error'].includes(status.status);
    if(terminal&&unit.active)unit=await this.boundary.stop(record.unit);
    const state=terminal?(status.status==='ok'?'completed':'failed'):'running';
    const result={...receipt,state,process_alive:unit.process_alive,unit_active:unit.active,descendants_exited:unit.descendants_exited};
    if(terminal&&!unit.active&&!unit.process_alive&&unit.descendants_exited) {
      const latest=await this.store.read(record.request);
      if(canonical(latest.task.native_execution?.receipt)!==canonical(receipt))hold('TERMINAL_CAS');
      await this.store.replace(latest,{...latest.task,native_execution:{...latest.task.native_execution,phase:'TERMINAL',observation:result}});
      if(this.releaseWorkerPlacement(record.session_key)!==true)hold('RUN_ADMISSION_RELEASE');
    }
    return result;
  }
  async report(receipt,runtime) {
    const {observed,record}=await this.record(receipt);
    if(record.report)return record.report;
    if(record.phase!=='TERMINAL')hold('REPORT_BEFORE_STOP');
    // This adapter must use host metadata/artifact checks, never assistant JSON.
    const result=await this.collectResult(runtime,record);
    if(result?.provider!=='openai'||result.model!=='gpt-5.6-sol'||result.model_verified!==true)hold('OBSERVED_MODEL');
    const report={...receipt,request:record.request,result,durable_receipt_id:'canonical:'+record.idempotency_key};
    await this.store.replace(observed,{...observed.task,native_execution:{...record,report}});
    return report;
  }
  async stop(receipt,runtime) {
    const {record}=await this.record(receipt,true);
    if(record.phase==='TERMINAL'&&record.observation?.unit_active===false
      &&record.observation?.process_alive===false&&record.observation?.descendants_exited===true) {
      this.releaseWorkerPlacement(record.session_key);
      return record.observation;
    }
    // Session cancellation and physical stop are separate observations.
    // Always attempt the physical stop even if cancellation response is lost.
    let cancelled=false;
    try {
      await runtime.subagent.deleteSession({sessionKey:record.session_key,deleteTranscript:false});
      cancelled=true;
    } finally {
      await this.boundary.stop(record.unit);
    }
    if(!cancelled)hold('SESSION_CANCELLATION_UNKNOWN');
    const stopped=await this.boundary.inspect(record.unit);
    if(this.releaseWorkerPlacement(record.session_key)!==true)hold('RUN_ADMISSION_RELEASE');
    return stopped;
  }
}
