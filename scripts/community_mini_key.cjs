'use strict';
const crypto=require('node:crypto');
function normalizeUploadKey(raw){
 if(typeof raw!=='string'||raw.length>65536)throw Error('UPLOAD_KEY_FORMAT_INVALID');
 let text=raw.trim();
 if(text.startsWith('"')){
  try{text=JSON.parse(text);if(typeof text!=='string')throw Error();}
  catch(_){throw Error('UPLOAD_KEY_QUOTING_INVALID');}
 }
 text=text.trim().replace(/\\r\\n/g,'\n').replace(/\\n/g,'\n').replace(/\r\n/g,'\n');
 try{const key=crypto.createPrivateKey(text);if(key.asymmetricKeyType!=='rsa')throw Error();}
 catch(_){
  const kind=text.startsWith('-----BEGIN CERTIFICATE-----')?'CERTIFICATE':text.startsWith('-----BEGIN PUBLIC KEY-----')?'PUBLIC_KEY':text.startsWith('-----BEGIN ENCRYPTED PRIVATE KEY-----')?'ENCRYPTED_KEY':text.startsWith('-----BEGIN')?'PEM_UNPARSEABLE':'NOT_PEM';
  throw Error('UPLOAD_KEY_'+kind);
 }
 return text;
}
module.exports={normalizeUploadKey};
