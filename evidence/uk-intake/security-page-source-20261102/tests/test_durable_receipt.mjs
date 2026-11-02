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

import {createDurableAcceptanceAdapter,MIGRATION_SQL} from '../durable_receipt_adapter.mjs';

let checks=0;const check=x=>{assert.ok(x);checks++;};
let clock=1000,live=true,actor={id:'owner',sessionBinding:'session-1'},lost=false;
const requests=new Map();
const create=(id)=>requests.set(id,{id,ownerId:'owner',sessionBinding:'session-1',purpose:'community-admin-acceptance',version:'community-acceptance-v1',status:'pending',createdAtMs:clock,expiresAtMs:clock+600000});
const options={runWriteTransaction:transaction,withReadSnapshot:fn=>fn({db,path:filename}),
 writeSecretStoreEntries:context.api.writeSecretStoreEntries,database:{path:filename},owner:()=>actor,
 originalRequest:id=>lost?null:requests.get(id),assertRunLive:()=>live,now:()=>clock,resolveUpdatedBy:()=> 'original-owner-audit'};
let adapter=createDurableAcceptanceAdapter(options);
try {
 db.exec(MIGRATION_SQL);
 create('request-a');check(adapter.register('request-a').status==='PENDING');
 check(adapter.register('request-a').status==='PENDING');
 const values=Object.fromEntries(NAMES.map(n=>[n,randomBytes(24).toString('hex')]));
 check(adapter.submit('request-a',values).status==='STORED');
 check(adapter.receipt('request-a').status==='STORED');
 check(Object.values(values).every(v=>!JSON.stringify(db.prepare('SELECT * FROM safe_input_request_receipts').all()).includes(v)));
 db.close();db=new DatabaseSync(filename);lost=true;live=false;
 adapter=createDurableAcceptanceAdapter(options);
 check(adapter.receipt('request-a').status==='STORED');
 check(adapter.submit('request-a',values).status==='REPLAY_REJECTED');
 clock+=700000;check(adapter.receipt('request-a').status==='STORED');check(writer.metadata().length===3);
 const changed=Object.fromEntries(NAMES.map(n=>[n,randomBytes(24).toString('hex')]));writer.write(changed);
 check(adapter.submit('request-a',values).status==='REPLAY_REJECTED');
 check(NAMES.every(n=>db.prepare('SELECT value FROM secret_store_entries WHERE name=?').get(n).value===changed[n]));
 context.remove({name:NAMES[2],database:{path:filename}});
 check(adapter.receipt('request-a').status==='STORED'); // historical receipt does not promise current values
 check(writer.metadata().filter(e=>e.status==='UNAVAILABLE').length===1);
 lost=false;live=true;create('request-b');adapter.register('request-b');clock+=600000;
 check(adapter.submit('request-b',values).status==='EXPIRED');
 create('request-c');adapter.register('request-c');adapter.cancel('request-c');
 check(adapter.submit('request-c',values).status==='CANCELLED');
 create('request-d');adapter.register('request-d');
 db.exec("CREATE TRIGGER canary_receipt_abort BEFORE UPDATE ON safe_input_request_receipts WHEN NEW.status='COMMITTED' BEGIN SELECT RAISE(ABORT,'SYNTHETIC_FAILURE'); END;");
 check(adapter.submit('request-d',values).status==='UNKNOWN_QUERY_ORIGINAL');
 check(adapter.receipt('request-d').status==='PENDING');
 check(db.prepare('SELECT deleted_at_ms FROM secret_store_entries WHERE name=?').get(NAMES[2]).deleted_at_ms!==null); // revived secret write rolled back too
 check(db.prepare('SELECT value FROM secret_store_entries WHERE name=?').get(NAMES[0]).value===changed[NAMES[0]]);
 db.exec('DROP TRIGGER canary_receipt_abort');
 const after=createDurableAcceptanceAdapter({...options,runWriteTransaction:(fn,...args)=>{const r=transaction(fn,...args);throw Error('AFTER_COMMIT_SIMULATED_DISCONNECT');}});
 check(after.submit('request-d',values).status==='UNKNOWN_QUERY_ORIGINAL');
 db.close();db=new DatabaseSync(filename);
 check(adapter.receipt('request-d').status==='STORED');
 check(adapter.submit('request-d',changed).status==='REPLAY_REJECTED');
 actor={id:'other',sessionBinding:'session-1'};check(adapter.receipt('request-d').status==='FORBIDDEN');
 actor={id:'owner',sessionBinding:'new-existing-auth-session'};check(adapter.receipt('request-d').status==='FORBIDDEN');
 check(adapter.submit('request-d',changed).status==='FORBIDDEN');
 actor={id:'owner',sessionBinding:'session-1'};live=true;lost=false;
 create('request-cancelled');requests.get('request-cancelled').status='cancelled';
 check(adapter.register('request-cancelled').status==='FORBIDDEN');
 create('request-cancel-after-register');check(adapter.register('request-cancel-after-register').status==='PENDING');
 requests.get('request-cancel-after-register').status='cancelled';
 check(adapter.submit('request-cancel-after-register',values).status==='FORBIDDEN');
 create('request-rebound');adapter.register('request-rebound');requests.get('request-rebound').version='different';
 check(adapter.submit('request-rebound',values).status==='FORBIDDEN');
 create('request-ended');adapter.register('request-ended');requests.delete('request-ended');
 check(adapter.submit('request-ended',values).status==='FORBIDDEN');
 check(db.prepare('SELECT updated_by FROM secret_store_entries LIMIT 1').get().updated_by==='original-owner-audit');
 console.log(JSON.stringify({stage:'SAME_DB_DURABLE_RECEIPT_ORIGINAL_WRITE_KERNEL',checks,pass:true,
  actual_sqlite_close_reopen:true,crash_window:'injected before/after commit, not OS kill',full_gateway:false,production:false}));
} finally {db.close();fs.rmSync(dir,{recursive:true,force:true});}
