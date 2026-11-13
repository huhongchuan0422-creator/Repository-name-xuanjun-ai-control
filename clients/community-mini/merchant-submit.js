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
async function submitApplicantApplication({read,current,prepareMaterials,preflight,submitPlatform,submitProvider,queryProvider}){
 let state=await read();if(!current())return {cancelled:true};const id=state.application;
 if(!id||!Number.isSafeInteger(state.version))throw Error('申请版本未确认，请刷新原申请');
 if(['SUBMISSION_UNKNOWN','SUBMITTED_TO_PROVIDER'].includes(state.reviewState)){
  await queryProvider({application:id});if(!current())return {cancelled:true};return read();
 }
 if(!['DRAFT','CORRECTION','PENDING_INTERNAL_REVIEW','INTERNAL_APPROVED'].includes(state.reviewState))throw Error('申请状态未确认，未重复发送微信');
 if(['DRAFT','CORRECTION'].includes(state.reviewState)&&prepareMaterials){await prepareMaterials(state,{platform:['DRAFT','CORRECTION_REQUIRED'].includes(state.platformState),wechat:true});if(!current())return {cancelled:true};state=await read();}
 if(!current()||state.application!==id)return {cancelled:true};
 if(preflight)await preflight(state,{platform:['DRAFT','CORRECTION_REQUIRED'].includes(state.platformState),wechat:true});
 if(!current())return {cancelled:true};
 // The original applicant backend validates and freezes the platform draft.
 // Do not split that action with a redundant client submit/read round trip.
 if(!current()||state.application!==id)return {cancelled:true};
 if(!Number.isSafeInteger(state.revision))throw Error('申请版本未确认，请刷新原申请');
 await submitProvider({application:id,expected_version:state.version,application_revision:state.revision});
 if(!current())return {cancelled:true};state=await read();
 if(!current()||state.application!==id)return {cancelled:true};
 // A verified POST receipt is acceptance, not approval or payment activation.
 if(state.reviewState!=='SUBMITTED_TO_PROVIDER')throw Error('微信受理结果待核实，请刷新原申请，勿重复提交');
 try{await queryProvider({application:id});if(!current())return {cancelled:true};state=await read();}catch(error){if(!current())return {cancelled:true};return {...state,queryPending:true,queryDiagnostic:safeSubmissionDiagnostic(error&&error.submissionDiagnostic)};}
 return state;
}
module.exports.submitApplicantApplication=submitApplicantApplication;
