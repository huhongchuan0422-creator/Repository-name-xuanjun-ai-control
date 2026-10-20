/** SDK APIs/transport are fixtures. No SDK import/evaluation or authentication claim. */
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';import {join} from 'node:path';
import {inspectionMethodRegistry,inspectionDispatcherParams,readonlyRequestFrame,withInspectionDispatcherContract,COMPILED_DISPATCH_BINDING} from '../../production/p2_install/b5_dispatch_registry_contract.mjs';
import {PLUGIN,READONLY_PROFILE,appendRecord,readRecords,recovery,digest} from '../../production/p2_install/b5_loader_contract.mjs';
import {METHOD} from '../../production/p2_install/b5_combined_contract.mjs';
const source='/isolated/plugin.mjs',identity='a'.repeat(64),versions={binding:'b'.repeat(64),node:'c'.repeat(64),plugin:'d'.repeat(64),sdk:'e'.repeat(64)};
const registry=()=>{const handler=()=>{};return {plugins:[{id:PLUGIN,source,version:READONLY_PROFILE.version,status:'loaded',enabled:true,imported:true,activated:false}],diagnostics:[],gatewayHandlers:{[METHOD]:handler},gatewayMethodDescriptors:[{name:METHOD,handler,scope:'operator.admin',owner:{kind:'plugin',pluginId:PLUGIN},profileAccess:'required'}]};};
const api={createPluginGatewayMethodDescriptors:r=>r.gatewayMethodDescriptors,createGatewayMethodRegistry:(ds,r)=>({pluginRegistry:r,getHandler:n=>ds.find(d=>d.name===n)?.handler,getScope:n=>ds.find(d=>d.name===n)?.scope,listMethods:()=>ds.map(d=>d.name),requiresAuthenticatedProfile:n=>ds.find(d=>d.name===n)?.profileAccess==='required',isControlPlaneWrite:()=>false,descriptors:()=>ds})};
const params=()=>({isWebchatConnect:()=>false,handler:{buildRequestContext:()=>{},send:()=>{},close:()=>{},isClosed:()=>false,getMethodRegistry:()=>null}});
const declaration={plugin_id:PLUGIN,plugin_version:READONLY_PROFILE.version,declared_capabilities:[{method:METHOD,operation:'describe',read_only:true,required_scope:'operator.admin'}]};
const metadata={...declaration,plugin_source_sha256:'848b0b77df2ee65394c810de8aea40402abc0cf46e8d1eb66a014f2890eedba9',declaration_sha256:digest(declaration)};
const frame=()=>({type:'req',id:'test',method:METHOD,params:{operation:'describe'},expectedProfileId:'owner-bound-profile'});
let count=0;
for(const mutation of [r=>r.gatewayMethodDescriptors[0].scope='operator.read',r=>r.gatewayMethodDescriptors[0].owner.pluginId='unknown',r=>r.gatewayMethodDescriptors[0].profileAccess='independent',r=>r.gatewayMethodDescriptors[0].handler=()=>{},r=>r.gatewayMethodDescriptors.push({...r.gatewayMethodDescriptors[0]})]){
 const r=registry();mutation(r);assert.throws(()=>inspectionMethodRegistry({registryApi:api,registry:r,expectedSource:source}),/HOLD_METHOD_DESCRIPTOR/);count++;
}
{
 const r=registry(),mr=inspectionMethodRegistry({registryApi:api,registry:r,expectedSource:source}),p=params(),old=p.handler.getMethodRegistry;
 const wired=inspectionDispatcherParams({params:p,methodRegistry:mr});assert.equal(wired.handler.getMethodRegistry(),mr);assert.equal(mr.pluginRegistry,r);assert.equal(p.handler.getMethodRegistry,old);assert.equal(wired.handler.buildRequestContext,p.handler.buildRequestContext);assert.equal(wired.isWebchatConnect,p.isWebchatConnect);count++;
 for(const key of ['client','connect','scopes','authPolicy','authenticated','expectedProfileBinding'])assert.throws(()=>inspectionDispatcherParams({params:{...p,handler:{...p.handler,[key]:{}}},methodRegistry:mr}),/HOLD_REQUEST_FACTS_IN_OWNER_CONFIG/);
}
for(const invalid of [{...frame(),method:'xuanjun.execution.start'},{...frame(),params:{operation:'launch'}},{...frame(),authenticated:true}]){assert.throws(()=>readonlyRequestFrame(invalid),/HOLD_/);count++;}
for(const failure of ['none','native-denied','owner-throws','descriptor-denied','release']) {
 const root=mkdtempSync(join(tmpdir(),'b5-dispatch-contract-'));let released=0,retained,receivedClient,receivedFrame;
 const r=registry(),p=params(),opaqueClient=Object.freeze({fixtureOnly:'OPAQUE_WS_OWNER_REFERENCE'});
 if(failure==='descriptor-denied')r.gatewayMethodDescriptors[0].profileAccess='independent';
 try {
  const run=()=>withInspectionDispatcherContract({acquire:async()=>({registry:r,release:async()=>{released++;if(failure==='release')throw Error('release');}}),registryApi:api,createAuthenticatedDispatcher:wired=>{
   assert.equal(wired.handler.getMethodRegistry().pluginRegistry,r);return {dispatch:async(f,c)=>{receivedClient=c;receivedFrame=f;if(failure==='native-denied')throw Error('FIXTURE_NATIVE_AUTH_DENIED');}};
  },params:p,expectedSource:source,record:phase=>appendRecord(root,identity,phase,versions),runAuthenticatedOwner:async dispatcher=>{retained=dispatcher;if(failure==='owner-throws')throw Error('owner');const f=frame();await dispatcher.dispatch(f,opaqueClient,100);assert.equal(receivedFrame,f);return metadata;}});
  if(failure==='none'){const out=await run();assert.equal(out.compiledBinding,'UNBOUND');assert.equal(out.authenticatedDispatch,'NOT_EXECUTED');assert.equal(receivedClient,opaqueClient);}
  else await assert.rejects(run);
  assert.equal(released,1);if(retained)assert.throws(()=>retained.dispatch(frame(),opaqueClient),/HOLD_INSPECTION_LEASE_CLOSED/);
  const rows=readRecords(root,identity);assert.equal(recovery(rows,identity).mayInvoke,false);assert.equal(rows.at(-1).phase,failure==='release'?'OBSERVED':'RELEASED');count++;
 } finally {rmSync(root,{recursive:true,force:true});}
}
{
 let finish,released=0;const r=registry(),seen=[];
 const result=withInspectionDispatcherContract({acquire:async()=>({registry:r,release:()=>{released++;seen.push('release');}}),registryApi:api,createAuthenticatedDispatcher:()=>({dispatch:()=>new Promise(resolve=>{finish=()=>{seen.push('settled');resolve();};})}),params:params(),expectedSource:source,record:phase=>seen.push(phase),runAuthenticatedOwner:async d=>{d.dispatch(frame(),Object.freeze({fixtureOnly:true}),100);return metadata;}});
 await new Promise(resolve=>setImmediate(resolve));assert.equal(released,0);finish();await result;assert.ok(seen.indexOf('settled')<seen.indexOf('release'));count++;
}
{
 let reject,released=0;const seen=[];
 const result=withInspectionDispatcherContract({acquire:async()=>({registry:registry(),release:()=>{released++;}}),registryApi:api,createAuthenticatedDispatcher:()=>({dispatch:()=>new Promise((resolve,fail)=>{reject=fail;})}),params:params(),expectedSource:source,record:phase=>seen.push(phase),runAuthenticatedOwner:async d=>{d.dispatch(frame(),Object.freeze({fixtureOnly:true}),100);return metadata;}});
 await new Promise(resolve=>setImmediate(resolve));assert.equal(released,0);reject(Error('LATE_NATIVE_DENIAL'));await assert.rejects(()=>result,/HOLD_NATIVE_DISPATCH_FAILED/);assert.equal(released,1);assert.ok(!seen.includes('OBSERVED'));assert.equal(seen.at(-1),'RELEASED');count++;
}
assert.equal(COMPILED_DISPATCH_BINDING.dispatcherSha256,null);
console.log(JSON.stringify({scope:'CONTRACT_FIXTURES_ONLY',contract_cases:count,real_compiled_registry:'UNBOUND',actual_authentication:'NOT_EXECUTED'}));
