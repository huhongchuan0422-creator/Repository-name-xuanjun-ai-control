'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),vm=require('node:vm');
const evidence=process.env.CLIENT_OVERLAY_MERGE_EVIDENCE_ROOT||path.resolve(__dirname,'../../../../community-mini-three-fixes-20261125/client-overlay-merge');
const read=(group,name)=>fs.readFileSync(path.join(evidence,group,name));
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const JS_PATH='pages/merchant-join/index.js',CSS_PATH='pages/checkout/index.wxss';
const source=fs.readFileSync(path.join(__dirname,JS_PATH),'utf8');
function fixture({fail=false}={}){
 let definition,release,entered;const gate=new Promise(r=>release=r),seen=new Promise(r=>entered=r),calls=[];
 const session={ensureLogin:async()=>{},isAuthenticated:()=>true,getGeneration:()=>1};
 vm.runInNewContext(source,{Page:p=>definition=p,wx:{},getApp:()=>({globalData:{}}),
  require(p){if(p==='../../session')return {getSharedSession:()=>session,customerError:()=> 'synthetic read failure'};
   if(p==='../../customer-auth')return {current:()=>1};if(p==='../../chain-telemetry')return require('./chain-telemetry');
   if(p==='../../merchant-form')return require('./merchant-form');if(p==='../../merchant-submit')return {};
   if(p==='../../merchant-official-fields')return require('./merchant-official-fields');
   if(p==='../../merchant-platform-reference-data')return require('./merchant-platform-reference-data');
   if(p==='./direct-ocr'||p==='./direct-proof')return {};
   throw Error('unexpected dependency '+p);}});
 const p={...definition,data:structuredClone(definition.data),setData(v){Object.assign(this.data,v);}};
 p.current=()=>true;p.scene='synthetic';p.verifyPlatformAppid=()=>{};p.refresh=()=>{};
 p.request=async op=>{calls.push(op);if(op==='catalog')return {materials:[]};if(op==='mine')return {applications:[{application:'approved-original',status:'APPROVED',revision:2},{application:'draft-cursor',status:'DRAFT',revision:1}],current_cursor:{application:'draft-cursor'}};throw Error('unexpected operation');};
 p.load=async id=>{calls.push(['load',id]);entered();await gate;if(fail)throw Error('synthetic');p.loadedDisplayApplication=id;p.setData({application:{application:id},step:3,wechatState:'APPLYMENT_STATE_TO_BE_SIGNED'});};
 return {page:p,calls,seen,release,allowRetry(){fail=false;}};
}

test('merge bases are exact two receipt-pinned upload bytes, not current working source',()=>{
 assert.equal(sha(read('upload-base',JS_PATH)),'6f1e1eed443e23c27a700402318f71064c318e36d79990d6e705e3d19628e531');
 assert.equal(sha(read('upload-base',CSS_PATH)),'f63346034db90edbe61ac2cafd6ae4c9a4697d89af2fe39f3529f6af09979e99');
 const proof=JSON.parse(fs.readFileSync(path.join(evidence,'UPLOAD-SOURCE-PROVENANCE.json'),'utf8'));
 assert.equal(proof.control_commit,'9fa4e5feb6ee42cc7b841bc8164c4120f80b78ba');
 assert.equal(proof.manifest_sha256,'a571d0a7d81c67ef5be7e00d1e464828714d84662304e3c75ecb13349a4ca725');assert.equal(proof.exact_receipt_matches,true);
});

test('merged JS differs from approved 8a3 only by preserving original uploaded selection overlay',()=>{
 const old=read('reviewed-8a3',JS_PATH).toString();
 const clause='.filter(a=>!result.current_cursor||a.application===result.current_cursor.application)';
 assert.equal(old.split(clause).length,2);assert.equal(source,old.replace(clause,''));
 assert.match(source,/ready:!selected,readState:selected\?'LOADING':'READY'/);
 assert.match(source,/recognizeCurrentDocument\(kind,options=\{\}\)\{\n  if\(kind==='bank_card'\)return/);
});

test('palette CSS preserves latest upload-tip bytes and adds only palette-inheriting icon rule',()=>{
 const tip=fs.readFileSync(path.join(evidence,'warm-rose-css/upload-tip.css'));
 assert.equal(sha(tip),'1731bb8ea0327b8e40d0c92161efb42aee187ba6f82a4803ab1b29299cc4153c');
 const oldRule=read('reviewed-8a3',CSS_PATH).toString().match(/\.storefront-symbol\{[^}]+\}/)[0];
 const rule=oldRule.replace('color:#728b7b;','color:inherit;');
 const actual=fs.readFileSync(path.join(__dirname,CSS_PATH));
 assert.deepEqual(actual,Buffer.concat([tip,Buffer.from('\n'+rule+'\n')]));
 assert.equal((actual.toString().match(/\.storefront-symbol\{/g)||[]).length,1);
});

test('original uploaded selection overlay and new neutral-loading gate coexist for pending signing',async()=>{
 const f=fixture(),opening=f.page.connectApplicant({automatic:true});await f.seen;
 assert.deepEqual(f.calls.find(x=>Array.isArray(x)),['load','approved-original']);
 assert.equal(f.page.data.ready,false);assert.equal(f.page.data.readState,'LOADING');
 assert.equal(f.page.data.canEditPlatform,false);f.release();await opening;
 assert.equal(f.page.data.ready,true);assert.equal(f.page.data.step,3);
 assert.equal(f.page.data.application.application,'approved-original');
 assert.equal(f.page.data.wechatState,'APPLYMENT_STATE_TO_BE_SIGNED');
 assert.ok(!f.calls.some(x=>['save','wechat_submit_review','wechat_apply'].includes(x)));
});

test('merged selection path keeps read failure retry without changing or creating an application',async()=>{
 const f=fixture({fail:true}),opening=f.page.connectApplicant({automatic:true});await f.seen;f.release();await opening;
 assert.equal(f.page.data.ready,false);assert.equal(f.page.data.readState,'FAILED');assert.equal(f.page.data.application,null);
 f.allowRetry();await f.page.retryApplicantRead();assert.equal(f.page.data.ready,true);assert.equal(f.page.data.step,3);
 assert.deepEqual(f.calls.filter(x=>Array.isArray(x)),[['load','approved-original'],['load','approved-original']]);
 assert.ok(!f.calls.some(x=>['save','wechat_submit_review','wechat_apply'].includes(x)));
});


test('palette CSS retains MERGED2 icon geometry while inheriting the warm-rose placeholder color',()=>{
 const actual=fs.readFileSync(path.join(__dirname,CSS_PATH),'utf8');
 const parse=rule=>Object.fromEntries(rule.slice(rule.indexOf('{')+1,-1).split(';').filter(Boolean).map(x=>x.split(':')));
 const previous=parse(read('reviewed-8a3',CSS_PATH).toString().match(/\.storefront-symbol\{[^}]+\}/)[0]);
 const current=parse(actual.match(/\.storefront-symbol\{[^}]+\}/)[0]);
 assert.equal(current.color,'inherit');delete current.color;delete previous.color;assert.deepEqual(current,previous);
 assert.match(actual,/\.shop-photo-placeholder\{[^}]*color:#756068;/);
 assert.ok(!actual.includes('color:#728b7b'));
});

test('palette CSS static mobile viewport checks fit icon and text at 320 375 and 414 pixels',()=>{
 const css=fs.readFileSync(path.join(__dirname,CSS_PATH),'utf8');
 function declarations(selector){const result={};for(const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)){if(m[1].trim().split(',').includes(selector))for(const item of m[2].split(';')){const k=item.indexOf(':');if(k>0)result[item.slice(0,k).trim()]=item.slice(k+1).trim();}}return result;}
 const page=declarations('.page'),card=declarations('.card'),photo=declarations('.shop-photo-placeholder'),shop=declarations('.shop-card'),icon=declarations('.storefront-symbol');
 const unit=value=>{assert.match(value,/^[\d.]+rpx$/);return Number.parseFloat(value);};
 for(const width of [320,375,414]){
  const scale=width/750,photoWidth=unit(photo.width)*scale,photoHeight=unit(photo.height)*scale,iconSize=unit(icon['font-size'])*scale;
  const copyWidth=width-2*unit(page.padding)*scale-2*unit(card.padding)*scale-2*Number.parseFloat(card.border)*scale-unit(shop.gap)*scale-photoWidth;
  assert.ok(copyWidth>0,'copy width '+width);assert.ok(iconSize<=photoWidth&&iconSize<=photoHeight,'icon within original placeholder '+width);
  assert.equal(icon.width,'100%');assert.equal(icon.height,'100%');assert.equal(icon.display,'flex');assert.equal(icon['align-items'],'center');assert.equal(icon['justify-content'],'center');
 }
});

test('palette CSS merge leaves all seven other palette files unchanged in the author worktree',()=>{
 const proof=JSON.parse(fs.readFileSync(path.join(evidence,'warm-rose-css/PALETTE-BASE-PINS.json'),'utf8'));
 assert.equal(proof.upload_tip,'193627c0b5c57f38a290db56cfcb536dc0479c4a');assert.equal(proof.preserve_seven.length,7);
 for(const row of proof.preserve_seven){const file=path.resolve(__dirname,'../..',row.file);assert.equal(sha(fs.readFileSync(file)),row.author_before_sha256,row.file);}
});


test('palette CSS preserves all MERGED2 non-palette layout declarations',()=>{
 function layout(css){const result={};css=css.replace(/\/\*[\s\S]*?\*\//g,'');for(const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)){for(const selector of m[1].split(',').map(x=>x.trim())){for(const item of m[2].split(';')){const k=item.indexOf(':');if(k<1)continue;const prop=item.slice(0,k).trim(),value=item.slice(k+1).trim();if(prop==='color'||prop.startsWith('background')||prop.endsWith('-color'))continue;(result[selector]??={})[prop]=value.replace(/#[0-9a-f]{3,8}\b/gi,'PALETTE');}}}return result;}
 const before=fs.readFileSync(path.join(evidence,'warm-rose-css/merged2.css'),'utf8');
 const after=fs.readFileSync(path.join(__dirname,CSS_PATH),'utf8');
 assert.deepEqual(layout(after),layout(before));
});
