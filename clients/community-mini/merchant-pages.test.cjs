const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const form=require('./merchant-form');const auth=require('./customer-auth');
function fixture(name,options={}){let definition,calls=[],pending=null,failure=null,storedProfile={},cashierMediaId='',ocrStatus='needs_review',ocrConfirmedFields=null,ocrConfirmationRevision=0;const app={application:'ma_'+ '1'.repeat(32),revision:1,status:'DRAFT',fields:{store_name:'Fixture Shop',address:'Fixture Address'},entity_type:'ENTERPRISE',delegated:false,identity_type:'IDENTIFICATION_TYPE_IDCARD',sales_scenes_type:['SALES_SCENES_MINI_PROGRAM'],required_materials:['business_license'],materials:{},wechat_submerchant_state:'NOT_VERIFIED',opening_state:'NOT_APPROVED'};
const session={clear(){},login:async()=>{},async merchant(scene,op,p){if(options.beforeOperation)await options.beforeOperation(op,p);calls.push({scene,op,p:structuredClone(p)});if(failure&&failure.operation===p.operation){const e=failure.error;failure=null;throw e;}if(pending)return pending;
 if(op==='ocr'){if(p.action==='submit')return {result:{job_id:'synthetic-ocr'}};if(p.action==='read')return {result:{job_id:p.job_id,application_revision:String(app.revision),provider_version:1,status:ocrStatus,document_type:'business_license',...(ocrStatus==='confirmed'?{confirmed_fields:structuredClone(ocrConfirmedFields),confirmation_revision:ocrConfirmationRevision}:{fields:{company_name:{value:'Fixture Company'},registered_address:{value:'OCR Address'}}})}};if(p.action==='confirm'){ocrStatus='confirmed';ocrConfirmedFields=structuredClone(p.fields);ocrConfirmationRevision=p.revision;return {result:{job_id:p.job_id,status:'confirmed',revision:p.revision,recorded:true,application_revision:p.application_revision,provider_version:p.provider_version}};}}
 if(op==='workspaces')return {workspaces:['merchant']};if(op==='read')return p.operation==='community.orders'?{orders:[]}:{counts:{},order_total_minor:0};
 if(p.operation==='mine')return {applications:options.duplicateApplications?[structuredClone(app),{...structuredClone(app),application:'ma_'+ '2'.repeat(32),status:'APPROVED'}]:[]};if(p.operation==='catalog')return {materials:[{id:'business_license',title:'营业执照'}]};if(p.operation==='save'){if(p.params.declarations)app.declarations=structuredClone(p.params.declarations);if(p.params.sales_scenes_type)app.sales_scenes_type=structuredClone(p.params.sales_scenes_type);app.entity_type=p.params.entity_type;app.delegated=p.params.delegated;app.identity_type=p.params.identity_type;return structuredClone(app);}if(p.operation==='read'){if(p.params.application!==app.application)return {...structuredClone(app),application:p.params.application,status:'APPROVED'};return structuredClone(app);}if(p.operation==='upload'){app.materials[p.params.kind]={uploaded:true,review:'PENDING'};app.revision++;cashierMediaId='';return structuredClone(app);}if(p.operation==='remove_material'){delete app.materials.cashier_photo;app.revision++;cashierMediaId='';return structuredClone(app);}if(p.operation==='wechat_media')return {media_id:'synthetic-admitted-media'};if(p.operation==='wechat_cashier_link'){cashierMediaId=p.params.media_id;return {version:2};}if(p.operation==='wechat_read')return {version:1,profile:structuredClone(storedProfile),cashier_media_id:cashierMediaId};if(p.operation==='wechat_save'){storedProfile=structuredClone(p.params.profile);return {version:2,profile:structuredClone(storedProfile)};}throw Error('unplanned');}};
 vm.runInNewContext(fs.readFileSync(__dirname+'/pages/'+name+'/index.js','utf8'),{Page:p=>definition=p,wx:{navigateTo(o){calls.push({navigation:o.url});if(o.success)o.success();if(o.complete)o.complete();},redirectTo(o){calls.push({navigation:o.url});if(o.success)o.success();if(o.complete)o.complete();},chooseMedia(o){if(options.chooseMedia)return options.chooseMedia(o);calls.push({p:{operation:'media_choice'},mediaChoice:{sourceType:o.sourceType,mediaType:o.mediaType,sizeType:o.sizeType}});o.success({tempFiles:[{tempFilePath:'synthetic-cashier.png',size:options.largeMedia?6000000:32}]});},compressImage(o){if(options.compressImage)return options.compressImage(o);calls.push({compress:{src:o.src,quality:o.quality}});o.success({tempFilePath:'synthetic-compressed.png'});},getFileSystemManager(){return {stat(o){o.success({stats:{size:options.largeMedia&&o.path==='synthetic-cashier.png'?6000000:17}});},readFile(o){calls.push({p:{operation:'read_file'},readFile:o.filePath});o.success({data:options.largeMedia&&o.filePath==='synthetic-cashier.png'?'A'.repeat(6666672):'iVBORw0KGgpzeW50aGV0aWM='});}}}},getApp:()=>({globalData:{baseUrl:'https://fixture.invalid'}}),require:p=>{if(p.endsWith('.json'))throw Error('WECHAT_JSON_MODULE_UNAVAILABLE');return p==='../../session'?{parseScene:()=> 'shop1',getSharedSession:()=>({...session,ensureLogin:session.login,isAuthenticated:()=>false}),customerError:()=> 'error'}:p==='../../customer-auth'?auth:p==='../../merchant-form'?form:p==='../../merchant-submit'?require('./merchant-submit'):p==='../../merchant-official-fields'?require('./merchant-official-fields'):p==='../../merchant-platform-reference-data'?require('./merchant-platform-reference-data'):require(p);},encodeURIComponent});
const page={...definition,data:structuredClone(definition.data),setData(p){Object.assign(this.data,p);}};return {page,calls,app,hold(p){pending=p;},failNext(operation,error){failure={operation,error};},get storedProfile(){return storedProfile;}};}
test('new admission defaults to LEGAL and places business-license fields and upload on the first screen',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 assert.equal(f.page.data.options.contact,'LEGAL');
 assert.ok(f.page.data.fields.some(x=>x.path==='subject_info.business_license_info.merchant_name'));
 assert.ok(f.page.data.fields.some(x=>x.path==='contact_info.mobile_phone'));
 assert.ok(f.page.data.fields.some(x=>x.path==='contact_info.contact_email'));
 assert.ok(f.page.data.licenseMaterial);
 const markup=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.equal(f.page.data.materialGroups[0].id,'license');assert.match(markup,/识别本组已上传证照/);assert.match(markup,/尚未请求识别/);assert.equal(markup.includes('当前尚无真实OCR接口'),false);assert.equal(markup.includes('OCR未接通'),false);
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
 for(const percent of [10,20,25,30])assert.ok(markup.includes('application&&application.redemption_percent==='+percent));
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
 assert.ok(wxml.includes('原申请已上传'));assert.ok(wxml.includes('未关联微信草稿'));assert.ok(wxml.includes('已关联微信草稿'));
});
test('merchant uses original summary/orders and hides late data after unload',async()=>{const f=fixture('merchant');await f.page.onLoad({scene:'shop1'});await f.page.open({currentTarget:{dataset:{view:'orders'}}});assert.equal(f.calls.at(-1).p.operation,'community.orders');let done;f.hold(new Promise(r=>done=r));const loading=f.page.open({currentTarget:{dataset:{view:'summary'}}});f.page.onUnload();done({order_total_minor:999});await loading;assert.equal(f.page.data.summary,null);});
test('revocation clears private application, fields and material metadata',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});await f.page.select({currentTarget:{dataset:{application:f.app.application}}});f.page.customerSessionRevoked();assert.equal(f.page.data.application,null);assert.equal(f.page.data.fields.length,0);assert.equal(f.page.data.materials.length,0);assert.equal(Object.keys(f.page.profile).length,0);});

test('merchant admin mobile keeps exact string, provider mapping and service phone separation',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({step:1,options:{...f.page.data.options,contact:'LEGAL'}});f.page.refresh();
 const path='contact_info.mobile_phone';
 for(const value of ['12345','0012345678','+44-123456789']){
  f.page.input({currentTarget:{dataset:{path}},detail:{value}});
  assert.equal(form.get(f.page.profile,path),value);assert.equal(typeof form.get(f.page.profile,path),'string');
  assert.equal(f.page.data.mobilePhoneError,'');
 }
 assert.equal(form.platformFields(f.page.profile,f.page.data.base).contact,'+44-123456789');
 form.put(f.page.profile,'business_info.service_phone','555-0100');assert.equal(form.get(f.page.profile,'business_info.service_phone'),'555-0100');assert.equal(form.get(f.page.profile,path),'+44-123456789');
 await f.page.save();
 assert.equal(form.get(f.storedProfile,path),'+44-123456789');
 assert.equal(typeof form.get(f.storedProfile,path),'string');
 assert.equal(f.calls.find(c=>c.p.operation==='wechat_save').p.params.profile.contact_info.mobile_phone,'+44-123456789');
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
 assert.equal(f.page.data.fields.find(x=>x.path==='contact_info.mobile_phone').maxlength,21);
 assert.notEqual(f.page.data.mobilePhoneError,'');
 for(const value of ['1234','abcde','123 45','12345\n','１２３４５']){
  f.page.input({currentTarget:{dataset:{path:'contact_info.mobile_phone'}},detail:{value}});
  assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),value);
  assert.notEqual(f.page.data.mobilePhoneError,'',JSON.stringify(value));
 }
 f.page.input({currentTarget:{dataset:{path:'contact_info.mobile_phone'}},detail:{value:'0012345678'}});
 assert.equal(f.page.data.mobilePhoneError,'');
 assert.equal(f.page.data.fields.find(x=>x.path==='contact_info.mobile_phone').maxlength,20);
 f.page.input({currentTarget:{dataset:{path:'contact_info.mobile_phone'}},detail:{value:'12345678901234567890'}});
 assert.equal(f.page.data.mobilePhoneError,'');
 assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),'12345678901234567890');
});
test('empty mobile is an empty string after save and reread, no stale fallback',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({step:1});
 f.page.input({currentTarget:{dataset:{path:'contact_info.mobile_phone'}},detail:{value:'0012345678'}});
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
 const path='contact_info.mobile_phone';f.page.input({currentTarget:{dataset:{path}},detail:{value:'0012345678'}});
 for(const contact of ['LEGAL','SUPER']){
  f.page.setData({options:{...f.page.data.options,contact},step:0});f.page.refresh();
  assert.equal(f.page.data.fields.filter(x=>x.path===path).length,1);
  assert.ok(f.page.data.fields.some(x=>x.path==='contact_info.contact_name'));
  assert.ok(f.page.data.fields.some(x=>x.path==='contact_info.contact_email'));
  f.page.setData({step:0});f.page.refresh();f.page.setData({step:1});f.page.refresh();
  assert.equal(form.get(f.page.profile,path),'0012345678');
 }
 const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');
 assert.ok(wxml.includes('type="text"'),'mobile phone field must use text input');assert.ok(wxml.includes('data-path="{{item.path}}"'),'mobile phone field must bind the exact field path');
 assert.ok(wxml.includes("maxlength=\"{{item.path===\'contact_info.mobile_phone\'?item.maxlength:512}}\""),'mobile_phone input must use the exact path-specific maxlength ternary');
 assert.ok(wxml.includes('bindblur="blur"'),'mobile phone field must bind blur validation');
 assert.ok(wxml.includes('5–20位，可含数字、+或-，不含空格'),'complete mobile format hint must be present verbatim');
 assert.equal(form.get(f.page.profile,'business_info.service_phone'),undefined);assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),'0012345678');
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

test('scene photos appear beside chosen actual store scene and not in mini-only scene',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.equal(wxml.includes('bindinput="baseInput"'),false);f.page.setData({step:1,options:{...f.page.data.options,scene:'both'},catalog:[...f.page.data.catalog,...['storefront_photo','interior_photo','mini_program_screenshot'].map(id=>({id,title:id}))]});f.page.refresh();const groups=f.page.data.materialGroups;assert.equal(groups[0].id,'scene');assert.ok(groups.find(g=>g.id==='store').fields.some(x=>x.path.endsWith('biz_store_address')));assert.deepEqual(Array.from(f.page.data.scenePhotoCards,x=>x.connected),[true,true,false]);assert.equal(f.page.materialProfilePath('storefront_photo'),'business_info.sales_info.biz_store_info.store_entrance_pic');assert.equal(f.page.materialProfilePath('interior_photo'),'business_info.sales_info.biz_store_info.indoor_pic');assert.equal(f.page.materialProfilePath('mini_program_screenshot'),'business_info.sales_info.mini_program_info.mini_program_pics');f.page.setData({options:{...f.page.data.options,scene:'mini'}});f.page.refresh();assert.equal(f.page.data.scenePhotoCards.length,0);assert.equal(f.page.data.materialGroups.some(g=>g.id==='store'),false);});

test('UBO passport hides only current beneficiaries back material',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({catalog:[...f.page.data.catalog,...['ubo_1_front','ubo_1_back','ubo_2_front','ubo_2_back'].map(id=>({id,title:id}))],options:{...f.page.data.options,entity:'ENTERPRISE',ubos:2,uboIndex:0}});form.put(f.page.profile,'subject_info.ubo_info_list.0.ubo_id_doc_type','IDENTIFICATION_TYPE_OVERSEA_PASSPORT');form.put(f.page.profile,'subject_info.ubo_info_list.1.ubo_id_doc_type','IDENTIFICATION_TYPE_IDCARD');f.page.refresh();assert.deepEqual(Array.from(f.page.data.adjacentMaterials,x=>x.id),['ubo_1_front']);f.page.setData({options:{...f.page.data.options,uboIndex:1}});f.page.refresh();assert.deepEqual(Array.from(f.page.data.adjacentMaterials,x=>x.id),['ubo_2_front','ubo_2_back']);});
test('selection immediately reveals document uploads above editable text and requires explicit OCR and human checking',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.ok(wxml.indexOf('wx:for="{{group.materials}}"')<wxml.indexOf('wx:for="{{group.fields}}"'));assert.ok(wxml.indexOf('识别本组已上传证照')<wxml.indexOf('wx:for="{{group.fields}}"'));assert.match(wxml,/识别结果需人工核对/);f.page.setData({options:{...f.page.data.options,entity:'SOLE_PROPRIETOR',contact:'SUPER'},catalog:[...f.page.data.catalog,...['identity_front','identity_back','operator_identity','operator_identity_back'].map(id=>({id,title:id}))]});f.page.refresh();assert.equal(f.page.data.materialGroups[0].id,'license');assert.ok(f.page.data.materialGroups.find(g=>g.id==='legal'));assert.ok(f.page.data.materialGroups.find(g=>g.id==='operator'));assert.equal(f.page.data.materialGroups.filter(g=>g.id==='contact').length,1);f.page.selectDocumentType({currentTarget:{dataset:{path:'subject_info.identity_info.id_doc_type'}},detail:{value:1}});assert.deepEqual(Array.from(f.page.data.materialGroups.find(g=>g.id==='legal').materials,m=>m.id),['identity_front']);assert.equal(f.calls.some(c=>/ocr|wechat_execute/.test(c.p.operation)),false);});

test('merchant material upload previews, links the WeChat draft and automatically starts bound OCR',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});const choice=f.calls.find(c=>c.mediaChoice);assert.deepEqual(Array.from(choice.mediaChoice.sourceType),['album','camera']);assert.deepEqual(Array.from(choice.mediaChoice.mediaType),['image']);assert.equal(f.calls.find(c=>c.readFile).readFile,'synthetic-cashier.png');assert.equal(f.calls.find(c=>c.p&&c.p.operation==='upload').p.params.kind,'business_license');assert.equal(f.page.data.materialPreviews.business_license,'synthetic-cashier.png');assert.equal(form.get(f.storedProfile,'subject_info.business_license_info.license_copy'),'synthetic-admitted-media');assert.equal(f.page.data.materialGroups[0].materials[0].synced,true);const ocr=f.calls.filter(c=>c.op==='ocr');assert.deepEqual(Array.from(ocr,c=>c.p.action),['submit','read']);assert.equal(ocr[0].p.document_type,'business_license');assert.equal(f.page.data.ocrKind,'business_license');assert.match(f.page.data.ocrStatus,/识别建议/);assert.equal(f.page.data.ocrRows[0].value,'Fixture Company');const script=fs.readFileSync(__dirname+'/pages/merchant-join/index.js','utf8'),markup=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.doesNotMatch(script,/chooseMessageFile/);assert.match(markup,/materialPreviews\[item\.id\]/);assert.match(markup,/拍照 \/ 从相册选择/);});

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

 test('cashier native uploads auto-links, replaces, removes and rereads the same original application without OCR',async()=>{const f=fixture('merchant-join');f.app.sales_scenes_type.push('SALES_SCENES_STORE');await f.page.onLoad({scene:'shop1'});await f.page.load(f.app.application);f.page.setData({step:1,options:{...f.page.data.options,scene:'both'},catalog:[...f.page.data.catalog,{id:'cashier_photo',title:'收银台照'}]});f.page.refresh();let card=f.page.data.scenePhotoCards.find(c=>c.id==='cashier_photo');assert.equal(card.connected,true);assert.equal(card.required,false);const ev={currentTarget:{dataset:{kind:'cashier_photo'}}};await f.page.upload(ev);card=f.page.data.scenePhotoCards.find(c=>c.id==='cashier_photo');assert.equal(card.uploaded,true);assert.equal(card.synced,true);await f.page.upload(ev);assert.equal(f.calls.filter(c=>c.p.operation==='upload').length,2);await f.page.syncMaterial(ev);assert.equal(f.page.data.scenePhotoCards.find(c=>c.id==='cashier_photo').synced,true);assert.equal(f.calls.find(c=>c.p.operation==='wechat_cashier_link').p.params.application,f.app.application);await f.page.removeCashierPhoto();assert.equal(f.page.data.scenePhotoCards.find(c=>c.id==='cashier_photo').uploaded,false);const removal=f.calls.find(c=>c.p.operation==='remove_material');assert.equal(removal.p.params.kind,'cashier_photo');assert.equal(removal.p.params.application,f.app.application);assert.equal(f.calls.some(c=>/ocr|wechat_execute/.test(c.p.operation)),false);});
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
test('original FOOD material rule and optional supplements are reachable without new mandatory documents',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({step:2,catalog:[...f.page.data.catalog,...['industry_permit','settlement_proof','operator_authorization'].map(id=>({id,title:id}))]});f.page.refresh();assert.equal(f.page.data.materialGroups.find(g=>g.id==='qualification').materials.length,0);f.page.condition({currentTarget:{dataset:{key:'category'}},detail:{value:1}});assert.equal(f.page.data.options.category,'FOOD');assert.equal(f.page.data.materialGroups.find(g=>g.id==='qualification').materials[0].id,'industry_permit');assert.equal(f.page.data.materialGroups.some(g=>g.id==='optional'),false);const historical=form.materialGroups(f.page.profile,f.page.data.options,[{id:'settlement_proof',uploaded:true,required:false}],2).find(g=>g.id==='optional');assert.equal(historical.optional,true);assert.ok(historical.materials.every(m=>!m.required));assert.equal(f.page.data.showOptionalMaterials,false);f.page.toggleOptional();assert.equal(f.page.data.showOptionalMaterials,true);await f.page.save();assert.equal(f.calls.find(c=>c.p.operation==='save').p.params.category,'FOOD');});

test('bank account choices display Chinese while retaining original submitted enum',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.page.setData({step:2});f.page.refresh();const bank=f.page.data.materialGroups.find(g=>g.id==='bank').fields.find(x=>x.path==='bank_account_info.bank_account_type');assert.equal(bank.label,'账户类型');assert.deepEqual(bank.choices,['BANK_ACCOUNT_TYPE_CORPORATE']);assert.deepEqual(bank.choiceLabels,['对公银行账户']);assert.equal(bank.choiceLabel,'请选择');f.page.choice({currentTarget:{dataset:{index:bank.index}},detail:{value:'0'}});assert.equal(form.get(f.page.profile,bank.path),'BANK_ACCOUNT_TYPE_CORPORATE');assert.equal(f.page.data.materialGroups.find(g=>g.id==='bank').fields.find(x=>x.path===bank.path).choiceLabel,'对公银行账户');});
test('material-group return waits for render completion before exact scroll',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});let completion;const original=f.page.setData;f.page.setData=function(p,afterRender){original.call(this,p);if(afterRender)completion=afterRender;};f.page.setData({step:3});f.page.refresh();f.page.returnMaterial({currentTarget:{dataset:{step:0,group:'legal'}}});assert.equal(typeof completion,'function');assert.equal(f.page.data.step,0);assert.ok(f.page.data.materialGroups.find(g=>g.id==='legal'));completion();});
test('original status meanings and recommendation header are display-only',()=>{const f=fixture('merchant-join');assert.equal(f.page.data.stateLabels.DRAFT,'草稿未提交');assert.equal(f.page.data.stateLabels.NOT_VERIFIED,'尚未核验');assert.equal(f.page.data.stateLabels.NOT_APPROVED,'尚未开通');assert.equal(f.page.data.stateLabels.APPROVED,'平台审核通过');const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.match(wxml,/stateLabels\[platformState\]/);assert.match(wxml,/class="progress-state"/);assert.match(fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8'),/recommendations-page/);assert.match(fs.readFileSync(__dirname+'/pages/checkout/index.wxss','utf8'),/background:#f5f8f7/);});
test('confirmed UI shows field values before editing and collapses without clearing actual draft',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 const group=f.page.data.materialGroups.find(x=>x.fields.length);assert.ok(group);
 form.put(f.page.profile,'contact_info.mobile_phone','13800138000');
 assert.equal(f.page.data.editMaterialGroup,'');
 f.page.toggleMaterialEdit({currentTarget:{dataset:{group:group.id}}});assert.equal(f.page.data.editMaterialGroup,group.id);
 f.page.toggleMaterialEdit({currentTarget:{dataset:{group:group.id}}});assert.equal(f.page.data.editMaterialGroup,'');
 assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),'13800138000');
 f.page.setData({canEditWechat:false});f.page.toggleMaterialEdit({currentTarget:{dataset:{group:group.id}}});assert.equal(f.page.data.editMaterialGroup,'');
 const markup=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.match(markup,/confirmed-field-list/);assert.match(markup,/bindinput="input"/);
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
test('industry selection explicitly maps confirmed subject and retains original values for unmapped choice',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});assert.equal(form.get(f.page.profile,'settlement_info.settlement_id'),undefined);f.page.chooseIndustry({detail:{value:'2'}});assert.equal(form.get(f.page.profile,'settlement_info.settlement_id'),'716');assert.equal(form.get(f.page.profile,'settlement_info.qualification_type'),'零售');assert.match(f.page.data.industryHint,/0.6%/);f.page.chooseIndustry({detail:{value:'4'}});assert.equal(form.get(f.page.profile,'settlement_info.qualification_type'),'零售');f.page.setData({canEditWechat:false});f.page.chooseIndustry({detail:{value:'1'}});assert.equal(form.get(f.page.profile,'settlement_info.qualification_type'),'零售');});
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
for(const change of ['scene','session','application'])test('media synchronization stops OCR after '+change+' changes during await',async()=>{let release,reached;const entered=new Promise(r=>reached=r),wait=new Promise(r=>release=r);const options={beforeOperation:async(op,p)=>{if(p.operation==='wechat_media'){reached();await wait;}}};const f=fixture('merchant-join',options);await f.page.onLoad({scene:'shop1'});const uploading=f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});await entered;if(change==='scene')f.page.scene='other-shop';if(change==='session')f.page.session={};if(change==='application')f.page.data.application={...f.app,application:'ma_other'};release();await uploading;assert.equal(f.calls.filter(c=>c.p&&c.p.operation==='upload').length,1);assert.equal(f.calls.some(c=>c.op==='ocr'),false);});
test('uncertain upload does not auto-retry or start OCR and asks to read original application',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});await f.page.load(f.app.application);const begin=f.calls.length;f.failNext('upload',Object.assign(Error('timeout'),{networkKind:'TIMEOUT'}));await f.page.upload({currentTarget:{dataset:{kind:'business_license'}}});const calls=f.calls.slice(begin);assert.equal(calls.filter(x=>x.p&&x.p.operation==='upload').length,1);assert.equal(calls.filter(x=>x.op==='ocr').length,0);assert.match(f.page.data.status,/请先重新读取原申请，勿重复提交/);});
