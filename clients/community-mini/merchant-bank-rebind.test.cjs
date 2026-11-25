const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{createRequire}=require('node:module');
const root=__dirname,file=path.join(root,'merchant-bank-picker.test.cjs'),original=fs.readFileSync(file,'utf8');
const prefix=original.split("const test=require('node:test');")[0],source=fs.readFileSync(path.join(root,'pages/merchant-join/index.js'),'utf8');
function make(fullSave=false){const code=fullSave?prefix.replace(",'finishConfirmedOcrSave'",''):prefix;return new Function('require','__dirname',code+';return fixture;')(createRequire(file),root)(source);}
const event={currentTarget:{dataset:{kind:'bank_card'}}};
const outcome=(status='needs_review')=>({job_id:'synthetic-job',document_type:'bank_card',application_revision:'8',provider_version:3,status,fields:{account_number:{value:'SYNTHETIC ACCOUNT'},account_bank:{value:'SYNTHETIC BANK'}}});
async function uploaded(f){const p=f.page.upload(event);f.pick();await p;}
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
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

test('independent: absent malformed or extra nested binding cannot produce rows or confirmation',async()=>{
 for(const mutate of [v=>delete v.binding,v=>v.binding=null,v=>v.binding=[],v=>delete v.binding.content_sha256,v=>v.binding.provider_version='3',v=>v.binding.application_revision=7,v=>v.binding.content_sha256='invalid',v=>v.binding.extra='forbidden',v=>v.revision=2,v=>v.confirmed=true]){
  const f=recoveryFixture(),p=f.page,transport=p.session.merchant;p.session.merchant=async(...args)=>{const r=await transport(...args);mutate(r.result);return r;};
  await p.recognizeCurrentDocument('bank_card',{existingMaterial:true});await p.confirmOcr();assert.equal(p.data.ocrRows.length,0);assert.equal(p.data.ocrConfirmed,false);assert.deepEqual(f.actions.map(a=>a.action),['recover_view']);
 }
});
test('independent: legitimate public material without private hash still requires protected exact binding',async()=>{
 const f=recoveryFixture(),p=f.page;delete p.data.application.materials.bank_card.object_id;delete p.data.application.materials.bank_card.sha256;
 await p.recognizeCurrentDocument('bank_card',{existingMaterial:true});assert.equal(p.data.ocrRows.length,2);assert.equal(p.ocrCapture.recovery_binding.content_sha256,digest);assert.equal(p.data.ocrConfirmed,false);
});
test('independent: late confirm with changed receipt binding never permits apply',async()=>{
 for(const field of ['content_sha256','attachment_id','application_revision','provider_version']){
 const f=recoveryFixture(),p=f.page;await p.recognizeCurrentDocument('bank_card',{existingMaterial:true});const transport=p.session.merchant;p.session.merchant=async(...args)=>{const r=await transport(...args);r.result.binding[field]=field==='provider_version'?4:'incorrect';return r;};await p.confirmOcr();assert.equal(p.data.ocrConfirmed,false);await p.applyRecovery();assert.equal(f.actions.some(a=>a.action==='recover_apply'),false);
 }
});
test('independent: remembered exact recovery binding survives same-version restore',async()=>{
 const f=recoveryFixture(),p=f.page;await p.recognizeCurrentDocument('bank_card',{existingMaterial:true});p.rememberKnownOcr();p.invalidateOcr();await p.restoreKnownOcr();assert.equal(p.data.ocrRows.length,2);assert.equal(p.ocrCapture.recovery_binding.content_sha256,digest);assert.deepEqual(f.actions.map(a=>a.action),['recover_view','recover_view']);
});
test('independent: provider-changed remembered recovery displays only after a fresh valid protected view',async()=>{
 const f=recoveryFixture(),p=f.page;await p.recognizeCurrentDocument('bank_card',{existingMaterial:true});p.rememberKnownOcr();p.invalidateOcr();p.version=4;
 const transport=p.session.merchant;p.session.merchant=async(...args)=>{const r=await transport(...args);if(args[2].action==='recover_view')r.result.binding.provider_version=4;return r;};
 await p.restoreKnownOcr();console.log('FRESH_REBOUND',JSON.stringify({actions:f.actions,rows:p.data.ocrRows.length,capture:p.ocrCapture,status:p.data.ocrStatus}));
 assert.equal(f.actions.length,2);assert.equal(f.actions[1].locator.current_material,true);assert.notEqual(f.actions[0].recovery_key,f.actions[1].recovery_key);assert.equal(p.data.ocrRows.length,2,'a valid new protected recovery must not be rejected solely because the old binding was remembered');assert.equal(p.ocrCapture.recovery_binding.provider_version,4);assert.equal(p.data.ocrConfirmed,false);
});

test('independent control: fresh protected provider rebind succeeds when no old recovery receipt is retained',async()=>{
 const f=recoveryFixture(),p=f.page;await p.recognizeCurrentDocument('bank_card',{existingMaterial:true});delete p.ocrCapture.recovery_binding;p.rememberKnownOcr();p.invalidateOcr();p.version=4;
 const transport=p.session.merchant;p.session.merchant=async(...args)=>{const r=await transport(...args);r.result.binding.provider_version=4;return r;};await p.restoreKnownOcr();assert.equal(p.data.ocrRows.length,2);assert.equal(p.ocrCapture.recovery_binding.provider_version,4);assert.equal(p.data.ocrConfirmed,false);console.log('NO_OLD_BINDING_CONTROL_PASS');
});
test('R1: pending fresh view carries no old rows confirmation or writeback authority',async()=>{
 const f=recoveryFixture(),p=f.page;await p.recognizeCurrentDocument('bank_card',{existingMaterial:true});
 const oldKey=p.ocrCapture.recovery_key;p.ocrCapture={...p.ocrCapture,auto_save_fields:{account_bank:'OLD'},recovery_confirmation:{recovery_id:oldKey,revision:1,fields:{account_bank:'OLD'},confirmation_key:'old-confirm'},recovery_confirmation_revision:1,recovery_writeback_key:'old-save'};p.data.ocrConfirmed=true;p.rememberKnownOcr();p.invalidateOcr();p.version=4;
 const transport=p.session.merchant,d=deferred(),entered=deferred();p.session.merchant=async(...args)=>{const r=await transport(...args);r.result.binding.provider_version=4;entered.resolve();await d.promise;return r;};
 p.ocrDisplayCaptures={bank_card:{...p.ocrHeldCaptures.bank_card}};const restoring=p.restoreKnownOcr();await entered.promise;assert.equal(p.ocrDisplayCaptures.bank_card,undefined);assert.equal(p.ocrHeldCaptures.bank_card,undefined);assert.notEqual(p.ocrCapture.recovery_key,oldKey);assert.equal(p.data.ocrRows.length,0);assert.equal(p.data.ocrConfirmed,false);assert.equal(p.ocrCapture.recovery_binding,null);assert.equal(p.ocrCapture.recovery_confirmation,null);assert.equal(p.ocrCapture.recovery_writeback_key,undefined);assert.equal(p.ocrCapture.recovery_confirmation_revision,undefined);assert.equal(p.ocrCapture.auto_save_fields,null);
 await p.applyRecovery();assert.equal(f.actions.length,2);d.resolve();await restoring;assert.equal(p.data.ocrRows.length,2);assert.equal(p.data.ocrConfirmed,false);await p.applyRecovery();assert.equal(f.actions.length,2);
 p.session.merchant=async(...args)=>{const r=await transport(...args);if(r.result.binding)r.result.binding.provider_version=4;return r;};p.load=async()=>{};await p.confirmAndSaveOcr();assert.deepEqual(f.actions.map(q=>q.action),['recover_view','recover_view','recover_confirm','recover_apply']);assert.equal(f.actions[2].recovery_id,f.actions[1].recovery_key);assert.notEqual(f.actions[2].confirmation_key,'old-confirm');assert.notEqual(f.actions[3].writeback_key,'old-save');
});
test('R1: same-key replay retains original binding even when public material omits hash',async()=>{
 const f=recoveryFixture(),p=f.page;delete p.data.application.materials.bank_card.object_id;delete p.data.application.materials.bank_card.sha256;await p.recognizeCurrentDocument('bank_card',{existingMaterial:true});const key=p.ocrCapture.recovery_key;const transport=p.session.merchant;p.session.merchant=async(...args)=>{const r=await transport(...args);r.result.binding.content_sha256='b'.repeat(64);return r;};await p.readOcr();assert.equal(f.actions[1].recovery_key,key);assert.equal(p.data.ocrRows.length,0);assert.equal(p.data.ocrConfirmed,false);await p.applyRecovery();assert.equal(f.actions.length,2);
});
test('R1: fresh key cannot consume an old receipt even if its current binding is complete',async()=>{
 const f=recoveryFixture(),p=f.page;await p.recognizeCurrentDocument('bank_card',{existingMaterial:true});const oldKey=p.ocrCapture.recovery_key;p.rememberKnownOcr();p.invalidateOcr();p.version=4;const transport=p.session.merchant;p.session.merchant=async(...args)=>{const r=await transport(...args);r.result.binding.provider_version=4;r.result.recovery_id=oldKey;return r;};await p.restoreKnownOcr();assert.equal(p.data.ocrRows.length,0);assert.equal(p.data.ocrConfirmed,false);await p.confirmOcr();await p.applyRecovery();assert.equal(f.actions.length,2);
});
test('R1: unknown old apply retains exact receipt and cannot migrate to new provider',async()=>{
 const f=recoveryFixture(),p=f.page;await p.recognizeCurrentDocument('bank_card',{existingMaterial:true});const old=p.ocrCapture;p.ocrCapture={...old,recovery_apply_pending:true,recovery_confirmation:{recovery_id:old.recovery_key,revision:1,fields:{account_bank:'OLD'},confirmation_key:'old-confirm'},recovery_confirmation_revision:1,recovery_writeback_key:'old-save'};p.rememberKnownOcr();p.invalidateOcr();p.version=4;await p.restoreKnownOcr();assert.equal(f.actions.length,1);assert.equal(p.ocrCapture.recovery_key,old.recovery_key);assert.equal(p.ocrCapture.recovery_binding.provider_version,3);assert.equal(p.ocrCapture.bound_provider_version,3);assert.equal(p.ocrCapture.recovery_writeback_key,'old-save');assert.equal(p.data.ocrConfirmed,false);
});
