/** New affected sequencing contracts only. SDK/auth/drain owner remain UNBOUND. */
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {mkdtempSync,rmSync} from 'node:fs';import {tmpdir} from 'node:os';import {join} from 'node:path';
import {closeThenDrainOwnedWs,withPublicWsContract} from '../../production/p2_install/b5_ws_public_contract.mjs';
import {PLUGIN,READONLY_PROFILE,digest,appendRecord,readRecords} from '../../production/p2_install/b5_loader_contract.mjs';
import {METHOD} from '../../production/p2_install/b5_combined_contract.mjs';
let cases=0;
for(const mode of ['normal','already-aborted','close-throws','close-returns-false','close-returns-object','drain-throws','drain-false']){
 const events=[],socket=new EventEmitter(),signal=new AbortController();if(mode==='already-aborted')signal.abort();
 let registrationCalls=0,finish;const gate=new Promise(resolve=>{finish=resolve;});
 const work={signal:signal.signal,isClosing:true,track:()=>{throw Error('must not replace tracker');},trackCleanup:()=>{throw Error('native owner only');},registerConnection:()=>{registrationCalls++;}};
 const params={socket,connectionWork:work,close:()=>{events.push('close');if(mode==='close-throws')throw Error('close');if(mode==='close-returns-false')return false;if(mode==='close-returns-object')return {state:'PASS'};}};
 const operation=closeThenDrainOwnedWs({params,quiesceAndDrain:async refs=>{
  assert.equal(refs.socket,socket);assert.equal(refs.connectionWork,work);events.push('drain-start');await gate;events.push('cleanup-settled');if(mode==='drain-throws')throw Error('drain');if(mode==='drain-false')return false;
 }});
 await new Promise(resolve=>setImmediate(resolve));assert.deepEqual(events,['close','drain-start']);finish();
 if(['normal','already-aborted'].includes(mode))await operation;else await assert.rejects(operation,/HOLD_WS_CLOSE_OR_DRAIN_UNKNOWN/);
 assert.equal(registrationCalls,0);assert.equal(params.connectionWork,work);assert.equal(work.signal,signal.signal);assert.equal(events.at(-1),'cleanup-settled');cases++;
}
// Focused actual adapter/journal integration: native close -> asynchronous cleanup ->
// registration retirement -> drain -> lease release; retained guard cannot admit.
for(const closeFails of [false,true]){
 const dir=mkdtempSync(join(tmpdir(),'b5-close-order-'));const events=[],socket=new EventEmitter();let stale,completeCleanup,release=0;
 const cleanup=new Promise(resolve=>{completeCleanup=resolve;});const signal=new AbortController();
 const work=Object.freeze({signal:signal.signal,isClosing:false,track:fn=>Promise.resolve().then(fn),trackCleanup:fn=>Promise.resolve().then(fn),registerConnection:()=>()=>{}});
 const handler=()=>{};const source='/isolated/plugin.mjs';
 const registry={plugins:[{id:PLUGIN,source,version:READONLY_PROFILE.version,status:'loaded',enabled:true,imported:true,activated:false}],diagnostics:[],gatewayHandlers:{[METHOD]:handler},gatewayMethodDescriptors:[{name:METHOD,handler,scope:'operator.admin',owner:{kind:'plugin',pluginId:PLUGIN},profileAccess:'required'}]};
 const api={createPluginGatewayMethodDescriptors:r=>r.gatewayMethodDescriptors,createGatewayMethodRegistry:(ds,r)=>({pluginRegistry:r,getHandler:()=>handler,getScope:()=> 'operator.admin',listMethods:()=>[METHOD],requiresAuthenticatedProfile:()=>true,isControlPlaneWrite:()=>false,descriptors:()=>ds})};
 const declaration={plugin_id:PLUGIN,plugin_version:READONLY_PROFILE.version,declared_capabilities:[{method:METHOD,operation:'describe',read_only:true,required_scope:'operator.admin'}]};
 const payload={...declaration,plugin_source_sha256:'848b0b77df2ee65394c810de8aea40402abc0cf46e8d1eb66a014f2890eedba9',declaration_sha256:digest(declaration)};
 const params={socket,connectionWork:work,getClient:()=>null,buildRequestContext:()=>null,isClosed:()=>false,send:()=>({kind:'sent'}),close:()=>{
  assert.equal(socket.listenerCount('message'),0);events.push('close');
  work.trackCleanup(async()=>{await cleanup;await new Promise(resolve=>setImmediate(resolve));events.push('cleanup');events.push('releaseConnection');});
  if(closeFails)throw Error('native-close-unknown');
 }};
 const versions={binding:'b'.repeat(64),node:'c'.repeat(64),plugin:'d'.repeat(64),sdk:'e'.repeat(64)};const identity='a'.repeat(64);
 const operation=withPublicWsContract({acquire:async()=>({registry,release:async()=>{events.push('lease-release');release++;}}),registryApi:api,attach:p=>{
  const receive=data=>{const f=JSON.parse(data);p.send({type:'res',id:f.id,ok:true,payload});};socket.on('message',receive);return receive;
 },params,expectedSource:source,record:phase=>appendRecord(dir,identity,phase,versions),runTransportOwner:async()=>{
  stale=socket.listeners('message')[0];socket.emit('message',JSON.stringify({type:'req',id:'one',method:METHOD,params:{operation:'describe'}}));
 },quiesceAndDrain:async refs=>{
  assert.equal(refs.connectionWork,work);events.push('drain-start');assert.throws(()=>stale('retained'),/INGRESS_CLOSED/);await cleanup;await new Promise(resolve=>setImmediate(resolve));await new Promise(resolve=>setImmediate(resolve));events.push('drain-finished');
 }});
 try{
  await new Promise(resolve=>setImmediate(resolve));assert.equal(release,0);assert.deepEqual(events,['close','drain-start']);completeCleanup();
  if(closeFails){await assert.rejects(operation,/HOLD_INSPECTION_RELEASE_OR_RECORD_UNKNOWN/);assert.equal(release,0);assert.ok(!readRecords(dir,identity).some(x=>x.phase==='RELEASED'||x.phase==='OBSERVED'));}
  else{const result=await operation;assert.equal(result.executionReadiness,'HOLD_REAL_OWNER_UNBOUND');assert.equal(release,1);assert.ok(events.indexOf('releaseConnection')<events.indexOf('drain-finished'));assert.ok(events.indexOf('drain-finished')<events.indexOf('lease-release'));}
  assert.throws(()=>stale('retained'),/INGRESS_CLOSED/);cases++;
 }finally{rmSync(dir,{recursive:true,force:true});}
}
console.log(JSON.stringify({new_affected_cases:cases,old_twenty:'NOT_RERUN',scope:'CONTRACT_ONLY',real_owner:'UNBOUND',sdk:'NOT_EXECUTED'}));
