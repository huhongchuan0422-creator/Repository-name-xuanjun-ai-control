const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const form=require('./merchant-form');const auth=require('./customer-auth');
function fixture(name){let definition,calls=[],pending=null,failure=null,storedProfile={};const app={application:'ma_'+ '1'.repeat(32),revision:1,status:'DRAFT',fields:{store_name:'Fixture Shop',address:'Fixture Address'},entity_type:'ENTERPRISE',delegated:false,identity_type:'IDENTIFICATION_TYPE_IDCARD',sales_scenes_type:['SALES_SCENES_MINI_PROGRAM'],required_materials:['business_license'],materials:{},wechat_submerchant_state:'NOT_VERIFIED',opening_state:'NOT_APPROVED'};
const session={clear(){},login:async()=>{},async merchant(scene,op,p){calls.push({scene,op,p:structuredClone(p)});if(failure&&failure.operation===p.operation){const e=failure.error;failure=null;throw e;}if(pending)return pending;
 if(op==='workspaces')return {workspaces:['merchant']};if(op==='read')return p.operation==='community.orders'?{orders:[]}:{counts:{},order_total_minor:0};
 if(p.operation==='mine')return {applications:[]};if(p.operation==='catalog')return {materials:[{id:'business_license',title:'营业执照'}]};if(p.operation==='read'||p.operation==='save')return structuredClone(app);if(p.operation==='wechat_read')return {version:1,profile:structuredClone(storedProfile)};if(p.operation==='wechat_save'){storedProfile=structuredClone(p.params.profile);return {version:2,profile:structuredClone(storedProfile)};}throw Error('unplanned');}};
vm.runInNewContext(fs.readFileSync(__dirname+'/pages/'+name+'/index.js','utf8'),{Page:p=>definition=p,wx:{navigateTo(){}},getApp:()=>({globalData:{baseUrl:'https://fixture.invalid'}}),require:p=>p==='../../session'?{parseScene:()=> 'shop1',createSession:()=>session,customerError:()=> 'error'}:p==='../../customer-auth'?auth:p==='../../merchant-form'?form:require(p),encodeURIComponent});
const page={...definition,data:structuredClone(definition.data),setData(p){Object.assign(this.data,p);}};return {page,calls,app,hold(p){pending=p;},failNext(operation,error){failure={operation,error};},get storedProfile(){return storedProfile;}};}
test('merchant entry is in existing display and same app routes, no second appid',()=>{const pages=JSON.parse(fs.readFileSync(__dirname+'/app.json')).pages;for(const p of ['merchant','merchant-join'])assert.ok(pages.includes('pages/'+p+'/index'));assert.match(fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8'),/bindtap="openMerchantJoin"/);});
test('join four stages save one shared profile and refresh original application',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});form.put(f.page.profile,'subject_info.business_license_info.merchant_name','Fixture Company');form.put(f.page.profile,'contact_info.mobile_phone','13800000000');await f.page.next();assert.equal(f.page.data.step,1);const save=f.calls.find(c=>c.p.operation==='save');assert.equal(save.p.params.fields.legal_name,'Fixture Company');assert.equal(save.p.params.fields.contact,'13800000000');const provider=f.calls.find(c=>c.p.operation==='wechat_save');assert.equal(provider.p.params.application,f.app.application);f.page.back();assert.equal(f.page.data.step,0);assert.ok(f.calls.some(c=>c.p.operation==='read'));assert.ok(!f.calls.some(c=>['wechat_execute','wechat_query'].includes(c.p.operation)));});
test('conditional document and delegated fields and single UBO editor',()=>{const o={entity:'SOLE_PROPRIETOR',contact:'LEGAL',doc:'IDENTIFICATION_TYPE_IDCARD',scene:'mini',ubos:0};const rows=form.rows({},o,0);assert.ok(rows.every(r=>!r.path.includes('.id_doc_info.')&&!r.path.includes('ubo_info_list')));assert.ok(form.rows({},o,1).every(r=>!r.path.includes('contact_id_number')));const changed=form.rows({}, {...o,entity:'ENTERPRISE',doc:'IDENTIFICATION_TYPE_OVERSEA_PASSPORT',ubos:2,uboIndex:1},0);assert.ok(changed.some(r=>r.path.includes('.ubo_info_list.1.')));assert.ok(changed.every(r=>!r.path.includes('.ubo_info_list.0.')));assert.ok(changed.every(r=>!r.path.includes('.id_card_info.')));});
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
test('merchant mobile rejects malformed values locally, preserves legacy overlength and clears errors on correction',()=>{
 const f=fixture('merchant-join');f.page.profile={contact_info:{mobile_phone:'123456789012345678901'}};
 f.page.setData({step:1});f.page.refresh();
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
  f.page.setData({options:{...f.page.data.options,contact},step:1});f.page.refresh();
  assert.equal(f.page.data.fields.filter(x=>x.path===path).length,1);
  assert.ok(f.page.data.fields.some(x=>x.path==='contact_info.contact_name'));
  assert.ok(f.page.data.fields.some(x=>x.path==='contact_info.contact_email'));
  f.page.setData({step:0});f.page.refresh();f.page.setData({step:1});f.page.refresh();
  assert.equal(form.get(f.page.profile,path),'0012345678');
 }
 const wxml=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');
 assert.match(wxml,/type="text"[^>]*data-path="{{item.path}}"/);
 assert.match(wxml,/maxlength="{{item.path==='contact_info.mobile_phone'?item.maxlength:512}}"/);
 assert.match(wxml,/bindblur="blur"/);
 assert.match(wxml,/5–20位，可含数字、+或-，不含空格/);
 assert.equal(form.get(f.page.profile,'business_info.service_phone'),undefined);assert.equal(form.get(f.page.profile,'contact_info.mobile_phone'),'0012345678');
});
test('approved platform application can continue original WeChat draft without resubmitting platform',async()=>{const f=fixture('merchant-join');await f.page.onLoad({scene:'shop1'});f.app.status='APPROVED';await f.page.select({currentTarget:{dataset:{application:f.app.application}}});f.calls.length=0;form.put(f.page.profile,'contact_info.mobile_phone','13800000000');await f.page.save();assert.ok(!f.calls.some(c=>c.p.operation==='save'));assert.ok(f.calls.some(c=>c.p.operation==='wechat_save'));});
