'use strict';
// One user action, two existing review queues. Never invokes provider execution.
async function submitSharedReview({read,submitPlatform,submitWechat,current}){
 let state=await read();if(!current())return {cancelled:true};
 const id=state.application;
 if(typeof id!=='string'||!id||!Number.isSafeInteger(state.revision)||!Number.isSafeInteger(state.version))throw Error('申请版本未确认，请刷新原申请');
 if(['DRAFT','CORRECTION_REQUIRED'].includes(state.platformState)){
  await submitPlatform({application:id,revision:state.revision});
  if(!current())return {cancelled:true};
  state=await read();if(!current())return {cancelled:true};
  if(state.application!==id)throw Error('申请已切换，已停止提交');
 }
 if(!['SUBMITTED','IN_REVIEW','APPROVED'].includes(state.platformState))throw Error('平台申请状态未确认，请刷新原申请');
 if(['DRAFT','CORRECTION'].includes(state.reviewState)){
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
