'use strict';
const definitions=require('./merchant-fields.json');
const docs=['IDENTIFICATION_TYPE_IDCARD','IDENTIFICATION_TYPE_OVERSEA_PASSPORT','IDENTIFICATION_TYPE_HONGKONG_PASSPORT','IDENTIFICATION_TYPE_MACAO_PASSPORT','IDENTIFICATION_TYPE_TAIWAN_PASSPORT','IDENTIFICATION_TYPE_FOREIGN_RESIDENT','IDENTIFICATION_TYPE_HONGKONG_MACAO_RESIDENT','IDENTIFICATION_TYPE_TAIWAN_RESIDENT'];
function get(o,path){return path.split('.').reduce((v,k)=>v&&v[k],o);}
function put(o,path,value){const keys=path.split('.');if(keys.some(k=>['__proto__','constructor','prototype'].includes(k)))throw Error('INVALID_FORM_PATH');let p=o;for(let i=0;i<keys.length-1;i++){const k=keys[i];if(!p[k])p[k]=/^\d+$/.test(keys[i+1])?[]:{};p=p[k];}p[keys[keys.length-1]]=value;}
function rows(profile,options,stage){return definitions.filter(f=>f.stage===stage).filter(f=>{
 const p=f.path;if(p.endsWith('id_doc_type'))return false;if(p.includes('{index}'))return options.entity==='ENTERPRISE'&&Number(options.ubos)>0;
 if(p.includes('contact_info.contact_')&&!['contact_info.contact_type','contact_info.contact_name','contact_info.contact_email'].includes(p)&&options.contact!=='SUPER')return false;
 if(p==='contact_info.contact_id_doc_copy_back'&&get(profile,'contact_info.contact_id_doc_type')===docs[1])return false;
 if(p.includes('.id_card_info.'))return options.doc===docs[0];
 if(p.includes('.id_doc_info.'))return options.doc!==docs[0];if(p.includes('biz_store_info.'))return options.scene!=='mini';if(p.includes('mini_program_info.'))return ['mini','both'].includes(options.scene);return true;
}).map(f=>({...f,path:f.path.replace('{index}',String(Math.min(Number(options.uboIndex||0),Math.max(0,Number(options.ubos)-1))))})).map(f=>({...f,label:f.path==='contact_info.contact_name'?(options.contact==='SUPER'?'经办人姓名':'法人/经营者姓名'):f.path==='contact_info.mobile_phone'?(options.contact==='SUPER'?'经办人手机':'法人/经营者联系电话'):f.path==='contact_info.contact_email'?(options.contact==='SUPER'?'经办人邮箱':'法人/经营者邮箱'):f.label,value:get(profile,f.path)||'',required:!(/license_address|business_license_info.period_|bank_branch_id|bank_name/.test(f.path)||(/id_card_address|id_doc_address/.test(f.path)&&options.entity!=='ENTERPRISE')),choices:f.path==='contact_info.contact_type'?['LEGAL','SUPER']:f.path.endsWith('id_doc_type')?docs:f.path==='bank_account_info.bank_account_type'?(options.entity==='ENTERPRISE'?['BANK_ACCOUNT_TYPE_CORPORATE']:['BANK_ACCOUNT_TYPE_CORPORATE','BANK_ACCOUNT_TYPE_PERSONAL']):null}));}
function platformFields(profile){const scenes=get(profile,'business_info.sales_info.sales_scenes_type')||[];const store=scenes.includes('SALES_SCENES_STORE');return {legal_name:get(profile,'subject_info.business_license_info.merchant_name')||'',contact:get(profile,'contact_info.mobile_phone')||'',store_name:get(profile,store?'business_info.sales_info.biz_store_info.biz_store_name':'business_info.merchant_shortname')||'',address:get(profile,store?'business_info.sales_info.biz_store_info.biz_store_address':'subject_info.business_license_info.license_address')||''};}
// Owner20261024 material groups: original field definitions, never a second form.
const docLabels=['中国大陆居民身份证','境外护照','香港来往内地通行证','澳门来往内地通行证','台湾居民来往大陆通行证','外国人永久居留身份证','港澳居民居住证','台湾居民居住证'];
function materialGroups(profile,options,materials,stage){
 const out=[],pick=(ids)=>ids.map(id=>materials.find(m=>m.id===id)||{id,title:({'business_license':'营业执照照片','identity_front':'身份证人像面 / 证件正面','identity_back':'身份证国徽面 / 证件背面','operator_identity':'经办人证件正面','operator_identity_back':'经办人证件背面','storefront_photo':'门头照','interior_photo':'店内环境照','cashier_photo':'收银台照（选填补充）','mini_program_screenshot':'小程序服务页面截图','industry_permit':'行业资质材料'})[id]||id,uploaded:false,connected:false}).map(m=>({...m,connected:m.connected!==false}));
 const add=(id,title,fields,ids=[],extra={})=>{const g={id,title,fields,materials:pick(ids),...extra};out.push(g);return g;};
 const fields=rows(profile,options,0).concat(rows(profile,options,1),rows(profile,options,2));
 const prefix=p=>fields.filter(f=>f.path.startsWith(p));
 const doc=(id,title,path,ids,fs,ocrKind='')=>{const value=get(profile,path)||(id==='legal'?options.doc:docs[0]);const g=add(id,title,fs,ids.filter(k=>value!==docs[1]||!k.endsWith('_back')),{docPath:path,docLabels,docValue:Math.max(0,docs.indexOf(value)),docLabel:docLabels[docs.indexOf(value)]||docLabels[0],ocrKind:ocrKind&&value===docs[0]?ocrKind:''});return g;};
 if(stage===0){
  add('license','营业执照',prefix('subject_info.business_license_info.'),['business_license'],{condition:'entity',conditionLabels:['企业','个体工商户'],conditionValue:options.entity==='ENTERPRISE'?0:1,conditionLabel:options.entity==='ENTERPRISE'?'主体类型 * · 企业':'主体类型 * · 个体工商户',ocrKind:'business_license'});
  add('applicant','办理人',[],[],{condition:'contact',conditionLabels:['法人 / 经营者本人（默认）','授权经办人'],conditionValue:options.contact==='SUPER'?1:0,conditionLabel:'办理人 * · '+(options.contact==='SUPER'?'授权经办人':'法人 / 经营者本人'),note:options.contact==='SUPER'?'法人资料保留；下方追加经办人证件，不替换法人。':'法人资料继续在本组下方填写。'});
  doc('legal','法人 / 经营者证件','subject_info.identity_info.id_doc_type',['identity_front','identity_back'],prefix('subject_info.identity_info.'),'id_front');
  if(options.contact==='SUPER')doc('operator','授权经办人证件','contact_info.contact_id_doc_type',['operator_identity','operator_identity_back'],fields.filter(f=>f.path==='contact_info.contact_name'||/contact_info.contact_(id_number|period_)/.test(f.path)));
  add('contact','联系资料',fields.filter(f=>(options.contact==='SUPER'?['contact_info.mobile_phone','contact_info.contact_email']:['contact_info.contact_name','contact_info.mobile_phone','contact_info.contact_email']).includes(f.path)),[],{note:'手机号和邮箱由本人填写，不由图片识别补造。'});
  if(options.entity==='ENTERPRISE'){
   add('beneficiaries','实际受益人',[],[],{condition:'ubos',conditionLabels:['尚待确认','已确认仅法人一人受益','完整名单1人','完整名单2人','完整名单3人','完整名单4人'],conditionValue:options.ubos==='unknown'?0:Number(options.ubos)+1,conditionLabel:'受益人情况 · '+(options.ubos==='unknown'?'尚待确认':Number(options.ubos)===0?'已确认仅法人一人受益':'完整名单'+options.ubos+'人'),note:options.ubos==='unknown'?'尚未确认，不默认豁免。':'完整名单包含适用法人；同一人不重复采集。'});
   for(let i=0;i<Number(options.ubos||0);i++){const fs=rows(profile,{...options,uboIndex:i},0).filter(f=>f.path.startsWith('subject_info.ubo_info_list.'));doc('ubo'+i,'第'+(i+1)+'位受益人资料','subject_info.ubo_info_list.'+i+'.ubo_id_doc_type',['ubo_'+(i+1)+'_front','ubo_'+(i+1)+'_back'],fs);}
  }
 }
 if(stage===1){
  add('scene','经营场景',[],[],{condition:'scene',conditionLabels:['待确认，请按实际经营选择','实体门店经营','确认仅线上小程序经营、无实体门店','实体门店＋线上小程序经营'],conditionValue:['unknown','store','mini','both'].indexOf(options.scene),conditionLabel:'实际经营场景 * · '+({unknown:'待确认',store:'实体门店',mini:'仅线上，无实体门店',both:'实体门店＋线上经营'}[options.scene]),note:'这是实际经营场景，不是填表渠道。待确认时保留实体门店材料要求。'});
  if(['mini','both'].includes(options.scene))add('mini','小程序经营资料',fields.filter(f=>f.path.startsWith('business_info.')&&!f.path.includes('biz_store_info.')),['mini_program_screenshot'],{note:'服务页面截图按原条件提供；不会自动提取或补造经营信息。'});
  if(options.scene!=='mini')add('store','实体门店资料',prefix('business_info.sales_info.biz_store_info.'),['storefront_photo','interior_photo','cashier_photo'],{photos:true,note:'门头和店内环境在确认实体经营后必传；收银台补充选填。本版各框1张，可替换。三类照片不做OCR、不自动回填；只显示上传、关联与审核状态。'});
  if(!['mini','both'].includes(options.scene))add('business','经营联系资料',fields.filter(f=>['business_info.merchant_shortname','business_info.service_phone'].includes(f.path)));
 }
 if(stage===2){add('industry','行业资质材料适用情况',[],[],{condition:'category',conditionLabels:['按原行业规则核对','原行业要求提供经营许可'],conditionValue:options.category==='FOOD'?1:0,conditionLabel:'行业资质 · '+(options.category==='FOOD'?'原行业要求提供经营许可':'按原行业规则核对'),note:'按实际适用的原行业要求提供资质，不新增微信结算字段或通用必传证照；结算规则仍以原审核核验为准。'});add('qualification','结算规则与行业',prefix('settlement_info.'),options.category==='FOOD'||materials.some(m=>m.id==='industry_permit'&&m.required)?['industry_permit']:[],{note:'只在原行业规则要求时提供资质；不新增默认必传材料。'});add('bank','结算账户',prefix('bank_account_info.'),[],{note:'沿用微信原账户类型与户名规则；其他银行联行号或支行全称至少一项，不新增银行卡照片。'});}
 if(stage===2){const kinds=['settlement_proof',...(options.contact==='SUPER'?['operator_authorization']:[])];const optional=materials.filter(m=>kinds.includes(m.id));if(optional.length)add('optional','原申请选填补充材料',[],optional.map(m=>m.id),{optional:true,note:'可展开原申请历史选填入口。不要求新增银行卡照片，不默认必传，不改变微信审核要求；仅按原审核补件需要使用。'});}
 return out;
}
module.exports={get,put,rows,platformFields,docs,materialGroups};
