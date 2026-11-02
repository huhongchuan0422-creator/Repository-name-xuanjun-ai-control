/** Minimal CANDIDATE extension inside original OpenClaw shared-state DB.
 * No second credential DB; this table contains metadata ONLY.
 * Production requires ORIGINAL schema registry/versioned migration admission.
 * Do not execute MIGRATION_SQL against a running database from this module.
 */
import {NAMES} from './openclaw_store_adapter.mjs';
export const MIGRATION_SQL=`CREATE TABLE IF NOT EXISTS safe_input_request_receipts (
 request_id TEXT PRIMARY KEY NOT NULL,
 owner_id TEXT NOT NULL,
 session_binding TEXT NOT NULL,
 purpose TEXT NOT NULL CHECK(purpose='community-admin-acceptance'),
 ui_version TEXT NOT NULL CHECK(ui_version='community-acceptance-v1'),
 created_at_ms INTEGER NOT NULL,
 expires_at_ms INTEGER NOT NULL CHECK(expires_at_ms=created_at_ms+600000),
 status TEXT NOT NULL CHECK(status IN ('PENDING','COMMITTED','EXPIRED','CANCELLED')),
 committed_at_ms INTEGER,
 CHECK((status='COMMITTED' AND committed_at_ms IS NOT NULL) OR
       (status!='COMMITTED' AND committed_at_ms IS NULL))
) STRICT;`;
const PURPOSE='community-admin-acceptance', VERSION='community-acceptance-v1';
const COLUMNS='request_id,owner_id,session_binding,purpose,ui_version,created_at_ms,expires_at_ms,status,committed_at_ms';
const validId=id=>typeof id==='string' && /^[A-Za-z0-9_-]{1,160}$/.test(id);
const result=status=>Object.freeze({status});

/** Composition bindings, all from ORIGINAL trusted host/state module:
 * runWriteTransaction = runOpenClawStateWriteTransaction (export l), original
 * withReadSnapshot = withExistingOpenClawStateDatabaseReadOnly (export f) from
 * openclaw-state-db-readonly-BUOubhzc.mjs, original (NOT state-db export f)
 * writeSecretStoreEntries = secret-store export l, original
 * owner = original server-side authenticated Owner {id,sessionBinding}; NEVER body.
 * originalRequest = ORIGINAL request metadata/live-run registry; NEVER client body.
 * assertRunLive = existing run/lifecycle/mutation authority check; no new grant.
 * HTTP auth/CSRF/origin/body validation must precede this private call.
 */
export function createDurableAcceptanceAdapter({runWriteTransaction,withReadSnapshot,
  writeSecretStoreEntries,database,owner,originalRequest,assertRunLive,
  now=Date.now,resolveUpdatedBy}) {
  if (![runWriteTransaction,withReadSnapshot,writeSecretStoreEntries,owner,
        originalRequest,assertRunLive,now,resolveUpdatedBy].every(f=>typeof f==='function'))
    throw Error('ORIGINAL_BINDINGS_REQUIRED');
  const select=(db,id)=>db.prepare(`SELECT ${COLUMNS} FROM safe_input_request_receipts WHERE request_id=?`).get(id);
  const authenticated=()=>{const p=owner();return p && typeof p.id==='string' && p.id &&
    typeof p.sessionBinding==='string' && p.sessionBinding ? p : null;};
  const matches=(row,p)=>row && row.owner_id===p.id && row.session_binding===p.sessionBinding &&
    row.purpose===PURPOSE && row.ui_version===VERSION;
  return Object.freeze({
    register(requestId) {
      try {
        const p=authenticated(), r=originalRequest(requestId);
        if (!p || !validId(requestId) || !r || r.id!==requestId || r.ownerId!==p.id ||
            r.sessionBinding!==p.sessionBinding || r.purpose!==PURPOSE || r.version!==VERSION || r.status!=='pending' ||
            !Number.isSafeInteger(r.createdAtMs) || r.expiresAtMs!==r.createdAtMs+600000 ||
            r.createdAtMs>now() || now()>=r.expiresAtMs || assertRunLive(requestId)!==true)
          return result('FORBIDDEN');
        return runWriteTransaction(({db})=>{
          const current=authenticated();
          const fresh=originalRequest(requestId);
          if(!current || current.id!==p.id || current.sessionBinding!==p.sessionBinding ||
            !fresh || fresh.id!==r.id || fresh.ownerId!==p.id || fresh.sessionBinding!==p.sessionBinding ||
            fresh.purpose!==PURPOSE || fresh.version!==VERSION || fresh.status!=='pending' ||
            fresh.createdAtMs!==r.createdAtMs || fresh.expiresAtMs!==r.expiresAtMs ||
            assertRunLive(requestId)!==true) return result('FORBIDDEN');
          const prior=select(db,requestId);
          if(prior) return result(matches(prior,p) && prior.created_at_ms===r.createdAtMs &&
            prior.expires_at_ms===r.expiresAtMs ? prior.status : 'FORBIDDEN');
          db.prepare(`INSERT INTO safe_input_request_receipts (${COLUMNS}) VALUES (?,?,?,?,?,?,?,?,NULL)`)
            .run(requestId,p.id,p.sessionBinding,PURPOSE,VERSION,r.createdAtMs,r.expiresAtMs,'PENDING');
          return result('PENDING');
        },database,{operationLabel:'safe-input.register'});
      }catch{return result('UNKNOWN_QUERY_ORIGINAL');}
    },
    submit(requestId,values) {
      try {
        const p=authenticated();
        if(!p || !validId(requestId)) return result('FORBIDDEN');
        if(!values || Object.keys(values).length!==3 || !NAMES.every(n=>Object.hasOwn(values,n) &&
            typeof values[n]==='string' && values[n].length>0)) return result('INVALID');
        return runWriteTransaction(state=>{
          const row=select(state.db,requestId), current=authenticated();
          if(!current || current.id!==p.id || current.sessionBinding!==p.sessionBinding || !matches(row,p)) return result('FORBIDDEN');
          // Durable claim first. No write on replay, even after process restart.
          if(row.status==='COMMITTED') return result('REPLAY_REJECTED');
          if(row.status!=='PENDING') return result(row.status);
          if(now()>=row.expires_at_ms){
            state.db.prepare("UPDATE safe_input_request_receipts SET status='EXPIRED' WHERE request_id=?").run(requestId);
            return result('EXPIRED');
          }
          const fresh=originalRequest(requestId);
          if(!fresh || fresh.id!==requestId || fresh.ownerId!==p.id || fresh.sessionBinding!==p.sessionBinding ||
            fresh.purpose!==PURPOSE || fresh.version!==VERSION || fresh.status!=='pending' ||
            fresh.createdAtMs!==row.created_at_ms || fresh.expiresAtMs!==row.expires_at_ms ||
            assertRunLive(requestId)!==true) return result('FORBIDDEN');
          // Original API joins this SAME managed transaction via SAME state handle;
          // original nested SAVEPOINT rolls back with receipt if outer commit fails.
          writeSecretStoreEntries({entries:NAMES.map(name=>({name,value:values[name],kind:'secret',allowedHosts:[]})),
            updatedBy:resolveUpdatedBy(),database:{...database,database:state}});
          state.db.prepare("UPDATE safe_input_request_receipts SET status='COMMITTED',committed_at_ms=? WHERE request_id=? AND status='PENDING'")
            .run(now(),requestId);
          return result('STORED');
        },database,{operationLabel:'safe-input.submit'});
      }catch{return result('UNKNOWN_QUERY_ORIGINAL');}
    },
    receipt(requestId) {
      try {
        const p=authenticated();
        if(!p || !validId(requestId)) return result('FORBIDDEN');
        return withReadSnapshot(({db})=>{
          const row=select(db,requestId);
          // Original Owner AND session binding retained for reads after process restart.
          // Re-authenticated new-session recovery needs original host policy, not this candidate.
          if(!matches(row,p))
            return result('FORBIDDEN');
          return result(row.status==='COMMITTED'?'STORED':
            row.status==='PENDING'&&now()>=row.expires_at_ms?'EXPIRED':row.status);
        },database) ?? result('NOT_FOUND');
      }catch{return result('UNKNOWN_QUERY_ORIGINAL');}
    },
    cancel(requestId) {
      try {
        const p=authenticated();
        if(!p || !validId(requestId))return result('FORBIDDEN');
        return runWriteTransaction(({db})=>{
          const row=select(db,requestId);
          if(!matches(row,p))return result('FORBIDDEN');
          if(row.status==='PENDING')db.prepare("UPDATE safe_input_request_receipts SET status='CANCELLED' WHERE request_id=?").run(requestId);
          return result(row.status==='PENDING'?'CANCELLED':row.status);
        },database,{operationLabel:'safe-input.cancel'});
      }catch{return result('UNKNOWN_QUERY_ORIGINAL');}
    }
  });
}
