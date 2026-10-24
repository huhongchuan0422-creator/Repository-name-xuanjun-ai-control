export class IntentConflict extends Error {}
const validKey=x=>typeof x==='string'&&/^[A-Za-z0-9_-]{16,128}$/.test(x);
const markerKey=x=>'xj_saas_legacy_unknown:'+encodeURIComponent(x.project)+':'+encodeURIComponent(x.page)+':'+x.version;
export function createIntentJournal(session,random=()=>crypto.randomUUID().replaceAll('-','')){
 const memory=new Map(); const scope=x=>[x.project,x.page,x.version].join('|');
 return {
  get:x=>memory.get(scope(x))||null,clear:x=>memory.delete(scope(x)),
  prepareCandidate(x){const k=scope(x),old=memory.get(k);if(old&&old.body!==JSON.stringify(x))throw new IntentConflict('SAME_KEY_DIFFERENT_BODY');if(old)return old;const key=random();if(!validKey(key))throw Error('INVALID_IDEMPOTENCY_KEY');const e={key,body:JSON.stringify(x),state:'pending'};memory.set(k,e);return e},
  markCandidate(x,state,result){const e=this.get(x);if(!e)throw Error('INTENT_STATE');Object.assign(e,{state,result});return e},
  markLegacyUnknown(x){session.setItem(markerKey(x),JSON.stringify({project:x.project,page:x.page,version:x.version,at:Date.now()}));},
  legacyUnknown(x){const v=session.getItem(markerKey(x));return v?JSON.parse(v):null},
  clearLegacyUnknown(x){session.removeItem(markerKey(x))},
  markerKey
 };
}
export async function submitLegacy(api,journal,x){if(journal.legacyUnknown(x))throw new IntentConflict('LEGACY_UNKNOWN_RECONCILE_FIRST');try{const r=await api.submit(x.project,x.page,x.version,x.text,x.intent);journal.clearLegacyUnknown(x);return r}catch(e){if(e.uncertain)journal.markLegacyUnknown(x);throw e}}
export async function submitCandidate(api,journal,x,{retryUnknown=false}={}){const e=journal.prepareCandidate(x);if(e.state==='confirmed')return e.result;if(e.state==='unknown'&&!retryUnknown)throw new IntentConflict('EXPLICIT_RETRY_REQUIRED');try{const r=await api.submitIdempotent({...x,idempotency_key:e.key});journal.markCandidate(x,'confirmed',r);return r}catch(err){if(err.uncertain)journal.markCandidate(x,'unknown');else journal.clear(x);throw err}}
