const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const sessionModule=require('./session');
const event=dataset=>({currentTarget:{dataset}});
const id=n=>n.toString(16).padStart(64,'0');
const record=n=>({id:id(n),kind:'FIXTURE',reference:'fixture-'+n,message:'Synthetic notice '+n,read:false,created_at:n});
function harness(count=63){
  let definition,logins=0;
  const records=Array.from({length:count},(_,i)=>record(i+1)),requests=[],writes=[];
  const wx={login(o){logins++;o.success({code:'fixture'});},request(o){
    if(o.url.endsWith('/mini/login'))o.success({statusCode:200,data:{payment_enabled:false,result:{
      session_token:String(logins).repeat(32),expires_at:Math.floor(Date.now()/1000)+1000,
      provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});else requests.push(o);
  }};
  vm.runInNewContext(fs.readFileSync(__dirname+'/pages/checkout/index.js','utf8'),{
    Page:p=>{definition=p;},wx,getApp:()=>({globalData:{mode:'CONNECTED',baseUrl:'https://fixture.invalid'}}),
    require:path=>path==='../../session'?sessionModule:path==='../../client'?{
      makeClient:()=>({reset(){},storefront:async()=>({merchant:{name:'fixture'},ads:{}})})
    }:{createPaymentFlow:()=>({reset(){}})}
  });
  const page={...definition,data:structuredClone(definition.data),setData(patch){writes.push(patch);Object.assign(this.data,patch);}};
  function reply(index=0,result){const req=requests[index];
    if(result===undefined){
      if(req.data.operation==='commerce.notices'){
        const remaining=records.filter(r=>r.id>req.data.params.after_id);
        result={records:remaining.slice(0,50).map(r=>({...r})),has_more:remaining.length>50,next_cursor:remaining.length>50?remaining[49].id:null};
      }else if(req.data.operation==='commerce.notice_read'){
        const found=records.find(r=>r.id===req.data.params.notice_id);assert.ok(found);found.read=true;result={...found};
      }else throw Error('Unexpected fixture operation '+req.data.operation);
    }
    req.success({statusCode:200,data:{payment_enabled:false,result}});
  }
  return {page,requests,writes,records,reply,fail:index=>requests[index].fail({errMsg:'fixture failure'}),logins:()=>logins};
}
async function ready(count){const h=harness(count);await h.page.onLoad({scene:'shop1'});h.page.setData({userId:'user1',projectCustomerId:'customer1'});return h;}
async function initial(h){const p=h.page.profileAction(event({operation:'notices'}));h.reply(h.requests.length-1);await p;}
test('original notice route loads 50 then appends through server cursor with terminal no-op',async()=>{
  const h=await ready();await initial(h);
  assert.equal(h.page.data.notices.length,50);assert.equal(h.page.data.noticeCursor,id(50));assert.equal(h.page.data.noticesMore,true);
  assert.deepEqual(Object.keys(h.requests[0].data.params),['after_id']);assert.equal(h.requests[0].data.params.after_id,'');
  const more=h.page.loadNotices(event({more:'true'}));assert.equal(h.requests[1].data.params.after_id,id(50));h.reply(1);await more;
  assert.equal(h.page.data.notices.length,63);assert.equal(new Set(h.page.data.notices.map(r=>r.id)).size,63);
  assert.equal(h.page.data.noticeCursor,null);assert.equal(h.page.data.noticesMore,false);assert.equal(h.page.data.noticesLoaded,true);
  await h.page.loadNotices(event({more:'true'}));assert.equal(h.requests.length,2);
});
test('empty and exact-50 terminal pages do not send unnecessary continuation',async()=>{
  for(const count of [0,50]){const h=await ready(count);await initial(h);assert.equal(h.page.data.notices.length,count);
    assert.equal(h.page.data.noticesMore,false);await h.page.loadNotices(event({more:'true'}));assert.equal(h.requests.length,1);}
});
test('pagination deduplicates and never downgrades an acknowledged read item',async()=>{
  const h=await ready();await initial(h);
  let pending=h.page.markNoticeRead(event({id:id(1)}));h.reply(1);await pending;
  pending=h.page.loadNotices(event({more:'true'}));h.reply(2,{records:[record(1),record(51),record(51)],has_more:false,next_cursor:null});await pending;
  assert.equal(h.page.data.notices.length,51);assert.equal(h.page.data.notices[0].read,true);
});
test('mark-read waits for original persisted acknowledgement and refresh returns persisted read state',async()=>{
  const h=await ready();await initial(h);
  const pending=h.page.markNoticeRead(event({id:id(2)}));assert.equal(h.page.data.notices[1].read,false);
  const request=h.requests[1];assert.equal(request.data.operation,'commerce.notice_read');
  assert.deepEqual(Object.keys(request.data.params),['notice_id']);assert.equal(request.data.params.notice_id,id(2));
  assert.equal(request.data.scene,'shop1');assert.equal(request.header['X-Community-Session'],'1'.repeat(32));
  h.reply(1);await pending;assert.equal(h.page.data.notices[1].read,true);assert.equal(h.records[1].read,true);
  await initial(h);assert.equal(h.page.data.notices[1].read,true);
  await h.page.markNoticeRead(event({id:id(2)}));assert.equal(h.requests.length,3);
});
test('double clicks and overlapping list/read actions issue only one request',async()=>{
  const h=await ready();let pending=h.page.loadNotices(event({}));await h.page.loadNotices(event({}));assert.equal(h.requests.length,1);h.reply(0);await pending;
  pending=h.page.markNoticeRead(event({id:id(1)}));await h.page.markNoticeRead(event({id:id(1)}));await h.page.loadNotices(event({more:'true'}));
  assert.equal(h.requests.length,2);h.reply(1);await pending;assert.equal(h.page.data.noticePending,false);
});
test('failed continuation preserves rows and cursor; explicit retry uses identical read-only request',async()=>{
  const h=await ready();await initial(h);const before=JSON.stringify(h.page.data.notices);
  let pending=h.page.loadNotices(event({more:'true'}));h.fail(1);await pending;
  assert.equal(JSON.stringify(h.page.data.notices),before);assert.equal(h.page.data.noticeCursor,id(50));assert.equal(h.page.data.noticePending,false);
  pending=h.page.loadNotices(event({more:'true'}));assert.equal(h.requests[2].data.params.after_id,id(50));h.reply(2);await pending;
  assert.equal(h.page.data.notices.length,63);
});
test('unknown read receipt has no optimistic update; explicit idempotent retry reconciles committed state',async()=>{
  const h=await ready();await initial(h);
  let pending=h.page.markNoticeRead(event({id:id(1)}));h.records[0].read=true;h.fail(1);await pending;
  assert.equal(h.page.data.notices[0].read,false);assert.equal(h.page.data.noticePending,false);
  pending=h.page.markNoticeRead(event({id:id(1)}));assert.equal(h.requests[2].data.params.notice_id,id(1));h.reply(2);await pending;
  assert.equal(h.page.data.notices[0].read,true);
});
test('unlisted, invalid or already-read notice IDs cannot be sent',async()=>{
  const h=await ready();await initial(h);
  for(const value of ['bad',id(999),undefined])await h.page.markNoticeRead(event({id:value}));
  assert.equal(h.requests.length,1);
});
for(const operation of ['page','receipt'])for(const change of ['unload','reauth','scene','user','customer','session'])for(const outcome of ['success','error']){
  test(`late ${operation} ${outcome} after ${change} cannot overwrite, clear newer pending, or reauthenticate`,async()=>{
    const h=await ready();await initial(h);const p=h.page;
    const pending=operation==='page'?p.loadNotices(event({more:'true'})):p.markNoticeRead(event({id:id(1)}));
    if(change==='unload')p.onUnload();
    if(change==='reauth')await p.session.login();
    if(change==='scene')p.scene='shop2';
    if(change==='user')p.setData({userId:'user2'});
    if(change==='customer')p.setData({projectCustomerId:'customer2'});
    if(change==='session')p.session={getGeneration:()=>2,commerce:async()=>({records:[],has_more:false,next_cursor:null})};
    const count=h.writes.length;
    outcome==='success'?h.reply(1):h.fail(1);await pending;
    assert.equal(h.writes.length,count);assert.equal(h.requests.length,2);assert.equal(h.logins(),change==='reauth'?2:1);
  });
}
test('new identity clears prior records/cursor before first page, and old finally cannot release new request',async()=>{
  const h=await ready();await initial(h);const old=h.page.loadNotices(event({more:'true'}));
  await h.page.session.login();const fresh=h.page.loadNotices(event({}));
  assert.equal(h.page.data.notices.length,0);assert.equal(h.page.data.noticeCursor,null);assert.equal(h.page.data.noticePending,true);
  assert.equal(h.requests[2].data.params.after_id,'');assert.equal(h.requests[2].header['X-Community-Session'],'2'.repeat(32));
  h.fail(1);await old;assert.equal(h.page.data.noticePending,true);
  h.reply(2,{records:[],has_more:false,next_cursor:null});await fresh;assert.equal(h.page.data.noticePending,false);
});
test('old notice cannot be marked after identity changes',async()=>{
  const h=await ready();await initial(h);await h.page.session.login();await h.page.markNoticeRead(event({id:id(1)}));
  assert.equal(h.page.data.notices.length,0);assert.equal(h.requests.length,1);
});
test('malformed cursor or mismatched read receipt preserves retryable state',async()=>{
  const h=await ready();await initial(h);
  for(const result of [{records:[record(51)],has_more:true,next_cursor:id(50)},
    {records:[record(51)],has_more:true,next_cursor:'wrong'},
    {records:[],has_more:true,next_cursor:id(51)},
    {records:[{...record(51),read:'false'}],has_more:false,next_cursor:null}]){
    const pending=h.page.loadNotices(event({more:'true'}));h.reply(h.requests.length-1,result);await pending;
    assert.equal(h.page.data.noticeCursor,id(50));assert.equal(h.page.data.notices.length,50);assert.equal(h.page.data.noticePending,false);
  }
  const pending=h.page.markNoticeRead(event({id:id(1)}));h.reply(h.requests.length-1,{...record(2),read:true});await pending;
  assert.equal(h.page.data.notices[0].read,false);assert.equal(h.page.data.notices[1].read,false);
});
test('verified profile identity change invalidates notices and its late page response',async()=>{
  const h=await ready();await initial(h);const old=h.page.loadNotices(event({more:'true'}));
  const profile=h.page.profileAction(event({operation:'profile_read'}));h.reply(2,{version:1,nickname:'Fixture',contact:'',user_id:'user2',project_customer_id:'customer2'});await profile;
  assert.equal(h.page.data.pending,false);assert.equal(h.page.data.notices.length,0);const count=h.writes.length;
  h.reply(1);await old;assert.equal(h.writes.length,count);
});
test('unloaded profile cannot reinstate identity or notifications',async()=>{
  const h=await ready();await initial(h);const pending=h.page.profileAction(event({operation:'profile_read'}));h.page.onUnload();const count=h.writes.length;
  h.reply(1,{version:1,nickname:'Fixture',contact:'',user_id:'user2',project_customer_id:'customer2'});await pending;assert.equal(h.writes.length,count);
});
test('notice markup provides explicit mark-read, continuation and terminal/empty states',()=>{
  const markup=fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8');
  assert.match(markup,/bindtap="markNoticeRead" data-id="{{item.id}}"/);
  assert.match(markup,/wx:if="{{noticesMore}}" bindtap="loadNotices" data-more="true"/);
  assert.match(markup,/通知已全部加载/);assert.match(markup,/暂无通知/);assert.match(markup,/pending\|\|noticePending/);
});

test('notification failure stays in its own UI and cannot overwrite order/payment status',async()=>{
  const h=await ready();await initial(h);const pending=h.page.loadNotices(event({more:'true'}));
  h.page.setData({status:'Original order result',pending:true});h.fail(1);await pending;
  assert.equal(h.page.data.status,'Original order result');assert.equal(h.page.data.pending,true);
  assert.match(h.page.data.noticeStatus,/SERVICE_RESULT_UNKNOWN/);assert.equal(h.page.data.noticePending,false);
});
test('page reload clears old notices immediately and ignores prior response',async()=>{
  const h=await ready();await initial(h);const old=h.page.loadNotices(event({more:'true'}));
  await h.page.onLoad({scene:'shop2'});assert.equal(h.page.data.notices.length,0);const count=h.writes.length;
  h.reply(1);await old;assert.equal(h.writes.length,count);
});

test('profile reauthentication discards old result but releases its owned pending for retry',async()=>{
  const h=await ready();const old=h.page.profileAction(event({operation:'profile_read'}));
  await h.page.session.login();h.reply(0,{version:1,nickname:'Old identity',contact:'',user_id:'old-user',project_customer_id:'old-customer'});await old;
  assert.equal(h.page.data.pending,false);assert.equal(h.page.data.userId,'user1');assert.equal(h.page._profileRequest,null);
  const fresh=h.page.profileAction(event({operation:'profile_read'}));assert.equal(h.requests.length,2);
  h.reply(1,{version:2,nickname:'New identity',contact:'',user_id:'new-user',project_customer_id:'new-customer'});await fresh;
  assert.equal(h.page.data.pending,false);assert.equal(h.page.data.userId,'new-user');
  await initial(h);assert.equal(h.page.data.notices.length,50);
});
test('old profile finally cannot release a newer profile request after reauthentication',async()=>{
  const h=await ready();const old=h.page.profileAction(event({operation:'profile_read'}));
  await h.page.session.login();h.page.setData({pending:false});
  const fresh=h.page.profileAction(event({operation:'profile_read'}));h.fail(0);await old;
  assert.equal(h.page.data.pending,true);
  h.reply(1,{version:2,nickname:'Current identity',contact:'',user_id:'new-user',project_customer_id:'new-customer'});await fresh;
  assert.equal(h.page.data.pending,false);assert.equal(h.page.data.userId,'new-user');
});
