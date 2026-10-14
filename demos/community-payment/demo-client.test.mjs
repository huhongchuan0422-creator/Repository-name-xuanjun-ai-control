import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {makeDemoClient}=require('./demo-client.js');
const scope={tenant_id:'t1',merchant_id:'m1',store_id:'s1'};
test('create and query exact loopback request contracts',async()=>{
 const sent=[];const client=makeDemoClient(async(url,opts)=>{sent.push({url,opts});return {status:200,json:async()=>({state:'PENDING'})};});
 await client.create(scope,'order1',123);await client.state(scope,'order1');
 assert.equal(sent.length,2);assert.equal(sent[0].url,'http://127.0.0.1:18791/demo/orders');
 assert.equal(JSON.parse(sent[0].opts.body).amount_minor,123);
 assert.equal(sent[0].opts.credentials,'omit');
 assert.equal(sent[1].url,'http://127.0.0.1:18791/demo/orders/state');
});
test('simulate explicit demo event only',async()=>{
 const requests=[];const client=makeDemoClient(async(u,o)=>{requests.push({u,o});return {status:200,json:async()=>({state:'SUCCESS',provider_settlement_verified:false})};});
 const result=await client.simulate(scope,'order1','evt1','SUCCESS','tx1',123);
 assert.equal(result.provider_settlement_verified,false);
 assert.equal(JSON.parse(requests[0].o.body).event_id,'evt1');
});
test('reject malformed tenant IDs and integer values before HTTP',async()=>{
 let count=0;const client=makeDemoClient(async()=>{count++;return {status:200,json:async()=>({})};});
 for(const bad of [true,1.2,0,100000001])assert.throws(()=>client.create(scope,'order1',bad));
 for(const bad of ['../escape','x y',''])assert.throws(()=>client.state(scope,bad));
 assert.throws(()=>client.state({...scope,merchant_id:'../wrong'},'order1'));
 assert.equal(count,0);
});
test('reject unrecognized target and unsafe responses',async()=>{
 const c=makeDemoClient(async()=>({status:503,json:async()=>({})}));
 assert.throws(()=>c.simulate(scope,'o1','e1','PAID','tx1',100));
 await assert.rejects(c.state(scope,'o1'),/DEMO_REQUEST_FAILED/);
});
test('no credentials, production payment domain or SDK',async()=>{
 const {readFileSync}=await import('node:fs');
 const src=readFileSync(new URL('./demo-client.js',import.meta.url),'utf8');
 assert.doesNotMatch(src,/wx\.requestPayment|Authorization|api\/v3\/pay\/transactions|https:\/\/api\.mch/);
});
