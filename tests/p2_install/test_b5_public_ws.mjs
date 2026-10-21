/** Contract-only scheduling fixtures. Never imports/evaluates the archived SDK. */
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {readFileSync,mkdtempSync,rmSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {tmpdir} from 'node:os';import {join} from 'node:path';
import {withPublicWsContract,bindPublicWsNamespace,WS_FILES} from '../../production/p2_install/b5_ws_public_contract.mjs';
import {PLUGIN,READONLY_PROFILE,digest,appendRecord,readRecords} from '../../production/p2_install/b5_loader_contract.mjs';
import {METHOD} from '../../production/p2_install/b5_combined_contract.mjs';
const source='/isolated/plugin.mjs';
const declaration={plugin_id:PLUGIN,plugin_version:READONLY_PROFILE.version,declared_capabilities:[{method:METHOD,operation:'describe',read_only:true,required_scope:'operator.admin'}]};
const metadata={...declaration,plugin_source_sha256:'848b0b77df2ee65394c810de8aea40402abc0cf46e8d1eb66a014f2890eedba9',declaration_sha256:digest(declaration)};
function registry(){const handler=()=>{};return {plugins:[{id:PLUGIN,source,version:READONLY_PROFILE.version,status:'loaded',enabled:true,imported:true,activated:false}],diagnostics:[],gatewayHandlers:{[METHOD]:handler},gatewayMethodDescriptors:[{name:METHOD,handler,scope:'operator.admin',owner:{kind:'plugin',pluginId:PLUGIN},profileAccess:'required'}]};}
const api={createPluginGatewayMethodDescriptors:r=>r.gatewayMethodDescriptors,createGatewayMethodRegistry:(ds,r)=>({pluginRegistry:r,getHandler:n=>ds.find(d=>d.name===n)?.handler,getScope:n=>ds.find(d=>d.name===n)?.scope,listMethods:()=>ds.map(d=>d.name),requiresAuthenticatedProfile:n=>ds.find(d=>d.name===n)?.profileAccess==='required',isControlPlaneWrite:()=>false,descriptors:()=>ds})};
const frame=(id='request')=>JSON.stringify({type:'req',id,method:METHOD,params:{operation:'describe'}});
let cases=0;
const retained=JSON.parse(readFileSync(new URL('../../evidence/p2-b5-ws-20261021/received-bytes.json',import.meta.url)));
const decoded=JSON.parse(gunzipSync(Buffer.from(retained.gzip_base64,'base64')));
const files=Object.fromEntries(Object.entries(decoded.files).map(([n,b])=>[n,Buffer.from(b,'utf8')]));const pkg=Buffer.from(decoded.package,'utf8');
const ns={attachGatewayWsMessageHandler:()=>{throw Error('SDK_FIXTURE_NAMESPACE_MUST_NOT_EXECUTE');}};
assert.equal(bindPublicWsNamespace(ns,files,pkg).attach,ns.attachGatewayWsMessageHandler);cases++;
for(const name of Object.keys(WS_FILES)){assert.throws(()=>bindPublicWsNamespace(ns,{...files,[name]:Buffer.from('tamper')},pkg),/SOURCE_SHA/);cases++;}
assert.throws(()=>bindPublicWsNamespace({createGatewayAuthenticatedRequestDispatcher:()=>{}},files,pkg),/NAMESPACE/);cases++;
for(const mode of ['queued-handshake','delayed','denied','disconnect','attach-throws','drain-fails','forbidden','no-response','drain-false','drain-true','drain-null','drain-object','drain-zero','interleaved-cleanup','old-callback']){
 const root=mkdtempSync(join(tmpdir(),'b5-public-ws-'));let released=0,client=null;const pending=new Set(),events=[],socket=new EventEmitter(),opaque=Object.freeze({fixtureOnly:'OPAQUE_REFERENCE_NOT_AUTHENTICATION'});
 let stale;let finish;const blocked=new Promise(resolve=>{finish=resolve;});
 const work={signal:new AbortController().signal,track:fn=>{const p=Promise.resolve().then(fn);pending.add(p);p.then(()=>pending.delete(p),()=>pending.delete(p));return p;}};
 const context=()=>opaque;
 const params={socket,connectionWork:work,getClient:()=>client,buildRequestContext:context,isClosed:()=>false,close:()=>events.push('closed'),send:()=>({kind:'sent'}),ownerPolicy:opaque};
 const attach=p=>{
  assert.equal(p.socket,socket);assert.equal(p.connectionWork,work);assert.equal(p.getClient,params.getClient);assert.equal(p.buildRequestContext,context);assert.equal(p.ownerPolicy,opaque);
  const onMessage=data=>{const f=JSON.parse(data.toString());work.track(async()=>{
   await blocked;
   if(f.method==='connect'){client=opaque;events.push('handshake-fixture-settled');return;}
   if(mode==='queued-handshake')await new Promise(resolve=>setImmediate(resolve));
   events.push('request-settled');
   if(mode!=='no-response')p.send({type:'res',id:f.id,ok:!['denied','disconnect'].includes(mode),...(mode==='denied'||mode==='disconnect'?{error:{code:'FORBIDDEN'}}:{payload:metadata})});
  });};
  socket.on('message',onMessage);
  if(mode==='attach-throws')throw Error('PARTIAL_ATTACH');
  return onMessage; // intentionally void dispatch, unlike old internal dispatcher fixture.
 };
 const identity='a'.repeat(64),versions={binding:'b'.repeat(64),node:'c'.repeat(64),plugin:'d'.repeat(64),sdk:'e'.repeat(64)};
 const operation=withPublicWsContract({acquire:async()=>({registry:registry(),release:async()=>{assert.equal(pending.size,0);released++;events.push('release');}}),registryApi:api,attach,params,expectedSource:source,record:phase=>appendRecord(root,identity,phase,versions),runTransportOwner:async()=>{
  stale=socket.listeners('message')[0];
  if(['queued-handshake','interleaved-cleanup'].includes(mode))socket.emit('message',JSON.stringify({type:'req',id:'connect',method:'connect',params:{fixtureOnly:true}}));
  socket.emit('message',mode==='forbidden'?JSON.stringify({type:'req',id:'bad',method:'launch',params:{}}):frame());
 },quiesceAndDrain:async owner=>{
  assert.equal(owner.connectionWork,work);events.push('drain-start');
  if(mode==='old-callback')assert.throws(()=>stale(frame('late-during-drain')),/HOLD_WS_INGRESS_CLOSED/);
  if(mode==='interleaved-cleanup')work.track(async()=>{await blocked;await new Promise(resolve=>setImmediate(resolve));work.track(async()=>{await new Promise(resolve=>setImmediate(resolve));events.push('cleanup-settled');});});
  if(mode==='drain-fails'){finish();await Promise.allSettled([...pending]);throw Error('UNKNOWN_DRAIN');}
  finish();while(pending.size){await Promise.allSettled([...pending]);await new Promise(resolve=>setImmediate(resolve));}
  socket.removeAllListeners('message');events.push('drained');
  if(mode.startsWith('drain-'))return ({'drain-false':false,'drain-true':true,'drain-null':null,'drain-object':{state:'PASS'},'drain-zero':0})[mode];
 }});
 try{
  if(['queued-handshake','delayed','interleaved-cleanup','old-callback'].includes(mode)){
   const result=await operation;assert.equal(result.authenticatedDispatch,'NOT_EXECUTED');assert.equal(result.nativeWorkDrain,'UNBOUND_OWNER_CONTRACT');assert.equal(result.executionReadiness,'HOLD_REAL_OWNER_UNBOUND');assert.ok(events.indexOf('drained')<events.indexOf('release'));assert.equal(released,1);assert.equal(readRecords(root,identity).at(-1).phase,'RELEASED');
  }else{await assert.rejects(operation);assert.equal(released,mode.startsWith('drain-')?0:1);assert.ok(!readRecords(root,identity).some(r=>r.phase==='OBSERVED'));}
  assert.equal(socket.listenerCount('message'),0);
  if(mode==='old-callback'){assert.throws(()=>stale(frame('late-after-release')),/HOLD_WS_INGRESS_CLOSED/);assert.equal(pending.size,0);}
  if(mode==='interleaved-cleanup'){assert.ok(events.indexOf('handshake-fixture-settled')<events.indexOf('cleanup-settled'));assert.ok(events.indexOf('cleanup-settled')<events.indexOf('release'));}
  cases++;
 }finally{rmSync(root,{recursive:true,force:true});}
}
console.log(JSON.stringify({cases,scope:'CONTRACT_AND_STATIC_BYTES_ONLY',sdk:'NOT_EXECUTED',realAuthentication:'NOT_EXECUTED'}));
