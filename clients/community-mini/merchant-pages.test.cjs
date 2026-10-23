const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const form=require('./merchant-form');const auth=require('./customer-auth');
function fixture(name){let definition,calls=[],pending=null,failure=null,storedProfile={};const app={application:'ma_'+ '1'.repeat(32),revision:1,status:'DRAFT',fields:{store_name:'Fixture Shop',address:'Fixture Address'},entity_type:'ENTERPRISE',delegated:false,identity_type:'IDENTIFICATION_TYPE_IDCARD',sales_scenes_type:['SALES_SCENES_MINI_PROGRAM'],required_materials:['business_license'],materials:{},wechat_submerchant_state:'NOT_VERIFIED',opening_state:'NOT_APPROVED'};
const session={clear(){},login:async()=>{},async merchant(scene,op,p){calls.push({scene,op,p:structuredClone(p)});if(failure&&failure.operation===p.operation){const e=failure.error;failure=null;throw e;}if(pending)return pending;
 if(op==='workspaces')return {workspaces:['merchant']};if(op==='read')return p.operation==='community.orders'?{orders:[]}:{counts:{},order_total_minor:0};
 if(p.operation==='mine')return {applications:[]};if(p.operation==='catalog')return {materials:[{id:'business_license',title:'营业执照'}]};if(p.operation==='read'||p.operation==='save')return structuredClone(app);if(p.operation==='wechat_read')return {version:1,profile:structuredClone(storedProfile)};if(p.operation==='wechat_save'){storedProfile=structuredClone(p.params.profile);return {version:2,profile:structuredClone(storedProfile)};}throw Error('unplanned');}};
vm.runInNewContext(fs.readFileSync(__dirname+'/pages/'+name+'/index.js','utf8'),{Page:p=>definition=p,wx:{navigateTo(){}},getApp:()=>({globalData:{baseUrl:'https://fixture.invalid'}}),require:p=>p==='../../session'?{parseScene:()=> 'shop1',createSession:()=>session,customerError:()=> 'error'}:p==='../../customer-auth'?auth:p==='../../merchant-form'?form:require(p),encodeURIComponent});
const page={...definition,data:structuredClone(definition.data),setData(p){Object.assign(this.data,p);}};return {page,calls,app,hold(p){pending=p;},failNext(operation,error){failure={operation,error};},get storedProfile(){return storedProfile;}};}
test('new admission defaults to LEGAL and places business-license fields and upload on the first screen',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 assert.equal(f.page.data.options.contact,'LEGAL');
 assert.ok(f.page.data.fields.some(x=>x.path==='subject_info.business_license_info.merchant_name'));
 assert.ok(f.page.data.fields.some(x=>x.path==='contact_info.mobile_phone'));
 assert.ok(f.page.data.fields.some(x=>x.path==='contact_info.contact_email'));
 assert.ok(f.page.data.licenseMaterial);
 assert.match(fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8'),/营业执照资料/);
});
test('native home/recommendations/profile tabs and entry navigation stay in the same five-page app',()=>{
 const app=JSON.parse(fs.readFileSync(__dirname+'/app.json','utf8'));
 assert.equal(app.tabBar,undefined);
 const home=fs.readFileSync(__dirname+'/pages/home/index.wxml','utf8');
 const checkout=fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8');
 const profile=fs.readFileSync(__dirname+'/pages/profile/index.wxml','utf8');
 for(const label of ['查看门店介绍','浏览推荐店铺','商家入驻与进度','商家工作台'])assert.ok(home.includes(label),label);
 assert.ok(checkout.includes('推荐店铺')&&checkout.includes('示例门店 A')&&checkout.includes('返回推荐店铺'));
 const join=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');assert.ok(join.includes('index===fieldCursor')&&join.includes('下一项资料'));
 for(const label of ['商家入驻与进度','商家工作台','门店与订单'])assert.ok(profile.includes(label),label);
});
test('dirty admission draft requires explicit save-or-stay before navigation',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 f.page.baseInput({currentTarget:{dataset:{key:'store_name'}},detail:{value:'Unsaved Shop'}});
 f.page.navigateSection({currentTarget:{dataset:{section:'orders'}}});
 assert.equal(f.page.data.leavePrompt,true);assert.equal(f.page.data.leaveTarget,'orders');assert.equal(f.page.data.dirty,true);
 assert.equal(f.page.data.base.store_name,'Unsaved Shop');
 f.page.cancelLeave();assert.equal(f.page.data.leavePrompt,false);assert.equal(f.page.data.dirty,true);
 assert.equal(f.calls.some(c=>c.p.operation==='save'),false);
});
test('merchant entry is in existing display and same app routes, no second appid',()=>{const pages=JSON.parse(fs.readFileSync(__dirname+'/app.json')).pages;for(const p of ['merchant','merchant-join'])assert.ok(pages.includes('pages/'+p+'/index'));assert.match(fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8'),/bindtap="openMerchantJoin"/);});
test('join four stages save one shared profile and refresh original application',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});form.put(f.page.profile,'subject_info.business_license_info.merchant_name','Fixture Company');form.put(f.page.profile,'contact_info.mobile_phone','13800000000');await f.page.next();assert.equal(f.page.data.step,1);const save=f.calls.find(c=>c.p.operation==='save');assert.equal(save.p.params.fields.legal_name,'Fixture Company');assert.equal(save.p.params.fields.contact,'13800000000');const provider=f.calls.find(c=>c.p.operation==='wechat_save');assert.equal(provider.p.params.application,f.app.application);f.page.back();assert.equal(f.page.data.step,0);assert.ok(f.calls.some(c=>c.p.operation==='read'));assert.ok(!f.calls.some(c=>['wechat_execute','wechat_query'].includes(c.p.operation)));});
test('conditional document and delegated fields and single UBO editor',()=>{const o={entity:'SOLE_PROPRIETOR',contact:'LEGAL',doc:'IDENTIFICATION_TYPE_IDCARD',scene:'mini',ubos:0};const rows=form.rows({},o,0);assert.ok(rows.every(r=>!r.path.includes('.id_doc_info.')&&!r.path.includes('ubo_info_list')));assert.ok(form.rows({},o,1).every(r=>!r.path.includes('contact_id_number')));const changed=form.rows({}, {...o,entity:'ENTERPRISE',doc:'IDENTIFICATION_TYPE_OVERSEA_PASSPORT',ubos:2,uboIndex:1},0);assert.ok(changed.some(r=>r.path.includes('.ubo_info_list.1.')));assert.ok(changed.every(r=>!r.path.includes('.ubo_info_list.0.')));assert.ok(changed.every(r=>!r.path.includes('.id_card_info.')));});
test('merchant clears scene-bound private state when the active scene changes',()=>{
 const script=fs.readFileSync(__dirname+'/pages/merchant/index.js','utf8');
 assert.match(script,/onShow\(\)\{const activeScene=getApp\(\)\.globalData\.scene/);
 assert.match(script,/current\(\)\{return !this\.dead&&!this\.sceneStale&&auth\.active\(this\.epoch\);\}/);
 assert.match(script,/workspaces:\[\],workspace:'',orders:\[\],summary:null,detail:null,settings:null/);
});
test('admission save keeps the current material cursor and sync is not mislabeled as WeChat submission',()=>{
 const script=fs.readFileSync(__dirname+'/pages/merchant-join/index.js','utf8');
 assert.match(script,/const savedPosition=\{step:this\.data\.step,fieldCursor:this\.data\.fieldCursor,cursorPath:this\.data\.cursorPath,materialCursor:this\.data\.materialCursor\}/);
 assert.match(script,/this\.setData\(savedPosition\);this\.refresh\(\)/);
 assert.ok(script.includes('尚未提交微信'));
 const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');
 assert.ok(wxml.includes('原申请已上传'));assert.ok(wxml.includes('待关联微信草稿'));assert.ok(wxml.includes('已关联微信草稿'));
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
 f.page.setData({step:1,cursorPath:'',fieldCursor:0,options:{...f.page.data.options,contact:'SUPER'}});f.page.refresh();
 assert.deepEqual(Array.from(f.page.data.adjacentMaterials,m=>m.id),['operator_identity','operator_identity_back']);
 const index=f.page.data.fields.findIndex(x=>x.path==='contact_info.contact_id_doc_type');
 f.page.choice({currentTarget:{dataset:{index}},detail:{value:1}});
 assert.deepEqual(Array.from(f.page.data.adjacentMaterials,m=>m.id),['operator_identity']);
 assert.equal(f.page.materialProfilePath('operator_identity'),'contact_info.contact_id_doc_copy');
});
test('saved SUPER administrator remains SUPER when reopening its original application',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 f.page.setData({options:{...f.page.data.options,contact:'SUPER'}});await f.page.save();
 assert.equal(f.page.data.options.contact,'SUPER');
 assert.equal(f.page.data.application.application,f.app.application);
 assert.equal(form.get(f.page.profile,'contact_info.contact_type'),'SUPER');
});

test('selection immediately reveals document uploads above editable text with OCR explicitly unavailable',async()=>{
 const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});
 const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');
 const license=wxml.indexOf('营业执照资料'),adjacent=wxml.indexOf('本组证件材料'),field=wxml.indexOf('第{{fieldCursor+1}}项');
 assert.ok(license>=0&&adjacent>license&&field>adjacent,'upload cards precede editable fields');
 assert.match(wxml,/识别：未接通/);
 assert.equal(f.page.data.showLicenseUpload,true);
 f.page.setData({options:{...f.page.data.options,entity:'SOLE_PROPRIETOR'}});f.page.refresh();
 assert.equal(f.page.data.showLicenseUpload,true);
 const catalog=[...f.page.data.catalog,...['identity_front','identity_back','operator_identity','operator_identity_back'].map(id=>({id,title:id}))];
 f.page.setData({catalog});f.page.refresh();
 assert.deepEqual(Array.from(f.page.data.adjacentMaterials,m=>m.id),['identity_front','identity_back']);
 f.page.setData({options:{...f.page.data.options,doc:'IDENTIFICATION_TYPE_OVERSEA_PASSPORT'}});f.page.refresh();
 assert.deepEqual(Array.from(f.page.data.adjacentMaterials,m=>m.id),['identity_front']);
 f.page.setData({step:1,options:{...f.page.data.options,contact:'SUPER'}});f.page.refresh();
 assert.deepEqual(Array.from(f.page.data.adjacentMaterials,m=>m.id),['operator_identity','operator_identity_back']);
 assert.equal(f.calls.some(c=>c.p.operation==='wechat_execute'),false);
});
