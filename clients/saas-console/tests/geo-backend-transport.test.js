import test from 'node:test';
import assert from 'node:assert/strict';
import {makeGeoHttpService} from '../src/geo-v4-http-service.js';
import {loadGeoRuntime,buildGeoView} from '../src/geo-v4-runtime.js';
const scope={project_id:'project-a',tenant_id:'tenant-a',customer_id:'customer-a'};
const body={type:'SAVE_BRAND',project_id:'project-a',tenant_id:'tenant-a',form:{name:'synthetic',website:'https://example.invalid'}};
const snap={...scope,connection:'CONNECTED',entitlement:{enabled:true,plan:'synthetic-only'},actions:{SAVE_BRAND:true},brand:{status:'READY',name:'synthetic'},last_command:null};
const reply=(d,status=200)=>({ok:status>=200&&status<300,status,json:async()=>d});
const service=fetcher=>makeGeoHttpService({fetcher,csrf:()=> 'synthetic-csrf',requestId:()=> 'synthetic-request-1'});
test('original snapshot fields, same-origin path/session/CSRF and transport idempotency',async()=>{
 const seen=[];const s=service(async(url,options)=>{seen.push({url,options});return reply(url.endsWith('snapshot')?snap:{state:'SUCCEEDED',idempotency_key:JSON.parse(options.body).idempotency_key})});
 await s.snapshot(scope);await s.command(body);
 assert.equal(seen[0].url,'/customer/center/api/geo/snapshot');assert.deepEqual(JSON.parse(seen[0].options.body),scope);
 assert.equal(seen[1].options.credentials,'same-origin');assert.equal(seen[1].options.headers['X-CSRF-Token'],'synthetic-csrf');assert.equal(JSON.parse(seen[1].options.body).idempotency_key,'synthetic-request-1');
});
test('transport unknown causes one send only; explicit snapshot receipt resolves',async()=>{
 let sends=0;const s=service(async url=>{if(url.endsWith('command')){sends++;throw Error('synthetic-disconnect')}return reply({...snap,last_command:{request_id:'synthetic-request-1',state:'SUCCEEDED'}})});
 await assert.rejects(s.command(body),e=>e.uncertain===true);await assert.rejects(s.command(body),/QUERY_REQUIRED/);assert.equal(sends,1);
 await s.snapshot(scope);await assert.rejects(s.command(body));assert.equal(sends,2);
});
test('server UNKNOWN stays query-only, including after unresolved snapshot',async()=>{
 let sends=0;const s=service(async url=>{if(url.endsWith('command')){sends++;return reply({state:'UNKNOWN',query_required:true},202)}return reply({...snap,last_command:{request_id:'synthetic-request-1',state:'UNKNOWN'}})});
 await assert.rejects(s.command(body),e=>e.uncertain===true);await s.snapshot(scope);await assert.rejects(s.command(body));assert.equal(sends,1);
});
test('wrong tenant/customer snapshot never resolves pending or passes integrity',async()=>{
 const s=service(async()=>reply({...snap,customer_id:'wrong-customer'}));await assert.rejects(s.snapshot(scope),/SUBJECT_MISMATCH/);
});
test('definitive permission refusal does not become ambiguous retry',async()=>{
 let sends=0;const s=service(async()=>{sends++;return reply({error:'DENIED'},403)});
 await assert.rejects(s.command(body),e=>e.status===403&&!e.uncertain);await assert.rejects(s.command(body));assert.equal(sends,2);
});
test('unmatched success receipt remains uncertain rather than successful',async()=>{
 let sends=0;const s=service(async()=>{sends++;return reply({state:'SUCCEEDED',idempotency_key:'wrong-request'})});
 await assert.rejects(s.command(body),e=>e.uncertain===true);await assert.rejects(s.command(body));assert.equal(sends,1);
});
test('unchanged original runtime directly consumes new backend service seam',async()=>{
 const s=service(async()=>reply(snap));
 const runtime=await loadGeoRuntime({api:{me:async()=>({projects:[{id:'project-a',tenant:'tenant-a',customer:'customer-a',role:'OWNER'}]})},service:s,search:''});
 assert.equal(runtime.mode,'CONNECTED');assert.equal(buildGeoView(runtime).brand.name,'synthetic');assert.equal(buildGeoView(runtime).diagnosis,null);
});
