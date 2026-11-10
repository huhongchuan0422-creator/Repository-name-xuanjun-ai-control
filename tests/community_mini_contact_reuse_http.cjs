// Native merchant controller, original HTTP/SQLite services, synthetic data only.
const fs=require('node:fs'),vm=require('node:vm'),http=require('node:http'),assert=require('node:assert/strict'),path=require('node:path');
const root=process.cwd()+'/clients/community-mini',session=require(root+'/session'),auth=require(root+'/customer-auth'),form=require(root+'/merchant-form');
const app={globalData:{baseUrl:process.env.COMMUNITY_TEST_ORIGIN}},trace=[];let login=0;
const wx={login(o){o.success({code:'contact-reuse-'+(++login)});},request(o){trace.push({operation:o.data.operation,child:o.data.params&&o.data.params.operation});const raw=JSON.stringify(o.data),req=http.request(o.url,{method:o.method,headers:{...o.header,'Content-Length':Buffer.byteLength(raw)}},res=>{let body='';res.on('data',v=>body+=v);res.on('end',()=>o.success({statusCode:res.statusCode,data:JSON.parse(body)}));});req.on('error',e=>o.fail({errMsg:e.message}));req.end(raw);}};
function page(){let definition;vm.runInNewContext(fs.readFileSync(root+'/pages/merchant-join/index.js','utf8'),{Page:p=>definition=p,wx,getApp:()=>app,require:p=>p==='../../session'?session:p==='../../customer-auth'?auth:p==='../../merchant-form'?form:require(path.resolve(root+'/pages/merchant-join',p)),encodeURIComponent});return {...definition,data:structuredClone(definition.data),setData(p){Object.assign(this.data,p);}};}
(async()=>{
 let p=page();await p.onLoad({scene:'shop1'});assert.equal(p.data.ready,true,p.data.status);
 const edit=(field,value)=>p.input({currentTarget:{dataset:{path:field}},detail:{value}});
 const choose=(key,value)=>p.condition({currentTarget:{dataset:{key}},detail:{value}});
 const get=field=>form.get(p.profile,field);
 choose('entity',1);assert.equal(p.data.options.entity,'SOLE_PROPRIETOR');
 choose('scene',3);choose('ubos',1);
 edit('subject_info.business_license_info.merchant_name','SYNTHETIC COMPANY ONE');
 edit('subject_info.business_license_info.license_address','SYNTHETIC STREET ONE');
 edit('subject_info.business_license_info.legal_person','SYNTHETIC LEGAL');
 edit('subject_info.identity_info.id_card_info.id_card_name','SYNTHETIC LEGAL');
 edit('contact_info.mobile_phone','13800138000');edit('business_info.merchant_shortname','SYNTHETIC SHORT');
 await p.save();assert.equal(p.data.dirty,false,p.data.status);const id=p.data.application.application;
 assert.equal(get('contact_info.contact_name'),'SYNTHETIC LEGAL');assert.equal(get('business_info.sales_info.biz_store_info.biz_store_name'),'SYNTHETIC COMPANY ONE');assert.equal(get('business_info.sales_info.biz_store_info.biz_store_address'),'SYNTHETIC STREET ONE');assert.equal(get('business_info.service_phone'),'13800138000');
 p.onUnload();p=page();await p.onLoad({scene:'shop1'});assert.equal(p.data.application.application,id);
 edit('subject_info.business_license_info.merchant_name','SYNTHETIC COMPANY TWO');edit('subject_info.business_license_info.license_address','SYNTHETIC STREET TWO');edit('contact_info.mobile_phone','13800138001');await p.save();
 assert.equal(get('business_info.sales_info.biz_store_info.biz_store_name'),'SYNTHETIC COMPANY TWO');assert.equal(get('business_info.sales_info.biz_store_info.biz_store_address'),'SYNTHETIC STREET TWO');assert.equal(get('business_info.service_phone'),'13800138001');
 choose('contact',1);edit('contact_info.contact_name','INDEPENDENT OPERATOR');edit('contact_info.mobile_phone','13800138002');p.setData({step:2});p.refresh();
 const account=p.data.fields.findIndex(f=>f.path==='bank_account_info.bank_account_type');const personal=p.data.fields[account].choices.indexOf('BANK_ACCOUNT_TYPE_PERSONAL');assert.ok(personal>0);p.choice({currentTarget:{dataset:{index:account}},detail:{value:String(personal)}});await p.save();
 assert.equal(get('contact_info.contact_name'),'INDEPENDENT OPERATOR');assert.equal(get('business_info.service_phone'),'13800138002');assert.equal(get('bank_account_info.account_name'),'SYNTHETIC LEGAL');assert.equal(get('bank_account_info.bank_account_type'),'BANK_ACCOUNT_TYPE_PERSONAL');assert.ok(!p.data.fields.some(f=>f.path==='bank_account_info.account_name'));
 form.put(p.profile,'business_info.sales_info.biz_store_info.biz_store_name','HISTORICAL NAME');form.put(p.profile,'business_info.sales_info.biz_store_info.biz_store_address','HISTORICAL ADDRESS');form.put(p.profile,'business_info.service_phone','555-0100');form.put(p.profile,'bank_account_info.account_name','HISTORICAL HOLDER');p.setData({dirty:true});await p.save();p.onUnload();p=page();await p.onLoad({scene:'shop1'});
 edit('subject_info.business_license_info.merchant_name','SYNTHETIC COMPANY THREE');edit('subject_info.business_license_info.license_address','SYNTHETIC STREET THREE');edit('contact_info.mobile_phone','13800138003');await p.save();
 assert.equal(get('business_info.sales_info.biz_store_info.biz_store_name'),'HISTORICAL NAME');assert.equal(get('business_info.sales_info.biz_store_info.biz_store_address'),'HISTORICAL ADDRESS');assert.equal(get('business_info.service_phone'),'555-0100');assert.equal(get('bank_account_info.account_name'),'HISTORICAL HOLDER');assert.equal(get('contact_info.contact_name'),'INDEPENDENT OPERATOR');
 p.setData({step:1});p.refresh();assert.equal(p.data.materialGroups.filter(g=>g.reuseHint).length,1);assert.match(p.data.materialGroups.find(g=>g.id==='store').reuseHint,/保留原值/);
 edit('contact_info.mobile_phone','1380013800312345678901');await p.save();await p.load(id);assert.equal(get('contact_info.mobile_phone'),'1380013800312345678901');const before=trace.length;await p.submitAllReview();assert.equal(trace.length,before);assert.match(p.data.mobilePhoneError,/11位/);
 assert.equal(login,1);p.onUnload();process.stdout.write(JSON.stringify({application:id,original_http:true,legal_super:true,private_holder_legal_only:true,saved_reopened:true,linked_source_updates:true,historical_conflicts_preserved:true,overlength_preserved:true,formal_submissions:0}));
})().catch(e=>{console.error(e);process.exitCode=1;});
