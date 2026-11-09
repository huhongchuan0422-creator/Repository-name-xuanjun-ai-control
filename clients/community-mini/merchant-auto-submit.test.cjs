'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const script=fs.readFileSync(__dirname+'/pages/merchant-join/index.js','utf8');
function fixture(handler=async()=>({ok:true})){
 let definition,next=0;const timers=new Map(),calls=[];
 vm.runInNewContext(script,{Page:value=>definition=value,wx:{},require:path=>path==='../../session'?{}:{active:()=>true},setTimeout(fn,ms){const id=++next;timers.set(id,{fn,ms});return id;},clearTimeout(id){timers.delete(id);}});
 const page={...definition,data:structuredClone(definition.data),setData(v){Object.assign(this.data,v);}};
 page.session={merchant:async(...args)=>{calls.push(args);return handler(...args);}};page.scene='shop1';page.epoch=1;page.data.application={application:'synthetic-app'};page.data.ready=true;page.reviewState='SUBMITTED_TO_PROVIDER';page.data.wechatState='APPLYMENT_STATE_AUDITING';page.current=()=>!page.dead;
 for(const name of ['privatePreviewCleanup','clearUploadedOcrRestoreTimer','beginStepScroll','clearOcrTimer','cancelReuse','rememberKnownOcr','invalidateOcr'])page[name]=()=>{};
 page.refreshApplication=async()=>{calls.push(['poll']);};
 return {page,timers,calls,async flush(){for(let n=0;n<10;n++)await Promise.resolve();},async fire(){const [id,timer]=timers.entries().next().value;timers.delete(id);await timer.fn();await Promise.resolve();}};
}
const limited=()=>Object.assign(Error('WECHAT_RATE_LIMITED'),{wechatRateLimited:true});
test('precise unexecuted WeChat rate limit waits exactly one minute then resumes once',async()=>{
 let count=0;const f=fixture(async()=>{if(++count===1)throw limited();return {accepted:true};});f.page.data.pending=true;
 const params={application:'synthetic-app',expected_version:1};const pending=f.page.requestWechatWithRateRecovery('wechat_apply',params);await f.flush();
 assert.equal(f.calls.length,1);assert.equal(f.timers.size,1);assert.equal([...f.timers.values()][0].ms,60000);assert.match(f.page.data.status,/一分钟.*本次请求尚未执行/);assert.equal(f.page.data.pending,true);
 await f.fire();assert.deepEqual(await pending,{accepted:true});assert.equal(f.calls.length,2);assert.equal(f.timers.size,0);assert.equal(f.calls[0][2].params,params);assert.equal(f.calls[1][2].params,params);
});
for(const error of [Object.assign(Error('TIMEOUT'),{networkKind:'TIMEOUT'}),Object.assign(Error('WECHAT_MEDIA_RESULT_UNKNOWN'),{wechatMediaUnknown:true}),Object.assign(Error('SERVICE_RESULT_UNKNOWN'),{uploadResultUnknown:true}),Error('WECHAT_RATE_LIMITED')])test('unknown or untyped failure never retries: '+error.message,async()=>{
 const f=fixture(async()=>{throw error;});await assert.rejects(f.page.requestWechatWithRateRecovery('wechat_apply',{application:'synthetic-app'}),e=>e===error);assert.equal(f.calls.length,1);assert.equal(f.timers.size,0);
});
test('typed rate error cannot retry a non-WeChat write',async()=>{const f=fixture(async()=>{throw limited();});await assert.rejects(f.page.requestWechatWithRateRecovery('save',{}));assert.equal(f.calls.length,1);assert.equal(f.timers.size,0);});
for(const change of ['session','scene','epoch','application','unload'])test('waiting rate recovery refuses changed '+change,async()=>{
 const f=fixture(async()=>{throw limited();});const pending=f.page.requestWechatWithRateRecovery('wechat_apply',{});const rejected=assert.rejects(pending,/STALE_SESSION/);await f.flush();assert.equal(f.timers.size,1);
 if(change==='session')f.page.session={};if(change==='scene')f.page.scene='other';if(change==='epoch')f.page.epoch++;if(change==='application')f.page.data.application={application:'other'};if(change==='unload')f.page.onUnload();
 await f.fire();await rejected;assert.equal(f.calls.length,1);assert.equal(f.timers.size,0);
});
for(const state of ['SUBMITTED_TO_PROVIDER','SUBMISSION_UNKNOWN'])test('active '+state+' page polls at original five-minute interval',async()=>{
 const f=fixture();f.page.reviewState=state;f.page.scheduleProviderPoll();assert.equal(f.timers.size,1);assert.equal([...f.timers.values()][0].ms,300000);await f.fire();assert.deepEqual(f.calls,[['poll']]);assert.equal(f.timers.size,1);f.page.clearProviderPoll();
});
for(const reason of ['hidden','finished','canceled','draft','absent','dead'])test('poll does not start for '+reason,()=>{
 const f=fixture();if(reason==='hidden')f.page.ocrHidden=true;if(reason==='finished')f.page.data.wechatState='APPLYMENT_STATE_FINISHED';if(reason==='canceled')f.page.data.wechatState='APPLYMENT_STATE_CANCELED';if(reason==='draft')f.page.reviewState='DRAFT';if(reason==='absent')f.page.data.application=null;if(reason==='dead')f.page.dead=true;
 f.page.scheduleProviderPoll();assert.equal(f.timers.size,0);assert.equal(f.calls.length,0);
});
for(const lifecycle of ['onHide','onUnload'])test(lifecycle+' clears existing poll and stale queued callback cannot request',async()=>{
 const f=fixture();f.page.scheduleProviderPoll();const callback=[...f.timers.values()][0].fn;f.page[lifecycle]();assert.equal(f.timers.size,0);await callback();assert.equal(f.calls.length,0);
});
test('busy page skips poll and schedules later; terminal response stops polling',async()=>{
 const f=fixture();f.page.data.pending=true;f.page.scheduleProviderPoll();await f.fire();assert.equal(f.calls.length,0);assert.equal(f.timers.size,1);f.page.data.pending=false;f.page.refreshApplication=async()=>{f.calls.push(['poll']);f.page.data.wechatState='APPLYMENT_STATE_FINISHED';};await f.fire();assert.deepEqual(f.calls,[['poll']]);assert.equal(f.timers.size,0);
});
for(const change of ['session','application'])test('scheduled poll refuses changed '+change,async()=>{const f=fixture();f.page.scheduleProviderPoll();if(change==='session')f.page.session={};else f.page.data.application={application:'other'};await f.fire();assert.equal(f.calls.length,0);assert.equal(f.timers.size,0);});
test('submit feedback displays detailed rate recovery status even while pending',()=>{
 const markup=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');const feedback=markup.match(/class="status-notice submit-feedback"[^>]*><text>(.*?)<\/text>/);assert.ok(feedback);assert.equal(feedback[1],"{{status||(pending?'正在处理，请稍候。':'')}}");assert.doesNotMatch(feedback[1],/^{{pending\?/);
});
