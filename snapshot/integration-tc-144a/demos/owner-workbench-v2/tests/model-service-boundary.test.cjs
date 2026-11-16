'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const evidence=path.resolve(root,'../../evidence/official-site-module-flow-20261031');
require(path.join(root,'data.js'));
const app=require(path.join(root,'app.js'));
const data=globalThis.XJ_WORKBENCH_FIXTURE;

test('admin keeps concise summary and has no customer purchase route',()=>{
  const html=app.render(data,{view:'config-models'});
  assert.match(html,/客户购买流程不属于管理后台/);
  assert.match(html,/官网原型 · NOT_DEPLOYED/);
  assert.doesNotMatch(html,/customer-model-service|data-customer-model-mode/);
  assert.equal(app.route('#customer-model-service').view,'overview');
});

test('official-site prototype is separate evidence with truthful boundaries',()=>{
  const html=fs.readFileSync(path.join(evidence,'index.html'),'utf8');
  const js=fs.readFileSync(path.join(evidence,'app.js'),'utf8');
  const css=fs.readFileSync(path.join(evidence,'styles.css'),'utf8');
  for(const text of ['证据原型','待确认','未部署','未验收','选择模块','选择服务方式','购买玄钧AI新 API 服务','无真实购买'])assert.match(html,new RegExp(text));
  assert.match(html,/data-mode="BYO_ACCOUNT"/);
  assert.match(html,/data-mode="XUANJUN_API_SERVICE"/);
  assert.doesNotMatch(html+css,/https?:\/\//i);
  assert.doesNotMatch(js,/fetch\(|XMLHttpRequest|localStorage|CREATE_API_ORDER|ACTIVATE_PROJECT_ENTITLEMENT/);
});
