import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {lstatSync,readFileSync,realpathSync} from 'node:fs';
import path from 'node:path';
import {canonical} from './canonical.mjs';
import {strictJson} from './strict-json.mjs';

export function protectedFile(file,sha256,executable=false,expectedUid=0) {
  if(!path.isAbsolute(file)||realpathSync(file)!==file)throw new Error('HOLD_HOST_PATH');
  let parent=path.dirname(file);
  for(;;){const info=lstatSync(parent);if(!info.isDirectory()||info.uid!==0||(info.mode&0o022))throw new Error('HOLD_HOST_PARENT');if(parent==='/')break;parent=path.dirname(parent);}
  const info=lstatSync(file);
  if(!Number.isSafeInteger(expectedUid)||expectedUid<0||!info.isFile()||info.uid!==expectedUid||(info.mode&0o022)||(executable&&!(info.mode&0o111)))throw new Error('HOLD_HOST_FILE');
  const raw=readFileSync(file);
  if(!/^[0-9a-f]{64}$/.test(sha256??'')||createHash('sha256').update(raw).digest('hex')!==sha256)throw new Error('HOLD_HOST_HASH');
}

/** Reuse existing SQLite task checkpoint, through its installed Python API. */
export class CanonicalLedgerStore {
  constructor({python,pythonSha256,bridge,config,files,invoke=execFileSync}) {
    this.python=python;this.pythonSha256=pythonSha256;this.bridge=bridge;
    this.config=config;this.files=files;this.invoke=invoke;
    if(!files||!Object.hasOwn(files,bridge)||!Object.hasOwn(files,config))throw new Error('HOLD_BRIDGE_MANIFEST');
  }
  call(operation,request,extra={}) {
    protectedFile(this.python,this.pythonSha256,true);
    for(const [file,hash] of Object.entries(this.files))protectedFile(file,hash);
    let raw;
    try {raw=this.invoke(this.python,['-B',this.bridge,'--config',this.config],{
      input:canonical({operation,request,...extra}),encoding:'utf8',timeout:15000,maxBuffer:1048576,
      env:{HOME:'/home/xuanjun_dev',PATH:'/usr/bin:/bin',LANG:'C.UTF-8'}});}
    catch{throw new Error('HOLD_CANONICAL_BRIDGE');}
    return strictJson(raw);
  }
  async read(binding){return this.call('read',binding);}
  async receipt(binding){return this.call('receipt',binding);}
  async replace(observed,task){
    return this.call('cas',observed.request,{expected:observed.native_expected,execution:task.native_execution});
  }
  guard(request){return this.call('guard',request)===true;}
}
