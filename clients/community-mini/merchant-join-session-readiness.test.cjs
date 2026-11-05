'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const sessions=require('./session'),auth=require('./customer-auth'),form=require('./merchant-form');

function fixture(){
 let definition,logins=0,failure=null;
 const calls=[],app={globalData:{baseUrl:'https://fixture.invalid',scene:'shop1'}};
 const wx={
  getAccountInfoSync(){return {miniProgram:{appId:require('./merchant-platform-reference-data').appid}};},
  login(o){logins++;o.success({code:'fixture-'+logins});},
  request(o){
   calls.push(o);
   if(o.url.endsWith('/mini/login'))return o.success({statusCode:200,data:{payment_enabled:false,result:{session_token:String(logins).repeat(32),expires_at:Math.floor(Date.now()/1000)+3600,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});
   const operation=o.data&&o.data.params&&o.data.params.operation;
   if(failure&&failure.operation===operation){const current=failure;failure=null;if(current.status)return o.success({statusCode:current.status,data:{error:'PRIVATE_DETAIL'}});return o.fail({errMsg:'isolated network failure'});}
   if(operation==='catalog')return o.success({statusCode:200,data:{payment_enabled:false,result:{materials:[{id:'business_license',title:'营业执照'}]}}});
   if(operation==='mine')return o.success({statusCode:200,data:{payment_enabled:false,result:{applications:[]}}});
   throw Error('UNPLANNED_REQUEST');
  },enableAlertBeforeUnload(){},disableAlertBeforeUnload(){}
 };
 vm.runInNewContext(fs.readFileSync(__dirname+'/pages/merchant-join/index.js','utf8'),{
  Page:value=>definition=value,wx,getApp:()=>app,getCurrentPages:()=>[],Date,Math,
  require:p=>p==='../../session'?sessions:p==='../../customer-auth'?auth:p==='../../merchant-form'?form:p==='../../merchant-submit'?require('./merchant-submit'):p==='../../merchant-official-fields'?require('./merchant-official-fields'):p==='../../merchant-platform-reference-data'?require('./merchant-platform-reference-data'):require(p)
 });
 const page={...definition,data:structuredClone(definition.data),setData(value){Object.assign(this.data,value);}};
 return {app,wx,page,calls,get logins(){return logins;},fail(operation,status){failure={operation,status};}};
}

async function homeLogin(f){await sessions.getSharedSession(f.wx,f.app.globalData).ensureLogin({automatic:true});}

test('merchant join reuses the valid home session without a second wx.login',async()=>{
 const f=fixture();await homeLogin(f);await f.page.onLoad({scene:'shop1'});
 assert.equal(f.logins,1);assert.equal(f.page.data.authenticated,true);assert.equal(f.page.data.ready,true);assert.equal(f.page.data.readState,'READY');
 assert.deepEqual(f.calls.filter(x=>x.data&&x.data.params).map(x=>x.data.params.operation),['catalog','mine']);
});

for(const operation of ['catalog','mine'])test(operation+' read failure stays authenticated and retries without wx.login',async()=>{
 const f=fixture();await homeLogin(f);f.fail(operation);await f.page.onLoad({scene:'shop1'});
 assert.equal(f.page.data.authenticated,true);assert.equal(f.page.data.ready,false);assert.equal(f.page.data.readState,'FAILED');assert.match(f.page.data.readError,new RegExp(operation==='catalog'?'材料清单':'本人申请'));
 assert.equal(f.logins,1);await f.page.retryApplicantRead();assert.equal(f.logins,1);assert.equal(f.page.data.ready,true);assert.equal(f.page.data.readState,'READY');
});

test('authenticated denial clears the shared session and returns to the login state',async()=>{
 const f=fixture();await homeLogin(f);f.fail('catalog',401);await f.page.onLoad({scene:'shop1'});
 assert.equal(f.page.data.authenticated,false);assert.equal(f.page.data.readState,'IDLE');assert.match(f.page.data.status,/访问权限/);assert.equal(f.logins,1);
 await f.page.connectApplicant();assert.equal(f.logins,2);assert.equal(f.page.data.authenticated,true);assert.equal(f.page.data.ready,true);
});

test('merchant join WXML renders authentication and read failures as separate cards',()=>{
 const markup=fs.readFileSync(__dirname+'/pages/merchant-join/index.wxml','utf8');
 assert.match(markup,/wx:if="{{!authenticated}}"/);assert.match(markup,/readState==='LOADING'/);assert.match(markup,/readState==='FAILED'/);assert.match(markup,/bindtap="retryApplicantRead"/);
});
