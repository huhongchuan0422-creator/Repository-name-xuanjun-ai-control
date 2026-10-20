import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,mkdirSync,symlinkSync,rmSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import os from 'node:os';import path from 'node:path';
import {UPSTREAM,PLUGIN,METHODS,digest,compatibleNode,measureTree,prepareInvocation,validateRegistry,recovery,appendRecord,readRecords,READONLY_PROFILE,readonlyInspectionOptions,inspectReadonlyLease,FIXED_COMPILED,bindFixedInspectionExport} from '../../production/p2_install/b5_loader_contract.mjs';
let count=0;function test(name,fn){fn();count++;console.log('ok',name);}
const H='a'.repeat(64),E='/snapshot/plugin/plugin.mjs';
const binding=()=>({scope:'ISOLATED_TEST_ONLY',upstream:UPSTREAM,openclawVersion:'2026.9.9',nodeVersion:'v24.21.0',nodeSha:H,compiledExport:{state:'VERIFIED',name:'acquirePluginRegistryForInspection',evidenceSha:H},closure:{state:'VERIFIED',evidenceSha:H,unresolved:[],nativeDependencies:'BOUND'},loaderRelativePath:'dist/loader.mjs',files:{'package.json':H,'dist/loader.mjs':H}});
const obs=b=>({nodeVersion:b.nodeVersion,nodeSha:b.nodeSha,files:b.files,readOnlySnapshot:true,nodeBindingsVerified:true});
const plan=b=>prepareInvocation(b,obs(b),digest(b));
const reg=()=>({plugins:[{id:PLUGIN,source:E,version:'0.1.0',enabled:true,imported:true,activated:false,status:'loaded'}],diagnostics:[],gatewayHandlers:Object.fromEntries(METHODS.map(k=>[k,()=>{}]))});
test('engine exact boundaries',()=>{for(const v of ['v22.23.3','24.15.9','25.1.0','26.0.9','UNKNOWN'])assert.equal(compatibleNode(v),false);for(const v of ['24.16.0','24.21.0','26.1.0','27.0.0'])assert.equal(compatibleNode(v),true);});
test('plan never means invocation',()=>{assert.equal(plan(binding()).execution,'NOT_EXECUTED');});
test('missing compiled export holds',()=>{const b=binding();b.compiledExport.state='UNKNOWN';assert.throws(()=>plan(b),/HOLD_COMPILED_EXPORT/);});
test('alias is not guessed',()=>{const b=binding();b.compiledExport.name='a';assert.throws(()=>plan(b),/HOLD_COMPILED_EXPORT/);});
test('dependency omissions hold',()=>{const b=binding();b.closure.unresolved=['dynamic import'];assert.throws(()=>plan(b),/HOLD_DEPENDENCY_CLOSURE/);});
test('tampered reference holds',()=>{const b=binding();assert.throws(()=>prepareInvocation(b,obs(b),'b'.repeat(64)),/HOLD_BINDING_DIGEST/);});
test('tree mismatch holds',()=>{const b=binding(),o=obs(b);o.files={...b.files,extra:H};assert.throws(()=>prepareInvocation(b,o,digest(b)),/HOLD_RUNTIME_TREE/);});
test('mutable tree holds',()=>{const b=binding(),o=obs(b);o.readOnlySnapshot=false;assert.throws(()=>prepareInvocation(b,o,digest(b)),/HOLD_SNAPSHOT_BOUNDARY/);});
test('live shape validates without functional pass',()=>{assert.equal(validateRegistry(reg(),E).cp11,'NOT_EXECUTED');});
test('serialized handlers not executable evidence',()=>{assert.throws(()=>validateRegistry(JSON.parse(JSON.stringify(reg())),E),/HOLD_GATEWAY_HANDLERS/);});
test('wrong source and activated rejected',()=>{const r=reg();r.plugins[0].activated=true;assert.throws(()=>validateRegistry(r,E),/HOLD_PLUGIN_RECORD/);r.plugins[0].activated=false;assert.throws(()=>validateRegistry(r,'/wrong'),/HOLD_PLUGIN_RECORD/);});
test('extra plugin and load error rejected',()=>{const r=reg();r.plugins.push({...r.plugins[0]});assert.throws(()=>validateRegistry(r,E),/HOLD_REGISTRY_SCOPE/);r.plugins.pop();r.diagnostics.push({level:'error'});assert.throws(()=>validateRegistry(r,E),/HOLD_REGISTRY_DIAGNOSTIC/);});
test('response loss never reinvokes',()=>{for(const phases of [['INTENT'],['INTENT','ACQUIRED'],['INTENT','ACQUIRED','VALIDATED']])assert.deepEqual(recovery(phases.map(phase=>({phase,identity:H})),H).mayInvoke,false);});
test('release receipt is not live handle or CP11',()=>{assert.equal(recovery(['INTENT','ACQUIRED','VALIDATED','RELEASED'].map(phase=>({phase,identity:H})),H).cp11,'NOT_EXECUTED');assert.throws(()=>recovery([{phase:'INTENT',identity:'wrong'}],H),/HOLD_OPERATION_CONFLICT/);});
test('missing begin and invalid sequence',()=>{assert.equal(recovery([],H).state,'PROVEN_NOT_INVOKED');assert.throws(()=>recovery([{phase:'ACQUIRED',identity:H}],H),/HOLD_RECORD_SEQUENCE/);});
test('real filesystem tree and special entry rejection',()=>{const root=mkdtempSync(path.join(os.tmpdir(),'b5-contract-'));try{mkdirSync(path.join(root,'dist'));writeFileSync(path.join(root,'dist/a.mjs'),'export{}');assert.equal(Object.keys(measureTree(root)).length,1);symlinkSync('a.mjs',path.join(root,'dist/link'));assert.throws(()=>measureTree(root),/HOLD_UNMATERIALIZED_LINK/);}finally{rmSync(root,{recursive:true});}});
test('immutable version records survive another process',()=>{const root=mkdtempSync(path.join(os.tmpdir(),'b5-record-'));try{const versions={plugin:H,sdk:H,node:H,binding:H};appendRecord(root,H,'INTENT',versions);const child=spawnSync(process.execPath,['--input-type=module','-e',`import {readRecords,recovery} from ${JSON.stringify(new URL('../../production/p2_install/b5_loader_contract.mjs',import.meta.url).href)};console.log(recovery(readRecords(${JSON.stringify(root)},${JSON.stringify(H)}),${JSON.stringify(H)}).state)`],{encoding:'utf8'});assert.equal(child.status,0,child.stderr);assert.match(child.stdout,/UNKNOWN_HOLD_RECONCILE/);assert.throws(()=>appendRecord(root,H,'ACQUIRED',{...versions,node:'b'.repeat(64)}),/HOLD_VERSION_REFERENCE_CONFLICT/);appendRecord(root,H,'ACQUIRED',versions);assert.equal(readRecords(root,H).length,2);writeFileSync(path.join(root,'001.json'),'{}');assert.throws(()=>readRecords(root,H),/HOLD_RECORD_CHAIN/);}finally{rmSync(root,{recursive:true});}});


// These are callbacks/registry fixtures, never an imported SDK or authenticated client.
const readonlyReg=()=>({plugins:[{id:PLUGIN,source:E,version:READONLY_PROFILE.version,enabled:true,imported:true,activated:false,status:'loaded'}],diagnostics:[],gatewayHandlers:{'xuanjun.capabilities.describe':()=>{}}});
async function asyncTest(name,fn){await fn();count++;console.log('ok',name);}
await asyncTest('readonly and legacy profiles never merge method surfaces',async()=>{
 assert.equal(validateRegistry(readonlyReg(),E,'readonly').version,READONLY_PROFILE.version);
 assert.throws(()=>validateRegistry(readonlyReg(),E),/HOLD_PLUGIN_RECORD/);
 assert.throws(()=>validateRegistry(reg(),E,'readonly'),/HOLD_PLUGIN_RECORD/);
 const r=readonlyReg();r.gatewayHandlers[METHODS[0]]=()=>{};assert.throws(()=>validateRegistry(r,E,'readonly'),/HOLD_GATEWAY_HANDLERS/);
 assert.throws(()=>validateRegistry(r,E,'unknown'),/HOLD_REGISTRY_PROFILE/);
});
await asyncTest('inspection options forbid process home and runtime effects',async()=>{
 const options=readonlyInspectionOptions();assert.equal(options.runtimeSideEffects,false);assert.equal(options.allowProcessHomeSessionCatalogs,false);
 assert.deepEqual(options.onlyPluginIds,[PLUGIN]);assert.throws(()=>options.onlyPluginIds.push('other'),TypeError);
});
await asyncTest('successful lease awaits release before RELEASED and returns no CP11 pass',async()=>{
 const phases=[];let released=false;
 const result=await inspectReadonlyLease({expectedSource:E,record:async p=>{if(p==='RELEASED')assert.equal(released,true);phases.push(p);},acquire:async options=>{
  assert.deepEqual(options,readonlyInspectionOptions());return {registry:readonlyReg(),release:async()=>{await Promise.resolve();released=true;}};
 }});
 assert.deepEqual(phases,['INTENT','ACQUIRED','VALIDATED','RELEASED']);assert.equal(result.cp11,'NOT_EXECUTED');assert.equal(result.authenticatedDispatch,'NOT_EXECUTED');
});
await asyncTest('bad plugin registry releases once and never records VALIDATED',async()=>{
 const phases=[];let releases=0;const r=readonlyReg();r.plugins[0].activated=true;
 await assert.rejects(inspectReadonlyLease({expectedSource:E,record:async p=>phases.push(p),acquire:async()=>({registry:r,release:async()=>{releases++;}})}),/HOLD_PLUGIN_RECORD/);
 assert.equal(releases,1);assert.deepEqual(phases,['INTENT','ACQUIRED','RELEASED']);
});
await asyncTest('ACQUIRED persistence failure still disposes acquired handle',async()=>{
 let releases=0;await assert.rejects(inspectReadonlyLease({expectedSource:E,record:async p=>{if(p==='ACQUIRED')throw Error('RECORD_FAILED');},acquire:async()=>({registry:readonlyReg(),release:async()=>{releases++;}})}),/RECORD_FAILED/);assert.equal(releases,1);
});
await asyncTest('release failure retains UNKNOWN and never records RELEASED',async()=>{
 const phases=[];await assert.rejects(inspectReadonlyLease({expectedSource:E,record:async p=>phases.push(p),acquire:async()=>({registry:readonlyReg(),release:async()=>{throw Error('DISPOSAL_FAILED');}})}),/HOLD_INSPECTION_RELEASE_OR_RECORD_UNKNOWN/);
 assert.deepEqual(phases,['INTENT','ACQUIRED','VALIDATED']);
});
await asyncTest('release append failure is not a historical release success',async()=>{
 let releases=0;await assert.rejects(inspectReadonlyLease({expectedSource:E,record:async p=>{if(p==='RELEASED')throw Error('RECORD_FAILED');},acquire:async()=>({registry:readonlyReg(),release:async()=>{releases++;}})}),/HOLD_INSPECTION_RELEASE_OR_RECORD_UNKNOWN/);assert.equal(releases,1);
});
await asyncTest('failed acquire and malformed handles never guess disposal or retry',async()=>{
 let calls=0;const phases=[];await assert.rejects(inspectReadonlyLease({expectedSource:E,record:async p=>phases.push(p),acquire:async()=>{calls++;throw Error('UPSTREAM_REJECTED');}}),/UPSTREAM_REJECTED/);assert.equal(calls,1);assert.deepEqual(phases,['INTENT']);
 await assert.rejects(inspectReadonlyLease({expectedSource:E,record:async()=>{},acquire:async()=>({registry:readonlyReg()})}),/HOLD_INSPECTION_HANDLE_UNKNOWN/);
});
await asyncTest('INTENT append failure does not call acquire',async()=>{
 let calls=0;await assert.rejects(inspectReadonlyLease({expectedSource:E,record:async()=>{throw Error('INTENT_FAILED');},acquire:async()=>{calls++;}}),/INTENT_FAILED/);assert.equal(calls,0);
});
test('a t function alone never binds an unverified compiled module',()=>{
 assert.equal(FIXED_COMPILED.exportName,'t');assert.throws(()=>bindFixedInspectionExport({t:()=>{}},{}),/HOLD_FIXED_THREE_FILE_SET/);
 const files=Object.fromEntries(Object.keys(FIXED_COMPILED.files).map(k=>[k,Buffer.from('synthetic-not-real-sdk')]));
 let accessed=false;const namespace={get t(){accessed=true;return ()=>{};}};
 assert.throws(()=>bindFixedInspectionExport(namespace,files),/HOLD_FIXED_SOURCE_BYTES/);assert.equal(accessed,false);
});
console.log(JSON.stringify({scope:'CONTRACT_FIXTURES_ONLY',tests:count,realLoader:'NOT_EXECUTED',authenticatedDispatch:'NOT_EXECUTED',compiledAliasBinding:'BLOCKED_INPUT_BYTES',cp11:'NOT_EXECUTED'}));
