/** EXACT ORIGINAL WRITE KERNEL + original bundled Kysely compiler; real SQLite.
 * Not full Gateway import (missing @openclaw/fs-safe dependencies). The 3 scoped
 * lifecycle shims below replace module graph setup, NOT the original write SQL.
 * Test DB is synthetic/temporary/deleted. Never deploy this harness or shims.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {randomBytes} from 'node:crypto';
import {createProtectedBundleWriter,NAMES} from '../openclaw_store_adapter.mjs';
const root=new URL('../original-source/',import.meta.url);
const source=fs.readFileSync(new URL('secret-store-CuSJMUWv.mjs',root),'utf8');
const compilerSource=fs.readFileSync(new URL('kysely-sync-BMSZn9yz.mjs',root),'utf8');
const compilerBody=compilerSource.slice(compilerSource.indexOf('//#region node_modules/'),compilerSource.indexOf('//#region src/infra/kysely-sync.ts'));
const compiler=vm.runInNewContext(compilerBody+'\n;({Kysely,SqliteDialect})',{}, {timeout:5000});
const compiled=new compiler.Kysely({dialect:new compiler.SqliteDialect({database:async()=>{throw Error('COMPILE_ONLY');}})});
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'safe-input-original-kernel-'));fs.chmodSync(dir,0o700);
const filename=path.join(dir,'canary.sqlite');let db=new DatabaseSync(filename);fs.chmodSync(filename,0o600);
const schema=`CREATE TABLE IF NOT EXISTS secret_store_entries (
 scope_kind TEXT NOT NULL CHECK(scope_kind IN ('team','identity')),scope_id TEXT NOT NULL,
 name TEXT NOT NULL,value TEXT NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('secret','env')),
 created_at_ms INTEGER NOT NULL CHECK(created_at_ms>=0),updated_at_ms INTEGER NOT NULL CHECK(updated_at_ms>=0),
 updated_by TEXT,deleted_at_ms INTEGER,allowed_hosts TEXT,
 CHECK((scope_kind='team' AND scope_id='') OR (scope_kind='identity' AND length(scope_id)>0)),
 PRIMARY KEY(scope_kind,scope_id,name)) STRICT;`;
// Harness shim 1: native persistent transaction, no mock/dictionary.
let savepoint=0;
const transaction=fn=>{const nested=db.isTransaction,key='test_nested_'+(++savepoint);db.exec(nested?'SAVEPOINT '+key:'BEGIN IMMEDIATE');try{const r=fn({db,path:filename});db.exec(nested?'RELEASE SAVEPOINT '+key:'COMMIT');return r;}catch(e){if(nested){db.exec('ROLLBACK TO SAVEPOINT '+key);db.exec('RELEASE SAVEPOINT '+key);}else db.exec('ROLLBACK');throw e;}};
// Harness shim 2: original compiled SQL -> native SQLite; no SQL translation.
const execute=(db,query)=>{const q=query.compile();const stmt=db.prepare(q.sql);return q.sql.startsWith('select')?{rows:stmt.all(...q.parameters)}:stmt.run(...q.parameters);};
const context={Buffer,Date,Set,JSON,Error,ENV_SECRET_REF_ID_RE:/^[A-Z][A-Z0-9_]{0,127}$/,
 SecretStoreValidationError:class extends Error{},SECRET_STORE_VALUE_MAX_BYTES:65536,
 isRedactedSecretValue:v=>v==='__OPENCLAW_REDACTED__',classifyHiddenGitHubStoreName:()=>undefined,
 normalizeExactAllowedHost:()=>{throw Error('EGRESS_NOT_TESTED');},
 runOpenClawStateWriteTransaction:transaction,
 // Harness shim 3: exact table columns/constraints from original schema, not full app schema admission.
 ensureSecretStoreSchema:()=>db.exec(schema),getNodeSqliteKysely:()=>compiled,
 executeSqliteQuerySync:execute,executeSqliteQueryTakeFirstSync:(d,q)=>execute(d,q).rows[0]};
const start=source.indexOf('function normalizeScope(');
const end=source.indexOf('function rollbackSecretStoreEntryWrite(');
vm.runInNewContext(source.slice(start,end)+'\nglobalThis.api={writeSecretStoreEntries};',context,{timeout:5000});
// Original metadata projection, with redaction-registry bookkeeping disabled in this harness only.
const meta=source.slice(source.indexOf('function toMetadata('),source.indexOf('function listSecretStoreEntries('));
Object.assign(context,{registerSecretValueForRedaction:()=>{},normalizeSqliteNumber:Number});
vm.runInNewContext(meta+'\nglobalThis.project=toMetadata;',context,{timeout:5000});
Object.assign(context,{openOpenClawStateDatabase:()=>({db,path:filename}),isMissingSecretStoreTableError:()=>false});
vm.runInNewContext(source.slice(source.indexOf('function deleteSecretStoreEntry('),source.indexOf('async function purgeExpiredSecretStoreEntries('))+'\nglobalThis.remove=deleteSecretStoreEntry;',context,{timeout:5000});
const list=()=>db.prepare('SELECT * FROM secret_store_entries WHERE deleted_at_ms IS NULL ORDER BY name').all().map(context.project);
const writer=createProtectedBundleWriter({writeSecretStoreEntries:context.api.writeSecretStoreEntries,
 listSecretStoreEntries:list,resolveStoreProvider:()=> 'default',database:{path:filename},updatedBy:'isolated-canary-only'});
let checks=0; const check=condition=>{assert.ok(condition);checks++;};
try {
 const values=Object.fromEntries(NAMES.map(n=>[n,randomBytes(24).toString('hex')]));
 check(writer.write(values).status==='STORED');
 const metadata=writer.metadata();
 check(metadata.length===3 && metadata.every(e=>e.kind==='secret' && e.allowedHosts.length===0));
 check(Object.values(values).every(v=>!JSON.stringify(metadata).includes(v)));
 db.close();db=new DatabaseSync(filename);
 check(writer.metadata().length===3); // actual close/reopen persistence, not app restart
 check(NAMES.every(n=>db.prepare('SELECT value FROM secret_store_entries WHERE name=?').get(n).value===values[n]));
 const changed=Object.fromEntries(NAMES.map(n=>[n,randomBytes(24).toString('hex')]));
 writer.write(changed);
 check(NAMES.every(n=>db.prepare('SELECT value FROM secret_store_entries WHERE name=?').get(n).value===changed[n]));
 // Native trigger interrupts the second update. Original batch transaction rolls all back.
 db.exec(`CREATE TRIGGER canary_abort BEFORE UPDATE ON secret_store_entries WHEN NEW.name='COMMUNITY_ADMIN_ACCEPTANCE_USERNAME' BEGIN SELECT RAISE(ABORT,'SYNTHETIC_FAILURE'); END;`);
 let failed=false;try{writer.write(values);}catch{failed=true;}
 check(failed);
 check(NAMES.every(n=>db.prepare('SELECT value FROM secret_store_entries WHERE name=?').get(n).value===changed[n]));
 db.exec('DROP TRIGGER canary_abort');
 // Original delete function through the same transaction/query harness. No purge claim.
 context.remove({name:NAMES[2],database:{path:filename}});
 check(writer.metadata().filter(e=>e.status==='UNAVAILABLE').length===1);
 check(db.prepare('SELECT count(*) n FROM secret_store_entries').get().n===3);
 check((fs.statSync(filename).mode & 0o777)===0o600);
 console.log(JSON.stringify({stage:'ORIGINAL_WRITE_KERNEL_REAL_SQLITE',checks,pass:true,
  full_gateway_import:false,real_credentials:false,production:false,temporary_fixture_removed_on_exit:true}));
} finally {db.close();fs.rmSync(dir,{recursive:true,force:true});}
