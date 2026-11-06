'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {endpoint,verifyReadiness}=require('../deploy/community-preview/endpoint.cjs');
const {createSession}=require('../clients/community-mini/session.js');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawnSync}=require('node:child_process');
const {sourceManifest,verifySource}=require('../deploy/community-preview/endpoint.cjs');
test('current-48df identity admits only the exact 44e product and 48df backend pair',()=>{
 const endpointPath=path.resolve(__dirname,'../deploy/community-preview/endpoint.cjs');
 const frontend='44e7344b9a0b00b3999e64eaf90c243d98f7c001',backend='48df407f30f512b1456270c8faba22f095404b9f',control='c'.repeat(40);
 const child=`const cp=require('node:child_process'),backend=process.argv[1];
cp.execFileSync=()=>JSON.stringify({product_source_sha:process.argv[3],backend_source_sha:backend,control_source_sha:'${control}',fixed_product:true,compatibility:'EXACT_SOURCE_MATCH'});
try{process.stdout.write(JSON.stringify(require(process.argv[2]).sourceIdentity()));}catch(error){process.stderr.write(error.message);process.exit(1);}`;
 const run=(value,product=frontend)=>spawnSync(process.execPath,['-e',child,value,endpointPath,product],{encoding:'utf8',env:{...process.env,GITHUB_SHA:control,COMMUNITY_FIXED_PRODUCT_PREVIEW:'true',COMMUNITY_FIXED_PRODUCT_KIND:'current-48df'}});
 const accepted=run(backend);
 assert.equal(accepted.status,0,accepted.stderr);assert.equal(JSON.parse(accepted.stdout).backend_source_sha,backend);
 const rejected=run('b'.repeat(40));
 assert.notEqual(rejected.status,0);assert.match(rejected.stderr,/FIXED_PRODUCT_IDENTITY_REQUIRED/);
 const stale=run(backend,'28ca2f0c66305a2bca4fa6e27cf27427f36aaefd');
 assert.notEqual(stale.status,0);assert.match(stale.stderr,/FIXED_PRODUCT_IDENTITY_REQUIRED/);
});
test('full prepared manifest detects non-app edits, additions, removals and links',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'mini-source-manifest-'));
 try{
  fs.writeFileSync(path.join(root,'session.js'),'original');
  fs.writeFileSync(path.join(root,'__proto__'),'must be hashed');
  const expected=sourceManifest(root);
  assert.match(expected.__proto__,/^[a-f0-9]{64}$/);
  verifySource(root,JSON.parse(JSON.stringify(expected)));
  fs.writeFileSync(path.join(root,'session.js'),'changed');
  assert.throws(()=>verifySource(root,expected),/PREPARED_SOURCE_CHANGED/);
  fs.writeFileSync(path.join(root,'session.js'),'original');
  fs.writeFileSync(path.join(root,'extra.js'),'extra');
  assert.throws(()=>verifySource(root,expected),/PREPARED_SOURCE_CHANGED/);
  fs.unlinkSync(path.join(root,'extra.js'));fs.unlinkSync(path.join(root,'session.js'));
  assert.throws(()=>verifySource(root,expected),/PREPARED_SOURCE_CHANGED/);
  fs.symlinkSync(path.join(root,'__proto__'),path.join(root,'session.js'));
  assert.throws(()=>verifySource(root,expected),/SOURCE_SYMLINK_DENIED/);
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});
test('prepared manifest enforces byte and entry budgets before hashing oversized input',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'mini-source-budget-'));
 try{
  const file=path.join(root,'large'),fd=fs.openSync(file,'wx');
  try{fs.ftruncateSync(fd,10000001);}finally{fs.closeSync(fd);}
  assert.throws(()=>sourceManifest(root),/SOURCE_MANIFEST_BUDGET_EXCEEDED/);
  fs.unlinkSync(file);
  for(let i=0;i<2001;i++)fs.mkdirSync(path.join(root,'d'+i));
  assert.throws(()=>sourceManifest(root),/SOURCE_MANIFEST_BUDGET_EXCEEDED/);
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});
test('UK prefix carries code-only login, scoped business and logout on same base',async()=>{
 const target=endpoint('uk-path-candidate'),calls=[];
 const wx={login:o=>o.success({code:'synthetic-once'}),request:o=>{
  calls.push(o);
  o.success({statusCode:200,data:{payment_enabled:false,result:o.url.endsWith('/mini/login')?
   {session_token:'s'.repeat(32),expires_at:200,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}:{simulation_only:true}}});
 }};
 const s=createSession(wx,target.baseUrl,()=>100);
 await s.login();await s.transport('shop1',{operation:'community.storefront',params:{}});await s.logout();
 assert.deepEqual(calls.map(x=>x.url),['/mini/login','/mini/api','/mini/logout'].map(x=>target.baseUrl+x));
 assert.deepEqual(calls[0].data,{code:'synthetic-once'});
 assert.equal(calls[1].header['X-Community-Session'],'s'.repeat(32));
});
test('only exact UK prefix is admitted, malformed roots and alternate paths denied before I/O',()=>{
 for(const base of ['https://uk.wenwenwenyiyiyi.work/community-preview/','https://uk.wenwenwenyiyiyi.work/other',
  'https://evil.invalid/community-preview','http://uk.wenwenwenyiyiyi.work/community-preview',
  'https://uk.wenwenwenyiyiyi.work/community-preview?x=1','https://uk.wenwenwenyiyiyi.work/community-preview#x',
  'https://uk.wenwenwenyiyiyi.work/community-preview/../mini','https://uk.wenwenwenyiyiyi.work/%63ommunity-preview',
  'https://user@uk.wenwenwenyiyiyi.work/community-preview','https://uk.wenwenwenyiyiyi.work:444/community-preview']){
  assert.throws(()=>createSession({},base),/TRUSTED_BACKEND_REQUIRED/);
 }
 assert.throws(()=>endpoint('unknown'),/EXACT_PREVIEW_PROFILE_REQUIRED/);
});
test('health proof is bound to exact target, source and freshness; UNKNOWN never qualifies',()=>{
 const target=endpoint('uk-path-candidate'),head='a'.repeat(40);
 const report={...target,status:'BACKEND_HEALTH_VERIFIED',http_status:200,login_verified:false,customer_acceptance:false,
  payment_enabled:false,frontend_source_sha:head,backend_source_sha:head,backend_version_source:'IMAGE_BUILD_STAMP',
  compatibility:'EXACT_SOURCE_MATCH',backend_observed_at:100,observed_at:100};
 verifyReadiness(report,target,head,100);
 for(const patch of [{...endpoint('legacy')},{status:'BACKEND_NOT_READY'}, {http_status:503}, {frontend_source_sha:'b'.repeat(40)}, {backend_source_sha:'b'.repeat(40)},
  {backend_source_sha:null},{backend_version_source:'CLIENT_ENV'},{compatibility:'UNVERIFIED'},
  {backend_observed_at:701},{backend_observed_at:-501},
  {observed_at:701},{observed_at:-501},{login_verified:true},{customer_acceptance:true},{payment_enabled:true}]){
  assert.throws(()=>verifyReadiness({...report,...patch},target,head,100),/MATCHING_FRESH_BACKEND_READINESS_REQUIRED/);
 }
 assert.throws(()=>verifyReadiness(report,target,null,100));
});
test('UNKNOWN login at UK prefix is not replayed and cannot reach business',async()=>{
 let calls=0;
 const s=createSession({login:o=>o.success({code:'synthetic-once'}),request:o=>{calls++;o.fail();}},endpoint('uk-path-candidate').baseUrl);
 await assert.rejects(s.login(),/SERVICE_RESULT_UNKNOWN/);
 assert.equal(calls,1);
 await assert.rejects(s.transport('shop1',{}),/SESSION_EXPIRED/);
 assert.equal(calls,1);
});
