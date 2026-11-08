'use strict';
// Exact original 4a1bbae input/reply guards; only transport/auth hooks adapted.
module.exports=({call,isAuthenticated,getGeneration})=>({
    async customer(operation, params={}) {
      if(!isAuthenticated())throw Error('SESSION_EXPIRED');
      const object=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
      const keys=(value,allowed)=>object(value)&&Object.keys(value).every(key=>allowed.includes(key));
      const hex=value=>typeof value==='string'&&/^[0-9a-f]{64}$/.test(value);
      const demoId=value=>typeof value==='string'&&/^demo_[0-9a-f]{64}$/.test(value);
      const demoRecord=value=>object(value)&&demoId(value.id)&&typeof value.name==='string'&&typeof value.description==='string'&&
        value.is_demo===true&&value.display_only===true&&value.payment_enabled===false&&value.purchasing_enabled===false&&
        value.include_in_real_statistics===false&&value.storefront_photo===null&&value.photo_asset_id==='community-demo-storefront-v1'&&
        value.photo_state==='BUNDLED_DEMO_ASSET_PENDING'&&value.category_state==='DEMO'&&value.version===1&&value.profile_version===0;
      const scene=value=>typeof value==='string'&&/^[A-Za-z0-9_-]{1,32}$/.test(value);
      const optional=(name,valid)=>!(name in params)||params[name]===''||valid(params[name]);
      let valid=false;
      if(operation==='contexts')valid=keys(params,['after_scene'])&&optional('after_scene',scene);
      else if(operation==='directory')valid=keys(params,['after_id','category_id'])&&optional('after_id',hex)&&optional('category_id',value=>typeof value==='string'&&/^[A-Za-z0-9_-]{1,40}$/.test(value));
      else if(operation==='store')valid=keys(params,['id'])&&Object.keys(params).length===1&&(hex(params.id)||demoId(params.id));
      if(!valid)throw Error('INVALID_CUSTOMER_READ');
      const version=getGeneration();
      const reply={payment_enabled:false,result:await call('/api',{scene:'',operation:'customer.'+operation,params:{...params}})};
      if(version!==getGeneration())throw Error('STALE_SESSION');
      const result=reply&&reply.result;
      if(!reply||reply.payment_enabled!==false||!object(result))throw Error('UNTRUSTED_CUSTOMER_REPLY');
      // Empty/malformed replies must never become a successful empty directory.
      if(operation==='store'){
        if(result.id!==params.id||typeof result.name!=='string'||typeof result.description!=='string'||
          (demoId(params.id)?!demoRecord(result):result.is_demo===true))throw Error('UNTRUSTED_CUSTOMER_REPLY');
      }else{
        const rows=operation==='contexts'?result.contexts:result.records;
        const cursor=operation==='contexts'?scene:hex;
        if(!Array.isArray(rows)||rows.length>50||typeof result.has_more!=='boolean'||
          (result.has_more?!cursor(result.next_cursor):result.next_cursor!==null))throw Error('UNTRUSTED_CUSTOMER_REPLY');
        if(operation==='contexts'){
          if(result.scope!=='CURRENT_CUSTOMER_AUTHORIZED_CONTEXTS'||result.payment_enabled!==false||
            rows.some(row=>!object(row)||!scene(row.scene)))throw Error('UNTRUSTED_CUSTOMER_REPLY');
        }else if(result.visibility!=='CURRENT_AUTHORIZED_PROJECT_TENANT'||result.storefront_photo_supported!==false||!Array.isArray(result.categories)||
          rows.some(row=>!object(row)||!hex(row.id)||row.is_demo===true||typeof row.name!=='string'||typeof row.description!=='string'))throw Error('UNTRUSTED_CUSTOMER_REPLY');
      }
      if(operation==='directory'&&Object.prototype.hasOwnProperty.call(result,'demo')){
        const demo=result.demo;
        if(!object(demo)||!['VISIBLE','HIDDEN_REAL_APPROVAL_OBSERVED','UNKNOWN','NOT_CURRENT_PROJECT'].includes(demo.state)||
          (demo.state==='VISIBLE'?!demoRecord(demo.record):demo.record!==null))throw Error('UNTRUSTED_CUSTOMER_REPLY');
      }
      return result;
    },
    async commerce(scene, operation, params) {
      if(!isAuthenticated())throw Error('SESSION_EXPIRED');
      if(typeof scene!=='string'||!/^[A-Za-z0-9_-]{1,32}$/.test(scene)||!['communities','community_mine','community_join','community_leave','promotion_redeem','profile_read','profile_update','referral_code','referral_bind','notices','notice_read','orders','products','purchase','purchase_read','purchase_recover','receipt_ad','project_summary','project_checklist','project_feedback','project_messages','project_save_reference','project_submit','refund_apply','refund_application','refund_current'].includes(operation))throw Error('INVALID_COMMERCE_REQUEST');
      const version=getGeneration();
      const reply={payment_enabled:false,result:await call('/api',{scene,operation:'commerce.'+operation,params})};
      if(version!==getGeneration())throw Error('STALE_SESSION');
      if(!reply||!reply.result||reply.payment_enabled!==false)throw Error('UNTRUSTED_COMMERCE_REPLY');
      return reply.result;
    },
    async merchant(scene, operation, params) {
      if(!isAuthenticated())throw Error('SESSION_EXPIRED');
      const applicantOcr=scene===''&&operation==='ocr'&&params&&['submit','read','confirm','delete','apply_confirmed','recover_view','recover_confirm','recover_apply'].includes(params.action);
      const applicantOnly=applicantOcr||scene===''&&operation==='onboarding'&&params&&
        ['material_preview','catalog','mine','read','save','upload','remove_material','submit','withdraw','history','notices','notice_read','wechat_read','wechat_save','wechat_submit_review','wechat_media','wechat_cashier_link'].includes(params.operation);
      if((!applicantOnly&&(typeof scene!=='string'||!/^[A-Za-z0-9_-]{1,32}$/.test(scene)))||
         !['workspaces','onboarding','read','write','collection_code','ocr'].includes(operation)||!params||typeof params!=='object'||Array.isArray(params))throw Error('INVALID_MERCHANT_REQUEST');
      const version=getGeneration();
      const reply={payment_enabled:false,result:await call('/merchant',{scene,operation,params})};
      if(version!==getGeneration())throw Error('STALE_SESSION');
      if(!reply||reply.payment_enabled!==false||!reply.result)throw Error('UNTRUSTED_MERCHANT_REPLY');
      return reply.result;
    },
    async projectDocument(scene, params, expectedGeneration=getGeneration()) {
      if(expectedGeneration!==getGeneration())throw Error('STALE_SESSION');
      if(!isAuthenticated())throw Error('SESSION_EXPIRED');
      if(typeof scene!=='string'||!/^[A-Za-z0-9_-]{1,32}$/.test(scene)||
         !params||Object.keys(params).sort().join(',')!=='content_base64,filename,item,revision'||
         typeof params.item!=='string'||!/^[A-Za-z0-9_-]{1,64}$/.test(params.item)||
         !Number.isSafeInteger(params.revision)||params.revision<0||
         typeof params.filename!=='string'||params.filename.length<1||params.filename.length>180||
         params.filename.trim()!==params.filename||/[\\/:\x00-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/.test(params.filename)||
         !/\.(pdf|png|jpe?g)$/i.test(params.filename))throw Error('INVALID_PROJECT_DOCUMENT');
      const content=params.content_base64;
      if(typeof content!=='string'||!content.length||content.length>6666668||content.length%4!==0||
         !/^[A-Za-z0-9+/]+={0,2}$/.test(content))throw Error('INVALID_PROJECT_DOCUMENT');
      const padding=content.endsWith('==')?2:content.endsWith('=')?1:0;
      const size=content.length/4*3-padding;
      const last='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'.indexOf(content[content.length-padding-1]);
      if(size<1||size>5000000||(padding===2&&(last&15)!==0)||(padding===1&&(last&3)!==0))throw Error('INVALID_PROJECT_DOCUMENT');
      // File names alone do not establish type; the server still owns scanning and final validation.
      let magic='',bits=0,value=0;
      const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
      for(const character of content.slice(0,12)){
        if(character==='=')break;
        value=(value<<6)|alphabet.indexOf(character);bits+=6;
        if(bits>=8){bits-=8;magic+=String.fromCharCode((value>>bits)&255);}
      }
      const extension=magic.startsWith('%PDF-')?/\.pdf$/i:
        magic.startsWith('\x89PNG\r\n\x1a\n')?/\.png$/i:magic.startsWith('\xff\xd8\xff')?/\.jpe?g$/i:null;
      if(!extension||!extension.test(params.filename))throw Error('INVALID_PROJECT_DOCUMENT');
      const version=getGeneration();
      const reply={payment_enabled:false,result:await call('/project-materials',{scene,params})};
      if(version!==getGeneration())throw Error('STALE_SESSION');
      const result=reply&&reply.result;
      if(!reply||reply.payment_enabled!==false||!result||
         Object.keys(result).sort().join(',')!=='revision,state,version'||
         typeof result.version!=='string'||!/^v_[0-9a-f]{32}$/.test(result.version)||
         !Number.isSafeInteger(result.revision)||result.revision!==params.revision+1||
         result.state!=='PARTIAL')throw Error('UNTRUSTED_PROJECT_DOCUMENT_REPLY');
      return result;
    },
});
