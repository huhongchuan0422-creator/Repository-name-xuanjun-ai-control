/** In-process candidate; caller must retain ORIGINAL question handlers' auth fences.
 * No public RPC, no synthetic Owner identity, no grants from request.body.
 * Receipt's legacy owner_id field below is a correlation of native task scope,
 * NOT a claim that operator.admin identifies a named human Owner.
 */
import {createHash} from 'node:crypto';
import {createDurableAcceptanceAdapter,MIGRATION_SQL} from './durable_receipt_adapter.mjs';
import {isAcceptanceQuestions,buildAcceptanceRequest,ACCEPTANCE_FIELDS} from './acceptance_questions.mjs';
const PURPOSE='community-admin-acceptance',VERSION='community-acceptance-v1';
export function createGatewayAcceptanceBridge({manager,runWriteTransaction,withReadSnapshot,
 writeSecretStoreEntries,database,resolveUpdatedBy,registerRedaction,ensureReceiptSchema,
 now=Date.now}) {
 const scope=record=>{
  if(!record?.agentId||!record.sessionKey||!record.runId)throw Error('ORIGINAL_TASK_SCOPE_REQUIRED');
  return JSON.stringify({agentId:record.agentId,sessionKey:record.sessionKey,runId:record.runId});
 };
 const instance=(record,client,assertCurrent)=>{
  const binding=scope(record),id='native-question:'+createHash('sha256').update(binding).digest('hex');
  const current=id=>{
   assertCurrent();const r=manager.get(id);
   if(!r||!isAcceptanceQuestions(r.questions)||scope(r)!==binding)return null;
   return {id:r.id,ownerId:'native-question:'+createHash('sha256').update(scope(r)).digest('hex'),
    sessionBinding:scope(r),purpose:PURPOSE,version:VERSION,status:r.status,
    createdAtMs:r.createdAtMs,expiresAtMs:r.expiresAtMs};
  };
  return createDurableAcceptanceAdapter({
   runWriteTransaction:(fn,db,opts)=>runWriteTransaction(state=>{ensureReceiptSchema(state.db);return fn(state);},db,opts),
   withReadSnapshot,writeSecretStoreEntries,database,now,
   owner:()=>{assertCurrent();return {id,sessionBinding:binding};},
   originalRequest:current,assertRunLive:questionId=>{assertCurrent();return current(questionId)?.status==='pending';},
   resolveUpdatedBy:()=>resolveUpdatedBy(client)
  });
 };
 return Object.freeze({
  register(record,client,assertCurrent){
   assertCurrent();if(!isAcceptanceQuestions(record.questions))throw Error('INVALID_ACCEPTANCE_BINDING');
   const outcome=instance(record,client,assertCurrent).register(record.id);
   if(outcome.status!=='PENDING')throw Error('ACCEPTANCE_REGISTER_UNCONFIRMED');
  },
  cancel(record,client,assertCurrent){
   if(!isAcceptanceQuestions(record.questions))return;
   const outcome=instance(record,client,assertCurrent).cancel(record.id);
   if(!['CANCELLED','EXPIRED'].includes(outcome.status))throw Error('ACCEPTANCE_CANCEL_UNCONFIRMED');
  },
  resolve(record,client,request,assertCurrent){
   assertCurrent();if(!isAcceptanceQuestions(record.questions)||request.id!==record.id||request.secretStoreAllowedHosts!==undefined)
    throw Error('INVALID_ACCEPTANCE_BINDING');
   const submitted=request.answers?.answers;
   if(!submitted||Object.keys(submitted).length!==3)throw Error('INVALID_ACCEPTANCE_ANSWERS');
   const values={};
   for(const [id,,name]of ACCEPTANCE_FIELDS){const item=submitted[id];
    if(!Array.isArray(item)||item.length!==1||typeof item[0]!=='string'||!item[0])throw Error('INVALID_ACCEPTANCE_ANSWERS');
    values[name]=item[0];registerRedaction(item[0]);
   }
   const durable=instance(record,client,assertCurrent);
   if(durable.receipt(record.id).status==='STORED')throw Error('ACCEPTANCE_ALREADY_CONSUMED');
   const result=manager.resolve(record.id,{answers:Object.fromEntries(ACCEPTANCE_FIELDS.map(([id])=>[id,['stored']]))},request.resolvedBy,{
    resolutionId:request.resolutionId,
    commit:()=>{assertCurrent();const outcome=durable.submit(record.id,values);
     if(outcome.status!=='STORED')throw Error('ACCEPTANCE_COMMIT_UNCONFIRMED');}
   });
   return {result,names:ACCEPTANCE_FIELDS.map(([, ,name])=>name)};
  },
  // Private metadata lookup. ORIGINAL caller must then apply original session read
  // policy before returning it. No values, auth tokens or subject claims are returned.
  persistedRecord(requestId){
   try{return withReadSnapshot(({db})=>{
    const row=db.prepare('SELECT request_id,session_binding,purpose,ui_version,created_at_ms,expires_at_ms,status FROM safe_input_request_receipts WHERE request_id=?').get(requestId);
    if(!row||row.purpose!==PURPOSE||row.ui_version!==VERSION||row.status==='PENDING')return null;
    const bound=JSON.parse(row.session_binding);
    if(typeof bound.agentId!=='string'||!bound.agentId||typeof bound.sessionKey!=='string'||!bound.sessionKey||typeof bound.runId!=='string'||!bound.runId)return null;
    return {id:row.request_id,...bound,questions:buildAcceptanceRequest(row.request_id).questions,
     createdAtMs:row.created_at_ms,expiresAtMs:row.expires_at_ms,
     status:row.status==='COMMITTED'?'answered':row.status==='EXPIRED'||now()>=row.expires_at_ms?'expired':'cancelled',
     ...(row.status==='COMMITTED'?{answers:{answers:Object.fromEntries(ACCEPTANCE_FIELDS.map(([id])=>[id,['stored']]))}}:{})};
   },database)??null;}catch{return null;}
  }
 });
}
export {MIGRATION_SQL};
