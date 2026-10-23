const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const auth=require('./customer-auth');
const id='a'.repeat(64);
function fixture(){
 let definition;const calls=[];let isRead=false;
 const session={login:async()=>{},clear(){},commerce:async(scene,operation,params)=>{calls.push({scene,operation,params});
  if(operation==='profile_read')return {user_id:'user-1',project_customer_id:'customer-1',nickname:'Fixture',contact:'',version:1};
  if(operation==='notices')return {records:[{id,message:'审核资料有更新',read:isRead}],has_more:false,next_cursor:null};
  if(operation==='notice_read'){assert.equal(params.notice_id,id);isRead=true;return {id,read:true};}
  throw Error('unexpected operation '+operation);
 }};
 vm.runInNewContext(fs.readFileSync(__dirname+'/pages/profile/index.js','utf8'),{
  Page:value=>{definition=value;},
  require:path=>path==='../../session'?{parseScene:o=>o.scene,createSession:()=>session,customerError:e=>e.message}:auth,
  getApp:()=>({globalData:{baseUrl:'https://fixture.invalid',scene:'shop1'}}),wx:{}
 });
 const page={...definition,data:{...definition.data},setData(values,callback){Object.assign(this.data,values);if(typeof callback==='function')callback();}};
 return {page,calls,session};
}
test('profile exposes only current-session notices and confirms read acknowledgement',async()=>{
 const {page,calls}=fixture();page._dead=false;page._sceneStale=false;page._authEpoch=auth.current();page.scene='shop1';
 await page.loginAndLoad();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(page.data.authenticated,true);assert.equal(page.data.notices.length,1);assert.equal(page.data.notices[0].message,'审核资料有更新');assert.equal(page.data.notices[0].read,false);
 page.openNotice({currentTarget:{dataset:{id}}});assert.equal(page.data.noticeDetailOpen,true);assert.equal(page.data.selectedNotice.id,id);
 await page.markNoticeRead({currentTarget:{dataset:{id}}});
 assert.equal(page.data.notices[0].read,true);assert.equal(page.data.selectedNotice.read,true);page.backNoticeList();assert.equal(page.data.noticeDetailOpen,false);assert.equal(page.data.selectedNotice,null);assert.equal(calls.filter(x=>x.operation==='notices').length,1);assert.equal(calls.at(-1).operation,'notice_read');
 page.customerSessionRevoked('退出测试');assert.equal(Array.isArray(page.data.notices),true);assert.equal(page.data.notices.length,0);assert.equal(page.data.noticesLoaded,false);
});
test('profile notices reject malformed records without exposing another payload',async()=>{
 const {page}=fixture();page._dead=false;page._authEpoch=auth.current();page._loginAttempt=1;page.scene='shop1';page.session=page.session||null;
 page.session={commerce:async()=>({records:[{id:'bad',message:'private',read:false}],has_more:false,next_cursor:null}),clear(){}};
 page.data.authenticated=true;page.data.loaded=true;
 const request={epoch:page._authEpoch,attempt:page._loginAttempt,session:page.session,scene:page.scene,after:''};page._noticeRequest=request;
 await page.loadNotices(null,page._authEpoch,page._loginAttempt,false);
 assert.equal(page.data.notices.length,0);assert.match(page.data.noticeStatus,/通知列表返回未确认/);
});
