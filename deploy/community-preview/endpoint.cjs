'use strict';
const profiles=require('./endpoint-profiles.json');
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
function endpoint(profile=process.env.COMMUNITY_PREVIEW_PROFILE??'legacy'){
 if(typeof profile!=='string'||!Object.hasOwn(profiles,profile))throw Error('EXACT_PREVIEW_PROFILE_REQUIRED');
 const baseUrl=profiles[profile];
 const expected=profile==='legacy'?'https://community-preview.wenwenwenyiyiyi.work':'https://uk.wenwenwenyiyiyi.work/community-preview';
 if(baseUrl!==expected)throw Error('PREVIEW_PROFILE_BINDING_MISMATCH');
 const origin=new URL(baseUrl).origin;
 return {profile,baseUrl,origin,health_url:baseUrl+'/community/health'};
}
function verifyReadiness(report,target,head,now=Math.floor(Date.now()/1000)){
 if(!report||report.status!=='BACKEND_HEALTH_VERIFIED'||report.http_status!==200||
    report.profile!==target.profile||report.baseUrl!==target.baseUrl||
    report.origin!==target.origin||report.health_url!==target.health_url||
    report.login_verified!==false||report.customer_acceptance!==false||report.payment_enabled!==false||
    !/^[a-f0-9]{40}$/.test(head||'')||report.frontend_source_sha!==head||report.backend_source_sha!==head||
    report.backend_version_source!=='IMAGE_BUILD_STAMP'||report.compatibility!=='EXACT_SOURCE_MATCH'||
    !Number.isSafeInteger(now)||!Number.isSafeInteger(report.backend_observed_at)||
    report.backend_observed_at>now+30||now-report.backend_observed_at>600||
    !Number.isSafeInteger(report.observed_at)||report.observed_at>now+30||now-report.observed_at>600)
  throw Error('MATCHING_FRESH_BACKEND_READINESS_REQUIRED');
}
module.exports={endpoint,verifyReadiness,sourceManifest,verifySource};
