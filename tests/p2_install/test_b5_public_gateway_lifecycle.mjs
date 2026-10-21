/** Pure fixture contracts: neither SDK nor genuine authentication is executed. */
import assert from 'node:assert/strict';
import {publicGatewayReadonlyLifecycle} from '../../production/p2_install/b5_public_gateway_lifecycle.mjs';
// Use the existing real validation/journal shape rather than replacing validators.
import {PLUGIN,READONLY_PROFILE,digest} from '../../production/p2_install/b5_loader_contract.mjs';
import {METHOD} from '../../production/p2_install/b5_combined_contract.mjs';
const declaration={plugin_id:PLUGIN,plugin_version:READONLY_PROFILE.version,declared_capabilities:[{method:METHOD,operation:'describe',read_only:true,required_scope:'operator.admin'}]};
const payload={...declaration,plugin_source_sha256:'848b0b77df2ee65394c810de8aea40402abc0cf46e8d1eb66a014f2890eedba9',declaration_sha256:digest(declaration)};
const expectedSource='/isolated/plugin.mjs';
let count=0;
for(const mode of ['ok','inspection-release-error','auth-error','close-error','nonpromise-close']){
 const events=[];const registry={plugins:[{id:PLUGIN,source:expectedSource,version:READONLY_PROFILE.version,status:'loaded',enabled:true,imported:true,activated:false}],diagnostics:[],gatewayHandlers:{[METHOD]:()=>{}}};
 let done;const gate=new Promise(r=>{done=r;});
 const server={close(){events.push('close');if(mode==='nonpromise-close')return;return gate.then(()=>{events.push('native-close-settled');if(mode==='close-error')throw Error('close');});}};
 const p=publicGatewayReadonlyLifecycle({expectedSource,record:phase=>events.push(phase),acquire:async()=>({registry,release:async()=>{events.push('inspect-release');if(mode==='inspection-release-error')throw Error('release');}}),startGateway:async()=>{events.push('start');assert.ok(events.indexOf('RELEASED')<events.indexOf('start'));return server;},runAuthenticatedClient:async handle=>{assert.equal(handle,server);events.push('client');if(mode==='auth-error')throw Error('auth');return payload;}});
 const rejection=mode==='ok'?null:assert.rejects(p);await new Promise(r=>setImmediate(r));
 if(mode==='inspection-release-error')assert.ok(!events.includes('start'));else assert.ok(events.includes('close'));
 done();if(rejection)await rejection;else {const r=await p;assert.equal(r.runtimeBinding,'UNBOUND');assert.equal(r.authenticatedDispatch,'NOT_EXECUTED');assert.equal(events.at(-1),'native-close-settled');}count++;
}
console.log(JSON.stringify({affected_cases:count,scope:'PUBLIC_LIFECYCLE_CONTRACT_ONLY',sdk:'NOT_EXECUTED',authentication:'NOT_EXECUTED'}));
