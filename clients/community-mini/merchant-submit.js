'use strict';
const {safeSubmissionDiagnostic}=require('./submission-diagnostic');
// One user action, two existing review queues. Never invokes provider execution.
async function submitSharedReview({read,submitPlatform,submitWechat,current,preflight,prepareMaterials}){
 let state=await read();if(!current())return {cancelled:true};
 const id=state.application;
 if(typeof id!=='string'||!id||!Number.isSafeInteger(state.revision)||!Number.isSafeInteger(state.version))throw Error('申请版本未确认，请刷新原申请');
 if(prepareMaterials&&['DRAFT','CORRECTION'].includes(state.reviewState)){
  await prepareMaterials(state,{platform:['DRAFT','CORRECTION_REQUIRED'].includes(state.platformState),wechat:true});
  if(!current())return {cancelled:true};
  state=await read();if(!current())return {cancelled:true};
  if(state.application!==id)throw Error('申请已切换，已停止提交');
 }
 if(preflight)await preflight(state,{platform:['DRAFT','CORRECTION_REQUIRED'].includes(state.platformState),wechat:['DRAFT','CORRECTION'].includes(state.reviewState)});
 if(!current())return {cancelled:true};
 if(['DRAFT','CORRECTION_REQUIRED'].includes(state.platformState)){
  await submitPlatform({application:id,revision:state.revision});
  if(!current())return {cancelled:true};
  state=await read();if(!current())return {cancelled:true};
  if(state.application!==id)throw Error('申请已切换，已停止提交');
 }
 if(!['SUBMITTED','IN_REVIEW','APPROVED'].includes(state.platformState))throw Error('平台申请状态未确认，请刷新原申请');
 if(['DRAFT','CORRECTION'].includes(state.reviewState)){
  if(preflight)await preflight(state,{platform:false,wechat:true});
  if(!current())return {cancelled:true};
  await submitWechat({application:id,expected_version:state.version});
  if(!current())return {cancelled:true};
  state=await read();if(!current())return {cancelled:true};
  if(state.application!==id)throw Error('申请已切换，已停止提交');
 }
 if(!['SUBMITTED','IN_REVIEW','APPROVED'].includes(state.platformState))throw Error('平台申请状态已变化，请刷新核实两侧进度');
 if(!['PENDING_INTERNAL_REVIEW','INTERNAL_APPROVED','SUBMISSION_UNKNOWN','SUBMITTED_TO_PROVIDER','CORRECTION'].includes(state.reviewState))throw Error('微信资料审核状态未确认，请刷新原申请');
 return {application:id,platformState:state.platformState,reviewState:state.reviewState,providerState:state.providerState};
}
module.exports={submitSharedReview};
// Authorized owner-only final submission. No fabricated internal approval.
async function submitApplicantApplication({read,current,prepareMaterials,preflight,submitProvider,queryProvider,confirm}){
 let state=await read();if(!current())return {cancelled:true};const id=state.application;
 const valid=s=>s&&s.application===id&&Number.isSafeInteger(s.version)&&Number.isSafeInteger(s.revision);
 if(!id||!valid(state))throw Error('申请版本未确认，请刷新原申请');
 if(state.reviewState==='SUBMISSION_UNKNOWN'||state.reviewState==='SUBMITTED_TO_PROVIDER'){
  // Existing submission is reconciled by the original server GET-only worker.
  // Never turn a status-refresh click into a fresh POST intent.
  if(state.reviewState==='SUBMITTED_TO_PROVIDER')await queryProvider({application:id});
  if(!current())return {cancelled:true};
  const latest=await read();return current()&&latest.application===id?latest:{cancelled:true};
 }
 if(!['DRAFT','CORRECTION','PENDING_INTERNAL_REVIEW','INTERNAL_APPROVED'].includes(state.reviewState))throw Error('申请状态未确认，未发送微信');
 if(['DRAFT','CORRECTION'].includes(state.reviewState)&&prepareMaterials){
  await prepareMaterials(state,{platform:['DRAFT','CORRECTION_REQUIRED'].includes(state.platformState),wechat:true});
  if(!current())return {cancelled:true};state=await read();
 }
 if(!current())return {cancelled:true};if(!valid(state))throw Error('申请或版本已变化，请重新核对');
 if(preflight)await preflight(state,{platform:['DRAFT','CORRECTION_REQUIRED'].includes(state.platformState),wechat:true});
 if(!current())return {cancelled:true};
 const frozen={application:id,version:state.version,revision:state.revision,reviewState:state.reviewState};
 if(typeof confirm!=='function')throw Error('请本人确认当前版本后提交');
 if(!await confirm({...frozen}))return {cancelled:true};
 if(!current())return {cancelled:true};
 state=await read();if(!current())return {cancelled:true};
 if(!valid(state)||state.version!==frozen.version||state.revision!==frozen.revision||state.reviewState!==frozen.reviewState)throw Error('确认后申请资料或状态已变化，未提交；请重新核对当前版本');
 await submitProvider({application:id,expected_version:frozen.version,application_revision:frozen.revision});
 if(!current())return {cancelled:true};state=await read();
 return current()&&state.application===id?state:{cancelled:true};
}
module.exports.submitApplicantApplication=submitApplicantApplication;
