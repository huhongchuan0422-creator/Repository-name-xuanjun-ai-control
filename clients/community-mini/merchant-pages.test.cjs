const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const form=require('./merchant-form');const auth=require('./customer-auth');
function fixture(name,options={}){let authenticated=false;let definition,calls=[],scrolls=[],pending=null,failure=null,storedProfile={},storedMiniLive=false,storedOcrDrafts={},cashierMediaId='',ocrStatus='needs_review',ocrConfirmedFields=null,ocrConfirmationRevision=0;const app={application:'ma_'+ '1'.repeat(32),revision:1,status:'DRAFT',fields:{store_name:'Fixture Shop',address:'Fixture Address'},entity_type:'ENTERPRISE',delegated:false,identity_type:'IDENTIFICATION_TYPE_IDCARD',sales_scenes_type:['SALES_SCENES_MINI_PROGRAM'],required_materials:['business_license'],materials:{},wechat_submerchant_state:'NOT_VERIFIED',opening_state:'NOT_APPROVED'};
const session={clear(){authenticated=false;},login:async()=>{authenticated=true;},async merchant(scene,op,p){if(options.beforeOperation)await options.beforeOperation(op,p);calls.push({scene,op,p:structuredClone(p)});if(failure&&failure.operation===p.operation){const e=failure.error;failure=null;throw e;}if(pending)return pending;
 if(op==='ocr'){if(p.action==='submit')return {result:{job_id:'synthetic-ocr'}};if(p.action==='read')return {result:{job_id:p.job_id,application_revision:String(app.revision),provider_version:1,status:ocrStatus,document_type:'business_license',...(ocrStatus==='confirmed'?{confirmed_fields:structuredClone(ocrConfirmedFields),confirmation_revision:ocrConfirmationRevision}:{fields:{company_name:{value:'Fixture Company'},registered_address:{value:'OCR Address'}}})}};if(p.action==='confirm'){ocrStatus='confirmed';ocrConfirmedFields=structuredClone(p.fields);ocrConfirmationRevision=p.revision;return {result:{job_id:p.job_id,status:'confirmed',revision:p.revision,recorded:true,application_revision:p.application_revision,provider_version:p.provider_version}};}}
 if(op==='workspaces')return {workspaces:['merchant']};if(op==='read')return p.operation==='community.orders'?{orders:[]}:{counts:{},order_total_minor:0};
 if(p.operation==='mine')return {applications:options.duplicateApplications?[structuredClone(app),{...structuredClone(app),application:'ma_'+ '2'.repeat(32),status:'APPROVED'}]:[]};if(p.operation==='catalog')return {materials:[{id:'business_license',title:'营业执照'}]};if(p.operation==='save'){if(typeof p.params.split_participation==='boolean'){app.split_participation=p.params.split_participation;app.requested_split_bps=p.params.requested_split_bps;app.effective_split_bps=0;}if(Number.isInteger(p.params.redemption_percent))app.redemption_percent=p.params.redemption_percent;if(p.params.declarations)app.declarations=structuredClone(p.params.declarations);if(p.params.sales_scenes_type)app.sales_scenes_type=structuredClone(p.params.sales_scenes_type);app.entity_type=p.params.entity_type;app.category=p.params.category;app.delegated=p.params.delegated;app.identity_type=p.params.identity_type;return structuredClone(app);}if(p.operation==='read'){if(p.params.application!==app.application)return {...structuredClone(app),application:p.params.application,status:'APPROVED'};return structuredClone(app);}if(p.operation==='upload'){app.materials[p.params.kind]={uploaded:true,review:'PENDING'};app.revision++;cashierMediaId='';return structuredClone(app);}if(p.operation==='remove_material'){delete app.materials.cashier_photo;app.revision++;cashierMediaId='';return structuredClone(app);}if(p.operation==='wechat_media')return {media_id:'synthetic-admitted-media'};if(p.operation==='wechat_cashier_link'){cashierMediaId=p.params.media_id;return {version:2};}if(p.operation==='submit'){app.status='SUBMITTED';return structuredClone(app);}if(p.operation==='wechat_submit_review'){app.wechatReview='PENDING_INTERNAL_REVIEW';return {state:app.wechatReview};}if(p.operation==='wechat_apply'){app.wechatReview='SUBMITTED_TO_PROVIDER';return {state:app.wechatReview,applyment_id:'123456'};}if(p.operation==='wechat_status'){return {state:app.wechatReview,provider_state:'APPLYMENT_STATE_AUDITING'};}if(p.operation==='wechat_read')return {version:1,state:app.wechatReview||'DRAFT',mini_program_live:storedMiniLive,profile:structuredClone(storedProfile),ocr_drafts:structuredClone(storedOcrDrafts),cashier_media_id:cashierMediaId};if(p.operation==='wechat_save'){if(typeof p.params.mini_program_live==='boolean')storedMiniLive=p.params.mini_program_live;if(p.params.ocr_drafts)storedOcrDrafts={...storedOcrDrafts,...structuredClone(p.params.ocr_drafts)};storedProfile=structuredClone(p.params.profile);return {version:2,profile:structuredClone(storedProfile)};}throw Error('unplanned');}};
 vm.runInNewContext(fs.readFileSync(__dirname+'/pages/'+name+'/index.js','utf8'),{Page:p=>definition=p,wx:{pageScrollTo(o){scrolls.push({...o,step:page.data.step});},navigateTo(o){calls.push({navigation:o.url});if(o.success)o.success();if(o.complete)o.complete();},redirectTo(o){calls.push({navigation:o.url});if(o.success)o.success();if(o.complete)o.complete();},chooseMedia(o){if(options.chooseMedia)return options.chooseMedia(o);calls.push({p:{operation:'media_choice'},mediaChoice:{sourceType:o.sourceType,mediaType:o.mediaType,sizeType:o.sizeType}});o.success({tempFiles:[{tempFilePath:'synthetic-cashier.png',size:options.largeMedia?6000000:32}]});},getImageInfo(o){o.success({width:1280,height:1706});},compressImage(o){if(options.compressImage)return options.compressImage(o);calls.push({compress:{src:o.src,quality:o.quality}});o.success({tempFilePath:'synthetic-compressed.png'});},getFileSystemManager(){return {stat(o){o.success({stats:{size:options.largeMedia&&o.path==='synthetic-cashier.png'?6000000:17}});},readFile(o){calls.push({p:{operation:'read_file'},readFile:o.filePath});o.success({data:options.largeMedia&&o.filePath==='synthetic-cashier.png'?'A'.repeat(6666672):'iVBORw0KGgpzeW50aGV0aWM='});}}}},getApp:()=>({globalData:{baseUrl:'https://fixture.invalid'}}),require:p=>{if(p.endsWith('.json'))throw Error('WECHAT_JSON_MODULE_UNAVAILABLE');return p==='../../session'?{parseScene:()=> 'shop1',getSharedSession:()=>({...session,ensureLogin:session.login,isAuthenticated:()=>authenticated}),customerError:options.customerError||(()=> 'error')}:p==='../../customer-auth'?auth:p==='../../merchant-form'?form:p==='../../merchant-submit'?require('./merchant-submit'):p==='../../merchant-official-fields'?require('./merchant-official-fields'):p==='../../merchant-platform-reference-data'?require('./merchant-platform-reference-data'):require(p);},encodeURIComponent});
const page={...definition,data:structuredClone(definition.data),setData(p,afterRender){Object.assign(this.data,p);if(afterRender)afterRender();}};return {page,calls,scrolls,app,hold(p){pending=p;},failNext(operation,error){failure={operation,error};},get storedProfile(){return storedProfile;}};}
test('new admission defaults to LEGAL and places business-license fields and upload on the first screen',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 assert.equal(f.page.data.options.contact,'LEGAL');
 assert.ok(f.page.data.fields.some(x=>x.path==='subject_info.business_license_info.merchant_name'));
 assert.ok(f.page.data.fields.some(x=>x.path==='contact_info.mobile_phone'));
 assert.ok(f.page.data.fields.some(x=>x.path==='contact_info.contact_email'));
 assert.ok(f.page.data.licenseMaterial);
 const markup=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.equal(f.page.data.materialGroups[0].id,'license');assert.match(markup,/识别营业执照/);assert.match(markup,/点击识别后请核对结果/);assert.equal(markup.includes('当前尚无真实OCR接口'),false);assert.equal(markup.includes('OCR未接通'),false);
});
test('native home/recommendations/profile tabs and entry navigation stay in the same five-page app',()=>{
 const app=JSON.parse(fs.readFileSync(__dirname+'/app.json','utf8'));
 assert.equal(app.tabBar,undefined);
 const home=fs.readFileSync(__dirname+'/pages/home/index.wxml','utf8');
 const checkout=fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8');
 const profile=fs.readFileSync(__dirname+'/pages/profile/index.wxml','utf8');
 for(const label of ['搜索附近好店','继续查看门店'])assert.ok(home.includes(label),label);
 assert.ok(checkout.includes('发现邻里好店')&&checkout.includes('industry-tabs')&&checkout.includes('返回店铺列表'));
 const join=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.ok(join.includes('wx:for="{{group.fields}}"'));assert.equal(join.includes('index===fieldCursor'),false,'original final design requires grouped fields, not a single-field carousel');
 assert.ok(profile.includes('我的订单'));assert.match(profile,/merchantEntryLabel/);const entryScript=fs.readFileSync(__dirname+'/pages/profile/index.js','utf8');for(const label of ['申请入驻','入驻进度','商家工作台'])assert.ok(entryScript.includes(label),label);
});
test('merchant admission bootstrap stays compatible with real-device WeChat runtimes',()=>{
 const script=fs.readFileSync(__dirname+'/pages/merchant-join/index.js','utf8');
 const markup=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');
 assert.doesNotMatch(script,/\?\.|\.flatMap\(|Object\.fromEntries\(/);
 assert.match(markup,/range="{{redemptionOptions}}"/);assert.match(markup,/bindchange="chooseRedemption"/);
});
test('merchant admission registers a visible page before loading optional form dependencies',async()=>{
 const script=fs.readFileSync(__dirname+'/pages/merchant-join/index.js','utf8');let definition;
 vm.runInNewContext(script,{Page:value=>definition=value,require:path=>{if(path==='../../session')return {parseScene(){},getSharedSession(){},customerError(){}};if(path==='../../customer-auth')return {current:()=>1};throw Error('synthetic dependency load failure');}});
 assert.ok(definition&&definition.data&&definition.data.steps.length===4);
 const page={...definition,data:structuredClone(definition.data),setData(value){Object.assign(this.data,value);}};
 await page.onLoad({});
 assert.match(page.data.status,/页面组件加载失败/);
 assert.equal(page.data.pending,false);
});
test('dirty admission draft requires explicit save-or-stay before navigation',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 f.page.input({currentTarget:{dataset:{path:'business_info.merchant_shortname'}},detail:{value:'Unsaved Shop'}});
 f.page.navigateSection({currentTarget:{dataset:{section:'orders'}}});
 assert.equal(f.page.data.leavePrompt,true);assert.equal(f.page.data.leaveTarget,'orders');assert.equal(f.page.data.dirty,true);
 assert.equal(form.get(f.page.profile,'business_info.merchant_shortname'),'Unsaved Shop');
 f.page.cancelLeave();assert.equal(f.page.data.leavePrompt,false);assert.equal(f.page.data.dirty,true);
 assert.equal(f.calls.some(c=>c.p.operation==='save'),false);
});
test('merchant entry is in existing display and same app routes, no second appid',()=>{const pages=JSON.parse(fs.readFileSync(__dirname+'/app.json')).pages;for(const p of ['merchant','merchant-join'])assert.ok(pages.includes('pages/'+p+'/index'));assert.doesNotMatch(fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8'),/bindtap="openMerchantJoin"/);assert.match(fs.readFileSync(__dirname+'/pages/profile/index.wxml','utf8'),/bindtap="openMerchantEntry"/);});
test('merchant admission first paint isolates the authenticated form subtree',()=>{const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');const gate=wxml.indexOf('<block wx:if="{{ready||status&&!pending}}">'),form=wxml.indexOf('<view wx:for="{{materialGroups}}"');assert.ok(gate>0&&form>gate);assert.ok(wxml.indexOf('微信登录后开始办理')<gate);});
test('join four stages save one shared profile and refresh original application',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});form.put(f.page.profile,'subject_info.business_license_info.merchant_name','Fixture Company');form.put(f.page.profile,'contact_info.mobile_phone','13800000000');await f.page.next();assert.equal(f.page.data.step,1);const save=f.calls.find(c=>c.p.operation==='save');assert.equal(save.p.params.fields.legal_name,'Fixture Company');assert.equal(save.p.params.fields.contact,'13800000000');const provider=f.calls.find(c=>c.p.operation==='wechat_save');assert.equal(provider.p.params.application,f.app.application);f.page.back();assert.equal(f.page.data.step,0);assert.ok(f.calls.some(c=>c.p.operation==='read'));assert.ok(!f.calls.some(c=>['wechat_execute','wechat_query'].includes(c.p.operation)));});
test('conditional document and delegated fields and single UBO editor',()=>{const o={entity:'SOLE_PROPRIETOR',contact:'LEGAL',doc:'IDENTIFICATION_TYPE_IDCARD',scene:'mini',ubos:0};const rows=form.rows({},o,0);assert.ok(rows.every(r=>!r.path.includes('.id_doc_info.')&&!r.path.includes('ubo_info_list')));assert.ok(form.rows({},o,1).every(r=>!r.path.includes('contact_id_number')));const changed=form.rows({}, {...o,entity:'ENTERPRISE',doc:'IDENTIFICATION_TYPE_OVERSEA_PASSPORT',ubos:2,uboIndex:1},0);assert.ok(changed.some(r=>r.path.includes('.ubo_info_list.1.')));assert.ok(changed.every(r=>!r.path.includes('.ubo_info_list.0.')));assert.ok(changed.every(r=>!r.path.includes('.id_card_info.')));});
test('merchant clears scene-bound private state when the active scene changes',()=>{
 const script=fs.readFileSync(__dirname+'/pages/merchant/index.js','utf8');
 assert.match(script,/const activeScene=getApp\(\)\.globalData\.scene/);
 assert.match(script,/current\(\)\{return !this\.dead&&!this\.sceneStale&&auth\.active\(this\.epoch\);\}/);
 assert.match(script,/workspaces:\[\],workspace:'',orders:\[\],summary:null,detail:null,settings:null/);
});
test('admission save keeps the current material cursor and sync is not mislabeled as WeChat submission',()=>{
 const script=fs.readFileSync(__dirname+'/pages/merchant-join/index.js','utf8');
 assert.match(script,/const savedPosition=\{step:this\.data\.step,fieldCursor:this\.data\.fieldCursor,cursorPath:this\.data\.cursorPath,materialCursor:this\.data\.materialCursor\}/);
 assert.match(script,/this\.setData\(savedPosition\);this\.refresh\(\)/);
 assert.ok(script.includes('尚未提交微信'));
 const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');
 assert.ok(wxml.includes('原申请已上传'));assert.ok(wxml.includes('提交时自动处理'));assert.ok(wxml.includes('资料处理已完成'));assert.doesNotMatch(wxml,/bindtap="syncMaterial"|用于微信申请/);
});
test('merchant uses original summary/orders and hides late data after unload',async()=>{const f=fixture('merchant');await f.page.onLoad({scene:'shop1'});await f.page.open({currentTarget:{dataset:{view:'orders'}}});assert.equal(f.calls.at(-1).p.operation,'community.orders');let done;f.hold(new Promise(r=>done=r));const loading=f.page.open({currentTarget:{dataset:{view:'summary'}}});f.page.onUnload();done({order_total_minor:999});await loading;assert.equal(f.page.data.summary,null);});
test('revocation clears private application, fields and material metadata',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});await f.page.select({currentTarget:{dataset:{application:f.app.application}}});f.page.customerSessionRevoked();assert.equal(f.page.data.application,null);assert.equal(f.page.data.fields.length,0);assert.equal(f.page.data.materials.length,0);assert.equal(Object.keys(f.page.profile).length,0);});

test('merchant admin mobile keeps exact string, provider mapping and service phone separation',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({step:1,options:{...f.page.data.options,contact:'LEGAL'}});f.page.refresh();
 const path='contact_info.mobile_phone';
 for(const value of ['13800138000','00123456789','19912345678']){
  f.page.input({currentTarget:{dataset:{path}},detail:{value}});
  assert.equal(form.get(f.page.profile,path),value);assert.equal(typeof form.get(f.page.profile,path),'string');
  assert.equal(f.page.data.mobilePhoneError,'');
 }
 assert.equal(form.platformFields(f.page.profile,f.page.data.base).contact,'19912345678');
 form.put(f.page.profile,'business_info.service_phone','555-0100');assert.equal(form.get(f.page.profile,'business_info.service_phone'),'555-0100');assert.equal(form.get(f.page.profile,path),'19912345678');
 await f.page.save();
 assert.equal(form.get(f.storedProfile,path),'19912345678');
 assert.equal(typeof form.get(f.storedProfile,path),'string');
 assert.equal(f.calls.find(c=>c.p.operation==='wechat_save').p.params.profile.contact_info.mobile_phone,'19912345678');
});
test('reverse navigation from account number returns to the two-field bank branch group',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 form.put(f.page.profile,'bank_account_info.account_bank','其他银行');
 form.put(f.page.profile,'bank_account_info.bank_branch_id','123456789012');
 form.put(f.page.profile,'bank_account_info.bank_name','示例支行');
 form.put(f.page.profile,'bank_account_info.account_number','6222000000000000');
 f.page.setData({step:2,fieldCursor:0});f.page.refresh();
 const fields=f.page.data.fields;
 const branch=fields.findIndex(x=>x.path==='bank_account_info.bank_branch_id');
 const bankName=fields.findIndex(x=>x.path==='bank_account_info.bank_name');
 const account=fields.findIndex(x=>x.path==='bank_account_info.account_number');
 assert.ok(branch>=0&&bankName===branch+1&&account===branch+2);
 f.page.setData({fieldCursor:account,cursorPath:fields[account].path});f.page.previousField();
 assert.equal(f.page.data.fieldCursor,branch);
 assert.equal(f.page.data.fields[f.page.data.fieldCursor].path,'bank_account_info.bank_branch_id');
});
test('editing a non-mobile merchant field marks the draft dirty',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 f.page.setData({dirty:false});
 f.page.input({currentTarget:{dataset:{path:'subject_info.business_license_info.merchant_name'}},detail:{value:'主体名称'}});
 assert.equal(f.page.data.dirty,true);
});
test('other bank branch group accepts either field, refreshes on bank changes and preserves draft values',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({step:2});
 const input=(path,value)=>f.page.input({currentTarget:{dataset:{path}},detail:{value}});
 input('bank_account_info.account_bank','Other Bank');assert.equal(f.page.data.bankBranchGroupHint,'');
 input('bank_account_info.account_bank','其他银行');
 assert.equal(f.page.data.bankBranchGroupHint,'支行信息：联行号或支行全称至少填写一项 *');
 assert.ok(f.page.data.fields.some(x=>x.path==='bank_account_info.bank_branch_id'));
 assert.ok(f.page.data.fields.some(x=>x.path==='bank_account_info.bank_name'));
 await f.page.save();assert.equal(f.page.data.bankBranchGroupHint,'支行信息：联行号或支行全称至少填写一项 *');
 input('bank_account_info.bank_branch_id','001234567890');assert.equal(f.page.data.bankBranchGroupHint,'支行信息：联行号或支行全称至少填写一项（已满足）');
 assert.equal(form.get(f.page.profile,'bank_account_info.bank_name')||'','');
 input('bank_account_info.bank_branch_id','');assert.equal(f.page.data.bankBranchGroupHint,'支行信息：联行号或支行全称至少填写一项 *');
 input('bank_account_info.bank_name','Fixture Branch Bank');assert.equal(f.page.data.bankBranchGroupHint,'支行信息：联行号或支行全称至少填写一项（已满足）');
 input('bank_account_info.bank_name','');assert.equal(f.page.data.bankBranchGroupHint,'支行信息：联行号或支行全称至少填写一项 *');
 input('bank_account_info.account_bank','Fixture Bank');assert.equal(f.page.data.bankBranchGroupHint,'');
 input('bank_account_info.account_bank','其他银行');assert.equal(f.page.data.bankBranchGroupHint,'支行信息：联行号或支行全称至少填写一项 *');
 input('bank_account_info.bank_name','Fixture Branch Bank');
 f.failNext('wechat_save',new Error('BANK_BRANCH_TEST_REJECTED'));await f.page.save();
 assert.equal(form.get(f.page.profile,'bank_account_info.bank_name'),'Fixture Branch Bank');
 assert.ok(!/保存成功/.test(f.page.data.status));
 await f.page.save();
 assert.equal(form.get(f.storedProfile,'bank_account_info.bank_name'),'Fixture Branch Bank');
 assert.equal(form.get(f.storedProfile,'bank_account_info.bank_branch_id')||'','');
 assert.equal(form.get(f.page.profile,'bank_account_info.bank_name'),'Fixture Branch Bank');
 f.page.setData({step:1});f.page.refresh();f.page.setData({step:2});f.page.refresh();
 assert.equal(f.page.data.bankBranchGroupHint,'支行信息：联行号或支行全称至少填写一项（已满足）');
 input('bank_account_info.bank_name','');assert.equal(f.page.data.bankBranchGroupHint,'支行信息：联行号或支行全称至少填写一项 *');
});
test('merchant mobile rejects malformed values locally, preserves legacy overlength and clears errors on correction',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.profile={contact_info:{mobile_phone:'123456789012345678901'}};
 f.page.setData({step:0});f.page.refresh();
 assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),'123456789012345678901');
 assert.equal(f.page.data.fields.find(x=>x.path==='contact_info.mobile_phone').maxlength,-1);
 assert.notEqual(f.page.data.mobilePhoneError,'');
 for(const value of ['1234','1234567890','123456789012','abcde','123 45','13800138000\n','１３８００１３８０００','+13800138000']){
  f.page.input({currentTarget:{dataset:{path:'contact_info.mobile_phone'}},detail:{value}});
  assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),value);
  assert.notEqual(f.page.data.mobilePhoneError,'',JSON.stringify(value));
 }
 f.page.input({currentTarget:{dataset:{path:'contact_info.mobile_phone'}},detail:{value:'00123456789'}});
 assert.equal(f.page.data.mobilePhoneError,'');
 assert.equal(f.page.data.fields.find(x=>x.path==='contact_info.mobile_phone').maxlength,-1);
 f.page.input({currentTarget:{dataset:{path:'contact_info.mobile_phone'}},detail:{value:'12345678901234567890'}});
 assert.notEqual(f.page.data.mobilePhoneError,'');
 assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),'12345678901234567890');
});
test('empty mobile is an empty string after save and reread, no stale fallback',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({step:1});
 f.page.input({currentTarget:{dataset:{path:'contact_info.mobile_phone'}},detail:{value:'00123456789'}});
 f.page.input({currentTarget:{dataset:{path:'contact_info.mobile_phone'}},detail:{value:''}});
 assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),'');
 assert.notEqual(f.page.data.mobilePhoneError,'');
 await f.page.save();
 assert.equal(form.get(f.storedProfile,'contact_info.mobile_phone'),'');
 assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),'');
});
test('server rejection preserves raw mobile input and never reports saved success',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({step:1});
 const raw='   ';f.page.input({currentTarget:{dataset:{path:'contact_info.mobile_phone'}},detail:{value:raw}});
 f.failNext('wechat_save',new Error('INVALID_OFFICIAL_CONTACT_FORMAT'));
 await f.page.save();
 assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),raw);
 assert.match(f.page.data.status,/error/);
 assert.ok(!/保存成功/.test(f.page.data.status));
 assert.ok(f.calls.some(c=>c.p.operation==='wechat_save'));
});
test('LEGAL and SUPER use one mobile field and keep identity/contact fields across stages',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 const path='contact_info.mobile_phone';f.page.input({currentTarget:{dataset:{path}},detail:{value:'00123456789'}});
 for(const contact of ['LEGAL','SUPER']){
  f.page.setData({options:{...f.page.data.options,contact},step:0});f.page.refresh();
  assert.equal(f.page.data.fields.filter(x=>x.path===path).length,1);
  assert.equal(f.page.data.fields.some(x=>x.path==='contact_info.contact_name'),contact==='SUPER');
  assert.ok(f.page.data.fields.some(x=>x.path==='contact_info.contact_email'));
  f.page.setData({step:0});f.page.refresh();f.page.setData({step:1});f.page.refresh();
  assert.equal(form.get(f.page.profile,path),'00123456789');
 }
 const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');
 assert.ok(wxml.includes('type="text"'),'mobile phone field must use text input');assert.ok(wxml.includes('data-path="{{item.path}}"'),'mobile phone field must bind the exact field path');
 assert.ok(wxml.includes("maxlength=\"{{item.path===\'contact_info.mobile_phone\'?item.maxlength:512}}\""),'mobile_phone input must use the exact path-specific maxlength ternary');
 assert.ok(wxml.includes('bindblur="blurUnifiedField"'),'mobile phone field must bind blur validation');
 assert.ok(wxml.includes('11位数字联系电话，不含空格、+或-'),'complete mobile format hint must be present verbatim');
 assert.equal(form.get(f.page.profile,'business_info.service_phone'),'00123456789');assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),'00123456789');
});
test('approved platform application can continue original WeChat draft without resubmitting platform',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.app.status='APPROVED';await f.page.select({currentTarget:{dataset:{application:f.app.application}}});f.calls.length=0;form.put(f.page.profile,'contact_info.mobile_phone','13800000000');await f.page.save();assert.ok(!f.calls.some(c=>c.p.operation==='save'));assert.ok(f.calls.some(c=>c.p.operation==='wechat_save'));});

test('business license upload stays adjacent to every active business-license field',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});const i=f.page.data.fields.findIndex(x=>x.path==='subject_info.business_license_info.merchant_name');assert.ok(i>=0);f.page.setData({fieldCursor:i,cursorPath:'subject_info.business_license_info.merchant_name'});f.page.refresh();assert.equal(f.page.data.fields[f.page.data.fieldCursor].path,'subject_info.business_license_info.merchant_name');assert.equal(f.page.data.showLicenseUpload,true);f.page.setData({options:{...f.page.data.options,entity:'SOLE_PROPRIETOR'},fieldCursor:i,cursorPath:'subject_info.business_license_info.merchant_name'});f.page.refresh();assert.equal(f.page.data.showLicenseUpload,true,'required license available for sole proprietor');f.page.setData({options:{...f.page.data.options,entity:'ENTERPRISE'}});f.page.refresh();const j=f.page.data.fields.findIndex(x=>x.path==='contact_info.mobile_phone');assert.ok(j>=0);f.page.setData({fieldCursor:j,cursorPath:'contact_info.mobile_phone'});f.page.refresh();assert.equal(f.page.data.showLicenseUpload,true,'license upload remains immediately visible, independent of field cursor');});
test('native field cursor refreshes license upload and preserves adjacent identity material paths',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 f.page.setData({catalog:[...f.page.data.catalog,...['identity_front','identity_back','operator_identity','operator_identity_back'].map(id=>({id,title:id}))]});f.page.refresh();
 assert.equal(f.page.data.showLicenseUpload,true,'license upload remains visible on stage zero');
 for(let i=0;i<5;i++)f.page.nextField();
 assert.equal(f.page.data.fields[f.page.data.fieldCursor].path,'subject_info.business_license_info.period_end');
 assert.equal(f.page.data.showLicenseUpload,true);
 f.page.nextField();assert.equal(f.page.data.showLicenseUpload,true,'license upload remains visible on stage zero');
 assert.deepEqual(Array.from(f.page.data.adjacentMaterials,m=>m.id),['identity_front','identity_back']);
 f.page.previousField();assert.equal(f.page.data.showLicenseUpload,true);
 f.page.setData({step:0,cursorPath:'',fieldCursor:0,options:{...f.page.data.options,contact:'SUPER'}});f.page.refresh();
 assert.deepEqual(Array.from(f.page.data.materialGroups.find(g=>g.id==='operator').materials,m=>m.id),['operator_identity','operator_identity_back']);
 assert.equal(f.page.data.fields.some(x=>x.path==='contact_info.contact_id_doc_type'),false,'no duplicate type selector');
 f.page.selectDocumentType({currentTarget:{dataset:{path:'contact_info.contact_id_doc_type'}},detail:{value:1}});
 assert.deepEqual(Array.from(f.page.data.materialGroups.find(g=>g.id==='operator').materials,m=>m.id),['operator_identity']);
 assert.equal(f.page.materialProfilePath('operator_identity'),'contact_info.contact_id_doc_copy');
});
test('saved SUPER administrator remains SUPER when reopening its original application',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 f.page.setData({options:{...f.page.data.options,contact:'SUPER'}});await f.page.save();
 assert.equal(f.page.data.options.contact,'SUPER');
 assert.equal(f.page.data.application.application,f.app.application);
 assert.equal(form.get(f.page.profile,'contact_info.contact_type'),'SUPER');
});

test('scene photographs require no OCR while business license keeps its distinct status',()=>{const options={entity:'ENTERPRISE',contact:'LEGAL',doc:form.docs[0],scene:'both',ubos:'unknown'};const groups=form.materialGroups({},options,[],1);const photos=groups.find(g=>g.id==='store');assert.equal(photos.ocrKind,undefined);assert.equal(photos.photos,true);assert.match(photos.note,/场景照片不做OCR/);assert.equal(form.materialGroups({},options,[],0)[0].ocrKind,'business_license');});

test('confirmed scene photo cards keep two required frames and retain uploaded cashier history',()=>{const css=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxss','utf8');const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.match(css,/\.onboarding-page \.upload-choice\{[^}]*border:/);assert.match(wxml,/wx:for="{{group.materials}}"[^>]*class="upload-slot"/);const groups=form.materialGroups({}, {entity:'ENTERPRISE',contact:'LEGAL',doc:form.docs[0],scene:'both',ubos:'unknown'},[],1);assert.deepEqual(groups.find(g=>g.id==='store').materials.map(x=>x.id),['storefront_photo','interior_photo']);const history=form.materialGroups({}, {entity:'ENTERPRISE',contact:'LEGAL',doc:form.docs[0],scene:'both',ubos:'unknown'},[{id:'cashier_photo',uploaded:true}],1);assert.deepEqual(history.find(g=>g.id==='store').materials.map(x=>x.id),['storefront_photo','interior_photo','cashier_photo']);});

test('scene photos appear beside chosen actual store scene and not in mini-only scene',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.equal(wxml.includes('bindinput="baseInput"'),false);f.page.setData({step:1,options:{...f.page.data.options,scene:'both'},catalog:[...f.page.data.catalog,...['storefront_photo','interior_photo','mini_program_screenshot'].map(id=>({id,title:id}))]});f.page.refresh();const groups=f.page.data.materialGroups;assert.equal(groups[0].id,'scene');assert.ok(!groups.find(g=>g.id==='store').fields.some(x=>x.path.endsWith('biz_store_address')));assert.match(groups.find(g=>g.id==='store').reuseHint,/返回第一步/);assert.deepEqual(Array.from(f.page.data.scenePhotoCards,x=>x.connected),[true,true,false]);assert.equal(f.page.materialProfilePath('storefront_photo'),'business_info.sales_info.biz_store_info.store_entrance_pic');assert.equal(f.page.materialProfilePath('interior_photo'),'business_info.sales_info.biz_store_info.indoor_pic');assert.equal(f.page.materialProfilePath('mini_program_screenshot'),'business_info.sales_info.mini_program_info.mini_program_pics');f.page.setData({options:{...f.page.data.options,scene:'mini'}});f.page.refresh();assert.equal(f.page.data.scenePhotoCards.length,0);assert.equal(f.page.data.materialGroups.some(g=>g.id==='store'),false);});

test('UBO passport hides only current beneficiaries back material',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({catalog:[...f.page.data.catalog,...['ubo_1_front','ubo_1_back','ubo_2_front','ubo_2_back'].map(id=>({id,title:id}))],options:{...f.page.data.options,entity:'ENTERPRISE',ubos:2,uboIndex:0}});form.put(f.page.profile,'subject_info.ubo_info_list.0.ubo_id_doc_type','IDENTIFICATION_TYPE_OVERSEA_PASSPORT');form.put(f.page.profile,'subject_info.ubo_info_list.1.ubo_id_doc_type','IDENTIFICATION_TYPE_IDCARD');f.page.refresh();assert.deepEqual(Array.from(f.page.data.adjacentMaterials,x=>x.id),['ubo_1_front']);f.page.setData({options:{...f.page.data.options,uboIndex:1}});f.page.refresh();assert.deepEqual(Array.from(f.page.data.adjacentMaterials,x=>x.id),['ubo_2_front','ubo_2_back']);});
test('selection immediately reveals document uploads above editable text and requires explicit OCR and human checking',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.ok(wxml.indexOf('wx:for="{{group.materials}}"')<wxml.indexOf('wx:for="{{group.fields}}"'));assert.ok(wxml.indexOf('识别营业执照')<wxml.indexOf('wx:for="{{group.fields}}"'));assert.match(wxml,/点击识别后请核对结果/);f.page.setData({options:{...f.page.data.options,entity:'SOLE_PROPRIETOR',contact:'SUPER'},catalog:[...f.page.data.catalog,...['identity_front','identity_back','operator_identity','operator_identity_back'].map(id=>({id,title:id}))]});f.page.refresh();assert.equal(f.page.data.materialGroups[0].id,'license');assert.ok(f.page.data.materialGroups.find(g=>g.id==='legal'));assert.ok(f.page.data.materialGroups.find(g=>g.id==='operator'));assert.equal(f.page.data.materialGroups.filter(g=>g.id==='contact').length,1);f.page.selectDocumentType({currentTarget:{dataset:{path:'subject_info.identity_info.id_doc_type'}},detail:{value:1}});assert.deepEqual(Array.from(f.page.data.materialGroups.find(g=>g.id==='legal').materials,m=>m.id),['identity_front']);assert.equal(f.calls.some(c=>/ocr|wechat_execute/.test(c.p.operation)),false);});

test('merchant material upload previews without WeChat transmission and automatically starts bound OCR',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});const choice=f.calls.find(c=>c.mediaChoice);assert.deepEqual(Array.from(choice.mediaChoice.sourceType),['album','camera']);assert.deepEqual(Array.from(choice.mediaChoice.mediaType),['image']);assert.equal(f.calls.find(c=>c.readFile).readFile,'synthetic-cashier.png');assert.equal(f.calls.find(c=>c.p&&c.p.operation==='upload').p.params.kind,'business_license');assert.equal(f.page.data.materialPreviews.business_license,'synthetic-cashier.png');assert.equal(form.get(f.storedProfile,'subject_info.business_license_info.license_copy'),undefined);assert.equal(f.page.data.materialGroups[0].materials[0].synced,false);assert.equal(f.calls.some(c=>c.p&&c.p.operation==='wechat_media'),false);const ocr=f.calls.filter(c=>c.op==='ocr');assert.deepEqual(Array.from(ocr,c=>c.p.action),['submit','read']);assert.equal(ocr[0].p.document_type,'business_license');assert.equal(f.page.data.ocrKind,'business_license');assert.match(f.page.data.ocrStatus,/识别建议/);assert.equal(f.page.data.ocrRows[0].value,'Fixture Company');const script=fs.readFileSync(__dirname+'/pages/merchant-join/index.js','utf8'),markup=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.doesNotMatch(script,/chooseMessageFile/);assert.match(markup,/materialPreviews\[item\.id\]/);assert.match(markup,/拍照 \/ 从相册选择/);});

test('business-license upload, OCR confirmation, blank-only fill and same-application reread form one pipeline',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});
 assert.deepEqual(Array.from(f.calls.filter(c=>c.op==='ocr'),c=>c.p.action),['submit','read']);
 form.put(f.page.profile,'subject_info.business_license_info.merchant_name','MANUAL EXISTING');
 f.page.editOcrSuggestion({currentTarget:{dataset:{key:'company_name'}},detail:{value:'OCR MUST NOT OVERWRITE'}});
 await f.page.confirmOcr();assert.equal(f.page.data.ocrConfirmed,true);assert.match(f.page.data.ocrStatus,/人工确认已留存/);
 await f.page.fillOcrDraft();
 assert.equal(form.get(f.page.profile,'subject_info.business_license_info.merchant_name'),'MANUAL EXISTING');
 assert.equal(form.get(f.page.profile,'subject_info.business_license_info.license_address'),'OCR Address');
 assert.equal(form.get(f.storedProfile,'subject_info.business_license_info.merchant_name'),'MANUAL EXISTING');
 // Re-confirm without changing the application, then reload the same application.
 await f.page.recognizeDocument({currentTarget:{dataset:{kind:'business_license'}}});await f.page.confirmOcr();
 const readsBefore=f.calls.filter(c=>c.op==='ocr'&&c.p.action==='read').length;await f.page.load(f.app.application);
 assert.equal(f.calls.filter(c=>c.op==='ocr'&&c.p.action==='read').length,readsBefore+1);assert.equal(f.page.data.ocrConfirmed,true);assert.match(f.page.data.ocrStatus,/人工确认已留存/);
});

test('upload errors remain an upload-stage failure and do not render as a login request',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.failNext('upload',Error('synthetic upload failure'));await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});
 assert.equal(f.page.data.authenticated,true);assert.match(f.page.data.status,/照片上传失败/);assert.equal(f.page.data.readState,'READY');
});

test('oversized phone photo is previewed, compressed and only the bounded image is uploaded',async()=>{const f=fixture('merchant-join',{largeMedia:true});await f.page.onLoad({scene:'shop1'});await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});assert.deepEqual(f.calls.find(c=>c.compress).compress,{src:'synthetic-cashier.png',quality:90});assert.equal(f.page.data.materialPreviews.business_license,'synthetic-compressed.png');assert.equal(f.calls.some(c=>c.readFile==='synthetic-cashier.png'),false);assert.ok(f.calls.some(c=>c.readFile==='synthetic-compressed.png'));assert.ok(f.calls.some(c=>c.p&&c.p.operation==='upload'));});

test('multiple legacy applications expose and open only one canonical continuation',async()=>{const f=fixture('merchant-join',{duplicateApplications:true});await f.page.onLoad({scene:'shop1'});assert.equal(f.page.data.applications.length,1);assert.equal(f.page.data.application.application,'ma_'+ '2'.repeat(32));assert.equal(f.page.data.application.status,'APPROVED');assert.equal(f.calls.filter(c=>c.p&&c.p.operation==='read').length,1);});

 test('cashier native uploads privately, internally links, replaces, removes and rereads the same original application without OCR',async()=>{const f=fixture('merchant-join');f.app.sales_scenes_type.push('SALES_SCENES_STORE');await f.page.onLoad({scene:'shop1'});await f.page.load(f.app.application);f.page.setData({step:1,options:{...f.page.data.options,scene:'both'},catalog:[...f.page.data.catalog,{id:'cashier_photo',title:'收银台照'}]});f.page.refresh();let card=f.page.data.scenePhotoCards.find(c=>c.id==='cashier_photo');assert.equal(card.connected,true);assert.equal(card.required,false);const ev={currentTarget:{dataset:{kind:'cashier_photo'}}};await f.page.upload(ev);card=f.page.data.scenePhotoCards.find(c=>c.id==='cashier_photo');assert.equal(card.uploaded,true);assert.equal(card.synced,false);assert.equal(f.calls.some(c=>['wechat_media','wechat_cashier_link'].includes(c.p.operation)),false);await f.page.upload(ev);assert.equal(f.calls.filter(c=>c.p.operation==='upload').length,2);await f.page.syncMaterial(ev);assert.equal(f.page.data.scenePhotoCards.find(c=>c.id==='cashier_photo').synced,true);assert.equal(f.calls.find(c=>c.p.operation==='wechat_cashier_link').p.params.application,f.app.application);await f.page.removeCashierPhoto();assert.equal(f.page.data.scenePhotoCards.find(c=>c.id==='cashier_photo').uploaded,false);const removal=f.calls.find(c=>c.p.operation==='remove_material');assert.equal(removal.p.params.kind,'cashier_photo');assert.equal(removal.p.params.application,f.app.application);assert.equal(f.calls.some(c=>/ocr|wechat_execute/.test(c.p.operation)),false);});
 test('cashier upload rejection keeps prior slot and never marks association successful',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});await f.page.load(f.app.application);f.failNext('upload',Error('scan rejected'));await f.page.upload({currentTarget:{dataset:{kind:'cashier_photo'}}});assert.equal(f.page.data.application.materials.cashier_photo,undefined);assert.match(f.page.data.status,/error/);assert.equal(f.calls.some(c=>c.p.operation==='wechat_cashier_link'),false);});

test('cashier receipt and visible cards clear on session revocation',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.cashierMediaId='private-old-receipt';f.page.setData({scenePhotoCards:[{id:'cashier_photo',uploaded:true,synced:true}]});f.page.customerSessionRevoked();assert.equal(f.page.cashierMediaId,'');assert.equal(f.page.data.scenePhotoCards.length,0);assert.equal(f.page.data.application,null);});

test('cashier association initializes a missing WeChat draft before media/link steps',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});await f.page.load(f.app.application);f.page.version=0;f.page.setData({dirty:false});const start=f.calls.length;await f.page.syncMaterial({currentTarget:{dataset:{kind:'cashier_photo'}}});const ops=f.calls.slice(start).map(c=>c.p.operation);assert.ok(ops.indexOf('wechat_save')>=0&&ops.indexOf('wechat_save')<ops.indexOf('wechat_media'));assert.ok(ops.indexOf('wechat_cashier_link')>ops.indexOf('wechat_media'));});

test('scene-less applicant restores identity and reads existing application without fabricated scene',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({});
 assert.equal(f.calls.length,2);assert.equal(f.page.data.ready,true);assert.equal(f.page.data.canEditPlatform,true);
 assert.ok(f.calls.every(c=>c.scene===''));assert.deepEqual(f.calls.map(c=>c.p.operation),['catalog','mine']);
 await f.page.save();assert.ok(f.calls.some(c=>c.p.operation==='save'&&c.scene===''));
 f.page.customerSessionRevoked();assert.equal(f.page.data.ready,false);assert.equal(f.page.data.canEditPlatform,false);
});

test('document selector immediately selects original passport material contract without back image',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({catalog:[...f.page.data.catalog,...['identity_front','identity_back','ubo_1_front','ubo_1_back'].map(id=>({id,title:id}))]});f.page.refresh();f.page.selectDocumentType({currentTarget:{dataset:{path:'subject_info.identity_info.id_doc_type'}},detail:{value:1}});assert.equal(f.page.data.options.doc,'IDENTIFICATION_TYPE_OVERSEA_PASSPORT');assert.deepEqual(Array.from(f.page.data.documentGroups[0].materials,m=>m.id),['identity_front']);assert.equal(f.page.data.documentGroups[0].label,'境外护照');assert.equal(f.calls.some(c=>c.p&&/ocr|execute/.test(c.p.operation)),false);});
test('save and leave actually navigates after the original draft requests finish',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.input({currentTarget:{dataset:{path:'business_info.merchant_shortname'}},detail:{value:'Changed'}});f.page.navigateSection({currentTarget:{dataset:{section:'orders'}}});await f.page.saveAndLeave();assert.equal(f.page.data.dirty,false);assert.equal(f.page.data.pending,false);assert.equal(f.calls.at(-1).navigation,'/pages/checkout/index?view=orders&scene=shop1');});

test('revoked dirty applicant can leave without saving or retaining private material metadata',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({dirty:true,leavePrompt:true,leaveTarget:'orders',documentGroups:[{materials:[{uploaded:true}]}]});f.page.customerSessionRevoked();assert.equal(f.page.data.dirty,false);assert.equal(f.page.data.leavePrompt,false);assert.equal(f.page.data.leaveTarget,'');assert.equal(f.page.session,null);assert.equal(f.page.data.documentGroups.length,0);f.page.navigateSection({currentTarget:{dataset:{section:'home'}}});assert.equal(f.calls.at(-1).navigation,'/pages/home/index?scene=shop1');});

test('session revocation clears prior application progress states as well as fields',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({step:3,platformState:'APPROVED',wechatState:'FINISHED',openingState:'OPEN'});f.page.customerSessionRevoked();assert.equal(f.page.data.step,0);assert.equal(f.page.data.platformState,'未提交');assert.equal(f.page.data.wechatState,'未核验');assert.equal(f.page.data.openingState,'未开通');});

test('single WeChat form projects same mini/store fields without independent base overrides',()=>{
 const p={subject_info:{business_license_info:{merchant_name:'Company',license_address:'Optional license address'}},contact_info:{mobile_phone:'13800000000'},business_info:{merchant_shortname:'Short name',sales_info:{sales_scenes_type:['SALES_SCENES_MINI_PROGRAM']}}};
 assert.deepEqual(form.platformFields(p,{store_name:'WRONG SECOND FORM',address:'WRONG SECOND FORM'}),{legal_name:'Company',contact:'13800000000',store_name:'Short name',address:'Optional license address'});
 p.business_info.sales_info.sales_scenes_type.push('SALES_SCENES_STORE');p.business_info.sales_info.biz_store_info={biz_store_name:'Actual store',biz_store_address:'Actual address'};
 assert.equal(form.platformFields(p).store_name,'Actual store');assert.equal(form.platformFields(p).address,'Actual address');
});
test('all document types selected once beside uploads and official store fields are conditional',()=>{
 const base={entity:'ENTERPRISE',contact:'SUPER',doc:form.docs[0],scene:'mini',ubos:2,uboIndex:1};
 for(const doc of form.docs)for(const step of [0,1,2])assert.ok(form.rows({}, {...base,doc},step).every(f=>!f.path.endsWith('id_doc_type')));
 assert.ok(form.rows({},base,1).every(f=>!f.path.includes('biz_store_info')));
 const paths=form.rows({}, {...base,scene:'both'},1).map(f=>f.path);
 for(const field of ['biz_store_name','biz_store_address','biz_address_code'])assert.ok(paths.includes('business_info.sales_info.biz_store_info.'+field));
 const markup=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.equal(markup.includes('data-key="category"'),false);assert.equal(markup.includes('其他受益人'),false);const g=form.materialGroups({},base,[],0).find(g=>g.id==='beneficiaries');assert.ok(g.conditionLabels.includes('尚待确认'));assert.ok(g.conditionLabels.includes('已确认仅法人一人受益'));assert.ok(g.conditionLabels.includes('完整名单4人'));
});

test('final design begins unknown and persists same-application declarations without inferred mini scope',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});assert.equal(f.page.data.options.scene,'unknown');assert.equal(f.page.data.options.ubos,'unknown');await f.page.save();const params=f.calls.find(c=>c.p.operation==='save').p.params;assert.deepEqual(params.declarations,{scene:'unknown',ubos:'unknown'});assert.equal(params.sales_scenes_type,undefined);assert.equal(form.get(f.storedProfile,'business_info.sales_info.sales_scenes_type'),undefined);assert.equal(f.page.data.options.scene,'unknown');assert.equal(f.page.data.options.ubos,'unknown');f.page.setData({step:1});f.page.refresh();assert.ok(f.page.data.materialGroups.find(g=>g.id==='store'));assert.equal(f.page.data.materialGroups.some(g=>g.id==='mini'),false);});
test('final design all beneficiaries have adjacent fields and distinct passport material selection',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({options:{...f.page.data.options,ubos:2}});f.page.refresh();const a=f.page.data.materialGroups.find(g=>g.id==='ubo0'),b=f.page.data.materialGroups.find(g=>g.id==='ubo1');assert.ok(a.fields.length>=5&&b.fields.length>=5);assert.ok(a.fields.every(x=>x.path.startsWith('subject_info.ubo_info_list.0.')));assert.ok(b.fields.every(x=>x.path.startsWith('subject_info.ubo_info_list.1.')));f.page.selectDocumentType({currentTarget:{dataset:{path:a.docPath}},detail:{value:1}});assert.equal(f.page.data.materialGroups.find(g=>g.id==='ubo0').materials.length,1);assert.equal(f.page.data.materialGroups.find(g=>g.id==='ubo1').materials.length,2);});
test('progress returns to exact original material group without new request or identity',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({step:3});f.page.refresh();const before=f.calls.length;f.page.returnMaterial({currentTarget:{dataset:{step:0,group:'legal'}}});assert.equal(f.page.data.step,0);assert.equal(f.calls.length,before);assert.ok(f.page.data.materialGroups.find(g=>g.id==='legal'));});

test('reopened individual declaration switches back to unknown enterprise rather than not_applicable',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.condition({currentTarget:{dataset:{key:'entity'}},detail:{value:1}});await f.page.save();assert.equal(f.page.data.options.entity,'SOLE_PROPRIETOR');assert.equal(f.page.data.options.ubos,'not_applicable');f.page.condition({currentTarget:{dataset:{key:'entity'}},detail:{value:0}});assert.equal(f.page.data.options.entity,'ENTERPRISE');assert.equal(f.page.data.options.ubos,'unknown');const g=f.page.data.materialGroups.find(g=>g.id==='beneficiaries');assert.equal(g.conditionValue,0);await f.page.save();assert.equal(f.page.data.application.declarations.ubos,'unknown');assert.equal(f.page.data.application.entity_type,'ENTERPRISE');});

test('native DOM projection changes tag selectors without corrupting CSS properties or class names',()=>{const {nativeCss}=require('../../tests/community_mini_native_render.cjs');const css='page{color:red} .text-link, view > text{ text-align:left; text-decoration:none } picker:hover{color:green}';const out=nativeCss(css);assert.match(out,/body\{/);assert.match(out,/\.text-link, div > span/);assert.match(out,/text-align:left/);assert.match(out,/text-decoration:none/);assert.match(out,/select:hover/);assert.ok(!out.includes('span-align'));});
test('original FOOD material rule and optional supplements are reachable without new mandatory documents',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({step:2,catalog:[...f.page.data.catalog,...['industry_permit','settlement_proof','operator_authorization'].map(id=>({id,title:id}))]});f.page.refresh();assert.equal(f.page.data.materialGroups.some(g=>g.id==='qualification'),false);f.page.condition({currentTarget:{dataset:{key:'category'}},detail:{value:1}});assert.equal(f.page.data.options.category,'FOOD');assert.equal(f.page.data.materialGroups.find(g=>g.id==='qualification').materials[0].id,'industry_permit');assert.equal(f.page.data.materialGroups.some(g=>g.id==='optional'),false);const historical=form.materialGroups(f.page.profile,f.page.data.options,[{id:'settlement_proof',uploaded:true,required:false}],2).find(g=>g.id==='optional');assert.equal(historical.optional,true);assert.ok(historical.materials.every(m=>!m.required));assert.equal(f.page.data.showOptionalMaterials,false);f.page.toggleOptional();assert.equal(f.page.data.showOptionalMaterials,true);await f.page.save();assert.equal(f.calls.find(c=>c.p.operation==='save').p.params.category,'FOOD');});

test('bank account choices display Chinese while retaining original submitted enum',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({step:2});f.page.refresh();const bank=f.page.data.materialGroups.find(g=>g.id==='bank').fields.find(x=>x.path==='bank_account_info.bank_account_type');assert.equal(bank.label,'账户类型');assert.deepEqual(bank.choices,['','BANK_ACCOUNT_TYPE_CORPORATE']);assert.deepEqual(bank.choiceLabels,['请选择实际账户类型','对公账户']);assert.equal(bank.choiceLabel,'请选择');f.page.choice({currentTarget:{dataset:{index:bank.index}},detail:{value:'1'}});assert.equal(form.get(f.page.profile,bank.path),'BANK_ACCOUNT_TYPE_CORPORATE');assert.equal(f.page.data.materialGroups.find(g=>g.id==='bank').fields.find(x=>x.path===bank.path).choiceLabel,'对公账户');});
test('material-group return waits for render completion before exact scroll',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});let completion;const original=f.page.setData;f.page.setData=function(p,afterRender){original.call(this,p);if(afterRender)completion=afterRender;};f.page.setData({step:3});f.page.refresh();f.page.returnMaterial({currentTarget:{dataset:{step:0,group:'legal'}}});assert.equal(typeof completion,'function');assert.equal(f.page.data.step,0);assert.ok(f.page.data.materialGroups.find(g=>g.id==='legal'));completion();});
test('original status meanings and recommendation header are display-only',()=>{const f=fixture('merchant-join');assert.equal(f.page.data.stateLabels.DRAFT,'草稿未提交');assert.equal(f.page.data.stateLabels.NOT_VERIFIED,'尚未核验');assert.equal(f.page.data.stateLabels.NOT_APPROVED,'尚未开通');assert.equal(f.page.data.stateLabels.APPROVED,'平台审核通过');const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.doesNotMatch(wxml,/微信资料内部审核：|平台审核：/);assert.match(wxml,/class="progress-state"/);assert.match(fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8'),/recommendations-page/);assert.match(fs.readFileSync(__dirname+'/pages/checkout/index.wxss','utf8'),/background:#f5f8f7/);});
test('confirmed UI shows field values before editing and collapses without clearing actual draft',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 const group=f.page.data.materialGroups.find(x=>x.fields.length);assert.ok(group);
 form.put(f.page.profile,'contact_info.mobile_phone','13800138000');
 assert.equal(f.page.data.editMaterialGroup,'');
 f.page.toggleMaterialEdit({currentTarget:{dataset:{group:group.id}}});assert.equal(f.page.data.editMaterialGroup,group.id);
 f.page.toggleMaterialEdit({currentTarget:{dataset:{group:group.id}}});assert.equal(f.page.data.editMaterialGroup,'');
 assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),'13800138000');
 f.page.setData({canEditWechat:false});f.page.toggleMaterialEdit({currentTarget:{dataset:{group:group.id}}});assert.equal(f.page.data.editMaterialGroup,'');
 const markup=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.match(markup,/confirmed-field-list/);assert.match(markup,/bindinput="inputUnifiedField"/);
});
test('only confirmed bound license reuses name/address into blank store fields; manual changes remain',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 form.put(f.page.profile,'subject_info.business_license_info.merchant_name','已核企业');form.put(f.page.profile,'subject_info.business_license_info.license_address','已核地址');
 f.page.ocrCapture={document_type:'business_license'};f.page.ocrCurrent=()=>true;
 assert.equal(f.page.reuseConfirmedLicense(),0);f.page.setData({ocrConfirmed:true});
 assert.equal(f.page.reuseConfirmedLicense(),2);assert.equal(form.get(f.page.profile,'business_info.sales_info.biz_store_info.biz_store_name'),'已核企业');
 form.put(f.page.profile,'business_info.sales_info.biz_store_info.biz_store_address','商家修订地址');assert.equal(f.page.reuseConfirmedLicense(),0);assert.equal(form.get(f.page.profile,'business_info.sales_info.biz_store_info.biz_store_address'),'商家修订地址');
 f.page.ocrCurrent=()=>false;assert.equal(f.page.reuseConfirmedLicense(),0);
});
test('industry selection maps explicit subject and clears stale rules for other real industry',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});assert.equal(form.get(f.page.profile,'settlement_info.settlement_id'),undefined);f.page.chooseIndustry({detail:{value:'2'}});assert.equal(form.get(f.page.profile,'settlement_info.settlement_id'),'716');assert.equal(form.get(f.page.profile,'settlement_info.qualification_type'),'零售');assert.doesNotMatch(f.page.data.industryHint,/0.6%|公示参考|费率/);f.page.chooseIndustry({detail:{value:String(f.page.data.industryLabels.length-1)}});assert.equal(form.get(f.page.profile,'settlement_info.qualification_type'),'');assert.equal(form.get(f.page.profile,'settlement_info.settlement_id'),undefined);f.page.inputIndustry({detail:{value:'真实其他行业'}});f.page.setData({canEditWechat:false});f.page.chooseIndustry({detail:{value:'1'}});assert.equal(form.get(f.page.profile,'settlement_info.qualification_type'),'真实其他行业');});
test('region columns never write guessed code until explicit valid confirmation',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});const path='business_info.sales_info.biz_store_info.biz_address_code';assert.equal(form.get(f.page.profile,path),undefined);f.page.changeRegionColumn({detail:{column:0,value:1}});assert.equal(form.get(f.page.profile,path),undefined);const indices=f.page.data.regionIndices;f.page.chooseRegion({detail:{value:indices}});const code=form.get(f.page.profile,path);assert.match(code,/^[0-9]{6}$/);f.page.chooseRegion({detail:{value:[9999,9999,9999]}});assert.equal(form.get(f.page.profile,path),code);f.page.setData({canEditWechat:false});f.page.chooseRegion({detail:{value:[0,0,0]}});assert.equal(form.get(f.page.profile,path),code);});


// Added isolated lifecycle cases; no network or customer material.
test('image selection cancellation has explicit non-upload feedback',async()=>{const options={chooseMedia:o=>o.fail({errMsg:'chooseMedia:fail cancel'})};const f=fixture('merchant-join',options);await f.page.onLoad({scene:'shop1'});await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});assert.match(f.page.data.status,/取消选择照片，未上传/);assert.equal(f.calls.some(c=>c.p&&c.p.operation==='upload'),false);});
test('account revocation while chooser is open discards late selection',async()=>{let choose;const f=fixture('merchant-join',{chooseMedia:o=>{choose=o;}});await f.page.onLoad({scene:'shop1'});const uploading=f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});f.page.customerSessionRevoked();choose.success({tempFiles:[{tempFilePath:'synthetic-cashier.png'}]});await uploading;assert.equal(f.calls.some(c=>c.p&&c.p.operation==='read_file'),false);assert.equal(f.calls.some(c=>c.p&&c.p.operation==='upload'),false);assert.equal(Object.keys(f.page.data.materialPreviews).length,0);});
test('new application while chooser is open cannot receive old selection',async()=>{let choose;const f=fixture('merchant-join',{chooseMedia:o=>{choose=o;}});await f.page.onLoad({scene:'shop1'});const uploading=f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});f.page.data.application={...f.app,application:'ma_other'};choose.success({tempFiles:[{tempFilePath:'synthetic-cashier.png'}]});await uploading;assert.equal(f.calls.some(c=>c.p&&c.p.operation==='upload'),false);});
test('repeat upload click while choosing has only one selection and request',async()=>{let choose,count=0;const f=fixture('merchant-join',{chooseMedia:o=>{count++;choose=o;}});await f.page.onLoad({scene:'shop1'});const event={currentTarget:{dataset:{kind:'storefront_photo'}}};const uploading=f.page.upload(event);await f.page.upload(event);assert.equal(count,1);choose.success({tempFiles:[{tempFilePath:'synthetic-cashier.png'}]});await uploading;assert.equal(f.calls.filter(c=>c.p&&c.p.operation==='upload').length,1);assert.equal(f.calls.filter(c=>c.op==='ocr').length,0);});
test('unload during image compression does not read or upload candidate',async()=>{let compress;const f=fixture('merchant-join',{largeMedia:true,compressImage:o=>{compress=o;}});await f.page.onLoad({scene:'shop1'});const uploading=f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});for(let i=0;i<10&&!compress;i++)await Promise.resolve();assert.ok(compress);f.page.onUnload();compress.success({tempFilePath:'synthetic-compressed.png'});await uploading;assert.equal(f.calls.some(c=>c.p&&c.p.operation==='read_file'),false);assert.equal(f.calls.some(c=>c.p&&c.p.operation==='upload'),false);});

for(const change of ['scene','session','application'])test('guarded draft save stops old image after '+change+' changes during await',async()=>{let release,reached;const entered=new Promise(r=>reached=r),wait=new Promise(r=>release=r);const options={beforeOperation:async(op,p)=>{if(p.operation==='save'){reached();await wait;}}};const f=fixture('merchant-join',options);await f.page.onLoad({scene:'shop1'});const uploading=f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});await entered;if(change==='scene')f.page.scene='other-shop';if(change==='session')f.page.session={};if(change==='application')f.page.data.application={...f.app,application:'ma_other'};release();await uploading;assert.equal(f.calls.some(c=>c.p&&c.p.operation==='upload'),false);assert.equal(f.calls.some(c=>c.p&&c.p.operation==='wechat_save'),false);});
test('guarded save allows same application revision/object replacement',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});await f.page.load(f.app.application);f.page.data.dirty=true;await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});const uploads=f.calls.filter(c=>c.p&&c.p.operation==='upload');assert.equal(uploads.length,1);assert.equal(uploads[0].p.params.application,f.app.application);});
test('first-save image binds the server-created application before upload',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});assert.equal(f.page.data.application,null);await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});const upload=f.calls.find(c=>c.p&&c.p.operation==='upload');assert.equal(upload.p.params.application,f.app.application);});
for(const change of ['scene','session','application'])test('media synchronization stops draft mutation after '+change+' changes during await',async()=>{let release,reached;const entered=new Promise(r=>reached=r),wait=new Promise(r=>release=r);const options={beforeOperation:async(op,p)=>{if(p.operation==='wechat_media'){reached();await wait;}}};const f=fixture('merchant-join',options);await f.page.onLoad({scene:'shop1'});await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});assert.equal(f.calls.some(c=>c.p&&c.p.operation==='wechat_media'),false);const before=f.calls.length;const syncing=f.page.syncCurrentMaterial('business_license',true);await entered;if(change==='scene')f.page.scene='other-shop';if(change==='session')f.page.session={};if(change==='application')f.page.data.application={...f.app,application:'ma_other'};release();await syncing;assert.equal(f.calls.filter(c=>c.p&&c.p.operation==='upload').length,1);assert.equal(f.calls.slice(before).some(c=>c.op==='ocr'||c.p&&c.p.operation==='wechat_save'),false);assert.equal(form.get(f.page.profile,'subject_info.business_license_info.license_copy'),undefined);});
test('uncertain upload does not auto-retry or start OCR and asks to read original application',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});await f.page.load(f.app.application);const begin=f.calls.length;f.failNext('upload',Object.assign(Error('timeout'),{networkKind:'TIMEOUT'}));await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});const calls=f.calls.slice(begin);assert.equal(calls.filter(x=>x.p&&x.p.operation==='upload').length,1);assert.equal(calls.filter(x=>x.op==='ocr').length,0);assert.match(f.page.data.status,/请先重新读取原申请，勿重复提交/);});

for(const status of [408,502,503,504])test(`HTTP ${status} uncertain upload keeps current application and does not resubmit or start OCR`,async()=>{
 const {createSession}=require('./session');const requests=[];
 const wx={login:o=>o.success({code:'synthetic'}),request(o){requests.push(o);o.success(o.url.endsWith('/mini/login')?{statusCode:200,data:{payment_enabled:false,result:{provider:'WECHAT_MINIPROGRAM',session_token:'S'.repeat(32),expires_at:200,payment_enabled:false}}}:{statusCode:status,data:{error:'synthetic failure'}});}};
 const session=createSession(wx,'https://example.org',()=>100);await session.login();let error;try{await session.merchant('shop1','onboarding',{operation:'upload',params:{}});}catch(e){error=e;}
 const f=fixture('merchant-join',{customerError:require('./session').customerError});await f.page.onLoad({scene:'shop1'});await f.page.load(f.app.application);const before=JSON.stringify(f.page.data.application),begin=f.calls.length;f.failNext('upload',error);await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});
 const calls=f.calls.slice(begin);assert.equal(calls.filter(x=>x.p&&x.p.operation==='upload').length,1);assert.equal(calls.filter(x=>x.op==='ocr').length,0);assert.equal(calls.filter(x=>x.p&&x.p.operation==='wechat_media').length,0);assert.equal(JSON.stringify(f.page.data.application),before);assert.match(f.page.data.status,/上传结果暂未确认.*重新读取原申请.*勿重复上传/);assert.equal(requests.length,2);
});

test('previous step preserves unsaved fields and uploaded material without any business request',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});f.page.data.step=2;f.page.input({currentTarget:{dataset:{path:'contact_info.mobile_phone'}},detail:{value:'+44-123456789'}});const before=JSON.stringify({profile:f.page.profile,materials:f.page.data.application.materials,previews:f.page.data.materialPreviews});const calls=f.calls.length;f.page.back();assert.equal(f.page.data.step,1);f.page.back();assert.equal(f.page.data.step,0);assert.equal(f.page.data.dirty,true);assert.equal(f.calls.length,calls);assert.equal(JSON.stringify({profile:f.page.profile,materials:f.page.data.application.materials,previews:f.page.data.materialPreviews}),before);await f.page.save();assert.equal(form.get(f.storedProfile,'contact_info.mobile_phone'),'+44-123456789');await f.page.load(f.app.application);assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),'+44-123456789');assert.ok(f.page.data.application.materials.business_license);});

test('final skipped stage has explicit edit return links; readonly navigation never writes',async()=>{for(const editable of [true,false]){const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({step:3,canEditWechat:editable,canEditPlatform:editable});f.page.refresh();assert.ok(f.page.data.reviewGroups.some(g=>g.id==='contact'&&g.step===0));const before=JSON.stringify(f.page.profile),count=f.calls.length;f.page.returnMaterial({currentTarget:{dataset:{step:0,group:'contact'}}});assert.equal(f.page.data.step,0);assert.equal(JSON.stringify(f.page.profile),before);assert.equal(f.calls.length,count);assert.equal(f.page.data.canEditWechat,editable);}const w=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.match(w,/修改本组资料/);assert.match(w,/查看本组资料（当前只读）/);});

test('workbench button and navigation require original approved AND opened state, never grant permission',async()=>{for(const [platform,opening,allowed] of [['DRAFT','NOT_APPROVED',false],['REJECTED','NOT_APPROVED',false],['CORRECTION_REQUIRED','NOT_APPROVED',false],['APPROVED','AWAITING_CRM_BINDING',false],['APPROVED','OPENED',true]]){const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({platformState:platform,openingState:opening,step:3});let navigation=0;f.page.navigateSection=()=>{navigation++;};const calls=f.calls.length;f.page.workbench();assert.equal(navigation,allowed?1:0);assert.equal(f.calls.length,calls);}const w=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.match(w,/platformState==='APPROVED' && openingState==='OPENED'/);});

test('redemption exact original options select save and reread; readonly and invalid inputs cannot change',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});for(const value of [0,10,20,25,30]){f.page.chooseRedemption({currentTarget:{dataset:{value:String(value)}}});assert.equal(f.page.data.pendingRedemptionPercent,value);assert.equal(f.page.data.dirty,true);await f.page.save();assert.equal(f.app.redemption_percent,value);assert.equal(f.page.data.application.redemption_percent,value);assert.equal(f.page.data.pendingRedemptionPercent,value);}f.page.chooseRedemption({currentTarget:{dataset:{value:99}}});assert.equal(f.page.data.pendingRedemptionPercent,30);f.page.data.canEditPlatform=false;f.page.chooseRedemption({currentTarget:{dataset:{value:10}}});assert.equal(f.page.data.pendingRedemptionPercent,30);f.page.data.canEditPlatform=true;f.page.data.pending=true;f.page.chooseRedemption({currentTarget:{dataset:{value:10}}});assert.equal(f.page.data.pendingRedemptionPercent,30);});

test('new application defaults to10 but existing explicit0 remains0; picker selection follows original array',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});assert.equal(f.page.data.application,null);assert.equal(f.page.data.pendingRedemptionPercent,10);await f.page.save();assert.equal(f.app.redemption_percent,10);f.page.chooseRedemption({currentTarget:{dataset:{}},detail:{value:'0'}});await f.page.save();assert.equal(f.app.redemption_percent,0);f.page.setData({pendingRedemptionPercent:30});await f.page.load(f.app.application);assert.equal(f.page.data.pendingRedemptionPercent,0);assert.equal(f.page.data.redemptionIndex,0);f.page.chooseRedemption({currentTarget:{dataset:{}},detail:{value:'3'}});assert.equal(f.page.data.pendingRedemptionPercent,25);});

test('OCR suggestions never gate manual license or identity validity dates and save retains all four',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({ocrKind:'business_license',ocrRows:[{key:'company_name',value:'SYNTHETIC'}]});f.page.refresh();const paths=['subject_info.business_license_info.period_begin','subject_info.business_license_info.period_end','subject_info.identity_info.id_card_info.card_period_begin','subject_info.identity_info.id_card_info.card_period_end'];for(const [index,path] of paths.entries()){const field=f.page.data.materialGroups.flatMap(g=>g.fields).find(x=>x.path===path);assert.ok(field,path);assert.equal(field.ocrResultPresent,false,path);f.page.input({currentTarget:{dataset:{path}},detail:{value:index%2?'2030-01-01':'2020-01-01'}});}await f.page.save();for(const [index,path] of paths.entries())assert.equal(form.get(f.storedProfile,path),index%2?'2030-01-01':'2020-01-01');});


test('only a new mini application defaults donation to50bps independently from points10',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 assert.equal(f.page.data.splitInput,'0.5');assert.equal(f.page.data.splitChoiceEdited,false);assert.equal(f.page.data.splitDefaultPending,true);
 await f.page.save();const save=f.calls.find(x=>x.p.operation==='save').p.params;
 assert.equal(save.split_participation,true);assert.equal(save.requested_split_bps,50);assert.equal(f.page.data.splitInput,'0.5');assert.equal(f.page.data.splitDefaultPending,false);
 assert.equal(save.redemption_percent,10,'the independently approved new-application points default stays unchanged');
});
test('explicit split percentage persists exact integer basis points and reloads separately from points',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 f.page.inputSplitPercent({detail:{value:'2.75'}});await f.page.save();
 const save=f.calls.find(x=>x.p.operation==='save').p.params;
 assert.equal(save.split_participation,true);assert.equal(save.requested_split_bps,275);assert.equal(save.redemption_percent,10);
 assert.equal(f.page.data.splitInput,'2.75');assert.equal(f.page.data.requestedSplitLabel,'2.75%');assert.equal(f.page.data.effectiveSplitLabel,'尚未生效');
 assert.equal(f.page.data.splitChoiceEdited,false);assert.equal(f.page.data.dirty,false);
 await f.page.load(f.app.application);assert.equal(f.page.data.splitInput,'2.75');
 assert.ok(f.calls.every(x=>!['wechat_execute','split','rule_create','community_receiver_bind'].includes(x.p.operation)));
});
test('explicit zero opts out while an untouched legacy positive choice is not silently reset',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 Object.assign(f.app,{split_participation:true,requested_split_bps:130,redemption_percent:0});await f.page.load(f.app.application);
 await f.page.save();let saves=f.calls.filter(x=>x.p.operation==='save');assert.equal(saves.at(-1).p.params.split_participation,undefined);assert.equal(f.app.requested_split_bps,130);assert.equal(f.page.data.pendingRedemptionPercent,0);
 f.page.inputSplitPercent({detail:{value:'0'}});await f.page.save();saves=f.calls.filter(x=>x.p.operation==='save');assert.equal(saves.at(-1).p.params.split_participation,false);assert.equal(saves.at(-1).p.params.requested_split_bps,0);assert.equal(f.page.data.requestedSplitLabel,'不参与（0%）');
});
test('split input rejects blank, extra precision, negative and excessive rates before transport',async()=>{
 for(const value of ['', ' ', '-1', '100.01', '101', '1e1', '0.001', '1.234', 'NaN', 'Infinity']){
  const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.inputSplitPercent({detail:{value}});await f.page.save();
  assert.equal(f.calls.filter(x=>x.p.operation==='save').length,0,value);assert.equal(f.page.data.splitSaveUnknown,false,value);
 }
});
test('split percentages preserve exact lower and upper basis-point boundaries',async()=>{
 for(const [value,bps]of [['0.01',1],['1.2',120],['100',10000]]){
  const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.inputSplitPercent({detail:{value}});await f.page.save();assert.equal(f.app.requested_split_bps,bps,value);
 }
});
test('approved application ratio is read-only with requested effective and provider maximum distinct',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});Object.assign(f.app,{status:'APPROVED',split_participation:true,requested_split_bps:250,effective_split_bps:250,provider_max_split_bps:1200});await f.page.load(f.app.application);
 assert.equal(f.page.data.requestedSplitLabel,'2.5%');assert.equal(f.page.data.effectiveSplitLabel,'2.5%');assert.equal(f.page.data.providerSplitLabel,'12%');
 f.page.inputSplitPercent({detail:{value:'5'}});assert.equal(f.page.data.splitInput,'2.5');assert.equal(f.page.data.splitChoiceEdited,false);
});
test('unknown split save is not retried and requires original application readback',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});await f.page.load(f.app.application);
 f.page.inputSplitPercent({detail:{value:'3'}});f.failNext('save',new Error('RESPONSE_UNKNOWN'));await f.page.save();
 assert.equal(f.page.data.splitSaveUnknown,true);const count=f.calls.filter(x=>x.p.operation==='save').length;
 f.page.inputSplitPercent({detail:{value:'9'}});assert.equal(f.page.data.splitInput,'3');await f.page.save();assert.equal(f.calls.filter(x=>x.p.operation==='save').length,count);
 // Synthetic lost reply: the authoritative original application can contain the accepted choice.
 Object.assign(f.app,{split_participation:true,requested_split_bps:300,effective_split_bps:0});await f.page.reloadSplitChoice();
 assert.equal(f.page.data.splitSaveUnknown,false);assert.equal(f.page.data.splitInput,'3');assert.equal(f.page.data.splitChoiceEdited,false);assert.equal(f.calls.filter(x=>x.p.operation==='save').length,count);
});
test('split UI contains no counterparty account field and does not promise admission or transfer',()=>{
 const markup=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');
 assert.match(markup,/bindinput="inputSplitPercent"/);assert.match(markup,/爱心捐赠比例/);assert.match(markup,/爱心积分抵扣收款金额比例/);assert.doesNotMatch(markup,/新申请默认10%|申请分账比例|以上为申请及配置状态/);
 assert.doesNotMatch(markup,/(?:bindinput|data-path)="(?:receiver_account|receiver_id|community_account|receiverAccount)"/);
});

test('LEGAL contact name is hidden and derives from the retained legal document on save, including non-ID cards',async()=>{
 for(const doc of [form.docs[0],form.docs[1]]){
  const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
  f.page.data.options.doc=doc;
  const path='subject_info.identity_info.'+(doc===form.docs[0]?'id_card_info.id_card_name':'id_doc_info.id_doc_name');
  f.page.input({currentTarget:{dataset:{path}},detail:{value:'CONFIRMED LEGAL NAME'}});
  f.page.refresh();assert.equal(f.page.data.materialGroups.find(g=>g.id==='contact').fields.length,2);
  assert.ok(!f.page.data.fields.some(x=>x.path==='contact_info.contact_name'));
  await f.page.save();assert.equal(form.get(f.storedProfile,'contact_info.contact_name'),'CONFIRMED LEGAL NAME');
  await f.page.load(f.app.application);assert.equal(form.get(f.page.profile,'contact_info.contact_name'),'CONFIRMED LEGAL NAME');
 }
});
test('SUPER operator name stays independent across role switches and same-application save/reopen',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 form.put(f.page.profile,'subject_info.identity_info.id_card_info.id_card_name','LEGAL PERSON');
 const choose=value=>f.page.condition({currentTarget:{dataset:{key:'contact'}},detail:{value}});
 choose(1);assert.equal(form.get(f.page.profile,'contact_info.contact_name'),'');
 f.page.input({currentTarget:{dataset:{path:'contact_info.contact_name'}},detail:{value:'INDEPENDENT OPERATOR'}});
 await f.page.save();assert.equal(form.get(f.storedProfile,'contact_info.contact_name'),'INDEPENDENT OPERATOR');
 assert.ok(f.page.data.materialGroups.find(g=>g.id==='operator').fields.some(x=>x.path==='contact_info.contact_name'));
 choose(0);await f.page.save();assert.equal(form.get(f.storedProfile,'contact_info.contact_name'),'LEGAL PERSON');
 choose(1);assert.equal(form.get(f.page.profile,'contact_info.contact_name'),'INDEPENDENT OPERATOR');
 await f.page.save();await f.page.load(f.app.application);assert.equal(form.get(f.page.profile,'contact_info.contact_name'),'INDEPENDENT OPERATOR');
 f.page.customerSessionRevoked();assert.equal(f.page.operatorContactName,'');
});
test('unconfirmed OCR identity suggestions never become the hidden LEGAL contact name',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 f.page.setData({ocrConfirmed:false,ocrKind:'id_front',ocrRows:[{key:'id_name',value:'UNCONFIRMED'}]});
 await f.page.save();assert.equal(form.get(f.storedProfile,'contact_info.contact_name'),undefined);
});
test('eleven-digit rule is identical on input blur and both submit routes; malformed drafts survive save/reopen',async()=>{
 for(const value of ['1234567890','123456789012','+13800138000','13800138x00','13800138000\n','１３８００１３８０００','']){
  const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
  f.page.input({currentTarget:{dataset:{path:'contact_info.mobile_phone'}},detail:{value}});
  assert.ok(f.page.data.mobilePhoneError);const message=f.page.data.mobilePhoneError;
  f.page.blur({currentTarget:{dataset:{path:'contact_info.mobile_phone'}}});assert.equal(f.page.data.mobilePhoneError,message);
  await f.page.save();assert.equal(form.get(f.storedProfile,'contact_info.mobile_phone'),value);
  await f.page.load(f.app.application);assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),value);
  const before=f.calls.length;await f.page.submit();assert.equal(f.calls.length,before);
  await f.page.submitAllReview();assert.equal(f.calls.length,before);assert.ok(f.page.data.mobilePhoneError);
 }
});
test('preexisting overlong phone is never truncated by render save or reread and a corrected value can submit',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 const value='123456789012345678901';form.put(f.page.profile,'contact_info.mobile_phone',value);f.page.refresh();
 assert.equal(f.page.data.fields.find(x=>x.path==='contact_info.mobile_phone').maxlength,-1);
 assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),value);
 await f.page.save();await f.page.load(f.app.application);assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),value);
 f.page.input({currentTarget:{dataset:{path:'contact_info.mobile_phone'}},detail:{value:'00123456789'}});
 assert.equal(f.page.data.mobilePhoneError,'');await f.page.save();
 let submissions=0;f.page.session.merchant=async(scene,op,p)=>{assert.equal(p.operation,'submit');submissions++;return {...f.app,status:'SUBMITTED'};};
 await f.page.submit();assert.equal(submissions,1);assert.equal(f.page.data.platformState,'SUBMITTED');
});
test('latest reread mobile is checked at submit transport boundary, not only before the shared flow',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 form.put(f.page.profile,'contact_info.mobile_phone','123456789012');await f.page.save();
 form.put(f.page.profile,'contact_info.mobile_phone','13800138000');f.page.data.dirty=false;form.put(f.page.profile,'business_info.sales_info.mini_program_info.mini_program_appid','wx'+'1'.repeat(16));f.app.required_materials=[];f.page.data.application.required_materials=[];
 const refresh=f.page.refresh.bind(f.page);f.page.refresh=function(...args){refresh(...args);this.data.reviewGroups=[{id:'contact',step:0,title:'联系人',items:[{path:'contact_info.mobile_phone',label:'手机号',complete:!form.mobilePhoneError(form.get(this.profile,'contact_info.mobile_phone'),true)}]}];};
 const before=f.calls.length;await f.page.submitAllReview();
 assert.ok(f.calls.length>before,'shared flow rereads the authoritative draft: '+f.page.data.status);
 assert.ok(!f.calls.slice(before).some(c=>['submit','wechat_submit_review'].includes(c.p.operation)));
 assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),'123456789012');
});
test('second stage hides duplicate name address and service phone, retains shorthand, and has one correction entry',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.data.options.scene='both';f.page.data.step=1;f.page.refresh();
 for(const path of ['business_info.sales_info.biz_store_info.biz_store_name','business_info.sales_info.biz_store_info.biz_store_address','business_info.service_phone'])assert.ok(!f.page.data.fields.some(x=>x.path===path),path);
 assert.ok(f.page.data.fields.some(x=>x.path==='business_info.merchant_shortname'));
 assert.equal(f.page.data.materialGroups.filter(g=>g.reuseHint).length,1);
 const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');
 assert.doesNotMatch(wxml,/资料直接填写|核对资料[、，]可修改|经营资料自行填写，可修改/);
 assert.match(wxml,/wx:if="{{group.hasOcrFields}}" class="fields-heading"/);
 assert.match(wxml,/'收起修改':'点击修改'/);assert.match(wxml,/>修改资料<\/button>/);
 assert.match(wxml,/'修改本组资料':'查看本组资料（当前只读）'/);
 assert.equal((wxml.match(/>返回第一步完善<\/button>/g)||[]).length,0);assert.match(wxml,/group.reuseHint && \(step!==0 \|\| group.conflictActions.length\)/);assert.match(wxml,/<text wx:if="{{step!==0}}" class="hint">{{group.reuseHint}}/);
 f.page.returnMaterial({currentTarget:{dataset:{step:0,group:'license'}}});assert.equal(f.page.data.step,0);
});
test('manual first-step name address and current operator mobile reuse into original fields and survive save/reopen',async()=>{
 for(const contact of ['LEGAL','SUPER']){
  const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.data.options={...f.page.data.options,contact,scene:'both'};
  for(const [path,value] of [['subject_info.business_license_info.merchant_name','DISTINCT SHOP NAME'],['subject_info.business_license_info.license_address','DISTINCT STREET ADDRESS'],['contact_info.mobile_phone','13800138000'],['business_info.merchant_shortname','SHORT MANUAL']])f.page.input({currentTarget:{dataset:{path}},detail:{value}});
  await f.page.save();await f.page.load(f.app.application);
  assert.equal(form.get(f.page.profile,'business_info.sales_info.biz_store_info.biz_store_name'),'DISTINCT SHOP NAME');
  assert.equal(form.get(f.page.profile,'business_info.sales_info.biz_store_info.biz_store_address'),'DISTINCT STREET ADDRESS');
  assert.equal(form.get(f.page.profile,'business_info.service_phone'),'13800138000');
  assert.equal(form.get(f.page.profile,'business_info.merchant_shortname'),'SHORT MANUAL');
  assert.equal(f.page.data.options.contact,contact);
 }
});
test('unconfirmed OCR name/address suggestions and invalid phone never fill hidden business fields',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.data.options.scene='both';
 f.page.setData({ocrConfirmed:false,ocrKind:'business_license',ocrRows:[{key:'company_name',value:'SUGGESTION NAME'},{key:'registered_address',value:'SUGGESTION ADDRESS'}]});
 form.put(f.page.profile,'contact_info.mobile_phone','12345');await f.page.save();
 for(const path of ['business_info.sales_info.biz_store_info.biz_store_name','business_info.sales_info.biz_store_info.biz_store_address','business_info.service_phone'])assert.equal(form.get(f.storedProfile,path),undefined);
});
test('different historical store and service fields stay unchanged with one conflict hint and no empty overwrite',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.data.options.scene='both';
 for(const [path,value] of [['subject_info.business_license_info.merchant_name','NEW NAME'],['subject_info.business_license_info.license_address','NEW ADDRESS'],['contact_info.mobile_phone','13800138000'],['business_info.sales_info.biz_store_info.biz_store_name','OLD NAME'],['business_info.sales_info.biz_store_info.biz_store_address','OLD ADDRESS'],['business_info.service_phone','555-0100']])form.put(f.page.profile,path,value);
 await f.page.save();await f.page.load(f.app.application);f.page.data.step=1;f.page.refresh();
 assert.equal(form.get(f.page.profile,'business_info.sales_info.biz_store_info.biz_store_name'),'OLD NAME');assert.equal(form.get(f.page.profile,'business_info.sales_info.biz_store_info.biz_store_address'),'OLD ADDRESS');assert.equal(form.get(f.page.profile,'business_info.service_phone'),'555-0100');
 assert.equal(f.page.data.materialGroups.filter(g=>g.reuseHint).length,1);assert.match(f.page.data.materialGroups.find(g=>g.id==='store').reuseHint,/不同，已保留原值/);
 form.put(f.page.profile,'subject_info.business_license_info.license_address','');form.put(f.page.profile,'contact_info.mobile_phone','');await f.page.save();
 assert.equal(form.get(f.storedProfile,'business_info.sales_info.biz_store_info.biz_store_address'),'OLD ADDRESS');assert.equal(form.get(f.storedProfile,'business_info.service_phone'),'555-0100');
});
test('source edits sync only linked business fields and restore matching links after reload',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.data.options.scene='both';
 const input=(path,value)=>f.page.input({currentTarget:{dataset:{path}},detail:{value}});
 const name='subject_info.business_license_info.merchant_name',address='subject_info.business_license_info.license_address',phone='contact_info.mobile_phone';
 input(name,'FIRST NAME');input(address,'FIRST ADDRESS');input(phone,'13800138000');await f.page.save();await f.page.load(f.app.application);
 input(name,'SECOND NAME');input(address,'SECOND ADDRESS');input(phone,'13800138001');await f.page.save();
 assert.equal(form.get(f.storedProfile,'business_info.sales_info.biz_store_info.biz_store_name'),'SECOND NAME');assert.equal(form.get(f.storedProfile,'business_info.sales_info.biz_store_info.biz_store_address'),'SECOND ADDRESS');assert.equal(form.get(f.storedProfile,'business_info.service_phone'),'13800138001');
 input(phone,'1');assert.equal(form.get(f.page.profile,'business_info.service_phone'),'13800138001');input(phone,'13800138002');assert.equal(form.get(f.page.profile,'business_info.service_phone'),'13800138002');
 form.put(f.page.profile,'business_info.sales_info.biz_store_info.biz_store_address','HISTORICAL DIFFERENT');input(address,'THIRD ADDRESS');assert.equal(form.get(f.page.profile,'business_info.sales_info.biz_store_info.biz_store_address'),'HISTORICAL DIFFERENT');
});
test('real industry control is visible without internal rule inputs or invented defaults',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.data.step=2;f.page.refresh();
 assert.ok(f.page.data.materialGroups.some(g=>g.id==='industry'));assert.ok(!f.page.data.fields.some(x=>x.path.startsWith('settlement_info.')));assert.equal(form.get(f.page.profile,'settlement_info.settlement_id'),undefined);
 const options={...f.page.data.options,category:'GENERAL'};assert.ok(form.materialGroups({},options,[{id:'industry_permit',required:true,connected:true}],2).find(g=>g.id==='qualification').materials.some(m=>m.id==='industry_permit'));
 const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.match(wxml,/bindchange="chooseIndustry"/);assert.match(wxml,/bindinput="inputIndustry"/);assert.doesNotMatch(wxml,/bindinput=".*settlement_id|\{\{group.note\}\}/);assert.match(wxml,/<button class="primary bank-ocr-entry" data-kind="bank_card" bindtap="recognizeDocument" disabled="{{pending\|\|!application\|\|!application.materials.bank_card}}">银行卡识别<\/button>/);assert.match(wxml,/需人工核对后保存/);
});
test('enterprise selector excludes personal while historical personal draft stays saved for explicit correction',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});form.put(f.page.profile,'bank_account_info.bank_account_type','BANK_ACCOUNT_TYPE_PERSONAL');form.put(f.page.profile,'bank_account_info.account_name','ORIGINAL HOLDER');form.put(f.page.profile,'bank_account_info.account_number','ORIGINAL NUMBER');await f.page.save();await f.page.load(f.app.application);f.page.data.step=2;f.page.refresh();
 const field=f.page.data.fields.find(x=>x.path==='bank_account_info.bank_account_type');assert.deepEqual(field.choices,['','BANK_ACCOUNT_TYPE_CORPORATE']);
 assert.equal(form.get(f.storedProfile,'bank_account_info.bank_account_type'),'BANK_ACCOUNT_TYPE_PERSONAL');assert.equal(form.get(f.storedProfile,'bank_account_info.account_name'),'ORIGINAL HOLDER');assert.equal(form.get(f.storedProfile,'bank_account_info.account_number'),'ORIGINAL NUMBER');assert.equal(f.page.data.materialGroups.find(g=>g.id==='bank').accountTypePending,true);
 const bank=f.page.data.reviewGroups.find(g=>g.id==='bank');assert.equal(bank.items.find(i=>i.path==='bank_account_info.bank_account_type').complete,false);assert.match(f.page.data.materialGroups.find(g=>g.id==='bank').accountTypeMessage,/企业主体当前仅接受对公/);
 const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.match(wxml,/group.accountTypeMessage/);assert.match(wxml,/group.accountTypeRule/);
});
test('personal holder uses legal identity or legal license name, never company or SUPER operator names',async()=>{
 for(const mode of ['identity','license','matching','conflicting','missing']){
  const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.data.options.entity='SOLE_PROPRIETOR';f.page.data.options.contact='SUPER';
  form.put(f.page.profile,'subject_info.business_license_info.merchant_name','COMPANY NOT A PERSON');form.put(f.page.profile,'contact_info.contact_name','OPERATOR NOT THE HOLDER');
  if(['identity','matching','conflicting'].includes(mode))form.put(f.page.profile,'subject_info.identity_info.id_card_info.id_card_name','LEGAL PERSON');
  if(['license','matching','conflicting'].includes(mode))form.put(f.page.profile,'subject_info.business_license_info.legal_person',mode==='conflicting'?'OTHER LEGAL':'LEGAL PERSON');
  f.page.data.step=2;f.page.refresh();const index=f.page.data.fields.findIndex(x=>x.path==='bank_account_info.bank_account_type');f.page.choice({currentTarget:{dataset:{index}},detail:{value:'2'}});await f.page.save();await f.page.load(f.app.application);
  assert.ok(!f.page.data.fields.some(x=>x.path==='bank_account_info.account_name'));
  assert.equal(form.get(f.storedProfile,'bank_account_info.account_name'),['conflicting','missing'].includes(mode)?undefined:'LEGAL PERSON');
  assert.equal(form.get(f.storedProfile,'contact_info.contact_name'),'OPERATOR NOT THE HOLDER');
  if(mode==='conflicting')assert.match(f.page.data.materialGroups.find(g=>g.id==='bank').reuseHint,/姓名不一致/);
  if(mode==='missing')assert.match(f.page.data.materialGroups.find(g=>g.id==='bank').reuseHint,/返回第一步/);
 }
});
test('personal holder restores linked reuse after save/reopen while different historical holder remains untouched',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 const id='subject_info.identity_info.id_card_info.id_card_name',legal='subject_info.business_license_info.legal_person',holder='bank_account_info.account_name';
 const edit=(path,value)=>f.page.input({currentTarget:{dataset:{path}},detail:{value}});
 edit(id,'FIRST PERSON');edit(legal,'FIRST PERSON');form.put(f.page.profile,'bank_account_info.bank_account_type','BANK_ACCOUNT_TYPE_PERSONAL');await f.page.save();await f.page.load(f.app.application);
 edit(id,'SECOND PERSON');assert.equal(form.get(f.page.profile,holder),'FIRST PERSON');edit(legal,'SECOND PERSON');assert.equal(form.get(f.page.profile,holder),'SECOND PERSON');await f.page.save();
 form.put(f.page.profile,holder,'HISTORICAL HOLDER');await f.page.save();await f.page.load(f.app.application);edit(id,'THIRD PERSON');edit(legal,'THIRD PERSON');await f.page.save();
 assert.equal(form.get(f.storedProfile,holder),'HISTORICAL HOLDER');f.page.data.step=2;f.page.refresh();assert.match(f.page.data.materialGroups.find(g=>g.id==='bank').reuseHint,/保留原值/);
});
test('switching private and corporate accounts preserves the chosen enum and never silently overwrites a historical holder',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.data.options.entity='SOLE_PROPRIETOR';form.put(f.page.profile,'subject_info.identity_info.id_card_info.id_card_name','LEGAL PERSON');form.put(f.page.profile,'bank_account_info.account_name','HISTORICAL COMPANY');f.page.data.step=2;f.page.refresh();
 const choose=value=>f.page.choice({currentTarget:{dataset:{index:f.page.data.fields.findIndex(x=>x.path==='bank_account_info.bank_account_type')}},detail:{value}});
 choose('2');assert.ok(!f.page.data.fields.some(x=>x.path==='bank_account_info.account_name'));assert.equal(form.get(f.page.profile,'bank_account_info.account_name'),'HISTORICAL COMPANY');assert.match(f.page.data.materialGroups.find(g=>g.id==='bank').reuseHint,/保留原值/);
 choose('1');assert.ok(f.page.data.fields.some(x=>x.path==='bank_account_info.account_name'));assert.equal(form.get(f.page.profile,'bank_account_info.account_name'),'HISTORICAL COMPANY');
});
test('hidden industry selector preserves FOOD required upload and original category across save/reopen',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 f.page.condition({currentTarget:{dataset:{key:'category'}},detail:{value:1}});
 await f.page.save();assert.equal(f.page.data.options.category,'FOOD');f.app.required_materials.push('industry_permit');
 f.page.data.catalog.push({id:'industry_permit',title:'原行业资质'});f.page.data.step=2;await f.page.load(f.app.application);
 let group=f.page.data.materialGroups.find(g=>g.id==='qualification');assert.ok(group);assert.equal(group.materialWarning,'');assert.equal(group.materials[0].required,true);assert.equal(group.materials[0].connected,true);
 await f.page.upload({currentTarget:{dataset:{kind:'industry_permit'}}});await f.page.load(f.app.application);
 group=f.page.data.materialGroups.find(g=>g.id==='qualification');assert.equal(group.materials[0].uploaded,true);assert.ok(f.calls.some(c=>c.p&&c.p.operation==='upload'&&c.p.params.kind==='industry_permit'));assert.equal(f.page.data.options.category,'FOOD');
 assert.ok(f.calls.filter(c=>c.p&&c.p.operation==='save').every(c=>c.p.params.category==='FOOD'));
 const missing=form.materialGroups({}, {...f.page.data.options,category:'FOOD'},[],2).find(g=>g.id==='qualification');assert.equal(missing.materials[0].connected,false);assert.match(missing.materialWarning,/入口尚未配置/);assert.match(missing.materialWarning,/不能视为免交/);
});
function conflictEvent(page,target){const field=form.reusedFields(page.profile,page.data.options).find(f=>f.targetPath===target);return {currentTarget:{dataset:{target,source:field.sourceValue,previous:form.get(page.profile,target)}}};}
async function conflictFixture(){const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.data.options.scene='both';for(const [path,value] of [['subject_info.business_license_info.merchant_name','SOURCE COMPANY'],['subject_info.business_license_info.license_address','SOURCE ADDRESS'],['subject_info.business_license_info.legal_person','SOURCE PERSON'],['subject_info.identity_info.id_card_info.id_card_name','SOURCE PERSON'],['contact_info.mobile_phone','13800138000'],['contact_info.contact_name','HISTORICAL CONTACT'],['business_info.sales_info.biz_store_info.biz_store_name','HISTORICAL COMPANY'],['business_info.sales_info.biz_store_info.biz_store_address','HISTORICAL ADDRESS'],['business_info.service_phone','555-0100'],['bank_account_info.bank_account_type','BANK_ACCOUNT_TYPE_PERSONAL'],['bank_account_info.account_name','HISTORICAL HOLDER']])form.put(f.page.profile,path,value);await f.page.save();await f.page.load(f.app.application);return f;}
test('all hidden historical conflicts remain unchanged on ordinary load and cancel; explicit adoption changes only local draft until save',async()=>{
 for(const target of ['contact_info.contact_name','business_info.sales_info.biz_store_info.biz_store_name','business_info.sales_info.biz_store_info.biz_store_address','business_info.service_phone','bank_account_info.account_name']){
  const f=await conflictFixture(),old=form.get(f.page.profile,target),event=conflictEvent(f.page,target),before=JSON.stringify(f.page.profile),calls=f.calls.length;
  assert.ok(old.startsWith('HISTORICAL')||old==='555-0100');assert.equal(f.page.reusedFieldLinks[target],undefined);
  f.page.startReuseConfirmation(event);assert.ok(f.page.data.reuseConfirmation);assert.equal(JSON.stringify(f.page.profile),before);f.page.cancelReuse();assert.equal(f.page.data.reuseConfirmation,null);assert.equal(JSON.stringify(f.page.profile),before);assert.equal(f.page.data.dirty,false);
  f.page.startReuseConfirmation(event);f.page.confirmReuse();assert.equal(form.get(f.page.profile,target),event.currentTarget.dataset.source);assert.equal(f.page.data.dirty,true);assert.equal(f.calls.length,calls);assert.equal(form.get(f.storedProfile,target),old);
  await f.page.save();await f.page.load(f.app.application);assert.equal(form.get(f.page.profile,target),event.currentTarget.dataset.source);assert.equal(f.page.reusedFieldLinks[target],event.currentTarget.dataset.source);
 }
});
test('conflict confirmation refuses changed source target application session and read-only or pending states',async()=>{
 for(const mutation of ['source','target','application','session','readonly','pending']){
  const f=await conflictFixture(),target='bank_account_info.account_name',event=conflictEvent(f.page,target),old=form.get(f.page.profile,target);
  f.page.startReuseConfirmation(event);
  if(mutation==='source'){form.put(f.page.profile,'subject_info.identity_info.id_card_info.id_card_name','NEW PERSON');form.put(f.page.profile,'subject_info.business_license_info.legal_person','NEW PERSON');}
  if(mutation==='target')form.put(f.page.profile,target,'NEW TARGET');
  if(mutation==='application')f.page.data.application={...f.page.data.application,application:'other-application'};
  if(mutation==='session')f.page.session={};
  if(mutation==='readonly')f.page.data.canEditWechat=false;
  if(mutation==='pending')f.page.data.pending=true;
  const before=f.calls.length;f.page.confirmReuse();assert.equal(form.get(f.page.profile,target),mutation==='target'?'NEW TARGET':old);assert.equal(f.calls.length,before);
 }
});
test('ambiguous legal sources cannot open a personal-holder replacement and stale displayed conflict cannot start confirmation',async()=>{
 const f=await conflictFixture(),target='bank_account_info.account_name',event=conflictEvent(f.page,target);
 form.put(f.page.profile,'subject_info.business_license_info.legal_person','DIFFERENT PERSON');f.page.startReuseConfirmation(event);assert.equal(f.page.data.reuseConfirmation,null);assert.equal(form.get(f.page.profile,target),'HISTORICAL HOLDER');
 const contact=conflictEvent(f.page,'contact_info.contact_name');form.put(f.page.profile,'contact_info.contact_name','NEW HISTORICAL');f.page.startReuseConfirmation(contact);assert.equal(f.page.data.reuseConfirmation,null);assert.equal(form.get(f.page.profile,'contact_info.contact_name'),'NEW HISTORICAL');
});
test('equal saved source/target values restore value links without inventing OCR confirmation; different values do not',()=>{
 const options={entity:'ENTERPRISE',contact:'LEGAL',doc:form.docs[0],scene:'both'},profile={subject_info:{business_license_info:{merchant_name:'SAME COMPANY',license_address:'SAME ADDRESS',legal_person:'SAME PERSON'},identity_info:{id_card_info:{id_card_name:'SAME PERSON'}}},contact_info:{contact_name:'SAME PERSON',mobile_phone:'13800138000'},business_info:{service_phone:'13800138000',sales_info:{biz_store_info:{biz_store_name:'SAME COMPANY',biz_store_address:'DIFFERENT ADDRESS'}}},bank_account_info:{bank_account_type:'BANK_ACCOUNT_TYPE_PERSONAL',account_name:'DIFFERENT HOLDER'}};
 const links=form.reusedFieldLinks(profile,options);assert.equal(links['contact_info.contact_name'],'SAME PERSON');assert.equal(links['business_info.service_phone'],'13800138000');assert.equal(links['business_info.sales_info.biz_store_info.biz_store_address'],undefined);assert.equal(links['bank_account_info.account_name'],undefined);assert.equal(profile.ocrConfirmed,undefined);
});


test('existing unset donation and explicit zero never inherit the new fifty basis-point default',async()=>{
 for(const choice of [undefined,0]){
  const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
  if(choice===0)Object.assign(f.app,{split_participation:false,requested_split_bps:0});
  await f.page.load(f.app.application);assert.equal(f.page.data.splitInput,'0');assert.equal(f.page.data.splitDefaultPending,false);
  await f.page.save();const saved=f.calls.filter(x=>x.p.operation==='save').at(-1).p.params;
  assert.equal(saved.split_participation,undefined);assert.equal(saved.requested_split_bps,undefined);
 }
});
test('known provider configuration caps edited donation but unknown configuration is not invented',async()=>{
 for(const maximum of [0,40,50,null]){
  const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});Object.assign(f.app,{provider_max_split_bps:maximum,requested_split_bps:0,split_participation:false});await f.page.load(f.app.application);
  f.page.inputSplitPercent({detail:{value:'0.5'}});await f.page.save();
  if(maximum===0||maximum===40){assert.equal(f.calls.filter(x=>x.p.operation==='save').length,0);assert.match(f.page.data.status,/渠道配置上限/);assert.equal(f.page.data.splitSaveUnknown,false);}
  else assert.equal(f.calls.find(x=>x.p.operation==='save').p.params.requested_split_bps,50);
 }
});
test('new default donation unknown save cannot repeat a creation without authoritative readback',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.failNext('save',new Error('UNKNOWN'));await f.page.save();
 assert.equal(f.page.data.splitSaveUnknown,true);const count=f.calls.filter(x=>x.p.operation==='save').length;await f.page.save();assert.equal(f.calls.filter(x=>x.p.operation==='save').length,count);
});
test('personal holder is visible read-only and the approved bank OCR follows account type',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});form.put(f.page.profile,'subject_info.identity_info.id_card_info.id_card_name','SYNTHETIC LEGAL');form.put(f.page.profile,'bank_account_info.bank_account_type','BANK_ACCOUNT_TYPE_PERSONAL');await f.page.save();f.page.setData({step:2});f.page.refresh();
 const bank=f.page.data.materialGroups.find(g=>g.id==='bank');assert.equal(bank.personalAccount,true);assert.equal(bank.personalAccountName,'SYNTHETIC LEGAL');assert.ok(!bank.fields.some(x=>x.path==='bank_account_info.account_name'));
 const w=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.match(w,/class="readonly-account-name" style="color:#83958b">{{group.personalAccountName}}/);assert.match(w,/返回第一步修改户名/);assert.match(w,/item.path==='bank_account_info.bank_account_type'[\s\S]*?class="primary bank-ocr-entry" data-kind="bank_card" bindtap="recognizeDocument" disabled="{{pending\|\|!application\|\|!application.materials.bank_card}}">银行卡识别/);
 const bankEntry=w.match(/<button class="primary bank-ocr-entry"[^>]*>/)[0];assert.match(bankEntry,/bindtap="recognizeDocument"/);assert.doesNotMatch(bankEntry,/chooseMedia|upload/);
});


test('next and back scroll only after rendered step transition; failed save preserves the step and draft',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});let afterRender;const original=f.page.setData;f.page.setData=function(p,done){original.call(this,p);if(done)afterRender=done;};
 await f.page.next();assert.equal(f.page.data.step,1);assert.equal(f.scrolls.length,0);assert.equal(typeof afterRender,'function');afterRender();assert.equal(f.scrolls.at(-1).scrollTop,0);assert.equal(f.scrolls.at(-1).step,1);
 f.page.back();assert.equal(f.page.data.step,0);assert.equal(f.scrolls.length,1);afterRender();assert.equal(f.scrolls.at(-1).step,0);
 const before=JSON.stringify(f.page.profile),count=f.scrolls.length;f.failNext('save',new Error('SAVE_FAILED'));await f.page.next();assert.equal(f.page.data.step,0);assert.equal(JSON.stringify(f.page.profile),before);assert.equal(f.scrolls.length,count);
});
test('targeted material return still waits for render and locates the requested original group',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({step:3});f.page.returnMaterial({currentTarget:{dataset:{step:0,group:'legal'}}});assert.equal(f.page.data.step,0);assert.equal(f.scrolls.at(-1).selector,'#material-legal');
});

test('all three successful next and back transitions request top after render, retaining targeted return',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 for(let step=1;step<=3;step++){await f.page.next();assert.equal(f.page.data.step,step);assert.deepEqual(f.scrolls.at(-1),{scrollTop:0,duration:0,step});}
 for(let step=2;step>=0;step--){f.page.back();assert.equal(f.page.data.step,step);assert.deepEqual(f.scrolls.at(-1),{scrollTop:0,duration:0,step});}
 const w=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.doesNotMatch(w,/只整理微信支付进件所需资料|mode="multiSelector"/);assert.doesNotMatch(w,/wx:if="{{step===0}}"[^>]*>返回第一步完善/);assert.match(w,/返回第一步修改户名/);
});

test('retained license address resolves original code on save and invalidates only its linked automatic code',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});const source='subject_info.business_license_info.license_address',target='business_info.sales_info.biz_store_info.biz_address_code';
 f.page.input({currentTarget:{dataset:{path:source}},detail:{value:'深圳市南山区科技园1号'}});assert.equal(form.get(f.page.profile,target),'440305');await f.page.save();assert.equal(form.get(f.storedProfile,target),'440305');await f.page.load(f.app.application);assert.equal(f.page.data.regionResolved,true);
 f.page.input({currentTarget:{dataset:{path:source}},detail:{value:'南山区'}});assert.equal(form.get(f.page.profile,target),undefined);await f.page.save();assert.equal(form.get(f.storedProfile,target),undefined);
 f.page.input({currentTarget:{dataset:{path:source}},detail:{value:'北京市东城区1号'}});await f.page.save();assert.equal(form.get(f.storedProfile,target),'110101');
});
test('region historical different code stays until explicit confirmation and unconfirmed OCR never supplies address',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});const source='subject_info.business_license_info.license_address',target='business_info.sales_info.biz_store_info.biz_address_code';
 f.page.setData({ocrRows:[{key:'registered_address',value:'深圳市南山区1号'}]});await f.page.save();assert.equal(form.get(f.storedProfile,target),undefined);
 form.put(f.page.profile,source,'深圳市南山区1号');form.put(f.page.profile,target,'110101');f.page.reusedFieldLinks={};await f.page.save();assert.equal(form.get(f.storedProfile,target),'110101');f.page.setData({step:1});f.page.refresh();assert.equal(f.page.data.regionResolved,false);
 const field=form.reusedFields(f.page.profile,f.page.data.options).find(x=>x.targetPath===target);f.page.startReuseConfirmation({currentTarget:{dataset:{target,source:field.sourceValue,previous:field.value}}});f.page.cancelReuse();assert.equal(form.get(f.page.profile,target),'110101');
 f.page.startReuseConfirmation({currentTarget:{dataset:{target,source:field.sourceValue,previous:field.value}}});f.page.confirmReuse();await f.page.save();assert.equal(form.get(f.storedProfile,target),'440305');assert.equal(f.page.data.regionResolved,true);
});

test('original identity back upload starts id_back against national-side material without choosing front',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});await f.page.upload({currentTarget:{dataset:{kind:'identity_back'}}});assert.equal(f.calls.find(c=>c.p&&c.p.operation==='upload').p.params.kind,'identity_back');assert.equal(f.calls.find(c=>c.op==='ocr'&&c.p.action==='submit').p.document_type,'id_back');assert.equal(form.get(f.storedProfile,'subject_info.identity_info.id_card_info.id_card_national'),undefined);assert.equal(f.calls.some(c=>c.p&&c.p.operation==='wechat_media'),false);assert.equal(form.get(f.storedProfile,'subject_info.identity_info.id_card_info.id_card_copy'),undefined);});
test('passport group exposes neither ID front nor ID back OCR controls',()=>{const options={entity:'ENTERPRISE',contact:'LEGAL',doc:'IDENTIFICATION_TYPE_OVERSEA_PASSPORT',scene:'mini',ubos:0};const group=form.materialGroups({},options,[],0).find(g=>g.id==='legal');assert.equal(group.ocrKind,'');assert.equal(group.ocrBackKind,'');});

test('OCR material controls use readable labels without claiming review submission',()=>{const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');for(const text of ['识别营业执照','识别身份证人像面','识别身份证国徽面','查看识别结果','确认已核对','仅填空白，不覆盖已有内容','提交时自动处理'])assert.ok(wxml.includes(text));for(const text of ['未关联微信草稿','关联当前微信资料草稿','识别本组已上传证照','留存人工确认','EXECUTION','REQUEST_IN_PROGRESS','诊断编号','已选用于微信申请（未送审）'])assert.ok(!wxml.includes(text));assert.doesNotMatch(wxml,/bindtap="syncMaterial"|用于微信申请/);assert.match(wxml,/bindtap="confirmAndSaveOcr"/);assert.doesNotMatch(wxml,/bindtap="fillOcrDraft"/);assert.match(wxml,/确认已核对并保存/);});
test('industry change invalidates old rule and activity but preserves original photos and bank data',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.chooseIndustry({detail:{value:'2'}});form.put(f.page.profile,'settlement_info.activities_id','synthetic-old-activity');form.put(f.page.profile,'settlement_info.debit_activities_rate','synthetic-old-rate');form.put(f.page.profile,'bank_account_info.account_number','synthetic-bank');const materials=JSON.stringify(f.app.materials);
 f.page.chooseIndustry({detail:{value:String(f.page.data.industryLabels.length-1)}});assert.equal(form.get(f.page.profile,'settlement_info.settlement_id'),undefined);assert.equal(form.get(f.page.profile,'settlement_info.activities_id'),undefined);assert.equal(form.get(f.page.profile,'bank_account_info.account_number'),'synthetic-bank');assert.equal(JSON.stringify(f.app.materials),materials);
 f.page.inputIndustry({detail:{value:'实际其他经营项目'}});await f.page.save();assert.equal(form.get(f.storedProfile,'settlement_info.qualification_type'),'实际其他经营项目');assert.equal(form.get(f.storedProfile,'settlement_info.settlement_id'),undefined);assert.equal(f.page.data.industryCustom,true);
 assert.throws(()=>form.assertReviewComplete(f.page.data.reviewGroups,f.page.data.application,{wechat:true}),/经营行业/);
});
test('subject changes never retain the previous subject settlement rule or silently choose a new one',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.chooseIndustry({detail:{value:'2'}});assert.equal(form.get(f.page.profile,'settlement_info.settlement_id'),'716');f.page.condition({currentTarget:{dataset:{key:'entity'}},detail:{value:'1'}});assert.equal(form.get(f.page.profile,'settlement_info.settlement_id'),undefined);assert.equal(form.get(f.page.profile,'settlement_info.qualification_type'),'零售');f.page.chooseIndustry({detail:{value:'2'}});assert.equal(form.get(f.page.profile,'settlement_info.settlement_id'),'719');
});
test('read-only and pending industry changes cannot alter saved choice or identifiers',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.chooseIndustry({detail:{value:'2'}});const prior=JSON.stringify(f.page.profile);for(const patch of [{pending:true},{pending:false,canEditWechat:false}]){f.page.setData(patch);f.page.chooseIndustry({detail:{value:String(f.page.data.industryLabels.length-1)}});f.page.inputIndustry({detail:{value:'late response'}});assert.equal(JSON.stringify(f.page.profile),prior);}
});
test('reselecting other industry preserves entered actual industry and draft',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.chooseIndustry({detail:{value:String(f.page.data.industryLabels.length-1)}});f.page.inputIndustry({detail:{value:'真实自填行业'}});const before=JSON.stringify(f.page.profile);f.page.chooseIndustry({detail:{value:String(f.page.data.industryLabels.length-1)}});assert.equal(JSON.stringify(f.page.profile),before);});
test('platform subject edit does not mutate a read-only WeChat profile',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.chooseIndustry({detail:{value:'2'}});const before=JSON.stringify(f.page.profile);f.page.setData({canEditPlatform:true,canEditWechat:false});f.page.condition({currentTarget:{dataset:{key:'entity'}},detail:{value:'1'}});assert.equal(JSON.stringify(f.page.profile),before);assert.match(f.page.data.status,/只读.*保留/);});

test('submit feedback is adjacent and remains visible for pending and failures',async()=>{
 const markup=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');
 assert.match(markup,/class="status-notice submit-feedback"[^>]*aria-live="assertive"><text>{{status\|\|\(pending\?'正在处理，请稍候。':''\)}}<\/text><\/view><button class="primary" bindtap="submitAllReview"/);
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 let finish;const wait=new Promise(resolve=>finish=resolve);
 const pending=f.page.run(async()=>{await wait;const error=Error('请填写联系人手机号');error.submitPreflight=true;throw error;},'提交审核');
 assert.equal(f.page.data.pending,true);assert.equal(f.page.data.status,'提交审核处理中，请稍候。');finish();await pending;
 assert.equal(f.page.data.pending,false);assert.equal(f.page.data.status,'提交审核未完成：请填写联系人手机号');
});


test('upload and each Next save privately without sending materials or applications to WeChat',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});
 await f.page.confirmOcr();
 for(let step=0;step<3;step++){f.page.setData({step});await f.page.next();assert.equal(f.page.data.step,step+1);}
 assert.equal(f.calls.some(c=>c.p&&['wechat_media','wechat_cashier_link','wechat_qualifications_select','wechat_execute','wechat_submit_review','submit'].includes(c.p.operation)),false);
 assert.ok(f.page.data.application.materials.business_license);
});
test('final Submit associates eligible original before single applicant backend submission',async()=>{
 const f=fixture('merchant-join',{customerError:e=>e.stack||e.message});await f.page.onLoad({scene:'shop1'});
 await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});
 form.put(f.page.profile,'contact_info.mobile_phone','13800000000');form.put(f.page.profile,'business_info.sales_info.mini_program_info.mini_program_appid','wx'+'1'.repeat(16));await f.page.save();
 // Isolate page orchestration with a minimal complete review model; form validation has its own tests.
 const refresh=f.page.refresh.bind(f.page);f.page.refresh=function(...args){refresh(...args);this.data.reviewGroups=[{id:'license',step:0,title:'营业执照',items:[{path:'material:business_license',label:'营业执照',material:true,uploaded:true,wechatRequired:true,synced:!!form.get(this.profile,'subject_info.business_license_info.license_copy')}]}];};f.page.refresh();
 const begin=f.calls.length;await f.page.submitAllReview();const ops=f.calls.slice(begin).map(c=>c.p&&c.p.operation);
 assert.equal(ops.filter(x=>x==='wechat_media').length,1);
 assert.equal(ops.filter(x=>x==='submit').length,0);assert.equal(ops.filter(x=>x==='wechat_apply').length,1);assert.ok(ops.indexOf('wechat_media')<ops.indexOf('wechat_apply'),JSON.stringify({ops,status:f.page.data.status}));
 assert.equal(form.get(f.storedProfile,'subject_info.business_license_info.license_copy'),'synthetic-admitted-media');
 assert.match(f.page.data.status,/提交成功，请等待微信审核/);assert.match(f.page.data.status,/已取得微信真实受理/);
 const second=f.calls.length;await f.page.submitAllReview();assert.equal(f.calls.slice(second).some(c=>['wechat_media','submit','wechat_submit_review','wechat_apply'].includes(c.p.operation)),false);
});
test('missing item navigation preserves draft and routes to its original field or material without requests',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});form.put(f.page.profile,'contact_info.mobile_phone','13800000000');f.page.data.dirty=true;
 for(const issue of [{path:'contact_info.mobile_phone',group:'contact',step:0,message:'请核对手机号'},{path:'material:identity_front',group:'legal',step:0,message:'请上传身份证人像面'}]){
 f.page.setData({step:3,submitIssues:[issue]});const before=JSON.stringify(f.page.profile),count=f.calls.length;
 f.page.goToSubmitIssue({currentTarget:{dataset:{index:0}}});assert.equal(f.page.data.step,issue.step);assert.equal(f.page.data.missingFieldPath,issue.path);assert.equal(f.page.data.status,issue.message);assert.equal(JSON.stringify(f.page.profile),before);assert.equal(f.page.data.dirty,true);assert.equal(f.calls.length,count);assert.match(f.scrolls.at(-1).selector,/^#(?:missing-field-|material-)/);
 }
});

test('final Submit gathers missing items before external work and keeps uploaded originals and entered fields',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});
 form.put(f.page.profile,'contact_info.mobile_phone','13800000000');f.page.data.dirty=true;
 const profile=JSON.stringify(f.page.profile),materials=JSON.stringify(f.page.data.application.materials),before=f.calls.length;
 await f.page.submitAllReview();assert.ok(f.page.data.submitIssues.length>1);assert.equal(f.calls.length,before);assert.equal(JSON.stringify(f.page.profile),profile);assert.equal(JSON.stringify(f.page.data.application.materials),materials);assert.equal(f.page.data.dirty,true);assert.doesNotMatch(f.page.data.status,/提交成功/);
 for(const issue of f.page.data.submitIssues){assert.ok(issue.path);assert.ok(issue.group);assert.ok(Number.isInteger(issue.step));}
});

test('confirmed OCR is saved by Next and survives reread without external submission',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});
 const path='subject_info.business_license_info.merchant_name';await f.page.confirmOcr();await f.page.next();
 assert.equal(form.get(f.storedProfile,path),'Fixture Company');assert.equal(f.page.data.step,1);
 await f.page.load(f.app.application);assert.equal(form.get(f.page.profile,path),'Fixture Company');
 assert.equal(f.calls.some(c=>c.p&&['wechat_media','wechat_apply','wechat_execute'].includes(c.p.operation)),false);
});
test('Next saves unconfirmed OCR edits privately and advances without confirming',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});
 const path='subject_info.business_license_info.merchant_name';f.page.inputUnifiedField({currentTarget:{dataset:{path}},detail:{value:'HUMAN CORRECTED COMPANY'}});
 await f.page.next();assert.equal(f.page.data.step,1);assert.equal(form.get(f.storedProfile,path),undefined);assert.match(f.page.data.status,/草稿已保存/);
 assert.equal(f.page.ocrDrafts.business_license.fields.company_name,'HUMAN CORRECTED COMPANY');
 f.page.ocrCapture=null;f.page.ocrHeldCaptures={};f.page.ocrDisplayCaptures={};f.page.data.ocrRows=[];
 await f.page.load(f.app.application);f.page.setData({step:0});f.page.refresh();
 const field=f.page.data.materialGroups.flatMap(g=>g.fields).find(x=>x.path===path);
 assert.equal(field.value,'HUMAN CORRECTED COMPANY');assert.equal(field.ocrSuggestion,true);
 assert.equal(f.calls.some(c=>c.op==='ocr'&&['confirm','recover_confirm','recover_apply'].includes(c.p.action)),false);
 assert.equal(f.calls.some(c=>c.p&&['wechat_media','wechat_apply'].includes(c.p.operation)),false);
});

test('runtime AppID is never silently inserted for any merchant scene',async()=>{
 for(const scene of ['unknown','store','mini','both']){
  const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
  f.page.platformAppid='wx1d5f8873eaea5392';f.page.setData({options:{...f.page.data.options,scene},dirty:true});
  await f.page.save();
  assert.equal(form.get(f.storedProfile,'business_info.sales_info.mini_program_info.mini_program_appid'),undefined);
  assert.equal(form.get(f.storedProfile,'business_info.sales_info.mini_program_info.mini_program_sub_appid'),undefined);
  assert.equal(f.page.data.options.scene,scene);
  assert.equal(f.calls.some(c=>c.p&&['wechat_media','wechat_apply'].includes(c.p.operation)),false);
 }
});
test('existing merchant-supplied AppIDs and original store data survive save and reload',async()=>{
 for(const key of ['mini_program_appid','mini_program_sub_appid']){
  const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
  f.page.platformAppid='wx1d5f8873eaea5392';f.page.setData({options:{...f.page.data.options,scene:'store'},dirty:true});
  const path='business_info.sales_info.mini_program_info.'+key;
  form.put(f.page.profile,path,'wx2222222222222222');
  form.put(f.page.profile,'business_info.sales_info.biz_store_info.biz_store_address','Synthetic original address');
  await f.page.save();await f.page.load(f.app.application);
  assert.equal(form.get(f.page.profile,path),'wx2222222222222222');
  assert.equal(form.get(f.page.profile,'business_info.sales_info.biz_store_info.biz_store_address'),'Synthetic original address');
  assert.equal(f.page.data.options.scene,'store');
 }
});
test('AppID field remains editable rather than promising automatic runtime reuse',()=>{
 const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');
 assert.equal(wxml.includes('无需商家手填 AppID'),false);
 assert.equal(wxml.includes('wx:elif="{{item.path===\'business_info.sales_info.mini_program_info.mini_program_appid\'}}"'),false);
 assert.ok(wxml.includes('bindinput="inputUnifiedField"'));
});

test('live mini declaration is explicit, persists through original save/read, and does not submit',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 f.page.setData({options:{...f.page.data.options,scene:'mini'}});
 form.put(f.page.profile,'business_info.sales_info.mini_program_info.mini_program_appid','wx2222222222222222');
 assert.equal(f.page.data.options.miniLive,false);
 f.page.chooseMiniLive({detail:{value:['live']}});assert.equal(f.page.data.options.miniLive,true);
 await f.page.save();await f.page.load(f.app.application);
 assert.equal(f.page.data.options.miniLive,true);
 assert.equal(f.calls.filter(c=>c.p&&c.p.operation==='wechat_save').at(-1).p.params.mini_program_live,true);
 assert.equal(f.calls.some(c=>c.p&&['wechat_apply','wechat_media','submit'].includes(c.p.operation)),false);
});
test('live mini cannot silently borrow runtime AppID and changing declared ID clears live fact',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.platformAppid='wx1d5f8873eaea5392';
 f.page.chooseMiniLive({detail:{value:['live']}});assert.equal(f.page.data.options.miniLive,false);assert.match(f.page.data.status,/有权/);
 const path='business_info.sales_info.mini_program_info.mini_program_appid';form.put(f.page.profile,path,'wx2222222222222222');
 f.page.chooseMiniLive({detail:{value:['live']}});assert.equal(f.page.data.options.miniLive,true);
 f.page.input({currentTarget:{dataset:{path}},detail:{value:'wx3333333333333333'}});
 assert.equal(f.page.data.options.miniLive,false);await f.page.save();
 assert.equal(f.calls.filter(c=>c.p&&c.p.operation==='wechat_save').at(-1).p.params.mini_program_live,false);
});
test('live mini screenshot is optional while unknown/unlaunched stays required and uploaded originals remain reusable',()=>{
 const profile={business_info:{sales_info:{mini_program_info:{mini_program_appid:'wx2222222222222222'},sales_scenes_type:['SALES_SCENES_MINI_PROGRAM']}}};
 const options={entity:'ENTERPRISE',contact:'LEGAL',doc:'IDENTIFICATION_TYPE_IDCARD',scene:'mini',ubos:0,category:'GENERAL'};
 for(const live of [false,true]){
  const groups=form.reviewRequirements(profile,{...options,miniLive:live},[],{});
  const item=groups.flatMap(g=>g.items).find(i=>i.path==='material:mini_program_screenshot');
  assert.equal(item.wechatRequired,!live);assert.equal(item.complete,live);
 }
 const materials=[{id:'mini_program_screenshot',title:'截图',uploaded:true,synced:false}];
 const item=form.reviewRequirements(profile,{...options,miniLive:true},materials,{}).flatMap(g=>g.items).find(i=>i.path==='material:mini_program_screenshot');
 assert.equal(item.autoWechat,true);assert.equal(item.uploaded,true);
 const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.match(wxml,/服务页面截图：选填/);assert.match(wxml,/未上线时必填/);assert.match(wxml,/group.id==='mini'/);
});
test('service and merchant AppIDs have distinct editable fields with one combined required choice',()=>{
 const options={entity:'ENTERPRISE',contact:'LEGAL',doc:'IDENTIFICATION_TYPE_IDCARD',scene:'mini',ubos:0,category:'GENERAL',miniLive:true};
 for(const key of ['mini_program_appid','mini_program_sub_appid']){
  const profile={business_info:{sales_info:{mini_program_info:{[key]:'wx2222222222222222'}}}};
  const fields=form.rows(profile,options,1).filter(f=>/mini_program_(?:sub_)?appid$/.test(f.path));
  assert.equal(fields.length,2);assert.ok(fields.every(f=>f.required===false));
  const item=form.reviewRequirements(profile,options,[],{}).flatMap(g=>g.items).filter(i=>i.path==='mini_appid');
  assert.equal(item.length,1);assert.equal(item[0].complete,true);
 }
 const item=form.reviewRequirements({},options,[],{}).flatMap(g=>g.items).find(i=>i.path==='mini_appid');assert.equal(item.complete,false);
});
