import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {strictJson} from './controller/strict-json.mjs';
import {NativeController} from './controller/controller.mjs';
import {registerController} from './controller/index.mjs';
for(const raw of ['{"a":1,"a":2}','{"__proto__":{}}','1e999','9007199254740993','[1,]','{"a":1}x'])assert.throws(()=>strictJson(raw));
assert.equal(strictJson('{"a":[true,null,"中文"]}').a[2],'中文');
let calls=0;
const bindings={store:{read:async()=>({task:{}})},boundary:{},prepare:async()=>{},eligibility:async()=>false,collectResult:async()=>{},verifyLease:async()=>false,commitGuard:()=>false};
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
