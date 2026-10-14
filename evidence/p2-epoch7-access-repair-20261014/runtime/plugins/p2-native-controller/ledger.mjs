import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {lstatSync,readFileSync,realpathSync,openSync,closeSync,fstatSync,readSync,constants} from 'node:fs';
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

const SDK_HOME='/home/xuanjun_dev';
const SDK_ROOT=SDK_HOME+'/.openclaw/tools/';
export const SDK_FILE_MAX_BYTES=8*1024*1024;
const SDK_READ_BYTES=64*1024;
export function validateSdkParent(parent, expectedUid, info) {
  if(!Number.isSafeInteger(expectedUid)||expectedUid<=0)throw new Error('HOLD_SDK_UID');
  const within=parent===SDK_HOME||parent.startsWith(SDK_HOME+'/');
  if(!info.isDirectory()||(info.mode&0o022)||
      !(info.uid===0||(within&&info.uid===expectedUid)))throw new Error('HOLD_SDK_PARENT');
  if((parent===SDK_HOME||parent===SDK_HOME+'/.openclaw')&&info.uid!==expectedUid)
    throw new Error('HOLD_SDK_HOME_IDENTITY');
}
export function protectedSdkFile(file,sha256,expectedUid,homeUid=expectedUid) {
  if(!Number.isSafeInteger(homeUid)||homeUid<=0||!Number.isSafeInteger(expectedUid)||
      !(expectedUid===0||expectedUid===homeUid)||!path.isAbsolute(file)||
      !file.startsWith(SDK_ROOT)||realpathSync(file)!==file)throw new Error('HOLD_SDK_PATH');
  if(!/^[0-9a-f]{64}$/.test(sha256??''))throw new Error('HOLD_SDK_HASH');
  const parentInfo=parent=>{
    const info=lstatSync(parent,{bigint:true});
    validateSdkParent(parent,homeUid,{uid:Number(info.uid),mode:Number(info.mode),
      isDirectory:()=>info.isDirectory()});
    return info;
  };
  const identity=(a,b,fields)=>fields.every(field=>a[field]===b[field]);
  const parentFields=['dev','ino','mode','uid','gid'];
  const fileFields=[...parentFields,'nlink','size','mtimeNs','ctimeNs'];
  const checkFile=info=>{
    if(!info.isFile()||info.uid!==BigInt(expectedUid)||(info.mode&0o022n)||
       info.nlink!==1n||info.size<0n||info.size>BigInt(SDK_FILE_MAX_BYTES))
      throw new Error('HOLD_SDK_FILE');
  };
  const parents=[];
  for(let parent=path.dirname(file);;parent=path.dirname(parent)) {
    parents.push([parent,parentInfo(parent)]);if(parent==='/')break;
  }
  const before=lstatSync(file,{bigint:true});checkFile(before);
  if(!Number.isInteger(constants.O_NOFOLLOW)||!Number.isInteger(constants.O_NONBLOCK))
    throw new Error('HOLD_SDK_OPEN_FLAGS');
  let fd;
  try {
    fd=openSync(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
    const opened=fstatSync(fd,{bigint:true});checkFile(opened);
    if(!identity(before,opened,fileFields))throw new Error('HOLD_SDK_FILE_CHANGED');
    const hash=createHash('sha256'),buffer=Buffer.alloc(SDK_READ_BYTES);
    let total=0;
    for(;;) {
      // At most limit+1 bytes, including the growth/EOF probe; never readFile(path).
      const count=readSync(fd,buffer,0,Math.min(buffer.length,SDK_FILE_MAX_BYTES+1-total),null);
      if(count===0)break;
      total+=count;if(total>SDK_FILE_MAX_BYTES)throw new Error('HOLD_SDK_FILE_BOUND');
      hash.update(buffer.subarray(0,count));
    }
    const after=fstatSync(fd,{bigint:true});checkFile(after);
    if(BigInt(total)!==opened.size||!identity(opened,after,fileFields))
      throw new Error('HOLD_SDK_FILE_CHANGED');
    if(realpathSync(file)!==file)throw new Error('HOLD_SDK_PATH_CHANGED');
    const current=lstatSync(file,{bigint:true});checkFile(current);
    if(!identity(after,current,fileFields))throw new Error('HOLD_SDK_FILE_CHANGED');
    for(const [parent,prior] of parents) {
      if(!identity(prior,parentInfo(parent),parentFields))throw new Error('HOLD_SDK_PARENT_CHANGED');
    }
    if(hash.digest('hex')!==sha256)throw new Error('HOLD_SDK_HASH');
  } finally {
    if(fd!==undefined)closeSync(fd);
  }
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
