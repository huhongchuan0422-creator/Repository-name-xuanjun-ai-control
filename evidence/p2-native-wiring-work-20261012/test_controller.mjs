import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {strictJson} from './controller/strict-json.mjs';
import {NativeController} from './controller/controller.mjs';
import {registerController} from './controller/index.mjs';
import {canonical} from './controller/canonical.mjs';
for(const raw of ['{"a":1,"a":2}','{"__proto__":{}}','1e999','9007199254740993','[1,]','{"a":1}x'])assert.throws(()=>strictJson(raw));
assert.equal(strictJson('{"a":[true,null,"中文"]}').a[2],'中文');
let calls=0;
const bindings={store:{read:async()=>({task:{}})},boundary:{},prepare:async()=>{},eligibility:async()=>false,collectResult:async()=>{},verifyLease:async()=>false,commitGuard:()=>false,verifyWorkerPlacement:async()=>null,releaseWorkerPlacement:()=>true};
assert.throws(()=>new NativeController({...bindings,commitGuard:undefined}),/HOST_BINDING/);
const controller=new NativeController(bindings);
await assert.rejects(()=>controller.admit('{}','0'.repeat(64),{}),/REQUEST_HASH/);
const raw=JSON.stringify({provider:'openai',model:'gpt-5.6-sol',sandbox:'workspace-write',prompt:'x',timeout_seconds:5});
await assert.rejects(()=>controller.admit(raw,createHash('sha256').update(raw).digest('hex'),{}),/LEASE_OR_FENCE/);
const handlers={};
registerController({runtime:{subagent:{run:()=>{calls++;},waitForRun:()=>{}}},registerGatewayMethod:(k,v)=>handlers[k]=v},bindings);
assert.equal(Object.keys(handlers).length,2);
let response;
await handlers['xuanjun.execution.start']({params:{operation:'launch'},client:{},respond:(...r)=>response=r});
assert.equal(response[0],false);assert.equal(response[2].message,'HOLD_ADMIN_REQUIRED');assert.equal(calls,0);
await handlers['xuanjun.execution.start']({params:{operation:'stop'},client:{connect:{scopes:['operator.admin']}},respond:(...r)=>response=r});
assert.equal(response[2].message,'HOLD_OPERATION');
console.log('controller validation: 12 assertions PASS; mocked/local only');
const receipt={idempotency_key:'a'.repeat(64),run_id:'run-1',session_id:'session-1',execution_unit_id:'docker:'+('b'.repeat(64))};
let task={native_execution:{phase:'RUNNING',receipt,idempotency_key:receipt.idempotency_key,request:{},unit:{}}};
let writes=0,stops=0;
const lifecycle=new NativeController({...bindings,
 store:{read:async()=>({task,revision:writes}),replace:async(o,next)=>{task=next;writes++;return {task,revision:writes};}},
 boundary:{inspect:async()=>({active:true,process_alive:true,descendants_exited:false}),stop:async()=>{stops++;return {active:false,process_alive:false,descendants_exited:true};}},
 collectResult:async()=>({provider:'openai',model:'gpt-5.6-sol',model_verified:true,ok:true})});
await assert.rejects(()=>lifecycle.report(receipt,{}),/REPORT_BEFORE_STOP/);
const observed=await lifecycle.inspect(receipt,{subagent:{waitForRun:async()=>({status:'ok'})}});
assert.equal(observed.state,'completed');assert.equal(observed.descendants_exited,true);assert.equal(stops,1);
const report=await lifecycle.report(receipt,{});
assert.equal(report.durable_receipt_id,'canonical:'+receipt.idempotency_key);
assert.equal(task.native_execution.report,report);
const writesBefore=writes;
assert.equal(await lifecycle.report(receipt,{}),report);assert.equal(writes,writesBefore);
await assert.rejects(()=>lifecycle.inspect({...receipt,run_id:'wrong'},{}),/RECEIPT_MISMATCH/);
// A timed-out wait must never become a successful terminal execution.
const pending=await lifecycle.inspect(receipt,{subagent:{waitForRun:async()=>({status:'timeout'})}});
assert.equal(pending.state,'running');
console.log('controller lifecycle: terminal stop, durable CAS, duplicate read, wrong identity, pending wait PASS (mock host)');
// Real file hashing + Git tree admission, with mock Gateway/OS boundary.
const {mkdtemp,writeFile,rm}=await import('node:fs/promises');
const os=await import('node:os');
const path=await import('node:path');
const dir=await mkdtemp(path.join(os.tmpdir(),'p2-controller-'));
try {
  const bytes=Buffer.from('approved source\n');await writeFile(path.join(dir,'main.py'),bytes,{mode:0o600});
  const blob=createHash('sha1').update(Buffer.from('blob '+bytes.length+'\0')).update(bytes).digest();
  const treeBytes=Buffer.concat([Buffer.from('100644 main.py\0'),blob]);
  const tree=createHash('sha1').update(Buffer.from('tree '+treeBytes.length+'\0')).update(treeBytes).digest('hex');
  const source={workdir:dir,commit:'c'.repeat(40),tree,files:[{path:'main.py',mode:'100644',sha256:createHash('sha256').update(bytes).digest('hex')}]};
  const request={task_id:'t',spec_hash:'a'.repeat(64),lease:'worker',fence:1,epoch:2,generation:1,instance:'instance',workdir:dir,sandbox:'workspace-write',provider:'openai',model:'gpt-5.6-sol',prompt:'approved',timeout_seconds:30};
  let current={...request,state:'RUNNING',lease_until:Date.now()/1000+60,source_manifest:source};
  let launchCalls=0,prepareCalls=0,leaseValid=true,unitStopped=false,placementValid=false;
  const store={read:async()=>({task:current}),receipt:async()=>({task:current}),replace:async(o,next)=>{assert.equal(o.task,current);current=next;return {task:current};}};
  const runtime={subagent:{run:async params=>{assert.equal(current.native_execution.phase,'LAUNCH_INTENT');params.assertCurrent();launchCalls++;return {runId:'run-real-files',sessionKey:params.sessionKey,runtime:{provider:'openai',model:'gpt-5.6-sol',harness:'embedded'}};}},agent:{session:{getSessionEntry:async()=>({sessionId:'session-real-files'})}}};
  const concrete=new NativeController({...bindings,store,
    prepare:async()=>{assert.equal(current.native_execution.phase,'PROVISIONING');prepareCalls++;return {backend:'docker',name:'unit'};},
    boundary:{bind:async unit=>({...unit,id:'d'.repeat(64),cgroup:'/sys/fs/cgroup/xuanjun-p2-test'}),inspect:async()=>({active:!unitStopped,process_alive:!unitStopped,descendants_exited:unitStopped}),stop:async()=>{unitStopped=true;return {active:false,process_alive:false,descendants_exited:true};}},
    verifyLease:async()=>leaseValid,commitGuard:()=>leaseValid,
    verifyWorkerPlacement:async(_runtime,{request,unit,sessionKey,source})=>placementValid?{
      verified:true,session_key:sessionKey,unit_backend:unit.backend,unit_id:unit.id,cgroup:unit.cgroup,
      source_manifest_sha256:source.manifest_sha256,
      request_sha256:createHash('sha256').update(canonical(request)).digest('hex')
    }:null});
  const raw=JSON.stringify(request),key=createHash('sha256').update(raw).digest('hex');
  const admission=await concrete.admit(raw,key,runtime);
  assert.equal(admission.isolation_enforced,true);assert.equal(prepareCalls,1);
  await concrete.admit(raw,key,runtime);assert.equal(prepareCalls,1);
  await assert.rejects(()=>concrete.launch(admission,runtime),/WORKER_PLACEMENT_UNVERIFIED/);
  assert.equal(launchCalls,0);
  assert.equal(current.native_execution.phase,'ADMITTED');
  placementValid=true;
  const launched=await concrete.launch(admission,runtime);
  assert.equal(launched.run_id,'run-real-files');assert.equal(launchCalls,1);
  await assert.rejects(()=>concrete.launch(admission,runtime),/RECEIPT_MISMATCH|LAUNCH_REPLAY/);
  leaseValid=false;
  // Stop uses persisted receipt even after the live claim is lost.
  assert.equal((await concrete.stop(launched,{subagent:{deleteSession:async()=>{}}})).descendants_exited,true);
  assert.equal(launchCalls,1);
  console.log('real snapshot admission / intent-before-effects / no duplicate launch / expired-lease stop PASS');
} finally {await rm(dir,{recursive:true,force:true});}

