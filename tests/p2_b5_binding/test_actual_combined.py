"""Actual SDK source bytes; namespace/transport remain explicit contract fixtures."""
import gzip,hashlib,importlib.util,json,subprocess,tempfile,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[2]
s=importlib.util.spec_from_file_location('actual_binding',R/'scripts/p2_b5_three_file_binding.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class ActualTests(unittest.TestCase):
 def test_actual_source_and_combined_lifecycle(self):
  with gzip.open(R/'evidence/p2-b5-20261020/three-files.tar.gz','rb') as f:raw=f.read(430081)
  self.assertEqual(len(raw),430080);self.assertEqual(hashlib.sha256(raw).hexdigest(),m.TAR_SHA)
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'actual.tar';p.write_bytes(raw);files=m.read_bound_archive(str(p))
  analysis=m.analyze(files);self.assertEqual(analysis['mapping']['compiled'],'t');self.assertEqual(analysis['dependency_closure'],'UNKNOWN')
  import base64
  payload=json.dumps({k:base64.b64encode(v).decode() for k,v in files.items()})
  code=r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {combinedContract,validateMetadata,METHOD} from './production/p2_install/b5_combined_contract.mjs';
import {PLUGIN,READONLY_PROFILE,digest} from './production/p2_install/b5_loader_contract.mjs';
const files=Object.fromEntries(Object.entries(JSON.parse(readFileSync(0,'utf8'))).map(([k,v])=>[k,Buffer.from(v,'base64')]));
const source='/isolated/plugin/plugin.mjs';
const declaration={plugin_id:PLUGIN,plugin_version:READONLY_PROFILE.version,declared_capabilities:[{method:METHOD,operation:'describe',read_only:true,required_scope:'operator.admin'}]};
const metadata={...declaration,plugin_source_sha256:'848b0b77df2ee65394c810de8aea40402abc0cf46e8d1eb66a014f2890eedba9',declaration_sha256:digest(declaration)};
for(const failure of ['none','dispatch','metadata','registry','release','record']) {
 let released=0,called=0;const events=[];
 const namespace={t:async options=>{
  assert.equal(options.runtimeSideEffects,false);assert.deepEqual(options.onlyPluginIds,[PLUGIN]);
  return {registry:{plugins:[{id:PLUGIN,source,version:READONLY_PROFILE.version,enabled:true,imported:true,activated:false,status:failure==='registry'?'error':'loaded'}],diagnostics:[],gatewayHandlers:{[METHOD]:()=>{}}},release:async()=>{released++;if(failure==='release')throw Error('release');}};
 }};
 const args={namespace,files,expectedSource:source,record:async event=>{events.push(event);if(failure==='record'&&event==='OBSERVED')throw Error('record');},dispatch:async(method,params)=>{called++;assert.equal(released,0);assert.equal(method,METHOD);assert.deepEqual(params,{operation:'describe'});if(failure==='dispatch')throw Error('dispatch');return failure==='metadata'?{...metadata,extra:'forbidden'}:metadata;}};
 if(failure==='none') {const r=await combinedContract(args);assert.equal(r.cp11,'NOT_EXECUTED');assert.equal(r.authenticatedDispatch,'NOT_EXECUTED');assert.deepEqual(events,['INTENT','ACQUIRED','VALIDATED','OBSERVED','RELEASED']);}
 else await assert.rejects(()=>combinedContract(args));
 assert.equal(released,1);assert.equal(called,failure==='registry'?0:1);
}
let effects=0;
await assert.rejects(()=>combinedContract({namespace:{t:()=>{effects++;}},files:{...files,'package.json':Buffer.from('{}')},expectedSource:source,record:()=>{effects++;},dispatch:()=>{effects++;}}),/HOLD_FIXED_SOURCE_BYTES/);
assert.equal(effects,0);
await assert.rejects(()=>combinedContract({namespace:{t:()=>{effects++;}},files,expectedSource:source,record:()=>{effects++;}}),/HOLD_AUTHENTICATED_TRANSPORT_UNBOUND/);
assert.equal(effects,0);
assert.throws(()=>validateMetadata({...metadata,plugin_source_sha256:'0'.repeat(64)}),/HOLD_READONLY_METADATA/);
console.log(JSON.stringify({actual_bytes:'PASS',combined_contract_cases:9,namespace:'FIXTURE_ONLY',transport:'FIXTURE_ONLY',real_loader:'NOT_EXECUTED',cp11:'NOT_EXECUTED'}));
'''
  r=subprocess.run(['node','--input-type=module','-e',code],input=payload.encode(),cwd=R,capture_output=True,timeout=20)
  self.assertEqual(r.returncode,0,r.stderr.decode());result=json.loads(r.stdout);self.assertEqual(result['cp11'],'NOT_EXECUTED')
if __name__=='__main__':unittest.main()
