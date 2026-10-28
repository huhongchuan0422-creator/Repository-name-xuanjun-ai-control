'use strict';
const definitions=require('./merchant-fields.json');
const docs=['IDENTIFICATION_TYPE_IDCARD','IDENTIFICATION_TYPE_OVERSEA_PASSPORT','IDENTIFICATION_TYPE_HONGKONG_PASSPORT','IDENTIFICATION_TYPE_MACAO_PASSPORT','IDENTIFICATION_TYPE_TAIWAN_PASSPORT','IDENTIFICATION_TYPE_FOREIGN_RESIDENT','IDENTIFICATION_TYPE_HONGKONG_MACAO_RESIDENT','IDENTIFICATION_TYPE_TAIWAN_RESIDENT'];
function get(o,path){return path.split('.').reduce((v,k)=>v&&v[k],o);}
function put(o,path,value){const keys=path.split('.');if(keys.some(k=>['__proto__','constructor','prototype'].includes(k)))throw Error('INVALID_FORM_PATH');let p=o;for(let i=0;i<keys.length-1;i++){const k=keys[i];if(!p[k])p[k]=/^\d+$/.test(keys[i+1])?[]:{};p=p[k];}p[keys[keys.length-1]]=value;}
function rows(profile,options,stage){return definitions.filter(f=>f.stage===stage).filter(f=>{
 const p=f.path;if(p.includes('{index}'))return options.entity==='ENTERPRISE'&&Number(options.ubos)>0;
 if(p.includes('contact_info.contact_')&&!['contact_info.contact_type','contact_info.contact_name','contact_info.contact_email'].includes(p)&&options.contact!=='SUPER')return false;
 if(p==='contact_info.contact_id_doc_copy_back'&&get(profile,'contact_info.contact_id_doc_type')===docs[1])return false;
 if(p.includes('.id_card_info.'))return options.doc===docs[0];
 if(p.includes('.id_doc_info.'))return options.doc!==docs[0];if(/biz_store_info\.(biz_store_name|biz_store_address)$/.test(p))return false;if(p.includes('biz_store_info.'))return options.scene==='both';return true;
}).map(f=>({...f,path:f.path.replace('{index}',String(Math.min(Number(options.uboIndex||0),Math.max(0,Number(options.ubos)-1))))})).map(f=>({...f,label:f.path==='contact_info.contact_name'?(options.contact==='SUPER'?'经办人姓名':'法人/经营者姓名'):f.path==='contact_info.mobile_phone'?(options.contact==='SUPER'?'经办人手机':'法人/经营者联系电话'):f.path==='contact_info.contact_email'?(options.contact==='SUPER'?'经办人邮箱':'法人/经营者邮箱'):f.label,value:get(profile,f.path)||'',required:!(/license_address|business_license_info.period_|bank_branch_id|bank_name/.test(f.path)||(/id_card_address|id_doc_address/.test(f.path)&&options.entity!=='ENTERPRISE')),choices:f.path==='contact_info.contact_type'?['LEGAL','SUPER']:f.path.endsWith('id_doc_type')?docs:f.path==='bank_account_info.bank_account_type'?(options.entity==='ENTERPRISE'?['BANK_ACCOUNT_TYPE_CORPORATE']:['BANK_ACCOUNT_TYPE_CORPORATE','BANK_ACCOUNT_TYPE_PERSONAL']):null}));}
function platformFields(profile,base){return {...base,legal_name:get(profile,'subject_info.business_license_info.merchant_name')||'',contact:get(profile,'contact_info.mobile_phone')||''};}
module.exports={get,put,rows,platformFields,docs};
