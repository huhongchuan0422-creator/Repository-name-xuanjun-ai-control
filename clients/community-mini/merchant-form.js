'use strict';
const definitions=require('./merchant-fields-data');
const licenseRegion=require('./merchant-license-region');
const industryFields=require('./merchant-official-fields');
const industryMaterialKind=kind=>/^industry_permit(?:_[2-5])?$/.test(kind);
function industryMaterialSynced(kind,bindings,profile){const values=get(profile,'settlement_info.qualifications');return Array.isArray(bindings)&&Array.isArray(values)&&bindings.some(b=>b.kind===kind&&typeof b.sha256==='string'&&b.sha256.length===64&&typeof b.media_id==='string'&&values.includes(b.media_id));}
const choiceText={LEGAL:'法人 / 经营者本人',SUPER:'授权经办人',BANK_ACCOUNT_TYPE_CORPORATE:'对公账户',BANK_ACCOUNT_TYPE_PERSONAL:'对私账户（经营者本人）'};
const docs=['IDENTIFICATION_TYPE_IDCARD','IDENTIFICATION_TYPE_OVERSEA_PASSPORT','IDENTIFICATION_TYPE_HONGKONG_PASSPORT','IDENTIFICATION_TYPE_MACAO_PASSPORT','IDENTIFICATION_TYPE_TAIWAN_PASSPORT','IDENTIFICATION_TYPE_FOREIGN_RESIDENT','IDENTIFICATION_TYPE_HONGKONG_MACAO_RESIDENT','IDENTIFICATION_TYPE_TAIWAN_RESIDENT'];
function get(o,path){return path.split('.').reduce((v,k)=>v&&v[k],o);}
function put(o,path,value){const keys=path.split('.');if(keys.some(k=>['__proto__','constructor','prototype'].includes(k)))throw Error('INVALID_FORM_PATH');let p=o;for(let i=0;i<keys.length-1;i++){const k=keys[i];if(!p[k])p[k]=/^\d+$/.test(keys[i+1])?[]:{};p=p[k];}p[keys[keys.length-1]]=value;}
function rows(profile,options,stage){return definitions.filter(f=>f.stage===stage).filter(f=>{
 const p=f.path;if(p==='business_info.service_phone'||p==='bank_account_info.account_name'&&get(profile,'bank_account_info.bank_account_type')==='BANK_ACCOUNT_TYPE_PERSONAL')return false;if(p==='contact_info.contact_name'&&options.contact!=='SUPER')return false;if(p.endsWith('id_doc_type'))return false;if(p.includes('{index}'))return options.entity==='ENTERPRISE'&&Number(options.ubos)>0;
 if(p.includes('contact_info.contact_')&&!['contact_info.contact_type','contact_info.contact_name','contact_info.contact_email'].includes(p)&&options.contact!=='SUPER')return false;
 if(p==='contact_info.contact_id_doc_copy_back'&&get(profile,'contact_info.contact_id_doc_type')===docs[1])return false;
 if(p.includes('.id_card_info.'))return options.doc===docs[0];
 if(p.includes('.id_doc_info.'))return options.doc!==docs[0];if(p.includes('biz_store_info.'))return options.scene!=='mini';if(p.includes('mini_program_info.'))return ['mini','both'].includes(options.scene);return true;
}).map(f=>({...f,path:f.path.replace('{index}',String(Math.min(Number(options.uboIndex||0),Math.max(0,Number(options.ubos)-1))))})).map(f=>({...f,label:f.path==='bank_account_info.bank_account_type'?'账户类型':f.path==='contact_info.contact_name'?(options.contact==='SUPER'?'经办人姓名':'法人/经营者姓名'):f.path==='contact_info.mobile_phone'?(options.contact==='SUPER'?'经办人手机':'法人/经营者联系电话'):f.path==='contact_info.contact_email'?(options.contact==='SUPER'?'经办人邮箱':'法人/经营者邮箱'):f.label,value:get(profile,f.path)||'',required:!(/license_address|business_license_info.period_|bank_branch_id|bank_name/.test(f.path)||(/id_card_address|id_doc_address/.test(f.path)&&options.entity!=='ENTERPRISE')),choices:f.path==='contact_info.contact_type'?['LEGAL','SUPER']:f.path.endsWith('id_doc_type')?docs:f.path==='bank_account_info.bank_account_type'?['BANK_ACCOUNT_TYPE_CORPORATE','BANK_ACCOUNT_TYPE_PERSONAL']:null}));}
function platformFields(profile){const scenes=get(profile,'business_info.sales_info.sales_scenes_type')||[];const store=scenes.includes('SALES_SCENES_STORE');return {legal_name:get(profile,'subject_info.business_license_info.merchant_name')||'',contact:get(profile,'contact_info.mobile_phone')||'',store_name:get(profile,store?'business_info.sales_info.biz_store_info.biz_store_name':'business_info.merchant_shortname')||'',address:get(profile,store?'business_info.sales_info.biz_store_info.biz_store_address':'subject_info.business_license_info.license_address')||''};}
// Owner20261024 material groups: original field definitions, never a second form.
const docLabels=['中国大陆居民身份证','境外护照','香港来往内地通行证','澳门来往内地通行证','台湾居民来往大陆通行证','外国人永久居留身份证','港澳居民居住证','台湾居民居住证'];
function materialGroups(profile,options,materials,stage){
 const out=[],pick=(ids)=>ids.map(id=>materials.find(m=>m.id===id)||{id,title:({'business_license':'营业执照照片','identity_front':'身份证人像面 / 证件正面','identity_back':'身份证国徽面 / 证件背面','operator_identity':'经办人证件正面','operator_identity_back':'经办人证件背面','storefront_photo':'门头照','interior_photo':'店内环境照','cashier_photo':'收银台照（选填补充）','mini_program_screenshot':'小程序服务页面截图','industry_permit':'行业资质材料'})[id]||id,uploaded:false,connected:false}).map(m=>({...m,connected:m.connected!==false}));
 const add=(id,title,fields,ids=[],extra={})=>{fields=fields.map(f=>({...f,choiceLabels:f.choices?f.choices.map(v=>choiceText[v]||v):null,choiceLabel:choiceText[f.value]||f.value||'请选择',choiceIndex:f.choices?Math.max(0,f.choices.indexOf(f.value)):0}));const g={id,title,fields,materials:pick(ids),...extra};out.push(g);return g;};
 const fields=rows(profile,options,0).concat(rows(profile,options,1),rows(profile,options,2));
 const prefix=p=>fields.filter(f=>f.path.startsWith(p));
 const doc=(id,title,path,ids,fs,ocrKind='')=>{const value=get(profile,path)||(id==='legal'?options.doc:docs[0]);const g=add(id,title,fs,ids.filter(k=>value!==docs[1]||!k.endsWith('_back')),{docPath:path,docLabels,docValue:Math.max(0,docs.indexOf(value)),docLabel:docLabels[docs.indexOf(value)]||docLabels[0],ocrKind:ocrKind&&value===docs[0]?ocrKind:'',ocrBackKind:ocrKind==='id_front'&&value===docs[0]?'id_back':''});return g;};
 if(stage===0){
  add('license','营业执照',prefix('subject_info.business_license_info.'),['business_license'],{condition:'entity',conditionLabels:['企业','个体工商户'],conditionValue:options.entity==='ENTERPRISE'?0:1,conditionLabel:options.entity==='ENTERPRISE'?'主体类型 * · 企业':'主体类型 * · 个体工商户',ocrKind:'business_license'});
  add('applicant','办理人',[],[],{condition:'contact',conditionLabels:['法人 / 经营者本人（默认）','授权经办人'],conditionValue:options.contact==='SUPER'?1:0,conditionLabel:'办理人 * · '+(options.contact==='SUPER'?'授权经办人':'法人 / 经营者本人'),note:options.contact==='SUPER'?'法人资料保留；下方追加经办人证件，不替换法人。':'法人资料继续在本组下方填写。'});
  doc('legal','法人 / 经营者证件','subject_info.identity_info.id_doc_type',['identity_front','identity_back'],prefix('subject_info.identity_info.'),'id_front');
  if(options.contact==='SUPER')doc('operator','授权经办人证件','contact_info.contact_id_doc_type',['operator_identity','operator_identity_back'],fields.filter(f=>f.path==='contact_info.contact_name'||/contact_info.contact_(id_number|period_)/.test(f.path)));
  add('contact','联系资料',fields.filter(f=>['contact_info.mobile_phone','contact_info.contact_email'].includes(f.path)),[],{...(options.contact==='LEGAL'?reuseView([legalContactReuse(profile,options)]):{}),note:'联系电话可直接填写。邮箱为正式微信进件必填项，草稿可先保存待补齐。法人本人办理时复用第一步证件姓名；经办人姓名在证件卡单独填写。'});
  if(options.entity==='ENTERPRISE'){
   add('beneficiaries','实际受益人',[],[],{condition:'ubos',conditionLabels:['尚待确认','已确认仅法人一人受益','完整名单1人','完整名单2人','完整名单3人','完整名单4人'],conditionValue:options.ubos==='unknown'?0:Number(options.ubos)+1,conditionLabel:'受益人情况 · '+(options.ubos==='unknown'?'尚待确认':Number(options.ubos)===0?'已确认仅法人一人受益':'完整名单'+options.ubos+'人'),note:options.ubos==='unknown'?'尚未确认，不默认豁免。':'完整名单包含适用法人；同一人不重复采集。'});
   for(let i=0;i<Number(options.ubos||0);i++){const fs=rows(profile,{...options,uboIndex:i},0).filter(f=>f.path.startsWith('subject_info.ubo_info_list.'));doc('ubo'+i,'第'+(i+1)+'位受益人资料','subject_info.ubo_info_list.'+i+'.ubo_id_doc_type',['ubo_'+(i+1)+'_front','ubo_'+(i+1)+'_back'],fs);}
  }
 }
 if(stage===1){
  add('scene','经营场景',[],[],{condition:'scene',conditionLabels:['待确认，请按实际经营选择','实体门店经营','确认仅线上小程序经营、无实体门店','实体门店＋线上小程序经营'],conditionValue:['unknown','store','mini','both'].indexOf(options.scene),conditionLabel:'实际经营场景 * · '+({unknown:'待确认',store:'实体门店',mini:'仅线上，无实体门店',both:'实体门店＋线上经营'}[options.scene]),note:'这是实际经营场景，不是填表渠道。待确认时保留实体门店材料要求。'});
  if(['mini','both'].includes(options.scene))add('mini','小程序经营资料',fields.filter(f=>f.path.startsWith('business_info.')&&!f.path.includes('biz_store_info.')),['mini_program_screenshot'],{...(options.scene==='mini'?reuseView([servicePhoneReuse(profile)]):{}),note:'服务页面截图按原条件提供；不会自动提取或补造经营信息。'});
  if(options.scene!=='mini')add('store','实体门店资料',prefix('business_info.sales_info.biz_store_info.').filter(f=>!['business_info.sales_info.biz_store_info.biz_store_name','business_info.sales_info.biz_store_info.biz_store_address'].includes(f.path)),['storefront_photo','interior_photo',...(materials.some(m=>m.id==='cashier_photo'&&m.uploaded)?['cashier_photo']:[])],{photos:true,...reuseView(storeReuseFields(profile).concat(servicePhoneReuse(profile),regionReuse(profile))),note:'门头和店内环境在确认实体经营后必传；不额外采集收银台照；已有历史材料保留。本版各框1张，可替换。场景照片不做OCR、不自动回填；只显示上传、关联与审核状态。'});
  if(!['mini','both'].includes(options.scene))add('business','经营联系资料',fields.filter(f=>f.path==='business_info.merchant_shortname'),[],{reuseHint:options.scene==='mini'?reuseHint([servicePhoneReuse(profile)]):''});
 }
 if(stage===2){add('industry','实际经营行业',[],[],{industry:true});const selectedIndustry=industryFields.selectedIndustry(options.entity,profile),slots=materials.filter(m=>industryMaterialKind(m.id));const conditional=!!selectedIndustry&&selectedIndustry.special_qualification_required===false&&(selectedIndustry.special_qualification_descriptions||[]).some(t=>t.trim()!=='无需特殊资质');const applicable=options.category==='FOOD'||slots.some(m=>m.required)||!!selectedIndustry&&(selectedIndustry.special_qualification_required===true||conditional&&options.industryQualificationApplies===true);const retained=slots.filter(m=>m.uploaded||m.synced);let visible=[];if(applicable){const last=slots.reduce((n,m,i)=>m.uploaded||m.synced?Math.max(n,i+1):n,0),count=Math.max(1,Number(options.industrySlotCount)||1,last);visible=slots.slice(0,count);}else visible=retained;if(applicable||conditional||retained.length)add('qualification','行业资质材料',[],visible.length?visible.map(m=>m.id):applicable&&!slots.length?['industry_permit']:[],{industryMaterials:true,industryUploadAllowed:applicable,industryConditional:conditional,industryConditionChoice:options.industryQualificationApplies===true?'适用':options.industryQualificationApplies===false?'不适用':'尚未确认',industryCanAdd:applicable&&visible.length<slots.length,materialWarning:applicable&&!slots.length?'行业资质材料入口尚未配置，请联系管理员完善，不能视为免交材料。':'',note:(selectedIndustry?selectedIndustry.condition:'请先选择实际行业，并按对应规则提供资质。')+' 按实际需要逐份添加，最多5份且以当前服务可用槽为准；历史文件保留，上传或选用不代表新行业资质适用或审核通过。'});add('bank','结算账户',prefix('bank_account_info.'),[],{ocrKind:'bank_card',...(get(profile,'bank_account_info.bank_account_type')==='BANK_ACCOUNT_TYPE_PERSONAL'?reuseView([personalAccountReuse(profile,options)]):{}),accountTypePending:options.entity==='ENTERPRISE'&&get(profile,'bank_account_info.bank_account_type')==='BANK_ACCOUNT_TYPE_PERSONAL',personalAccount:get(profile,'bank_account_info.bank_account_type')==='BANK_ACCOUNT_TYPE_PERSONAL',personalAccountName:get(profile,'bank_account_info.account_name')||personalAccountReuse(profile,options).sourceValue||'待确认',note:'沿用微信原账户类型与户名规则；其他银行联行号或支行全称至少一项，不新增银行卡照片。'});}
 if(stage===2){const kinds=['settlement_proof',...(options.contact==='SUPER'?['operator_authorization']:[])];const optional=materials.filter(m=>kinds.includes(m.id)&&m.uploaded);if(optional.length)add('optional','原申请选填补充材料',[],optional.map(m=>m.id),{optional:true,note:'可展开原申请历史选填入口。不要求新增银行卡照片，不默认必传，不改变微信审核要求；仅按原审核补件需要使用。'});}
 return out;
}
// Draft values are preserved verbatim; only the mini formal-submit path requires 11 ASCII digits.
function mobilePhoneError(value,required=false){if(value===undefined||value===null||value==='')return required?'请填写11位联系电话':'';return typeof value==='string'&&value.length===11&&/^[0-9]+$/.test(value)?'':'请输入11位数字联系电话，不含空格、+或-';}
function legalContactName(profile,options){const value=get(profile,'subject_info.identity_info.'+(options.doc===docs[0]?'id_card_info.id_card_name':'id_doc_info.id_doc_name'));return typeof value==='string'?value:'';}
// These are retained form fields, never live OCR suggestions. Confirmed OCR enters
// them only through the existing source/version-bound fillOcrDraft operation.
function storeReuseFields(profile){return [['merchant_name','biz_store_name','门店名称'],['license_address','biz_store_address','详细地址']].map(([source,target,label])=>{const sourcePath='subject_info.business_license_info.'+source,targetPath='business_info.sales_info.biz_store_info.'+target;const raw=get(profile,sourcePath),retained=get(profile,targetPath);const sourceValue=typeof raw==='string'?raw:'',value=typeof retained==='string'?retained:'';const hasSource=!!sourceValue.trim(),hasValue=!!value.trim();return {sourcePath,targetPath,label,sourceValue,value:hasValue?value:sourceValue,conflict:hasSource&&hasValue&&value!==sourceValue,missing:!hasSource,status:hasSource&&hasValue&&value!==sourceValue?'与第一步资料不同，原值已保留，请核对':hasSource?'复用第一步已填写或已核对资料':hasValue?'保留原申请资料；请返回第一步完善':'请返回第一步填写或核对资料'};});}
function reuseStoreFields(profile){let changed=0;for(const field of storeReuseFields(profile))if(!field.missing&&!get(profile,field.targetPath)){put(profile,field.targetPath,field.sourceValue);changed++;}return changed;}
function servicePhoneReuse(profile){const sourceValue=get(profile,'contact_info.mobile_phone'),value=get(profile,'business_info.service_phone');return {label:'客服电话',targetPath:'business_info.service_phone',value,sourceValue,missing:!!mobilePhoneError(sourceValue,true),conflict:!!value&&!mobilePhoneError(sourceValue,true)&&value!==sourceValue};}
function reuseServicePhone(profile){const field=servicePhoneReuse(profile);if(field.missing||get(profile,field.targetPath))return 0;put(profile,field.targetPath,field.sourceValue);return 1;}
function personalAccountReuse(profile,options){const identity=legalContactName(profile,options),license=get(profile,'subject_info.business_license_info.legal_person'),identityName=typeof identity==='string'?identity:'',licenseName=typeof license==='string'?license:'';const sourceConflict=!!identityName.trim()&&!!licenseName.trim()&&identityName!==licenseName,sourceValue=sourceConflict?'':identityName.trim()?identityName:licenseName,value=get(profile,'bank_account_info.account_name');return {label:'个人账户户名',targetPath:'bank_account_info.account_name',value,sourceValue,missing:sourceConflict||!sourceValue.trim(),conflict:sourceConflict||!!value&&!!sourceValue&&value!==sourceValue,sourceConflict};}
function legalContactReuse(profile,options){const sourceValue=legalContactName(profile,options),value=get(profile,'contact_info.contact_name');return {label:'联系人姓名',targetPath:'contact_info.contact_name',value,sourceValue,missing:!sourceValue.trim(),conflict:!!value&&!!sourceValue.trim()&&value!==sourceValue};}
function regionReuse(profile){const resolution=licenseRegion.resolveLicenseRegion(get(profile,licenseRegion.LICENSE_ADDRESS_PATH)),value=get(profile,licenseRegion.BIZ_ADDRESS_CODE_PATH);return {label:'实际经营地区编码',targetPath:licenseRegion.BIZ_ADDRESS_CODE_PATH,value,sourceValue:resolution.ok?resolution.code:'',missing:!resolution.ok,conflict:resolution.ok&&!!value&&value!==resolution.code,resolution};}
function reusedFields(profile,options){return (options.scene==='mini'?[]:storeReuseFields(profile).concat(regionReuse(profile))).concat(options.contact==='LEGAL'?[legalContactReuse(profile,options)]:[],servicePhoneReuse(profile),get(profile,'bank_account_info.bank_account_type')==='BANK_ACCOUNT_TYPE_PERSONAL'?[personalAccountReuse(profile,options)]:[]);}
// A saved source and target may restore a value link only when exactly equal.
// This is not proof of historical OCR confirmation; different values never link.
function reusedFieldLinks(profile,options){return reusedFields(profile,options).reduce((links,field)=>{if(!field.missing&&!field.sourceConflict&&get(profile,field.targetPath)===field.sourceValue)links[field.targetPath]=field.sourceValue;return links;},{});}
function syncReusedFields(profile,options,links){let changed=0;const fields=reusedFields(profile,options);for(const f of fields){if(f.missing){if(f.targetPath===licenseRegion.BIZ_ADDRESS_CODE_PATH&&Object.prototype.hasOwnProperty.call(links,f.targetPath)&&get(profile,f.targetPath)===links[f.targetPath]){const store=get(profile,'business_info.sales_info.biz_store_info');if(store){delete store.biz_address_code;changed++;}delete links[f.targetPath];}continue;}const previous=get(profile,f.targetPath),linked=Object.prototype.hasOwnProperty.call(links,f.targetPath)&&previous===links[f.targetPath];if(!previous||linked){if(previous!==f.sourceValue){put(profile,f.targetPath,f.sourceValue);changed++;}links[f.targetPath]=f.sourceValue;}}return changed;}
function reuseView(fields){return {reuseHint:reuseHint(fields),conflictActions:fields.filter(f=>f.conflict&&!f.missing&&!f.sourceConflict).map(f=>({label:f.label,targetPath:f.targetPath,sourceValue:f.sourceValue,previousValue:f.value}))};}
function reuseHint(fields){return fields.some(f=>f.sourceConflict)?'第一步证件姓名与营业执照法人/经营者姓名不一致，请返回第一步核对。':fields.some(f=>f.conflict)?'原申请资料与第一步内容不同，已保留原值，请返回第一步核对。':fields.some(f=>f.missing)?'请先返回第一步完善资料，已填写的内容会保留。':'';}
// Presentation of the existing required inputs, not a second validation policy.
// Presence is not validity, approval, or OCR confirmation. No profile writes.
function reviewRequirements(profile,options,materials,application){
 const present=v=>typeof v==='string'?!!v.trim():Array.isArray(v)?v.length>0:v!==undefined&&v!==null&&v!==false;
 const labels=new Map(definitions.map(f=>[f.path,f.label]));
 const result=[];
 for(const step of [0,1,2])for(const group of materialGroups(profile,options,materials,step)){
  const items=[],seen=new Set();
  const add=(path,label,value=get(profile,path))=>{if(seen.has(path))return;seen.add(path);items.push({path,label,complete:path==='contact_info.mobile_phone'?!mobilePhoneError(value,true):present(value)});};
  for(const f of group.fields)if(f.required){
   if(f.path.endsWith('mini_program_appid'))add('mini_appid','小程序 AppID（服务商或商户任选一项）',present(get(profile,f.path))||present(get(profile,f.path.replace('mini_program_appid','mini_program_sub_appid'))));
   else add(f.path,f.label);
  }
  if(group.docPath)add(group.docPath,'证件类型');
  if(group.id==='contact'&&options.contact==='LEGAL')add('contact_info.contact_name','法人/经营者联系人姓名');
  if(group.id==='applicant')add('contact_info.contact_type','办理人类型');
  if(group.id==='license'){add('subject_info.subject_type','主体类型');if(['store','both'].includes(options.scene))add('subject_info.business_license_info.license_address','营业执照注册地址（实体经营适用）');}
  if(group.id==='scene'){add('business_info.sales_info.sales_scenes_type','实际经营场景');if(application&&application.declarations)add('declaration:scene','确认实际经营场景',application.declarations.scene!=='unknown');}
  if(group.id==='beneficiaries'&&application&&application.declarations)add('declaration:ubos','确认受益人情况',application.declarations.ubos!=='unknown');
  if(group.id==='store')for(const f of storeReuseFields(profile).concat(regionReuse(profile)))add(f.targetPath,f.label);
  if(group.id===(options.scene==='mini'?'mini':'store'))add('business_info.service_phone','客服电话');
  if(group.id==='bank'){
   add('bank_account_info.account_name','结算开户名称');
   if(get(profile,'bank_account_info.account_bank')==='其他银行')add('bank_branch','支行联行号或支行全称',present(get(profile,'bank_account_info.bank_branch_id'))||present(get(profile,'bank_account_info.bank_name')));
   for(const path of ['settlement_info.settlement_id','settlement_info.qualification_type'])add(path,labels.get(path));
  }
  for(const m of group.materials){
   if(group.optional||m.id==='cashier_photo')continue;
   if(industryMaterialKind(m.id)&&!(group.industryUploadAllowed&&m.uploaded)&&!m.required&&!(m.id==='industry_permit'&&options.category==='FOOD'))continue;
   items.push({path:'material:'+m.id,label:m.title,complete:!!m.uploaded&&(industryMaterialKind(m.id)||!!m.synced),material:true,uploaded:!!m.uploaded,wechatRequired:!industryMaterialKind(m.id),autoWechat:industryMaterialKind(m.id)&&group.industryUploadAllowed===true,synced:!!m.synced});
  }
  if(group.id==='license'&&get(profile,'subject_info.finance_institution')===true){add('subject_info.finance_institution_info.finance_type','金融机构类型');add('subject_info.finance_institution_info.finance_license_pics','金融业务许可证资料');}
  if(group.id==='bank'&&get(profile,'settlement_info.activities_id')){add('settlement_info.debit_activities_rate','优惠活动借记卡费率');add('settlement_info.credit_activities_rate','优惠活动信用卡费率');}
  const missing=items.filter(x=>!x.complete);
  result.push({id:group.id,title:group.title,step,items,total:items.length,completed:items.length-missing.length,missing:missing.map(x=>x.label+(x.material&&x.uploaded?'（提交时自动处理）':'')),missingText:missing.map(x=>x.label+(x.material&&x.uploaded?'（提交时自动处理）':'')).join('、')});
 }
 return result;
}
function assertReviewComplete(groups,application,{platform,wechat}){
 const issues=[];
 const add=(g,item,message)=>{if(issues.some(i=>i.path===item.path))return;issues.push({id:issues.length,message,step:g.step,group:['settlement_info.settlement_id','settlement_info.qualification_type'].includes(item.path)?'industry':g.id,path:item.path});};
 if(wechat)for(const g of groups)for(const item of g.items)if(item.material?item.wechatRequired&&!item.synced:!item.complete)add(g,item,(item.path==='settlement_info.settlement_id'||item.path==='settlement_info.qualification_type'?'经营行业：请选择真实行业，结算配置待系统或平台核定':g.title+'：'+item.label)+(item.material&&item.uploaded?'（已上传，待自动处理）':''));
 if(platform&&application)for(const kind of application.required_materials||[])if(!(application.materials||{})[kind]){const g=groups.find(g=>g.items.some(x=>x.path==='material:'+kind))||{id:'license',step:0,items:[]};const item=g.items.find(x=>x.path==='material:'+kind)||{path:'material:'+kind,label:kind};add(g,item,'原申请证照：'+item.label);}
 if(issues.length){const e=Error('必填资料尚未完成，请补齐：'+issues.map(i=>i.message).join('；'));e.submitPreflight=true;e.issues=issues.map(i=>i.message);e.submitIssues=issues;throw e;}
}
// Plan only already-uploaded required originals. This does not claim provider acceptance.
function reviewMaterialPlan(groups,application,sides){
 const kinds=[];
 const projected=groups.map(group=>({...group,items:group.items.map(item=>{
  if(sides.wechat&&item.material&&(item.wechatRequired||item.autoWechat)&&!item.synced&&item.uploaded){
   const kind=item.path.startsWith('material:')?item.path.slice(9):'';
   if(kind&&kind!=='bank_card'&&application&&application.materials&&application.materials[kind]){if(!kinds.includes(kind))kinds.push(kind);return {...item,synced:true,complete:true};}
  }
  return item;
 })}));
 assertReviewComplete(projected,application,sides);
 return kinds;
}
module.exports={reviewMaterialPlan,industryMaterialKind,industryMaterialSynced,assertReviewComplete,reviewRequirements,get,put,rows,platformFields,docs,materialGroups,mobilePhoneError,legalContactName,storeReuseFields,reuseStoreFields,servicePhoneReuse,reuseServicePhone,reuseHint,reusedFieldLinks,syncReusedFields,personalAccountReuse,legalContactReuse,reusedFields,regionReuse};
