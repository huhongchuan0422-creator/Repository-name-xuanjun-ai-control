'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const ROOT=path.resolve(__dirname,'../..');
const SOURCE=path.join(ROOT,'clients/community-mini');
const OUT=process.env.COMMUNITY_CONNECTED_MINI_OUTPUT;
const {endpoint,sourceManifest}=require('./endpoint.cjs');
const target=endpoint();
const HOST=target.baseUrl;
if(!OUT)throw Error('OUTPUT_DIRECTORY_REQUIRED');
function absent(p){try{fs.lstatSync(p);return false;}catch(e){if(e.code==='ENOENT')return true;throw e;}}
if(!absent(OUT))throw Error('OUTPUT_MUST_NOT_EXIST');
// Reject links before copying; do not leave an uploadable partial tree on validation failure.
function inspect(p){
 const s=fs.lstatSync(p);
 if(s.isSymbolicLink())throw Error('SOURCE_SYMLINK_DENIED');
 if(s.isDirectory()){for(const n of fs.readdirSync(p))inspect(path.join(p,n));}
 else if(!s.isFile())throw Error('SOURCE_REGULAR_FILE_REQUIRED');
}
inspect(SOURCE);
const required=['app.js','app.json','app.wxss','session.js','project.config.json'];
const config=JSON.parse(fs.readFileSync(path.join(SOURCE,'project.config.json'),'utf8'));
if(config.appid!=='wx1d5f8873eaea5392'||config.compileType!=='miniprogram'||config.miniprogramRoot!=='./')throw Error('EXPECTED_MINI_PROJECT_REQUIRED');
const pages=JSON.parse(fs.readFileSync(path.join(SOURCE,'app.json'),'utf8')).pages;
if(!Array.isArray(pages)||!pages.includes('pages/home/index'))throw Error('HOME_ENTRY_REQUIRED');
for(const page of pages){
 if(typeof page!=='string'||!/^pages\/[a-z0-9_-]+\/index$/.test(page))throw Error('SAFE_PAGE_PATH_REQUIRED');
 for(const ext of ['.js','.json','.wxml'])required.push(page+ext);
}
for(const name of required)if(!fs.lstatSync(path.join(SOURCE,name)).isFile())throw Error('REQUIRED_MINI_FILE_MISSING');
const original=fs.readFileSync(path.join(SOURCE,'app.js'),'utf8');
const needle="App({\n  globalData: {baseUrl: '', token: '', mode: 'WECHAT_LOGIN', payments: false},";
if(!original.includes(needle))throw Error('EXPECTED_APP_BASELINE_REQUIRED');
const replacement="App({\n  globalData: {baseUrl: '"+HOST+"', token: '', mode: 'WECHAT_LOGIN', payments: false, commerce: true},";
const updated=original.replace(needle,replacement);
const receipt={
 status:'CONNECTED_PREVIEW_SOURCE_PREPARED_NOT_UPLOADED',
 ...target,commerce:true,payments:false,scene:'shop1',
 appid:config.appid,
 source_app_sha256:crypto.createHash('sha256').update(original).digest('hex'),
 connected_app_sha256:crypto.createHash('sha256').update(updated).digest('hex'),
 request_domain_change_performed:false,
 upload_performed:false,
 real_wechat_login_verified:false
};
// OUT is published only after all preparation succeeds. The parent must already exist.
const temp=fs.mkdtempSync(path.join(path.dirname(path.resolve(OUT)),'.connected-mini-'));
try{
 fs.cpSync(SOURCE,temp,{recursive:true,errorOnExist:true,force:false,filter:p=>!p.endsWith('.test.cjs')});
 fs.writeFileSync(path.join(temp,'app.js'),updated);
 receipt.prepared_files=sourceManifest(temp);
 fs.writeFileSync(path.join(temp,'CONNECTED_PREVIEW_RECEIPT.json'),JSON.stringify(receipt,null,2)+'\n');
 if(!absent(OUT))throw Error('OUTPUT_MUST_NOT_EXIST');
 fs.renameSync(temp,OUT);
}finally{fs.rmSync(temp,{recursive:true,force:true});}
console.log(JSON.stringify(receipt));
