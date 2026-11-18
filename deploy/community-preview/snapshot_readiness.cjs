'use strict';
// Candidate exact-pair contract only. No HTTP, secret, SDK or authority changes.
function verifySnapshotReadiness(report,binding,now){
 const fail=()=>{throw Error('MATCHING_FRESH_SNAPSHOT_READINESS_REQUIRED');};
 const hex=(v,n)=>typeof v==='string'&&new RegExp('^[a-f0-9]{'+n+'}$').test(v);
 if(!binding||!hex(binding.manifest_sha256,64)||!hex(binding.archive_sha256,64)||!hex(binding.control_source_sha,40)||!hex(binding.backend_source_sha,40)||!hex(binding.compatibility_evidence_sha256,64)||binding.appid!=='wx1d5f8873eaea5392')fail();
 // Binding is externally reviewed product input, not generated from health response.
 if(!report||report.status!=='BACKEND_HEALTH_VERIFIED'||report.http_status!==200||report.profile!=='uk-path-candidate'||report.baseUrl!=='https://uk.wenwenwenyiyiyi.work/community-preview'||report.origin!=='https://uk.wenwenwenyiyiyi.work'||report.health_url!=='https://uk.wenwenwenyiyiyi.work/community-preview/community/health'||report.login_verified!==false||report.customer_acceptance!==false||report.payment_enabled!==false||report.control_source_sha!==binding.control_source_sha||report.backend_source_sha!==binding.backend_source_sha||report.backend_version_source!=='IMAGE_BUILD_STAMP'||report.frontend_manifest_sha256!==binding.manifest_sha256||report.frontend_archive_sha256!==binding.archive_sha256||report.compatibility!=='EXACT_REVIEWED_SNAPSHOT_BACKEND_PAIR'||report.compatibility_evidence_sha256!==binding.compatibility_evidence_sha256)fail();
 for(const t of [report.observed_at,report.backend_observed_at])if(!Number.isSafeInteger(now)||!Number.isSafeInteger(t)||t>now+30||now-t>600)fail();
 return true;
}
module.exports={verifySnapshotReadiness};
