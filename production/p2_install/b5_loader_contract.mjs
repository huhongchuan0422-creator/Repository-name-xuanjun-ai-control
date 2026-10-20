/** Source/contract preparation only. No CLI, SDK import, registration or health endpoint. */
import {createHash} from 'node:crypto';
import {lstatSync,readFileSync,readdirSync,realpathSync,openSync,writeFileSync,fsyncSync,closeSync} from 'node:fs';
import path from 'node:path';
export const UPSTREAM='bcfc88812a35243893585dbeca87ca41b48272ca';
export const PLUGIN='xuanjun-p2-native-controller';
export const METHODS=Object.freeze(['xuanjun.owner.delivery','xuanjun.execution.start','xuanjun.execution.inspect']);
const hold=code=>{throw new Error(code);};
const sha=value=>createHash('sha256').update(value).digest('hex');
export const digest=value=>sha(JSON.stringify(value));
const hash=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
export function compatibleNode(v) {
 const m=/^v?(\d+)\.(\d+)\.(\d+)$/.exec(v??'');
 return !!m&&((+m[1]===24&&+m[2]>=16)||(+m[1]===26&&+m[2]>=1)||+m[1]>26);
}
/** Exact immutable snapshot enumeration. Symlinks/native-loader closure need prior materialization.
 * Caller must supply an approved read-only snapshot, never a mutable live home/runtime tree.
 * This check alone does not prove mount immutability or resolve dynamic imports.
 */
export function measureTree(root) {
 if(!path.isAbsolute(root)||realpathSync(root)!==root)hold('HOLD_TREE_PATH');
 const files={}; let bytes=0;
 function walk(dir) {
  const ds=lstatSync(dir); if(!ds.isDirectory()||ds.isSymbolicLink())hold('HOLD_TREE_DIRECTORY');
  for(const name of readdirSync(dir).sort()) {
   const p=path.join(dir,name),s=lstatSync(p),rel=path.relative(root,p);
   if(s.isSymbolicLink())hold('HOLD_UNMATERIALIZED_LINK');
   if(s.isDirectory())walk(p);
   else {
    if(!s.isFile()||s.nlink!==1||s.size>64*1024*1024)hold('HOLD_TREE_MEMBER');
    if(Object.keys(files).length>=100000||(bytes+=s.size)>1024*1024*1024)hold('HOLD_TREE_BOUND');
    const raw=readFileSync(p),after=lstatSync(p);
    if(s.dev!==after.dev||s.ino!==after.ino||s.size!==after.size||s.mtimeMs!==after.mtimeMs||s.ctimeMs!==after.ctimeMs||raw.length!==s.size)hold('HOLD_TREE_CHANGED');
    files[rel]=sha(raw);
   }
  }
 }
 walk(root); return files;
}
/** This is an invocation plan, NOT permission or a loader execution entry. */
export function prepareInvocation(binding,observed,approvedBindingSha) {
 if(!hash(approvedBindingSha)||digest(binding)!==approvedBindingSha)hold('HOLD_BINDING_DIGEST');
 if(binding.scope!=='ISOLATED_TEST_ONLY'||binding.upstream!==UPSTREAM||binding.openclawVersion!=='2026.9.9')hold('HOLD_VERSION');
 if(!compatibleNode(observed.nodeVersion)||observed.nodeVersion!==binding.nodeVersion||observed.nodeSha!==binding.nodeSha||!hash(binding.nodeSha))hold('HOLD_NODE_BINDING');
 if(binding.compiledExport?.state!=='VERIFIED'||binding.compiledExport?.name!=='acquirePluginRegistryForInspection'||!hash(binding.compiledExport?.evidenceSha))hold('HOLD_COMPILED_EXPORT');
 if(binding.closure?.state!=='VERIFIED'||!hash(binding.closure?.evidenceSha)||binding.closure?.unresolved?.length!==0||binding.closure?.nativeDependencies!=='BOUND')hold('HOLD_DEPENDENCY_CLOSURE');
 if(observed.readOnlySnapshot!==true||observed.nodeBindingsVerified!==true)hold('HOLD_SNAPSHOT_BOUNDARY');
 if(!observed.files||!binding.files||Object.keys(binding.files).length===0||Object.values(binding.files).some(v=>!hash(v))||digest(observed.files)!==digest(binding.files))hold('HOLD_RUNTIME_TREE');
 if(!hash(binding.files[binding.loaderRelativePath])||!hash(binding.files['package.json']))hold('HOLD_LOADER_MEMBER');
 return Object.freeze({source:UPSTREAM,exportName:'acquirePluginRegistryForInspection',
  signature:'(options) => Promise<{registry,release:()=>Promise<void>}>',
  optionsPolicy:{onlyPluginIds:[PLUGIN],mode:'full',allowProcessHomeSessionCatalogs:false,
   throwOnLoadError:true,loadModules:true},
  lifecycle:'acquire -> validate live registry -> await release in finally',
  runtimeOverridesAllowed:false,activation:false,cache:false,
  execution:'NOT_EXECUTED',cp11:'NOT_EXECUTED'});
}
/** Validates a LIVE upstream PluginRegistry, not JSON supplied as proof of real loading.
 * Contract fixtures may exercise this function but never count as SDK acceptance.
 */
export function validateRegistry(registry,expectedSource) {
 if(!path.isAbsolute(expectedSource))hold('HOLD_PLUGIN_SOURCE');
 if(!Array.isArray(registry?.plugins)||!Array.isArray(registry?.diagnostics)||!registry.gatewayHandlers)hold('HOLD_REGISTRY_SHAPE');
 if(registry.plugins.length!==1)hold('HOLD_REGISTRY_SCOPE');
 const r=registry.plugins[0];
 if(r.id!==PLUGIN||r.source!==expectedSource||(r.packageVersion??r.version)!=='0.1.0'||r.status!=='loaded'||r.enabled!==true||r.imported!==true||r.activated===true||r.error)hold('HOLD_PLUGIN_RECORD');
 if(registry.diagnostics.some(d=>d.level==='error'))hold('HOLD_REGISTRY_DIAGNOSTIC');
 const keys=Object.keys(registry.gatewayHandlers).sort();
 if(JSON.stringify(keys)!==JSON.stringify([...METHODS].sort())||METHODS.some(k=>typeof registry.gatewayHandlers[k]!=='function'))hold('HOLD_GATEWAY_HANDLERS');
 return {state:'REGISTRY_STRUCTURE_VALIDATED',pluginId:r.id,source:r.source,version:r.packageVersion??r.version,
  methods:keys,functionalAcceptance:'NOT_EXECUTED',cp11:'NOT_EXECUTED'};
}
/** Pure recovery classification; never repeats an uncertain loader invocation. */
export function recovery(records,identity) {
 if(records.some(r=>r.identity!==identity))hold('HOLD_OPERATION_CONFLICT');
 const phases=records.map(r=>r.phase);
 const allowed=[[],['INTENT'],['INTENT','ACQUIRED'],['INTENT','ACQUIRED','VALIDATED'],['INTENT','ACQUIRED','VALIDATED','RELEASED'],['INTENT','ACQUIRED','RELEASED']];
 if(!allowed.some(a=>JSON.stringify(a)===JSON.stringify(phases)))hold('HOLD_RECORD_SEQUENCE');
 if(phases.length===0)return {state:'PROVEN_NOT_INVOKED',mayInvoke:false};
 if(phases.at(-1)==='RELEASED')return {state:'RELEASE_RECORDED_PROCESS_ENDED',mayInvoke:false,cp11:'NOT_EXECUTED'};
 return {state:'UNKNOWN_HOLD_RECONCILE',mayInvoke:false,reason:'lost response or process-local registry handle cannot be reconstructed from a receipt'};
}

/** Private, pre-created record directory only. One immutable event per phase; no overwrite.
 * O_EXCL handles competing same-phase writers; invalid/missing events remain HOLD.
 * Caller owns the single operation executor. This utility grants no runtime permission.
 */
export function readRecords(root,identity) {
 const s=lstatSync(root);
 if(realpathSync(root)!==root||!s.isDirectory()||(s.mode&0o077)!==0||s.uid!==process.getuid())hold('HOLD_RECORD_ROOT');
 const names=readdirSync(root).sort(),records=[];let previous=null;
 for(let i=0;i<names.length;i++) {
  if(names[i]!==String(i).padStart(3,'0')+'.json')hold('HOLD_RECORD_GAP');
  const p=path.join(root,names[i]),st=lstatSync(p);
  if(!st.isFile()||st.isSymbolicLink()||st.nlink!==1||st.uid!==process.getuid()||(st.mode&0o077)!==0||st.size>65536)hold('HOLD_RECORD_FILE');
  const r=JSON.parse(readFileSync(p,'utf8'));
  if(r.previous!==previous||r.identity!==identity||r.sequence!==i||r.scope!=='ISOLATED_TEST_ONLY')hold('HOLD_RECORD_CHAIN');
  if(!r.versions||Object.keys(r.versions).sort().join(',')!=='binding,node,plugin,sdk'||Object.values(r.versions).some(v=>!hash(v))||(records.length&&digest(r.versions)!==digest(records[0].versions)))hold('HOLD_RECORD_REFERENCES');
  records.push(r);previous=digest(r);
 }
 recovery(records,identity);return records;
}
export function appendRecord(root,identity,phase,versionReferences) {
 if(!hash(identity)||!versionReferences||Object.keys(versionReferences).sort().join(',')!=='binding,node,plugin,sdk'||Object.values(versionReferences).some(v=>!hash(v)))hold('HOLD_RECORD_REFERENCES');
 const records=readRecords(root,identity);
 if(records.length&&digest(records[0].versions)!==digest(versionReferences))hold('HOLD_VERSION_REFERENCE_CONFLICT');
 const event={scope:'ISOLATED_TEST_ONLY',identity,sequence:records.length,phase,
  versions:versionReferences,previous:records.length?digest(records.at(-1)):null};
 recovery([...records,event],identity);
 const fd=openSync(path.join(root,String(records.length).padStart(3,'0')+'.json'),'wx',0o600);
 try{writeFileSync(fd,JSON.stringify(event)+'\n');fsyncSync(fd);}finally{closeSync(fd);}
 const d=openSync(root,'r');try{fsyncSync(d);}finally{closeSync(d);}
 return event;
}
