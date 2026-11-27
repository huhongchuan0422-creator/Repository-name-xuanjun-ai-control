function copySigning(page,wx){
 const value=page.data.signUrl;
 if(!page.current())return;
 if(!officialSigningUrl(value)){page.setData({status:'签约链接格式未通过核验，请刷新原申请进度。'});return;}
 const application=page.data.application&&page.data.application.application,session=page.session,epoch=page.epoch,scene=page.scene;
 const current=()=>page.current()&&page.session===session&&page.epoch===epoch&&page.scene===scene&&(page.data.application&&page.data.application.application)===application&&page.data.signUrl===value;
 wx.setClipboardData({data:value,success:()=>{if(current())page.setData({status:'已复制微信官方认证/签约链接，请超级管理员在微信中按页面指引办理'});},fail:()=>{if(current())page.setData({status:'未能复制签约链接，请重试；未进行签约操作。'});}});
}

// Exact existing backend official_signing_url contract. No URL normalization.
function officialSigningUrl(value){
 if(typeof value!=='string'||value.length<1||value.length>256||/[^\x21-\x7e]|\\/.test(value)||value.includes('#')||value.slice(0,8).toLowerCase()!=='https://')return false;
 const rest=value.slice(8),slash=rest.indexOf('/');if(slash<0)return false;
 const host=rest.slice(0,slash),tail=rest.slice(slash),q=tail.indexOf('?');
 if(q<0||q===tail.length-1)return false;
 const path=tail.slice(0,q);
 return host==='pay.weixin.qq.com'&&path==='/public/apply4ec_sign/s'||host==='mp.weixin.qq.com'&&path.startsWith('/')&&!path.startsWith('//');
}

const OCR_PAGE_RESUME=new WeakMap();
const OWNER_WECHAT_CLICK=new WeakMap();
const OWNER_WECHAT_SENT=new WeakMap();
const {parseScene,getSharedSession,customerError,safeOcrDiagnostic,profileValidationDetails}=require('../../session');
const {createChainTelemetry,shouldBlockResubmit,readbackReconciled,SUBMIT_READBACK_COOLDOWN_MS}=require('../../chain-telemetry');
const auth=require('../../customer-auth');
function materialAssociationFailure(error){
 if(!error)return '';
 if(error.mediaCode==='WECHAT_MEDIA_UNAVAILABLE')return '微信材料关联服务暂不可用；照片仍在原申请，本轮未进入提交确认。';
 if(error.mediaCode==='WECHAT_MEDIA_RESULT_UNKNOWN')return '微信材料回执暂未确认；请刷新原申请核对，勿重传照片或重复提交。';
 if(error.networkKind==='TIMEOUT')return '当前步骤未在请求时限内返回；请刷新原申请核对，勿重传照片或重复提交。';
 if(error.code==='ACCESS_DENIED')return '当前步骤被拒绝，无法确认是登录还是资料权限问题。请先核对原申请，不要重复上传或提交。';
 return '';
}
function submissionFailureFeedback(error){
 // Preserve known actionable field/access messages, never generic retry advice.
 if(error&&(['DIRECTORY_MISMATCH','AMBIGUOUS_ADDRESS','INVALID_ADDRESS','INCOMPLETE_ADDRESS','UNRECOGNIZED_ADDRESS','INVALID_REGION_CODE','REGION_CODE_MISMATCH'].includes(error.regionReason)||error.uploadResultUnknown===true||['WECHAT_MEDIA_RESULT_UNKNOWN','WECHAT_MEDIA_UNAVAILABLE'].includes(error.mediaCode)||error.code==='ACCESS_DENIED'||['SESSION_EXPIRED','SIGNED_OUT','UNTRUSTED_SESSION'].includes(error.message)))return customerError(error);
 return '提交进度尚未核实，当前提示不代表微信已受理或未受理';
}
function failedOcrDiagnostic(result){
 const d=typeof safeOcrDiagnostic==='function'?safeOcrDiagnostic(result&&result.ocr_diagnostic):null;
 return d&&d.stage==='EXECUTION'&&['INFERENCE_FAILED','RESULT_PROCESSING_FAILED','RESULT_PERSISTENCE_FAILED'].includes(d.reason)&&d.retryable===false&&d.request_retained===true?d:null;
}
function failedOcrFeedback(result){
 const code=result&&result.error_code;
 if(['INVALID_IMAGE_SIZE','UNSUPPORTED_IMAGE_MAGIC','IMAGE_PIXEL_LIMIT','IMAGE_DECODE_FAILED','ALIYUN_IMAGE_DIMENSIONS_UNSUPPORTED'].includes(code))return '这张照片未能识别，请核对照片是否清晰、完整，或手动填写。';
 if(['ALIYUN_DOCUMENT_TYPE_MISMATCH','ALIYUN_ID_SIDE_MISMATCH'].includes(code))return '请核对照片是否为所选证件及正确的正反面，或手动填写。';
 return '暂时无法读取识别结果，可手动填写。原资料已保留，请勿重复上传。';
}
let form,submitSharedReview,officialFields,platformReference;
let merchantDependencyError=null;
function loadMerchantDependencies(){
 if(form&&submitSharedReview&&officialFields&&platformReference)return;
 form=require('../../merchant-form');
 submitSharedReview=require('../../merchant-submit').submitApplicantApplication;
 officialFields=require('../../merchant-official-fields');
 platformReference=require('../../merchant-platform-reference-data');
}
try{loadMerchantDependencies();}catch(error){merchantDependencyError=error;}
const flatten=lists=>[].concat.apply([],lists);
const RECEIVING_MINI_APPID="wx1d5f8873eaea5392";function fillReceivingMiniAppid(profile,options){
 if(!profile||!options||!['mini','both'].includes(options.scene))return;
 const base='business_info.sales_info.mini_program_info.';
 if(['mini_program_appid','mini_program_sub_appid'].some(key=>{const v=form.get(profile,base+key);return typeof v==='string'&&!!v.trim();}))return;
 form.put(profile,base+'mini_program_appid',RECEIVING_MINI_APPID);
}
const toObject=entries=>entries.reduce((value,entry)=>{value[entry[0]]=entry[1];return value;},{});
const ocrInputFields=kind=>({business_license:['company_name','credit_code','legal_representative','registered_address'],id_front:['id_name','id_number','registered_address'],id_back:['issuing_authority','valid_from','valid_to'],bank_card:['account_number','account_bank']})[kind]||[];
function projectedWechatAuditText(record){
 if(!record||record.provider_state!=='APPLYMENT_STATE_REJECTED'||!Array.isArray(record.audit_detail))return '';
 return record.audit_detail.map(item=>{
  const path=item&&typeof item.param_name==='string'?item.param_name:'';
  const label=path.includes('business_license')?'营业执照':path.includes('identity')?'身份证明':path.includes('bank_account')?'结算账户':path.includes('contact')?'联系人':path.includes('sales')?'经营场景':'微信申请资料';
  const reason=item&&typeof item.reject_reason==='string'?item.reject_reason:'';
  const action=/模糊|不清晰|遮挡|不完整|反光/.test(reason)?'请更换清晰完整的对应材料':/不一致|不匹配/.test(reason)?'请核对填写信息与对应证照保持一致':/过期|有效期/.test(reason)?'请核对有效期并更新对应证件':/缺少|缺失|未提供/.test(reason)?'请补齐对应信息或材料':'请核对并修改对应信息或材料后重新提交微信';
  return label+'：'+action;
 }).filter((x,i,a)=>a.indexOf(x)===i).join('；');
}
function projectedWechatParameterFeedback(app,record){
 const f=record&&record.provider_feedback;
 if(!app||!record||!f||typeof f!=='object'||Array.isArray(f))return null;
 const need=['application','application_revision','code','source','version'];
 const opt=['field','message'];
 if(!need.every(k=>Object.prototype.hasOwnProperty.call(f,k))||
    Object.keys(f).some(k=>!need.includes(k)&&!opt.includes(k)))return null;
 if(f.source!=='VERIFIED_WECHAT'||typeof f.application!=='string'||!f.application||
    f.application!==app.application||!Number.isSafeInteger(f.application_revision)||
    f.application_revision<1||f.application_revision!==app.revision||
    !Number.isSafeInteger(f.version)||f.version<0||f.version!==record.version||
    !['DRAFT','CORRECTION'].includes(record.state)||
    typeof f.code!=='string'||!/^[A-Z][A-Z0-9_]{0,39}$/.test(f.code))return null;
 // Defense in depth only; signed origin and trusted static provider wording are
 // verified on the authenticated server. Never render the raw receipt.
 const field=typeof f.field==='string'&&f.field.length<=128&&
  /^(?:\/[A-Za-z0-9_]+){1,12}$|^[A-Za-z_][A-Za-z0-9_]*(?:(?:\.[A-Za-z0-9_]+)|(?:\[[0-9]{1,3}\])){0,12}$/.test(f.field)?f.field:'';
 const message=typeof f.message==='string'&&f.message.length<=256&&
  !/[<>\u0000-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2060-\u206f]|https?:\/\/|www\.|[\w.+-]+@[\w.-]+|\d(?:[ -]?\d){5,}|[A-Za-z0-9_+=\/-]{20,}/i.test(f.message)?f.message:'';
 return {application:f.application,revision:f.application_revision,version:f.version,
  text:[f.code,field,message].filter(Boolean).join(' · ')};
}
const submitClientOperationLabels=Object.freeze({
 catalog:'读取材料清单',mine:'读取本人申请',read:'读取原申请',wechat_read:'读取微信申请草稿',
 save:'保存原申请草稿',wechat_save:'保存微信申请草稿',wechat_media:'关联照片到微信',wechat_media_status:'读取当前材料关联状态',wechat_media_receipt:'读取已关联材料回执',
 wechat_qualifications_select:'保存资质关联',wechat_cashier_link:'保存收银台照片关联',
 wechat_submit_review:'提交至微信',wechat_apply:'提交至微信',submit:'提交申请',wechat_status:'查询原申请进度'
});
const storePhotoSlotTitles=Object.freeze({storefront_photo:'门头照（第 1 张，共 2 张）',interior_photo:'店内环境照（第 2 张，共 2 张）'});
const miniScreenshotKind='mini_program_screenshot';
const scenePhotoLabels=Object.freeze({...storePhotoSlotTitles,[miniScreenshotKind]:'小程序实际商品或服务页面截图'});
const isScenePhotoKind=id=>Object.prototype.hasOwnProperty.call(scenePhotoLabels,id);
function scenePhotoRequired(id,options){
 const {scene,miniLive}=options;
 if(id===miniScreenshotKind)return (scene==='mini'||scene==='both')&&miniLive!==true;
 return Object.prototype.hasOwnProperty.call(storePhotoSlotTitles,id)&&scene!=='mini';
}
function labelStorePhotoSlots(groups,options){
 return groups.map(group=>{
  const items=group.materials||[];
  const visible=items.filter(item=>!isScenePhotoKind(item.id)||scenePhotoRequired(item.id,options));
  const isStoreGroup=visible.some(item=>Object.prototype.hasOwnProperty.call(storePhotoSlotTitles,item.id));
  if(!items.some(item=>isScenePhotoKind(item.id)))return group;
  return {...group,...(isStoreGroup?{title:'门店照片（门头照、店内环境照各一张）'}:{}),materials:visible.map(item=>isScenePhotoKind(item.id)?{...item,title:scenePhotoLabels[item.id],required:true}:item)};
 });
}
function projectScenePhotoReview(groups,options){
 return groups.map(group=>{
  const items=group.items.filter(item=>!item.material||!isScenePhotoKind(item.path.slice(9))||scenePhotoRequired(item.path.slice(9),options));
  if(items.length===group.items.length)return group;
  const missing=items.filter(item=>!item.complete).map(item=>item.label+(item.material&&item.uploaded?'（提交时自动处理）':''));
  return {...group,items,total:items.length,completed:items.length-missing.length,missing,missingText:missing.join('、')};
 });
}
const branchField=path=>path==='bank_account_info.bank_name'||path==='bank_account_info.bank_branch_id';
const bankNeedsBranch=profile=>form.get(profile,'bank_account_info.account_bank')==='其他银行';
function settlementProfileForSave(profile){
 const selected=form.get(profile,'bank_account_info.account_bank');
 if(typeof selected!=='string'||!selected.trim()||bankNeedsBranch(profile)||!profile.bank_account_info)return profile;
 const value={...profile,bank_account_info:{...profile.bank_account_info}};
 delete value.bank_account_info.bank_name;
 delete value.bank_account_info.bank_branch_id;
 return value;
}
const ocrHasValue=value=>typeof value==='string'?!!value.trim():value!==undefined&&value!==null;
const sameOcrView=(left,right)=>JSON.stringify(left)===JSON.stringify(right);
const sameOcrFields=(left,right)=>!!left&&!!right&&sameOcrView(Object.keys(left).sort(),Object.keys(right).sort())&&Object.keys(left).every(key=>left[key]===right[key]);
function ocrCandidateHint(field){const candidates=field&&Array.isArray(field.candidates)?field.candidates.filter(item=>item&&typeof item.value==='string'&&item.value.trim()):[];return candidates.length>1?'存在多个识别候选，请核对：'+candidates.map(item=>item.value).join('；'):field&&Array.isArray(field.warnings)&&field.warnings.includes('LAYOUT_VALUE_MISSING')?'未识别到可靠值，请手动核对填写':field&&Array.isArray(field.warnings)&&field.warnings.includes('LAYOUT_GEOMETRY_UNAVAILABLE')?'该项文字位置未识别完整，请核对':'';}
function ocrOrientationHint(result){const o=result&&result.orientation;if(!o||typeof o!=='object')return '';if(o.ambiguous===true)return '图片方向尚有歧义，请对照原图核对；';const degrees=o.clockwise_rotation_to_upright_degrees;if(o.ambiguous!==false||![0,90,180,270].includes(degrees))return '';return degrees===0?'已按正向图像识别；':'已将图像顺时针旋转'+degrees+'°后识别；';}
function splitBps(text){const value=String(text).trim(),match=/^(0|[1-9]\d{0,2})(?:\.(\d{1,2}))?$/.exec(value);if(!match)throw Error('请填写有效爱心捐赠比例，最多两位小数；0表示不参与');const bps=Number(match[1])*100+Number((match[2]||'').padEnd(2,'0'));if(bps>10000)throw Error('爱心捐赠比例超出有效范围');return bps;}
function splitLabel(value){return Number.isSafeInteger(value)&&value>=0&&value<=10000?String(Number((value/100).toFixed(2)))+'%':'待核验';}
// Byte units are decimal: 1 MB target, existing 5 MB persisted-file boundary.
// Image quality cannot be inferred from byte size; device/OCR acceptance remains required.
const MERCHANT_IMAGE_TRIGGER=1500000,MERCHANT_IMAGE_TARGET=1000000,MERCHANT_IMAGE_SAVE_LIMIT=5000000;
function merchantImageError(code){const error=new Error(code);error.imagePreparation=true;return error;}
function merchantImageMessage(error){return ({IMAGE_CANCELLED:'已取消照片处理，未上传',IMAGE_INFO_FAILED:'无法读取照片信息，未上传；请重新选择原图',IMAGE_COMPRESSION_FAILED:'照片无法自动压缩至可保存大小，未上传；请保留原图并重拍清晰证照',IMAGE_SAVE_LIMIT:'处理后的照片仍超过5MB保存门禁，未上传；请重拍清晰证照',IMAGE_READ_FAILED:'处理后的照片读取失败，未上传；请重新选择原图',IMAGE_FILE_CHANGED:'照片处理期间文件发生变化，未上传；请重新选择原图'})[error.message]||'照片处理失败，未上传；请保留原图后重试';}
async function prepareMerchantImage(api,source,current,onProgress,originalOnly=false,saveLimit=MERCHANT_IMAGE_SAVE_LIMIT){
 const check=()=>{if(!current())throw merchantImageError('IMAGE_CANCELLED');};
 const invoke=(method,options,code)=>new Promise((resolve,reject)=>{try{method({...options,success:resolve,fail:()=>reject(merchantImageError(code))});}catch(_){reject(merchantImageError(code));}});
 const fs=api.getFileSystemManager();
 const stat=async path=>{
  check();let value;
  if(typeof fs.stat==='function'){const result=await invoke(o=>fs.stat(o),{path},'IMAGE_INFO_FAILED');value=result.stats&&result.stats.size;}
  else if(typeof api.getFileInfo==='function'){const result=await invoke(o=>api.getFileInfo(o),{filePath:path},'IMAGE_INFO_FAILED');value=result.size;}
  else throw merchantImageError('IMAGE_INFO_FAILED');
  check();if(!Number.isSafeInteger(value)||value<1)throw merchantImageError('IMAGE_INFO_FAILED');return value;
 };
 check();const originalSize=await stat(source),privateCopy=saveLimit===MERCHANT_IMAGE_TARGET;let best={path:source,size:originalSize},attempts=0;
 if(originalOnly&&originalSize>MERCHANT_IMAGE_SAVE_LIMIT)throw merchantImageError('IMAGE_SAVE_LIMIT'); if(!originalOnly&&originalSize>Math.min(MERCHANT_IMAGE_TRIGGER,saveLimit)){
  let info=null;
  if(typeof api.getImageInfo==='function'){try{info=await invoke(o=>api.getImageInfo(o),{src:source},'IMAGE_INFO_FAILED');}catch(_){}check();}
  const validDimensions=value=>value&&Number.isSafeInteger(value.width)&&Number.isSafeInteger(value.height)&&value.width>0&&value.height>0;
  const inspectCandidate=async(path,width,height)=>{
   if(!path||path===source)return null;
   const output=await invoke(o=>api.getImageInfo(o),{src:path},'IMAGE_INFO_FAILED');check();
   // EXIF normalization may swap axes, but must not silently downsample or upscale.
   if(!validDimensions(output))return null;
   const short=Math.min(output.width,output.height),long=Math.max(output.width,output.height);
   if(privateCopy){
    const sourceShort=Math.min(info.width,info.height),sourceLong=Math.max(info.width,info.height);
    if(short<Math.min(1200,sourceShort)-1||short>sourceShort||long>sourceLong||
       Math.abs(long-short*sourceLong/sourceShort)>Math.max(2,long*0.01))return null;
   }else if(short!==Math.min(width,height)||long!==Math.max(width,height))return null;
   const size=await stat(path);return size<best.size?{path,size,width:output.width,height:output.height}:null;
  };
  // Always encode from the original, never recompress a prior lossy output.
  // The three quality trials are bounded local work, not an original-file size cap.
  if(validDimensions(info)&&typeof api.compressImage==='function')for(const quality of (privateCopy?[90,75,60,45]:[90,80,70])){
   check();onProgress('正在自动压缩照片，目标约1MB；保留原图');attempts++;
   try{const result=await invoke(o=>api.compressImage(o),{src:source,quality,compressedWidth:info.width,compressedHeight:info.height},'IMAGE_COMPRESSION_FAILED');check();const candidate=await inspectCandidate(result.tempFilePath,info.width,info.height);if(candidate)best=candidate;if(best.size<=MERCHANT_IMAGE_TARGET)break;}catch(error){check();}
  }
  // At most two proportional resizes; never enlarge or shrink the shorter edge
  // below 1600 px (or its original value). This pixel safeguard is not a claim
  // that text is legible; dense-text and device acceptance are still mandatory.
  if(best.size>MERCHANT_IMAGE_TARGET&&validDimensions(info)&&typeof api.compressImage==='function'){
   const floor=Math.min(1,(privateCopy?1200:1600)/Math.min(info.width,info.height));let scale=1;
   for(let step=0;step<(privateCopy?4:2);step++){
    const next=Math.max(floor,scale*Math.max(privateCopy?0.55:0.75,Math.sqrt(MERCHANT_IMAGE_TARGET/best.size)*(privateCopy?0.88:1)));
    if(next>=scale)break;scale=next;check();attempts++;onProgress('正在保留证照细节并调整照片尺寸；原图不变');
    try{const width=Math.max(1,Math.round(info.width*scale)),height=Math.max(1,Math.round(info.height*scale));const result=await invoke(o=>api.compressImage(o),{src:source,quality:privateCopy?[75,60,45,32][step]:80,compressedWidth:width,compressedHeight:height},'IMAGE_COMPRESSION_FAILED');check();const candidate=await inspectCandidate(result.tempFilePath,width,height);if(candidate)best=candidate;if(best.size<=MERCHANT_IMAGE_TARGET)break;}catch(error){check();}
   }
  }
 }
 const validateSelected=async()=>{check();if(best.path===source)return true;try{const output=await invoke(o=>api.getImageInfo(o),{src:best.path},'IMAGE_INFO_FAILED');check();return output&&output.width===best.width&&output.height===best.height&&(await stat(best.path))===best.size;}catch(error){check();return false;}};
 if(!await validateSelected())best={path:source,size:originalSize};
 check();if(best.size>saveLimit)throw merchantImageError(saveLimit===MERCHANT_IMAGE_TARGET?'IMAGE_PRIVATE_SAVE_LIMIT':attempts?'IMAGE_SAVE_LIMIT':'IMAGE_COMPRESSION_FAILED');
 // Only the selected bounded file enters base64/JSON memory.
 const result=await invoke(o=>fs.readFile(o),{filePath:best.path,encoding:'base64'},'IMAGE_READ_FAILED');check();const content=result.data;
 if(typeof content!=='string'||content.length%4||!/^[A-Za-z0-9+/]*={0,2}$/.test(content))throw merchantImageError('IMAGE_READ_FAILED');
 const bytes=Math.floor(content.length/4)*3-(content.endsWith('==')?2:content.endsWith('=')?1:0);
 if(!await validateSelected())throw merchantImageError('IMAGE_FILE_CHANGED');
 if(bytes!==best.size)throw merchantImageError('IMAGE_FILE_CHANGED');if(bytes<1||bytes>saveLimit)throw merchantImageError(saveLimit===MERCHANT_IMAGE_TARGET?'IMAGE_PRIVATE_SAVE_LIMIT':'IMAGE_SAVE_LIMIT');
 return {path:best.path,originalPath:source,originalSize,size:bytes,content,compressed:best.path!==source,targetReached:bytes<=MERCHANT_IMAGE_TARGET,attempts};
}
let freshNavigation=null;
function freshGeneration(s){return s&&typeof s.getGeneration==='function'?s.getGeneration():null;}
function freshSame(page,i){return !!(i&&page.current()&&page.session===i.session&&page.epoch===i.epoch&&page.scene===i.scene&&freshGeneration(page.session)===i.generation);}
const {startDirectOcr}=require('./direct-ocr');
const {directProof}=require('./direct-proof');
const clientOcrClock=()=>typeof performance!=='undefined'&&typeof performance.now==='function'?performance.now():null;
async function directOriginal(api,source,current){
 const check=()=>{if(!current())throw merchantImageError('IMAGE_CANCELLED');};
 const fs=api.getFileSystemManager();
 const run=(method,data)=>new Promise((resolve,reject)=>method({...data,success:resolve,fail:()=>reject(merchantImageError('IMAGE_READ_FAILED'))}));
 async function boundedSize(){
  check();let n;
  if(typeof fs.stat==='function'){const r=await run(o=>fs.stat(o),{path:source});n=r.stats&&r.stats.size;}
  else if(typeof api.getFileInfo==='function')n=(await run(o=>api.getFileInfo(o),{filePath:source})).size;
  if(!Number.isSafeInteger(n)||n<1)throw merchantImageError('IMAGE_INFO_FAILED');
  return n;
 }
 const size=await boundedSize();
 if(size>10000000)return {path:source,size,content:null,compressed:false,ocrTooLarge:true};
 const reply=await run(o=>fs.readFile(o),{filePath:source,encoding:'base64'});check();
 const content=reply.data;
 if(typeof content!=='string'||content.length%4||!/^[A-Za-z0-9+/]*={0,2}$/.test(content))throw merchantImageError('IMAGE_READ_FAILED');
 const n=content.length/4*3-(content.endsWith('==')?2:content.endsWith('=')?1:0);
 if(n!==size||await boundedSize()!==size)throw merchantImageError('IMAGE_FILE_CHANGED');
 return {path:source,size,content,compressed:false};
}
function directOcrHint(page,kind,key,hasStored,row,field,savedRow,freshRow,active,held){
 const hint=page.directOcrHints&&page.directOcrHints[kind];
 const value=hint&&hint.active()&&hint.fields[key];
 const has=(object,key)=>object!=null&&Object.prototype.hasOwnProperty.call(object,key);
 const touched=has(page.ocrExplicitEmptyFields,field.path)||(active&&has(page.ocrSuggestionEdits,key))||(held&&held.local_state&&has(held.local_state.edits,key));
 const blankLegacy=row&&!savedRow&&!freshRow&&row.value==='';
 if(kind==='bank_card'&&hasStored&&typeof value==='string'&&value&&value!==form.get(page.profile,field.path))return {ocrDirect:'',ocrDirectCompare:kind,ocrHint:'识别建议：'+value+'；已填写内容保留，请人工核对。'};
 if(hasStored||touched||(row&&!blankLegacy)||typeof value!=='string'||!value)return {ocrDirect:''};
 const display={value,ocrDirect:kind,ocrHint:'识别建议，请人工核对',ocrKey:'',ocrRetained:false,ocrPrivateDraft:false,ocrSuggestion:false,ocrConflict:false,ocrInReview:false,ocrResultPresent:kind!=='bank_card'};
 if(kind==='bank_card'&&key==='account_bank'&&Array.isArray(field.choices)){
  const compact=v=>typeof v==='string'?v.trim().replace(/\s/g,'').replace(/股份有限公司$|有限责任公司$|有限公司$/,''):'';
  const matches=field.choices.map((x,i)=>[x,i]).filter(([x,i])=>[x,(field.choiceLabels||[])[i]].some(v=>compact(v)&&compact(v)===compact(value)));
  if(matches.length===1){const [bank,i]=matches[0];return {...display,value:bank,choiceIndex:i,choiceLabel:(field.choiceLabels||[])[i]||bank};}
  return {...display,ocrManualBank:true,choiceLabel:'识别到：'+value+'（请选择开户银行）'};
 }
 return display;
}
Page({
  scanStore(){return auth.scanStore(this,wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
  goBack(){return this.navigateSection({currentTarget:{dataset:{section:'back'}}});},
 data:{signQrImage:'',signQrPending:false,signQrStatus:'',providerAuditText:'',providerParameterFeedback:null,submitIssues:[],missingFieldPath:'',reuseConfirmation:null,splitInput:'',splitChoiceEdited:false,splitSaveUnknown:false,requestedSplitLabel:'尚未填写',effectiveSplitLabel:'尚未生效',providerSplitLabel:'尚未核定',splitReceiverLabel:'社区接收账户由后台配置，当前配置状态待核验',pendingRedemptionPercent:10,redemptionIndex:1,redemptionOptions:['0%','10%','20%','25%','30%'],wechatReviewState:'NOT_SUBMITTED',editMaterialGroup:'',stateLabels:{"PROVIDER_ACCEPTED":"微信已受理，等待审核状态","APPLYMENT_STATE_EDITTING":"微信资料待补正","未提交":"未提交","PENDING_INTERNAL_REVIEW":"待本人提交微信（旧本站状态不再审核）","INTERNAL_APPROVED":"待本人提交微信（非微信通过）","SUBMISSION_UNKNOWN":"微信提交结果待核实","SUBMITTED_TO_PROVIDER":"已向微信提交，结果以微信进度为准","未核验":"未核验","未开通":"未开通","未提供":"未提供","DRAFT":"草稿未提交","SUBMITTED":"已提交，待审核","IN_REVIEW":"审核中","CORRECTION_REQUIRED":"待补正资料","CORRECTION":"待补正资料","REJECTED":"审核未通过","APPROVED":"平台审核通过","WITHDRAWN":"已撤回","PENDING":"待审核","NOT_SUBMITTED":"尚未提交微信","NOT_VERIFIED":"尚未核验","NOT_APPROVED":"尚未开通","AWAITING_CRM_BINDING":"等待原业务绑定","ACCESS_SUSPENDED":"访问已暂停","OPENING_PENDING":"开通处理中","OPENED":"工作台已开通","APPLYMENT_STATE_EDITING":"微信资料编辑中","APPLYMENT_STATE_AUDITING":"微信审核中","APPLYMENT_STATE_REJECTED":"微信审核未通过","APPLYMENT_STATE_TO_BE_CONFIRMED":"待微信账户确认","APPLYMENT_STATE_TO_BE_SIGNED":"待签约","APPLYMENT_STATE_SIGNING":"签约处理中","APPLYMENT_STATE_FINISHED":"微信进件完成，收款资格另核","APPLYMENT_STATE_CANCELED":"微信申请已取消"},showOptionalMaterials:false,uploadFeedback:null,ocrFeedback:null,ocrProgressState:'',materialPreviewHints:{},materialPreviews:{},ocrConfirmed:false,ocrRows:[],ocrJob:'',ocrKind:'',ocrDiagnostic:null,materialOcrErrors:{},ocrStatus:'证照按需离线识别，结果须人工核对；三照片不识别',pending:false,authenticated:false,sessionRecoveryRequired:false,ready:false,readState:'IDLE',readError:'',needsScene:true,status:'',activeSection:'profile',licenseMaterial:null,mobilePhoneError:'',mobilePhoneTouched:false,dirty:false,leavePrompt:false,leaveTarget:'',fieldCursor:0,cursorPath:'',materialCursor:0,step:0,steps:['主体与法人资料','实际经营场景','结算资料','核对与进度'],applications:[],application:null,fields:[],base:{store_name:'',address:''},options:{entity:'ENTERPRISE',contact:'LEGAL',doc:'IDENTIFICATION_TYPE_IDCARD',scene:'unknown',miniLive:false,ubos:'unknown',uboIndex:0,category:'GENERAL'},materials:[],catalog:[],canEditPlatform:false,canEditWechat:false,platformState:'未提交',wechatReviewState:'NOT_SUBMITTED',wechatState:'未核验',openingState:'未开通'},
 onShow(){this.invalidateSigningQr();this.ocrHidden=false;if(this.pendingPickerShow)this.pendingPickerShow.finish(true);this.providerForeground=(this.providerForeground||0)+1;if(this.data.application&&this.session&&!this.sceneStale)this.materialPreviewRestore=this.restoreUploadedMaterialPreviews();this.scheduleUploadedOcrRestore();if(this.ocrPolling)this.scheduleOcrPoll();const activeScene=getApp().globalData.scene;if(this.scene&&activeScene&&this.scene!==activeScene&&!this.sceneStale){this.privatePreviewCleanup();this.invalidateOcr();this.cancelStepOcrReview();this.sceneStale=true;this.dead=true;this.session=null;this.profile={};this.ocrDrafts={};this.industryOtherSelected=false;this.industryConditionChoices={};this.operatorContactName='';this.legalContactName='';this.reusedFieldLinks={};this.syncSplitChoice(null);this.inactiveUboList=null;this.version=0;this.reviewState=null;this.cashierMediaId='';this.setData({submitIssues:[],missingFieldPath:'',uploadFeedback:null,materialOcrErrors:{},materialPreviews:{},regionLabel:'',regionIndices:[0,0,0],regionColumns:[[],[],[]],industryLabels:[],industryValue:0,industryHint:'',platformAppidStatus:'平台身份未核实',ocrRows:[],ocrJob:'',showOptionalMaterials:false,displayReviewGroups:[],reviewGroups:[],materialGroups:[],documentGroups:[],scenePhotoCards:[],miniSceneMaterials:[],adjacentMaterials:[],licenseMaterial:null,applications:[],application:null,fields:[],materials:[],signUrl:'',base:{store_name:'',address:''},step:0,platformState:'未提交',wechatReviewState:'NOT_SUBMITTED',wechatState:'未核验',openingState:'未开通',pending:false,ready:false,authenticated:false,canEditPlatform:false,canEditWechat:false,dirty:false,leavePrompt:false,leaveTarget:'',status:'授权场景已切换，原申请资料已清除，请重新进入对应门店'});this.syncLeaveGuard();}if(this.session&&typeof this.session.isAuthenticated==='function'&&!this.session.isAuthenticated()&&!this.data.pending&&!this.sceneInvalid&&!this._sceneStale&&!this.sceneStale){this.connectApplicant({automatic:true});}this.presentStepOcrReview();this.scheduleProviderPoll();},
 async onLoad(options){if(options&&options.freshDraft==='1'&&freshNavigation&&freshNavigation.phase==='NAVIGATING'){this.freshIntent=freshNavigation;freshNavigation.phase='VERIFYING';this.setData({freshDraftPage:true});}this.cancelStepOcrReview();this.ocrRestoreOnLoad=true;this.dead=false;this.sceneStale=false;if(merchantDependencyError){try{loadMerchantDependencies();merchantDependencyError=null;}catch(_){this.setData({pending:false,ready:false,authenticated:false,status:'商家入驻页面组件加载失败，请返回后重试'});return;}}this.verifyPlatformAppid();this.invalidateOcr();this.epoch=auth.current();this.profile={};this.ocrDrafts={};this.industryOtherSelected=false;this.industryConditionChoices={};this.operatorContactName='';this.legalContactName='';this.reusedFieldLinks={};this.version=0;const value=options&&options.scene||getApp().globalData.scene;this.scene='';if(value){try{this.scene=parseScene({scene:value});getApp().globalData.scene=this.scene;}catch(_){this.sceneInvalid=true;this.setData({status:'门店入口无效，请返回首页或重新扫码；不会自动切换到其他门店'});this.refresh();return;}}this.setData({needsScene:!this.scene,status:'无需已有门店。微信登录后填写并保存本人申请，审核通过后才开通工作台。'});this.refresh();if(this.scene||getApp().globalData.baseUrl)await this.connectApplicant({automatic:true});},
 verifyPlatformAppid(){this.platformAppid=null;try{const info=typeof wx.getAccountInfoSync==='function'?wx.getAccountInfoSync():null;if(info&&info.miniProgram&&info.miniProgram.appId===platformReference.appid)this.platformAppid=info.miniProgram.appId;}catch(_){}},
 async connectApplicant(options={}){if(this.sceneInvalid||this.data.pending)return;this.verifyPlatformAppid();this.epoch=auth.current();let phase='login';this.setData({pending:true,status:'正在验证微信身份',ready:false,readState:'IDLE',readError:'',canEditPlatform:false,canEditWechat:false});try{this.session=getSharedSession(wx,getApp().globalData,undefined,this);this.epoch=auth.current();await this.session.ensureLogin({automatic:options.automatic===true,prepared:true});if(!this.current())return;this.setData({authenticated:true,sessionRecoveryRequired:false,readState:'LOADING',status:'身份已验证，正在读取材料清单和本人申请'});phase='catalog';const catalog=await this.request('catalog',{});phase='mine';const result=await this.request('mine',{});if(!this.current())return;const ranks={APPROVED:7,IN_REVIEW:6,SUBMITTED:6,PENDING_INTERNAL_REVIEW:6,CORRECTION_REQUIRED:5,REJECTED:4,DRAFT:3,WITHDRAWN:0};const applications=[...result.applications].sort((a,b)=>(ranks[b.status]||1)-(ranks[a.status]||1)||Number(b.revision||0)-Number(a.revision||0)||String(a.application).localeCompare(String(b.application)));let useFresh=false;
 if(this.freshIntent){
 const intent=this.freshIntent;
 const match=applications.find(a=>a.application===intent.application&&a.status==='DRAFT'&&a.revision===intent.revision);
 if(intent.phase==='VERIFYING'&&match&&freshSame(this,intent)){intent.phase='BLANK';useFresh=true;}
 else if(intent.phase==='BLANK'&&match&&freshSame(this,intent)){useFresh=true;}
 else if(intent.phase==='UNKNOWN'){this.setData({ready:false,canEditPlatform:false,canEditWechat:false,status:'另开草稿的结果待核实。不会再次创建，请返回原草稿。'});return;}
 else if(intent.phase==='KNOWN'&&freshSame(this,intent)&&applications.some(a=>a.application===intent.saved)){/* select below */}
 else {this.setData({ready:false,canEditPlatform:false,canEditWechat:false,status:'原草稿状态或登录已变化，请返回。'});return;}
 }
 const recovery=this.interruptedReviewDraft;
 const recovering=!!(recovery&&recovery.scene===this.scene);
 const selected=recovering?applications.find(a=>a.application===recovery.application):useFresh?null:this.freshIntent?applications.find(a=>a.application===this.freshIntent.saved):applications[0]||null;
 if(recovering&&!selected){
  const message='此登录未读到原申请。不会改读其他申请或新建草稿，请核对原微信账号。';
  this.setData({authenticated:false,sessionRecoveryRequired:true,ready:false,readState:'FAILED',readError:message,canEditPlatform:false,canEditWechat:false,status:message});
  return;
 }
 this.setData({authenticated:true,ready:!selected,readState:selected?'LOADING':'READY',readError:'',canEditPlatform:!selected,canEditWechat:!selected,catalog:catalog.materials,applications:selected?[selected]:[],dirty:false,status:selected?'已找到本人唯一继续申请，正在读取':'身份已验证。填写资料并保存同一份申请草稿。'});if(selected){
  const selectedSession=this.session,selectedGeneration=freshGeneration(this.session);
  await this.load(selected.application);
  if(!this.current()||this.session!==selectedSession||freshGeneration(this.session)!==selectedGeneration||!this.data.application||this.data.application.application!==selected.application||this.loadedDisplayApplication!==selected.application)return;
  this.setData({ready:true,readState:'READY'});this.refresh();
  if(recovering&&this.current()&&this.interruptedReviewDraft===recovery&&this.loadedDisplayApplication===recovery.application&&this.data.application&&this.data.application.application===recovery.application)this.interruptedReviewDraft=null;
 }else{this.syncSplitChoice(null);this.setData({pendingRedemptionPercent:10,redemptionIndex:1});this.refresh();}}catch(error){if(!this.current())return;const sessionLost=!this.session||typeof this.session.isAuthenticated==='function'&&!this.session.isAuthenticated();const expired=error&&(error.code==='SESSION_EXPIRED'||error.message==='SESSION_EXPIRED');if(phase==='login'||expired||sessionLost){this.setData({authenticated:false,ready:false,readState:'IDLE',readError:'',status:customerError(error)});}else{const label=phase==='catalog'?'材料清单':'本人申请';const message=customerError(error);this.setData({authenticated:true,ready:false,readState:'FAILED',readError:label+'读取失败：'+message,status:label+'读取失败，可直接重试读取；无需重新登录'});}}finally{if(this.current())this.setData({pending:false});}},
 retryApplicantRead(){return this.connectApplicant({automatic:true});},
 current(){return !this.dead&&!this.sceneStale&&auth.active(this.epoch);},

 async requestWechatWithRateRecovery(operation,params,noMediaRetry=false){const session=this.session,scene=this.scene,epoch=this.epoch,id=this.data.application&&this.data.application.application;const current=()=>this.current()&&this.session===session&&this.scene===scene&&this.epoch===epoch&&(!id||this.data.application&&this.data.application.application===id);for(;;){if(!current())throw Error('STALE_SESSION');try{return await session.merchant(scene||'','onboarding',{operation,params});}catch(error){if(noMediaRetry&&['wechat_media','wechat_media_status','wechat_submit_review','wechat_read','wechat_save','wechat_status'].includes(operation)||!error||error.wechatRateLimited!==true||!operation.startsWith('wechat_')||typeof setTimeout!=='function'||!current()){
 if(this.submitClientTrace&&error&&typeof error==='object'&&Object.prototype.hasOwnProperty.call(submitClientOperationLabels,operation))
  this.submitClientTrace.set(error,submitClientOperationLabels[operation]);
 throw error;
 }this.setData({status:'已达到原服务请求频率限制，正在等待一分钟后继续；本次请求尚未执行，已保存资料保留。'});await new Promise(resolve=>setTimeout(resolve,60000));}}},
 request(operation,params,noMediaRetry=false,skipDonationDraft=false){if(!this.session)throw Error('SESSION_EXPIRED');if(['submit','wechat_submit_review','wechat_apply'].includes(operation)&&!(operation==='wechat_apply'&&params&&params.retry_unknown===true)){this.assertSubmitCooldown(operation);}let edited=false;if(operation==='save'){if(!skipDonationDraft&&this.data.splitSaveUnknown)throw Error('上次爱心捐赠比例保存结果待核实，请先重新读取原申请');params={...params,redemption_percent:Number.isInteger(this.data.pendingRedemptionPercent)?this.data.pendingRedemptionPercent:Number((this.data.application&&this.data.application.redemption_percent)||0)};if(!skipDonationDraft&&(this.data.splitChoiceEdited||this.data.splitDefaultPending&&!this.data.application)){let bps;try{bps=splitBps(this.data.splitInput);const maximum=this.data.application&&this.data.application.provider_max_split_bps;if(Number.isSafeInteger(maximum)&&bps>maximum)throw Error('爱心捐赠比例超过当前渠道配置上限（'+splitLabel(maximum)+'）');}catch(error){error.donationValidation=true;throw error;}params={...params,split_participation:bps>0,requested_split_bps:bps};edited=true;}}try{const response=this.requestWechatWithRateRecovery(operation,params,noMediaRetry);return edited?Promise.resolve(response).catch(error=>{if(this.current())this.setData({splitSaveUnknown:true,status:'爱心捐赠比例保存结果待核实，请先重新读取原申请，不要重复保存'});throw error;}):response;}catch(error){if(edited&&this.current())this.setData({splitSaveUnknown:true});throw error;}},
 syncSplitChoice(app){const click=OWNER_WECHAT_CLICK.get(this);const preserve=click&&app&&app.application===click.application&&click.donationDraft;const participates=app&&app.split_participation===true,requested=app&&app.requested_split_bps,effective=app&&app.effective_split_bps;this.setData({splitInput:app?(Number.isSafeInteger(requested)?String(Number((requested/100).toFixed(2))):'0'):'0.5',splitChoiceEdited:false,splitDefaultPending:!app,splitSaveUnknown:false,requestedSplitLabel:app?(participates?splitLabel(requested):'不参与（0%）'):'尚未填写',effectiveSplitLabel:app&&app.status==='APPROVED'?(participates?splitLabel(effective):'不参与（0%）'):'尚未生效',providerSplitLabel:app&&Number.isSafeInteger(app.provider_max_split_bps)?splitLabel(app.provider_max_split_bps):'尚未核定',splitReceiverLabel:'社区接收账户由后台配置，当前配置状态待核验',...(preserve||{})});},
 inputSplitPercent(event){if(this.data.pending||!this.data.canEditPlatform||this.data.splitSaveUnknown)return;this.setData({splitInput:event.detail.value,splitChoiceEdited:true,dirty:true,status:'爱心捐赠比例尚未保存'});this.syncLeaveGuard();},
 async reloadSplitChoice(){if(this.data.pending)return;if(this.data.application)return this.run(()=>this.load(this.data.application.application));await this.connectApplicant({automatic:true});},
 // Presentation-only expiry recovery. Never renew a session, replay an action,
 // clear draft data, or infer that an earlier request was not received here.
 showApplicantSessionRecovery(){
  if(!this.current()||!(this.data.authenticated||this.data.sessionRecoveryRequired))return false;
  const session=this.session;
  if(session&&(typeof session.isAuthenticated!=='function'||session.isAuthenticated()))return false;
  const rejected=this.interruptedReviewDraft&&this.interruptedReviewDraft.denied;
  const signedOut=!!(session&&typeof session.isSignedOut==='function'&&session.isSignedOut());
  this.setData({authenticated:false,sessionRecoveryRequired:true,status:signedOut?'已退出登录；请按需重新登录并核对原申请，系统不会自动继续保存、上传或确认。':rejected?'上次材料关联请求被拒，原申请仍待核对；没有证据表示微信登录过期。请读取原申请，不要重复提交。':'登录已失效；请重新登录并核对原申请，本次操作未完成，系统不会自动重试。'});
  return true;
 },
 async run(task,stage=''){if(this.data.pending)return;if(this.showApplicantSessionRecovery())return;
 const binding=stage==='提交审核'?{session:this.session,epoch:this.epoch,scene:this.scene,application:this.data.application&&this.data.application.application,generation:this.session&&typeof this.session.getGeneration==='function'?this.session.getGeneration():null}:null;
 // Result writes still require the original authenticated generation.
 const samePageBinding=()=>this.current()&&(!binding||this.session===binding.session&&this.epoch===binding.epoch&&this.scene===binding.scene&&(this.data.application&&this.data.application.application)===binding.application);
 const currentResult=()=>samePageBinding()&&(!binding||binding.generation===null||this.session&&typeof this.session.getGeneration==='function'&&this.session.getGeneration()===binding.generation);
 let rejectedAccess=false,clientStep=''; const trace=binding?new WeakMap():null;if(trace)this.submitClientTrace=trace;
 const invalidatedSameBinding=()=>binding&&samePageBinding()&&!currentResult()&&this.session&&typeof this.session.isAuthenticated==='function'&&this.session.isAuthenticated()===false;
 if(stage==='提交审核')this.reviewMaterialStage=null;
 this.setData({pending:true,...(stage?{status:stage+'处理中，请稍候。'}:{})});try{await task();}catch(e){clientStep=trace&&e&&typeof e==='object'?trace.get(e)||'':'';rejectedAccess=!!(e&&e.code==='ACCESS_DENIED'&&e.accessHttpStatus!==401);if(currentResult()){if(e&&e.mediaReceiptRecovered){this.setData({status:'材料回执已恢复并保存；本轮未重新发送材料或提交申请，请核对后继续。'});return;}this.noteSubmitOutcome(e);if(e&&e.message==='SESSION_EXPIRED'&&this.showApplicantSessionRecovery())return;
  const profileFailure=stage==='提交审核'&&typeof profileValidationDetails==='function'?profileValidationDetails(e,this.data.reviewGroups||[]):null;
  const material=stage==='提交审核'&&this.reviewMaterialStage;
  const failureStage=material?'关联'+material.material+'（'+material.count+'）：'+material.phase:stage==='提交审核'&&e&&e.submissionDiagnostic&&e.submissionDiagnostic.operation==='wechat_status'?'查询原申请进度':stage;
  const directMediaFailure=material&&material.phase==='发送本材料到微信'&&!profileFailure&&e&&!e.submitPreflight&&!e.contactValidation&&e.code!=='ACCESS_DENIED'&&
   !['SESSION_EXPIRED','SIGNED_OUT','UNTRUSTED_SESSION'].includes(e.message);
  const associationFailure=directMediaFailure?'未收到可核验的微信返回。本次未发出正式审核申请，原照片已保留。':material&&!profileFailure&&materialAssociationFailure(e);
  this.setData({submitIssues:e&&e.submitIssues||profileFailure&&profileFailure.issues||[],status:associationFailure?failureStage+'：'+associationFailure:e&&(e.contactValidation||e.submitPreflight)?(stage?stage+'未完成：':'')+e.message:(failureStage?failureStage+'失败：':'')+(profileFailure?profileFailure.feedback:e&&e.donationValidation===true?e.message:stage==='提交审核'?submissionFailureFeedback(e):customerError(e))+(profileFailure?'；原申请内容已保留，未自动重试。':'；请先重新读取原申请，勿重复提交。')});
  }}finally{
  const association=binding&&this.reviewMaterialStage;
  if(binding)this.reviewMaterialStage=null;if(trace&&this.submitClientTrace===trace)this.submitClientTrace=null;
  if(currentResult()){
   this.setData({pending:false});await this.finishConfirmedOcrSave();this.presentStepOcrReview();if(this.providerForeground)this.scheduleProviderPoll();
  }else if(invalidatedSameBinding()){
   // A generic 403 can clear the session inside request(). Release this
   // operation's spinner without using its results or replaying any write.
   const where=clientStep?clientStep+'时':association?'处理'+association.material+'（'+association.count+'）时':'';const status=where+(rejectedAccess?'请求被拒，具体原因未确认。':'登录会话已中断。')+'请通过页面登录入口重新验证并只读核对，不会重传或提交。';
   if(binding.application)this.interruptedReviewDraft={application:binding.application,scene:binding.scene,denied:rejectedAccess};
   this.setData({pending:false,authenticated:false,sessionRecoveryRequired:true,canEditPlatform:false,canEditWechat:false,status});
  }
 } },
 syncLeaveGuard(){if(typeof wx.enableAlertBeforeUnload!=='function')return;if(this.data.dirty)wx.enableAlertBeforeUnload({message:'当前有未保存修改，确认离开将丢失未保存内容。'});else if(typeof wx.disableAlertBeforeUnload==='function')wx.disableAlertBeforeUnload();},
 refresh(afterRender){if(!this.current())return;if(this.data.ready&&this.data.canEditWechat)fillReceivingMiniAppid(this.profile,this.data.options);this.syncLeaveGuard();const app=this.data.application;const count=this.data.options.entity==='ENTERPRISE'&&this.data.options.ubos!=='unknown'?Number(this.data.options.ubos):0;const mobileError='';const bankAccount=form.get(this.profile,'bank_account_info.account_bank');const bankBranchId=form.get(this.profile,'bank_account_info.bank_branch_id');const bankName=form.get(this.profile,'bank_account_info.bank_name');const bankBranchMissing=bankAccount==='其他银行'&&!((typeof bankBranchId==='string'&&bankBranchId.length>0)||(typeof bankName==='string'&&bankName.length>0));const bankBranchGroupHint=bankAccount==='其他银行'?(bankBranchMissing?'支行信息：联行号或支行全称至少填写一项 *':'支行信息：联行号或支行全称至少填写一项（已满足）'):'';const fields=flatten(form.materialGroups(this.profile,this.data.options,[],this.data.step).map(group=>group.fields)).map(field=>field.path==='contact_info.mobile_phone'?{...field,maxlength:-1,phoneHint:'11位数字联系电话，不含空格、+或-'}:field);const oldCursorPath=this.data.cursorPath||(this.data.fields[this.data.fieldCursor]&&this.data.fields[this.data.fieldCursor].path);const foundCursor=oldCursorPath?fields.findIndex(field=>field.path===oldCursorPath):-1;const fieldCursor=foundCursor>=0?foundCursor:Math.min(Number(this.data.fieldCursor||0),Math.max(0,fields.length-1));const materials=this.data.catalog.map(m=>{const path=this.materialProfilePath(m.id),value=m.id==='cashier_photo'?this.cashierMediaId:path?form.get(this.profile,path):undefined;return {...m,required:!!app&&app.required_materials.includes(m.id),uploaded:!!app&&!!app.materials[m.id],synced:form.industryMaterialKind(m.id)?form.industryMaterialSynced(m.id,this.industryQualificationBindings,this.profile):Array.isArray(value)?value.length>0:!!value,industryMaterial:form.industryMaterialKind(m.id),review:app&&app.materials[m.id]?app.materials[m.id].review:'未提供'};});const licenseMaterial=materials.find(m=>m.id==='business_license')||null;const materialCursor=Math.min(Number(this.data.materialCursor||0),Math.max(0,materials.length-1));const showLicenseUpload=this.data.step===0;const activePath=(fields[fieldCursor]&&fields[fieldCursor].path)||'';let adjacentKinds=[];if(this.data.step===0)adjacentKinds=['identity_front',...(this.data.options.doc==='IDENTIFICATION_TYPE_OVERSEA_PASSPORT'?[]:['identity_back']),...(count>0?['ubo_'+(this.data.options.uboIndex+1)+'_front',...(form.get(this.profile,'subject_info.ubo_info_list.'+this.data.options.uboIndex+'.ubo_id_doc_type')==='IDENTIFICATION_TYPE_OVERSEA_PASSPORT'?[]:['ubo_'+(this.data.options.uboIndex+1)+'_back'])]:[])];if(this.data.step===1&&this.data.options.contact==='SUPER')adjacentKinds=['operator_identity',...(form.get(this.profile,'contact_info.contact_id_doc_type')==='IDENTIFICATION_TYPE_OVERSEA_PASSPORT'?[]:['operator_identity_back'])];const adjacentMaterials=materials.filter(m=>adjacentKinds.includes(m.id));const docLabels=['中国大陆居民身份证','境外护照','香港来往内地通行证','澳门来往内地通行证','台湾居民来往大陆通行证','外国人永久居留身份证','港澳居民居住证','台湾居民居住证'];const docSelector=(path,title,kinds)=>{const value=form.get(this.profile,path)||(path==='subject_info.identity_info.id_doc_type'?this.data.options.doc:form.docs[0]);return {path,title,labels:docLabels,value,label:docLabels[form.docs.indexOf(value)]||'请选择证件类型',materials:materials.filter(m=>kinds.includes(m.id))};};const documentGroups=this.data.step===0?[docSelector('subject_info.identity_info.id_doc_type',this.data.options.entity==='ENTERPRISE'?'法人身份证明':'经营者身份证明',['identity_front','identity_back']),...(count>0?[docSelector('subject_info.ubo_info_list.'+this.data.options.uboIndex+'.ubo_id_doc_type','第'+(this.data.options.uboIndex+1)+'位受益人身份证明',['ubo_'+(this.data.options.uboIndex+1)+'_front','ubo_'+(this.data.options.uboIndex+1)+'_back'])]:[])]:this.data.step===1&&this.data.options.contact==='SUPER'?[docSelector('contact_info.contact_id_doc_type','经办人身份证明',['operator_identity','operator_identity_back'])]:[];for(const group of documentGroups)if(group.value==='IDENTIFICATION_TYPE_OVERSEA_PASSPORT')group.materials=group.materials.filter(m=>!m.id.endsWith('_back'));const photoFor=(kind,title,required)=>{const found=materials.find(x=>x.id===kind);return {id:kind,title,required,uploaded:!!(found&&found.uploaded),synced:!!(found&&found.synced),connected:!!found,review:(found&&found.review)||'未提供'};};const scenePhotoCards=this.data.step===1&&this.data.options.scene!=='mini'?[photoFor('storefront_photo',storePhotoSlotTitles.storefront_photo,true),photoFor('interior_photo',storePhotoSlotTitles.interior_photo,true),photoFor('cashier_photo','收银台照',false)]:[];const miniSceneMaterials=this.data.step===1&&scenePhotoRequired(miniScreenshotKind,this.data.options)?materials.filter(x=>x.id===miniScreenshotKind):[];const materialGroups=labelStorePhotoSlots(form.materialGroups(this.profile,this.data.options,materials,this.data.step),this.data.options);const groupedFields=flatten(materialGroups.map(g=>g.fields)).map(f=>({...f,maxlength:f.path==='contact_info.mobile_phone'?-1:512,phoneHint:'11位数字联系电话，不含空格、+或-'}));for(const group of materialGroups)group.fields=group.fields.map(f=>({...f,ocrResultPresent:this.ocrFieldPresent(f.path,group.ocrKind),index:groupedFields.findIndex(x=>x.path===f.path),maxlength:f.path==='contact_info.mobile_phone'?-1:512,phoneHint:'11位数字联系电话，不含空格、+或-'}));for(const group of materialGroups)group.hasOcrFields=group.fields.some(field=>field.ocrResultPresent);const reviewGroups=projectScenePhotoReview(form.reviewRequirements(this.profile,this.data.options,materials,app),this.data.options);this.setData({...this.officialFieldView(),materialOcrErrors:this.materialOcrFailureView(),reviewGroups,displayReviewGroups:this.reviewPresentation({...this.data,materials}),materialGroups:this.projectOcrGroups(materialGroups),documentGroups,scenePhotoCards,miniSceneMaterials,adjacentMaterials,showLicenseUpload,fieldCursor,cursorPath:fields[fieldCursor]?fields[fieldCursor].path:'',materialCursor,licenseMaterial,bankBranchGroupHint,mobilePhoneError:mobileError,uboLabels:Array.from({length:count},(_,i)=>'第'+(i+1)+'位'),fields:groupedFields,materials},()=>{this.presentStepOcrReview();if(afterRender)afterRender();});},
 navigateSection(e){if(this.sceneStale&&['home','back'].includes(e.currentTarget.dataset.section))return this.navigateToSection('home');if(this.sceneStale){this.setData({status:'授权场景已切换，请重新进入对应门店'});return;}if(this.data.pending){this.setData({status:'当前请求仍在进行，请等待完成后再离开'});return;}const section=e.currentTarget.dataset.section;if(this.data.dirty){this.setData({leavePrompt:true,leaveTarget:section,status:'当前有未保存修改。选择“保存并离开”才会保存；取消将留在本页。'});return;}this.navigateToSection(section);},
 navigateToSection(section){return auth.navigate(this,section==='merchant'?'merchant':section,wx,getApp(),typeof getCurrentPages==='function'?getCurrentPages():[]);},
 cancelLeave(){this.setData({leavePrompt:false,leaveTarget:'',status:'已保留未保存修改'});},
 async saveAndLeave(){if(this.data.pending)return;const target=this.data.leaveTarget;let saved=false;await this.run(async()=>{await this.saveDraft();saved=this.current()&&!this.data.dirty;if(saved)this.setData({leavePrompt:false,leaveTarget:''});});if(saved&&this.current())this.navigateToSection(target);},

 openMerchant(){return this.navigateSection({currentTarget:{dataset:{section:'merchant'}}});},
 async select(e){if(this.data.dirty){this.setData({status:'当前草稿有未保存修改，请先保存或取消修改后再切换原申请'});return;}const id=e.currentTarget.dataset.application;await this.run(()=>this.load(id));},
 createSubmitReadback(app,record,filtered=false){
  if(!record||!Number.isSafeInteger(record.version))return null;
  // Write replies keep historical OCR drafts; only wechat_read filters them.
  // Fall back to that original read whenever this projection is needed.
  if(!filtered&&record.ocr_drafts&&Object.keys(record.ocr_drafts).length)return null;
  if(!filtered&&record.mini_program_live===true){const mini=form.get(record.profile||{},'business_info.sales_info.mini_program_info')||{},ids={};for(const key of ['mini_program_appid','mini_program_sub_appid'])if(typeof mini[key]==='string'&&mini[key].trim())ids[key]=mini[key];if(!Object.keys(ids).length||!sameOcrFields(ids,record.mini_program_live_appids||{}))return null;}
  return {application:app.application,revision:app.revision,record:JSON.parse(JSON.stringify(record)),session:this.session,epoch:this.epoch,scene:this.scene,used:false};
 },
 createProviderReceiptReadback(app,record,operation){
  if(!app||!record||typeof record.provider_state!=='string')return null;
  let revision=app.revision,platformState=app.status;
  if(operation==='wechat_apply'||operation==='wechat_submit_review'){
   if(record.state!=='SUBMITTED_TO_PROVIDER')return null;
   if(platformState==='DRAFT'){revision++;platformState='SUBMITTED';}
   else if(!['SUBMITTED','IN_REVIEW','APPROVED'].includes(platformState))return null;
  }else if(operation==='wechat_status'){
   // Editable or unresolved states still need the original fresh provider view.
   if(record.state!=='SUBMITTED_TO_PROVIDER')return null;
  }else return null;
  const receipt=this.createSubmitReadback({application:app.application,revision},record);
  return receipt?{...receipt,platformState,providerState:record.provider_state}:null;
 },
 applyLoadedApplicationDisplay(app,record){
  const first=this.loadedDisplayApplication!==app.application;
  this.loadedDisplayApplication=app.application;
  const state=record.state||'DRAFT',provider=app.wechat_submerchant_state;
  const correction=state==='CORRECTION'||app.status==='CORRECTION_REQUIRED';
  const progress=provider==='APPLYMENT_STATE_FINISHED'||!correction&&['SUBMISSION_UNKNOWN','SUBMITTED_TO_PROVIDER'].includes(state);
  const status=provider==='APPLYMENT_STATE_FINISHED'?'微信已完成进件；工作台和收款资格仍按原系统授权分别核验':state==='SUBMISSION_UNKNOWN'?'微信提交结果待核实，请查看原申请进度；不会重复提交':state==='SUBMITTED_TO_PROVIDER'?'已读取微信进件进度，审核与签约以微信核验结果为准':state==='CORRECTION'||app.status==='CORRECTION_REQUIRED'?'已读取原申请补正资料，请按审核意见核对':state==='DRAFT'||app.status==='DRAFT'?'已读取原申请草稿':'已读取原申请状态';
  this.setData({...(first?{step:progress?3:0}:{}),status});
 },
 async load(id,guard,readback){this.invalidateSigningQr();const loadSession=this.session,loadEpoch=this.epoch,loadScene=this.scene,loadGeneration=freshGeneration(this.session);const loadCurrent=()=>this.current()&&this.session===loadSession&&this.epoch===loadEpoch&&this.scene===loadScene&&freshGeneration(this.session)===loadGeneration&&(!guard||guard());if(!loadCurrent())return;
 const feedbackSession=this.session,feedbackEpoch=this.epoch,feedbackScene=this.scene;
 const feedbackGeneration=feedbackSession&&typeof feedbackSession.getGeneration==='function'?feedbackSession.getGeneration():null;
 const feedbackLoad={};this.providerParameterFeedbackLoad=feedbackLoad;this.setData({providerParameterFeedback:null});
 const supplied=readback&&!readback.used&&readback.application===id&&readback.session===this.session&&readback.epoch===this.epoch&&readback.scene===this.scene?readback:null;if(readback)readback.used=true;const previous=this.data.ocrConfirmed&&this.ocrCapture?{...this.ocrCapture,confirmationRevision:this.ocrConfirmationRevision}:null;this.invalidateOcr('正在读取当前申请，旧识别请求已失效');const app=await this.request('read',{application:id});if(!loadCurrent())return;if(!app||app.application!==id)throw Error('APPLICATION_IDENTITY_MISMATCH');const record=supplied&&supplied.application===app.application&&supplied.revision===app.revision&&supplied.session===this.session&&supplied.epoch===this.epoch&&supplied.scene===this.scene&&(!Object.prototype.hasOwnProperty.call(supplied,'platformState')||supplied.platformState===app.status&&supplied.providerState===app.wechat_submerchant_state)?supplied.record:await this.request('wechat_read',{application:id},OWNER_WECHAT_CLICK.has(this));if(!loadCurrent())return;const feedbackFresh=this.providerParameterFeedbackLoad===feedbackLoad&&feedbackSession&&
   this.session===feedbackSession&&this.epoch===feedbackEpoch&&this.scene===feedbackScene&&
   feedbackGeneration!==null&&feedbackSession.getGeneration()===feedbackGeneration&&
   typeof feedbackSession.isAuthenticated==='function'&&feedbackSession.isAuthenticated()&&
   app.application===id&&!(supplied&&supplied.record===record);
 const providerParameterFeedback=feedbackFresh?projectedWechatParameterFeedback(app,record):null;
 const localDraft=app.local_presubmission_editable===true&&
    ['DRAFT','CORRECTION_REQUIRED','SUBMITTED','IN_REVIEW'].includes(app.status)&&
    ['DRAFT','CORRECTION','PENDING_INTERNAL_REVIEW','INTERNAL_APPROVED'].includes(record.state)&&
    (record.provider_state===undefined||record.provider_state==='NOT_SUBMITTED')&&!record.business_code&&!record.applyment_id;
  this.invalidateOcr('已读取当前申请；可按需识别已上传证照并人工核对');this.syncSplitChoice(app);if(this.data.application&&this.data.application.application!==app.application){this.setData({uploadFeedback:null,materialPreviews:{}});this.operatorContactName='';this.legalContactName='';this.reusedFieldLinks={};}this.industryOtherSelected=false;this.ocrExplicitEmptyFields={};this.profile=record.profile||{};this.ocrDrafts=record.ocr_drafts||{};if(form.get(this.profile,'contact_info.contact_type')==='SUPER')this.operatorContactName=form.get(this.profile,'contact_info.contact_name')||'';else this.legalContactName=form.get(this.profile,'contact_info.contact_name')||'';this.version=record.version;this.reviewState=localDraft&&record.state!=='CORRECTION'?'DRAFT':record.state||'DRAFT';this.miniLiveEdited=false;this.cashierMediaId=record.cashier_media_id||'';this.industryQualificationBindings=Array.isArray(record.industry_qualification_bindings)?record.industry_qualification_bindings:[];this.setData({pendingRedemptionPercent:Number.isInteger(app.redemption_percent)?app.redemption_percent:0,redemptionIndex:Math.max(0,[0,10,20,25,30].indexOf(app.redemption_percent)),mobilePhoneTouched:false,dirty:false,leavePrompt:false,leaveTarget:'',fieldCursor:0,cursorPath:'',materialCursor:0,application:app,base:{store_name:app.fields.store_name,address:app.fields.address},options:{entity:app.entity_type,contact:form.get(this.profile,'contact_info.contact_type')||(app.delegated?'SUPER':'LEGAL'),doc:app.identity_type,scene:app.declarations?app.declarations.scene:(form.get(this.profile,'business_info.sales_info.sales_scenes_type')||[]).length?(app.sales_scenes_type.includes('SALES_SCENES_STORE')?(app.sales_scenes_type.includes('SALES_SCENES_MINI_PROGRAM')?'both':'store'):'mini'):'unknown',ubos:app.declarations?app.declarations.ubos:((form.get(this.profile,'subject_info.ubo_info_list')||[]).length||'unknown'),uboIndex:0,category:app.category,miniLive:record.mini_program_live===true,industryQualificationApplies:(this.industryConditionChoices||{})[JSON.stringify([app.application,app.entity_type,form.get(this.profile,'settlement_info.settlement_id'),form.get(this.profile,'settlement_info.qualification_type')])]},platformState:localDraft?'DRAFT':app.status,wechatReviewState:this.reviewState,wechatState:app.wechat_submerchant_state,signUrl:record.provider_sign_url||'',...(this.providerParameterFeedbackLoad===feedbackLoad?{providerParameterFeedback}:{}),providerAuditText:projectedWechatAuditText(record),openingState:app.opening_state,canEditPlatform:localDraft||['DRAFT','CORRECTION_REQUIRED'].includes(app.status),canEditWechat:app.status!=='WITHDRAWN'&&['DRAFT','CORRECTION'].includes(this.reviewState),materials:Object.entries(app.materials).map(([kind,m])=>({kind,...m})),status:'已读取原申请草稿'});this.applyLoadedApplicationDisplay(app,record);this.reusedFieldLinks=form.reusedFieldLinks(this.profile,this.data.options);this.cancelReuse();this.refresh();if(previous&&previous.application===app.application&&previous.revision===app.revision&&previous.seen_application_revision===String(app.revision)&&previous.seen_provider_version===record.version){this.ocrRequestGeneration=(this.ocrRequestGeneration||0)+1;this.ocrCapture={...previous,generation:this.ocrGeneration,request_generation:this.ocrRequestGeneration};this.ocrConfirmationRevision=previous.confirmationRevision;this.setData({ocrKind:previous.document_type,ocrJob:previous.job_id,ocrStatus:'正在重新读取已确认的OCR记录'});await this.readOcr();}else if(this.ocrRestoreOnLoad){this.ocrRestoreOnLoad=false;await this.restoreKnownOcr();}this.queueUploadedOcrRestore();this.materialPreviewRestore=this.restoreUploadedMaterialPreviews();this.scheduleProviderPoll();if(loadCurrent()&&this.data.application===app&&this.version===record.version&&(!supplied||record!==supplied.record))return this.createSubmitReadback(app,record,true);},
 chooseRedemption(e){if(this.data.pending||!this.data.canEditPlatform)return;const choices=[0,10,20,25,30],value=e.currentTarget.dataset.value!==undefined?Number(e.currentTarget.dataset.value):choices[Number(e.detail&&e.detail.value)];if(!choices.includes(value))return;this.setData({pendingRedemptionPercent:value,redemptionIndex:choices.indexOf(value),dirty:true});this.syncLeaveGuard();},
 chooseMiniLive(e){if(this.data.pending||!this.data.canEditWechat)return;const live=Array.isArray(e.detail.value)&&e.detail.value.includes('live');if(live&&!form.get(this.profile,'business_info.sales_info.mini_program_info.mini_program_appid')&&!form.get(this.profile,'business_info.sales_info.mini_program_info.mini_program_sub_appid')){this.setData({options:{...this.data.options,miniLive:false},status:'请先填写你有权用于本次进件的小程序 AppID；不使用当前运行小程序的身份。'});return;}this.miniLiveEdited=true;this.setData({options:{...this.data.options,miniLive:live},dirty:true});this.syncLeaveGuard();this.refresh();},
 input(e){const path=e.currentTarget.dataset.path;if(path==='bank_account_info.account_name'||branchField(path)&&!bankNeedsBranch(this.profile))return;const value=e.detail.value;if(!this.ocrExplicitEmptyFields)this.ocrExplicitEmptyFields={};if(value==='')this.ocrExplicitEmptyFields[path]=true;else delete this.ocrExplicitEmptyFields[path];this.ocrFormEditVersion=(this.ocrFormEditVersion||0)+1;if(!this.reusedFieldLinks)this.reusedFieldLinks={};const source=['subject_info.business_license_info.merchant_name','subject_info.business_license_info.license_address','contact_info.mobile_phone','subject_info.business_license_info.legal_person','subject_info.identity_info.id_card_info.id_card_name','subject_info.identity_info.id_doc_info.id_doc_name'].includes(path);if(source)Object.assign(this.reusedFieldLinks,form.reusedFieldLinks(this.profile,this.data.options));form.put(this.profile,path,value);if(['business_info.sales_info.mini_program_info.mini_program_appid','business_info.sales_info.mini_program_info.mini_program_sub_appid'].includes(path)){this.miniLiveEdited=true;this.setData({options:{...this.data.options,miniLive:false}});this.refresh();}if(source&&this.data.canEditWechat)form.syncReusedFields(this.profile,this.data.options,this.reusedFieldLinks);this.setData({dirty:true});this.syncLeaveGuard();if(path==='contact_info.mobile_phone'){this.setData({dirty:true,mobilePhoneTouched:true,mobilePhoneError:''});this.refresh();}else if(['bank_account_info.account_bank','bank_account_info.bank_branch_id','bank_account_info.bank_name'].includes(path)){this.refresh();}},
 startReuseConfirmation(e){if(!this.current()||this.data.pending||!this.data.canEditWechat)return;const data=e.currentTarget.dataset,field=form.reusedFields(this.profile,this.data.options).find(f=>f.targetPath===data.target);if(!field||!field.conflict||field.missing||field.sourceConflict)return;if(field.sourceValue!==data.source||form.get(this.profile,field.targetPath)!==data.previous){this.setData({status:'资料已变化，请核对当前内容后再确认采用第一步资料'});this.refresh();return;}this.reuseConfirmationBinding={application:this.data.application&&this.data.application.application,session:this.session,epoch:this.epoch};this.setData({reuseConfirmation:{target:field.targetPath,source:field.sourceValue,previous:data.previous,label:field.label}});},
 cancelReuse(){this.reuseConfirmationBinding=null;this.setData({reuseConfirmation:null});},
 confirmReuse(){if(!this.current()||this.data.pending||!this.data.canEditWechat)return;const data=this.data.reuseConfirmation,binding=this.reuseConfirmationBinding;if(!data||!binding)return;const field=form.reusedFields(this.profile,this.data.options).find(f=>f.targetPath===data.target);if(binding.application!==(this.data.application&&this.data.application.application)||binding.session!==this.session||binding.epoch!==this.epoch||!field||!field.conflict||field.missing||field.sourceConflict||field.sourceValue!==data.source||form.get(this.profile,field.targetPath)!==data.previous){this.cancelReuse();this.setData({status:'申请或资料已变化，请重新核对并确认，原值未替换'});this.refresh();return;}form.put(this.profile,field.targetPath,field.sourceValue);if(!this.reusedFieldLinks)this.reusedFieldLinks={};this.reusedFieldLinks[field.targetPath]=field.sourceValue;this.cancelReuse();this.setData({dirty:true,status:'已按你的确认更新本地草稿，请保存'});this.syncLeaveGuard();this.refresh();},
 switchContactName(next){if(next===this.data.options.contact)return;const value=form.get(this.profile,'contact_info.contact_name')||'';if(this.data.options.contact==='SUPER')this.operatorContactName=value;else this.legalContactName=value;form.put(this.profile,'contact_info.contact_name',next==='SUPER'?(this.operatorContactName||''):(this.legalContactName||form.legalContactName(this.profile,this.data.options)));if(this.reusedFieldLinks)delete this.reusedFieldLinks['contact_info.contact_name'];},
 focusField(e){const path=e.currentTarget.dataset.path;if((this.data.materialGroups||[]).some(group=>(group.fields||[]).some(field=>field.path===path)))this.ocrFocus={kind:'field',path,value:(flatten(this.data.materialGroups.map(g=>g.fields||[])).find(field=>field.path===path)||{}).value||'',capture:this.ocrCapture};},
 focusOcrSuggestion(e){const key=e.currentTarget.dataset.key;if(this.data.ocrRows.some(row=>row.key===key))this.ocrFocus={kind:'suggestion',key};},
 blurOcrSuggestion(e){const key=e.currentTarget.dataset.key;if(this.ocrFocus&&this.ocrFocus.kind==='suggestion'&&this.ocrFocus.key===key)this.ocrFocus=null;if(this.ocrDeferredFocusedKey===key){this.ocrDeferredFocusedKey=null;if(!Object.prototype.hasOwnProperty.call(this.ocrSuggestionEdits||{},key)&&this.ocrCurrent(this.ocrCapture))return this.readOcr();}},
 blur(e){const path=e.currentTarget.dataset.path;if(this.ocrFocus&&this.ocrFocus.kind==='field'&&this.ocrFocus.path===path)this.ocrFocus=null;if(path!=='contact_info.mobile_phone')return;this.setData({mobilePhoneTouched:true});this.refresh();},
 selectDocumentType(e){if(this.data.pending||!this.data.canEditWechat)return;const group=this.data.materialGroups.find(g=>g.docPath===e.currentTarget.dataset.path);if(group)group.path=group.docPath;const value=form.docs[Number(e.detail.value)];if(!group||!value)return;form.put(this.profile,group.path,value);const options={...this.data.options};if(group.path==='subject_info.identity_info.id_doc_type')options.doc=value;this.setData({options,dirty:true});this.refresh();},
 choice(e){const field=this.data.fields[Number(e.currentTarget.dataset.index)];if(!field||!field.choices)return;const value=field.choices[Number(e.detail.value)];if(field.path==='bank_account_info.bank_account_type'&&(!value||!form.bankAccountChoices(this.data.options.entity).includes(value))){this.setData({status:'请按实际开户主体选择结算账户类型；原账户类型、户名和账号均已保留'});return;}form.put(this.profile,field.path,value);const options={...this.data.options};if(field.path==='contact_info.contact_type'){this.switchContactName(value);options.contact=value;}if(field.path==='subject_info.identity_info.id_doc_type')options.doc=value;this.setData({dirty:true,options});if(field.path==='bank_account_info.bank_account_type'){if(value==='BANK_ACCOUNT_TYPE_PERSONAL'&&!form.get(this.profile,'bank_account_info.account_name')){const reuse=form.personalAccountReuse(this.profile,options);if(!reuse.missing&&!reuse.conflict&&!reuse.sourceConflict){form.put(this.profile,'bank_account_info.account_name',reuse.sourceValue);if(!this.reusedFieldLinks)this.reusedFieldLinks={};this.reusedFieldLinks['bank_account_info.account_name']=reuse.sourceValue;}}this.setData({status:'已按你的选择更新本地账户类型；请核对实际开户主体、户名和账号后保存，原已填写的户名和账号未替换'});}this.refresh();},
 condition(e){if(this.data.pending||!this.data.canEditPlatform)return;const key=e.currentTarget.dataset.key;if(key==='entity'){const previous=form.get(this.profile,'subject_info.ubo_info_list');if(previous)this.inactiveUboList=JSON.parse(JSON.stringify(previous));if(Number(e.detail.value)===0&&this.inactiveUboList)form.put(this.profile,'subject_info.ubo_info_list',JSON.parse(JSON.stringify(this.inactiveUboList)));}const values=key==='entity'?['ENTERPRISE','SOLE_PROPRIETOR']:key==='contact'?['LEGAL','SUPER']:key==='category'?['GENERAL','FOOD']:key==='ubos'?['unknown',0,1,2,3,4]:key==='uboIndex'?[0,1,2,3]:['unknown','store','mini','both'];if(key==='contact')this.switchContactName(values[Number(e.detail.value)]);if(key==='entity'&&values[Number(e.detail.value)]!==this.data.options.entity){if(this.data.canEditWechat)this.clearIndustryRule();else this.setData({status:'微信资料当前只读，原结算配置已保留；主体变化须在微信资料退回补正后重新核定。'});}this.setData({dirty:true,options:{...this.data.options,[key]:values[Number(e.detail.value)],...(key==='entity'&&Number(e.detail.value)===0&&this.data.options.ubos==='not_applicable'?{ubos:'unknown'}:{})},fieldCursor:0});if(key==='entity'&&this.data.canEditWechat){const error=form.bankAccountTypeError(this.data.options.entity,form.get(this.profile,'bank_account_info.bank_account_type'));if(error)this.setData({status:error});}this.refresh();},
 privateOcrDraftUpdates(){const updates={};for(const field of flatten(this.projectOcrGroups(this.data.materialGroups||[]).map(g=>g.fields||[]))){const explicitEmpty=field.value===''&&this.ocrExplicitEmptyFields&&this.ocrExplicitEmptyFields[field.path]&&this.ocrDrafts&&this.ocrDrafts[field.ocrDocument]&&Object.prototype.hasOwnProperty.call(this.ocrDrafts[field.ocrDocument].fields||{},field.ocrKey);if((!field.ocrSuggestion&&!explicitEmpty)||!field.ocrDocument||!field.ocrKey||typeof field.value!=='string')continue;if(field.ocrDocument===this.data.ocrKind&&this.data.ocrConfirmed)continue;const kind=field.ocrDocument;if(!updates[kind])updates[kind]={fields:{}};updates[kind].fields[field.ocrKey]=field.value;}return updates;},
 startFreshDraft(){
 const app=this.data.application,s=this.session;
 if(this.freshIntent||freshNavigation||!this.current()||!this.data.ready||!this.data.canEditPlatform||
    this.data.pending||this.data.dirty||this.ocrFlight||!app||app.status!=='DRAFT'||!s)return;
 const intent={session:s,epoch:this.epoch,generation:freshGeneration(s),scene:this.scene,application:app.application,revision:app.revision,phase:'NAVIGATING'};
 freshNavigation=intent;
 wx.navigateTo({url:'/pages/merchant-join/index?freshDraft=1'+(this.scene?'&scene='+encodeURIComponent(this.scene):''),fail:()=>{if(freshNavigation===intent&&intent.phase==='NAVIGATING')freshNavigation=null;}});
 },
 returnFreshDraft(){if(!this.freshIntent||this.data.pending)return;if(this.data.dirty){this.setData({status:'请先保存新草稿的修改再返回，或使用原返回并取消修改。'});return;}wx.navigateBack({delta:1});},
 async freshCreate(old,invoke){
 const i=this.freshIntent;if(old||!i)return invoke();
 if(i.phase!=='BLANK'||!freshSame(this,i))throw Error('尚不能另开新草稿；请返回原草稿。');
 i.phase='PENDING';
 try{
  const a=await invoke();
  if(!a||a.status!=='DRAFT'||a.revision!==1||typeof a.application!=='string'||!a.application||
    a.application===i.application||!a.materials||Object.keys(a.materials).length)throw Error('新草稿保存结果待核实');
  i.phase='KNOWN';i.saved=a.application;return a;
 }catch(e){i.phase='UNKNOWN';this.setData({canEditPlatform:false,canEditWechat:false,freshUnknown:true,status:'新草稿保存结果待核实，不会自动重试。'});throw e;}
 },
 async saveDraft(binding){const saveCurrent=()=>this.current()&&(!binding||binding.current());if(!saveCurrent())return;this.providerParameterFeedbackLoad=null;this.setData({providerParameterFeedback:null});const ocrDraftUpdates=this.privateOcrDraftUpdates();if(!this.data.ready||!this.session)throw Error('SESSION_EXPIRED');const o=this.data.options;if(this.data.canEditWechat){fillReceivingMiniAppid(this.profile,o);this.fillPersonalAccountName();}const scenes=o.scene==='unknown'?null:[...(['mini','both'].includes(o.scene)?['SALES_SCENES_MINI_PROGRAM']:[]),...(['store','both'].includes(o.scene)?['SALES_SCENES_STORE']:[])];if(scenes)form.put(this.profile,'business_info.sales_info.sales_scenes_type',scenes);else if((this.profile.business_info&&this.profile.business_info.sales_info))delete this.profile.business_info.sales_info.sales_scenes_type;form.put(this.profile,'contact_info.contact_type',o.contact);form.put(this.profile,'subject_info.identity_info.id_doc_type',o.doc);form.put(this.profile,'subject_info.subject_type',o.entity==='ENTERPRISE'?'SUBJECT_TYPE_ENTERPRISE':'SUBJECT_TYPE_INDIVIDUAL');if(o.entity!=='ENTERPRISE'||o.ubos!== 'unknown'&&!Number(o.ubos)){if(this.profile.subject_info)delete this.profile.subject_info.ubo_info_list;}else if(o.entity==='ENTERPRISE'&&o.ubos!=='unknown') {const list=form.get(this.profile,'subject_info.ubo_info_list')||[];form.put(this.profile,'subject_info.ubo_info_list',Array.from({length:Number(o.ubos)},(_,i)=>list[i]||{}));}for(const group of form.materialGroups(this.profile,o,this.data.materials,0)){if(group.docPath&&!form.get(this.profile,group.docPath))form.put(this.profile,group.docPath,form.docs[group.docValue]);}if(this.data.canEditWechat){if(!this.reusedFieldLinks)this.reusedFieldLinks={};form.syncReusedFields(this.profile,o,this.reusedFieldLinks);}const old=this.data.application;
 if(binding&&binding.progress)binding.progress('保存平台草稿');
 const app=old&&!this.data.canEditPlatform&&!['DRAFT','CORRECTION_REQUIRED'].includes(old.status)?old:await this.freshCreate(old,()=>this.request('save',{application:old?old.application:null,revision:old?old.revision:0,fields:form.platformFields(this.profile),entity_type:o.entity,category:o.category||'GENERAL',delegated:o.contact==='SUPER',identity_type:o.doc,...(scenes?{sales_scenes_type:scenes}:{}),declarations:{scene:o.scene,ubos:o.entity==='ENTERPRISE'?o.ubos:'not_applicable'}},false,!!(binding&&binding.skipDonationDraft)));if(!saveCurrent())return;if(binding&&!binding.accept(app,old))return;if(old&&app&&old.status===app.status)this.advanceDirectOcrHints('',old,app,null);this.setData({application:app});if(!this.data.canEditWechat){this.setData({dirty:false,status:'原申请资料已保存；微信资料当前只读'});return app;}if(binding&&binding.progress)binding.progress('保存微信资料草稿');const record=await this.request('wechat_save',{application:app.application,expected_version:this.version,profile:settlementProfileForSave(this.profile),...(this.miniLiveEdited?{mini_program_live:this.data.options.miniLive===true}:{}),...(Object.keys(ocrDraftUpdates).length?{ocr_drafts:ocrDraftUpdates,application_revision:app.revision}:{})},!!(binding&&binding.skipDonationDraft));if(!saveCurrent())return;this.version=record.version;if(binding&&typeof binding.readback==='function')binding.readback(this.createSubmitReadback(app,record));if(binding&&binding.deferReload===true)return app;const savedPosition={step:this.data.step,fieldCursor:this.data.fieldCursor,cursorPath:this.data.cursorPath,materialCursor:this.data.materialCursor};await this.load(app.application,saveCurrent);if(saveCurrent()){this.setData(savedPosition);this.refresh();return app;}},
 save(){return this.run(()=>this.saveDraft());},
 stepOcrReviewRows(){const byKind={};for(const group of this.projectOcrGroups(this.data.materialGroups||[]))for(const field of group.fields||[]){const kind=field.ocrDocument,key=field.ocrKey,draft=kind&&this.ocrDrafts&&this.ocrDrafts[kind];if(!kind||!key||typeof field.value!=='string'||!(field.ocrSuggestion||draft&&draft.fields&&Object.prototype.hasOwnProperty.call(draft.fields,key)))continue;if(kind===this.data.ocrKind&&this.data.ocrConfirmed&&!draft)continue;if(!byKind[kind])byKind[kind]={kind,title:({business_license:'营业执照',id_front:'身份证人像面',id_back:'身份证国徽面',bank_card:'银行卡'})[kind],group:group.id,source:this.ocrSource(kind),fields:[]};byKind[kind].fields.push({key,path:field.path,label:field.label,value:field.value,required:field.required===true});}return Object.values(byKind);},
 stepOcrPendingIntent(){const app=this.data.application;return [this.ocrCapture,...Object.values(this.ocrHeldCaptures||{}),...Object.values(this.ocrDisplayCaptures||{})].find(c=>c&&app&&c.application===app.application&&c.session===this.session&&(c.recovery_apply_pending||c.pending_confirmation||c.recovery_confirmation&&!c.recovery_confirmation_revision));},
 stepOcrReviewCurrent(intent){const app=this.data.application;return !!intent&&this.current()&&!this.ocrHidden&&this.data.canEditWechat&&this.session&&this.session.isAuthenticated()&&this.session===intent.session&&this.session.getGeneration()===intent.session_generation&&this.scene===intent.scene&&app&&app.application===intent.application&&app.revision===intent.revision&&this.version===intent.version&&this.data.step===intent.step&&sameOcrView(this.stepOcrReviewRows(),intent.rows);},
 cancelStepOcrReview(){this.stepOcrRender=(this.stepOcrRender||0)+1;this.stepOcrReviewIntent=null;this.stepOcrEditIntent=null;this.setData({stepOcrReview:[]});},
 presentStepOcrReview(){
  if(this.data.pending)return;
  const serial=this.stepOcrRender=(this.stepOcrRender||0)+1;this.stepOcrReviewIntent=null;this.stepOcrEditIntent=null;
  const rows=this.stepOcrReviewRows(),app=this.data.application;
  if(!this.current()||this.ocrHidden||this.data.step>=3||!this.data.ready||!this.data.canEditWechat||!app||!this.session||typeof this.session.getGeneration!=='function'||typeof this.session.isAuthenticated!=='function'||!this.session.isAuthenticated()||!rows.length){this.setData({stepOcrReview:[]});return;}
  const intent={session:this.session,session_generation:this.session.getGeneration(),scene:this.scene,application:app.application,revision:app.revision,version:this.version,step:this.data.step,rows:JSON.parse(JSON.stringify(rows))};
  this.stepOcrEditIntent=intent;
  // All approved values are expanded, editable and rendered before the one save action.
  this.setData({stepOcrReview:rows},()=>{if(this.stepOcrRender===serial&&this.stepOcrReviewCurrent(intent))this.stepOcrReviewIntent=intent;});
 },
 reviewAndNext(){if(this.data.pending)return;if(this.showApplicantSessionRecovery())return;if(this.stepOcrPendingReview)return this.confirmStepOcrReview();if(this.ocrFlight){this.setData({status:'原识别请求正在读取中，资料未覆盖；完成后可保存本页。'});return;}if(this.stepOcrPendingIntent()){this.setData({status:'原核对或保存结果尚未确定，已保留原请求和草稿；请等待原回执，勿再次确认或上传。'});return;}const rows=this.stepOcrReviewRows();if(!rows.length||!this.data.canEditWechat)return this.next();if(!this.stepOcrReviewCurrent(this.stepOcrReviewIntent)){this.presentStepOcrReview();this.setData({status:'本页资料刚发生变化，已展开当前准确值；请看过后再保存，未确认任何新内容。'});return;}this.stopOcrPoll();this.clearUploadedOcrRestoreTimer();return this.confirmStepOcrReview();},
 editStepOcrReview(e){if(this.data.pending)return;const path=e.currentTarget.dataset.path;if(!this.stepOcrEditIntent||!this.stepOcrEditIntent.rows.some(g=>g.fields.some(f=>f.path===path)))return this.inputUnifiedField(e);if(!this.stepOcrReviewCurrent(this.stepOcrEditIntent))return;const document=this.stepOcrEditIntent.rows.find(g=>g.fields.some(f=>f.path===path)),field=document.fields.find(f=>f.path===path),draft=this.ocrDrafts&&this.ocrDrafts[document.kind];
 const i=this.stepOcrEditIntent;this.stepOcrCorrections=this.stepOcrCorrections||{};
 let edits=this.stepOcrCorrections[document.kind];
 if(!edits||edits.application!==i.application||edits.revision!==i.revision||edits.version!==i.version||
    edits.session!==i.session||edits.generation!==i.session_generation||edits.source!==document.source)
  edits=this.stepOcrCorrections[document.kind]={application:i.application,revision:i.revision,version:i.version,
    session:i.session,generation:i.session_generation,source:document.source,fields:{}};
 const earlier=edits.fields[field.key];
 edits.fields[field.key]={before:earlier&&earlier.value===field.value?earlier.before:field.value,value:e.detail.value};if(this.ocrFreshReview&&this.ocrFreshReview[document.kind]){const fresh=this.ocrFreshReview[document.kind];fresh.fields={...fresh.fields,[field.key]:e.detail.value};}if(draft&&draft.fields&&Object.prototype.hasOwnProperty.call(draft.fields,field.key))draft.fields={...draft.fields,[field.key]:e.detail.value};this.stepOcrRender=(this.stepOcrRender||0)+1;this.stepOcrReviewIntent=null;this.inputUnifiedField(e);this.refresh();this.presentStepOcrReview();},
 async confirmStepOcrReview(){
  if(this.data.pending||this.ocrFlight||this.showApplicantSessionRecovery())return;
  const resumed=this.stepOcrPendingReview;
  const intent=resumed?resumed.intent:this.stepOcrReviewIntent;
  if(!resumed&&(!this.stepOcrReviewCurrent(intent)||this.stepOcrPendingIntent())){
   this.cancelStepOcrReview();this.setData({status:'资料已变化，请核对当前资料。未保存新的识别结果。'});return;
  }
  if(!intent)return;
  const session=intent.session;
  const stable=()=>this.current()&&!this.ocrHidden&&this.session===session&&session.isAuthenticated()&&
    session.getGeneration()===intent.session_generation&&this.scene===intent.scene&&
    this.data.application&&this.data.application.application===intent.application&&this.data.step===intent.step;
  if(!stable())return;
  const missing=flatten(intent.rows.map(g=>g.fields.filter(f=>f.required&&!f.value.trim()).map(f=>({group:g.group,field:f}))));
  if(!resumed&&missing.length){const first=missing[0];this.setData({missingFieldPath:first.field.path,editMaterialGroup:first.group,status:'请补齐本页必填资料，再核对保存。'});this.refresh();return;}
  let complete=false;
  await this.run(async()=>{
   const userError=message=>{const error=Error(message);error.contactValidation=true;return error;};
   let batch=resumed&&resumed.batch;
   if(!batch){
    // Save non-OCR manual edits through the same original action as before.
    // Refresh the exact binding afterwards; never confirm an older OCR job.
    const before=this.data.application.revision,beforeProvider=this.version;
    const evidence={};
    for(const approved of intent.rows){
     const fresh=this.ocrFreshReview&&this.ocrFreshReview[approved.kind];
     if(fresh&&fresh.application===intent.application&&fresh.revision===before&&fresh.version===beforeProvider&&fresh.source===approved.source)
      evidence[approved.kind]=fresh.original_fields;
     const recorded=this.stepOcrCorrections&&this.stepOcrCorrections[approved.kind];
     const exact=recorded&&recorded.application===intent.application&&recorded.revision===before&&recorded.version===beforeProvider&&
       recorded.session===intent.session&&recorded.generation===intent.session_generation&&recorded.source===approved.source;
     if(exact){
      const checked=toObject(approved.fields.filter(f=>recorded.fields[f.key]&&recorded.fields[f.key].value===f.value)
        .map(f=>[f.key,recorded.fields[f.key].before]));
      if(Object.keys(checked).length)evidence[approved.kind]={...checked,...(evidence[approved.kind]||{})};
     }
    }
    this.acceptDisplayedDirectOcr();
    if(this.data.dirty||this.miniLiveEdited)await this.saveDraft();
    if(!stable())return;
    const revision=this.data.application.revision,version=this.version;
    const current=()=>stable()&&this.data.application.revision===revision&&this.version===version;
    const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
    const call=async(action,p)=>{
     let attempt=0;
     while(current()){
      try{return await this.ocrCall(action,p);}
      catch(error){const closed=error&&error.ocrDiagnostic&&error.ocrDiagnostic.retryable===false;
       if(closed||!error||!error.networkKind&&error.ocrCode!=='OCR_REQUEST_PENDING')throw error;
       await pause([1000,2000,4000,8000][Math.min(3,attempt++)]);
      }
     }
     throw userError('当前资料已变化。未写入识别结果。');
    };
    this.setData({status:'正在读取当前版本的识别结果，完成后会核对并保存。'});
    const docs=[];
    for(const approved of intent.rows){
     if(!current()||this.ocrSource(approved.kind)!==approved.source)throw userError('证照已变化，请重新核对。未写入识别结果。');
     const shown=this.stepOcrReviewRows().find(g=>g.kind===approved.kind);
     if((!shown||!sameOcrView(shown,approved))&&!Object.prototype.hasOwnProperty.call(evidence,approved.kind))throw userError('显示内容已变化，请重新核对。未写入识别结果。');
     let item;
     try{item=await call('locate',{document_type:approved.kind,locator:{current_material:true}});}
     catch(error){
      const d=error&&error.ocrDiagnostic;
      if(!current()||!d||d.stage!=='RESULT_READ'||d.reason!=='MATERIAL_JOB_NOT_FOUND'||d.retryable!==false||d.request_retained!==false)throw error;
      const key='mini-first-'+Date.now()+'-'+Math.random().toString(36).slice(2);
      item=await call('submit',{document_type:approved.kind,idempotency_key:key});
     }
     const job=item&&item.result&&item.result.job_id;
     if(typeof job!=='string'||!/^[a-f0-9-]{36}$/.test(job))throw userError('暂时无法读取识别结果。原资料已保留。');
     const read=await call('read',{job_id:job});const result=read&&read.result;
     if(!current()||!result||result.job_id!==job||result.document_type!==approved.kind||
       result.application_revision!==String(revision)||result.provider_version!==version||!['needs_review','confirmed'].includes(result.status))
       throw userError('暂时无法读取当前识别结果。原资料已保留。');
     const fields=toObject(approved.fields.filter(f=>f.value.trim()).map(f=>[f.key,f.value]));
     if(!Object.keys(fields).length)throw userError('请先补齐需要核对的证照资料。');
     if(!Object.keys(fields).every(key=>{
       const suggested=result.status==='confirmed'?result.confirmed_fields&&result.confirmed_fields[key]:result.fields&&result.fields[key]&&result.fields[key].value;
       const anchored=evidence[approved.kind];
       const expected=anchored&&Object.prototype.hasOwnProperty.call(anchored,key)?anchored[key]:fields[key];
       return (typeof suggested==='string'?suggested:null)===expected;
     })){
      // Present the changed result in the existing review, scoped only to
      // this immutable document and current versions. Keep prior draft edits.
      const raw=toObject(approved.fields.map(({key})=>{
       const value=result.status==='confirmed'?result.confirmed_fields&&result.confirmed_fields[key]:result.fields&&result.fields[key]&&result.fields[key].value;
       return [key,typeof value==='string'?value:null];
      }));
      const proposed=toObject(Object.entries(raw).map(([key,value])=>[key,value===null?'':value]));
      this.ocrFreshReview={...(this.ocrFreshReview||{}),[approved.kind]:{application:intent.application,
        revision,version,source:approved.source,fields:proposed,original_fields:raw}};
      this.refresh();this.presentStepOcrReview();
      throw userError('当前识别结果与刚核对的内容不同，新的识别值已展开。请重新核对；原资料未被覆盖。');
     }
     docs.push({document_type:approved.kind,job_id:job,fields});
    }
    if(!current())return;
    batch={application_revision:revision,provider_version:version,docs,review_key:'mini-review-'+Date.now()+'-'+Math.random().toString(36).slice(2)};
    this.stepOcrPendingReview={intent,batch};
   }
   try{
    const r=await this.ocrCall('review_current',batch);
    if(!stable())return;
    if(!r||!r.result||r.result.saved!==true)throw userError('本次保存结果尚未核实，请重新读取。');
   }catch(error){if(error&&error.ocrDiagnostic&&error.ocrDiagnostic.retryable===false)this.stepOcrPendingReview=null;throw error;}
   const readback=await this.load(intent.application,stable);if(!stable())return;
   if(!readback||readback.application!==intent.application||!readback.record)
    throw userError('已收到保存回执，当前草稿暂未读取。再次点击只核对同一笔回执，不重复写入。');
   this.stepOcrPendingReview=null;this.ocrFreshReview=null;this.stepOcrCorrections=null;
   this.cancelStepOcrReview();
   complete=true;this.setData({status:'已核对并保存本页识别资料；未提交微信。'});
  },'本人核对并保存');
  if(complete&&stable())this.showStepTop(Math.min(3,intent.step+1));
 },
 next(){return this.run(async()=>{const step=this.data.step;if(this.ocrFlight){this.setData({status:'原识别请求仍在处理中，草稿未覆盖，请稍候再保存下一步。'});return;}if(this.data.ocrConfirmed&&this.data.canEditWechat)await this.fillConfirmedOcrDraft();if(!this.current())return;if(this.ocrCapture&&this.ocrCapture.recovery_apply_pending){this.setData({status:'保存结果暂未确认，正在查询原保存回执；已保留草稿，请勿重复提交。'});return;}this.acceptDisplayedDirectOcr();const waiting=flatten(this.projectOcrGroups(this.data.materialGroups).map(g=>g.fields||[])).filter(f=>f.ocrSuggestion&&f.ocrResultPresent);if(this.data.canEditPlatform||this.data.canEditWechat)await this.saveDraft();if(this.current()){this.setData({status:waiting.length?'草稿已保存；以下识别资料待本人核对，尚未提交微信：'+waiting.map(f=>f.label||f.path).join('、'):'本步资料已保存到同一申请；最后提交时统一处理，尚未发送微信。'});this.showStepTop(Math.min(3,step+1));}},'保存资料');},
 showStepTop(step){if(!this.current())return;const transition=this.beginStepScroll();this.setData({step,fieldCursor:0});this.refresh(()=>this.finishStepScroll(transition,step,{scrollTop:0,duration:0}));},
 nextField(){if(this.data.pending)return;const fields=this.data.fields;const current=fields[this.data.fieldCursor];const increment=current&&current.path==='bank_account_info.bank_branch_id'?2:1;const cursor=this.data.fieldCursor+increment;if(cursor<fields.length){this.setData({fieldCursor:cursor,cursorPath:fields[cursor].path});this.refresh();}},
 previousField(){if(this.data.pending)return;const fields=this.data.fields;let cursor=Math.max(0,this.data.fieldCursor-1);if(fields[cursor]&&fields[cursor].path==='bank_account_info.bank_name')cursor=Math.max(0,cursor-1);this.setData({fieldCursor:cursor,cursorPath:fields[cursor]?fields[cursor].path:''});this.refresh();},
 nextMaterial(){if(this.data.pending)return;const cursor=this.data.materialCursor+1;if(cursor<this.data.materials.length)this.setData({materialCursor:cursor});},
 previousMaterial(){if(this.data.pending)return;this.setData({materialCursor:Math.max(0,this.data.materialCursor-1)});},
 officialFieldView(){const options=officialFields.industriesFor(this.data.options.entity),selected=officialFields.selectedIndustry(this.data.options.entity,this.profile),code=form.get(this.profile,'business_info.sales_info.biz_store_info.biz_address_code'),region=officialFields.regionForCode(code)||officialFields.regionColumns(),derived=form.regionReuse(this.profile),matched=derived.resolution.ok&&code===derived.resolution.code;return {regionResolved:matched,regionRetained:!!officialFields.regionForCode(code),regionResolutionMessage:derived.conflict?'营业执照地区与原申请地区不同，原编码已保留，请确认后再采用第一步资料。':!derived.resolution.ok?derived.resolution.message:!matched?'地区已匹配，保存草稿时写入原申请。':'',platformAppidStatus:(form.get(this.profile,'business_info.sales_info.mini_program_info.mini_program_appid')||form.get(this.profile,'business_info.sales_info.mini_program_info.mini_program_sub_appid'))?'原申请 AppID 已保留；请核对使用授权及微信绑定条件':'当前运行小程序不会自动用于进件；请仅填写本申请获准使用的 AppID',industryLabels:['请选择实际经营行业',...options.map(x=>x.ui_label),'其他行业（按真实业务填写）'],industryValue:selected?options.indexOf(selected)+1:(this.industryOtherSelected||form.get(this.profile,'settlement_info.qualification_type')?options.length+1:0),industryCustom:!selected&&!!(this.industryOtherSelected||form.get(this.profile,'settlement_info.qualification_type')),industryActualName:form.get(this.profile,'settlement_info.qualification_type')||'',industrySubjectLabel:this.data.options.entity==='ENTERPRISE'?'企业':this.data.options.entity==='SOLE_PROPRIETOR'?'个体工商户':'请先确认主体类型',industryHint:selected?'按所选主体和行业匹配；'+(selected.condition||'具体经营资质仍须按微信规则核验。'):form.get(this.profile,'settlement_info.settlement_id')?'已有结算资料保留；当前行业尚未匹配，不能擅自覆盖。':'按实际经营选择，无默认行业或费率。',regionColumns:region.columns,regionIndices:region.indices,regionLabel:code?(officialFields.regionForCode(code)?region.row.slice(1).join(' / '):'原地区资料已保留，请核对官方地区选择'):'请选择实际经营地区'};},
 addIndustryMaterialSlot(){if(this.data.pending||!this.data.canEditPlatform)return;const group=this.data.materialGroups.find(g=>g.id==='qualification');if(!group||!group.industryCanAdd)return;this.setData({options:{...this.data.options,industrySlotCount:group.materials.length+1}});this.refresh();},
 industryQualificationUiKey(app=this.data.application,profile=this.profile){return JSON.stringify([app&&app.application,this.data.options.entity,form.get(profile,'settlement_info.settlement_id'),form.get(profile,'settlement_info.qualification_type')]);},
 chooseIndustryQualificationCondition(e){if(this.data.pending||!this.data.canEditWechat)return;const value=e.currentTarget.dataset.applies;if(!['yes','no'].includes(value))return;if(!this.industryConditionChoices)this.industryConditionChoices={};this.industryConditionChoices[this.industryQualificationUiKey()]=value==='yes';this.setData({options:{...this.data.options,industryQualificationApplies:value==='yes',industrySlotCount:1},status:value==='yes'?'已按实际业务选择条件适用，请提供对应资质；最终由原审核核验。':'已选择该条件不适用；原文件保留，不代表平台或微信已确认免交。'});this.refresh();},
 clearIndustryRule(){this.industryConditionChoices={};this.setData({options:{...this.data.options,industryQualificationApplies:undefined,industrySlotCount:1},status:'行业已变更，原资质文件保留；须按新行业条件重新核对，不沿用原适用结论。'});const info=this.profile.settlement_info;if(!info)return;delete info.settlement_id;for(const key of ['activities_id','activities_rate','debit_activities_rate','credit_activities_rate'])delete info[key];},
 chooseIndustry(e){if(this.data.pending||!this.data.canEditWechat)return;const rows=officialFields.industriesFor(this.data.options.entity),index=Number(e.detail.value)-1,row=rows[index];if(!Number.isInteger(index)||index<0||index>rows.length)return;
  if(!row){if(this.data.industryCustom)return;this.clearIndustryRule();form.put(this.profile,'settlement_info.qualification_type','');this.industryOtherSelected=true;this.setData({dirty:true,industryCustom:true,industryActualName:'',industryHint:'请填写实际经营行业；当前未匹配官方规则，可保存草稿但不能提交，不会沿用旧行业配置。'});this.refresh();return;}
  const old=officialFields.selectedIndustry(this.data.options.entity,this.profile);if(!old||old.qualification_type!==row.qualification_type)this.clearIndustryRule();form.put(this.profile,'settlement_info.settlement_id',row.settlement_id);form.put(this.profile,'settlement_info.qualification_type',row.qualification_type);this.industryOtherSelected=false;this.setData({dirty:true});this.refresh();
 },
 inputIndustry(e){if(this.data.pending||!this.data.canEditWechat||typeof e.detail.value!=='string')return;this.clearIndustryRule();form.put(this.profile,'settlement_info.qualification_type',e.detail.value);this.industryOtherSelected=true;this.setData({dirty:true});this.refresh();},
 changeRegionColumn(e){if(this.data.pending||!this.data.canEditWechat)return;const indices=[...(this.data.regionIndices||[0,0,0])],column=Number(e.detail.column),value=Number(e.detail.value);if(!Number.isInteger(column)||column<0||column>2||!Number.isInteger(value)||value<0)return;indices[column]=value;for(let i=column+1;i<3;i++)indices[i]=0;const next=officialFields.regionColumns(indices);this.setData({regionColumns:next.columns,regionIndices:next.indices});},
 chooseRegion(e){if(this.data.pending||!this.data.canEditWechat||!Array.isArray(e.detail.value)||e.detail.value.length!==3||e.detail.value.some(x=>!Number.isInteger(x)||x<0))return;const selected=officialFields.regionColumns(e.detail.value);if(selected.indices.some((x,i)=>x!==e.detail.value[i]))return;form.put(this.profile,'business_info.sales_info.biz_store_info.biz_address_code',selected.row[0]);this.setData({dirty:true});this.refresh();},
 toggleMaterialEdit(e){const id=e.currentTarget.dataset.group;if(this.data.pending||!this.data.canEditWechat||!this.data.materialGroups.some(g=>g.id===id))return;if(this.data.editMaterialGroup===id)this.ocrFocus=null;this.setData({editMaterialGroup:this.data.editMaterialGroup===id?'':id});},
 toggleOptional(){this.setData({showOptionalMaterials:!this.data.showOptionalMaterials});},
 async goToSubmitIssue(e){const issue=this.data.submitIssues[Number(e.currentTarget.dataset.index)];if(!issue||this.data.pending)return;const kind=Object.keys(this.ocrDrafts||{}).find(k=>this.ocrPathKey(issue.path,k));const session=this.session,application=this.data.application&&this.data.application.application,scene=this.scene;const current=()=>this.current()&&this.session===session&&this.scene===scene&&(this.data.application&&this.data.application.application)===application;if(kind&&this.data.dirty){await this.run(()=>this.saveDraft({current,accept:()=>current()}));if(!current()||this.data.dirty)return;}if(!current())return;this.setData({missingFieldPath:issue.path,editMaterialGroup:issue.group,status:issue.message});const transition=this.beginStepScroll();this.setData({step:issue.step,fieldCursor:0});this.refresh(()=>{const index=this.data.fields.findIndex(f=>f.path===issue.path);const hidden=['business_info.sales_info.biz_store_info.biz_address_code','bank_account_info.bank_branch_id'].includes(issue.path);const selector=index>=0&&!hidden?'#missing-field-'+index:'#material-'+issue.group;this.finishStepScroll(transition,issue.step,{selector,duration:180});});if(kind)return this.reviewSavedOcrIssue(kind,issue);},
 async reviewSavedOcrIssue(kind,issue){return this.run(async()=>{if(this.data.dirty){this.setData({status:'本页修改仍保留，请先保存，再核对已保存的识别资料。'});return;}const app=this.data.application;if(!app||!this.ocrSource(kind))return;const held=this.ocrCapture&&this.ocrCapture.document_type===kind?this.ocrCapture:this.retainedOcrCapture(kind);const previous=held&&held.source===this.ocrSource(kind)?held:{application:app.application,revision:app.revision,document_type:kind,source:this.ocrSource(kind),session:this.session,session_generation:this.session.getGeneration(),scene:this.scene,job_id:'',idempotency_key:'',original_locator:{current_material:true}};await this.recoverCurrentDocument(previous);if(this.ocrCapture&&this.ocrCapture.recovery_apply_pending)return;if(!this.current()||this.data.application.application!==app.application||this.data.step!==issue.step||this.data.ocrKind!==kind)return;this.setData({editMaterialGroup:issue.group,status:'识别草稿已保存。请核对本证照的显示内容，点击“确认已核对并保存”即可，无需重新上传。'});const transition=this.beginStepScroll();this.refresh(()=>this.finishStepScroll(transition,issue.step,{selector:'#ocr-review-'+issue.group,duration:180}));});},
 returnMaterial(e){const step=Number(e.currentTarget.dataset.step),group=e.currentTarget.dataset.group;if(!Number.isInteger(step)||step<0||step>2)return;const transition=this.beginStepScroll();this.setData({step,fieldCursor:0});this.refresh(()=>this.finishStepScroll(transition,step,{selector:'#material-'+group,duration:180}));},
 back(){if(this.data.pending)return;this.showStepTop(Math.max(0,this.data.step-1));},
 beginStepScroll(){this.ocrFocus=null;this.stepScrollGeneration=(this.stepScrollGeneration||0)+1;return this.stepScrollGeneration;},
 finishStepScroll(transition,step,options){if(!this.current()||this.ocrHidden||transition!==this.stepScrollGeneration||this.stepScrollCompleted===transition||this.data.step!==step)return;this.stepScrollCompleted=transition;if(typeof wx.pageScrollTo==='function')wx.pageScrollTo(options);},
 copySigning(){return copySigning(this,wx);},
 clearSigningPreviewFile(){
  const path=this.signQrPreviewFile;this.signQrPreviewFile=null;this.signQrPreviewActive=null;
  if(path&&typeof wx.getFileSystemManager==='function'){try{wx.getFileSystemManager().unlink({filePath:path,success:()=>{},fail:()=>{}});}catch(_){}}
 },
 invalidateSigningQrForHide(){
  const active=this.signQrPreviewActive;
  const preserve=active&&active.path===this.signQrPreviewFile&&active.current()?active.path:null;
  this.invalidateSigningQr(preserve);
 },
 previewSigningQr(){
  if(!this.current()||!this.session||!this.data.application)return;
  const value=this.data.signQrImage,match=typeof value==='string'&&/^data:image\/png;base64,(iVBORw0KGgo[A-Za-z0-9+/]*={0,2})$/.exec(value);
  if(!match||value.length>1000000||!wx.env||typeof wx.env.USER_DATA_PATH!=='string'||typeof wx.getFileSystemManager!=='function'){
   this.setData({signQrStatus:'当前二维码无法安全预览，仍可复制原官方链接；未进行签约操作。'});return;
  }
  const application=this.data.application.application,session=this.session,epoch=this.epoch,scene=this.scene,version=this.version,generation=this.signQrGeneration;
  const current=()=>this.current()&&this.session===session&&this.epoch===epoch&&this.scene===scene&&this.version===version&&this.signQrGeneration===generation&&this.data.application&&this.data.application.application===application&&this.data.signQrImage===value;
  this.clearSigningPreviewFile();let fs;try{fs=wx.getFileSystemManager();}catch(_){this.setData({signQrStatus:'当前设备无法创建私密预览，请使用复制官方链接。'});return;}
  if(typeof fs.writeFile!=='function'||typeof fs.unlink!=='function'){this.setData({signQrStatus:'当前设备无法创建私密预览，请使用复制官方链接。'});return;}
  this.signQrPreviewSequence=(this.signQrPreviewSequence||0)+1;
  const path=wx.env.USER_DATA_PATH.replace(/\/$/,'')+'/community-signing-preview-'+Date.now()+'-'+this.signQrPreviewSequence+'.png';this.signQrPreviewFile=path;
  const remove=()=>{if(this.signQrPreviewFile===path)this.signQrPreviewFile=null;if(this.signQrPreviewActive&&this.signQrPreviewActive.path===path)this.signQrPreviewActive=null;try{fs.unlink({filePath:path,success:()=>{},fail:()=>{}});}catch(_){}};
  const fail=()=>{remove();if(current())this.setData({signQrStatus:'二维码预览失败，仍可复制原官方链接；未进行签约操作。'});};
  try{fs.writeFile({filePath:path,data:match[1],encoding:'base64',success:()=>{if(!current()||this.signQrPreviewFile!==path){remove();return;}try{this.signQrPreviewActive={path,current};wx.previewImage({urls:[path],current:path,fail});}catch(_){fail();}},fail});}catch(_){fail();}
 },
 invalidateSigningQr(preservePath){if(!preservePath||preservePath!==this.signQrPreviewFile||!this.signQrPreviewActive||this.signQrPreviewActive.path!==preservePath)this.clearSigningPreviewFile();this.signQrGeneration=(this.signQrGeneration||0)+1;this.setData({signQrImage:'',signQrPending:false,signQrStatus:''});},
 async showSigningQr(){
  if(!this.current()||!this.session||!this.data.application||this.data.signQrPending||this.reviewState!=='SUBMITTED_TO_PROVIDER'||
     this.data.wechatState!=='APPLYMENT_STATE_TO_BE_SIGNED')return;
  this.invalidateSigningQr();const generation=this.signQrGeneration;
  const application=this.data.application.application,session=this.session,epoch=this.epoch,scene=this.scene,version=this.version;
  const current=()=>this.signQrGeneration===generation&&this.current()&&this.session===session&&this.epoch===epoch&&this.scene===scene&&this.version===version&&this.data.application&&this.data.application.application===application;
  this.setData({signQrPending:true,signQrImage:'',signQrStatus:'正在读取本申请已核验的签约二维码'});
  try{
   const r=await this.request('wechat_owner_sign_qr',{application,qr_format:'WECHAT_OFFICIAL'});
   if(!current()||this.reviewState!=='SUBMITTED_TO_PROVIDER'||this.data.wechatState!=='APPLYMENT_STATE_TO_BE_SIGNED')return;
   if(!r||r.application!==application||typeof r.applyment_id!=='string'||!/^\d{1,32}$/.test(r.applyment_id)||r.provider_state!=='APPLYMENT_STATE_TO_BE_SIGNED'||r.qr_source!=='WECHAT_OFFICIAL'||r.qr_available!==true||typeof r.png_data!=='string'||r.png_data.length>1000000||!/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(r.png_data)||typeof r.url_sha256!=='string'||!/^[a-f0-9]{64}$/.test(r.url_sha256))throw Error('UNVERIFIED_SIGNING_QR_REPLY');
   this.setData({signQrImage:r.png_data,signQrStatus:'请申请单超级管理员在微信中长按识别官方签约码。'});
  }catch(error){if(current())this.setData({signQrImage:'',signQrStatus:'暂未取得微信支付官方签约码。申请仍为待签约。'});}
  finally{if(current())this.setData({signQrPending:false});}
 },
 signingQrImageError(){this.clearSigningPreviewFile();this.setData({signQrImage:'',signQrStatus:'当前设备未能显示微信支付官方签约码，未进行签约操作。'});},

 materialProfilePath(kind){const map={business_license:'subject_info.business_license_info.license_copy',identity_front:'subject_info.identity_info.'+(this.data.options.doc==='IDENTIFICATION_TYPE_IDCARD'?'id_card_info.id_card_copy':'id_doc_info.id_doc_copy'),identity_back:'subject_info.identity_info.'+(this.data.options.doc==='IDENTIFICATION_TYPE_IDCARD'?'id_card_info.id_card_national':'id_doc_info.id_doc_copy_back'),mini_program_screenshot:'business_info.sales_info.mini_program_info.mini_program_pics',storefront_photo:'business_info.sales_info.biz_store_info.store_entrance_pic',interior_photo:'business_info.sales_info.biz_store_info.indoor_pic',operator_identity:'contact_info.contact_id_doc_copy',operator_identity_back:'contact_info.contact_id_doc_copy_back',industry_permit:'settlement_info.qualifications'};let path=map[kind];const ubo=/^ubo_([1-4])_(front|back)$/.exec(kind);if(ubo)path='subject_info.ubo_info_list.'+(Number(ubo[1])-1)+'.ubo_id_doc_'+(ubo[2]==='front'?'copy':'copy_back');return path||'';},
 clearMediaStatusWait(){const wait=this.mediaStatusWait;if(wait){this.mediaStatusWait=null;clearTimeout(wait.timer);wait.resolve();}},
 async resolveCurrentMedia(application,kind,current){
  const session=this.session,scene=this.scene,epoch=this.epoch,providerVersion=this.version,transferIntent=OWNER_WECHAT_CLICK.get(this);
  const revision=this.data.application&&this.data.application.revision;
  const generation=session&&typeof session.getGeneration==='function'?session.getGeneration():null;
  const stale=()=>{const e=Error('原申请或版本已变化；未发送本材料。');e.submitPreflight=true;return e;};
  const unknown=()=>Object.assign(Error('WECHAT_MEDIA_RESULT_UNKNOWN'),{mediaCode:'WECHAT_MEDIA_RESULT_UNKNOWN'});
  const currentAuthorization=()=>current()&&generation!==null&&Number.isSafeInteger(revision)&&revision>0&&
   this.session===session&&this.scene===scene&&this.epoch===epoch&&this.version===providerVersion&&
   session.getGeneration()===generation&&typeof session.isAuthenticated==='function'&&session.isAuthenticated()&&
   this.data.application&&this.data.application.application===application&&this.data.application.revision===revision;
  if(!currentAuthorization()||!transferIntent||OWNER_WECHAT_CLICK.get(this)!==transferIntent||
     transferIntent.application!==application||transferIntent.operationStarted)throw stale();
  const stored=this.data.application.materials;
  if(!stored||!Object.prototype.hasOwnProperty.call(stored,kind)||!stored[kind]||kind==='bank_card')throw stale();
  const issued=transferIntent.mediaIssued||(transferIntent.mediaIssued=new Set());
  if(issued.has(kind))throw unknown();
  issued.add(kind);
  // Original writer uses the saved, authorized source, owns the single-write fence,
  // and returns the provider media_id. No status pre-read or automatic fallback.
  const material=stored[kind],source=material.sha256,foreground=this.providerForeground;
  const materialCurrent=()=>currentAuthorization()&&!this.ocrHidden&&this.providerForeground===foreground&&this.data.application.materials&&this.data.application.materials[kind]===material&&material.sha256===source;
  let result=await this.request('wechat_media',{application,kind,application_revision:revision,owner_confirmed_material_send:true,async_media:true},true);
  if(result&&result.state==='UPLOADING'){
   const expectedSource=result.source_sha256;
   const active=()=>materialCurrent()&&!this.ocrHidden;
   const bound=value=>value&&value.kind===kind&&value.source_sha256===expectedSource&&
    (value.application===undefined||value.application===application)&&
    (value.application_revision===undefined||value.application_revision===revision);
   if(!bound(result)||source!==undefined&&expectedSource!==source||typeof expectedSource!=='string'||!/^[0-9a-f]{64}$/.test(expectedSource))throw unknown();
   while(result.state==='UPLOADING'){
    if(!active())throw unknown();
    await new Promise(resolve=>{this.mediaStatusWait={resolve,timer:setTimeout(()=>this.clearMediaStatusWait(),1000)};});
    if(!active())throw unknown();
    result=await this.request('wechat_media_status',{application,kind,expected_source_sha256:expectedSource},true);
    if(!active()||!bound(result)||!['UPLOADING','READY'].includes(result.state))throw unknown();
   }
  }
  if(!materialCurrent()){if(!current())return null;throw unknown();}
  if(!result||result.state!==undefined&&result.state!=='READY'||result.kind!==kind||typeof result.source_sha256!=='string'||!/^[0-9a-f]{64}$/.test(result.source_sha256)||
     typeof result.media_id!=='string'||result.media_id.length<1||result.media_id.length>1024||
     result.application!==undefined&&result.application!==application||
     result.application_revision!==undefined&&result.application_revision!==revision)throw unknown();
  return result;
 },
 async syncCurrentMaterial(kind,persist,binding){const syncId=this.data.application&&this.data.application.application,syncSession=this.session,syncEpoch=this.epoch,syncScene=this.scene;const syncCurrent=()=>this.current()&&this.scene===syncScene&&this.session===syncSession&&this.epoch===syncEpoch&&(this.data.application&&this.data.application.application)===syncId&&(!binding||binding.current());if(!syncCurrent())return;if(form.industryMaterialKind(kind)&&!this.data.catalog.some(m=>m.id===kind)){this.setData({status:'当前服务未提供此资质槽，未上传或选用；请先核对服务版本。'});return;}if(form.industryMaterialKind(kind)&&this.data.catalog.some(m=>m.id==='industry_permit_2')){
 if(!this.data.catalog.some(m=>m.id===kind)){this.setData({status:'当前服务未提供此资质槽，未上传或选用；请先核对服务版本。'});return;}
 let materialReadCurrent=!!(binding&&binding.materialReadCurrent);if(this.data.dirty||!this.version){await this.saveDraft(binding);if(!syncCurrent())return;materialReadCurrent=false;}
 const id=this.data.application.application,position=this.data.step;
 // The final-submit loop has just read this exact slot; other callers still reload.
 if(!materialReadCurrent)await this.load(id,syncCurrent);if(!syncCurrent())return;
 const app=this.data.application,r=await this.resolveCurrentMedia(id,kind,syncCurrent);if(!syncCurrent())return;
 if(binding&&binding.progress)binding.progress('保存材料关联');
 const record=await this.request('wechat_qualifications_select',{application:id,expected_version:this.version,application_revision:app.revision,kind,media_id:r.media_id,selected:true});if(!syncCurrent())return;
 if(binding&&binding.deferReload===true){this.version=record.version;if(typeof binding.readback==='function')binding.readback(this.createSubmitReadback(app,record));return;}
 await this.load(id,syncCurrent);if(syncCurrent()){this.setData({step:position,status:'本槽资质已选用，其他材料保留；仍须按当前行业规则审核。'});this.refresh();}return;
 }if(kind==='bank_card'){this.setData({status:'银行卡照片已私密保存，请人工填写并核对开户信息。'});return;}if((kind==='cashier_photo'||form.industryMaterialKind(kind))&&(this.data.dirty||!this.version))await this.saveDraft(binding);if(!syncCurrent())return;const app=this.data.application;const r=await this.resolveCurrentMedia(app.application,kind,syncCurrent);if(!syncCurrent())return;if(kind==='cashier_photo'){if(binding&&binding.progress)binding.progress('保存材料关联');await this.request('wechat_cashier_link',{application:app.application,expected_version:this.version,media_id:r.media_id});if(syncCurrent()){const position=this.data.step;await this.load(app.application,syncCurrent);if(syncCurrent())this.setData({step:position,status:'收银台照片已处理'});this.refresh();}return;}const profilePath=this.materialProfilePath(kind);if(!profilePath){this.setData({status:'该选填材料已保存于原申请'});return;}form.put(this.profile,profilePath,/mini_program_pics|store_entrance_pic|indoor_pic|qualifications/.test(profilePath)?[r.media_id]:r.media_id);this.setData({dirty:true,...(!(binding&&binding.progress)?{status:persist?'正在保存申请照片':'照片已处理，正在保存申请资料'}:{})});this.syncLeaveGuard();if(persist)await this.saveDraft(binding);else this.refresh();},
 async removeIndustryMaterial(e){if(this.data.pending||!this.data.application||!this.data.canEditWechat)return;const kind=e.currentTarget.dataset.kind;if(!form.industryMaterialKind(kind)||!this.data.catalog.some(m=>m.id===kind)||!this.data.catalog.some(m=>m.id==='industry_permit_2'))return;return this.run(async()=>{const id=this.data.application.application,session=this.session,epoch=this.epoch,position=this.data.step,current=()=>this.current()&&this.session===session&&this.epoch===epoch&&this.data.application&&this.data.application.application===id;if(this.data.dirty){await this.saveDraft();if(!current())return;}await this.load(id,current);if(!current())return;await this.request('wechat_qualifications_select',{application:id,expected_version:this.version,application_revision:this.data.application.revision,kind,media_id:null,selected:false});if(!current())return;await this.load(id,current);if(current()){this.setData({step:position,status:'已取消本槽选用，原文件及历史保留；其他资质不变。'});this.refresh();}},'资质撤选');},
 async syncMaterial(e){if(!this.data.application)return;const kind=e.currentTarget.dataset.kind;await this.run(()=>this.syncCurrentMaterial(kind,false));},
 async removeCashierPhoto(){if(this.data.pending||!this.data.canEditPlatform||!this.data.application)return;await this.run(async()=>{if(this.data.dirty)await this.saveDraft();if(!this.current())return;const app=this.data.application;await this.request('remove_material',{application:app.application,revision:app.revision,kind:'cashier_photo',expected_wechat_version:this.version});if(this.current()){const step=this.data.step;await this.load(app.application);if(this.current())this.setData({step,status:'收银台当前材料已移除；历史文件和审核记录保留'});this.refresh();}});},
 removeScenePhoto(e){if(this.data.pending||!this.data.canEditWechat)return;const kind=e.currentTarget.dataset.kind;if(!['storefront_photo','interior_photo'].includes(kind))return;const path=this.materialProfilePath(kind);if(!path)return;form.put(this.profile,path,[]);this.setData({dirty:true,status:'已取消选用这张照片，请保存资料；已上传的原照片仍保留'});this.syncLeaveGuard();this.refresh();},
 submitWechatReview(){return this.refreshApplication();},

 waitPickedImageShow(viewToken){
  if(!this.ocrHidden)return Promise.resolve(true);
  if(this.pendingPickerShow)this.pendingPickerShow.finish(false);
  return new Promise(resolve=>{
   const waiter={viewToken,timer:null,finish:shown=>{
    if(this.pendingPickerShow!==waiter)return;
    this.pendingPickerShow=null;clearTimeout(waiter.timer);
    resolve(shown&&this.uploadViewToken===viewToken);
   }};
   this.pendingPickerShow=waiter;
   waiter.timer=setTimeout(()=>waiter.finish(false),5000);
  });
 },
 async upload(e){if(this.data.pending)return;const kind=e.currentTarget.dataset.kind;
 if(isScenePhotoKind(kind)&&!scenePhotoRequired(kind,this.data.options))return;
 await this.run(async()=>{
  this.materialPreviewGeneration=(this.materialPreviewGeneration||0)+1;
  const uploadSession=this.session,uploadEpoch=this.epoch,uploadScene=this.scene,uploadApplication=this.data.application,uploadRevision=uploadApplication&&uploadApplication.revision;
  const uploadProviderVersion=this.version;
  const uploadSessionGeneration=uploadSession&&typeof uploadSession.getGeneration==='function'?uploadSession.getGeneration():null;
  const uploadIdentity=()=>this.current()&&this.session===uploadSession&&this.epoch===uploadEpoch&&this.scene===uploadScene&&
    (!['business_license','identity_front','identity_back','bank_card'].includes(kind)||(!this.ocrHidden&&this.uploadViewToken===viewToken&&
      (uploadSessionGeneration===null||uploadSession.getGeneration()===uploadSessionGeneration)));
  const sameApplication=(expected,revision)=>{const actual=this.data.application;return expected?!!actual&&actual.application===expected.application&&actual.revision===revision:!actual;};
  const uploadAuthorized=()=>uploadIdentity()&&this.data.canEditPlatform&&
   (uploadSessionGeneration===null||uploadSession.getGeneration()===uploadSessionGeneration)&&
   (!uploadSession||typeof uploadSession.isAuthenticated!=='function'||uploadSession.isAuthenticated());
  const uploadCurrent=()=>uploadAuthorized()&&this.version===uploadProviderVersion&&sameApplication(uploadApplication,uploadRevision);
  const pickerTerminal=status=>{if(this.current()&&this.uploadViewToken===viewToken)this.setData({uploadFeedback:null,status});}; const abandonBeforeUpload=()=>{pickerTerminal('当前选图等待已结束或申请状态已变化，照片未上传；请核对原申请。');if(!uploadIdentity())return;if(this.showApplicantSessionRecovery())return;this.setData({status:'当前申请状态已变化，照片未上传；请核对后重新选择。'});};
  let boundApplicationId=uploadApplication?uploadApplication.application:null;
  const binding={current:()=>uploadAuthorized()&&(this.data.application?this.data.application.application:null)===boundApplicationId,accept:(saved,old)=>{if(!binding.current()||!saved||typeof saved.application!=='string'||!saved.application)return false;if(boundApplicationId!==null&&saved.application!==boundApplicationId)return false;if(boundApplicationId===null&&old!==null&&old!==undefined)return false;boundApplicationId=saved.application;return true;}};
  const ocrKind=kind==='business_license'?'business_license':kind==='identity_front'?'id_front':kind==='identity_back'?'id_back':kind==='bank_card'?'bank_card':'';
  const waitsForForeground=['business_license','identity_front','identity_back','bank_card'].includes(kind); const bankOcrKind=kind==='bank_card'?'bank_card':''; const viewToken={};this.uploadViewToken=viewToken;
  let uploadSent=false,uploadConfirmed=false;
  const feedback=(phase,label)=>{if(binding.current()&&this.uploadViewToken===viewToken)this.setData({uploadFeedback:{kind,phase,label}});};
  try{
  let chosen;
  try{chosen=await new Promise((resolve,reject)=>{const options={count:1,sourceType:['album','camera'],success:resolve,fail:reject};let ide=false;try{const info=typeof wx.getDeviceInfo==='function'?wx.getDeviceInfo():typeof wx.getSystemInfoSync==='function'?wx.getSystemInfoSync():null;ide=!!info&&info.platform==='devtools';}catch(_){}if(ide&&typeof wx.chooseImage==='function')wx.chooseImage({...options,sizeType:['original']});else if(typeof wx.chooseMedia==='function')wx.chooseMedia({...options,mediaType:['image'],sizeType:['original']});else wx.chooseImage({...options,sizeType:['original']});});}
  catch(error){pickerTerminal(/cancel/i.test(String(error&&error.errMsg||''))?'已取消选择照片，未上传':'选择照片失败，未上传；请重新选择');return;}
  if(waitsForForeground&&this.ocrHidden&&!await this.waitPickedImageShow(viewToken)){abandonBeforeUpload();return;}
  if(!uploadCurrent()){abandonBeforeUpload();return;}
  const directPickedAt=clientOcrClock();
  const f=chosen.tempFiles&&chosen.tempFiles[0];const originalPath=f&&(f.tempFilePath||f.path)||(chosen.tempFilePaths&&chosen.tempFilePaths[0]);if(!originalPath)throw merchantImageError('IMAGE_INFO_FAILED');
  feedback('preparing','正在处理照片，尚未上传');
  this.setData({materialPreviews:{...this.data.materialPreviews,[kind]:originalPath},status:'已选择照片，正在检查并自动压缩；尚未上传'});
  const originalOnly=!!ocrKind;let prepared;
  try{prepared=await (ocrKind?directOriginal:prepareMerchantImage)(wx,originalPath,uploadCurrent,status=>{if(uploadCurrent()){this.setData({status});feedback('preparing','正在压缩照片，尚未上传');}},originalOnly);}
  catch(error){if(error.directSizeLimit){if(uploadCurrent()){this.setData({status:error.message});feedback('failed',error.message);}return;}if(error.imagePreparation){if(uploadCurrent()){this.setData({status:merchantImageMessage(error)});feedback('failed',merchantImageMessage(error));}return;}throw error;}
  if(!uploadCurrent()){abandonBeforeUpload();return;}
  const path=prepared.path,content=prepared.content;
  feedback('preparing','正在准备上传');
  this.setData({materialPreviews:{...this.data.materialPreviews,[kind]:path},status:prepared.compressed?'照片已自动压缩，正在准备上传；请核对证照小字，大小不代表识别成功':'照片可保存，正在准备上传'});
  if(!binding.current())return;if(!this.data.application||(kind==='cashier_photo'||form.industryMaterialKind(kind))&&this.data.dirty){const saved=await this.saveDraft(binding);if(!saved||saved.application!==boundApplicationId)return;}if(!binding.current()||!this.data.application)return;const app=this.data.application,postedRevision=app.revision,postedProviderVersion=this.version;
  // One original selection, one scoped proof, two independent image transfers.
  if(ocrKind){
   let originalDigest='';
   const selectionAttempt={token:viewToken,kind:ocrKind,photo_confirmed:false};
   const active=()=>{
    const view=this.data.application;
    // wx.setData may clone the application object; compare bound identity
    // not material-save revisions. The original upload token still owns it.
    return binding.current()&&uploadIdentity()&&view&&view.application===app.application&&['DRAFT','CORRECTION_REQUIRED'].includes(view.status);
   };
   let savePreparationFailed=false,photoRecognizing=false,photoSaving=false;
   const clock=()=>clientOcrClock()??Date.now();
   const spans={};
   const timed=async(key,fn)=>{const start=clock();spans[key+'_started_ms']=Math.max(0,Math.round(start-directPickedAt));try{return await fn();}finally{const end=clock();spans[key]=Math.max(0,Math.round(end-start));spans[key+'_received_ms']=Math.max(0,Math.round(end-directPickedAt));}};
   const privateSave=fn=>timed('private_save_ms',fn);
   const directSend=arg=>{
    const start=clock(), mark=()=>{spans.aliyun_round_trip_ms=Math.max(0,Math.round(clock()-start));};
    return wx.request({...arg,success:r=>{mark();if(arg.success)arg.success(r);},fail:e=>{mark();if(arg.fail)arg.fail(e);}});
   };
   const reportTiming=()=>{
    if(!active())return;
    const previous=this.directOcrTimings[ocrKind]||{}, row={};
    for(const key of ['sign_wait_ms','sign_wait_ms_started_ms','sign_wait_ms_received_ms','aliyun_round_trip_ms','private_save_ms','private_save_ms_started_ms','private_save_ms_received_ms','ocr_round_trip_ms','pick_to_front_filled_ms','ocr_http_status']){
     const n=Object.prototype.hasOwnProperty.call(spans,key)?spans[key]:previous[key];
     if(Number.isFinite(n)&&n>=0)row[key]=Math.round(n);
    }
    row.photo_state=uploadConfirmed?'SAVED':savePreparationFailed?'FAILED':'NOT_CONFIRMED';
    row.ocr_state=Number.isFinite(previous.pick_to_front_filled_ms)?'SUGGESTION_VISIBLE':this.directOcrHints[ocrKind]?.active()?'RECEIVED_NOT_RENDER_CONFIRMED':'NO_CURRENT_SUGGESTION';
    if(typeof previous.request_id_present==='boolean')row.request_id_present=previous.request_id_present;
    if(typeof previous.request_id_sha256==='string'&&/^[a-f0-9]{64}$/.test(previous.request_id_sha256))row.request_id_sha256=previous.request_id_sha256;
    this.directOcrTimings[ocrKind]=row;
    let preview=false;
    try{const info=wx.getAccountInfoSync();preview=!!info&&!!info.miniProgram&&['develop','trial'].includes(info.miniProgram.envVersion);}catch(_){}
    if(preview&&typeof console!=='undefined'&&typeof console.info==='function'&&Object.keys(row).length){try{console.info('[OCR 分段耗时 ms]',ocrKind,row);}catch(_){}}
   };
   const photoOverlay=()=>photoRecognizing?{kind,phase:'recognizing',label:'正在识别…'}:null;
   const updatePhotoOverlay=(whenDone=false)=>{
    if(!ocrKind||!active()||this.uploadViewToken!==viewToken)return;
    const old=this.data.uploadFeedback;
    if(photoRecognizing){
     if(!old||old.kind===kind&&!['failed','unknown'].includes(old.phase))this.setData({uploadFeedback:photoOverlay()});
    }else if(whenDone&&old&&old.kind===kind&&old.phase==='recognizing'){
     this.setData({uploadFeedback:photoSaving?{kind,phase:'uploading',label:'正在上传'}:null});
    }
   };
   this.directOcrHints=this.directOcrHints||{};this.directOcrTimings=this.directOcrTimings||{};
   delete this.directOcrHints[ocrKind];delete this.directOcrTimings[ocrKind];
   if(this.ocrCapture&&this.ocrCapture.document_type===ocrKind)this.invalidateOcr('当前证照已更换');
   this.updateOcrView({ocrKind,ocrJob:'',ocrRows:[],ocrConfirmed:false,ocrProgressState:'',ocrStatus:kind==='bank_card'?'正在识别原图；银行卡照片不存入本站':'正在识别原图；材料仅临时中转给微信，成功后释放原件'});
   for(const cache of [this.ocrHeldCaptures,this.ocrDisplayCaptures])if(cache)delete cache[ocrKind];
   feedback('preparing','正在核对识别授权');
   const prepareSaveCopy=async()=>{
    if(!active())return null;
    let copy=prepared;
    if(prepared.size>MERCHANT_IMAGE_TARGET){
     feedback('preparing','正在压缩用于保存的照片；识别仍用原图');
     try{copy=await prepareMerchantImage(wx,originalPath,active,()=>{},false,MERCHANT_IMAGE_TARGET);}
     catch(_){if(active()){savePreparationFailed=true;const message='照片未能压缩到1MB以内，未保存；识别仍使用原图';feedback('failed',message);this.setData({status:message});}return null;}
    }
    return active()&&copy.size<=MERCHANT_IMAGE_TARGET?copy:null;
   };
   const saveCopy=kind==='bank_card'?Promise.resolve(null):prepareSaveCopy();
   const save=async()=>{
    const copy=await saveCopy;if(!copy||!active())return null;
    photoSaving=true;
    if(photoRecognizing)updatePhotoOverlay();else feedback('uploading','正在上传');
    this.setData({status:'正在上传照片'});uploadSent=true;
    return privateSave(()=>this.request('upload',{application:app.application,revision:postedRevision,kind,content_base64:copy.content,expires_at:null}));
   };
   const ack=result=>{
    photoSaving=false;
    if(!active()||savePreparationFailed)return;
    // Material-save verification only; OCR does not consume this receipt.
    if(!result||result.application!==app.application||result.revision!==postedRevision+1||!result.materials||!result.materials[kind]){
     const status='上传结果待核实，请先重新读取原申请；不会自动重传';feedback('unknown',status);this.setData({status});return;
    }
    uploadConfirmed=true;selectionAttempt.photo_confirmed=true;
    if(this.ocrDrafts)delete this.ocrDrafts[ocrKind];
    if(this.ocrFreshReview)delete this.ocrFreshReview[ocrKind];
    this.advanceDirectOcrHints(ocrKind,app,result,active);
    this.rememberDirectOriginal(ocrKind,path,originalDigest,result);
    this.setData({uploadFeedback:photoOverlay(),status:'照片已保存到原申请',application:result,materialPreviews:{...this.data.materialPreviews,[kind]:path}});
    if(active())this.updateOcrView();
   };
   if(prepared.ocrTooLarge||typeof wx.base64ToArrayBuffer!=='function'){
    const saved=await save();if(saved!==null)ack(saved);
    if(active())this.updateOcrView({ocrStatus:prepared.ocrTooLarge?'原图超过当前识别接口10MB上限，保存不受影响；可手动填写或换图识别。':'识别服务暂不可用，可手动填写'});
    return;
   }
   const original=wx.base64ToArrayBuffer(content);
   if(!(original instanceof ArrayBuffer)||original.byteLength!==prepared.size)throw merchantImageError('IMAGE_FILE_CHANGED');
   const proof=directProof((operation,params)=>uploadSession.merchant(uploadScene||'','onboarding',{operation,params}),app.application,postedRevision,postedProviderVersion);
   originalDigest=proof.sha256(original);
   this.directSelectionAttempt=selectionAttempt;
   const clearBankFeedback=this.beginBankOcrFeedback(ocrKind,active);
   photoRecognizing=true;updatePhotoOverlay();
   const finishBankFeedback=(refresh=true)=>{
    if(photoRecognizing){photoRecognizing=false;updatePhotoOverlay(true);}
    clearBankFeedback(refresh);
   };
   try{
   const attempt=startDirectOcr({kind:ocrKind,original,sha256:()=>originalDigest,signDigest:(...args)=>timed('sign_wait_ms',()=>proof.signDigest(...args)),
    savePrivate:save,request:directSend,isCurrent:active,onSave:ack,
    onSuggestion:result=>{
     if(!active()){finishBankFeedback();return false;}
     finishBankFeedback(false);
     if(!result||!result.fields||!Object.keys(result.fields).length){this.updateOcrView({ocrStatus:'未取得识别建议，可手动填写'});return false;}
     this.setDirectOcrHint(ocrKind,result.fields,active,uploadConfirmed);
     return new Promise(resolve=>this.updateOcrView({ocrStatus:'识别建议，请人工核对'},()=>{
      const visible=(this.data.materialGroups||[]).some(g=>(g.fields||[]).some(field=>{
       const k=(field.ocrDirect===ocrKind||field.ocrDirectCompare===ocrKind)&&this.ocrPathKey(field.path,ocrKind);
       return !!k&&typeof result.fields[k]==='string'&&!!result.fields[k]&&(field.ocrDirectCompare===ocrKind?typeof field.ocrHint==='string'&&field.ocrHint.includes(result.fields[k]):!!field.value);
      }));
      resolve(active()&&visible);
     }));
    },timing:{pickedAt:directPickedAt,now:clientOcrClock,hashRequestId:id=>typeof id==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(id)?proof.sha256(Uint8Array.from(Array.from(id,ch=>ch.charCodeAt(0))).buffer):null,record:row=>{if(active())this.directOcrTimings[ocrKind]=row;}}
   });
   await Promise.all([attempt.storage,attempt.ocr]);
   }finally{finishBankFeedback();reportTiming();if(this.directSelectionAttempt===selectionAttempt)this.directSelectionAttempt=null;}
   return;
  }
 feedback('uploading','正在上传');this.setData({status:'正在上传照片'});uploadSent=true;const result=await this.request('upload',{application:app.application,revision:app.revision,kind,content_base64:content,expires_at:null,
   ...(originalOnly?{intent_key:'mini-ocr-upload-'+Date.now()+'-'+Math.random().toString(36).slice(2)}:{})});
  if(binding.current()&&this.version===postedProviderVersion&&sameApplication(app,postedRevision)&&result&&result.application===boundApplicationId){
   if(originalOnly){
    if(!Number.isSafeInteger(result.revision)||result.revision!==app.revision+1||!result.materials||!result.materials[kind]){
     feedback('unknown','上传结果待核实，请先重新读取原申请；不会自动重传');
     this.setData({status:'上传结果待核实，请先重新读取原申请；不会自动重传'});return;
    }
    uploadConfirmed=true;
    const {upload_ocr:job,...savedApplication}=result;
    this.retainOcrDisplay(this.ocrCapture);this.invalidateOcr('照片已保存，正在核对本次识别结果');
    for(const cache of [this.ocrHeldCaptures,this.ocrDisplayCaptures])if(cache)delete cache[ocrKind];
    this.setData({uploadFeedback:null,status:'营业执照照片已保存到原申请',application:savedApplication,materialPreviews:{...this.data.materialPreviews,[kind]:path}});
    if(!binding.current()||this.data.application!==savedApplication)return;
    await this.acceptCommittedLicenseOcr(job,savedApplication,ocrKind);
    if(binding.current()&&this.data.application===savedApplication)this.refresh();
    return;
   }
   if(bankOcrKind&&(!Number.isSafeInteger(result.revision)||result.revision!==app.revision+1||!result.materials||!result.materials.bank_card)){feedback('unknown','上传结果待核实，请先重新读取原申请；不会自动重传');this.setData({status:'上传结果待核实，请先重新读取原申请；不会自动重传'});return;}
   uploadConfirmed=true;if((bankOcrKind||ocrKind)){if(this.ocrCapture&&this.ocrCapture.document_type===(bankOcrKind||ocrKind))this.invalidateOcr('新照片已上传，旧识别建议已撤下；正在识别当前材料');for(const cache of [this.ocrHeldCaptures,this.ocrDisplayCaptures])if(cache)delete cache[(bankOcrKind||ocrKind)];}this.retainOcrDisplay(this.ocrCapture);this.setData({uploadFeedback:null,status:kind==='bank_card'?'银行卡照片已私密保存，正在读取识别建议；请人工核对':'照片已保存到原申请，最后提交时自动处理',application:result,materialPreviews:{...this.data.materialPreviews,[kind]:path}});if(!binding.current())return;if((bankOcrKind||ocrKind))await this.recognizeCurrentDocument((bankOcrKind||ocrKind),{newIntent:true,uploadedMaterial:true});if(!binding.current())return;this.refresh();}
  else if(binding.current()){feedback('unknown','上传结果待核实，请先重新读取原申请；不会自动重传');this.setData({status:'上传结果待核实，请先重新读取原申请；不会自动重传'});}
  }catch(error){
   if(!uploadConfirmed){const unknown=uploadSent&&(error.uploadResultUnknown||error.networkKind||error.code==='SERVICE_RESULT_UNKNOWN'||error.message==='SERVICE_RESULT_UNKNOWN');feedback(unknown?'unknown':'failed',unknown?'上传结果待核实，请先重新读取原申请；不会自动重传':uploadSent?'上传失败，请先重新读取原申请后再操作':'照片未上传，请检查提示后重新选择');}
   throw error;
  }finally{
   if(!binding.current()&&this.uploadViewToken===viewToken){this.setData({uploadFeedback:null});if(uploadIdentity())this.showApplicantSessionRecovery();}
   else if(!uploadSent&&this.data.uploadFeedback&&this.data.uploadFeedback.kind===kind&&this.data.uploadFeedback.phase==='preparing')feedback('failed','照片尚未上传，请先核对原申请保存状态');
  }
 },'照片上传');},
 privatePreviewCleanup(){
  this.materialPreviewGeneration=(this.materialPreviewGeneration||0)+1;
  const paths=this.privateMaterialPreviewPaths||new Set();this.privateMaterialPreviewPaths=new Set();
  const previews={...(this.data.materialPreviews||{})};for(const [kind,path] of Object.entries(previews))if(paths.has(path))delete previews[kind];
  try{if(typeof wx.getFileSystemManager==='function'){const fs=wx.getFileSystemManager();if(fs&&typeof fs.unlink==='function')for(const filePath of paths){try{fs.unlink({filePath,fail:()=>{this.privatePreviewCleanupFailed=true;}});}catch(_){this.privatePreviewCleanupFailed=true;}}}}catch(_){this.privatePreviewCleanupFailed=true;}
  this.setData({materialPreviews:previews,materialPreviewHints:{}});
 },
 async restoreUploadedMaterialPreviews(){
  this.privatePreviewCleanup();const app=this.data.application,application=app&&app.application,revision=app&&app.revision,materialSnapshot=JSON.stringify(app&&app.materials||{}),session=this.session,scene=this.scene,epoch=this.epoch,generation=this.materialPreviewGeneration,sessionGeneration=session&&typeof session.getGeneration==='function'?session.getGeneration():undefined;
  if(!app||!session||typeof wx.getFileSystemManager!=='function'||!wx.env||typeof wx.env.USER_DATA_PATH!=='string')return;
  let fs;try{fs=wx.getFileSystemManager();}catch(_){this.privatePreviewCleanupFailed=true;return;}if(!fs||typeof fs.writeFile!=='function'||typeof fs.unlink!=='function')return;
  const privatePreview=require('../../material-private-preview');
  const current=()=>this.current()&&!this.ocrHidden&&this.session===session&&this.scene===scene&&this.epoch===epoch&&this.materialPreviewGeneration===generation&&this.data.application&&this.data.application.application===application&&this.data.application.revision===revision&&JSON.stringify(this.data.application.materials||{})===materialSnapshot&&(!session.isAuthenticated||session.isAuthenticated())&&(sessionGeneration===undefined||session.getGeneration()===sessionGeneration);
  const clearRevoked=()=>{if(this.session===session&&this.scene===scene&&this.epoch===epoch&&typeof session.isAuthenticated==='function'&&!session.isAuthenticated())this.privatePreviewCleanup();};
  // Remove only this feature's opaque temporary names left by an interrupted VM.
  if(typeof fs.readdir!=='function')return;
  try{const old=await new Promise((resolve,reject)=>fs.readdir({dirPath:wx.env.USER_DATA_PATH,success:resolve,fail:reject}));if(!current()){clearRevoked();return;}for(const name of old.files||[]){if(!current()){clearRevoked();return;}if(/^community-private-preview-[0-9]+-[a-z0-9]+\.(?:png|jpg)$/.test(name))await new Promise(resolve=>fs.unlink({filePath:wx.env.USER_DATA_PATH+'/'+name,success:resolve,fail:resolve}));}}catch(_){return;}
  if(!current()){clearRevoked();return;}
  for(const kind of ['business_license','identity_front','identity_back','bank_card','settlement_proof']){
   if(!current()){clearRevoked();return;}if(!app.materials||!app.materials[kind])continue;
   this.setData({materialPreviewHints:{...this.data.materialPreviewHints,[kind]:'正在读取已上传照片'}});
   let filePath;
   try{
    const r=await this.request('material_preview',{application,revision,kind});if(!current()){clearRevoked();return;}if(r&&r.status==='UNAVAILABLE')throw Error(['BANK_CARD_BINDING_UNAVAILABLE','MATERIAL_PREVIEW_IMAGE_REQUIRED'].includes(r.reason)?r.reason:'MATERIAL_PREVIEW_UNAVAILABLE');
    if(!r||r.application!==application||r.revision!==revision||r.kind!==kind||!/^o_[a-f0-9]{32}$/.test(r.object_id||'')||! /^[a-f0-9]{64}$/.test(r.sha256||'')||!['image/jpeg','image/png'].includes(r.mime)||!Number.isSafeInteger(r.size)||r.size<1||r.size>5000000||typeof r.content_base64!=='string'||r.content_base64.length!==4*Math.ceil(r.size/3)||!/^[A-Za-z0-9+/]*={0,2}$/.test(r.content_base64)||r.cache!=='PRIVATE_TEMPORARY_ONLY')throw Error('MATERIAL_PREVIEW_INVALID');
    privatePreview.verify(r);
    filePath=wx.env.USER_DATA_PATH+'/community-private-preview-'+Date.now()+'-'+Math.random().toString(36).slice(2)+(r.mime==='image/png'?'.png':'.jpg');
    await new Promise((resolve,reject)=>fs.writeFile({filePath,data:r.content_base64,encoding:'base64',success:resolve,fail:reject}));
    if(!current()){clearRevoked();try{fs.unlink({filePath,fail:()=>{this.privatePreviewCleanupFailed=true;}});}catch(_){this.privatePreviewCleanupFailed=true;}return;}
    this.privateMaterialPreviewPaths.add(filePath);this.setData({materialPreviews:{...this.data.materialPreviews,[kind]:filePath},materialPreviewHints:{...this.data.materialPreviewHints,[kind]:''}});
   }catch(error){if(filePath){try{fs.unlink({filePath,fail:()=>{this.privatePreviewCleanupFailed=true;}});}catch(_){this.privatePreviewCleanupFailed=true;}}if(!current()){clearRevoked();return;}const code=String(error&&error.message||'');const text=code==='BANK_CARD_BINDING_UNAVAILABLE'?'当前材料未明确标为银行卡，暂不展示，原材料保留。':code==='MATERIAL_PREVIEW_IMAGE_REQUIRED'?'原材料不是可预览的照片，文件仍已保留。':'暂时无法读取这张照片，已上传材料仍保留，请勿重复上传。';this.setData({materialPreviewHints:{...this.data.materialPreviewHints,[kind]:text}});}
  }
 },
 // Polling resumes only the original operation/key, including an explicitly sent confirmation/save receipt. It never creates a new confirmation, OCR task or upload.
 clearUploadedOcrRestoreTimer(){if(this.ocrRestoreTimer!==undefined&&typeof clearTimeout==='function')clearTimeout(this.ocrRestoreTimer);this.ocrRestoreTimer=undefined;},
 uploadedOcrRestoreCurrent(queue){return !!queue&&queue===this.ocrRestoreQueue&&this.current()&&this.session===queue.session&&this.scene===queue.scene&&this.epoch===queue.epoch&&this.data.application&&this.data.application.application===queue.application&&this.data.application.revision===queue.revision&&this.version===queue.version&&(!this.session.isAuthenticated||this.session.isAuthenticated())&&(queue.sessionGeneration===undefined||this.session.getGeneration()===queue.sessionGeneration);},
 queueUploadedOcrRestore(){
  this.clearUploadedOcrRestoreTimer();const a=this.data.application;if(!a||!this.session)return;
  const kinds=['business_license','id_front','id_back','bank_card'].filter(kind=>{const material=a.materials&&a.materials[kind==='id_front'?'identity_front':kind==='id_back'?'identity_back':kind];return !!material;});
  this.ocrRestoreQueue={session:this.session,sessionGeneration:typeof this.session.getGeneration==='function'?this.session.getGeneration():undefined,scene:this.scene,epoch:this.epoch,application:a.application,revision:a.revision,version:this.version,failures:{},items:kinds.map(kind=>({kind,source:this.ocrSource(kind)}))};
  this.scheduleUploadedOcrRestore();
 },
 scheduleUploadedOcrRestore(){
  this.clearUploadedOcrRestoreTimer();const queue=this.ocrRestoreQueue;
  if(!this.uploadedOcrRestoreCurrent(queue)||!queue.items.length||this.ocrHidden||this.data.dirty||this.data.ocrConfirmed||this.ocrFlight||this.ocrPolling||this.ocrRestoreRunning||typeof setTimeout!=='function')return;
  this.ocrRestoreTimer=setTimeout(async()=>{
   this.ocrRestoreTimer=undefined;if(!this.uploadedOcrRestoreCurrent(queue)||this.ocrHidden||this.data.dirty||this.data.ocrConfirmed)return;
   if(this.data.pending||this.ocrFocus||this.ocrFlight||this.ocrPolling){this.scheduleUploadedOcrRestore();return;}
   const item=queue.items.shift();if(!item)return;
   if(item.source!==this.ocrSource(item.kind)){this.scheduleUploadedOcrRestore();return;}
   const held=this.retainedOcrCapture(item.kind),active=this.ocrCapture&&this.ocrCapture.document_type===item.kind&&this.ocrCurrent(this.ocrCapture)&&this.data.ocrRows.length;
   const visible=(this.data.materialGroups||[]).some(group=>group.ocrKind===item.kind||group.ocrBackKind===item.kind);
   if(active||!visible&&held&&held.local_state.rows&&held.local_state.rows.length){this.scheduleUploadedOcrRestore();return;}
   this.ocrRestoreRunning=true;
   try{if(item.kind==='bank_card')await this.recognizeCurrentDocument(item.kind,{existingMaterial:true});/* Bank restoration only reads the original binding; never creates a job. */}
   finally{this.ocrRestoreRunning=false;this.scheduleUploadedOcrRestore();}
  },this.data.pending||this.ocrFocus?1000:0);
 },
 rememberKnownOcr(){const c=this.ocrCapture;if(!this.session||!c||(!c.job_id&&!c.idempotency_key)||!this.data.application||c.application!==this.data.application.application||c.revision!==this.data.application.revision||c.source!==this.ocrSource(c.document_type))return;OCR_PAGE_RESUME.set(this.session,{application:c.application,revision:c.revision,document_type:c.document_type,bound_provider_version:c.bound_provider_version,recovery_binding:c.recovery_binding?{...c.recovery_binding}:undefined,job_id:c.job_id,idempotency_key:c.idempotency_key,source:c.source,scene:this.scene,epoch:this.epoch,session_generation:c.session_generation,transport:this.ocrTransport,auto_save_fields:c.auto_save_fields?{...c.auto_save_fields}:null,recovery:c.recovery===true,recovery_key:c.recovery_key,original_locator:c.original_locator?{...c.original_locator}:undefined,recovery_confirmation:c.recovery_confirmation?{...c.recovery_confirmation,fields:{...c.recovery_confirmation.fields}}:undefined,recovery_confirmation_revision:c.recovery_confirmation_revision,recovery_writeback_key:c.recovery_writeback_key,recovery_apply_pending:c.recovery_apply_pending===true,local_rows:this.data.ocrRows.map(row=>({...row})),local_edits:{...(this.ocrSuggestionEdits||{})},local_edit_version:this.ocrSuggestionEditVersion||0,edit_material_group:this.data.editMaterialGroup,pending_confirmation:c.pending_confirmation===true,pending_confirmation_revision:c.pending_confirmation_revision,pending_confirmation_edit_version:c.pending_confirmation_edit_version,pending_confirmation_provider_version:c.pending_confirmation_provider_version,pending_confirmation_fields:c.pending_confirmation_fields?{...c.pending_confirmation_fields}:undefined});},
 async restoreKnownOcr(){const session=this.session,record=session&&OCR_PAGE_RESUME.get(session),app=this.data.application;if(!record||!app)return;const valid=()=>this.current()&&this.session===session&&this.epoch===record.epoch&&this.scene===record.scene&&this.data.application&&this.data.application.application===record.application&&(this.data.application.revision===record.revision||record.recovery===true&&record.recovery_apply_pending===true&&typeof record.recovery_writeback_key==='string'&&record.recovery_confirmation)&&!this.data.dirty&&record.source===this.ocrSource(record.document_type)&&(record.session_generation===undefined||record.session_generation===session.getGeneration());if(!valid()||!['business_license','id_front','id_back','bank_card'].includes(record.document_type))return;if(record.transport){try{await record.transport;}catch(_){}if(!valid())return;}if(OCR_PAGE_RESUME.get(session)!==record)return;OCR_PAGE_RESUME.delete(session);const c={application:record.application,revision:record.recovery_apply_pending?this.data.application.revision:record.revision,auto_save_fields:record.auto_save_fields?{...record.auto_save_fields}:null,recovery:record.recovery===true,recovery_key:record.recovery_key,original_locator:record.original_locator?{...record.original_locator}:undefined,recovery_confirmation:record.recovery_confirmation?{...record.recovery_confirmation,fields:{...record.recovery_confirmation.fields}}:undefined,recovery_confirmation_revision:record.recovery_confirmation_revision,recovery_writeback_key:record.recovery_writeback_key,recovery_apply_pending:record.recovery_apply_pending===true,document_type:record.document_type,bound_provider_version:record.bound_provider_version,recovery_binding:record.recovery_binding?{...record.recovery_binding}:undefined,job_id:record.job_id,idempotency_key:record.idempotency_key,source:record.source,pending_confirmation:record.pending_confirmation===true,pending_confirmation_revision:record.pending_confirmation_revision,pending_confirmation_edit_version:record.pending_confirmation_edit_version,pending_confirmation_provider_version:record.pending_confirmation_provider_version,pending_confirmation_fields:record.pending_confirmation_fields?{...record.pending_confirmation_fields}:undefined};if(c.document_type==='bank_card'&&(!Number.isSafeInteger(c.bound_provider_version)||c.bound_provider_version!==this.version)){this.updateOcrView({ocrRows:[],ocrConfirmed:false});return this.recoverCurrentDocument({...c,session,session_generation:record.session_generation,scene:this.scene});}this.ocrCapture={...c,session,session_generation:record.session_generation,scene:this.scene,generation:this.ocrGeneration,request_generation:(this.ocrRequestGeneration||0)+1};this.ocrRequestGeneration=this.ocrCapture.request_generation;this.ocrSuggestionEdits=toObject(Object.entries(record.local_edits||{}).filter(([key,value])=>ocrInputFields(c.document_type).includes(key)&&typeof value==='string'));this.ocrSuggestionEditVersion=record.local_edit_version||0;this.updateOcrView({ocrKind:c.document_type,ocrJob:c.job_id,ocrRows:(record.local_rows||[]).filter(row=>ocrInputFields(c.document_type).includes(row.key)).map(row=>({...row})),ocrConfirmed:false,editMaterialGroup:record.edit_material_group||'',ocrStatus:'正在恢复原申请识别请求；不会重新上传材料'});this.ocrPolling=true;if(c.job_id||c.recovery)await this.readOcr();else if(c.idempotency_key)await this.resumeOcrSubmit(this.ocrCapture);},
 ocrPathKey(path,kind){const maps={bank_card:{'bank_account_info.account_number':'account_number','bank_account_info.account_bank':'account_bank'},business_license:{'subject_info.business_license_info.merchant_name':'company_name','subject_info.business_license_info.license_number':'credit_code','subject_info.business_license_info.legal_person':'legal_representative','subject_info.business_license_info.license_address':'registered_address'},id_front:{'subject_info.identity_info.id_card_info.id_card_name':'id_name','subject_info.identity_info.id_card_info.id_card_number':'id_number','subject_info.identity_info.id_card_info.id_card_address':'registered_address'},id_back:{'subject_info.identity_info.id_card_info.card_period_begin':'valid_from','subject_info.identity_info.id_card_info.card_period_end':'valid_to'}};return maps[kind]&&maps[kind][path];},
 ocrFieldPresent(path,kind,view=this.data){if(!kind||kind!==view.ocrKind)return false;const key=this.ocrPathKey(path,kind);return !!key&&view.ocrRows.some(row=>row.key===key&&typeof row.value==='string'&&!!row.value.trim());},
 retainedOcrCapture(kind){const c=this.ocrDisplayCaptures&&this.ocrDisplayCaptures[kind],a=this.data.application;if(!c||!c.local_state||!a||c.document_type!==kind||c.application!==a.application||c.session!==this.session||c.scene!==this.scene||c.source!==this.ocrSource(kind)||(c.session_generation!==undefined&&c.session_generation!==this.session.getGeneration())||this.session.isAuthenticated&&!this.session.isAuthenticated())return null;return c;},
 retainOcrDisplay(capture){if(!capture)return;const c=capture===this.ocrCapture?this.holdOcrLocal(capture):capture;this.ocrDisplayCaptures=this.ocrDisplayCaptures||{};this.ocrDisplayCaptures[c.document_type]=c;},
 settlementAccountName(profile=this.profile,options=this.data.options){
  const type=form.get(profile,'bank_account_info.bank_account_type');
  if(type==='BANK_ACCOUNT_TYPE_CORPORATE'){
   const value=form.get(profile,'subject_info.business_license_info.merchant_name');
   return {type,name:typeof value==='string'?value.trim():'',hint:'对公户名来自本申请营业执照主体全称。'};
  }
  if(type==='BANK_ACCOUNT_TYPE_PERSONAL'){
   const entity=form.personalAccountReuse(profile,options);
   return {type,name:entity&&!entity.missing&&!entity.sourceConflict&&typeof entity.sourceValue==='string'?entity.sourceValue.trim():'',hint:entity&&entity.sourceConflict?'证件姓名和执照法人／经营者姓名不一致，请返回第一步核对。':'对私户名来自本申请法人／经营者姓名。'};
  }
  return {type,name:'',hint:'请先选择结算账户类型。'};
 },
 fillPersonalAccountName(){
  if(!this.data.canEditWechat)return false;
  const derived=this.settlementAccountName();
  if(!derived.name)return false;
  const path='bank_account_info.account_name';
  const changed=form.get(this.profile,path)!==derived.name;
  if(changed)form.put(this.profile,path,derived.name);
  this.reusedFieldLinks=this.reusedFieldLinks||{};
  this.reusedFieldLinks[path]=derived.name;
  return changed;
 },
 acceptDisplayedDirectOcr(){
  if(!this.current()||!this.data.ready||!this.data.canEditWechat)return 0;
  let filled=0;
  for(const field of flatten(this.projectOcrGroups(this.data.materialGroups||[]).map(group=>group.fields||[]))){
   const hint=this.directOcrHints&&this.directOcrHints[field.ocrDirect];
   if(!hint||!hint.active()||field.ocrManualBank||typeof field.value!=='string'||!field.value.trim()||
      ocrHasValue(form.get(this.profile,field.path)))continue;
   form.put(this.profile,field.path,field.value);filled++;
  }
  if(filled){this.fillPersonalAccountName();this.setData({dirty:true});this.syncLeaveGuard();}
  return filled;
 },
 personalAccountDisplay(view=this.data){
  const derived=this.settlementAccountName(this.profile||{},view.options||this.data.options);
  return {personalAccountName:derived.name||'待前一步核对',personalAccountNameHint:derived.hint};
 },
 // Display presence is separate from the unchanged saved-profile submission gate.
 reviewPresentation(view=this.data){
  if(!form||!this.profile)return [];
  const profile=this.profile,options=view.options||{},materials=view.materials||[];
  const base=form.reviewRequirements(profile,options,materials,view.application),effective=JSON.parse(JSON.stringify(profile));
  const present=v=>typeof v==='string'?!!v.trim():Array.isArray(v)?v.length>0:v!==undefined&&v!==null&&v!==false;
  const suggestions=new Map();
  for(const kind of ['business_license','id_front','id_back','bank_card']){
   const active=this.ocrCapture&&this.ocrCapture.document_type===kind&&this.ocrCurrent(this.ocrCapture,view),held=!active&&this.retainedOcrCapture(kind);
   const rows=active?view.ocrRows:held&&held.local_state.rows;
   for(const group of base)for(const item of group.items){const key=this.ocrPathKey(item.path,kind),row=key&&(rows||[]).find(r=>r.key===key&&present(r.value));if(row&&!present(form.get(profile,item.path))){suggestions.set(item.path,row.value);form.put(effective,item.path,row.value);}}
  }
  const reused=new Map();
  for(const field of form.reusedFields(effective,options))if(!field.missing&&!field.conflict&&!field.sourceConflict&&present(field.sourceValue)&&!present(form.get(profile,field.targetPath)))reused.set(field.targetPath,field.sourceValue);
  const configuration=[];
  const summarize=(group,items)=>{const missing=items.filter(x=>!x.complete),pending=items.filter(x=>x.complete&&(!x.savedComplete||x.sourceConflict));return {...group,items,total:items.length,completed:items.length-missing.length,missing:missing.map(x=>x.label),missingText:missing.map(x=>x.label).join('、'),pendingText:pending.map(x=>x.label+(x.material?'（已上传，微信关联待完成）':x.sourceConflict?'（资料不一致，待核对）':'（已取得，待核对或保存）')).join('、')};};
  const groups=base.map(group=>{
   const items=group.items.filter(item=>{if(branchField(item.path)&&!bankNeedsBranch(profile))return false;if(group.id==='bank'&&item.path.startsWith('settlement_info.')){configuration.push(item);return false;}return true;}).map(item=>{
    const value=form.get(profile,item.path),suggestion=suggestions.get(item.path),reuse=reused.get(item.path);
    let complete=item.material?!!item.uploaded:item.complete||present(suggestion)||present(reuse),sourceConflict=false;
    if(item.path==='bank_account_info.account_name'){
     const expected=this.settlementAccountName(profile,options);
     sourceConflict=!!value&&value!==expected.name;
     return {...item,complete:!!expected.name,savedComplete:!!expected.name&&value===expected.name&&item.complete,sourceConflict};
    }
    return {...item,complete,savedComplete:item.complete,sourceConflict};
   });return summarize(group,items);
  });
  const industry=groups.find(g=>g.id==='industry');if(industry){const actual=form.get(profile,'settlement_info.qualification_type'),ready=configuration.length===2&&configuration.every(x=>x.complete);Object.assign(industry,summarize(industry,[{path:'industry_choice',label:'实际经营行业',complete:present(actual),savedComplete:present(actual)}]),{industryStatus:ready?(officialFields.selectedIndustry(options.entity,profile)?'已匹配结算配置，仍以微信最终审核为准。':'原结算配置已保留，须由平台核对；不代表微信已核准。'):present(actual)?'行业已记录但尚未匹配官方规则，可保存草稿、暂不能提交；不会沿用旧行业规则。':'请选择真实经营行业，系统按当前主体匹配官方规则。'});}
  return groups;
 },
 projectOcrGroups(groups,view=this.data){return groups.map(group=>{const bank=group.id==='bank';const fields=(group.fields||[]).filter(field=>field.path!=='bank_account_info.account_name'&&(!branchField(field.path)||bankNeedsBranch(this.profile||{}))).map(field=>{const kind=['business_license','id_front','id_back','bank_card'].find(type=>this.ocrPathKey(field.path,type)),key=kind&&this.ocrPathKey(field.path,kind),active=kind===view.ocrKind&&(view.ocrRows||[]).find(item=>item.key===key),held=!active&&kind&&this.retainedOcrCapture(kind),draft=kind&&this.ocrDrafts&&this.ocrDrafts[kind],savedRow=draft&&draft.fields&&typeof draft.fields[key]==='string'?{key,value:draft.fields[key],hint:'草稿已保存，待本人核对'}:null,fresh=kind&&this.ocrFreshReview&&this.ocrFreshReview[kind],freshRow=fresh&&view.application&&
fresh.application===view.application.application&&fresh.revision===view.application.revision&&fresh.version===this.version&&
fresh.source===this.ocrSource(kind)&&typeof fresh.fields[key]==='string'?{key,value:fresh.fields[key],hint:'当前证照重新识别，请核对'}:null,row=freshRow||savedRow||active||held&&(held.local_state.rows||[]).find(item=>item.key===key),failure=kind&&this.uploadedOcrRestoreCurrent(this.ocrRestoreQueue)&&this.ocrRestoreQueue.failures[kind],failureHint=failure&&failure.source===this.ocrSource(kind)?failure.text:'',stored=form.get(this.profile||{},field.path),hasStored=typeof stored==='string'&&(!!stored.trim()||!!(this.ocrExplicitEmptyFields&&this.ocrExplicitEmptyFields[field.path])),conflict=!!row&&hasStored&&!!row.value.trim()&&stored!==row.value,retained=!!row&&!active;return {...field,value:hasStored?stored:row?row.value:kind?(typeof stored==='string'?stored:''):field.value,ocrKey:row?key:'',ocrDocument:kind||'',ocrRetained:retained,ocrPrivateDraft:!!savedRow,ocrSuggestion:!!row&&!hasStored,ocrConflict:conflict,ocrHint:conflict?'已保留原填写内容，与识别建议不同；请核对，尚未覆盖原资料。':retained?(row.value.trim()?'此前识别内容已保留，待核对，尚未保存。':row.hint||'未识别到可靠值，请手动核对填写'):row?row.hint||'待人工核对':failureHint,ocrInReview:!!(kind&&key&&row&&(!hasStored||draft&&draft.fields&&Object.prototype.hasOwnProperty.call(draft.fields,key))&&!(kind===view.ocrKind&&view.ocrConfirmed&&!draft)),ocrResultPresent:!!row&&typeof row.value==='string'&&!!row.value.trim(),...directOcrHint(this,kind,key,hasStored,row,field,savedRow,freshRow,active,held)};});return {...group,fields,hasOcrFields:fields.some(field=>field.ocrResultPresent),...(bank?{personalAccount:true,...this.personalAccountDisplay(view)}:{})};});},
 editRetainedOcr(field,value){const c=this.retainedOcrCapture(field.ocrDocument);if(!c||typeof value!=='string'||!ocrInputFields(field.ocrDocument).includes(field.ocrKey))return;const local=c.local_state;this.ocrDisplayCaptures[field.ocrDocument]={...c,local_state:{...local,edits:{...(local.edits||{}),[field.ocrKey]:value},rows:(local.rows||[]).map(row=>row.key===field.ocrKey?{...row,value}:row),edit_version:(local.edit_version||0)+1}};const held=this.ocrHeldCaptures&&this.ocrHeldCaptures[field.ocrDocument];if(held&&held.session===c.session&&held.application===c.application&&held.revision===c.revision&&held.source===c.source&&held.job_id===c.job_id&&held.idempotency_key===c.idempotency_key)this.ocrHeldCaptures[field.ocrDocument]=this.ocrDisplayCaptures[field.ocrDocument];this.updateOcrView();},
 inputUnifiedField(e){const field=flatten((this.data.materialGroups||[]).map(g=>g.fields||[])).find(f=>f.path===e.currentTarget.dataset.path);if(field&&field.ocrSuggestion&&field.ocrPrivateDraft){const draft=this.ocrDrafts[field.ocrDocument];draft.fields={...draft.fields,[field.ocrKey]:e.detail.value};this.setData({dirty:true});this.syncLeaveGuard();this.refresh();return;}if(field&&field.ocrSuggestion&&field.ocrRetained)return this.editRetainedOcr(field,e.detail.value);if(field&&field.ocrSuggestion)return this.editOcrSuggestion({currentTarget:{dataset:{key:field.ocrKey}},detail:e.detail});return this.input(e);},
 focusUnifiedField(e){const field=flatten((this.data.materialGroups||[]).map(g=>g.fields||[])).find(f=>f.path===e.currentTarget.dataset.path);if(field&&field.ocrSuggestion&&field.ocrRetained){this.ocrFocus={kind:'retained',path:field.path,document_type:field.ocrDocument};return;}if(field&&field.ocrSuggestion){this.focusOcrSuggestion({currentTarget:{dataset:{key:field.ocrKey}}});if(this.ocrFocus)this.ocrFocus.path=field.path;return;}return this.focusField(e);},
 blurUnifiedField(e){if(this.ocrFocus&&this.ocrFocus.kind==='retained'&&this.ocrFocus.path===e.currentTarget.dataset.path){this.ocrFocus=null;return;}if(this.ocrFocus&&this.ocrFocus.kind==='field'&&this.ocrFocus.path===e.currentTarget.dataset.path&&this.ocrDeferredFocusedKey){const key=this.ocrDeferredFocusedKey;this.ocrFocus=null;this.ocrDeferredFocusedKey=null;if(!Object.prototype.hasOwnProperty.call(this.ocrSuggestionEdits||{},key)&&this.ocrCurrent(this.ocrCapture))return this.readOcr();}if(this.ocrFocus&&this.ocrFocus.kind==='suggestion'&&this.ocrFocus.path===e.currentTarget.dataset.path)return this.blurOcrSuggestion({currentTarget:{dataset:{key:this.ocrFocus.key}}});return this.blur(e);},
 ocrConfirmationRows(){const visible=new Map(flatten(this.projectOcrGroups(this.data.materialGroups).map(g=>g.fields||[])).filter(f=>f.ocrKey&&f.ocrDocument===this.data.ocrKind&&!f.ocrRetained).map(f=>[f.ocrKey,f.value]));return this.data.ocrRows.map(row=>visible.has(row.key)?{...row,value:visible.get(row.key)}:row);},
 beginBankOcrFeedback(kind,active){
  if(kind!=='bank_card')return ()=>{};
  const task={active};this.bankOcrFeedbackTask=task;this.updateOcrView();
  return (refresh=true)=>{
   if(this.bankOcrFeedbackTask!==task)return;
   this.bankOcrFeedbackTask=null;
   if(refresh&&this.current())this.updateOcrView();
  };
 },
 materialOcrFeedback(view=this.data){
  const bank=this.bankOcrFeedbackTask;
  if(bank&&bank.active())return {kind:'bank_card',label:'正在识别…'};
  const capture=this.ocrCapture;
  if(!this.ocrPolling||!capture||!this.ocrCurrent(capture,view)||view.ocrConfirmed||!['requesting','reading','querying','queued','processing'].includes(view.ocrProgressState))return null;
  const kind=({business_license:'business_license',id_front:'identity_front',id_back:'identity_back',bank_card:'bank_card'})[capture.document_type];
  if(!kind)return null;
  const status=String(view.ocrStatus||'');
  return {kind,label:/等待/.test(status)?'等待识别，请稍候':/查询|读取|网络|暂时/.test(status)?'正在查询识别结果，请稍候':'正在识别，请稍候'};
 },
 materialOcrFailureView(){
  const queue=this.ocrRestoreQueue,visible={};if(!this.uploadedOcrRestoreCurrent(queue))return visible;
  for(const kind of ['business_license','id_front','id_back','bank_card']){
   const failure=queue.failures&&queue.failures[kind];
   if(!failure||failure.source!==this.ocrSource(kind)||typeof failure.text!=='string')continue;
   const material=kind==='id_front'?'identity_front':kind==='id_back'?'identity_back':kind;
   visible[material]={text:failure.text,diagnostic:failure.diagnostic||null};
  }
  return visible;
 },
 updateOcrView(patch={},afterRender){
  const queue=this.ocrRestoreQueue,capture=this.ocrCapture;
  if(this.uploadedOcrRestoreCurrent(queue)&&capture&&this.ocrCurrent(capture)){
   if((patch.ocrDiagnostic&&patch.ocrDiagnostic.retryable===false||patch.ocrProgressState==='failed')&&typeof patch.ocrStatus==='string')queue.failures[capture.document_type]={source:this.ocrSource(capture.document_type),text:patch.ocrStatus,diagnostic:patch.ocrDiagnostic?toObject(['version','diagnostic_id','stage','reason','retryable','request_retained'].map(key=>[key,patch.ocrDiagnostic[key]])):null};
   else if(['needs_review','confirmed'].includes(patch.ocrProgressState))delete queue.failures[capture.document_type];
  }
  const view={...this.data,...patch},groups=this.projectOcrGroups(view.materialGroups||[],view);
  const focused=this.ocrFocus&&this.ocrFocus.path&&groups.find(group=>group.fields.some(field=>field.path===this.ocrFocus.path&&(field.ocrResultPresent||field.ocrKey)));
  // Keep the existing input branch mounted. This is the same v9 edit mode,
  // not a new layout or an automatic write of OCR values to the profile.
  const next={...patch,materialOcrErrors:this.materialOcrFailureView(),displayReviewGroups:this.reviewPresentation(view),ocrFeedback:this.materialOcrFeedback(view),materialGroups:groups,...(focused?{editMaterialGroup:focused.id}:{})},changed={};
  for(const key of Object.keys(next))if(!sameOcrView(this.data[key],next[key]))changed[key]=next[key];
  if(Object.keys(changed).length)this.setData(changed,()=>{this.presentStepOcrReview();if(afterRender)afterRender();});else if(afterRender)afterRender();
 },
 syncOcrFieldModes(){this.updateOcrView();},
 ocrSource(kind,view=this.data){const app=view.application;const key=kind==='id_front'?'identity_front':kind==='id_back'?'identity_back':kind;const material=app&&app.materials&&app.materials[key];return JSON.stringify(material?toObject(['uploaded','review','expires_at','object_id','sha256'].filter(k=>material[k]!==undefined).map(k=>[k,material[k]])):null);},
 clearOcrTimer(){if(this.ocrTimer!==undefined&&typeof clearTimeout==='function')clearTimeout(this.ocrTimer);this.ocrTimer=undefined;},
 stopOcrPoll(){this.clearOcrTimer();this.ocrPolling=false;this.ocrPollAttempt=0;},
 chainRecord(chain,stage,source){try{const telemetry=this.chainTelemetry||(this.chainTelemetry=createChainTelemetry());return telemetry.record(chain,stage,source&&typeof source==='object'?source:null);}catch(error){return null;}},
 submitUnknownState(){if(!this.submitUnknownUntil||!this.submitUnknownApplication)return null;if(this.data.application&&this.data.application.application===this.submitUnknownApplication)return {until:this.submitUnknownUntil,application:this.submitUnknownApplication};return null;},
 noteSubmitOutcome(error){const click=OWNER_WECHAT_CLICK.get(this);if(click&&!click.operationStarted)return;const diagnostic=error&&error.submissionDiagnostic;if(!diagnostic||!['wechat_apply','submit','wechat_submit_review'].includes(diagnostic.operation))return;this.chainRecord('submit','SUBMIT_04',diagnostic);if(diagnostic.code!=='PROVIDER_RESULT_UNKNOWN')return;this.submitUnknownUntil=Date.now()+SUBMIT_READBACK_COOLDOWN_MS;this.submitUnknownApplication=this.data.application&&this.data.application.application;},
 assertSubmitCooldown(operation){const state=this.submitUnknownState();if(!state||!shouldBlockResubmit(state,Date.now()))return;this.chainRecord('submit','SUBMIT_05',{reason:'READBACK_ONLY'});throw Error('提交结果待核实：5分钟冷却窗口内仅允许回读原申请状态收敛（readback_reconciled），不会自动重发；请点击“刷新原申请进度”读取结果。');},
 reconcileSubmitReadback(result){if(!this.submitUnknownUntil)return;// 切片v3：收敛只认 provider 回读观察值；冷却到期不是确认——未观察到收敛态则保持「未核实」与仅回读，不清态、不自动重提；后端 5min 防重窗口（assertSubmitCooldown）保留不动。
 if(!readbackReconciled(result)){this.chainRecord('submit','SUBMIT_05',{reason:'READBACK_ONLY'});return;}this.submitUnknownUntil=0;this.submitUnknownApplication=null;this.chainRecord('submit','SUBMIT_06',{reason:'READBACK_RECONCILED'});},
 waitForOcr(error){const d=error&&error.ocrDiagnostic;this.chainRecord('ocr','OCR_03',d||(error&&error.ocrCode==='OCR_EMPTY_RESPONSE'?{reason:'PROVIDER_EMPTY_RESPONSE'}:null));if(d&&d.retryable===false){this.stopOcrPoll();if(this.ocrCapture&&this.ocrCapture.original_locator&&this.ocrCapture.original_locator.current_material===true&&['JOB_NOT_FOUND','MATERIAL_JOB_NOT_FOUND','IDEMPOTENCY_CONFLICT'].includes(d.reason)){this.updateOcrView({ocrDiagnostic:d,ocrStatus:['JOB_NOT_FOUND','MATERIAL_JOB_NOT_FOUND'].includes(d.reason)?'没有找到这份照片的原识别结果，照片仍已保留；未重新识别或上传。':'这份照片有多份识别记录，暂时无法确定应恢复哪一份；未选择任何结果，也未重新识别。'});return;}const status=d.reason==='IDEMPOTENCY_CONFLICT'||['APPLICATION_REVISION_CHANGED','PROVIDER_VERSION_CHANGED','SOURCE_BINDING_CHANGED','ATTACHMENT_CHANGED','SOURCE_EXPIRED'].includes(d.reason)?'申请资料已更新，原识别结果需要重新核对。已暂停自动查询，原资料保留，请勿重复上传。':d.reason==='RATE_LIMITED'?'识别请求较多，已暂停自动查询。原资料保留，请稍后查看结果，勿重复上传。':d.reason==='AUTHENTICATION_FAILED'?'暂时无法核实识别结果的访问权限，已暂停自动查询。原资料保留，请先核对登录状态。':d.reason==='APPLICATION_ACCESS_DENIED'?(this.data.application&&this.data.application.status==='SUBMITTED'?'当前申请已提交，识别结果读取被拒绝，已暂停自动查询。原申请与材料保留，请勿重复上传或提交。':'当前申请的识别结果读取被拒绝，可能与申请状态或访问权限有关，已暂停自动查询。原申请与材料保留，请勿重复上传或提交。'):'暂时无法读取识别结果，已暂停自动查询。原资料保留，请联系管理员核对，勿重复上传。';this.updateOcrView({ocrDiagnostic:d,ocrStatus:status});return;}this.ocrPolling=true;const status=error&&error.networkKind?'网络连接暂时不稳定，正在继续查询识别结果，无需重新上传。':d&&d.request_retained===false?'识别结果还没返回，正在自动查询，请勿重复上传。':error&&error.ocrCode==='OCR_EMPTY_RESPONSE'?'识别服务本次返回空结果，原识别任务已保留，正在继续自动查询，无需重新上传。':error&&error.ocrCode==='OCR_UNAVAILABLE'?'识别服务暂时无法响应，正在继续查询，原材料无需重新上传。':d&&d.stage==='QUEUE'?'正在等待识别，请稍候，无需重新上传。':d&&d.stage==='EXECUTION'&&d.request_retained===true?'原识别任务仍在处理中，尚未取得可核对结果；耗时未确认，请勿重复上传。':'正在查询识别结果，请稍候，无需重新上传。';this.updateOcrView({ocrDiagnostic:d||null,ocrProgressState:'querying',ocrStatus:status});},
 pauseInvalidOcr(capture){if(this.ocrHidden||!this.current()||capture&&capture!==this.ocrCapture)return;this.stopOcrPoll();const a=this.data.application;const onlyDirty=this.data.dirty&&capture&&capture.session===this.session&&capture.scene===this.scene&&a&&capture.application===a.application&&capture.revision===a.revision&&capture.source===this.ocrSource(capture.document_type)&&(capture.session_generation===undefined||capture.session_generation===this.session.getGeneration())&&(!this.session.isAuthenticated||this.session.isAuthenticated());const sessionLost=this.session&&typeof this.session.isAuthenticated==='function'&&!this.session.isAuthenticated();this.updateOcrView({ocrConfirmed:false,...(onlyDirty?{}:{ocrRows:[]}),ocrStatus:onlyDirty?'当前资料有未保存修改，原识别查询已暂停；原任务标识已保留':!capture?'原识别请求标识不可用，无法查询原结果；请联系管理员核对原任务，勿重复上传':sessionLost?'原识别请求的登录状态已失效，已停止查询；原任务结果待核对，勿重复上传':'原识别请求与当前申请、材料或会话不一致，已停止查询；未创建新任务，请核对原任务'});},
 scheduleOcrPoll(){this.clearOcrTimer();const capture=this.ocrCapture;if(!this.ocrPolling||this.ocrHidden||this.ocrFlight)return;if(!this.ocrCurrent(capture)){this.pauseInvalidOcr(capture);return;}if(typeof setTimeout!=='function')return;const delay=[1000,2000,4000,8000][Math.min(this.ocrPollAttempt||0,3)];this.ocrPollAttempt=(this.ocrPollAttempt||0)+1;this.chainRecord('ocr','OCR_03',null);this.ocrTimer=setTimeout(async()=>{this.ocrTimer=undefined;if(!this.ocrPolling||this.ocrHidden)return;if(!this.ocrCurrent(capture)){this.pauseInvalidOcr(capture);return;}if(capture.job_id||capture.recovery){const missing=await this.readOcr();if(missing&&missing.explicit_first_key&&this.ocrCurrent(missing)&&missing.source!=='null'){const next={...missing,idempotency_key:missing.explicit_first_key,recovery:false};delete next.explicit_first_key;delete next.original_locator;this.ocrCapture=next;this.chainRecord('ocr','OCR_01',null);this.updateOcrView({ocrProgressState:'requesting',ocrStatus:'正在请求证照识别；结果仍需人工核对'});await this.resumeOcrSubmit(next);}}else if(capture.idempotency_key)await this.resumeOcrSubmit(capture);},delay);},
 onHide(){this.clearMediaStatusWait();if(this.directSelectionAttempt&&this.directSelectionAttempt.token===this.uploadViewToken){const attempt=this.directSelectionAttempt;this.uploadViewToken=null;this.directSelectionAttempt=null;this.ocrHidden=true;if(this.directOcrHints)delete this.directOcrHints[attempt.kind];const status=attempt.photo_confirmed?'本次识别回填已停止，照片已私密保存。':'本次识别回填已停止；照片保存结果请刷新原申请核对，不会自动重传。';this.updateOcrView({uploadFeedback:null,ocrProgressState:'',ocrStatus:status,status});}this.invalidateSigningQrForHide();this.cancelStepOcrReview();this.clearProviderPoll();this.privatePreviewCleanup();this.ocrHidden=true;this.clearUploadedOcrRestoreTimer();this.beginStepScroll();this.clearOcrTimer();if(this.ocrCapture)this.ocrRequest(this.ocrCapture);},
 ocrFeedback(error){const code=String(error&&error.ocrCode||error&&error.message||'');if(/REVOKED|CHANGED|EXPIRED|REVISION|BINDING/.test(code))return '暂时无法读取识别结果：资料或登录状态已变化，请先重新读取原申请；无需重新上传材料。';if(code==='OCR_UNAVAILABLE')return '暂时无法读取识别结果，原材料无需重新上传，请稍后查询原任务。';if(error&&error.code==='ACCESS_DENIED'||/AUTH|SESSION|PERMISSION|LOGIN/.test(code))return '识别结果的认证或权限验证未通过，请重新登录后读取原申请；无需重新上传材料。';return '暂时无法读取识别结果，请稍后查询原任务；原材料无需重新上传。';},
 async ocrCall(action,extra){this.clearUploadedOcrRestoreTimer();const app=this.data.application;if(!app)throw new Error('APPLICATION_REQUIRED');const request=this.session.merchant(this.scene,'ocr',{action,application:app.application,...extra});this.ocrTransport=request;return request;},
 holdOcrLocal(capture){return {...capture,local_state:{edits:{...(this.ocrSuggestionEdits||{})},rows:(this.data.ocrRows||[]).map(row=>({...row})),edit_version:this.ocrSuggestionEditVersion||0,confirmation_revision:this.ocrConfirmationRevision||0,edit_group:this.data.editMaterialGroup||''}};},
 restoreOcrLocal(capture){const local=capture.local_state||{},keys=ocrInputFields(capture.document_type);this.ocrSuggestionEdits=toObject(Object.entries(local.edits||{}).filter(([key,value])=>keys.includes(key)&&typeof value==='string'));this.ocrSuggestionEditVersion=local.edit_version||0;this.ocrConfirmationRevision=local.confirmation_revision||0;this.ocrFocus=null;this.ocrDeferredFocusedKey=null;return {ocrRows:(local.rows||[]).filter(row=>keys.includes(row.key)).map(row=>({...row})),ocrConfirmed:false,editMaterialGroup:local.edit_group||''};},
 invalidateOcr(status){this.ocrCommittedLicenseRead=null;if(this.ocrCapture){this.ocrHeldCaptures=this.ocrHeldCaptures||{};this.ocrHeldCaptures[this.ocrCapture.document_type]=this.holdOcrLocal(this.ocrCapture);}this.stopOcrPoll();this.ocrGeneration=(this.ocrGeneration||0)+1;this.ocrCapture=null;this.ocrConfirmationRevision=0;this.ocrSuggestionEdits={};this.ocrDeferredFocusedKey=null;this.ocrSuggestionEditVersion=(this.ocrSuggestionEditVersion||0)+1;this.updateOcrView({ocrConfirmed:false,ocrRows:[],ocrJob:'',ocrDiagnostic:null,ocrStatus:status||'原识别查询已停止，未创建新任务；识别结果须重新核对'});},
 ocrRequest(capture){this.ocrRequestGeneration=(this.ocrRequestGeneration||0)+1;const next={...capture,request_generation:this.ocrRequestGeneration};this.ocrCapture=next;return next;},
 ocrCurrent(capture,view=this.data){return !!capture&&(capture.document_type!=='bank_card'||Number.isSafeInteger(capture.bound_provider_version)&&capture.bound_provider_version===this.version)&&!this.ocrHidden&&this.current()&&(!this.session||typeof this.session.isAuthenticated!=='function'||this.session.isAuthenticated())&&(capture.source===undefined||capture.source===this.ocrSource(capture.document_type))&&view.application&&(capture.session===undefined||capture.session===this.session)&&(capture.scene===undefined||capture.scene===this.scene)&&(capture.session_generation===undefined||capture.session_generation===this.session.getGeneration())&&capture.application===view.application.application&&capture.revision===view.application.revision&&!view.dirty&&capture.generation===this.ocrGeneration&&capture.request_generation===this.ocrRequestGeneration&&capture===this.ocrCapture&&capture.job_id===view.ocrJob&&capture.document_type===view.ocrKind;},
 async acceptCommittedLicenseOcr(job,application,kind){
  const source=this.ocrSource(kind);
  if(!this.current()||!this.session||this.ocrHidden||this.data.application!==application||this.data.dirty||!source||source==='null')return;
  if(!job||typeof job.job_id!=='string'||!/^[A-Za-z0-9_-]{1,128}$/.test(job.job_id)||!['queued','processing','needs_review','confirmed','failed'].includes(job.status)){
   this.updateOcrView({ocrKind:kind,ocrProgressState:'failed',ocrStatus:'营业执照照片已保存，但未取得本次识别回执；请重新读取原申请，不会自动再次识别或上传。'});
   return;
  }
  const capture=this.ocrRequest({source,application:application.application,revision:application.revision,job_id:job.job_id,
   document_type:kind,session:this.session,session_generation:typeof this.session.getGeneration==='function'?this.session.getGeneration():undefined,
   scene:this.scene,generation:this.ocrGeneration,idempotency_key:''});
  const pending=['queued','processing'].includes(job.status),snapshot=job.snapshot;
  if(!pending&&snapshot&&snapshot.job_id===job.job_id&&snapshot.status===job.status&&snapshot.document_type===kind&&
     snapshot.application_revision===String(application.revision)&&(snapshot.provider_version===null||snapshot.provider_version===this.version)){
   this.ocrCommittedLicenseRead={capture,snapshot};
  }
  this.ocrPolling=true;
  this.updateOcrView({ocrKind:kind,ocrJob:job.job_id,ocrProgressState:pending?job.status:'reading',
   ocrStatus:pending?'正在识别中，请稍候。结果返回后会自动显示。':'照片已保存，正在读取识别结果'});
  if(!this.ocrFlight)await this.readOcr();
 },
 async retryCommittedFailedLicense(capture){
  if(this.ocrFlight||!this.ocrCurrent(capture)||!capture.job_id||!/^[A-Za-z0-9_-]{1,96}$/.test(capture.job_id))return;
  this.stopOcrPoll();this.ocrFlight=true;
  let job;
  try{const r=await this.ocrCall('read',{job_id:capture.job_id});job=r&&r.result;}
  catch(error){if(this.ocrCurrent(capture))this.updateOcrView({ocrStatus:this.ocrFeedback(error)});return;}
  finally{this.ocrFlight=false;}
  if(!this.ocrCurrent(capture))return;
  if(!job||job.status!=='failed'||job.job_id!==capture.job_id||job.document_type!==capture.document_type||
    job.application_revision!==String(capture.revision)||!(job.provider_version===null||job.provider_version===this.version))return this.readOcr();
  const next={source:capture.source,application:capture.application,revision:capture.revision,
   job_id:'',document_type:capture.document_type,session:capture.session,session_generation:capture.session_generation,
   scene:capture.scene,idempotency_key:'mini-license-retry-'+capture.job_id,generation:this.ocrGeneration};
  this.ocrRequest(next);
  this.ocrSuggestionEdits={};this.ocrConfirmationRevision=0;this.ocrPolling=true;
  this.updateOcrView({ocrJob:'',ocrRows:[],ocrConfirmed:false,ocrDiagnostic:null,ocrProgressState:'requesting',ocrStatus:'正在重新识别营业执照；不会重新上传'});
  await this.resumeOcrSubmit(this.ocrCapture);
 },
 async recognizeCurrentDocument(kind,options={}){
  const active=this.ocrCapture;if(active&&active.document_type!==kind)this.retainOcrDisplay(active);
  let previous=active&&active.document_type===kind?active:this.ocrHeldCaptures&&this.ocrHeldCaptures[kind];
  const explicitlyCheckingCurrent=options.newIntent===true&&options.existingMaterial===true&&options.explicitRecognition===true;
  const previousProvider=previous&&(previous.seen_provider_version===undefined?previous.bound_provider_version:previous.seen_provider_version);
  const providerDrift=previous&&previousProvider!==undefined&&previousProvider!==this.version;
  if(previous&&(!this.ocrCurrent(previous)||explicitlyCheckingCurrent&&providerDrift)){
   const a=this.data.application;
   const authenticated=this.session&&(!this.session.isAuthenticated||this.session.isAuthenticated());
   const sameSession=previous.session===this.session&&(previous.session_generation===undefined||previous.session_generation===this.session.getGeneration());
   const sameSource=a&&previous.application===a.application&&previous.revision===a.revision&&previous.source===this.ocrSource(kind)&&previous.scene===this.scene;
   const sameMaterial=a&&previous.application===a.application&&previous.source===this.ocrSource(kind)&&previous.scene===this.scene;
   if(explicitlyCheckingCurrent&&sameSession&&sameMaterial&&!this.data.dirty&&authenticated&&
      (previous.revision!==a.revision||providerDrift)&&!previous.pending_confirmation&&!previous.recovery_apply_pending&&!previous.recovery_confirmation){
    // A later document may have advanced the application revision. Keep the old
    // capture as history, but resolve only the current binding for this click.
    previous=null;
   }else if(sameSession&&sameSource&&!this.data.dirty&&authenticated){
    // Preserve the group being left before restoring another group's original pointer.
    if(active&&active!==previous){this.ocrHeldCaptures=this.ocrHeldCaptures||{};this.ocrHeldCaptures[active.document_type]=this.holdOcrLocal(active);}
    previous={...previous,generation:this.ocrGeneration,request_generation:(this.ocrRequestGeneration||0)+1};
    this.ocrCapture=previous;this.ocrRequestGeneration=previous.request_generation;
    this.updateOcrView({ocrKind:kind,ocrJob:previous.job_id,...this.restoreOcrLocal(previous)});
   }else if(options.newIntent===true&&sameSession&&authenticated&&!this.data.dirty&&a&&previous.application===a.application&&previous.scene===this.scene&&previous.source===this.ocrSource(kind)&&(previous.job_id||previous.idempotency_key)){
    return this.recoverCurrentDocument(previous);
   }else if(options.newIntent===true&&authenticated&&!this.data.dirty&&a&&(!sameSession||!sameSource)){
    // A deliberate click or confirmed replacement upload is a new intent, not a
    // background retry. Never send an old job under its changed binding.
    previous=null;
   }else{
    if(previous===this.ocrCapture)this.pauseInvalidOcr(previous);
    else this.updateOcrView({ocrStatus:'原识别任务对应的申请、材料或会话已变化，原查询已停止；可明确选择识别当前材料'});
    return;
   }
  }
  if(previous&&this.ocrCurrent(previous)){
   if(previous.job_id){
    if(kind==='business_license'&&options.explicitRecognition===true&&this.data.ocrProgressState==='failed')return this.retryCommittedFailedLicense(previous);
    return this.readOcr();
   }
   if(previous.idempotency_key)return this.resumeOcrSubmit(previous);
  }
  this.invalidateOcr();if(active&&active.document_type!==kind)this.ocrFocus=null;
  if(this.data.dirty){this.setData({ocrStatus:'请先保存并重新读取当前申请，再识别证照'});return;}
  let capture={source:this.ocrSource(kind),application:this.data.application.application,revision:this.data.application.revision,bound_provider_version:this.version,job_id:'',document_type:kind,session:this.session,session_generation:typeof this.session.getGeneration==='function'?this.session.getGeneration():undefined,scene:this.scene,idempotency_key:'mini-ocr-'+Date.now()+'-'+Math.random().toString(36).slice(2),generation:this.ocrGeneration,request_generation:(this.ocrRequestGeneration||0)+1};
  this.ocrRequestGeneration=capture.request_generation;this.ocrCapture=capture;
  if(options.existingMaterial===true&&options.uploadedMaterial!==true){
   const firstKey=capture.idempotency_key.replace('mini-ocr-','mini-first-');capture.original_locator={current_material:true};capture.idempotency_key='';if(options.explicitRecognition===true)capture.explicit_first_key=firstKey;
   const missing=await this.recoverCurrentDocument(capture);
   // Only this explicit click may start the first job for the verified current binding.
   // Background restoration stays read-only; known jobs and pending keys returned above.
   if(options.explicitRecognition!==true||!missing||!this.ocrCurrent(missing)||missing.source==='null')return;
   capture={...capture,idempotency_key:firstKey,generation:missing.generation,request_generation:missing.request_generation};
   delete capture.original_locator;delete capture.explicit_first_key;this.ocrCapture=capture;
  }
  this.chainRecord('ocr','OCR_01',null);this.ocrPolling=true;this.updateOcrView({ocrKind:kind,ocrProgressState:'requesting',ocrStatus:'正在请求证照识别；结果仍需人工核对'});
  return this.resumeOcrSubmit(capture);
 },
 async recoverCurrentDocument(previous){
  if(this.ocrFlight||this.ocrHidden||this.data.dirty||!previous)return;
  const a=this.data.application,authenticated=this.session&&(!this.session.isAuthenticated||this.session.isAuthenticated());
  if(!a||!authenticated||previous.session!==this.session||(previous.session_generation!==undefined&&previous.session_generation!==(typeof this.session.getGeneration==='function'?this.session.getGeneration():undefined))||previous.application!==a.application||previous.scene!==this.scene||previous.source!==this.ocrSource(previous.document_type))return;
  this.retainOcrDisplay(this.ocrCapture);this.stopOcrPoll();
  const local=previous===this.ocrCapture?this.holdOcrLocal(previous):previous;
  if(previous.recovery_apply_pending===true){
   // Unknown save outcome: retain the exact original receipt, never mint a new intent.
   if(previous.recovery!==true||typeof previous.recovery_key!=='string'||!previous.recovery_key||typeof previous.recovery_writeback_key!=='string'||!previous.recovery_writeback_key||!previous.recovery_confirmation||typeof previous.recovery_confirmation.confirmation_key!=='string'||!previous.recovery_confirmation.confirmation_key||!Number.isSafeInteger(previous.recovery_confirmation_revision)||previous.recovery_confirmation_revision<1){this.setData({ocrStatus:'原保存回执信息不完整，已停止操作并保留草稿；请联系管理员核对，勿重新确认或上传。'});return;}
   const capture={...previous,revision:a.revision,generation:this.ocrGeneration,request_generation:(this.ocrRequestGeneration||0)+1};
   this.ocrCapture=capture;this.ocrRequestGeneration=capture.request_generation;
   this.updateOcrView({...this.restoreOcrLocal(local),ocrKind:capture.document_type,ocrJob:capture.job_id,ocrConfirmed:false,ocrProgressState:'querying',ocrStatus:'正在查询原保存回执；不会重复确认或重新上传。'});
   return this.readOcr();
  }
  const capture={...previous,...(previous.document_type==='bank_card'?{bound_provider_version:this.version,recovery_binding:null,recovery_confirmation_revision:undefined,recovery_writeback_key:undefined,recovery_apply_pending:false,auto_save_fields:null,pending_confirmation_fields:undefined}:{}),original_locator:previous.original_locator||(previous.job_id?{job_id:previous.job_id}:{original_key:previous.idempotency_key}),recovery_key:'mini-recovery-'+Date.now()+'-'+Math.random().toString(36).slice(2),recovery:true,recovery_confirmation:null,pending_confirmation:false,revision:a.revision,generation:this.ocrGeneration,request_generation:(this.ocrRequestGeneration||0)+1};
  this.ocrCapture=capture;this.ocrRequestGeneration=capture.request_generation;
  // A new bank recovery key is a fresh view, not a replay of the old receipt or its human authority.
  if(capture.document_type==='bank_card')for(const cache of [this.ocrHeldCaptures,this.ocrDisplayCaptures])if(cache)delete cache.bank_card;
  const restored=this.restoreOcrLocal(capture.document_type==='bank_card'?{}:local);this.updateOcrView({...restored,ocrKind:capture.document_type,ocrJob:capture.job_id,ocrConfirmed:false,ocrProgressState:'reading',ocrStatus:'正在读取原识别结果，不会重新识别或上传。'});
  return this.readOcr();
 },
 bankRecoveryBindingMatches(capture,binding){
  const material=this.data.application&&this.data.application.materials&&this.data.application.materials.bank_card;
  return !!binding&&typeof binding==='object'&&!Array.isArray(binding)&&Object.keys(binding).sort().join(',')==='application_revision,attachment_id,content_sha256,document_type,provider_version'&&
   binding.application_revision===String(capture.revision)&&binding.provider_version===capture.bound_provider_version&&binding.provider_version===this.version&&binding.document_type==='bank_card'&&
   typeof binding.attachment_id==='string'&&!!binding.attachment_id&&typeof binding.content_sha256==='string'&&/^[a-f0-9]{64}$/.test(binding.content_sha256)&&!!material&&
   (material.object_id===undefined||material.object_id===binding.attachment_id)&&(material.sha256===undefined||material.sha256===binding.content_sha256)&&
   (!capture.recovery_binding||sameOcrFields(capture.recovery_binding,binding));
 },
 async recoveryResult(capture){
  if(capture.document_type==='bank_card'){
   const locator=capture.original_locator,keys=locator&&Object.keys(locator);
   if(!this.ocrCurrent(capture)||!keys||keys.length!==1||!(keys[0]==='current_material'&&locator.current_material===true||['job_id','original_key'].includes(keys[0])&&typeof locator[keys[0]]==='string'&&!!locator[keys[0]]))throw Error('OCR_JOB_BINDING_CHANGED');
   const r=await this.ocrCall('recover_view',{document_type:'bank_card',locator:{...locator},recovery_key:capture.recovery_key});
   if(!this.ocrCurrent(capture))return null;
   const v=r&&r.result;
   if(!v||v.recovery_id!==capture.recovery_key||v.revision!==1||v.onboarding_application_id!==undefined&&v.onboarding_application_id!==capture.application||typeof v.job_id!=='string'||!v.job_id||v.status!=='needs_review'||v.confirmed!==false||v.requires_human_confirmation!==true||!this.bankRecoveryBindingMatches(capture,v.binding)||locator.job_id&&v.job_id!==locator.job_id)throw Error('OCR_JOB_BINDING_CHANGED');
   capture.recovery_binding={...v.binding};
   // Normalize bank rows only; retain the recovery receipt and human-confirmation protocol.
   return {result:{...v,document_type:'bank_card',application_revision:v.binding.application_revision,provider_version:v.binding.provider_version}};
  }
  if(this.ocrCurrent(capture)){this.stopOcrPoll();this.updateOcrView({ocrDiagnostic:null,ocrProgressState:'',ocrStatus:'请点击识别原图；如原图已不在当前设备，请重新选择或手动填写。已保存照片仍保留。'});}
  return null;
 },
 async confirmRecovery(){
  const capture=this.ocrCapture;if(!capture||!capture.recovery||!this.ocrCurrent(capture)||this.ocrFlight)return;
  const fields=toObject(this.ocrConfirmationRows().filter(r=>ocrInputFields(capture.document_type).includes(r.key)&&typeof r.value==='string'&&r.value.trim()).map(r=>[r.key,r.value]));
  if(!Object.keys(fields).length)return;
  const editVersion=this.ocrSuggestionEditVersion||0;
  const request=capture.recovery_confirmation&&sameOcrFields(capture.recovery_confirmation.fields,fields)?capture.recovery_confirmation:{recovery_id:capture.recovery_key,revision:1,fields,confirmation_key:'mini-recovery-confirm-'+Date.now()+'-'+Math.random().toString(36).slice(2)};
  const next=this.ocrRequest({...capture,recovery_confirmation:request});this.ocrPolling=true;this.ocrFlight=true;
  try{const r=await this.ocrCall('recover_confirm',request);if(!this.ocrCurrent(next))return;const v=r.result;
   if(!v||v.recovery_id!==next.recovery_key||v.confirmation_id!==request.confirmation_key||v.status!=='confirmed'||!sameOcrFields(v.confirmed_fields,request.fields)||v.binding.application_revision!==String(next.revision)||v.binding.provider_version!==this.version||next.document_type==='bank_card'&&(!this.bankRecoveryBindingMatches(next,v.binding)||v.confirmation_revision!==1))throw Error('OCR_CONFIRMATION_METADATA_INVALID');
   if(editVersion!==(this.ocrSuggestionEditVersion||0)){this.ocrCapture={...this.ocrCapture,recovery_confirmation:null};this.updateOcrView({ocrConfirmed:false,ocrStatus:'核对期间内容发生变化，请核对当前显示内容后再确认。'});return;}
   this.ocrCapture={...next,recovery_confirmation:request,recovery_confirmation_revision:v.confirmation_revision};this.stopOcrPoll();this.ocrSuggestionEdits={};this.updateOcrView({ocrConfirmed:true,ocrStatus:'当前资料已核对，可保存到空白项；原有内容不会覆盖。'});
  }catch(error){if(this.ocrCurrent(next)){this.waitForOcr(error);this.updateOcrView({ocrConfirmed:false});}}finally{this.ocrFlight=false;if(this.ocrPolling)this.scheduleOcrPoll();}
 },
 async applyRecovery(){
  const capture=this.ocrCapture;if(!capture||!capture.recovery||(!this.data.ocrConfirmed&&!capture.recovery_apply_pending)||!this.ocrCurrent(capture)||!capture.recovery_confirmation||this.ocrFlight)return;
  const key=capture.recovery_writeback_key||'mini-recovery-save-'+Date.now()+'-'+Math.random().toString(36).slice(2);
  const requestCapture=this.ocrRequest({...capture,recovery_writeback_key:key,recovery_apply_pending:true});this.ocrPolling=true;this.ocrFlight=true;
  try{await this.ocrCall('recover_apply',{recovery_id:capture.recovery_key,confirmation_id:capture.recovery_confirmation.confirmation_key,confirmation_revision:capture.recovery_confirmation_revision,writeback_key:key});
   if(!this.ocrCurrent(requestCapture))return;
   // The original save receipt is now known. Retire only this completed local
   // intent, so a rebuilt page cannot re-enqueue its pending apply indefinitely.
   const completed=c=>c&&c.session===requestCapture.session&&c.application===requestCapture.application&&c.recovery_writeback_key===key;
   for(const cache of [this.ocrHeldCaptures,this.ocrDisplayCaptures])if(cache&&completed(cache[capture.document_type]))delete cache[capture.document_type];
   const remembered=OCR_PAGE_RESUME.get(this.session);if(remembered&&remembered.application===capture.application&&remembered.recovery_writeback_key===key)OCR_PAGE_RESUME.delete(this.session);
   this.ocrCapture=null;this.setData({ocrConfirmed:false});
   await this.load(capture.application,()=>this.current()&&requestCapture.session===this.session&&requestCapture.session_generation===(typeof this.session.getGeneration==='function'?this.session.getGeneration():undefined)&&this.data.application&&this.data.application.application===capture.application);this.updateOcrView({ocrConfirmed:false,ocrStatus:'已保存核对后的空白项，原有资料未覆盖。其他证件请重新读取原结果并核对。'});
  }catch(error){if(this.ocrCurrent(requestCapture))this.waitForOcr(error);}finally{this.ocrFlight=false;if(this.ocrPolling)this.scheduleOcrPoll();else this.scheduleUploadedOcrRestore();}
 },
 async resumeOcrSubmit(capture){if(this.ocrFlight||!this.ocrCurrent(capture))return;this.clearOcrTimer();this.ocrPolling=true;this.ocrFlight=true;let read=false,recover=false;try{const r=await this.ocrCall('submit',{document_type:capture.document_type,idempotency_key:capture.idempotency_key});if(!this.ocrCurrent(capture))return;if(typeof (r.result&&r.result.job_id)!=='string'||!r.result.job_id||r.result.job_id.length>128)throw Error('OCR_JOB_BINDING_INVALID');this.chainRecord('ocr','OCR_02',r&&r.ocr_diagnostic);this.ocrCapture={...capture,job_id:r.result.job_id};this.updateOcrView({ocrJob:r.result.job_id});read=true;}catch(error){if(this.ocrCurrent(capture)){const diag=error&&error.ocrDiagnostic;if(diag&&diag.reason==='IDEMPOTENCY_CONFLICT'&&diag.retryable===false&&!capture.recovery){recover=true;this.stopOcrPoll();}if(error&&error.networkKind||['OCR_REQUEST_PENDING','OCR_UNAVAILABLE'].includes(String(error&&error.ocrCode||error&&error.message)))this.waitForOcr(error);else this.invalidateOcr(this.ocrFeedback(error));}}finally{this.ocrFlight=false;if(capture===this.ocrCapture&&!this.ocrCurrent(capture))this.pauseInvalidOcr(capture);if(!read&&this.ocrPolling)this.scheduleOcrPoll();}if(recover)await this.recoverCurrentDocument(capture);else if(read)await this.readOcr();},
 directHintBinding(kind,application){
  const session=this.session,source=this.ocrSource(kind,{application});
  if(!session||!application||!source||source==='null')return null;
  return {application:application.application,revision:application.revision,provider_version:this.version,source,session,scene:this.scene,epoch:this.epoch,
   generation:typeof session.getGeneration==='function'?session.getGeneration():undefined};
 },
 directHintBindingMatches(kind,bound,application=this.data.application){
  const current=this.directHintBinding(kind,application);
  return !!current&&!!bound&&this.current()&&!this.ocrHidden&&
   (!current.session.isAuthenticated||current.session.isAuthenticated())&&
   current.application===bound.application&&current.revision===bound.revision&&current.provider_version===bound.provider_version&&current.source===bound.source&&
   current.session===bound.session&&current.scene===bound.scene&&current.epoch===bound.epoch&&current.generation===bound.generation;
 },
 setDirectOcrHint(kind,fields,currentAttempt,committed){
  // Valid OCR fields belong to the authenticated application, not a saved material/revision.
  const session=this.session,application=this.data.application&&this.data.application.application,
   scene=this.scene,epoch=this.epoch,generation=freshGeneration(session);
  const hint={fields,bound:null,currentAttempt};
  hint.active=()=>this.directOcrHints&&this.directOcrHints[kind]===hint&&this.current()&&!this.ocrHidden&&
   this.session===session&&this.scene===scene&&this.epoch===epoch&&freshGeneration(session)===generation&&
   (!session.isAuthenticated||session.isAuthenticated())&&this.data.application&&
   this.data.application.application===application&&['DRAFT','CORRECTION_REQUIRED'].includes(this.data.application.status);
  this.directOcrHints[kind]=hint;
 },
 advanceDirectOcrHints(uploadedKind,before,after,currentAttempt){
  if(!before||!after||after.application!==before.application||after.revision!==before.revision+1)return;
  for(const [kind,hint] of Object.entries(this.directOcrHints||{})){
   const next=this.directHintBinding(kind,after);
   if(!next)continue;
   if(kind===uploadedKind){
    if(hint.currentAttempt===currentAttempt&&!hint.bound)hint.bound=next;
   }else if(hint.bound&&next.source===hint.bound.source&&this.directHintBindingMatches(kind,hint.bound,before)){
    hint.bound=next;
   }
  }
 },
 rememberDirectOriginal(kind,path,digest,application){
  const app=application,source=this.ocrSource(kind,{application}),session=this.session;
  if(!app||!session||typeof path!=='string'||!path||source==='null'||!source||!/^[a-f0-9]{64}$/.test(digest))return;
  this.directOriginals=this.directOriginals||Object.create(null);
  this.directOriginals[kind]={application:app.application,revision:app.revision,version:this.version,
   session,generation:typeof session.getGeneration==='function'?session.getGeneration():undefined,
   scene:this.scene,source,path,digest};
 },
 async retryDirectOriginal(kind){
  if(kind==='bank_card')return;
  const app=this.data.application,session=this.session,record=this.directOriginals&&this.directOriginals[kind];
  const generation=()=>session&&typeof session.getGeneration==='function'?session.getGeneration():undefined;
  const active=()=>!!record&&!!app&&!!session&&this.current()&&!this.ocrHidden&&
   this.session===session&&record.session===session&&record.generation===generation()&&
   (!session.isAuthenticated||session.isAuthenticated())&&this.scene===record.scene&&
   this.version===record.version&&this.data.application&&this.data.application.application===record.application&&
   this.data.application.revision===record.revision&&this.ocrSource(kind)===record.source&&
   this.directOriginals&&this.directOriginals[kind]===record;
  const choose=()=>this.updateOcrView({ocrJob:'',ocrRows:[],ocrConfirmed:false,ocrDiagnostic:null,
   ocrProgressState:'',ocrStatus:'原图不在当前设备的临时文件中，请重新选择原图或手动填写。已保存照片仍保留。'});
  if(!active()){choose();return;}
  if(this.directOcrRetry===record)return;
  this.directOcrRetry=record;
  const finishBankFeedback=this.beginBankOcrFeedback(kind,active);
  try{
   const pickedAt=clientOcrClock();
   let original,proof,digest;
   try{
    const prepared=await directOriginal(wx,record.path,active);
    if(!active())return;if(prepared.ocrTooLarge){choose();return;}
    original=wx.base64ToArrayBuffer(prepared.content);
    proof=directProof((operation,params)=>session.merchant(record.scene||'','onboarding',{operation,params}),
     record.application,record.revision,record.version);
    digest=proof.sha256(original);
   }catch(_){if(active())choose();return;}
   if(!active())return;
   if(digest!==record.digest){choose();return;}
   this.directOcrHints=this.directOcrHints||{};this.directOcrTimings=this.directOcrTimings||{};
   this.updateOcrView({ocrJob:'',ocrRows:[],ocrConfirmed:false,ocrDiagnostic:null,
    ocrProgressState:'',ocrStatus:'正在识别原图'});
   const attempt=startDirectOcr({kind,original,sha256:()=>digest,signDigest:proof.signDigest,
    savePrivate:()=>null,onSave:()=>{},request:arg=>wx.request(arg),isCurrent:active,
    onSuggestion:result=>{
     if(!active()){finishBankFeedback();return false;}
     finishBankFeedback(false);
     if(!result||!result.fields||!Object.keys(result.fields).length){
      this.updateOcrView({ocrStatus:'未取得识别建议，可手动填写'});return false;
     }
     this.setDirectOcrHint(kind,result.fields,active,true);
     return new Promise(resolve=>this.updateOcrView({ocrStatus:'识别建议，请人工核对'},()=>{
      const visible=(this.data.materialGroups||[]).some(g=>(g.fields||[]).some(f=>{
       const k=f.ocrDirect===kind&&this.ocrPathKey(f.path,kind);
       return !!k&&typeof result.fields[k]==='string'&&!!result.fields[k]&&!!f.value;
      }));
      resolve(active()&&visible);
     }));
    },timing:{pickedAt,now:clientOcrClock,hashRequestId:id=>typeof id==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(id)?proof.sha256(Uint8Array.from(Array.from(id,ch=>ch.charCodeAt(0))).buffer):null,record:r=>{if(active())this.directOcrTimings[kind]=r;}}
   });
   return await attempt.ocr;
  }finally{finishBankFeedback();if(this.directOcrRetry===record)this.directOcrRetry=null;}
 },
 recognizeDocument(e){const kind=e.currentTarget.dataset.kind;if(!['business_license','id_front','id_back'].includes(kind)||!this.data.application)return;return this.run(()=>this.retryDirectOriginal(kind));},
 async readOcr(){if(this.ocrFlight||this.ocrHidden)return;if(this.ocrCapture&&this.ocrCapture.recovery_apply_pending)return this.applyRecovery();this.clearOcrTimer();let capture=this.ocrCapture,missingCurrentMaterialJob=null;if(!capture||(!capture.job_id&&!capture.recovery)||!this.ocrCurrent(capture)){if(!capture||capture===this.ocrCapture)this.invalidateOcr('申请版本已变化，请重新读取并识别');return;}const committed=this.ocrCommittedLicenseRead;
 if(committed)this.ocrCommittedLicenseRead=null;
 const uploadSnapshot=committed&&committed.capture===capture?committed.snapshot:null;
 capture=this.ocrRequest(capture);this.ocrPolling=true;this.ocrFlight=true;try{const r=uploadSnapshot?{result:uploadSnapshot}:capture.recovery?await this.recoveryResult(capture):await this.ocrCall('read',{job_id:capture.job_id});if(!r||!this.ocrCurrent(capture))return;const result=r.result;if(capture.recovery){capture={...capture,recovery:capture.document_type==='bank_card',ocr_rebound_same_version:true,job_id:result.job_id};delete capture.explicit_first_key;this.ocrCapture=capture;this.updateOcrView({ocrJob:result.job_id});}if(result.job_id!==capture.job_id||result.document_type!==capture.document_type||capture.document_type==='bank_card'&&result.provider_version!==capture.bound_provider_version||typeof result.application_revision!=='string'||result.application_revision!==String(capture.revision)||!(result.provider_version===null||Number.isSafeInteger(result.provider_version)&&result.provider_version>=0))throw new Error('OCR_JOB_BINDING_CHANGED');const inputFields=ocrInputFields(capture.document_type);if(!inputFields.length)throw Error('OCR_DOCUMENT_NOT_SUPPORTED');const allowed=capture.document_type==='business_license'?[...inputFields,'business_scope']:inputFields;let values,confirmationRevision=0;if(result.status==='confirmed'){if(!Number.isSafeInteger(result.confirmation_revision)||result.confirmation_revision<1||result.confirmation_revision>=Number.MAX_SAFE_INTEGER||!result.confirmed_fields||typeof result.confirmed_fields!=='object'||Array.isArray(result.confirmed_fields))throw Error('OCR_CONFIRMATION_METADATA_INVALID');const keys=Object.keys(result.confirmed_fields);if(!keys.length||keys.some(key=>!allowed.includes(key)||typeof result.confirmed_fields[key]!=='string'))throw Error('OCR_CONFIRMATION_METADATA_INVALID');values=result.confirmed_fields;confirmationRevision=result.confirmation_revision;}else{values=toObject(inputFields.filter(key=>result.fields&&result.fields[key]&&typeof result.fields[key].value==='string').map(key=>[key,result.fields[key].value]));if(result.confirmation_revision!==undefined){if(!Number.isSafeInteger(result.confirmation_revision)||result.confirmation_revision<0||result.confirmation_revision>=Number.MAX_SAFE_INTEGER)throw Error('OCR_CONFIRMATION_METADATA_INVALID');confirmationRevision=result.confirmation_revision;}}const privateDraft=this.ocrDrafts&&this.ocrDrafts[capture.document_type];const privateEdits=privateDraft&&privateDraft.fields||{};const pendingDraftEdits=result.status==='confirmed'&&Object.entries(privateEdits).filter(([,v])=>typeof v==='string'&&v.trim()).every(([k,v])=>result.confirmed_fields&&result.confirmed_fields[k]===v)?{}:privateEdits;let edits=toObject(Object.entries({...pendingDraftEdits,...(this.ocrSuggestionEdits||{})}).filter(([key,value])=>inputFields.includes(key)&&typeof value==='string'));this.ocrSuggestionEdits=edits;
const pendingMatched=result.status==='confirmed'&&capture.pending_confirmation&&capture.pending_confirmation_revision===confirmationRevision&&capture.pending_confirmation_fields&&sameOcrFields(capture.pending_confirmation_fields,result.confirmed_fields)&&capture.pending_confirmation_provider_version===result.provider_version;
const pendingConfirmation=capture.pending_confirmation===true&&!pendingMatched;
if(pendingMatched&&capture.pending_confirmation_edit_version===(this.ocrSuggestionEditVersion||0)){this.ocrSuggestionEdits={};edits=this.ocrSuggestionEdits;}
// A server read is a full snapshot, not an append-only row list. Only human edits survive missing keys.
let focusedValueHeld=false;
if(this.ocrFocus&&this.ocrFocus.kind==='field'&&this.ocrFocus.capture&&this.ocrFocus.capture.document_type===capture.document_type&&this.ocrFocus.capture.idempotency_key===capture.idempotency_key&&this.ocrFocus.capture.session===capture.session&&this.ocrFocus.capture.session_generation===capture.session_generation&&this.ocrFocus.capture.scene===capture.scene&&this.ocrFocus.capture.application===capture.application&&this.ocrFocus.capture.revision===capture.revision&&this.ocrFocus.capture.source===capture.source){const key=this.ocrPathKey(this.ocrFocus.path,capture.document_type);if(key&&!Object.prototype.hasOwnProperty.call(edits,key)&&values[key]!==this.ocrFocus.value){values={...values,[key]:this.ocrFocus.value};this.ocrDeferredFocusedKey=key;focusedValueHeld=true;}}
if(this.ocrFocus&&this.ocrFocus.kind==='suggestion'){const focused=this.data.ocrRows.find(row=>row.key===this.ocrFocus.key);if(focused&&inputFields.includes(focused.key)&&!Object.prototype.hasOwnProperty.call(edits,focused.key)&&(!Object.prototype.hasOwnProperty.call(values,focused.key)||values[focused.key]!==focused.value)){values={...values,[focused.key]:focused.value};this.ocrDeferredFocusedKey=focused.key;focusedValueHeld=true;}}
values={...values,...toObject(Object.keys(edits).filter(key=>inputFields.includes(key)&&typeof edits[key]==='string').map(key=>[key,edits[key]]))};
const confirmed=result.status==='confirmed'&&!pendingConfirmation&&!focusedValueHeld&&Object.keys(edits).length===0;
this.chainRecord('ocr','OCR_04',result&&result.ocr_diagnostic);const completeSnapshot=['needs_review','confirmed'].includes(result.status);
const rows=inputFields.filter(key=>completeSnapshot||Object.prototype.hasOwnProperty.call(values,key)&&typeof values[key]==='string').map(key=>({key,label:({account_number:'银行卡号（需人工核对）',account_bank:'卡面银行名称（需人工核对）',company_name:'主体名称',credit_code:'统一社会信用代码',legal_representative:'法定代表人',registered_address:'证件地址',id_name:'姓名',id_number:'身份证号码',issuing_authority:'签发机关（仅留存核对，不提交微信字段）',valid_from:'身份证有效期开始',valid_to:'身份证有效期结束或长期'})[key],value:typeof values[key]==='string'?values[key]:'',hint:completeSnapshot&&!(typeof values[key]==='string'&&values[key].trim())?(result.status==='confirmed'?'此项未确认，未识别到可靠值，请手动核对填写':ocrCandidateHint(result.fields&&result.fields[key])||'未识别到可靠值，请手动核对填写'):result.status==='confirmed'?'':result.fields&&result.fields[key]?ocrCandidateHint(result.fields[key]):((this.data.ocrRows.find(row=>row.key===key)||{}).hint||'')}));this.ocrCapture={...capture,pending_confirmation:pendingConfirmation,seen_application_revision:result.application_revision,seen_provider_version:result.provider_version,...(capture.recovery&&result.status==='confirmed'?{recovery_confirmation_revision:result.confirmation_revision}:{})};this.ocrConfirmationRevision=confirmationRevision;if(['queued','processing'].includes(result.status)||focusedValueHeld){this.ocrPolling=true;}else this.stopOcrPoll();this.updateOcrView({ocrConfirmed:confirmed,ocrRows:rows,ocrProgressState:result.status,...(result.status==='failed'?{ocrDiagnostic:failedOcrDiagnostic(result)}:{}),ocrStatus:ocrOrientationHint(result)+(pendingConfirmation?'确认结果暂未返回，原任务已保留；请重新读取确认记录，勿重复确认':confirmed?'人工确认已留存；未自动覆盖申请字段':result.status==='needs_review'||result.status==='confirmed'?'识别建议，需逐项人工核对；不证明证件真实或审核通过':result.status==='processing'?'原识别任务仍在处理中，尚未取得可核对结果；耗时未确认，请勿重复上传。':result.status==='queued'?'正在等待识别，请稍候。完成后会自动显示。':result.status==='failed'?failedOcrFeedback(result):'识别尚无可确认建议，请人工核对')});}catch(error){if(this.ocrCurrent(capture)){
const diagnostic=error&&error.ocrDiagnostic;
if(capture.recovery===true&&capture.original_locator&&capture.original_locator.current_material===true&&!capture.job_id&&!capture.idempotency_key&&error.ocrCode==='OCR_UNAVAILABLE'&&diagnostic&&diagnostic.stage==='RESULT_READ'&&diagnostic.reason==='MATERIAL_JOB_NOT_FOUND'&&diagnostic.retryable===false&&diagnostic.request_retained===false)missingCurrentMaterialJob=capture;
if(error&&error.networkKind||['OCR_REQUEST_PENDING','OCR_UNAVAILABLE'].includes(String(error&&error.ocrCode||error&&error.message)))this.waitForOcr(error);else this.invalidateOcr(this.ocrFeedback(error));}}finally{this.ocrFlight=false;if(capture===this.ocrCapture&&!this.ocrCurrent(capture))this.pauseInvalidOcr(capture);if(this.ocrPolling)this.scheduleOcrPoll();else this.scheduleUploadedOcrRestore();}await this.finishConfirmedOcrSave();return missingCurrentMaterialJob&&this.ocrCurrent(missingCurrentMaterialJob)?missingCurrentMaterialJob:null;},
 editOcrSuggestion(e){const key=e.currentTarget.dataset.key,value=e.detail.value;if(typeof value!=='string'||!ocrInputFields(this.data.ocrKind).includes(key)||!this.data.ocrRows.some(row=>row.key===key))return;this.stopOcrPoll();if(this.ocrCapture)this.ocrRequest(this.ocrCapture);if(this.ocrDeferredFocusedKey===key)this.ocrDeferredFocusedKey=null;this.ocrSuggestionEdits={...(this.ocrSuggestionEdits||{}),[key]:value};this.ocrSuggestionEditVersion=(this.ocrSuggestionEditVersion||0)+1;this.updateOcrView({ocrConfirmed:false,ocrRows:this.data.ocrRows.map(row=>row.key===key?{...row,value}:row)});},
 async confirmAndSaveOcr(){if(this.data.pending||this.ocrFlight)return;this.chainRecord('ocr','OCR_05',null);const c=this.ocrCapture;if(!c||!this.ocrCurrent(c))return;this.ocrCapture={...c,auto_save_fields:toObject(this.ocrConfirmationRows().filter(r=>ocrInputFields(c.document_type).includes(r.key)&&typeof r.value==='string'&&r.value.trim()).map(r=>[r.key,r.value]))};if(!this.data.ocrConfirmed)await this.confirmOcr();return this.finishConfirmedOcrSave();},
 async finishConfirmedOcrSave(){const c=this.ocrCapture;if(!c||!c.auto_save_fields||!this.data.ocrConfirmed||this.data.pending||this.ocrFlight||this.ocrAutoSaving||!this.ocrCurrent(c))return;const fields=toObject(this.ocrConfirmationRows().filter(r=>ocrInputFields(c.document_type).includes(r.key)&&typeof r.value==='string'&&r.value.trim()).map(r=>[r.key,r.value]));if(!sameOcrFields(c.auto_save_fields,fields)){this.ocrCapture={...c,auto_save_fields:null};this.setData({ocrConfirmed:false,ocrStatus:'内容已变化，请核对当前资料后再确认。'});return;}this.ocrAutoSaving=true;this.ocrCapture={...c,auto_save_fields:null};try{await this.fillOcrDraft();}finally{this.ocrAutoSaving=false;}},
 confirmOcr(){if(this.ocrDrafts&&this.ocrDrafts[this.data.ocrKind]&&this.ocrCapture&&!this.ocrCapture.recovery&&!this.ocrCapture.ocr_rebound_same_version)return this.run(async()=>{await this.recoverCurrentDocument(this.ocrCapture);if(this.ocrCapture&&this.ocrCapture.recovery)await this.confirmRecovery();});if(this.ocrCapture&&this.ocrCapture.recovery_apply_pending)return this.run(()=>this.applyRecovery());if(this.ocrCapture&&this.ocrCapture.recovery)return this.run(()=>this.confirmRecovery());if(this.ocrFlight)return;this.stopOcrPoll();return this.run(async()=>{let capture=this.ocrCapture;if(capture&&capture.pending_confirmation&&this.ocrCurrent(capture)){await this.readOcr();return;}if(!capture||!capture.job_id||!this.ocrCurrent(capture)){this.invalidateOcr('申请版本已变化，请重新读取并识别');return;}if(!Number.isSafeInteger(this.ocrConfirmationRevision)||this.ocrConfirmationRevision<0||this.ocrConfirmationRevision>=Number.MAX_SAFE_INTEGER){this.invalidateOcr('确认版本不可用，请重新读取识别记录');return;}if(capture.seen_application_revision!==String(capture.revision)||!(capture.seen_provider_version===null||Number.isSafeInteger(capture.seen_provider_version)&&capture.seen_provider_version>=0)){this.invalidateOcr('确认版本不可用，请重新读取识别记录');return;}const fields=toObject(this.ocrConfirmationRows().filter(r=>ocrInputFields(capture.document_type).includes(r.key)&&typeof r.value==='string'&&r.value.trim()).map(r=>[r.key,r.value]));if(!Object.keys(fields).length)return;const revision=this.ocrConfirmationRevision+1;capture=this.ocrRequest({...capture,pending_confirmation:true,pending_confirmation_revision:revision,pending_confirmation_fields:fields,pending_confirmation_edit_version:this.ocrSuggestionEditVersion||0,pending_confirmation_form_edit_version:this.ocrFormEditVersion||0,pending_confirmation_provider_version:capture.seen_provider_version});try{const r=await this.ocrCall('confirm',{job_id:capture.job_id,revision,fields,application_revision:capture.seen_application_revision,provider_version:capture.seen_provider_version,idempotency_key:'mini-confirm-'+Date.now()+'-'+Math.random().toString(36).slice(2)});if(!this.ocrCurrent(capture))return;if((r.result&&r.result.job_id)!==capture.job_id||r.result.status!=='confirmed'||r.result.recorded!==true||r.result.revision!==revision||r.result.application_revision!==capture.seen_application_revision||r.result.provider_version!==capture.seen_provider_version)throw Error('OCR_CONFIRMATION_METADATA_INVALID');this.ocrConfirmationRevision=revision;const receipt=r.result;this.ocrCapture={...capture,pending_confirmation:false,...(capture.document_type==='business_license'&&sameOcrFields(receipt.confirmed_fields,fields)&&receipt.confirmed_binding&&receipt.confirmed_binding.application_revision===capture.seen_application_revision&&receipt.confirmed_binding.provider_version===capture.seen_provider_version?{license_fill_receipt:{revision,fields:{...fields},formEditVersion:capture.pending_confirmation_form_edit_version,suggestionEditVersion:capture.pending_confirmation_edit_version}}:{})};this.ocrSuggestionEdits={};this.updateOcrView({ocrConfirmed:true,ocrStatus:'人工确认已留存；未自动覆盖资料，可选择填入空白微信资料'});}catch(error){if(this.ocrCurrent(capture)){if(error&&error.networkKind||String(error&&error.ocrCode||error&&error.message)==='OCR_REQUEST_PENDING'){this.ocrCapture={...capture,pending_confirmation:true,pending_confirmation_revision:revision,pending_confirmation_fields:fields};this.updateOcrView({ocrStatus:'确认结果暂未返回，原任务已保留；请重新读取确认记录，勿重复确认'});}else this.invalidateOcr(this.ocrFeedback(error));}}});},
 reuseConfirmedIdentity(){this.ocrContactNameConflict=false;const capture=this.ocrCapture;if(this.data.options.contact!=='LEGAL'||!this.data.ocrConfirmed||!capture||capture.document_type!=='id_front'||!this.ocrCurrent(capture)||this.version!==capture.seen_provider_version||form.get(this.profile,'contact_info.contact_name'))return 0;const row=this.data.ocrRows.find(r=>r.key==='id_name');if(!row||typeof row.value!=='string'||!row.value.trim())return 0;const retained=form.get(this.profile,'subject_info.identity_info.id_card_info.id_card_name');if(typeof retained==='string'&&retained.trim()&&retained.trim()!==row.value.trim()){this.ocrContactNameConflict=true;return 0;}form.put(this.profile,'contact_info.contact_name',row.value.trim());return 1;},
 reuseConfirmedLicense(){if(!this.data.ocrConfirmed||!this.ocrCapture||this.ocrCapture.document_type!=='business_license'||!this.ocrCurrent(this.ocrCapture))return 0;let count=0;for(const [source,target] of [['subject_info.business_license_info.merchant_name','business_info.sales_info.biz_store_info.biz_store_name'],['subject_info.business_license_info.license_address','business_info.sales_info.biz_store_info.biz_store_address']]){const value=form.get(this.profile,source);if(typeof value==='string'&&value.trim()&&!ocrHasValue(form.get(this.profile,target))){form.put(this.profile,target,value.trim());count++;}}return count;},
 fillOcrDraft(){return this.run(()=>this.fillConfirmedOcrDraft());},
 async fillConfirmedOcrDraft(){if(this.ocrDrafts&&this.ocrDrafts[this.data.ocrKind]&&this.ocrCapture&&!this.ocrCapture.recovery&&!this.ocrCapture.ocr_rebound_same_version){await this.recoverCurrentDocument(this.ocrCapture);this.setData({ocrStatus:'已读取保存的识别草稿，请核对当前资料后确认；未覆盖原有资料。'});return;}if(this.ocrCapture&&this.ocrCapture.recovery)return this.applyRecovery();if(this.ocrFlight)return;this.stopOcrPoll();const capture=this.ocrCapture;if(!this.data.ocrConfirmed||!this.data.canEditWechat||!this.ocrCurrent(capture)||this.version!==capture.seen_provider_version){this.invalidateOcr('申请或确认版本已变化，请重新读取');return;}const proof=capture.document_type==='business_license'&&capture.license_fill_receipt;const reuse=proof&&proof.revision===this.ocrConfirmationRevision&&proof.formEditVersion===(this.ocrFormEditVersion||0)&&proof.suggestionEditVersion===(this.ocrSuggestionEditVersion||0);if(!reuse)await this.readOcr();const current=this.ocrCapture;if(!this.data.ocrConfirmed||!this.ocrCurrent(current)||this.version!==current.seen_provider_version)return;const maps={bank_card:{account_number:'bank_account_info.account_number',account_bank:'bank_account_info.account_bank'},business_license:{company_name:'subject_info.business_license_info.merchant_name',credit_code:'subject_info.business_license_info.license_number',legal_representative:'subject_info.business_license_info.legal_person',registered_address:'subject_info.business_license_info.license_address'},id_front:{id_name:'subject_info.identity_info.id_card_info.id_card_name',id_number:'subject_info.identity_info.id_card_info.id_card_number',registered_address:'subject_info.identity_info.id_card_info.id_card_address'},id_back:{valid_from:'subject_info.identity_info.id_card_info.card_period_begin',valid_to:'subject_info.identity_info.id_card_info.card_period_end'}};if(['id_front','id_back'].includes(current.document_type)&&this.data.options.doc!=='IDENTIFICATION_TYPE_IDCARD')throw Error('OCR_DOCUMENT_BINDING_CHANGED');const mapping=maps[current.document_type];if(!mapping)throw Error('OCR_DOCUMENT_NOT_SUPPORTED');let filled=0;for(const row of reuse?Object.entries(proof.fields).map(([key,value])=>({key,value})):this.data.ocrRows){const path=mapping[row.key];if(path&&!(current.document_type==='business_license'&&this.ocrExplicitEmptyFields&&this.ocrExplicitEmptyFields[path])&&typeof row.value==='string'&&row.value.trim()&&!ocrHasValue(form.get(this.profile,path))){form.put(this.profile,path,row.value.trim());filled++;}}filled+=this.reuseConfirmedIdentity();filled+=this.reuseConfirmedLicense();if(!filled){this.setData({ocrStatus:this.ocrContactNameConflict?'已填写证件姓名与识别确认姓名不同，原值已保留；请人工核对联系人姓名':'没有可填入的空白项；已填写资料保持不变'});return;}this.setData({dirty:true});this.syncLeaveGuard();await this.saveDraft();if(this.current())this.invalidateOcr(this.ocrContactNameConflict?'空白资料已保存；证件姓名与识别确认姓名不同，未补填联系人姓名，请人工核对':'已将人工核对资料填入空白微信资料并保存；未提交审核，已有值未覆盖');},
 canRouteSavedWechatMaterial(kind){
  return kind==='cashier_photo'||!!this.materialProfilePath(kind)||(form.industryMaterialKind(kind)&&
   this.data.catalog.some(m=>m.id===kind)&&this.data.catalog.some(m=>m.id==='industry_permit_2'));
 },
 plannedUploadedReviewMaterials(sides){
  if(!sides||sides.wechat!==true||!this.data.application)return [];
  const originals=this.data.application.materials||{},seen=new Set(),kinds=[];
  for(const group of this.data.reviewGroups||[])for(const item of group.items||[]){
   if(!item||!item.material||!(item.wechatRequired||item.autoWechat)||item.synced||!item.uploaded||
      typeof item.path!=='string'||!item.path.startsWith('material:'))continue;
   const kind=item.path.slice(9);
   if(!kind||kind==='bank_card'||seen.has(kind)||!Object.prototype.hasOwnProperty.call(originals,kind)||!originals[kind]||!this.canRouteSavedWechatMaterial(kind))continue;
   seen.add(kind);kinds.push(kind);
  }
  return kinds;
 },
 async prepareReviewMaterials(state,sides,readback){
  const id=state.application,session=this.session,epoch=this.epoch,scene=this.scene;
  const current=()=>this.current()&&this.scene===scene&&this.session===session&&this.epoch===epoch&&this.data.application&&this.data.application.application===id;
  const fail=message=>{const error=Error(message);error.submitPreflight=true;throw error;};
  const pick=()=>this.plannedUploadedReviewMaterials(sides);
  const label=kind=>({business_license:'营业执照',identity_front:'身份证人像面',identity_back:'身份证国徽面',storefront_photo:'门头照',interior_photo:'店内环境照',mini_program_screenshot:'小程序截图',operator_identity:'经办人证件正面',operator_identity_back:'经办人证件背面',cashier_photo:'收银台照'})[kind]||'申请材料';
  this.reviewMaterialStage=null;
  const kinds=pick();
  const sources=toObject(kinds.map(kind=>[kind,JSON.stringify(this.data.application.materials[kind])]));
  for(let index=0;index<kinds.length;index++){
   if(!current())return;const kind=kinds[index];
   const progress=(phase)=>{
    if(!current())return;
    const count=(index+1)+'/'+kinds.length,material=label(kind);
    this.reviewMaterialStage={material,phase,count};
    this.setData({status:'正在关联'+material+'（'+count+'）：'+phase+'。尚未提交微信审核。'});
   };
   progress('核对原申请材料');
   const previous=readback;readback=null;await this.load(id,current,previous);if(!current())return;
   if(JSON.stringify(this.data.application.materials[kind])!==sources[kind])fail('申请材料已变化，请核对原申请后再次提交；已完成的关联会保留。');
   const remaining=pick();
   if(!remaining.includes(kind))continue;
   progress('发送本材料到微信');
   // The next material (or final submit read) reloads before using this saved draft.
   this.mediaReceiptRecovered=false;await this.syncCurrentMaterial(kind,true,{current,deferReload:true,materialReadCurrent:true,skipDonationDraft:true,progress,readback:value=>{readback=value;},accept:app=>!!app&&app.application===id&&current()});if(!current())return;
  }
  this.reviewMaterialStage=null;
 },
 async onOwnerSubmitTap(e){
  const bound=e&&e.currentTarget,ds=bound&&bound.dataset;
  const app=this.data.application,session=this.session;
  if(!e||e.type!=='tap'||!bound||bound.id!=='owner-wechat-submit'||!ds||ds.action!=='owner-wechat-submit'||
     !app||ds.application!==app.application||String(ds.revision)!==String(app.revision)||!this.current()||
     this.data.pending||!this.data.ready||OWNER_WECHAT_CLICK.has(this))return;
  if(this.data.sessionRecoveryRequired||this.interruptedReviewDraft||['SUBMISSION_UNKNOWN','SUBMITTED_TO_PROVIDER'].includes(this.reviewState))
   return this.refreshApplication();
  const previous=OWNER_WECHAT_SENT.get(this);
  if(previous&&previous.application===app.application&&previous.scene===this.scene&&
      previous.revision===app.revision&&previous.version===this.version)return this.refreshApplication();
  if(!session||typeof session.isAuthenticated!=='function'||!session.isAuthenticated()||
     typeof session.getGeneration!=='function'||!Number.isSafeInteger(app.revision)||!Number.isSafeInteger(this.version))return;
  const click={application:app.application,revision:app.revision,version:this.version,session,scene:this.scene,
   epoch:this.epoch,generation:session.getGeneration(),operationStarted:false,confirmed:null,
   donationDraft:this.data.splitChoiceEdited||this.data.splitSaveUnknown?{
    splitInput:this.data.splitInput,splitChoiceEdited:this.data.splitChoiceEdited,splitDefaultPending:this.data.splitDefaultPending,splitSaveUnknown:this.data.splitSaveUnknown}:null};
  OWNER_WECHAT_CLICK.set(this,click);
  try{return await this.submitAllReview(click);}
  finally{if(OWNER_WECHAT_CLICK.get(this)===click){
   OWNER_WECHAT_CLICK.delete(this);
   if(click.donationDraft&&this.current()&&this.session===session&&this.epoch===click.epoch&&this.scene===click.scene&&
      session.isAuthenticated()&&session.getGeneration()===click.generation&&this.data.application&&this.data.application.application===click.application){
    this.setData({...click.donationDraft,...(click.donationDraft.splitChoiceEdited?{dirty:true}:{})});
    this.syncLeaveGuard();
   }
  }}
 },
 submitAllReview(click){
  const initial=this.data.application;
  if(!click||OWNER_WECHAT_CLICK.get(this)!==click||!this.data.ready||!initial||
     initial.application!==click.application||initial.revision!==click.revision||this.version!==click.version)return;
  if(this.data.sessionRecoveryRequired||this.interruptedReviewDraft)return this.refreshApplication();
  this.setData({submitIssues:[],missingFieldPath:''});
  return this.run(async()=>{
   this.chainRecord('submit','SUBMIT_01',null);this.refresh();
   const {application:id,session,epoch,scene,generation}=click;
   const current=()=>this.current()&&OWNER_WECHAT_CLICK.get(this)===click&&this.session===session&&this.epoch===epoch&&this.scene===scene&&
    session.getGeneration()===generation&&session.isAuthenticated()&&this.data.application&&this.data.application.application===id;
   if(!current())return;
   let pendingReadback=null,latestReadback=null;
   if(this.data.dirty){
    await this.saveDraft({current,deferReload:true,skipDonationDraft:true,readback:value=>{pendingReadback=value;},accept:app=>!!app&&app.application===id&&current()});
    if(!current())return;
   }
   const read=async()=>{
    const previous=pendingReadback;pendingReadback=null;latestReadback=await this.load(id,current,previous);
    return {application:this.data.application&&this.data.application.application,revision:this.data.application&&this.data.application.revision,
     version:this.version,platformState:this.data.platformState,reviewState:this.reviewState,providerState:this.data.wechatState};
   };
   const result=await submitSharedReview({read,current,
    // Original shared-review call shape: the applicant-direct contract never
    // invokes this; the historical two-queue caller still expects the handle.
    submitPlatform:async params=>this.request('submit',params),
    prepareMaterials:(state,sides)=>this.prepareReviewMaterials(state,sides,latestReadback),
    confirm:async state=>{
     if(!current()||click.confirmed||click.operationStarted||!state||state.application!==id||
       state.revision!==this.data.application.revision||state.version!==this.version||state.reviewState!==this.reviewState)return false;
     click.confirmed={revision:state.revision,version:state.version};return true;
    },
    submitProvider:async params=>{
     const proof=click.confirmed;
     if(!current()||!proof||click.operationStarted||params.application!==id||params.expected_version!==proof.version||
       params.application_revision!==proof.revision||this.version!==proof.version||this.data.application.revision!==proof.revision)
      throw Error('原申请状态已变化，请刷新进度；未向微信提交。');
     click.operationStarted=true;
     OWNER_WECHAT_SENT.set(this,{application:id,scene,revision:proof.revision,version:proof.version});
     this.chainRecord('submit','SUBMIT_03',null);
     const app={...this.data.application};
     // Owner-direct WeChat submission per the installed backend contract
     // (2026-11-27 18:41:58 26-byte 403 evidence): the live route lineage
     // (community_mini_merchant APPLICANT + onboarding _owner_submit binding +
     // applyment fields wechat_submit_review|{application_revision}) admits
     // wechat_submit_review {application,expected_version,application_revision}
     // as the mini owner-direct op, rejects provider re-POST on unresolved
     // intents (QUERY_EXISTING_APPLICATION_ONLY / SUBMISSION_UNKNOWN→GET query)
     // and freezes the original platform draft server-side. The site pre-review
     // queue (two-parameter wechat_submit_review, web reviewer flow only) is not
     // entered; wechat_apply 403s at admission before any provider IO.
     const record=await this.request('wechat_submit_review',params,true);
     if(current()&&this.scene===scene&&record&&record.version===params.expected_version)pendingReadback=this.createProviderReceiptReadback(app,record,'wechat_submit_review');
     return record;
    },
    queryProvider:async params=>{
     this.chainRecord('submit','SUBMIT_05',null);const app={...this.data.application};
     const record=await this.request('wechat_status',params);
     if(current())pendingReadback=this.createProviderReceiptReadback(app,record,'wechat_status');return record;
    }});
   this.reconcileSubmitReadback(result);
   if(current()&&!result.cancelled){
    const feedback=this.data.providerParameterFeedback;
    this.setData({step:3,status:result.queryPending?'已有受理回执，最新状态读取失败；请刷新原申请，不要重复提交。':
     result.reviewState==='CORRECTION'?(feedback?'微信接口返回了进件参数说明，请看“微信返回（进件参数）”。':'当前申请可补正，请核对微信返回的结果；已填写资料保留。'):
     result.providerState==='APPLYMENT_STATE_FINISHED'?'微信审核已通过并完成进件；收款资格仍需另行核验，未自动开通支付。':
     result.reviewState==='SUBMITTED_TO_PROVIDER'?'提交成功，请等待微信审核。已取得微信真实受理结果；尚不代表收款已开通。':
     '微信提交结果待核实，可刷新原申请进度，不会重复提交。'});
   }
  },'提交审核');
 },
 submit(){if(!this.data.application)return;return this.run(async()=>{const app=this.data.application;const r=await this.request('submit',{application:app.application,revision:app.revision});if(this.current()){this.setData({application:r,platformState:r.status,status:'已提交平台审核；微信认证尚未完成'});}});},
 clearProviderPoll(){if(this.providerPoll&&typeof clearTimeout==='function')clearTimeout(this.providerPoll);this.providerPoll=null;},
 scheduleProviderPoll(){
  this.clearProviderPoll();
  const session=this.session,app=this.data.application,id=app&&app.application,scene=this.scene,epoch=this.epoch,foreground=this.providerForeground;
  const generation=session&&typeof session.getGeneration==='function'?session.getGeneration():null;
  const same=()=>this.current()&&!this.ocrHidden&&this.session===session&&this.scene===scene&&this.epoch===epoch&&
   generation!==null&&session.getGeneration()===generation&&typeof session.isAuthenticated==='function'&&session.isAuthenticated()&&
   this.data.authenticated&&!this.data.sessionRecoveryRequired&&!this.interruptedReviewDraft&&this.data.application&&this.data.application.application===id;
  const eligible=()=>same()&&!this.data.dirty&&['SUBMISSION_UNKNOWN','SUBMITTED_TO_PROVIDER'].includes(this.reviewState)&&
   !['APPLYMENT_STATE_FINISHED','APPLYMENT_STATE_CANCELED','APPLYMENT_STATE_REJECTED','APPLYMENT_STATE_EDITTING','APPLYMENT_STATE_EDITING'].includes(this.data.wechatState);
  const matches=(x)=>x&&x.session===session&&x.generation===generation&&x.id===id&&x.scene===scene;
  if(typeof setTimeout!=='function'||!foreground||!id||!eligible()||this.providerObserveFlight||matches(this.providerObserveDenied))return;
  const immediate=!matches(this.providerForegroundRead)||this.providerForegroundRead.foreground!==foreground;
  this.providerPoll=setTimeout(async()=>{
   this.providerPoll=null;
   if(!eligible()||this.providerForeground!==foreground||this.data.pending||this.providerObserveFlight)return;
   const flight={session,generation,id,scene,foreground};
   this.providerObserveFlight=flight;this.providerForegroundRead=flight;
   try{
    await this.request('wechat_status',{application:id},true);
    if(same()&&!this.data.dirty&&!this.data.pending)await this.load(id,()=>same()&&!this.data.dirty&&!this.data.pending);
   }catch(error){
    if(error&&(error.code==='ACCESS_DENIED'||error.accessHttpStatus===401||error.accessHttpStatus===403||error.message==='SESSION_EXPIRED'))this.providerObserveDenied=flight;
   }finally{
    if(this.providerObserveFlight===flight){this.providerObserveFlight=null;this.scheduleProviderPoll();}
   }
  },immediate?0:300000);
 },
 refreshApplication(){
  if(!this.current()||this.data.pending||!this.data.application)return;
  const app=this.data.application,session=this.session;
  const missing=!session||typeof session.isAuthenticated==='function'&&!session.isAuthenticated();
  if(this.data.sessionRecoveryRequired||this.interruptedReviewDraft||missing){
   if(session&&typeof session.isSignedOut==='function'&&session.isSignedOut()){this.setData({status:'已主动退出登录。请从页面登录入口重新登录后，再核对原申请。'});return;}
   if(this.data.dirty){this.setData({status:'本页还有未保存修改。请先留存修改，再通过页面登录入口只读核对原申请；系统未重试提交。'});return;}
   const already=this.interruptedReviewDraft;
   if(already&&(already.application!==app.application||already.scene!==this.scene)){
    this.setData({status:'原申请归属尚未核对，未切换到其他申请，也未提交。'});return;
   }
   this.interruptedReviewDraft={application:app.application,scene:this.scene,denied:!!(already&&already.denied)};
   return this.connectApplicant({automatic:false});
  }
  return this.run(async()=>{const id=app.application;
   if(['SUBMISSION_UNKNOWN','SUBMITTED_TO_PROVIDER'].includes(this.reviewState))await this.request('wechat_status',{application:id});
   if(this.current())await this.load(id);
  });
 },
 workbench(){
  const a=this.data.application;
  if(this.current()&&this.data.authenticated&&this.data.openingState==='OPENED'&&auth.openingTarget(a))return auth.navigateOpening(this,a,wx,getApp());
  if(this.data.platformState==='APPROVED'&&this.data.openingState==='OPENED'&&a&&!a.opening_scene&&!a.opening_workspace)
    return this.navigateSection({currentTarget:{dataset:{section:'merchant'}}});
  this.setData({status:'工作台尚未开通，请查看原申请进度；可返回修改可编辑资料'});
 },
 customerSessionRevoked(){this.clearMediaStatusWait();this.providerParameterFeedbackLoad=null;this.setData({providerParameterFeedback:null});this.invalidateSigningQr();this.loadedDisplayApplication=null;this.cancelStepOcrReview();this.setData({submitIssues:[],missingFieldPath:''});this.privatePreviewCleanup();this.clearUploadedOcrRestoreTimer();this.ocrRestoreQueue=null;this.beginStepScroll();if(this.session){OCR_PAGE_RESUME.delete(this.session);}this.cancelReuse();this.reviewState=null;this.platformAppid=null;this.setData({submitIssues:[],missingFieldPath:'',uploadFeedback:null,materialPreviews:{},regionLabel:'',regionIndices:[0,0,0],regionColumns:[[],[],[]],industryLabels:[],industryValue:0,industryHint:'',platformAppidStatus:'平台身份未核实',wechatReviewState:'NOT_SUBMITTED',ready:false,authenticated:false,readState:'IDLE',readError:'',canEditPlatform:false,canEditWechat:false});this.invalidateOcr();if(this.session)this.session.clear();this.ocrHeldCaptures=null;this.ocrDisplayCaptures=null;this.session=null;this.profile={};this.ocrDrafts={};this.industryOtherSelected=false;this.industryConditionChoices={};this.operatorContactName='';this.legalContactName='';this.reusedFieldLinks={};this.inactiveUboList=null;this.version=0;this.reviewState=null;this.cashierMediaId='';this.setData({pendingRedemptionPercent:0,uploadFeedback:null,materialPreviews:{},ocrRows:[],ocrJob:'',showOptionalMaterials:false,displayReviewGroups:[],reviewGroups:[],materialGroups:[],documentGroups:[],scenePhotoCards:[],miniSceneMaterials:[],adjacentMaterials:[],licenseMaterial:null,applications:[],application:null,fields:[],materials:[],signUrl:'',base:{store_name:'',address:''},step:0,platformState:'未提交',wechatReviewState:'NOT_SUBMITTED',wechatState:'未核验',openingState:'未开通',pending:false,dirty:false,leavePrompt:false,leaveTarget:'',status:'登录已退出，请重新进入'});this.syncLeaveGuard();},
 onUnload(){this.clearMediaStatusWait();if(this.pendingPickerShow)this.pendingPickerShow.finish(false);if(this.freshIntent&&freshNavigation===this.freshIntent&&!['PENDING','UNKNOWN'].includes(this.freshIntent.phase))freshNavigation=null;this.invalidateSigningQr();this.cancelStepOcrReview();this.clearProviderPoll();this.privatePreviewCleanup();this.clearUploadedOcrRestoreTimer();this.ocrRestoreQueue=null;this.beginStepScroll();this.cancelReuse();this.rememberKnownOcr();this.invalidateOcr();this.ocrHeldCaptures=null;this.ocrDisplayCaptures=null;this.dead=true;this.profile={};this.ocrDrafts={};this.industryOtherSelected=false;this.industryConditionChoices={};this.operatorContactName='';this.legalContactName='';this.reusedFieldLinks={};this.cashierMediaId='';this.setData({materialPreviews:{},uploadFeedback:null});if(this.session&&this.session.detachPage)this.session.detachPage(this);this.session=null;if(typeof wx.disableAlertBeforeUnload==='function')wx.disableAlertBeforeUnload();}
});
