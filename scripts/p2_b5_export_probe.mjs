/** Candidate for a LATER explicitly approved offline container, never host execution.
 * Observes an actual named export. Does not acquire a registry or invoke a handler.
 */
import {readFileSync,realpathSync,lstatSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {compatibleNode} from '../production/p2_install/b5_loader_contract.mjs';
const INSTALL='/home/xuanjun_dev/.openclaw/tools/node-v24.21.0';
const NODE=INSTALL+'/bin/node',SDK=INSTALL+'/lib/node_modules/openclaw';
const LOADER=SDK+'/dist/loader-runtime-load-DpgEqnzx.mjs';
const EXPECTED_LOADER='3c30c5d43fb3cd19525853bb6b756cf45cfd05f5da32a732dc129b85cb309787';
const sha=b=>createHash('sha256').update(b).digest('hex');
const check=(value,reason)=>{if(!value)throw new Error(reason);};
const result={scope:'ISOLATED_TEST_ONLY_EXPORT_OBSERVATION',state:'HOLD',dependency_closure:'UNKNOWN',compiled_export:'UNKNOWN',loader_acquire:'NOT_EXECUTED',handlers:'NOT_EXECUTED',cp11:'NOT_EXECUTED'};
try {
 check(process.getuid()===1002&&process.execPath===NODE,'HOLD_FIXED_UID_NODE');
 check(realpathSync('/.dockerenv')==='/.dockerenv','HOLD_OFFLINE_CONTAINER_REQUIRED');
 check(compatibleNode(process.version),'HOLD_NODE_ENGINE');
 check(/^[a-f0-9]{64}$/.test(process.env.P2_B5_SNAPSHOT_MANIFEST_SHA??''),'HOLD_FROZEN_MANIFEST_REQUIRED');
 const ms=lstatSync('/snapshot/manifest.json');check(ms.isFile()&&ms.size<=16*1024*1024,'HOLD_MANIFEST_BOUND');
 const raw=readFileSync('/snapshot/manifest.json');check(sha(raw)===process.env.P2_B5_SNAPSHOT_MANIFEST_SHA,'HOLD_MANIFEST_DIGEST');
 const manifest=JSON.parse(raw);check(manifest.scope==='ISOLATED_TEST_ONLY_SOURCE_SNAPSHOT'&&Array.isArray(manifest.files)&&manifest.files.length<=20000,'HOLD_MANIFEST_SCOPE');
 let total=0;const seen=new Set();
 for(const r of manifest.files){
  check(typeof r.path==='string'&&r.path.startsWith('/')&&!seen.has(r.path)&&/^[a-f0-9]{64}$/.test(r.sha256),'HOLD_MANIFEST_MEMBER');seen.add(r.path);
  check(r.path===NODE||r.path.startsWith(SDK+'/')||(r.kind==='elf-library'&&['/usr/lib64/','/lib64/','/usr/lib/x86_64-linux-gnu/','/lib/x86_64-linux-gnu/'].some(prefix=>r.path.startsWith(prefix))),'HOLD_SOURCE_SCOPE');
  check(realpathSync(r.path)===r.path,'HOLD_RUNTIME_ALIAS');const s=lstatSync(r.path);
  check(s.isFile()&&s.nlink===1&&s.uid===r.uid&&s.gid===r.gid&&(s.mode&0o7777)===r.mode&&s.size===r.bytes&&s.size<=128*1024*1024&&(total+=s.size)<=512*1024*1024,'HOLD_RUNTIME_FILE_BOUND');
  check(sha(readFileSync(r.path))===r.sha256,'HOLD_RUNTIME_FILE_HASH');
 }
 check(seen.has(NODE)&&seen.has(LOADER)&&seen.has(SDK+'/package.json'),'HOLD_REQUIRED_MEMBERS');
 check(sha(readFileSync(LOADER))===EXPECTED_LOADER,'HOLD_LOADER_HISTORICAL_PIN');
 check(JSON.parse(readFileSync(SDK+'/package.json')).version==='2026.9.9','HOLD_OPENCLAW_VERSION');
 result.node_version=process.version;result.node_sha256=sha(readFileSync(NODE));
 // This evaluates REAL upstream module code: only allowed in the later isolated action.
 const namespace=await import(pathToFileURL(LOADER).href);
 check(Object.keys(namespace).length<=512,'HOLD_EXPORT_BOUND');
 result.actual_namespace_exports=Object.fromEntries(Object.keys(namespace).sort().map(k=>[k,typeof namespace[k]]));
 result.sdk_namespace_import='OBSERVED';
 result.compiled_export=typeof namespace.acquirePluginRegistryForInspection==='function'?'NAMED_FUNCTION_OBSERVED_SIGNATURE_UNPROVEN':'UNKNOWN_HOLD_NO_NAMED_EXPORT';
 result.reason='Namespace observation is not dependency closure, registry acquisition, signature/provenance proof, or CP11 acceptance. Never guess a minified alias.';
} catch(error) {result.error=/^HOLD_[A-Z_]+$/.test(error?.message??'')?error.message:error?.code??'HOLD_RUNTIME_IMPORT';}
// New output only; caller supplies a separately approved UID1002 private output mount.
try{writeFileSync('/probe-result/export-observation.json',JSON.stringify(result)+'\n',{flag:'wx',mode:0o600});}
catch(error){result.persist_error=error?.code??'UNKNOWN';}
console.log(JSON.stringify(result));process.exitCode=2;
