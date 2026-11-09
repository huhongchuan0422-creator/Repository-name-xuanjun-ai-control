// Actual native controllers + actual session transport to the original Python HTTP services.
const fs=require('node:fs'),vm=require('node:vm'),http=require('node:http'),assert=require('node:assert/strict');
const root=process.cwd()+'/clients/community-mini',session=require(root+'/session'),auth=require(root+'/customer-auth'),form=require(root+'/merchant-form');
let code=0;const base=process.env.COMMUNITY_TEST_ORIGIN;
const app={globalData:{baseUrl:base}},trace=[];let lastCredential;
const image=Buffer.from('\x89PNG\r\n\x1a\nSynthetic test document','binary');
const responseErrors=[];const navigations=[];const wx={chooseMedia(o){assert.equal(o.mediaType.join(','),'image');o.success({tempFiles:[{tempFilePath:'isolated-fixture.png',size:image.length}]});},getFileSystemManager(){return {stat(o){assert.equal(o.path,'isolated-fixture.png');o.success({stats:{size:image.length}});},readFile(o){assert.equal(o.filePath,'isolated-fixture.png');o.success({data:image.toString('base64')});}}},login(o){o.success({code:'controller-code-'+(++code)});},request(o){trace.push({path:new URL(o.url).pathname,operation:o.data.operation,child:o.data.params?.operation,scene:o.header['X-Community-Scene']||''});lastCredential=o.header['X-Community-Session']||lastCredential;const u=new URL(o.url),raw=JSON.stringify(o.data);const req=http.request(u,{method:o.method,headers:{...o.header,'Content-Length':Buffer.byteLength(raw)}},res=>{let body='';res.on('data',v=>body+=v);res.on('end',()=>{try{const data=JSON.parse(body);if(res.statusCode>=400)responseErrors.push({operation:o.data.operation,child:o.data.params?.operation,error:data.error});o.success({statusCode:res.statusCode,data});}catch(e){o.fail({errMsg:'invalid reply'});}});});req.on('error',()=>o.fail({errMsg:'transport unknown'}));req.end(raw);},navigateTo(o){navigations.push(o.url);o.success?.();o.complete?.();},redirectTo(o){navigations.push(o.url);o.success?.();o.complete?.();}};
function page(name){let definition;vm.runInNewContext(fs.readFileSync(root+'/pages/'+name+'/index.js','utf8'),{Page:p=>definition=p,wx,getApp:()=>app,require:p=>p==='../../session'?session:p==='../../customer-auth'?auth:p==='../../merchant-form'?form:(p.startsWith('.')?require(require('node:path').resolve(root+'/pages/'+name,p)):require(p)),encodeURIComponent});return {...definition,data:structuredClone(definition.data),setData(p){Object.assign(this.data,p);}};}
(async()=>{
 if(process.env.COMMUNITY_TEST_SCENELESS==='true'){
  const join=page('merchant-join');await join.onLoad({});
  // Owner R2: restore actual identity silently, never infer merchant authorization.
  assert.equal(join.data.ready,true,join.data.status);assert.equal(join.data.authenticated,true);
  assert.equal(code,1);assert.equal(join.scene,'');assert.equal(join.data.application,null);
  assert.deepEqual(trace.map(r=>[r.path,r.child||null,r.scene]),[
   ['/mini/login',null,''],['/mini/merchant','catalog',''],['/mini/merchant','mine','']]);
  const reopened=page('merchant-join');await reopened.onLoad({});
  assert.equal(reopened.data.ready,true);assert.equal(reopened.session,join.session);
  assert.equal(code,1,'same App reentry reuses verified identity');reopened.onUnload();
  // Upload first, before any manual business fields. Original blank draft must be retained.
  await join.upload({currentTarget:{dataset:{kind:'business_license'}}});assert.ok(join.data.application,join.data.status);assert.ok(join.data.application.materials.business_license,join.data.status);const application=join.data.application.application;assert.equal(join.session.isAuthenticated(),true);assert.equal(trace.some(x=>x.child==='wechat_media'),false,'upload before final submit must not send provider media');assert.ok(responseErrors.some(x=>x.operation==='ocr'&&x.error==='OCR_UNAVAILABLE'));assert.equal(join.data.ocrJob,'');assert.match(join.data.status,/照片已保存到原申请/);assert.doesNotMatch(join.data.status,/照片上传失败/);
  form.put(join.profile,'business_info.merchant_shortname','HTTP Native Store');form.put(join.profile,'subject_info.business_license_info.license_address','HTTP Native Address');form.put(join.profile,'subject_info.business_license_info.merchant_name','HTTP Native Company');form.put(join.profile,'contact_info.mobile_phone','13800000000');await join.save();assert.equal(join.data.application.application,application);assert.equal(join.data.application.fields.legal_name,'HTTP Native Company');
  assert.equal(join.data.options.scene,'unknown');assert.equal(join.data.options.ubos,'unknown');join.condition({currentTarget:{dataset:{key:'ubos'}},detail:{value:1}});await join.next();assert.equal(join.data.step,1);join.condition({currentTarget:{dataset:{key:'scene'}},detail:{value:2}});await join.save();assert.deepEqual(join.data.application.declarations,{scene:'mini',ubos:0});
  for(const kind of join.data.application.required_materials)if(!join.data.application.materials[kind])await join.upload({currentTarget:{dataset:{kind}}});
  for(let i=2;i<=3;i++){await join.next();assert.equal(join.data.step,i,join.data.status);assert.equal(join.data.application.application,application);}
  await join.submit();assert.equal(join.data.platformState,'SUBMITTED',join.data.status);await join.refreshApplication();assert.equal(join.data.application.status,'SUBMITTED');assert.equal(join.data.application.application,application);
  // Bypass native whitelist only inside test to verify actual HTTP server authority.
  // All requests are read-only; this does not grant project/merchant access.
  const denied=async(scene,operation,params)=>new Promise((resolve,reject)=>wx.request({
   url:base+'/mini/merchant',method:'POST',header:{'content-type':'application/json',
    'X-Community-Session':lastCredential,...(scene?{'X-Community-Scene':scene}:{})},
   data:{operation,params},success:r=>{try{assert.equal(r.statusCode,403);assert.equal(r.data.error,'ACCESS_DENIED');resolve();}catch(e){reject(e);}},fail:reject}));
  await denied('','workspaces',{});
  await denied('','read',{workspace:'merchant',operation:'community.orders',params:{}});
  await denied('shop1','read',{workspace:'merchant',operation:'community.orders',params:{}});
  await denied('unknown','onboarding',{operation:'mine',params:{}});
  // Refusals did not create grants; own submitted application is still readable.
  await join.refreshApplication();assert.equal(join.data.application.status,'SUBMITTED');
  assert.equal(code,1);assert.equal(join.data.application.application,application);
  join.navigateSection({currentTarget:{dataset:{section:'profile'}}});assert.equal(navigations.at(-1),'/pages/profile/index');join.onUnload();
  process.stdout.write(JSON.stringify({application,registration:'ORIGINAL_PROVIDER_VERIFIED_ACCOUNT',scene:null,upload_before_fields:true,four_steps:true,silent_identity_only:true,reentry_identity_reused:true,authority_denials:4,status:'SUBMITTED',payment_enabled:false}));return;
 }
 const join=page('merchant-join');await join.onLoad({scene:'shop1'});assert.equal(join.data.pending,false);assert.equal(join.data.applications.length,0);form.put(join.profile,'business_info.merchant_shortname','HTTP Native Store');form.put(join.profile,'subject_info.business_license_info.license_address','HTTP Native Address');form.put(join.profile,'subject_info.business_license_info.merchant_name','HTTP Native Company');form.put(join.profile,'contact_info.mobile_phone','13800000000');await join.next();assert.equal(join.data.step,1,join.data.status);assert.equal(join.data.application.fields.legal_name,'HTTP Native Company');assert.equal(join.data.application.fields.contact,'13800000000');assert.equal(join.data.application.split_participation,true);assert.equal(join.data.application.requested_split_bps,50);assert.equal(join.data.application.redemption_percent,10);
 if(process.env.COMMUNITY_TEST_REUSE==='true'){
 // Reused fields must persist through the same real controller/HTTP record.
 join.condition({currentTarget:{dataset:{key:'scene'}},detail:{value:1}});await join.save();
 assert.equal(form.get(join.profile,'business_info.sales_info.biz_store_info.biz_store_name'),'HTTP Native Company');
 assert.equal(form.get(join.profile,'business_info.sales_info.biz_store_info.biz_store_address'),'HTTP Native Address');
 assert.equal(form.get(join.profile,'business_info.service_phone'),'13800000000');
 form.put(join.profile,'subject_info.business_license_info.merchant_name','HTTP Updated Company');form.put(join.profile,'subject_info.business_license_info.license_address','HTTP Updated Address');form.put(join.profile,'contact_info.mobile_phone','13900000000');await join.save();await join.refreshApplication();
 assert.equal(form.get(join.profile,'business_info.sales_info.biz_store_info.biz_store_name'),'HTTP Updated Company');
 assert.equal(form.get(join.profile,'business_info.sales_info.biz_store_info.biz_store_address'),'HTTP Updated Address');
 assert.equal(form.get(join.profile,'business_info.service_phone'),'13900000000');
 form.put(join.profile,'business_info.sales_info.biz_store_info.biz_store_address','Historical separate store address');await join.save();await join.refreshApplication();
 form.put(join.profile,'subject_info.business_license_info.license_address','HTTP Native Address');form.put(join.profile,'subject_info.business_license_info.merchant_name','HTTP Native Company');form.put(join.profile,'contact_info.mobile_phone','13800000000');
 form.put(join.profile,'subject_info.identity_info.id_card_info.id_card_name','Synthetic Legal');form.put(join.profile,'subject_info.business_license_info.legal_person','Synthetic Legal');form.put(join.profile,'bank_account_info.bank_account_type','BANK_ACCOUNT_TYPE_PERSONAL');await join.save();await join.refreshApplication();
 assert.equal(form.get(join.profile,'business_info.sales_info.biz_store_info.biz_store_address'),'Historical separate store address','a historical different value is not replaced');
 assert.equal(form.get(join.profile,'business_info.sales_info.biz_store_info.biz_store_name'),'HTTP Native Company');
 assert.equal(form.get(join.profile,'business_info.service_phone'),'13800000000');
 assert.equal(form.get(join.profile,'bank_account_info.account_name'),'Synthetic Legal');
 assert.equal(form.get(join.profile,'contact_info.contact_name'),'Synthetic Legal');
 // This is an incomplete synthetic draft, not provider eligibility or submission proof.
 }else{
 // Actual controller -> original HTTP -> encrypted original record, not the HTML adapter.
 join.inputSplitPercent({detail:{value:'2.75'}});await join.save();assert.equal(join.data.application.split_participation,true);assert.equal(join.data.application.requested_split_bps,275);assert.equal(join.data.requestedSplitLabel,'2.75%');
 await join.refreshApplication();assert.equal(join.data.splitInput,'2.75');await join.save();assert.equal(join.data.application.requested_split_bps,275,'untouched original ratio must survive');
 join.inputSplitPercent({detail:{value:'0'}});await join.save();assert.equal(join.data.application.split_participation,false);assert.equal(join.data.application.requested_split_bps,0);await join.refreshApplication();assert.equal(join.data.splitInput,'0');
 join.inputSplitPercent({detail:{value:'2.75'}});await join.save();assert.equal(join.data.application.requested_split_bps,275,JSON.stringify({status:join.data.status,errors:responseErrors}));}
 const application=join.data.application.application;join.back();assert.equal(join.data.step,0);await join.refreshApplication();assert.equal(join.data.application.application,application);const merchant=page('merchant');await merchant.onLoad({scene:'shop1'});assert.equal(merchant.data.workspace,'merchant',merchant.data.status);await merchant.open({currentTarget:{dataset:{view:'summary'}}});assert.equal(merchant.data.view,'summary',merchant.data.status);assert.equal(merchant.data.summary.provider_settlement_verified,false);await merchant.open({currentTarget:{dataset:{view:'orders'}}});assert.equal(merchant.data.orders.length,0);join.onUnload();merchant.onUnload();process.stdout.write(JSON.stringify({application,summary:'ORIGINAL_ORDER_SUMMARY',payment_enabled:false}));})().catch(e=>{console.error(e);process.exitCode=1;});
