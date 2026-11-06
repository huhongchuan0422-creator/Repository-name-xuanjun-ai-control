import test from'node:test';
import assert from'node:assert/strict';
import fs from'node:fs';
import crypto from'node:crypto';

const root=new URL('../geo-v4/',import.meta.url);
const contract=JSON.parse(fs.readFileSync(new URL('GEO_BACKEND_CONTRACT_REQUIRED.json',root),'utf8'));
const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(new URL(p,root))).digest('hex');

test('GEO backend contract remains explicitly required-not-connected',()=>{
 assert.equal(contract.state,'REQUIRED_NOT_CONNECTED');
 assert.equal(contract.customer_writer_must_not_implement_backend,true);
 assert.equal(contract.identity_source,'existing /customer/center/api/me');
});

test('GEO backend contract requires tenant authority and no blind retry',()=>{
 assert.match(contract.required_service.tenant_rule,/must equal/);
 assert.match(contract.required_service.unknown_rule,/never blindly retries/);
 assert.ok(contract.required_service.snapshot_response_required.includes('tenant_id'));
 assert.ok(contract.required_service.snapshot_response_required.includes('actions'));
});

test('GEO backend contract covers complete V4 customer business chain',()=>{
 for(const key of['entitlement','billing_usage','diagnosis','task','versions','results','next_round'])
  assert.ok(contract.required_domains[key],key);
});

test('GEO backend contract rejects known offline/runtime sources as production authority',()=>{
 assert.equal(contract.known_non_authoritative_sources.length,3);
 assert.ok(contract.known_non_authoritative_sources.some(x=>x.includes('community_saas_modules.py')));
 assert.ok(contract.known_non_authoritative_sources.some(x=>x.includes('community_saas_phase2_http.py')));
 assert.ok(contract.known_non_authoritative_sources.some(x=>x.includes('task_supervisor_runtime.py')));
});

test('GEO V4 visual source parity remains exact and live adds only runtime guard plus module',()=>{
 const expected={
  'index.html':'39ba7edef950d05c3ab32c626ff2eb19f00007e5a0e231316103a6ae1ea08456',
  'styles.css':'90bb08cecbfc8c6033497dad09b6cb1c70a9d6a1c767910703ebf9868acf899a',
  'ecosystem.css':'d9973bfc62cc3ee4facce90fa08b299c8701e1746059ccfc59358ea9e6cdb79a',
  'app.js':'d6aa15803319ff60b7ec3b073f73eb85a65d2494d89a7cdf68070504700b6822'};
 for(const [p,h] of Object.entries(expected))assert.equal(sha(p),h,p);
 const frozen=fs.readFileSync(new URL('index.html',root),'utf8');
 const live=fs.readFileSync(new URL('live.html',root),'utf8');
 const normalized=live
   .replace('<style id="geo-runtime-guard">body{visibility:hidden}</style>','')
   .replace('<script type="module" src="../src/geo-v4-runtime.js"></script>','');
 assert.equal(normalized,frozen);
});
