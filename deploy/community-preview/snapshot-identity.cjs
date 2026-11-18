'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
function identity(env,{verifySource}){
 const need=(v)=>{if(!v)throw Error('EXACT_HANGZHOU_SNAPSHOT_IDENTITY_REQUIRED');};
 need((env.GITHUB_EVENT_NAME==='workflow_dispatch'||(env.GITHUB_EVENT_NAME==='push'&&env.COMMUNITY_SNAPSHOT_PUSH==='true'))&&env.GITHUB_REPOSITORY==='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'&&env.GITHUB_REF==='refs/heads/feature/chatgpt-community-wechat-sp-offline-20261017');
 need(/^[a-f0-9]{40}$/.test(env.GITHUB_SHA||'')&&env.PREVIEW_CONTROL_SHA===env.GITHUB_SHA&&env.PREVIEW_TARGET==='uk-path-candidate'&&env.PREVIEW_ENABLED==='true'&&env.IMAGE_BUILD_ENABLED==='false');
 const bindingPath=env.COMMUNITY_SNAPSHOT_BINDING,root=env.COMMUNITY_SNAPSHOT_ROOT;
 need(bindingPath&&root&&/^[a-f0-9]{64}$/.test(env.COMMUNITY_SNAPSHOT_BINDING_SHA256||''));
 need(!fs.lstatSync(bindingPath).isSymbolicLink()&&!fs.lstatSync(root).isSymbolicLink());
 const raw=fs.readFileSync(bindingPath);need(sha(raw)===env.COMMUNITY_SNAPSHOT_BINDING_SHA256);const b=JSON.parse(raw);
 need(b.control_source_sha===env.GITHUB_SHA&&b.appid==='wx1d5f8873eaea5392'&&b.baseUrl==='https://uk.wenwenwenyiyiyi.work/community-preview'&&b.scene===null&&b.payments===false&&b.commerce===true);
 for(const n of ['manifest_sha256','archive_sha256','compatibility_evidence_sha256'])need(/^[a-f0-9]{64}$/.test(b[n]||''));
 need(/^[a-f0-9]{40}$/.test(b.backend_source_sha||''));
 const receipt=JSON.parse(fs.readFileSync(path.join(root,'snapshot-receipt.json'),'utf8'));
 need(receipt.status==='SNAPSHOT_STAGED_NOT_UPLOAD_ADMITTED'&&receipt.manifest_sha256===b.manifest_sha256&&receipt.zip_sha256===b.archive_sha256&&receipt.appid===b.appid&&Object.keys(receipt.source_files).length===51);
 // Receipt cannot substitute the externally pinned complete source map.
 need(JSON.stringify(Object.entries(receipt.source_files).sort())===JSON.stringify(Object.entries(b.source_files).sort()));
 verifySource(path.join(root,'clients/community-mini'),b.source_files);
 return {product_source_sha:b.manifest_sha256,source_type:'FILE_SNAPSHOT_SHA256_NOT_GIT_COMMIT',control_source_sha:env.GITHUB_SHA,source_root:root,fixed_product:true,prepared_files:b.source_files,backend_source_sha:b.backend_source_sha,compatibility:'EXACT_REVIEWED_SNAPSHOT_BACKEND_PAIR',snapshot_binding:b};
}
module.exports={identity};
