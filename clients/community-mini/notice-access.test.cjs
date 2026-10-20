'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const {createSession}=require('./session');
const auth=require('./customer-auth');
const event=dataset=>({currentTarget:{dataset}});
const key=n=>n.toString(16).padStart(64,'0');
const rows=Array.from({length:50},(_,i)=>({id:key(i+1),message:'Synthetic private notification '+i,read:false}));
async function ready(){
  let definition,clock=100,logins=0;
  const requests=[],writes=[];
  const wx={login:o=>{logins++;o.success({code:'fixture'});},request:o=>{
    if(o.url.endsWith('/mini/login'))o.success({statusCode:200,data:{payment_enabled:false,result:{
      session_token:String(logins).repeat(32),expires_at:200,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});
    else requests.push(o);
  }};
  vm.runInNewContext(fs.readFileSync(__dirname+'/pages/checkout/index.js','utf8'),{Page:value=>definition=value,require:p=>p==='../../customer-auth'?auth:{},wx});
  const session=createSession(wx,'https://fixture.invalid',()=>clock);await session.login();
  const page={...definition,data:structuredClone(definition.data),session,scene:'shop1',_pageGeneration:1,_authEpoch:auth.current(),
    setData(value){writes.push(value);Object.assign(this.data,value);}};
  page.setData({userId:'user1',projectCustomerId:'customer1'});
  const reply=(index,result)=>requests[index].success({statusCode:200,data:{payment_enabled:false,result}});
  const pending=page.loadNotices();reply(0,{records:rows.map(row=>({...row})),has_more:true,next_cursor:key(50)});await pending;
  return {page,requests,writes,reply,wx,clock:value=>clock=value,logins:()=>logins};
}
const start=(h,operation)=>operation==='list'?h.page.loadNotices(event({more:'true'})):h.page.markNoticeRead(event({id:key(1)}));
function cleared(page){assert.equal(page.data.notices.length,0);assert.equal(page.data.noticeCursor,null);
  assert.equal(page.data.noticesMore,false);assert.equal(page.data.noticesLoaded,false);assert.equal(page.data.noticePending,false);}
for(const operation of ['list','read'])for(const status of [401,403])test(`${operation} HTTP ${status} removes current private rows and continuation without reauthentication or retry`,async()=>{
  const h=await ready();h.page.setData({status:'Original order result'});
  const pending=start(h,operation);h.requests[1].success({statusCode:status,data:{error:'PRIVATE_RESPONSE_DETAIL'}});await pending;
  cleared(h.page);assert.match(h.page.data.noticeStatus,/拒绝|过期/);assert(!h.page.data.noticeStatus.includes('PRIVATE_RESPONSE_DETAIL'));
  assert.equal(h.page.data.status,'Original order result');assert.equal(h.requests.length,2);assert.equal(h.logins(),1);
  await h.page.markNoticeRead(event({id:key(1)}));await h.page.loadNotices(event({more:'true'}));assert.equal(h.requests.length,2);
  // Explicit fresh read is permitted; the client never treats denial as a new grant.
  const refresh=h.page.loadNotices();assert.equal(h.requests[2].data.params.after_id,'');
  h.reply(2,{records:[],has_more:false,next_cursor:null});await refresh;assert.equal(h.page.data.noticesLoaded,true);
});
for(const operation of ['list','read'])test(`${operation} local expiry removes private rows without sending a request`,async()=>{
  const h=await ready();h.clock(200);await start(h,operation);cleared(h.page);assert.equal(h.requests.length,1);assert.equal(h.logins(),1);
});
for(const operation of ['list','read'])for(const outcome of ['network',500,429,400])test(`${operation} ${outcome} remains unknown or service failure, retaining retryable rows`,async()=>{
  const h=await ready(),before=JSON.stringify(h.page.data.notices),pending=start(h,operation);
  if(outcome==='network')h.requests[1].fail({errMsg:'PRIVATE_NETWORK_DETAIL'});
  else h.requests[1].success({statusCode:outcome,data:{error:'PRIVATE_RESPONSE_DETAIL'}});
  await pending;assert.equal(JSON.stringify(h.page.data.notices),before);assert.equal(h.page.data.noticeCursor,key(50));
  assert.equal(h.page.data.noticesMore,true);assert.equal(h.page.data.noticePending,false);assert.equal(h.requests.length,2);
  assert.match(h.page.data.noticeStatus,/SERVICE_RESULT_UNKNOWN|SERVICE_REQUEST_REJECTED/);assert(!h.page.data.noticeStatus.includes('PRIVATE_'));
});
for(const operation of ['list','read'])for(const change of ['reauth','scene','user','customer','session','unload'])test(`late denied ${operation} after ${change} cannot clear newer UI or release its pending`,async()=>{
  const h=await ready(),pending=start(h,operation),p=h.page;
  if(change==='reauth')await p.session.login();
  if(change==='scene')p.scene='shop2';
  if(change==='user')p.setData({userId:'user2'});
  if(change==='customer')p.setData({projectCustomerId:'customer2'});
  if(change==='session'){p.session=createSession(h.wx,'https://fixture.invalid',()=>100);await p.session.login();}
  if(change==='unload')p.onUnload();
  if(change==='unload'){
    const before=h.writes.length;h.requests[1].success({statusCode:403,data:'PRIVATE_DENIED_BODY'});await pending;assert.equal(h.writes.length,before);
  }else{
    const fresh=p.loadNotices();assert.equal(p.data.noticePending,true);
    const before=h.writes.length;h.requests[1].success({statusCode:403,data:'PRIVATE_DENIED_BODY'});await pending;
    assert.equal(h.writes.length,before);assert.equal(p.data.noticePending,true);
    h.reply(2,{records:[{id:key(99),message:'Current identity notice',read:false}],has_more:false,next_cursor:null});await fresh;
    assert.equal(p.data.notices.length,1);assert.equal(p.data.notices[0].message,'Current identity notice');assert.equal(p.data.noticePending,false);
  }
});
test('HTTP classification exposes only an explicit denial flag, never provider body or credentials',async()=>{
  const h=await ready();
  for(const status of [401,403,400,429,500]){
    const pending=h.page.session.commerce('shop1','notices',{after_id:''});
    h.requests.at(-1).success({statusCode:status,data:{error:'PRIVATE_BODY',session_token:'SECRET'}});
    await assert.rejects(pending,error=>{assert.equal(error.message,'SERVICE_REQUEST_REJECTED');
      assert.equal(error.code,status===401||status===403?'ACCESS_DENIED':undefined);
      assert(!JSON.stringify(error).includes('PRIVATE_BODY'));assert(!JSON.stringify(error).includes('SECRET'));return true;});
  }
  assert.equal(h.logins(),1);
});
for(const status of [401,403])test(`payment preparation HTTP ${status} does not invoke SDK, retry, or relogin`,async()=>{
  const h=await ready();let sdk=0;
  const {createPaymentFlow}=require('./payment');
  const flow=createPaymentFlow({requestPayment(){sdk++;}},(operation,reference)=>h.page.session.payment('shop1',operation,reference));
  const pending=flow.pay('fixture-order');assert.equal(h.requests[1].data.operation,'prepare');
  h.requests[1].success({statusCode:status,data:{error:'PRIVATE_BODY'}});
  await assert.rejects(pending,error=>error.code==='ACCESS_DENIED');assert.equal(sdk,0);assert.equal(h.requests.length,2);assert.equal(h.logins(),1);
});
