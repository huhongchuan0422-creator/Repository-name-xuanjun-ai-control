export const ACCEPTANCE_REASON='community-admin-acceptance;version=community-acceptance-v1';
export const ACCEPTANCE_FIELDS=Object.freeze([
 ['community_acceptance_url','验收地址','COMMUNITY_ADMIN_ACCEPTANCE_URL'],
 ['community_acceptance_username','验收用户名','COMMUNITY_ADMIN_ACCEPTANCE_USERNAME'],
 ['community_acceptance_password','验收密码','COMMUNITY_ADMIN_ACCEPTANCE_PASSWORD'],
]);
export function isAcceptanceQuestions(questions) {
 return Array.isArray(questions)&&questions.length===3&&ACCEPTANCE_FIELDS.every(([id,,name],i)=>{
  const q=questions[i],s=q?.secretStore;
  return q?.questionId===id&&q.isSecret===true&&Array.isArray(q.options)&&q.options.length===0&&
   !q.multiSelect&&!q.isOther&&s?.name===name&&s.kind==='secret'&&s.reason===ACCEPTANCE_REASON&&
   Array.isArray(s.allowedHosts)&&s.allowedHosts.length===0;
 });
}
// Use only through the original trusted agent question.request API, not public input.
export function buildAcceptanceRequest(id) {
 return {id,timeoutMs:600000,questions:ACCEPTANCE_FIELDS.map(([questionId,header,name])=>({
  questionId,header,question:header,options:[],isSecret:true,multiSelect:false,isOther:false,
  secretStore:{name,kind:'secret',allowedHosts:[],reason:ACCEPTANCE_REASON}}))};
}
