'use strict';
// Development preview only: no release, payment or server deployment API.
const {normalizeUploadKey}=require('./community_mini_key.cjs');
const fs=require('node:fs');const path=require('node:path');const crypto=require('node:crypto');
async function main(){
 const destination=process.env.COMMUNITY_PREVIEW_OUTPUT;
 if(!destination)throw Error('OUTPUT_DIRECTORY_REQUIRED');
 fs.mkdirSync(destination,{recursive:true,mode:0o700});
 const projectPath=path.resolve('clients/community-mini');
 const config=JSON.parse(fs.readFileSync(path.join(projectPath,'project.config.json'),'utf8'));
 const appid=process.env.WECHAT_MINIPROGRAM_APPID||config.appid;
 const receipt={head:process.env.GITHUB_SHA||null,appid,operation:'DEVELOPMENT_PREVIEW_ONLY',
   public_release:false,payment_enabled:false,source_hashes:{},status:'NOT_RUN'};
 function source(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){
  const file=path.join(dir,entry.name);if(entry.isSymbolicLink())throw Error('SYMLINK_SOURCE_DENIED');
  if(entry.isDirectory())source(file);else if(!file.endsWith('.test.cjs'))receipt.source_hashes[path.relative(projectPath,file)]=crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
 }}
 source(projectPath);
 const save=()=>fs.writeFileSync(path.join(destination,'receipt.json'),JSON.stringify(receipt,null,2));
 if(appid!==config.appid){receipt.status='APPID_BINDING_MISMATCH';save();process.exitCode=2;return;}
 let key=process.env.WECHAT_MINIPROGRAM_PRIVATE_KEY;
 if(!key){receipt.status='UPLOAD_KEY_NOT_AVAILABLE';save();console.log('MINI_PREVIEW_STATUS='+receipt.status);process.exitCode=2;return;}
 try{key=normalizeUploadKey(key);}
 catch(e){receipt.status=/^UPLOAD_KEY_[A-Z_]+$/.test(e.message)?e.message:'UPLOAD_KEY_PARSE_FAILED';save();console.log('MINI_PREVIEW_STATUS='+receipt.status);process.exitCode=2;return;}
 const ci=require(path.join(process.env.COMMUNITY_MINI_CI_MODULE_ROOT,'node_modules/miniprogram-ci'));
 const log=console.log,error=console.error,warn=console.warn;
 const stdout=process.stdout.write,stderr=process.stderr.write;
 try{
  console.log=console.error=console.warn=()=>{};
  process.stdout.write=process.stderr.write=()=>true;
  const project=new ci.Project({appid,type:'miniProgram',projectPath,privateKey:key,
    ignores:['**/*.test.cjs','node_modules/**/*']});
  await ci.preview({project,desc:'Community phase integration '+String(receipt.head).slice(0,12),
    setting:{es6:true,es7:true,minify:true},robot:1,threads:1,
    qrcodeFormat:'image',qrcodeOutputDest:path.join(destination,'preview.png'),
    pagePath:'pages/home/index',searchQuery:'scene=shop1',onProgressUpdate:()=>{}});
  if(!fs.existsSync(path.join(destination,'preview.png')))throw Error('PREVIEW_QR_MISSING');
  receipt.status='DEVELOPMENT_PREVIEW_UPLOADED';
 }catch(e){
  const message=String(e&&(e.errMsg||e.message)||'');
  receipt.status=/ip|whitelist|白名单/i.test(message)?'UPLOAD_IP_NOT_ALLOWED':'PREVIEW_FAILED_OR_UNKNOWN';
  const code=e&&(e.errCode||e.code);if(Number.isSafeInteger(code))receipt.provider_error_code=code;
  process.exitCode=3;
 }finally{
  console.log=log;console.error=error;console.warn=warn;process.stdout.write=stdout;process.stderr.write=stderr;
  key=null;delete process.env.WECHAT_MINIPROGRAM_PRIVATE_KEY;save();
 }
 log('MINI_PREVIEW_STATUS='+receipt.status);
}
main().catch(()=>{console.error('MINI_PREVIEW_STATUS=LOCAL_PREVIEW_SETUP_FAILED');process.exitCode=4;});
