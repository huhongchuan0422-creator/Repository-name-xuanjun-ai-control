/** Real filesystem journal + independent process readback; SDK callbacks are fixtures. */
import assert from 'node:assert/strict';
import fs,{mkdtempSync,rmSync,readlinkSync,readdirSync,readFileSync} from 'node:fs';
import {syncBuiltinESMExports} from 'node:module';
import {spawnSync} from 'node:child_process';
import {tmpdir} from 'node:os';
import {resolve,join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {inspectReadonlyLease,appendRecord,readRecords,recovery,PLUGIN,READONLY_PROFILE} from '../../production/p2_install/b5_loader_contract.mjs';
const moduleURL=pathToFileURL(resolve('production/p2_install/b5_loader_contract.mjs')).href;
const identity='a'.repeat(64),versions={binding:'b'.repeat(64),node:'c'.repeat(64),plugin:'d'.repeat(64),sdk:'e'.repeat(64)};
let count=0;
for(const failure of ['none','observed-before','observed-after','release']) {
 const root=mkdtempSync(join(tmpdir(),'b5-journal-'));let released=0;
 try {
  const record=async phase=>{
   if(failure==='observed-before'&&phase==='OBSERVED')throw Error('INJECT_OBSERVED_WRITE');
   appendRecord(root,identity,phase,versions);
   if(failure==='observed-after'&&phase==='OBSERVED')throw Error('INJECT_OBSERVED_RESPONSE_LOSS');
  };
  const call=()=>inspectReadonlyLease({expectedSource:'/isolated/plugin.mjs',record,whileAcquired:async()=>{},acquire:async()=>({registry:{plugins:[{id:PLUGIN,source:'/isolated/plugin.mjs',version:READONLY_PROFILE.version,status:'loaded',enabled:true,imported:true,activated:false}],diagnostics:[],gatewayHandlers:{'xuanjun.capabilities.describe':()=>{}}},release:async()=>{released++;if(failure==='release')throw Error('INJECT_RELEASE');}})});
  if(failure==='none')assert.equal((await call()).released,true);else await assert.rejects(call);
  assert.equal(released,1);
  const records=readRecords(root,identity),expected=['INTENT','ACQUIRED','VALIDATED'];
  if(failure!=='observed-before')expected.push('OBSERVED');
  if(failure!=='release')expected.push('RELEASED');
  assert.deepEqual(records.map(r=>r.phase),expected);
  const code=`import {readRecords,recovery} from ${JSON.stringify(moduleURL)}; const rows=readRecords(process.argv[1],process.argv[2]); console.log(JSON.stringify({phases:rows.map(r=>r.phase),result:recovery(rows,process.argv[2])}));`;
  const child=spawnSync(process.execPath,['--input-type=module','-e',code,root,identity],{encoding:'utf8',timeout:5000});
  assert.equal(child.status,0,child.stderr);const recovered=JSON.parse(child.stdout);
  assert.deepEqual(recovered.phases,expected);assert.equal(recovered.result.mayInvoke,false);
  assert.equal(recovered.result.state,failure==='release'?'UNKNOWN_HOLD_RECONCILE':'RELEASE_RECORDED_PROCESS_ENDED');
  assert.throws(()=>appendRecord(root,identity,'OBSERVED',versions),/HOLD_RECORD_SEQUENCE/);
  count++;console.log('ok persistent journal '+failure);
 } finally {rmSync(root,{recursive:true,force:true});}
}
// Inject an actual write failure inside appendRecord after O_EXCL creates 003.json.
// The empty immutable file is retained; RELEASED must not be fabricated over it.
{
 const root=mkdtempSync(join(tmpdir(),'b5-journal-write-'));const original=fs.writeFileSync;let released=0;
 try {
  fs.writeFileSync=(fd,...args)=>{
   if(typeof fd==='number'&&readlinkSync('/proc/self/fd/'+fd)===join(root,'003.json'))throw Object.assign(Error('INJECT_EIO'),{code:'EIO'});
   return original(fd,...args);
  };syncBuiltinESMExports();
  await assert.rejects(()=>inspectReadonlyLease({expectedSource:'/isolated/plugin.mjs',record:phase=>appendRecord(root,identity,phase,versions),whileAcquired:async()=>{},acquire:async()=>({registry:{plugins:[{id:PLUGIN,source:'/isolated/plugin.mjs',version:READONLY_PROFILE.version,status:'loaded',enabled:true,imported:true,activated:false}],diagnostics:[],gatewayHandlers:{'xuanjun.capabilities.describe':()=>{}}},release:async()=>{released++;}})}),/HOLD_INSPECTION_RELEASE_OR_RECORD_UNKNOWN/);
  assert.equal(released,1);assert.deepEqual(readdirSync(root).sort(),['000.json','001.json','002.json','003.json']);assert.equal(readFileSync(join(root,'003.json')).length,0);
  const code=`import {readRecords} from ${JSON.stringify(moduleURL)}; readRecords(process.argv[1],process.argv[2]);`;
  const child=spawnSync(process.execPath,['--input-type=module','-e',code,root,identity],{encoding:'utf8',timeout:5000});assert.notEqual(child.status,0);assert.equal(readFileSync(join(root,'003.json')).length,0);
  console.log('ok appendRecord EIO retains incomplete file and cross-process HOLD');count++;
 } finally {fs.writeFileSync=original;syncBuiltinESMExports();rmSync(root,{recursive:true,force:true});}
}
for(const phases of [['OBSERVED'],['INTENT','OBSERVED'],['INTENT','ACQUIRED','OBSERVED'],['INTENT','ACQUIRED','VALIDATED','OBSERVED','OBSERVED'],['INTENT','ACQUIRED','VALIDATED','RELEASED','OBSERVED']])assert.throws(()=>recovery(phases.map(phase=>({phase,identity})),identity),/HOLD_RECORD_SEQUENCE/);
console.log(JSON.stringify({persistent_scenarios:count,invalid_sequences:5,scope:'CONTRACT_ONLY',sdk:'NOT_EXECUTED'}));
