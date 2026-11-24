'use strict';
let epoch=0;
function current(){return epoch;}
function active(snapshot){return snapshot===epoch;}
function revokePages(pages,status='登录已退出，请重新登录'){
  epoch++;
  const snapshot=[...(Array.isArray(pages)?pages:[])];
  for(const page of snapshot){
    if(page&&typeof page.customerSessionRevoked==='function')page.customerSessionRevoked(status);
  }
  return epoch;
}
const routes={home:'/pages/home/index',recommendations:'/pages/checkout/index?view=recommendations',orders:'/pages/checkout/index?view=orders',profile:'/pages/profile/index',join:'/pages/merchant-join/index',merchant:'/pages/merchant/index',services:'/pages/checkout/index?view=services','store-detail':'/pages/checkout/index?view=store-detail'};
function navigate(page,section,wx,app,pages=[]){
  const stale=page._sceneStale||page.sceneStale;if(stale){if(!['home','back'].includes(section)){page.setData({status:'授权场景已切换，请重新进入对应门店'});return;}section='home';}
  if(page.data.pending||page._navigationPending)return;
  if(section==='back')return back(page,wx,app,pages);
  let url=routes[section];if(!url)return;
  const scene=page.sceneInvalid?'':stale?app.globalData.scene||'':page.scene||app.globalData.scene||'';
  if(scene){try{require('./session').parseScene({scene});}catch(_){page.setData({status:'门店入口无效，请重新扫码'});return;}url+=(url.includes('?')?'&':'?')+'scene='+encodeURIComponent(scene);}
  const tab=['home','recommendations','orders','profile'].includes(section);
  if(!stale&&!page._refreshNavigation&&page.route===url.split('?')[0].slice(1)&&page.data.activeSection===section)return;
  page._refreshNavigation=false;
  page._navigationPending=true;
  const done=()=>{page._navigationPending=false;};
  const fail=()=>{done();page.setData({status:'页面暂时无法打开，请重试或返回首页'});};
  try{const method=tab&&typeof wx.redirectTo==='function'?'redirectTo':'navigateTo';wx[method]({url,success:done,fail,complete:done});}catch(_){fail();}
}
function back(page,wx,app,pages=[]){
  if(page.data.pending)return;
  if(pages.length>1&&typeof wx.navigateBack==='function')wx.navigateBack({delta:1,fail:()=>navigate(page,'home',wx,app,pages)});
  else navigate(page,'home',wx,app,pages);
}
function scanStore(page,wx,app,pages=[]){
  if(page.data.pending||page._scanPending)return;
  if(typeof wx.scanCode!=='function'){page.setData({status:'请在微信中扫描商家提供的本小程序门店码进入'});return;}
  page._scanPending=true;
  const fail=()=>{page._scanPending=false;page.setData({status:'扫码未完成。可重试，或先办理商家入驻；未关联任何门店。'});};
  wx.scanCode({onlyFromCamera:false,scanType:['qrCode'],success:result=>{
    page._scanPending=false;
    // wx.path is supplied only for this mini program's code. Never follow arbitrary URLs.
    const m=typeof result.path==='string'&&/^\/?pages\/(?:home|checkout)\/index\?scene=([^&#]+)$/.exec(result.path);
    try{if(!m)throw Error('INVALID_SCENE');const scene=require('./session').parseScene({scene:m[1]});app.globalData.scene=scene;page.scene=scene;page.sceneInvalid=false;page._refreshNavigation=true;navigate(page,'home',wx,app,pages);}
    catch(_){page.setData({status:'请扫描本小程序的有效门店码，其他二维码不会关联门店。'});}
  },fail});
}
// Existing authenticated workspaces check remains authoritative at both ends.
function openingTarget(a){
 if(!a||a.opening_state!=='OPENED'||typeof a.opening_scene!=='string'||!/^[A-Za-z0-9_-]{1,32}$/.test(a.opening_scene)||
    typeof a.opening_workspace!=='string'||!a.opening_workspace||a.opening_workspace.length>256)return null;
 return {scene:a.opening_scene,workspace:a.opening_workspace};
}
function openingSession(s,g,e){return !!s&&typeof s.getGeneration==='function'&&typeof s.isAuthenticated==='function'&&
 s.getGeneration()===g&&s.isAuthenticated()&&active(e);}
const boundOpening=new WeakMap();
async function navigateOpening(page,a,wx,app){
 const target=openingTarget(a),s=page.session,e=current(),ambient=app.globalData.scene,
       g=s&&typeof s.getGeneration==='function'?s.getGeneration():null;
 if(!target||page.data.pending||page._navigationPending||page._dead||page.dead||page.sceneStale||page._sceneStale||
    !openingSession(s,g,e))return;
 const key={...target,s,g,e,ambient};page._navigationPending=true;
 const candidateCurrent=()=>page.route!=='pages/merchant-join/index'||(page.data.application===a&&page.data.openingState==='OPENED');
 const currentPage=()=>page.session===s&&openingSession(s,g,e)&&!page._dead&&!page.dead&&!page.sceneStale&&!page._sceneStale&&app.globalData.scene===ambient;
 const clear=()=>{page._navigationPending=false;if(boundOpening.get(app)===key)boundOpening.delete(app);};
 const fail=()=>{clear();if(currentPage())page.setData({status:'该申请对应的商家工作台暂不可用，请刷新进度'});};
 try{
   const r=await s.merchant(target.scene,'workspaces',{});
   if(!currentPage()||!candidateCurrent()){clear();return;}
   if(!r||!Array.isArray(r.workspaces)||!r.workspaces.includes(target.workspace)){fail();return;}
   boundOpening.set(app,key);
   wx.navigateTo({url:'/pages/merchant/index?fromVerifiedOpening=1',complete:()=>{page._navigationPending=false;},fail});
 }catch(_){fail();}
}
function takeOpening(app){
 const i=boundOpening.get(app);boundOpening.delete(app);
 return i&&i.ambient===app.globalData.scene&&openingSession(i.s,i.g,i.e)?i:null;
}
module.exports={current,active,revokePages,navigate,back,scanStore,openingTarget,openingSession,navigateOpening,takeOpening};
