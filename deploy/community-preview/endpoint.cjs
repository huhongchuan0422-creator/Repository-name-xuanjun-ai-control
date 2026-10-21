'use strict';
const profiles=require('./endpoint-profiles.json');
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
    !/^[a-f0-9]{40}$/.test(head||'')||report.source_sha!==head||
    !Number.isSafeInteger(report.observed_at)||report.observed_at>now+30||now-report.observed_at>600)
  throw Error('MATCHING_FRESH_BACKEND_READINESS_REQUIRED');
}
module.exports={endpoint,verifyReadiness};
