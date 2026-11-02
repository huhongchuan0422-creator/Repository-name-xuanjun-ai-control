/** Local in-framework candidate. No listener, database, key, RPC or plaintext read.
 * Real 2026.9.9 bindings, injected by ORIGINAL Gateway's module composition:
 * secret-store-CuSJMUWv.mjs {l:writeSecretStoreEntries,r:listSecretStoreEntries}
 * ref-contract-D0kWy5jy.mjs resolveDefaultSecretProviderAlias (original source).
 * Do NOT expose this module as an agent tool or import secret values through CLI.
 */
export const NAMES = Object.freeze([
  'COMMUNITY_ADMIN_ACCEPTANCE_URL',
  'COMMUNITY_ADMIN_ACCEPTANCE_USERNAME',
  'COMMUNITY_ADMIN_ACCEPTANCE_PASSWORD',
]);
export function createProtectedBundleWriter({writeSecretStoreEntries, listSecretStoreEntries,
  resolveStoreProvider, database, updatedBy}) {
  if (![writeSecretStoreEntries, listSecretStoreEntries, resolveStoreProvider].every(f=>typeof f==='function'))
    throw new Error('ORIGINAL_STORE_BINDINGS_REQUIRED');
  return Object.freeze({
    // Called only inside original authorized question-manager resolve(commit).
    write(values) {
      if (!values || Object.keys(values).length!==NAMES.length ||
          !NAMES.every(n=>Object.hasOwn(values,n) && typeof values[n]==='string' && values[n].length>0))
        throw new Error('INVALID_BUNDLE');
      // Native function already performs ONE SQLite transaction for the entries.
      const kinds=writeSecretStoreEntries({entries:NAMES.map(name=>({
        name, value:values[name], kind:'secret', allowedHosts:[]
      })), updatedBy, database});
      if (kinds.length!==3 || kinds.some(k=>k!=='secret')) throw new Error('STORE_RESULT_UNCONFIRMED');
      // No prior value, rollback value or supplied value is ever returned.
      return Object.freeze({status:'STORED'});
    },
    metadata() {
      const provider=resolveStoreProvider();
      if (typeof provider!=='string' || !/^[a-z][a-z0-9_-]{0,63}$/.test(provider))
        throw new Error('STORE_PROVIDER_UNCONFIRMED');
      const entries=listSecretStoreEntries({database});
      return NAMES.map(name=>{
        const entry=entries.find(e=>e.name===name);
        if (!entry || entry.kind!=='secret') return {name,status:'UNAVAILABLE'};
        // Whitelist metadata fields. Never spread an upstream entry (env has valuePreview).
        return {name,kind:'secret',updatedAtMs:entry.updatedAtMs,
          allowedHosts:entry.allowedHosts,secretRef:{source:'store',provider,id:name}};
      });
    }
  });
}

/** Candidate extension for the ORIGINAL question.resolve handler, not a new RPC.
 * Existing native handler supports one store-bound value; this extends ONLY a
 * pre-registered acceptance-bundle request, after existing session/auth/CSRF and
 * purpose/version binding checks. A client-supplied array of names is forbidden.
 * Native QuestionManager.resolve synchronously checks pending/expiry, runs commit,
 * then marks answered. Its answers remain ['stored'], NEVER the 3 input values.
 * Existing live-run cancellation, authority checks and original lifecycle stay.
 * Integration must keep original question.get/waitAnswer receipt semantics.
 */
export function resolveAcceptanceBundle({authorizeOriginalQuestion, manager, writer,
  requestId, resolutionId, values, reloadReferences}) {
  let committed=false;
  try {
    const admitted=authorizeOriginalQuestion(requestId);
    if (!admitted || admitted.id!==requestId || admitted.purpose!=='community-admin-acceptance' ||
        admitted.version!=='community-acceptance-v1' || typeof admitted.questionId!=='string')
      return {status:'FORBIDDEN'};
    manager.resolve(requestId,{answers:{[admitted.questionId]:['stored']}},admitted.resolvedBy,{
      resolutionId,
      commit:()=>{writer.write(values); committed=true;}
    });
  } catch {
    // Generic fixed outcome; inspect the ORIGINAL receipt before any retry.
    return {status:committed?'STORED_REFRESH_PENDING':'UNKNOWN_QUERY_ORIGINAL'};
  }
  // A refresh must not undo the committed one-time answer or authorize another write.
  return Promise.resolve().then(()=>reloadReferences(NAMES)).then(
    ()=>({status:'STORED'}),()=>({status:'STORED_REFRESH_PENDING'}));
}
