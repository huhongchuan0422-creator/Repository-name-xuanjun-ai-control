'use strict';
const profiles=require('./endpoint-profiles.json');
const FIXED_FRONTEND='57242e0be52e0535746c3f8c02dcf36bb69d6281',FIXED_BACKEND='57242e0be52e0535746c3f8c02dcf36bb69d6281',FIXED_PROOF_SHA256='a44125664276adae415d9a67734aee3aea3c03a92604a64482beb1761ac456f0',FIXED_COMPATIBILITY='EXACT_SOURCE_MATCH';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
function sourceManifest(root){
 const result=Object.create(null);let count=0,total=0;
 function walk(dir){
  if(!fs.lstatSync(dir).isDirectory())throw Error('SOURCE_DIRECTORY_REQUIRED');
  for(const name of fs.readdirSync(dir).sort()){
   const file=path.join(dir,name),s=fs.lstatSync(file);
   if(s.isSymbolicLink())throw Error('SOURCE_SYMLINK_DENIED');
   if(s.isDirectory()){
    if(++count>2000)throw Error('SOURCE_MANIFEST_BUDGET_EXCEEDED');
    walk(file);continue;
   }
   if(!s.isFile())throw Error('SOURCE_REGULAR_FILE_REQUIRED');
   const relative=path.relative(root,file).split(path.sep).join('/');
   if(relative==='CONNECTED_PREVIEW_RECEIPT.json')continue;
   if(++count>2000)throw Error('SOURCE_MANIFEST_BUDGET_EXCEEDED');
   total+=s.size;
   if(total>10000000)throw Error('SOURCE_MANIFEST_BUDGET_EXCEEDED');
   const fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);
   try{
    const actual=fs.fstatSync(fd);
    if(!actual.isFile()||actual.dev!==s.dev||actual.ino!==s.ino||actual.size!==s.size)throw Error('SOURCE_CHANGED_DURING_READ');
    const data=Buffer.alloc(s.size+1);let used=0,n;
    while(used<data.length&&(n=fs.readSync(fd,data,used,data.length-used,null))>0)used+=n;
    const after=fs.fstatSync(fd);
    if(used!==s.size||after.size!==s.size||after.mtimeMs!==actual.mtimeMs||after.ctimeMs!==actual.ctimeMs)throw Error('SOURCE_CHANGED_DURING_READ');
    result[relative]=crypto.createHash('sha256').update(data.subarray(0,used)).digest('hex');
   }finally{fs.closeSync(fd);}
  }
 }
 walk(root);
 return result;
}
function verifySource(root,expected){
 if(!expected||typeof expected!=='object'||Array.isArray(expected))throw Error('COMPLETE_PREPARED_MANIFEST_REQUIRED');
 const actual=sourceManifest(root),keys=Object.keys(actual).sort(),wanted=Object.keys(expected).sort();
 if(!keys.length||JSON.stringify(keys)!==JSON.stringify(wanted)||
    keys.some(k=>typeof expected[k]!=='string'||actual[k]!==expected[k]))throw Error('PREPARED_SOURCE_CHANGED');
 return actual;
}

// Fixed-product mode is admitted by the same original Python control contract.
// No global GITHUB_SHA rewrite and no upload credential is passed to the child.
function sourceIdentity(){
 const env=process.env,mode=env.COMMUNITY_FIXED_PRODUCT_PREVIEW??'false';
 if(!['true','false'].includes(mode))throw Error('EXACT_PRODUCT_MODE_REQUIRED');
 if(mode==='false'){
  if(env.COMMUNITY_PREVIEW_PRODUCT_CONTEXT)throw Error('UNEXPECTED_PRODUCT_CONTEXT');
  return {product_source_sha:env.GITHUB_SHA||null,control_source_sha:env.GITHUB_SHA||null,source_root:null,fixed_product:false};
 }
 const keys=['PATH','GITHUB_SHA','GITHUB_EVENT_NAME','GITHUB_REPOSITORY','GITHUB_REF','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT',
  'PREVIEW_CONTROL_SHA','PREVIEW_SOURCE_SHA','PREVIEW_TARGET','PREVIEW_EVIDENCE_RUN_ID','PREVIEW_ENABLED',
  'IMAGE_BUILD_ENABLED','RUNNER_TEMP','COMMUNITY_FIXED_PRODUCT_PREVIEW','COMMUNITY_PREVIEW_PRODUCT_CONTEXT'];
 const childEnv=Object.fromEntries(keys.filter(k=>env[k]!==undefined).map(k=>[k,env[k]]));
 let identity;
 try{identity=JSON.parse(require('node:child_process').execFileSync('/usr/bin/python3',
  ['-I','-B',path.resolve(__dirname,'../../scripts/community_preview_fixed_product.py'),'identity'],
  {env:childEnv,encoding:'utf8',timeout:10000,maxBuffer:16384,stdio:['ignore','pipe','pipe']}));}
 catch(_){throw Error('FIXED_PRODUCT_IDENTITY_REQUIRED');}
 if(identity.fixed_product!==true||identity.control_source_sha!==env.GITHUB_SHA||
    identity.product_source_sha!==FIXED_FRONTEND||identity.backend_source_sha!==FIXED_BACKEND||
    identity.compatibility!==FIXED_COMPATIBILITY||identity.compatibility_sha256!==FIXED_PROOF_SHA256)throw Error('FIXED_PRODUCT_IDENTITY_REQUIRED');
 return identity;
}

function endpoint(profile=process.env.COMMUNITY_PREVIEW_PROFILE??'legacy'){
 if(typeof profile!=='string'||!Object.hasOwn(profiles,profile))throw Error('EXACT_PREVIEW_PROFILE_REQUIRED');
 const baseUrl=profiles[profile];
 const expected=profile==='legacy'?'https://community-preview.wenwenwenyiyiyi.work':'https://uk.wenwenwenyiyiyi.work/community-preview';
 if(baseUrl!==expected)throw Error('PREVIEW_PROFILE_BINDING_MISMATCH');
 const origin=new URL(baseUrl).origin;
 return {profile,baseUrl,origin,health_url:baseUrl+'/community/health'};
}
function verifyReadiness(report,target,head,now=Math.floor(Date.now()/1000),controlSha=null){
 if(controlSha!==null&&report?.control_source_sha!==controlSha)throw Error('MATCHING_CONTROL_READINESS_REQUIRED');
 const fixedPair=head===FIXED_FRONTEND && /^[a-f0-9]{40}$/.test(controlSha||'');
 const expectedBackend=fixedPair?FIXED_BACKEND:head;
 const expectedCompatibility=fixedPair?FIXED_COMPATIBILITY:'EXACT_SOURCE_MATCH';
 if(fixedPair && report?.compatibility_sha256!==FIXED_PROOF_SHA256)throw Error('FIXED_COMPATIBILITY_PROOF_REQUIRED');
 if(!report||report.status!=='BACKEND_HEALTH_VERIFIED'||report.http_status!==200||
    report.profile!==target.profile||report.baseUrl!==target.baseUrl||
    report.origin!==target.origin||report.health_url!==target.health_url||
    report.login_verified!==false||report.customer_acceptance!==false||report.payment_enabled!==false||
    !/^[a-f0-9]{40}$/.test(head||'')||report.frontend_source_sha!==head||report.backend_source_sha!==expectedBackend||
    report.backend_version_source!=='IMAGE_BUILD_STAMP'||report.compatibility!==expectedCompatibility||
    !Number.isSafeInteger(now)||!Number.isSafeInteger(report.backend_observed_at)||
    report.backend_observed_at>now+30||now-report.backend_observed_at>600||
    !Number.isSafeInteger(report.observed_at)||report.observed_at>now+30||now-report.observed_at>600)
  throw Error('MATCHING_FRESH_BACKEND_READINESS_REQUIRED');
}
module.exports={endpoint,verifyReadiness,sourceManifest,verifySource,sourceIdentity};
