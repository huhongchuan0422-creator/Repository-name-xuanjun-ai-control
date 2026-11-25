const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{createRequire}=require('node:module');
const root=__dirname,file=path.join(root,'merchant-bank-picker.test.cjs'),original=fs.readFileSync(file,'utf8');
const prefix=original.split("const test=require('node:test');")[0],source=fs.readFileSync(path.join(root,'pages/merchant-join/index.js'),'utf8');
function make(fullSave=false){const code=fullSave?prefix.replace(",'finishConfirmedOcrSave'",''):prefix;return new Function('require','__dirname',code+';return fixture;')(createRequire(file),root)(source);}
const event={currentTarget:{dataset:{kind:'bank_card'}}};
const outcome=(status='needs_review')=>({job_id:'synthetic-job',document_type:'bank_card',application_revision:'8',provider_version:3,status,fields:{account_number:{value:'SYNTHETIC ACCOUNT'},account_bank:{value:'SYNTHETIC BANK'}}});
// Explicit synthetic legacy job for unchanged persisted-job confirmation/recovery guards.
async function uploaded(f){const p=f.page.upload(event);f.pick();await p;await f.page.recognizeCurrentDocument('bank_card',{newIntent:true,uploadedMaterial:true});}
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
test('review bank: current-material restoration must reach existing recover_view without creating or reuploading',async()=>{
 const f=make();f.page.data.application.materials.bank_card={object_id:'synthetic-object'};
 f.page.session.merchant=async(scene,op,p)=>{f.calls.push({op,action:p.action});return {result:outcome()};};
 await f.page.recognizeCurrentDocument('bank_card',{existingMaterial:true});
 console.log('RESTORE_ACTUAL',JSON.stringify({calls:f.calls,rows:f.page.data.ocrRows.length,status:f.page.data.ocrStatus}));
 assert.deepEqual(f.calls.map(c=>c.action),['recover_view'],'must consume protected recovery API rather than a local no-op');
 assert.equal(f.calls.some(c=>c.action==='submit'||c.op==='upload'),false);
});
test('review bank: rebuilt known-job capture must still reject a late result after provider drift',async()=>{
 const f=make();await uploaded(f);f.page.rememberKnownOcr();f.page.invalidateOcr();const d=deferred(),entered=deferred(),actions=[];
 f.page.session.merchant=async(scene,op,p)=>{actions.push(p.action);if(p.action==='read'){entered.resolve();return d.promise;}return {result:{job_id:p.job_id,status:'confirmed',recorded:true,revision:p.revision,application_revision:p.application_revision,provider_version:p.provider_version}};};
 const restoring=f.page.restoreKnownOcr();await entered.promise;f.page.version++;
 d.resolve({result:outcome()});await restoring;
 const staleRows=f.page.data.ocrRows.length,count=actions.length;await f.page.confirmOcr();
 console.log('RESTORED_PROVIDER_DRIFT',JSON.stringify({actions,providerVersion:f.page.version,bound:f.page.ocrCapture&&f.page.ocrCapture.bound_provider_version,rows:f.page.data.ocrRows.map(r=>({key:r.key,value:r.value}))}));
 assert.equal(staleRows,0,'late old-provider result must not repopulate suggestions after restore');
 assert.equal(actions.length,count,'drift must also block a confirmation request');
});
test('review bank: persisted bank failure must project to the new bank error surface',()=>{
 const f=make(),p=f.page;p.data.application.materials={bank_card:{object_id:'synthetic-bank-object'},business_license:{object_id:'synthetic-license-object'}};
 const q={session:p.session,sessionGeneration:p.session.getGeneration(),scene:p.scene,epoch:p.epoch,application:p.data.application.application,revision:p.data.application.revision,version:p.version,items:[],failures:{}};
 q.failures.bank_card={source:p.ocrSource('bank_card'),text:'SYNTHETIC BANK FAILURE'};q.failures.business_license={source:p.ocrSource('business_license'),text:'SYNTHETIC LICENSE FAILURE'};p.ocrRestoreQueue=q;
 assert.equal(p.uploadedOcrRestoreCurrent(q),true);const visible=p.materialOcrFailureView();console.log('BANK_FAILURE_SURFACE',JSON.stringify(visible));
 assert.equal(visible.business_license.text,'SYNTHETIC LICENSE FAILURE');assert.ok(visible.bank_card,'new bank WXML error surface must receive its persisted failure');
});
test('review bank: actual 5000ms timer callback terminates selection and a late onShow cannot upload',async()=>{
 const f=make(),upload=f.page.upload(event);f.page.onHide();f.pick();for(let i=0;i<12;i++)await Promise.resolve();
 const timeout=[...f.timers.values()].find(t=>t.ms===5000);assert.ok(timeout);timeout.fn();await upload;f.page.onShow();
 assert.equal(f.page.pendingPickerShow,null);assert.equal(f.page.data.pending,false);assert.equal(f.calls.length,0);assert.match(f.page.data.status,/未上传/);
});
test('review bank: real confirmAndSave helper chain requires human confirmation and preserves existing manual values',async()=>{
 const f=make(true);await uploaded(f);f.page.profile={bank_account_info:{account_number:'MANUAL SYNTHETIC'}};let confirmed=false,saves=0;const actions=[];
 f.page.session.merchant=async(scene,op,p)=>{actions.push(p.action);if(p.action==='confirm'){confirmed=true;return {result:{job_id:p.job_id,status:'confirmed',recorded:true,revision:p.revision,application_revision:p.application_revision,provider_version:p.provider_version}};}const r=outcome(confirmed?'confirmed':'needs_review');if(confirmed){r.confirmation_revision=1;r.confirmed_fields={account_number:'SYNTHETIC ACCOUNT',account_bank:'SYNTHETIC BANK'};}return {result:r};};
 f.page.saveDraft=async()=>{saves++;f.page.data.dirty=false;};
 assert.equal(saves,0);await f.page.confirmAndSaveOcr();
 console.log('HUMAN_SAVE_CHAIN',JSON.stringify({actions,saves,account:f.page.profile.bank_account_info}));
 assert.equal(actions.filter(a=>a==='confirm').length,1);assert.ok(actions.includes('read'));assert.equal(saves,1);assert.equal(f.page.profile.bank_account_info.account_number,'MANUAL SYNTHETIC');assert.equal(f.page.profile.bank_account_info.account_bank,'SYNTHETIC BANK');
});
const digest='a'.repeat(64);
function recoveryFixture(){
 const f=make(true),p=f.page;const material={uploaded:true,object_id:'synthetic-object',sha256:digest};p.data.application.materials.bank_card=material;
 let view,confirmation;const actions=[];
 p.session.merchant=async(scene,op,q)=>{
  actions.push(structuredClone(q));assert.equal(op,'ocr');assert.equal(q.application,'synthetic-app');
  if(q.action==='recover_view'){
   assert.deepEqual(Object.keys(q).sort(),['action','application','document_type','locator','recovery_key']);
   view={recovery_id:q.recovery_key,revision:1,job_id:'synthetic-job',original_application_revision:'6',original_provider_version:2,binding:{application_revision:'7',provider_version:3,document_type:'bank_card',attachment_id:'synthetic-object',content_sha256:digest},fields:{account_number:{value:'SYNTHETIC ACCOUNT'},account_bank:{value:'SYNTHETIC BANK'}},status:'needs_review',confirmed:false,requires_human_confirmation:true,authenticity_verified:false};return {result:structuredClone(view)};
  }
  if(q.action==='recover_confirm'){
   assert.deepEqual(Object.keys(q).sort(),['action','application','confirmation_key','fields','recovery_id','revision']);assert.equal(q.recovery_id,view.recovery_id);assert.equal(q.revision,view.revision);
   confirmation={...view,confirmation_id:q.confirmation_key,confirmation_revision:1,confirmed_fields:{...q.fields},status:'confirmed',confirmed:true};return {result:structuredClone(confirmation)};
  }
  if(q.action==='recover_apply'){
   assert.deepEqual(Object.keys(q).sort(),['action','application','confirmation_id','confirmation_revision','recovery_id','writeback_key']);assert.equal(q.recovery_id,view.recovery_id);assert.equal(q.confirmation_id,confirmation.confirmation_id);assert.equal(q.confirmation_revision,1);
   const bank=p.profile.bank_account_info||(p.profile.bank_account_info={});for(const [k,v] of Object.entries(confirmation.confirmed_fields))if(!bank[k])bank[k]=v;
   return {result:{written:true,application_revision:8,wechat_version:4,applied:['account_bank'],skipped:['account_number']}};
  }
  throw Error('NO_SUBMIT_UPLOAD_OR_OTHER_ACTION');
 };
 return {...f,actions};
}
test('fix F01: actual nested recovery view renders and real human confirm/apply preserves filled account',async()=>{
 const f=recoveryFixture(),p=f.page;p.profile={bank_account_info:{account_number:'MANUAL SYNTHETIC'}};
 await p.recognizeCurrentDocument('bank_card',{existingMaterial:true});
 assert.equal(f.actions.length,1);assert.equal(f.actions[0].locator.current_material,true);assert.equal(p.data.ocrRows[0].value,'SYNTHETIC ACCOUNT');assert.equal(p.ocrCapture.recovery,true);assert.equal(p.ocrCapture.recovery_binding.content_sha256,digest);assert.equal(p.data.ocrConfirmed,false);
 p.load=async()=>{};await p.confirmAndSaveOcr();
 assert.deepEqual(f.actions.map(q=>q.action),['recover_view','recover_confirm','recover_apply']);assert.equal(p.profile.bank_account_info.account_number,'MANUAL SYNTHETIC');assert.equal(p.profile.bank_account_info.account_bank,'SYNTHETIC BANK');
});
test('fix F01: malformed nested recovery binding or receipt never displays or confirms',async()=>{
 for(const defect of ['hash','attachment','application','provider','document','recovery','flat']){
  const f=recoveryFixture(),p=f.page,transport=p.session.merchant;p.session.merchant=async(...args)=>{const r=await transport(...args),v=r.result;if(defect==='hash')v.binding.content_sha256='b'.repeat(64);if(defect==='attachment')v.binding.attachment_id='other';if(defect==='application')v.binding.application_revision='8';if(defect==='provider')v.binding.provider_version=4;if(defect==='document')v.binding.document_type='id_front';if(defect==='recovery')v.recovery_id='other';if(defect==='flat')return {result:outcome()};return r;};
  await p.recognizeCurrentDocument('bank_card',{existingMaterial:true});assert.equal(p.data.ocrRows.length,0,defect);assert.equal(p.data.ocrConfirmed,false);assert.equal(f.actions.length,1);assert.equal(f.actions[0].action,'recover_view');
 }
});
test('fix F01: job and original-key locators stay exact and never create another job',async()=>{
 for(const locator of [{job_id:'synthetic-job'},{original_key:'synthetic-original'}]){
  const f=recoveryFixture(),p=f.page,a=p.data.application;
  await p.recoverCurrentDocument({document_type:'bank_card',application:a.application,revision:a.revision,source:p.ocrSource('bank_card'),session:p.session,session_generation:1,scene:p.scene,job_id:locator.job_id||'',idempotency_key:locator.original_key||'',original_locator:locator});
  assert.deepEqual(f.actions[0].locator,locator);assert.equal(f.actions.length,1);assert.equal(p.data.ocrRows.length,2);
 }
});
test('fix F02: missing remembered provider requires protected recovery, not repinning an old read',async()=>{
 const f=make();await uploaded(f);delete f.page.ocrCapture.bound_provider_version;f.page.rememberKnownOcr();f.page.invalidateOcr();const actions=[];f.page.session.merchant=async(scene,op,q)=>{actions.push(q);return {result:outcome()};};await f.page.restoreKnownOcr();assert.deepEqual(actions.map(q=>q.action),['recover_view']);assert.equal(f.page.data.ocrRows.length,0);
});
test('fix F02: late recovery or confirmation on provider drift never restores rows or confirms',async()=>{
 for(const phase of ['recover_view','recover_confirm']){
  const f=recoveryFixture(),p=f.page,transport=p.session.merchant,d=deferred(),entered=deferred();
  if(phase==='recover_confirm')await p.recognizeCurrentDocument('bank_card',{existingMaterial:true});
  p.session.merchant=async(...args)=>{const r=await transport(...args);entered.resolve();await d.promise;return r;};
  const running=phase==='recover_view'?p.recognizeCurrentDocument('bank_card',{existingMaterial:true}):p.confirmOcr();await entered.promise;p.version++;d.resolve();await running;assert.equal(p.data.ocrConfirmed,false);if(phase==='recover_view')assert.equal(p.data.ocrRows.length,0);const n=f.actions.length;await p.confirmOcr();assert.equal(f.actions.length,n);
 }
});
test('fix F03: source and queue invalidation isolate bank errors without erasing license',()=>{
 const f=make(),p=f.page;p.data.application.materials={bank_card:{object_id:'bank'},business_license:{object_id:'license'}};
 const q={session:p.session,sessionGeneration:1,scene:p.scene,epoch:p.epoch,application:p.data.application.application,revision:7,version:3,items:[],failures:{bank_card:{source:p.ocrSource('bank_card'),text:'BANK'},business_license:{source:p.ocrSource('business_license'),text:'LICENSE'}}};p.ocrRestoreQueue=q;
 assert.equal(p.materialOcrFailureView().bank_card.text,'BANK');p.data.application.materials.bank_card.object_id='changed';assert.equal(p.materialOcrFailureView().bank_card,undefined);assert.equal(p.materialOcrFailureView().business_license.text,'LICENSE');q.version++;assert.equal(Object.keys(p.materialOcrFailureView()).length,0);
});
test('fix F02: restored read rejects response provider different from original binding',async()=>{
 const f=make();await uploaded(f);f.page.rememberKnownOcr();f.page.invalidateOcr();f.page.session.merchant=async()=>({result:{...outcome(),provider_version:4}});await f.page.restoreKnownOcr();assert.equal(f.page.data.ocrRows.length,0);assert.equal(f.page.data.ocrConfirmed,false);
});
test('fix F01: late recover_view cannot cross application material session or scene',async()=>{
 for(const drift of ['application','material','session','scene']){
  const f=recoveryFixture(),p=f.page,transport=p.session.merchant,d=deferred(),entered=deferred();p.session.merchant=async(...args)=>{const r=await transport(...args);entered.resolve();await d.promise;return r;};
  const running=p.recognizeCurrentDocument('bank_card',{existingMaterial:true});await entered.promise;if(drift==='material')p.data.application.materials.bank_card.sha256='c'.repeat(64);else f.drift(drift);d.resolve();await running;assert.equal(p.data.ocrRows.length,0,drift);assert.equal(f.actions.length,1);assert.equal(p.data.ocrConfirmed,false);
 }
});
