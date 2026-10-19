const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const event=operation=>({currentTarget:{dataset:{operation}}});
function harness(){
 let definition,generation=1;const calls=[],writes=[],money=[];
 const session={getGeneration:()=>generation,clear(){generation++;},commerce(scene,operation,params){return new Promise((resolve,reject)=>calls.push({scene,operation,params,resolve,reject}));}};
 vm.runInNewContext(fs.readFileSync(process.env.COMMUNITY_CHECKOUT_SOURCE||__dirname+'/pages/checkout/index.js','utf8'),{Page:p=>definition=p,require:()=>({}),wx:{}});
 const p={...definition,data:structuredClone(definition.data),_pageGeneration:1,scene:'shop1',session,
  setData(v){writes.push(v);Object.assign(this.data,v);},paymentFlow:{reset(){},pay(){money.push('pay');return new Promise(()=>{});}}};
 p.setData({reference:'orderA',refundApplication:'refundA',refundAmount:'50',refundReason:'reason A',communityId:'co_A',promotionCode:'cp_A',userId:'user1',projectCustomerId:'customer1',commerceEnabled:true});
 return {p,calls,writes,money,reauth:()=>generation++};
}
const refund=()=>({reference:'orderA',application_id:'refundA',user_id:'user1',status:'APPROVED',opinion:'private order A opinion',revision:1,amount_minor:50,reason:'reason A'});
const actions={
 refundRead:{start:p=>p.refundStatus(),result:refund},
 refundSubmit:{start:p=>p.requestRefund(),result:refund},
 communityRead:{start:p=>p.communityAction(event('community_mine')),result:()=>({community_id:'co_A',active:true})},
 communityJoin:{start:p=>p.communityAction({currentTarget:{dataset:{operation:'community_join',id:'co_A'}}}),result:()=>({community_id:'co_A',active:true})},
 communityList:{start:p=>p.communityAction(event('communities')),result:()=>({records:[{id:'co_A',name:'private old scope'}],has_more:false,next_cursor:null})},
 orderList:{start:p=>p.loadOrders(),result:()=>({records:[{reference:'orderA',private:'old order'}],has_more:false,next_cursor:null})}
};
test('late refund reply after normal order selection cannot populate or unlock the new selection',async()=>{
 const h=harness(),old=h.p.refundStatus();h.p.inputReference({detail:{value:'orderB'}});
 h.p.setData({status:'Now order B',pending:true});h.calls[0].resolve(refund());await old;
 assert.equal(h.p.data.reference,'orderB');assert.equal(h.p.data.status,'Now order B');assert.equal(h.p.data.pending,true);
});
test('late community result after scene switch cannot replace current community or pending owner',async()=>{
 const h=harness(),old=h.p.communityAction(event('community_mine'));h.p.scene='shop2';h.p.setData({communityId:'co_B',status:'New scope',pending:true});
 h.calls[0].resolve({community_id:'co_A',active:true});await old;assert.equal(h.p.data.communityId,'co_B');assert.equal(h.p.data.status,'New scope');assert.equal(h.p.data.pending,true);
});
for(const [name,action] of Object.entries(actions))test(`${name} success and error stay bound to lifecycle, scene and identity`,async()=>{
 for(const change of ['scene','session','generation','user','customer','page','unload'])for(const outcome of ['success','error']){
  const h=harness(),p=h.p,pending=action.start(p);
  if(change==='scene')p.scene='shop2';
  if(change==='session')p.session={...p.session};
  if(change==='generation')h.reauth();
  if(change==='user')p.setData({userId:'user2'});
  if(change==='customer')p.setData({projectCustomerId:'customer2'});
  if(change==='page')p._pageGeneration++;
  if(change==='unload')p.onUnload();
  p.setData({status:'NEW CONTEXT',pending:true});const count=h.writes.length;
  outcome==='success'?h.calls[0].resolve(action.result()):h.calls[0].reject(Error('private old error'));
  await pending;assert.equal(h.p.data.status,'NEW CONTEXT',change+' '+outcome);assert.equal(h.p.data.pending,true);
  assert.equal(h.writes.length,count,change+' '+outcome);assert.equal(h.calls.length,1);assert.equal(h.money.length,0);
 }
});
test('refund form ABA invalidates old read and old finally cannot release the replacement read',async()=>{
 const h=harness(),p=h.p,old=p.refundStatus();
 p.inputRefund({currentTarget:{dataset:{field:'refundApplication'}},detail:{value:'refundB'}});
 p.inputRefund({currentTarget:{dataset:{field:'refundApplication'}},detail:{value:'refundA'}});
 const fresh=p.refundStatus();assert.equal(h.calls.length,2);h.calls[0].reject(Error('old error'));await old;assert.equal(p.data.pending,true);
 h.calls[1].resolve(refund());await fresh;assert.equal(p.data.pending,false);assert.match(p.data.status,/APPROVED/);
});
test('community input ABA invalidates old read and keeps replacement ownership',async()=>{
 const h=harness(),p=h.p,old=p.communityAction(event('community_mine'));
 for(const value of ['co_B','co_A'])p.inputCommunity({currentTarget:{dataset:{field:'communityId'}},detail:{value}});
 const fresh=p.communityAction(event('community_mine'));assert.equal(h.calls.length,2);
 h.calls[0].resolve({community_id:'co_stale',active:true});await old;assert.equal(p.data.pending,true);assert.equal(p.data.communityId,'co_A');
 h.calls[1].resolve({community_id:'co_A',active:true});await fresh;assert.equal(p.data.pending,false);
});
test('mutating refund or membership request keeps one frozen submission and cannot be unlocked by input',async()=>{
 for(const name of ['refundSubmit','communityJoin']){
  const h=harness(),p=h.p,pending=actions[name].start(p);await actions[name].start(p);
  p.inputReference({detail:{value:'orderB'}});p.inputRefund({currentTarget:{dataset:{field:'refundReason'}},detail:{value:'changed'}});
  p.inputCommunity({currentTarget:{dataset:{field:'communityId'}},detail:{value:'co_B'}});
  assert.equal(p.data.reference,'orderA');assert.equal(p.data.refundReason,'reason A');assert.equal(p.data.communityId,'co_A');assert.equal(p.data.pending,true);
  await p.pay();assert.equal(h.money.length,0);assert.equal(h.calls.length,1);
  h.calls[0].resolve(actions[name].result());await pending;assert.equal(p.data.pending,false);
 }
});
test('selection may release an obsolete read but its finally cannot unlock a funds action',async()=>{
 const h=harness(),p=h.p,old=p.refundStatus();p.inputReference({detail:{value:'orderB'}});p.pay();
 assert.equal(h.money.length,1);assert.equal(p.data.pending,true);h.calls[0].reject(Error('old'));await old;
 assert.equal(p.data.pending,true);await p.pay();assert.equal(h.money.length,1);
 p.inputReference({detail:{value:'orderC'}});assert.equal(p.data.reference,'orderB');assert.equal(p.data.pending,true);
});
test('refund response must echo original order, application and account before presenting a status',async()=>{
 for(const patch of [{reference:'orderB'},{application_id:'refundB'},{user_id:'user2'},{status:undefined}]){
  const h=harness(),pending=h.p.refundStatus();h.calls[0].resolve({...refund(),...patch});await pending;
  assert.doesNotMatch(h.p.data.status,/APPROVED|private order A opinion/);assert.equal(h.p.data.pending,false);
 }
});
test('unloaded page cannot start refund, membership or order list calls',async()=>{
 for(const action of Object.values(actions)){const h=harness();h.p.onUnload();await action.start(h.p);assert.equal(h.calls.length,0);}
});

test('real mini-session stale replies and errors cannot overwrite another session instance',async()=>{
 const {createSession}=require('./session');
 for(const mode of ['replace','clear','reauth'])for(const outcome of ['success','error']){
  const h=harness(),requests=[];
  const wx={login:options=>options.success({code:'synthetic'}),request:options=>{
   if(options.url.endsWith('/mini/login'))options.success({statusCode:200,data:{payment_enabled:false,result:{provider:'WECHAT_MINIPROGRAM',payment_enabled:false,session_token:'s'.repeat(32),expires_at:1500}}});
   else requests.push(options);
  }};
  const session=createSession(wx,'https://fixture.invalid',()=>1000);await session.login();h.p.session=session;
  const pending=h.p.refundStatus();assert.equal(requests[0].data.operation,'commerce.refund_application');
  if(mode==='replace'){h.p.session=createSession(wx,'https://fixture.invalid',()=>1000);await h.p.session.login();}
  if(mode==='clear')session.clear();if(mode==='reauth')await session.login();
  h.p.setData({status:'new session status',pending:true});const count=h.writes.length;
  if(outcome==='success')requests[0].success({statusCode:200,data:{payment_enabled:false,result:refund()}});else requests[0].fail({errMsg:'old error'});
  await pending;assert.equal(h.p.data.status,'new session status');assert.equal(h.p.data.pending,true);assert.equal(h.writes.length,count);assert.equal(requests.length,1);
 }
});
