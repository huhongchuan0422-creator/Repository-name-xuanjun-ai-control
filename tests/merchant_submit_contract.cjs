'use strict';
// Synthetic contract checks for the applicant-direct submit state machine only.
// No network, no real WeChat provider, no fixture claims about live services.
const assert=require('node:assert/strict');
const {submitApplicantApplication}=require('../clients/community-mini/merchant-submit');
let failures=0;
const test=async(name,body)=>{try{await body();console.log('PASS '+name);}catch(error){failures++;console.error('FAIL '+name+' :: '+(error&&error.message));}};
const states=rows=>{let i=0;return {read:async()=>{const v=rows[Math.min(i,rows.length-1)];i++;return {...v};}};};
const always=()=>({current:()=>true});
(async()=>{
 await test('missing_confirm_never_posts',async()=>{
  const calls=[];
  await assert.rejects(()=>submitApplicantApplication({
   ...states([{application:'app1',revision:3,version:2,reviewState:'DRAFT',platformState:'DRAFT'}]),...always(),
   prepareMaterials:async()=>calls.push('prepare'),submitProvider:async()=>calls.push('post'),queryProvider:async()=>calls.push('query')}),
   /请本人确认当前版本后提交/);
  // 确认门之前仅材料准备，绝不发微信POST。
  assert.deepEqual(calls,['prepare']);
 });
 await test('confirm_false_cancels_without_post',async()=>{
  const calls=[];
  const out=await submitApplicantApplication({...states([{application:'app1',revision:3,version:2,reviewState:'DRAFT',platformState:'DRAFT'}]),...always(),
   confirm:async()=>false,submitProvider:async()=>calls.push('post'),queryProvider:async()=>calls.push('query')});
  assert.deepEqual(out,{cancelled:true});assert.deepEqual(calls,[]);
 });
 await test('unknown_active_get_no_post',async()=>{
  const calls=[];
  const out=await submitApplicantApplication({...states([{application:'app1',revision:4,version:1,reviewState:'SUBMISSION_UNKNOWN',platformState:'SUBMITTED'},
   {application:'app1',revision:4,version:1,reviewState:'SUBMISSION_UNKNOWN',platformState:'SUBMITTED'}]),...always(),
   submitProvider:async()=>calls.push('post'),queryProvider:async p=>{assert.deepEqual(p,{application:'app1'});calls.push('query');}});
  assert.deepEqual(calls,['query']);assert.equal(out.reviewState,'SUBMISSION_UNKNOWN');
 });
 await test('submitted_to_provider_active_get_no_post',async()=>{
  const calls=[];
  await submitApplicantApplication({...states([{application:'app1',revision:4,version:1,reviewState:'SUBMITTED_TO_PROVIDER',platformState:'SUBMITTED'},
   {application:'app1',revision:4,version:1,reviewState:'SUBMITTED_TO_PROVIDER',platformState:'SUBMITTED'}]),...always(),
   submitProvider:async()=>calls.push('post'),queryProvider:async()=>calls.push('query')});
  assert.deepEqual(calls,['query']);
 });
 await test('draft_posts_frozen_version_and_revision',async()=>{
  const posts=[];
  await submitApplicantApplication({...states([{application:'app1',revision:7,version:5,reviewState:'DRAFT',platformState:'DRAFT'},
   {application:'app1',revision:7,version:5,reviewState:'DRAFT',platformState:'DRAFT'},
   {application:'app1',revision:7,version:5,reviewState:'DRAFT',platformState:'DRAFT'},
   {application:'app1',revision:7,version:5,reviewState:'SUBMITTED_TO_PROVIDER',platformState:'SUBMITTED'}]),...always(),
   confirm:async s=>{assert.equal(s.revision,7);assert.equal(s.version,5);return true;},
   submitProvider:async p=>posts.push(p),queryProvider:async()=>{throw Error('MUST_NOT_QUERY_BEFORE_POST');}});
  assert.deepEqual(posts,[{application:'app1',expected_version:5,application_revision:7}]);
 });
 await test('revision_missing_or_unsafe_blocks',async()=>{
  for(const bad of [{revision:undefined},{revision:'7'},{version:undefined}]){
   await assert.rejects(()=>submitApplicantApplication({
    ...states([{application:'app1',revision:7,version:5,...bad,reviewState:'DRAFT',platformState:'DRAFT'}]),...always(),
    confirm:async()=>true,submitProvider:async()=>{throw Error('MUST_NOT_POST');}}),/申请版本未确认/);
  }
 });
 await test('post_confirm_drift_blocks_submit',async()=>{
  const posts=[];
  await assert.rejects(()=>submitApplicantApplication({
   ...states([{application:'app1',revision:7,version:5,reviewState:'DRAFT',platformState:'DRAFT'},
    {application:'app1',revision:8,version:6,reviewState:'DRAFT',platformState:'DRAFT'}]),...always(),
   confirm:async()=>true,submitProvider:async p=>posts.push(p),queryProvider:async()=>{}}),/确认后申请资料或状态已变化/);
  assert.deepEqual(posts,[]);
 });
 await test('application_switch_after_read_blocks',async()=>{
  const posts=[];
  await assert.rejects(()=>submitApplicantApplication({
   ...states([{application:'app1',revision:7,version:5,reviewState:'DRAFT',platformState:'DRAFT'},
    {application:'app2',revision:1,version:1,reviewState:'DRAFT',platformState:'DRAFT'}]),...always(),
   confirm:async()=>true,submitProvider:async()=>posts.push('post')}),/确认后申请资料或状态已变化|申请或版本已变化|申请版本未确认/);
  assert.deepEqual(posts,[]);
 });
 console.log(failures?('CONTRACT_FAILURES='+failures):'ALL_MERCHANT_SUBMIT_CONTRACT_PASS');
 process.exitCode=failures?1:0;
})();
