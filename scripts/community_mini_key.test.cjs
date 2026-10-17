const {test}=require('node:test');const assert=require('node:assert/strict');const crypto=require('node:crypto');
const {normalizeUploadKey}=require('./community_mini_key.cjs');
const raw=crypto.generateKeyPairSync('rsa',{modulusLength:2048}).privateKey.export({format:'pem',type:'pkcs8'});
test('standard PEM, CRLF, escaped newline and JSON quoted PEM normalize without logging',()=>{
 for(const source of [raw,raw.replace(/\n/g,'\r\n'),raw.replace(/\n/g,'\\n'),JSON.stringify(raw),JSON.stringify(raw.replace(/\n/g,'\\n'))]){
  const key=crypto.createPrivateKey(normalizeUploadKey(source));assert.equal(key.asymmetricKeyType,'rsa');
 }
});
test('public key, certificate and opaque data safely rejected',()=>{
 for(const [source,code]of [['secret-opaque-value','NOT_PEM'],['-----BEGIN CERTIFICATE-----\nnot-a-private-key\n-----END CERTIFICATE-----','CERTIFICATE'],['-----BEGIN PUBLIC KEY-----\nabc\n-----END PUBLIC KEY-----','PUBLIC_KEY']]){
  assert.throws(()=>normalizeUploadKey(source),e=>e.message==='UPLOAD_KEY_'+code&&!e.message.includes('secret-opaque-value'));
 }
});

test('base64 PEM and RSA DER preserve the same public key',()=>{
 const original=crypto.createPrivateKey(raw);
 const der=original.export({format:'der',type:'pkcs8'});
 for(const source of [Buffer.from(raw).toString('base64'),der.toString('base64')]){
  const normalized=crypto.createPrivateKey(normalizeUploadKey(source));
  assert.deepEqual(crypto.createPublicKey(original).export({format:'der',type:'spki'}),crypto.createPublicKey(normalized).export({format:'der',type:'spki'}));
 }
});
