/** Actual SQLite consumer kernel; browser and sensitive lease are TEST DOUBLES.
 * Does not prove original browser isolation, mobile, TLS or native support. */
import {DatabaseSync} from 'node:sqlite';import assert from 'node:assert/strict';import {randomBytes,randomUUID} from 'node:crypto';
import {createNativeAcceptanceConsumer} from '../native_browser_consumer.mjs';import {NAMES} from '../openclaw_store_adapter.mjs';
const db=new DatabaseSync(':memory:');db.exec("CREATE TABLE secret_store_entries(name TEXT,value TEXT,kind TEXT,allowed_hosts TEXT,updated_at_ms INTEGER,revision_token TEXT,scope_kind TEXT,scope_id TEXT,deleted_at_ms INTEGER)");
const revisions=Object.fromEntries(NAMES.map(n=>[n,randomUUID()]));
const values=['https://community.invalid/login',randomBytes(16).toString('hex'),randomBytes(16).toString('hex')];
NAMES.forEach((n,i)=>db.prepare('INSERT INTO secret_store_entries VALUES(?,?,?,?,?,?,?,?,NULL)').run(n,values[i],'secret','["community.invalid"]',1,revisions[n],'team',''));
const refs=NAMES.map(id=>({source:'store',provider:'default',id}));let reads=0,fills=0,clicks=0,quarantined=0,auth=true,destination=true,versions=true;
let plan={purpose:'community-admin-acceptance',version:'community-acceptance-v1',storeProvider:'default',approvedOrigin:'https://community.invalid',allowedHosts:['community.invalid'],secretVersions:{...revisions}};
const current=()=>{if(!auth)throw Error('REVOKED');};
const deps={withReadSnapshot:fn=>{reads++;return fn({db});},authorize:async()=>({assertCurrent:current,plan}),acquirePrivateBoundary:async()=>({finishQuarantined:async()=>{quarantined++;},run:async(fn)=>fn({page:{goto:async()=>{}},assertCurrent:current,assertDestination:async()=>{if(!destination)throw Error(values[2]);},assertVersionCurrent:async()=>{if(!versions)throw Error('STALE');},usernameLocator:async()=>({fill:async value=>{assert.equal(value,values[1]);fills++;}}),passwordLocator:async()=>({fill:async value=>{assert.equal(value,values[2]);fills++;}}),submitLocator:async()=>({click:async()=>{clicks++;}}),loginSuccess:async()=>true})})};
let checks=0;const check=b=>{assert.ok(b);checks++;};const run=()=>createNativeAcceptanceConsumer(deps).login({refs,targetId:'original-target'});
check((await createNativeAcceptanceConsumer({}).login({})).status==='BROWSER_SECRET_INJECTION_UNSUPPORTED');
plan.allowedHosts=[];check((await run()).status==='EGRESS_DENIED');check(reads===0);plan.allowedHosts=['community.invalid'];
auth=false;check((await run()).status==='PRIVATE_LOGIN_UNCONFIRMED');check(reads===0);auth=true;
const acquire=deps.acquirePrivateBoundary;deps.acquirePrivateBoundary=async()=>null;check((await run()).status==='HOLD_OBSERVATION_BOUNDARY');check(reads===0);deps.acquirePrivateBoundary=acquire;
const good=await run();check(good.status==='LOGIN_CONFIRMED_OBSERVATION_QUARANTINED');check(fills===2&&clicks===1&&quarantined===1);check(!JSON.stringify(good).includes(values[1]));
db.prepare('UPDATE secret_store_entries SET allowed_hosts=? WHERE name=?').run('[]',NAMES[2]);check((await run()).status==='PRIVATE_LOGIN_UNCONFIRMED');check(fills===2);db.prepare('UPDATE secret_store_entries SET allowed_hosts=?').run('["community.invalid"]');
destination=false;const rejected=await run();check(rejected.status==='PRIVATE_LOGIN_UNCONFIRMED');check(!JSON.stringify(rejected).includes(values[2]));check(fills===2);destination=true;
versions=false;check((await run()).status==='PRIVATE_LOGIN_UNCONFIRMED');check(fills===2);versions=true;
db.prepare('UPDATE secret_store_entries SET revision_token=?').run('00000000-0000-4000-8000-000000000000');check((await run()).status==='PRIVATE_LOGIN_UNCONFIRMED');check(fills===2);
check((await createNativeAcceptanceConsumer(deps).login({refs,targetId:'original-target',ownerAuthorized:true})).status==='INVALID_REF_REQUEST');
const validPlanVersions=plan.secretVersions;plan.secretVersions=Object.fromEntries(NAMES.map(n=>[n,1]));check((await run()).status==='VERSION_BINDING_REQUIRED');plan.secretVersions=validPlanVersions;
const meta=await createNativeAcceptanceConsumer(deps).revisionMetadata({refs,targetId:'original-target'});check(meta.status==='REVISION_METADATA');check(!JSON.stringify(meta).includes(values[2]));
db.prepare('UPDATE secret_store_entries SET revision_token=NULL').run();check((await createNativeAcceptanceConsumer(deps).revisionMetadata({refs,targetId:'original-target'})).status==='VERSION_BINDING_REQUIRED');
db.close();console.log(JSON.stringify({checks,status:'PASS',realSqlite:true,browser:'TEST_DOUBLE',boundary:'TEST_DOUBLE',originalBrowserSupport:'UNSUPPORTED_UNTIL_INTEGRATED'}));
