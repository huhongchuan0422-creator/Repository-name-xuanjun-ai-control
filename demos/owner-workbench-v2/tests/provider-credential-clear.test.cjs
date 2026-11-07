'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const app=require(path.join(root,'app.js'));
const source=fs.readFileSync(path.join(root,'app.js'),'utf8');

test('provider credential clear helper removes the DOM value',()=>{
  const form={elements:{credential:{value:'temporary-secret'}}};
  app.clearProviderCredential(form);
  assert.equal(form.elements.credential.value,'');
});

test('connection-test failure clears credential before preserving error',()=>{
  assert.match(source,/TEST_PROVIDER_CONNECTION[^\n]+\.catch\(function\(error\)\{clearProviderCredential\(providerForm\);setStatus\(error\.message\|\|'连接测试失败',true\);\}/);
});

test('save failure clears credential before preserving error',()=>{
  assert.match(source,/SAVE_PROVIDER_ONBOARDING[^\n]+\.catch\(function\(error\)\{clearProviderCredential\(providerForm\);setStatus\(error\.message\|\|'保存失败',true\);\}/);
});
