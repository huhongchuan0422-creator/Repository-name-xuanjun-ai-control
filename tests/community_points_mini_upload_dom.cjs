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
const page={...definition,data:{...JSON.parse(JSON.stringify(definition.data)),application:null,canEditPlatform:true},session:{merchant:(scene,operation,body)=>{calls.push({scene,operation,body});return body;}},scene:'shop',
  setData(value){Object.assign(this.data,value);},syncLeaveGuard(){}};
const wxml=fs.readFileSync(path.join(root,'pages/merchant-join/index.wxml'),'utf8');
const pickers=[...wxml.matchAll(/<picker\b([^>]*class="redemption-picker"[^>]*)>/g)];
assert.equal(pickers.length,1,'one original dynamic points picker');
const attrs=Object.fromEntries([...pickers[0][1].matchAll(/([:\w-]+)="([^"]*)"/g)].map(x=>[x[1],x[2]]));
assert.equal(attrs.range,'{{redemptionOptions}}');assert.equal(attrs.value,'{{redemptionIndex}}');
assert.equal(attrs.bindchange,'chooseRedemption');assert.equal(attrs.disabled,'{{pending||!canEditPlatform}}');
assert.equal(attrs['aria-label'],'爱心积分抵扣收款金额比例');
assert.deepEqual(page.data.redemptionOptions,['0%','10%','20%','25%','30%']);
assert.equal(page.data.pendingRedemptionPercent,10);assert.equal(page.data.redemptionIndex,1);
// Actual picker emits an index, not the former button's data-value attribute.
// The original request handler must persist every supported tier independently
// of an existing donation choice, including explicit points0.
page.data.application={application:'synthetic',split_participation:true,requested_split_bps:275};
page.data.splitInput='2.75';page.data.splitChoiceEdited=false;
for(const [index,tier] of [0,10,20,25,30].entries()){
 page[attrs.bindchange]({currentTarget:{dataset:{}},detail:{value:String(index)}});
 assert.equal(page.data.pendingRedemptionPercent,tier);assert.equal(page.data.redemptionIndex,index);
 page.request('save',{application:'synthetic',revision:index});
 const params=calls.at(-1).body.params;assert.equal(params.redemption_percent,tier);
 assert.equal(Object.hasOwn(params,'split_participation'),false);assert.equal(Object.hasOwn(params,'requested_split_bps'),false);
 assert.equal(page.data.splitInput,'2.75');assert.equal(page.data.application.requested_split_bps,275);
}
for(const value of ['-1','5','1.5','invalid']){
 page[attrs.bindchange]({currentTarget:{dataset:{}},detail:{value}});
 assert.equal(page.data.pendingRedemptionPercent,30);assert.equal(page.data.redemptionIndex,4);
}
// Retain the existing button-event compatibility check and invalid tier gate.
page.chooseRedemption({currentTarget:{dataset:{value:'25'}}});assert.equal(page.data.pendingRedemptionPercent,25);
page.chooseRedemption({currentTarget:{dataset:{value:'15'}}});assert.equal(page.data.pendingRedemptionPercent,25);
for(const state of [{pending:true,canEditPlatform:true},{pending:false,canEditPlatform:false}]){
 Object.assign(page.data,state,{dirty:false});
 page[attrs.bindchange]({currentTarget:{dataset:{}},detail:{value:'0'}});
 assert.equal(page.data.pendingRedemptionPercent,25);assert.equal(page.data.dirty,false);
}
assert(wxml.includes('爱心积分抵扣收款金额比例（申请值）'));
console.log('POINTS_MINI_UPLOAD_DOM_OK');
