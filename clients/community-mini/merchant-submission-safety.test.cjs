'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {submitApplicantApplication:submit}=require('./merchant-submit');
function fixture(){let definition;vm.runInNewContext(fs.readFileSync(__dirname+'/pages/merchant-join/index.js','utf8'),{Page:v=>definition=v,require:p=>p==='../../session'?require('./session'):{},wx:{}});return {...definition,data:{pending:false},setData(v){Object.assign(this.data,v)},current:()=>true,finishConfirmedOcrSave:async()=>{},presentStepOcrReview:()=>{}};}
test('original Page run holds a synchronous lock across two concurrent clicks',async()=>{
 const p=fixture();let release,entered=0;const held=new Promise(r=>release=r);
 const first=p.run(async()=>{entered++;await held;},'提交审核');
 await p.run(async()=>{entered++;},'提交审核');assert.equal(entered,1);assert.equal(p.data.pending,true);
 release();await first;assert.equal(p.data.pending,false);
});
for(const e of [Error('SERVICE_RESULT_UNKNOWN'),Error('SERVICE_REQUEST_REJECTED'),Object.assign(Error('secret_identity_address_token'),{networkKind:'TIMEOUT'}),Error('SERVICE_UNAVAILABLE')])test('final submit generic failure neither reveals raw error nor invites retry '+e.message.split('_')[0],async()=>{
 const p=fixture();await p.run(async()=>{throw e;},'提交审核');
 assert.match(p.data.status,/尚未核实/);assert.match(p.data.status,/勿重复提交/);
 assert.doesNotMatch(p.data.status,/稍后重试|检查网络后重试|secret_identity_address_token|登录连接超时/);
});
test('specific directory guidance survives without exposing server detail',async()=>{const p=fixture();await p.run(async()=>{throw Object.assign(Error('secret'),{regionReason:'DIRECTORY_MISMATCH'});},'提交审核');assert.match(p.data.status,/不要改成旧地名/);assert.doesNotMatch(p.data.status,/secret/);});
test('separate invocations and new controller after unknown response query only',async()=>{
 let record={application:'synthetic',version:1,revision:1,platformState:'SUBMITTED',reviewState:'DRAFT'},posts=0,queries=0;
 function args(){return {read:async()=>({...record}),current:()=>true,submitPlatform:async()=>{throw Error('unexpected platform')},submitProvider:async()=>{posts++;record.reviewState='SUBMISSION_UNKNOWN';throw Error('lost response')},queryProvider:async()=>{queries++;throw Error('query timeout')}};}
 await assert.rejects(submit(args()),/lost response/);
 for(let i=0;i<3;i++)await assert.rejects(submit(args()),/query timeout/);
 assert.equal(posts,1);assert.equal(queries,3);assert.equal(record.reviewState,'SUBMISSION_UNKNOWN');
});

test('known media unknown keeps original material recovery instruction',async()=>{const p=fixture();await p.run(async()=>{throw Object.assign(Error('secret'),{mediaCode:'WECHAT_MEDIA_RESULT_UNKNOWN'});},'提交审核');assert.match(p.data.status,/不会重复发送该材料/);assert.doesNotMatch(p.data.status,/secret|稍后重试/);});

test('unknown region reason fails closed to non-retry feedback',async()=>{const p=fixture();await p.run(async()=>{throw Object.assign(Error('SERVICE_REQUEST_REJECTED'),{regionReason:'UNKNOWN_SECRET'});},'提交审核');assert.match(p.data.status,/尚未核实/);assert.doesNotMatch(p.data.status,/UNKNOWN_SECRET|稍后重试/);});
