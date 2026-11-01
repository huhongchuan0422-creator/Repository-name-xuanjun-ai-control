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
assert.equal(page.data.pendingRedemptionPercent,25);
const wxml=fs.readFileSync(path.join(root,'pages/merchant-join/index.wxml'),'utf8');
for(const tier of ['0','10','20','25','30'])assert(wxml.includes('data-value="'+tier+'"'));
assert(wxml.includes('后台获批比例'));
console.log('POINTS_MINI_UPLOAD_DOM_OK');
