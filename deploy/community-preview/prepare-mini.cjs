'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const ROOT=path.resolve(__dirname,'../..');
const SOURCE=path.join(ROOT,'clients/community-mini');
const OUT=process.env.COMMUNITY_CONNECTED_MINI_OUTPUT;
const HOST='https://community-preview.wenwenwenyiyiyi.work';
if(!OUT)throw Error('OUTPUT_DIRECTORY_REQUIRED');
if(fs.existsSync(OUT))throw Error('OUTPUT_MUST_NOT_EXIST');
fs.cpSync(SOURCE,OUT,{recursive:true,errorOnExist:true,filter:p=>!p.endsWith('.test.cjs')});
const appPath=path.join(OUT,'app.js');
const original=fs.readFileSync(appPath,'utf8');
const needle="App({\n  globalData: {baseUrl: '', token: '', mode: 'WECHAT_LOGIN', payments: false},";
if(!original.includes(needle))throw Error('EXPECTED_APP_BASELINE_REQUIRED');
const replacement="App({\n  globalData: {baseUrl: '"+HOST+"', token: '', mode: 'WECHAT_LOGIN', payments: false, commerce: true},";
const updated=original.replace(needle,replacement);
fs.writeFileSync(appPath,updated);
const receipt={
 status:'CONNECTED_PREVIEW_SOURCE_PREPARED_NOT_UPLOADED',
 baseUrl:HOST,commerce:true,payments:false,scene:'shop1',
 appid:JSON.parse(fs.readFileSync(path.join(OUT,'project.config.json'),'utf8')).appid,
 source_app_sha256:crypto.createHash('sha256').update(original).digest('hex'),
 connected_app_sha256:crypto.createHash('sha256').update(updated).digest('hex'),
 request_domain_change_performed:false,
 upload_performed:false,
 real_wechat_login_verified:false
};
fs.writeFileSync(path.join(OUT,'CONNECTED_PREVIEW_RECEIPT.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(JSON.stringify(receipt));
