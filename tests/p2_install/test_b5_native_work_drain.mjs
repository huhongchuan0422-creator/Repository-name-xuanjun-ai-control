/** Scheduling fixtures test our glue only; no archived SDK/class is evaluated. */
import assert from 'node:assert/strict';
import {createNativeGatewayDrain} from '../../production/p2_install/b5_native_work_drain.mjs';
let count=0;
for(const mode of ['ok','wrong-owner','active','unknown-active','begin-result','drain-void','drain-result','drain-reject','pending']){
 let resolve;const gate=new Promise(r=>{resolve=r;});const events=[],controller=new AbortController();
 const owner={hasPendingWork:true,isClosing:false,signal:controller.signal,beginClose(){events.push('begin');this.isClosing=true;controller.abort();if(mode==='begin-result')return true;},drain(){events.push('drain');if(mode==='drain-void')return;return gate.then(()=>{events.push('cleanup-settled');if(mode==='drain-reject')throw Error('native-cleanup-failure');this.hasPendingWork=mode==='pending';if(mode==='drain-result')return true;});}};
 const fn=createNativeGatewayDrain({connectionWork:owner,isActiveHere:w=>{assert.equal(w,owner);return mode==='active'?true:mode==='unknown-active'?undefined:false;}});
 const promise=fn({connectionWork:mode==='wrong-owner'?{}:owner});const rejected=mode==='ok'?null:assert.rejects(promise);
 await new Promise(r=>setImmediate(r));
 if(['wrong-owner','active','unknown-active'].includes(mode))assert.deepEqual(events,[]);
 else if(mode==='begin-result')assert.deepEqual(events,['begin']);
 else assert.deepEqual(events,['begin','drain']);
 resolve();if(rejected)await rejected;else {assert.equal(await promise,undefined);assert.equal(owner.hasPendingWork,false);assert.deepEqual(events,['begin','drain','cleanup-settled']);}count++;
}
assert.throws(()=>createNativeGatewayDrain({connectionWork:{},isActiveHere:()=>false}),/INTERFACE/);count++;
console.log(JSON.stringify({affected_cases:count,scope:'ADAPTER_CONTRACT_ONLY',real_owner_binding:'UNBOUND',sdk:'NOT_EXECUTED'}));
