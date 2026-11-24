'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const form=require('./merchant-form');
const script=fs.readFileSync(__dirname+'/pages/merchant-join/index.js','utf8');
function harness(){
 let definition;const calls=[];
 const wx={chooseMedia(o){o.success({tempFiles:[{tempFilePath:'synthetic-bank.jpg'}]});},
  getFileSystemManager(){return {stat(o){o.success({stats:{size:3}});},readFile(o){o.success({data:'YWJj'});}};},
  base64ToArrayBuffer(){return Uint8Array.from([97,98,99]).buffer;},request(){throw Error('unexpected network');}};
 const context={wx,ArrayBuffer,Uint8Array,Page:p=>definition=p,
  require(p){if(p==='../../session')return {customerError:e=>e.message};if(p==='../../customer-auth')return {};
   if(p==='../../chain-telemetry')return require('./chain-telemetry');if(p==='../../merchant-form')return form;
   if(p==='../../merchant-submit')return {};if(p==='../../merchant-official-fields')return require('./merchant-official-fields');
   if(p==='../../merchant-platform-reference-data')return require('./merchant-platform-reference-data');
   if(p==='./direct-ocr')return {startDirectOcr(o){calls.push(['direct-ocr',o.kind]);return {storage:Promise.resolve(),ocr:Promise.resolve()};}};
   if(p==='./direct-proof')return {directProof(){return {sha256:()=> 'a'.repeat(64),signDigest:async()=>({})};}};
   throw Error('unexpected dependency '+p);}};
 vm.runInNewContext(script,context);
 const page={...definition,data:structuredClone(definition.data),setData(p,done){Object.assign(this.data,p);if(done)done();}};
 page.data.application={application:'synthetic',revision:1,materials:{}};page.data.canEditPlatform=true;page.data.canEditWechat=true;page.data.ready=true;
 page.session={isAuthenticated:()=>true,getGeneration:()=>1};page.epoch=1;page.scene='synthetic-scene';page.version=1;page.profile={};page.ocrDrafts={};
 page.current=()=>true;page.run=async task=>task();page.refresh=()=>calls.push(['refresh']);page.retainOcrDisplay=()=>{};
 page.chainRecord=()=>{};page.updateOcrView=()=>{};page.advanceDirectOcrHints=()=>{};
 page.request=async(op,params)=>{calls.push([op,params]);assert.equal(op,'upload');return {...page.data.application,revision:2,materials:{[params.kind]:{uploaded:true}}};};
 page.recognizeCurrentDocumentSpy=definition.recognizeCurrentDocument;
 return {page,calls};
}
const click=kind=>({currentTarget:{dataset:{kind}}});

test('F1 bank upload persists private photo and preview without OCR or WeChat material call',async()=>{
 const h=harness();h.page.recognizeCurrentDocument=kind=>{h.calls.push(['recognizeCurrentDocument',kind]);};
 await h.page.upload(click('bank_card'));
 assert.equal(h.calls.filter(x=>x[0]==='upload').length,1);
 assert.equal(h.calls.filter(x=>x[0]==='direct-ocr'||x[0]==='recognizeCurrentDocument').length,0);
 assert.equal(h.page.data.application.materials.bank_card.uploaded,true);
 assert.equal(h.page.data.materialPreviews.bank_card,'synthetic-bank.jpg');
 assert.match(h.page.data.status,/私密保存.*人工填写.*核对开户/);
 assert.doesNotMatch(h.page.data.status,/识别/);
});

test('F1 bank explicit handler and lower-level retry/recognition cannot start OCR',async()=>{
 const h=harness();let runs=0;h.page.run=()=>{runs++;};
 h.page.recognizeDocument(click('bank_card'));
 await h.page.retryDirectOriginal('bank_card');
 await h.page.recognizeCurrentDocumentSpy.call(h.page,'bank_card',{newIntent:true});
 assert.equal(runs,0);assert.deepEqual(h.calls,[]);
 assert.equal(h.page.ocrCurrent({document_type:'bank_card'}),false);
});

test('F1 other document explicit recognition remains routed to original retry',()=>{
 const h=harness();h.page.run=fn=>fn();h.page.retryDirectOriginal=kind=>h.calls.push(['retry',kind]);
 for(const kind of ['business_license','id_front','id_back'])h.page.recognizeDocument(click(kind));
 assert.deepEqual(h.calls,[['retry','business_license'],['retry','id_front'],['retry','id_back']]);
});

test('F1 other document uploads retain original direct OCR branch',async()=>{
 for(const [material,document] of [['business_license','business_license'],['identity_front','id_front'],['identity_back','id_back']]){
  const h=harness();await h.page.upload(click(material));
  assert.equal(h.calls.filter(x=>x[0]==='direct-ocr'&&x[1]===document).length,1,material);
 }
});

test('F1 bank fields remain manual and old bank OCR suggestions are not projected',()=>{
 const h=harness(),profile={bank_account_info:{bank_account_type:'BANK_ACCOUNT_TYPE_CORPORATE',account_bank:'其他银行',account_number:'manual-account',bank_name:'manual-branch'}};
 const options={entity:'ENTERPRISE',contact:'LEGAL',doc:'IDENTIFICATION_TYPE_IDCARD',ubos:'unknown',category:'GENERAL'};
 h.page.profile=profile;h.page.ocrDrafts={bank_card:{fields:{account_number:'unapproved-ocr',account_bank:'unapproved-bank'}}};
 const bank=form.materialGroups(profile,options,[],2).find(g=>g.id==='bank');assert.ok(bank);assert.ok(!bank.ocrKind);
 for(const path of ['bank_account_info.bank_account_type','bank_account_info.account_bank','bank_account_info.account_number','bank_account_info.bank_name','bank_account_info.bank_branch_id'])assert.ok(bank.fields.some(f=>f.path===path),path);
 const projected=h.page.projectOcrGroups([bank])[0];const number=projected.fields.find(f=>f.path==='bank_account_info.account_number');
 assert.equal(number.value,'manual-account');assert.equal(number.ocrSuggestion,false);assert.equal(number.ocrDocument,'');assert.equal(projected.hasOcrFields,false);
 const w=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');
 assert.doesNotMatch(w,/识别银行卡|银行卡识别|仅本地识别|卡面印刷|materialOcrErrors\.bank_card|ocrFeedback.kind==='bank_card'/);
 assert.match(w,/class="primary bank-photo-entry" data-kind="bank_card" bindtap="upload"/);
 assert.match(w,/识别身份证国徽面/);
});

test('F1 uploaded bank card is excluded from restored OCR queues and review suggestions',()=>{
 const h=harness();h.page.data.application.materials={bank_card:{sha256:'b'},business_license:{sha256:'l'}};
 h.page.scheduleUploadedOcrRestore=()=>{};h.page.ocrSource=kind=>kind;
 h.page.queueUploadedOcrRestore();assert.deepEqual(Array.from(h.page.ocrRestoreQueue.items,x=>x.kind),['business_license']);
});
