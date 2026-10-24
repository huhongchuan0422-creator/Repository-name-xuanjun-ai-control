// Browser-only pending intent journal; authoritative state always belongs to the server.
export class IntentConflict extends Error {}
const KEY='xj_saas_pending_intent_v1:';
const validKey = x => typeof x==='string' && /^[A-Za-z0-9_-]{16,128}$/.test(x);
const frozen = ({project,page,version,text,intent}) => JSON.stringify({project,page,version,text,intent});
export function createIntentJournal(storage,random=()=>crypto.randomUUID().replaceAll('-','')){
  const scope=x=>KEY+encodeURIComponent(x.project)+'/'+encodeURIComponent(x.page)+'/'+x.version;
  function load(x){const raw=storage.getItem(scope(x));if(!raw)return null;let entry;try{entry=JSON.parse(raw)}catch{throw new IntentConflict('PENDING_INTENT_CORRUPT')}
    if(!validKey(entry.key)||typeof entry.body!=='string'||!['pending','unknown','confirmed'].includes(entry.state))throw new IntentConflict('PENDING_INTENT_CORRUPT');return entry;}
  return {
    load,
    prepare(x){const body=frozen(x),old=load(x);if(old){if(old.body!==body)throw new IntentConflict('SAME_INTENT_DIFFERENT_BODY');return old;}
      const key=random();if(!validKey(key))throw new Error('INVALID_IDEMPOTENCY_KEY');const entry={key,body,state:'pending'};storage.setItem(scope(x),JSON.stringify(entry));return entry;},
    mark(x,state,result){const old=load(x);if(!old||!['unknown','confirmed'].includes(state))throw Error('INTENT_STATE');const next={...old,state,...(result===undefined?{}:{result})};storage.setItem(scope(x),JSON.stringify(next));return next;},
    // Explicit user action after server-side reconciliation; never called on timeout.
    newRequest(x){const old=load(x);if(old&&old.state==='unknown')throw new IntentConflict('UNKNOWN_RESULT_RECONCILE_FIRST');storage.removeItem(scope(x));}
  };
}
export async function submitIntent(api,journal,x,{idempotent=false,retryUnknown=false}={}){
  if(!idempotent){const pending=journal.load(x);if(pending)throw new IntentConflict('LEGACY_SUBMISSION_ALREADY_ATTEMPTED');journal.prepare(x);
    try{const result=await api.submit(x.project,x.page,x.version,x.text,x.intent);journal.mark(x,'confirmed',result);return result;}
    catch(e){journal.mark(x,'unknown');throw e;}
  }
  const entry=journal.prepare(x);
  if(entry.state==='confirmed')return entry.result;
  if(entry.state==='unknown'&&!retryUnknown)throw new IntentConflict('EXPLICIT_RETRY_REQUIRED');
  try{const result=await api.submitIdempotent({...x,idempotency_key:entry.key});journal.mark(x,'confirmed',result);return result;}
  catch(e){journal.mark(x,'unknown');throw e;}
}
