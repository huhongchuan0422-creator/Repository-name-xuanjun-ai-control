'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {verifySnapshotReadiness:verify}=require('../deploy/community-preview/snapshot_readiness.cjs');
const c=require('../deploy/community-preview/native-snapshot-version.json');
const pins=require('./fixtures/pomelo-native-startup-pins.json');
const binding={appid:'wx1d5f8873eaea5392',manifest_sha256:c.frontend_manifest_sha256,archive_sha256:c.frontend_archive_sha256,control_source_sha:'c'.repeat(40),backend_source_sha:c.runtime_source_sha,compatibility_evidence_sha256:'d'.repeat(64)};
const r={status:'BACKEND_HEALTH_VERIFIED',http_status:200,profile:'uk-path-candidate',baseUrl:'https://uk.wenwenwenyiyiyi.work/community-preview',origin:'https://uk.wenwenwenyiyiyi.work',health_url:'https://uk.wenwenwenyiyiyi.work/community-preview/community/health',login_verified:false,customer_acceptance:false,payment_enabled:false,control_source_sha:binding.control_source_sha,backend_source_sha:c.runtime_source_sha,backend_version_source:c.version_source,source_coverage:c.source_coverage,startup_source_manifest_sha256:c.startup_source_manifest_sha256,startup_source_pins:pins,frontend_manifest_sha256:binding.manifest_sha256,frontend_archive_sha256:binding.archive_sha256,compatibility:'EXACT_REVIEWED_SNAPSHOT_BACKEND_PAIR',compatibility_evidence_sha256:binding.compatibility_evidence_sha256,observed_at:100,backend_observed_at:100};
test('exact native coverage and original image contract both accepted',()=>{assert.equal(verify(r,binding,100),true);assert.equal(verify({...r,backend_version_source:'IMAGE_BUILD_STAMP'},binding,100),true);});
test('baseline, labels, digest, mutated pin set, time and snapshot drift rejected',()=>{
for(const delta of [{backend_source_sha:'e'.repeat(40)},{source_coverage:'SINGLE_GIT_REVISION'},{backend_version_source:'CLIENT_ENV'},{startup_source_manifest_sha256:'e'.repeat(64)},{startup_source_pins:{}},{startup_source_pins:{...pins,extra:'e'.repeat(64)}},{payment_enabled:true}])assert.throws(()=>verify({...r,...delta},binding,100));
for(const delta of [{source_coverage:'SINGLE_GIT_REVISION'},{startup_source_pins:{}},{backend_source_sha:'e'.repeat(40)},{startup_source_manifest_sha256:'e'.repeat(64)}])assert.throws(()=>verify({...r,...delta},binding,100));
assert.throws(()=>verify({...r,backend_observed_at:0},binding,701));
assert.throws(()=>verify({...r,frontend_manifest_sha256:'e'.repeat(64)},{...binding,manifest_sha256:'e'.repeat(64)},100));
});
