'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'../clients/community-mini');
let definition;
const auth={current:()=>1,active:()=>true};
const form={};
vm.runInNewContext(fs.readFileSync(path.join(root,'pages/merchant-join/index.js'),'utf8'),{
  Page:value=>definition=value,wx:{},getApp:()=>({globalData:{}}),getCurrentPages:()=>[],encodeURIComponent,
  require:value=>value==='../../session'?{}:value==='../../customer-auth'?auth:value==='../../merchant-form'?form:
    value==='../../merchant-submit'?{}:value==='../../merchant-official-fields'?{}:
    value==='../../merchant-platform-reference.json'?{appid:'fixture'}:require(value)
});
const calls=[];
const page={...definition,data:{application:null,canEditPlatform:true},session:{merchant:(scene,operation,body)=>{calls.push({scene,operation,body});return body;}},scene:'shop',
  setData(value){Object.assign(this.data,value);},syncLeaveGuard(){}};
page.chooseRedemption({currentTarget:{dataset:{value:'25'}}});
assert.equal(page.data.pendingRedemptionPercent,25);
page.request('save',{application:null,revision:0});
assert.equal(calls[0].body.params.redemption_percent,25);
page.chooseRedemption({currentTarget:{dataset:{value:'15'}}});
assert.equal(page.data.pendingRedemptionPercent,25,'unsupported tier must not replace current application choice');
const wxml=fs.readFileSync(path.join(root,'pages/merchant-join/index.wxml'),'utf8');
for(const tier of ['0','10','20','25','30'])assert(wxml.includes('data-value="'+tier+'"'));
assert(wxml.includes('爱心积分抵扣比例（审核生效）'));
assert(!wxml.includes('积分商城抵扣比例'));
assert(!wxml.includes('申请抵扣比例'));
const adminHtml=fs.readFileSync(path.resolve(__dirname,'../demos/community-stage/onboarding.html'),'utf8');
const adminJs=fs.readFileSync(path.resolve(__dirname,'../demos/community-stage/onboarding.js'),'utf8');
for(const tier of ['0','10','20','25','30'])assert(adminHtml.includes('value="'+tier+'"'));
assert(adminJs.includes('爱心积分抵扣比例'));
assert(!adminJs.includes('申请积分抵扣比例'));
assert(!adminJs.includes('积分商城申请抵扣比例'));
console.log('POINTS_APPLICATION_DOM_OK application tiers, save payload, mini review and admin review display');
