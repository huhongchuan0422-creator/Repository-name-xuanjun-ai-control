import test from'node:test';
import assert from'node:assert/strict';
import fs from'node:fs';
import crypto from'node:crypto';
import {resolveGeoProject,loadGeoRuntime,geoRuntimeNotice} from'../src/geo-v4-runtime.js';

const root=new URL('../geo-v4/',import.meta.url);
const expected={
 'index.html':'39ba7edef950d05c3ab32c626ff2eb19f00007e5a0e231316103a6ae1ea08456',
 'styles.css':'90bb08cecbfc8c6033497dad09b6cb1c70a9d6a1c767910703ebf9868acf899a',
 'ecosystem.css':'d9973bfc62cc3ee4facce90fa08b299c8701e1746059ccfc59358ea9e6cdb79a',
 'app.js':'d6aa15803319ff60b7ec3b073f73eb85a65d2494d89a7cdf68070504700b6822'
};
const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(new URL(p,root))).digest('hex');

test('GEO V4 frozen implementation files remain byte exact',()=>{for(const [p,h] of Object.entries(expected))assert.equal(sha(p),h,p)});
test('GEO live entry changes frozen index only by loading separate runtime adapter',()=>{
 const frozen=fs.readFileSync(new URL('index.html',root),'utf8');
 const live=fs.readFileSync(new URL('live.html',root),'utf8');
 assert.equal(live.replace('<script type="module" src="../src/geo-v4-runtime.js"></script>',''),frozen);
});
test('GEO project context never guesses among multiple tenants',()=>{
 const me={projects:[{id:'a',tenant:'ta',role:'OWNER'},{id:'b',tenant:'tb',role:'OWNER'}]};
 assert.equal(resolveGeoProject(me,'').status,'PROJECT_SELECTION_REQUIRED');
 assert.equal(resolveGeoProject(me,'?project=b').project.tenant,'tb');
 assert.equal(resolveGeoProject(me,'?project=x').status,'PROJECT_FORBIDDEN');
});
test('GEO runtime reuses SaaS identity and reports not connected instead of demo success',async()=>{
 const api={me:async()=>({projects:[{id:'p',tenant:'tenant-a',customer:'c',role:'OWNER'}]})};
 const r=await loadGeoRuntime({api,service:null,search:''});
 assert.equal(r.mode,'NOT_CONNECTED');assert.equal(r.project.id,'p');assert.equal(r.state.service_ready,false);
 assert.match(geoRuntimeNotice(r),/真实 GEO 服务尚未接通/);
});
test('GEO runtime rejects cross-tenant service snapshots',async()=>{
 const api={me:async()=>({projects:[{id:'p',tenant:'tenant-a',customer:'c',role:'OWNER'}]})};
 const service={snapshot:async()=>({tenant_id:'tenant-b',connection:'CONNECTED',entitlement:{enabled:true}})};
 await assert.rejects(loadGeoRuntime({api,service,search:''}),/GEO_TENANT_MISMATCH/);
});
test('GEO runtime only becomes connected with matching tenant and enabled entitlement',async()=>{
 const api={me:async()=>({projects:[{id:'p',tenant:'tenant-a',customer:'c',role:'EDITOR'}]})};
 const service={snapshot:async x=>({tenant_id:x.tenant_id,connection:'CONNECTED',entitlement:{enabled:true,plan:'专业版',quota:1000,remaining:760},approval_required:false})};
 const r=await loadGeoRuntime({api,service,search:''});
 assert.equal(r.mode,'CONNECTED');assert.equal(r.state.service_ready,true);assert.equal(r.state.entitlement.remaining,760);
});
test('GEO service errors do not create fake metrics or execution readiness',async()=>{
 const api={me:async()=>({projects:[{id:'p',tenant:'tenant-a',customer:'c',role:'OWNER'}]})};
 const service={snapshot:async()=>{throw Error('down')}};
 const r=await loadGeoRuntime({api,service,search:''});
 assert.equal(r.mode,'SERVICE_ERROR');assert.equal(r.state.service_ready,false);assert.match(geoRuntimeNotice(r),/不会创建任务或写入数据/);
});
