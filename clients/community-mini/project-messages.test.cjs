const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const sessionModule=require('./session');
const auth=require('./customer-auth');
const event=(more=false)=>({currentTarget:{dataset:{operation:'project_messages',...(more?{more:'true'}:{})}}});
function harness(){
  let definition,loginCount=0;
  const calls=[],writes=[];
  const wx={login(o){loginCount++;o.success({code:'fixture-code'});},request(o){
    // Independent startup directory read; original test queue retains only the operation under test.
    if(o.data&&o.data.operation==='customer.directory')return o.success({statusCode:200,data:{payment_enabled:false,result:{records:[],categories:[],has_more:false,next_cursor:null,visibility:'CURRENT_AUTHORIZED_PROJECT_TENANT',storefront_photo_supported:false}}});

    if(o.url.endsWith('/mini/login'))o.success({statusCode:200,data:{payment_enabled:false,result:{
      session_token:'s'.repeat(32),expires_at:Math.floor(Date.now()/1000)+1000,
      provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});
    else calls.push(o);
  }};
  vm.runInNewContext(fs.readFileSync(__dirname+'/pages/checkout/index.js','utf8'),{
    Page:value=>{definition=value;},wx,
    getApp:()=>({globalData:{mode:'CONNECTED',baseUrl:'https://fixture.invalid',commerce:false,payments:false}}),
    require:path=>path==='../../customer-auth'?auth:path==='../../session'?sessionModule:path==='../../client'?{
      makeClient:()=>({reset(){},storefront:async()=>({merchant:{name:'fixture'},ads:{}})})
    }:{createPaymentFlow:()=>({reset(){}})}
  });
  const page={...definition,data:structuredClone(definition.data),setData(patch){writes.push(patch);Object.assign(this.data,patch);}};
  return {page,calls,writes,loginCount:()=>loginCount,
    reply(index,result){calls[index].success({statusCode:200,data:{payment_enabled:false,result}});},
    fail(index){calls[index].fail({errMsg:'delayed failure'});}};
}
async function ready(){const h=harness();await h.page.onLoad({scene:'shop1'});h.page.setData({userId:'user1',projectCustomerId:'customer1'});return h;}
const record=n=>({id:'m_'+String(n).padStart(32,'0'),created:100+Math.floor(n/20),channel:'WEB',status:'ARCHIVED',body:'synthetic '+n});
function page(start,count,more=false){const records=Array.from({length:count},(_,n)=>record(start+n));return {
  records,has_more:more,next_cursor:more?JSON.stringify([records.at(-1).created,records.at(-1).id]):null,
  source:'ORIGINAL_CENTER_ARCHIVE',provider_reply_verified:false};}
async function complete(h,response,more=false){const i=h.calls.length,pending=h.page.projectAction(event(more));h.reply(i,response);await pending;}

test('actual session sends keyset cursor and 201 records load exactly once',async()=>{
  const h=await ready();
  for(let n=0;n<5;n++){
    const i=h.calls.length,pending=h.page.projectAction(event(n>0));
    const body=h.calls[i].data;
    assert.equal(body.operation,'commerce.project_messages');
    assert.equal(body.scene,'shop1');
    assert.deepEqual(Object.keys(body.params),['after_id']);
    assert.equal(body.params.after_id,n?JSON.stringify([record(n*50-1).created,record(n*50-1).id]):'');
    h.reply(i,page(n*50,n===4?1:50,n<4));await pending;
  }
  assert.equal(h.page.data.projectMessages.length,201);
  assert.equal(new Set(h.page.data.projectMessages.map(r=>r.id)).size,201);
  assert.equal(h.page.data.projectMessages.at(-1).body,'synthetic 200');
  assert.equal(h.page.data.projectMessagesMore,false);assert.equal(h.page.data.projectMessagesCursor,null);
  assert.equal(h.page.data.projectMessagesLoaded,true);assert.equal(h.page.data.pending,false);
  await h.page.projectAction(event(true));assert.equal(h.calls.length,5);assert.equal(h.loginCount(),1);
});

test('failed continuation retains old history and cursor for explicit retry only',async()=>{
  const h=await ready();await complete(h,page(0,50,true));const before=JSON.stringify(h.page.data.projectMessages),cursor=h.page.data.projectMessagesCursor;
  const pending=h.page.projectAction(event(true));await h.page.projectAction(event(true));assert.equal(h.calls.length,2);
  h.fail(1);await pending;
  assert.equal(JSON.stringify(h.page.data.projectMessages),before);assert.equal(h.page.data.projectMessagesCursor,cursor);
  assert.match(h.page.data.projectMessagesStatus,/SERVICE_RESULT_UNKNOWN/);assert.equal(h.page.data.pending,false);
  await complete(h,page(50,1),true);assert.equal(h.page.data.projectMessages.length,51);
});

test('explicit refresh replaces history, empty result ends paging, no false provider reply',async()=>{
  const h=await ready();await complete(h,page(0,50,true));await complete(h,page(0,0));
  assert.equal(h.page.data.projectMessages.length,0);assert.equal(h.page.data.projectMessagesLoaded,true);
  assert.equal(h.page.data.projectMessagesMore,false);assert.equal(h.page.data.projectMessagesCursor,null);
  assert.match(h.page.data.projectMessagesStatus,/不代表已获得人工回复/);
});

const switches={
  user:p=>p.setData({userId:'other-user'}),customer:p=>p.setData({projectCustomerId:'other-customer'}),
  scene:p=>{p.scene='shop2';},session:p=>{p.session={clear(){},commerce(){throw Error('must not call replacement');}};},
  generation:p=>p.session.clear(),unload:p=>p.onUnload(),
  selection:p=>{p._projectRequest=null;p.setData({projectReferenceItem:'new-item'});}
};
for(const [name,change] of Object.entries(switches))for(const result of ['success','error'])test(`stale continuation ${result} after ${name} cannot write or unlock new context`,async()=>{
  const h=await ready();await complete(h,page(0,50,true));const pending=h.page.projectAction(event(true));
  change(h.page);h.page.setData({pending:true,status:'new identity'});const before=JSON.stringify(h.page.data),writes=h.writes.length;
  if(result==='success')h.reply(1,page(50,1));else h.fail(1);await pending;
  assert.equal(JSON.stringify(h.page.data),before);assert.equal(h.writes.length,writes);assert.equal(h.calls.length,2);assert.equal(h.loginCount(),1);
});
for(const name of ['user','customer','scene','generation'])test(`new ${name} clears old history and cannot reuse old cursor`,async()=>{
  const h=await ready();await complete(h,page(0,50,true));switches[name](h.page);
  await h.page.projectAction(event(true));
  assert.equal(h.page.data.projectMessages.length,0);assert.equal(h.page.data.projectMessagesCursor,null);
  assert.equal(h.page.data.projectMessagesLoaded,false);assert.equal(h.calls.length,1);
});

test('old failed request cannot release new request after identity ABA',async()=>{
  const h=await ready(),p=h.page,old=p.projectAction(event());
  p.setData({pending:false,userId:'other'});const fresh=p.projectAction(event());
  h.fail(0);await old;assert.equal(p.data.pending,true);
  h.reply(1,page(0,1));await fresh;assert.equal(p.data.pending,false);assert.equal(p.data.projectMessages.length,1);
});

test('server evidence or extra fields never enter page state',async()=>{
  const h=await ready(),response=page(0,1);Object.assign(response.records[0],{raw_payload:'private',provider_ref:'private',evidence:{sender_id:'private'}});
  await complete(h,response);assert.deepEqual(Object.keys(h.page.data.projectMessages[0]).sort(),['body','channel','created','id','status']);
  assert.equal(JSON.stringify(h.page.data.projectMessages).includes('private'),false);
});
const malformed={
  missing_metadata:r=>{delete r.has_more;},false_source:r=>{r.source='UNVERIFIED';},claimed_provider_reply:r=>{r.provider_reply_verified=true;},
  missing_body:r=>{delete r.records[0].body;},invalid_time:r=>{r.records[0].created=1.2;},duplicate:r=>{r.records[1]=r.records[0];},
  unordered:r=>{[r.records[0],r.records[1]]=[r.records[1],r.records[0]];},bad_cursor:r=>{r.next_cursor='bad';},
  false_cursor:r=>{r.next_cursor=JSON.stringify([0,'missing']);},partial_more:r=>{r.records.pop();},
  unbounded:r=>{r.records.push(record(50));},bad_id:r=>{r.records[0].id='bad/id';}
};
for(const [name,change] of Object.entries(malformed))test(`invalid page ${name} fails closed without moving cursor`,async()=>{
  const h=await ready(),response=page(0,50,true);change(response);await complete(h,response);
  assert.equal(h.page.data.projectMessages.length,0);assert.equal(h.page.data.projectMessagesCursor,null);
  assert.equal(h.page.data.projectMessagesLoaded,false);assert.match(h.page.data.projectMessagesStatus,/返回无效/);assert.equal(h.page.data.pending,false);
});

test('response behind continuation cursor cannot duplicate or regress history',async()=>{
  const h=await ready();await complete(h,page(0,50,true));const cursor=h.page.data.projectMessagesCursor;
  await complete(h,page(0,1),true);assert.equal(h.page.data.projectMessages.length,50);assert.equal(h.page.data.projectMessagesCursor,cursor);
  assert.match(h.page.data.projectMessagesStatus,/返回无效/);
});

test('consumer storefront excludes internal project feedback controls',()=>{
  // Keep the current shopper boundary; transport pagination/race tests remain unchanged.
  const source=fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8');
  assert.doesNotMatch(source,/projectAction|projectMessagesMore|project_messages/);
  assert.match(source,/bindtap="loadOrders"/);
});
