'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {splitChoiceSnapshot:snapshot,splitChoiceDraft:save}=require('../../tests/community_mini_native_render.cjs');
test('native trace keeps omitted JSON fields absent rather than undefined properties',()=>{
 for(const input of [{},{split_participation:undefined,requested_split_bps:undefined},{unrelated:1}]){
  const trace=snapshot(input);assert.deepEqual(trace,{});assert.deepEqual(Object.getOwnPropertyNames(trace),[]);
 }
 assert.deepEqual(snapshot({split_participation:null,requested_split_bps:null}),{split_participation:null,requested_split_bps:null});
 assert.deepEqual(snapshot({split_participation:false,requested_split_bps:0}),{split_participation:false,requested_split_bps:0});
});
test('unmodified positive and explicit zero remain unchanged across unrelated fixture save',()=>{
 for(const previous of [{split_participation:true,requested_split_bps:275,effective_split_bps:250},{split_participation:false,requested_split_bps:0,effective_split_bps:0}]){
  const before=structuredClone(previous);assert.deepEqual(save({},previous),previous);assert.deepEqual(previous,before);
 }
 assert.deepEqual(save({},{}),{split_participation:false,requested_split_bps:0,effective_split_bps:0});
});
test('explicit null is not omitted and never erases a previous fixture choice',()=>{
 const previous={split_participation:true,requested_split_bps:275,effective_split_bps:0},before=structuredClone(previous);
 for(const params of [{split_participation:null},{requested_split_bps:null},{split_participation:null,requested_split_bps:null}])assert.throws(()=>save(params,previous),/INVALID_SPLIT_PARTICIPATION/);
 assert.deepEqual(previous,before);
 assert.deepEqual(save({split_participation:false,requested_split_bps:0},previous),{split_participation:false,requested_split_bps:0,effective_split_bps:0});
});
test('fixture matches strict original boolean/integer and ratio consistency contract',()=>{
 for(const params of [{split_participation:1,requested_split_bps:50},{split_participation:true,requested_split_bps:'50'},{split_participation:true,requested_split_bps:1.5},{split_participation:true,requested_split_bps:10001}])assert.throws(()=>save(params),/INVALID_SPLIT_PARTICIPATION/);
 for(const params of [{split_participation:true,requested_split_bps:0},{split_participation:false,requested_split_bps:50}])assert.throws(()=>save(params),/SPLIT_PARTICIPATION_RATIO_MISMATCH/);
});
