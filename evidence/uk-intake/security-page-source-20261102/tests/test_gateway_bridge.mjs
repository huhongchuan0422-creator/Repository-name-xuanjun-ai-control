/** Native SQLite and candidate bridge; manager/auth ports are explicit test doubles. */
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {randomBytes} from 'node:crypto';
import {createGatewayAcceptanceBridge} from '../gateway_acceptance_bridge.mjs';
import {ensureAcceptanceReceiptSchema} from '../receipt_schema.mjs';
import {buildAcceptanceRequest,ACCEPTANCE_FIELDS,isAcceptanceQuestions} from '../acceptance_questions.mjs';
let checks=0;const check=(b)=>{assert.ok(b);checks++;};
const db=new DatabaseSync(':memory:');let failAfterCommit=false,writes=0,live=true,auth=true;
let record={...buildAcceptanceRequest('test-request'),agentId:'a',sessionKey:'s',runId:'r',createdAtMs:1000,expiresAtMs:601000,status:'pending'};
const manager={get:id=>id===record.id&&live?record:null,resolve(id,answers,by,opts){assert.equal(record.status,'pending');opts.commit();record.status='answered';record.answers=answers;return {status:'answered',answers};}};
const tx=fn=>{db.exec('BEGIN IMMEDIATE');let r;try{r=fn({db});db.exec('COMMIT');}catch(e){db.exec('ROLLBACK');throw e;}if(failAfterCommit){failAfterCommit=false;throw Error('test lost response');}return r;};
const bridge=createGatewayAcceptanceBridge({manager,runWriteTransaction:tx,withReadSnapshot:fn=>fn({db}),writeSecretStoreEntries:()=>{writes++;},database:{},resolveUpdatedBy:()=> 'original-actor',registerRedaction:()=>{},ensureReceiptSchema:ensureAcceptanceReceiptSchema,now:()=>1001});
const admit=()=>{if(!auth)throw Error('ORIGINAL_AUTH_REVOKED');};
check(isAcceptanceQuestions(record.questions));
for(const mutation of [q=>q[0].secretStore.allowedHosts.push('example.invalid'),q=>q[0].secretStore.reason='other',q=>q[1].secretStore.name=q[0].secretStore.name,q=>q[0].isSecret=false]){const qs=structuredClone(record.questions);mutation(qs);check(!isAcceptanceQuestions(qs));}
bridge.register(record,{},admit);check(db.prepare('SELECT status FROM safe_input_request_receipts').get().status==='PENDING');
ensureAcceptanceReceiptSchema(db);ensureAcceptanceReceiptSchema(db);check(true);
check(bridge.persistedRecord(record.id)===null);
auth=false;assert.throws(()=>bridge.resolve(record,{}, {},admit));check(writes===0);auth=true;
const secret=randomBytes(16).toString('hex');const request={id:record.id,answers:{answers:Object.fromEntries(ACCEPTANCE_FIELDS.map(([id])=>[id,[secret]]))}};
assert.throws(()=>bridge.resolve(record,{}, {...request,secretStoreAllowedHosts:[]},admit));check(writes===0);
failAfterCommit=true;assert.throws(()=>bridge.resolve(record,{},request,admit));check(writes===1);check(record.status==='pending');
check(bridge.persistedRecord(record.id).status==='answered');
assert.throws(()=>bridge.cancel(record,{},admit));check(db.prepare('SELECT status FROM safe_input_request_receipts').get().status==='COMMITTED');
assert.throws(()=>bridge.resolve(record,{},request,admit));check(writes===1);
live=false;const stored=bridge.persistedRecord(record.id);check(stored.status==='answered');check(!JSON.stringify(stored).includes(secret));
const bad=new DatabaseSync(':memory:');bad.exec('CREATE TABLE safe_input_request_receipts(request_id TEXT PRIMARY KEY)');assert.throws(()=>ensureAcceptanceReceiptSchema(bad));check(true);bad.close();db.close();
console.log(JSON.stringify({checks,status:'PASS',realSqlite:true,managerAndAuth:'TEST_DOUBLES',gateway:'NOT_EXECUTED',secretOutput:false}));
