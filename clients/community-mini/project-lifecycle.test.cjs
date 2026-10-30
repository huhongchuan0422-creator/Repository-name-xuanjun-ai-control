const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const sessionModule=require('./session');
const auth=require('./customer-auth');
const event=dataset=>({currentTarget:{dataset}});
function harness({delayLogin=false}={}) {
  let definition,loginRequest,loginCount=0;
  const calls=[],writes=[];
  const wx={login(o){loginCount++;o.success({code:'fixture-code'});},request(o){
    // Independent startup directory read; original test queue retains only the operation under test.
    if(o.data&&o.data.operation==='customer.directory')return o.success({statusCode:200,data:{payment_enabled:false,result:{records:[],categories:[],has_more:false,next_cursor:null,visibility:'CURRENT_AUTHORIZED_PROJECT_TENANT',storefront_photo_supported:false}}});

    if(o.url.endsWith('/mini/login')){
      loginRequest=o;
      if(!delayLogin)finishLogin();
    }else calls.push(o);
  }};
  function finishLogin(){loginRequest.success({statusCode:200,data:{payment_enabled:false,result:{
    session_token:'s'.repeat(32),expires_at:Math.floor(Date.now()/1000)+1000,
    provider:'WECHAT_MINIPROGRAM',payment_enabled:false
  }}});}
  vm.runInNewContext(fs.readFileSync(__dirname+'/pages/checkout/index.js','utf8'),{
    Page:value=>{definition=value;},wx,
    getApp:()=>({globalData:{mode:'CONNECTED',baseUrl:'https://fixture.invalid',commerce:false,payments:false}}),
    require:path=>path==='../../customer-auth'?auth:path==='../../session'?sessionModule:path==='../../client'?{
      makeClient:()=>({reset(){},storefront:async()=>({merchant:{name:'fixture'},ads:{}})})
    }:{createPaymentFlow:()=>({reset(){}})}
  });
  const page={...definition,data:structuredClone(definition.data),setData(patch){writes.push(patch);Object.assign(this.data,patch);}};
  function reply(index,result){calls[index].success({statusCode:200,data:{payment_enabled:false,result}});}
  function fail(index){calls[index].fail({errMsg:'delayed failure'});}
  return {page,calls,writes,reply,fail,finishLogin,loginCount:()=>loginCount};
}
async function ready(){
  const h=harness();await h.page.onLoad({scene:'shop1'});
  h.page.setData({projectCustomerId:'customer1',projectReferenceItem:'material1',
    projectReferenceRevision:1,projectReferenceKind:'SECRETREF',projectReference:'ref1',projectFeedback:'feedback1',
    projectChecklist:[{id:'material1',revision:1,submission_type:'SECRETREF'},
      {id:'material2',revision:2,submission_type:'OAUTH'}]});
  return h;
}
const operations={
  save:p=>p.saveProjectReference(),
  submit:p=>p.submitProjectItem(event({item:'material1',revision:1})),
  feedback:p=>p.projectAction(event({operation:'project_feedback'})),
  summary:p=>p.projectAction(event({operation:'project_summary'})),
  checklist:p=>p.projectAction(event({operation:'project_checklist'})),
  messages:p=>p.projectAction(event({operation:'project_messages'}))
};
const results={save:{revision:2},submit:{state:'SUBMITTED'},feedback:{id:'feedback1'},
  summary:{title:'Current project',role:'CUSTOMER',customer_id:'customer2',checklist_overall:'PARTIAL'},
  checklist:{items:[{id:'fresh',revision:3,title:'Fresh requirement'}]},messages:{records:[{id:'message1',created:1,channel:'WEB',status:'ARCHIVED',body:'fixture'}],has_more:false,next_cursor:null,source:'ORIGINAL_CENTER_ARCHIVE',provider_reply_verified:false}};
function switchSelection(p){
  // Simulate navigation releasing the old pending UI before selecting a new requirement.
  p.setData({pending:false});
  p.selectProjectRequirement(event({item:'material2',revision:2}));
  p.setData({status:'new selection',projectFeedback:'new feedback',projectReference:'new reference',pending:true});
}
for(const [name,start] of Object.entries(operations))for(const change of ['switch','unload'])for(const outcome of ['success','error']){
  test(`${name}: delayed ${outcome} after ${change} cannot write, continue, or reauthenticate`,async()=>{
    const h=await ready(),p=h.page,pending=start(p);
    assert.equal(h.calls.length,1);
    if(change==='switch')switchSelection(p);else p.onUnload();
    const before=JSON.stringify(p.data),writeCount=h.writes.length;
    if(outcome==='success')h.reply(0,results[name]);else h.fail(0);
    await pending;
    assert.equal(JSON.stringify(p.data),before);
    assert.equal(h.writes.length,writeCount);
    assert.equal(h.calls.length,1);
    assert.equal(h.loginCount(),1);
    if(change==='unload'){
      await start(p);assert.equal(h.calls.length,1);assert.equal(h.writes.length,writeCount);
    }
  });
}
for(const name of ['save','submit'])for(const change of ['switch','unload'])for(const outcome of ['success','error']){
  test(`${name}: second checklist ${outcome} after ${change} is ignored including finally`,async()=>{
    const h=await ready(),p=h.page,pending=operations[name](p);
    h.reply(0,results[name]);await new Promise(resolve=>setImmediate(resolve));
    assert.equal(h.calls.length,2);
    assert.equal(h.calls[1].data.operation,'commerce.project_checklist');
    if(change==='switch')switchSelection(p);else p.onUnload();
    const before=JSON.stringify(p.data),writeCount=h.writes.length;
    if(outcome==='success')h.reply(1,results.checklist);else h.fail(1);
    await pending;
    assert.equal(JSON.stringify(p.data),before);assert.equal(h.writes.length,writeCount);
    assert.equal(h.loginCount(),1);
  });
}
for(const [name,start] of Object.entries(operations))test(`${name}: current result still applies and releases pending`,async()=>{
  const h=await ready(),p=h.page,pending=start(p);
  h.reply(0,results[name]);await new Promise(resolve=>setImmediate(resolve));
  if(name==='save'||name==='submit')h.reply(1,results.checklist);
  await pending;assert.equal(p.data.pending,false);
  if(name==='save')assert.equal(p.data.projectReferenceRevision,2);
  if(name==='save'||name==='submit'||name==='checklist')assert.equal(p.data.projectChecklist[0].id,'fresh');
  if(name==='feedback')assert.equal(p.data.projectFeedback,'');
  if(name==='summary')assert.equal(p.data.projectCustomerId,'customer2');
  if(name==='messages')assert.equal(p.data.projectMessages[0].id,'message1');
});
test('old request cannot release a newer project request even when selection returns to same item',async()=>{
  const h=await ready(),p=h.page,old=operations.feedback(p);
  p.setData({pending:false});p.selectProjectRequirement(event({item:'material1',revision:1}));
  const fresh=operations.messages(p);
  h.fail(0);await old;assert.equal(p.data.pending,true);
  h.reply(1,results.messages);await fresh;assert.equal(p.data.pending,false);
  assert.equal(p.data.projectMessages[0].id,'message1');
});
test('unload during login prevents initialization writes and subsequent business requests',async()=>{
  const h=harness({delayLogin:true}),pending=h.page.onLoad({scene:'shop1'});
  await Promise.resolve();h.page.onUnload();const count=h.writes.length;
  h.finishLogin();await pending;
  assert.equal(h.writes.length,count);assert.equal(h.calls.length,0);assert.equal(h.loginCount(),1);
  assert.equal(h.page.client,undefined);
});
test('current error remains visible and releases pending',async()=>{
  const h=await ready(),pending=operations.feedback(h.page);h.fail(0);await pending;
  assert.equal(h.page.data.pending,false);assert.match(h.page.data.status,/SERVICE_RESULT_UNKNOWN/);
});
for(const change of ['scene','session','customer','revision'])for(const outcome of ['success','error'])test(`project context ${change} change rejects stale ${outcome}`,async()=>{
  const h=await ready(),p=h.page,pending=operations.feedback(p);
  if(change==='scene')p.scene='shop2';
  if(change==='session')p.session={clear(){},commerce(){throw Error('must not call replacement session');}};
  if(change==='customer')p.setData({projectCustomerId:'other-customer'});
  if(change==='revision')p.setData({projectReferenceRevision:99});
  const count=h.writes.length;
  if(outcome==='success')h.reply(0,results.feedback);else h.fail(0);
  await pending;assert.equal(h.writes.length,count);assert.equal(h.calls.length,1);assert.equal(h.loginCount(),1);
});
