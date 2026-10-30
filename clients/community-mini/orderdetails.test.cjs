const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const sessionModule=require('./session');
const auth=require('./customer-auth');
const event=dataset=>({currentTarget:{dataset}});
const scope={tenant_id:'tenant1',merchant_id:'merchant1',store_id:'store1'};
function basket(reference='order1') {return {reference,user_id:'user1',scope,amount_minor:250,currency:'CNY',
  lines:[{item_id:'item1',name:'Frozen product title',revision:2,quantity:2,unit_minor:125,subtotal_minor:250}],
  order:{state:'SUCCESS',amount_minor:250,currency:'CNY',provider_transaction_id:null,provider_settlement_verified:false}};}
function application(reference='order1',status='SUBMITTED'){return {reference,application:{reference,application_id:'ra_original',
  user_id:'user1',project:'project1',scope,amount_minor:125,reason:'Original reason',status,revision:3,opinion:'Original opinion'}};}
function harness(){
  let definition,logins=0;const calls=[],writes=[],money=[];
  const wx={login(o){logins++;o.success({code:'fixture'});},request(o){
    // Independent startup directory read; original test queue retains only the operation under test.
    if(o.data&&o.data.operation==='customer.directory')return o.success({statusCode:200,data:{payment_enabled:false,result:{records:[],categories:[],has_more:false,next_cursor:null,visibility:'CURRENT_AUTHORIZED_PROJECT_TENANT',storefront_photo_supported:false}}});
if(o.url.endsWith('/mini/login'))o.success({statusCode:200,data:{payment_enabled:false,result:{
    session_token:String(logins).repeat(32),expires_at:Math.floor(Date.now()/1000)+1000,provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});else calls.push(o);}};
  vm.runInNewContext(fs.readFileSync(__dirname+'/pages/checkout/index.js','utf8'),{Page:p=>{definition=p;},wx,
    getApp:()=>({globalData:{mode:'CONNECTED',baseUrl:'https://fixture.invalid'}}),
    require:path=>path==='../../customer-auth'?auth:path==='../../session'?sessionModule:path==='../../client'?{makeClient:()=>({reset(){},storefront:async()=>({merchant:{name:'fixture'},ads:{}})})}:{createPaymentFlow:()=>({reset(){},pay(){money.push('pay');},query(){money.push('query');}})}
  });
  const page={...definition,data:structuredClone(definition.data),setData(patch){writes.push(patch);Object.assign(this.data,patch);}};
  return {page,calls,writes,money,logins:()=>logins,reply(index,result){calls[index].success({statusCode:200,data:{payment_enabled:false,result}});},fail(index){calls[index].fail({errMsg:'fixture failure'});}};
}
async function ready(){const h=harness();await h.page.onLoad({scene:'shop1'});h.page.setData({commerceEnabled:true,reference:'order1',userId:'user1',projectCustomerId:'customer1'});return h;}
const starts={details:p=>p.loadOrderDetails(),refund:p=>p.recoverRefundApplication()};
const results={details:basket,refund:application};
test('purchase details use frozen original line prices after catalog changes and only send original reference',async()=>{
  const h=await ready();h.page.setData({products:[{item_id:'item1',name:'Current title',revision:99,unit_minor:99999,quantity:50}]});
  const pending=h.page.loadOrderDetails();const c=h.calls[0];assert.equal(c.data.operation,'commerce.purchase_read');
  assert.deepEqual(Object.keys(c.data.params),['reference']);assert.equal(c.data.params.reference,'order1');assert.equal(c.data.scene,'shop1');
  assert.equal(c.header['X-Community-Session'],'1'.repeat(32));h.reply(0,basket());await pending;
  const line=h.page.data.orderDetails.lines[0];assert.equal(line.name,'Frozen product title');assert.equal(line.quantity,2);assert.equal(line.unit_minor,125);assert.equal(line.subtotal_minor,250);assert.equal(line.revision,2);
  assert.equal(h.page.data.orderDetails.amount_minor,250);assert.equal(h.page.data.products[0].unit_minor,99999);assert.equal(h.page.data.orderDetailsPending,false);
});
test('missing basket, mismatched reference/user or invalid totals never manufacture line items',async()=>{
  for(const patch of [{lines:null},{lines:[]},{reference:'other-order'},{user_id:'other-user'},{amount_minor:999},
    {lines:[{...basket().lines[0],subtotal_minor:1}]}]){
    const h=await ready(),pending=h.page.loadOrderDetails();h.reply(0,{...basket(),...patch});await pending;
    assert.equal(h.page.data.orderDetails,null);assert.match(h.page.data.orderDetailsStatus,/快照未确认/);assert.equal(h.calls.length,1);
  }
});
test('fulfillment is displayed only from original record; SUCCESS alone performs no completion/payment',async()=>{
  const h=await ready();let pending=h.page.loadOrderDetails();h.reply(0,basket());await pending;
  assert.equal(h.page.data.orderDetails.fulfillment_state,'');assert.equal(h.page.data.orderDetails.fulfillment_revision,null);
  assert.equal(h.page.data.orderDetails.order_state,'SUCCESS');assert.equal(h.calls.length,1);assert.equal(h.money.length,0);
  pending=h.page.loadOrderDetails();h.reply(1,{...basket(),fulfillment_state:'COMPLETED',fulfillment_revision:4,completion_note:'Original fulfillment',completed_at:123});await pending;
  assert.equal(h.page.data.orderDetails.fulfillment_state,'COMPLETED');assert.equal(h.page.data.orderDetails.completion_note,'Original fulfillment');
  assert.equal(h.calls.every(c=>c.data.operation==='commerce.purchase_read'),true);assert.equal(h.money.length,0);
});
test('refund recovery needs no manually entered ID and restores original version, fields and unknown status verbatim',async()=>{
  const h=await ready(),pending=h.page.recoverRefundApplication();const c=h.calls[0];
  assert.equal(c.data.operation,'commerce.refund_current');assert.deepEqual(Object.keys(c.data.params),['reference']);
  h.reply(0,application('order1','LEGACY_PROVIDER_RESULT_UNKNOWN'));await pending;
  assert.equal(h.page.data.refundApplication,'ra_original');assert.equal(h.page.data.refundAmount,'125');assert.equal(h.page.data.refundReason,'Original reason');
  assert.equal(h.page.data.refundCurrent.revision,3);assert.equal(h.page.data.refundCurrent.status,'LEGACY_PROVIDER_RESULT_UNKNOWN');
  assert.equal(h.page.data.refundCurrent.opinion,'Original opinion');assert.equal(h.calls.length,1);assert.equal(h.money.length,0);
});
test('no prior application is explicit; mismatched order/owner/receipt cannot restore a different application',async()=>{
  const h=await ready();h.page.setData({refundApplication:'old',refundAmount:'9',refundReason:'draft'});
  let pending=h.page.recoverRefundApplication();h.reply(0,{reference:'order1',application:null});await pending;
  assert.equal(h.page.data.refundCurrent,null);assert.equal(h.page.data.refundRecoveryLoaded,true);assert.equal(h.page.data.refundApplication,'');
  for(const result of [{reference:'other',application:null},{reference:'order1'},application('other'),
    {reference:'order1',application:{...application().application,user_id:'other-user'}},
    {reference:'order1',application:{...application().application,revision:-1}}]){
    pending=h.page.recoverRefundApplication();h.reply(h.calls.length-1,result);await pending;
    assert.equal(h.page.data.refundCurrent,null);assert.equal(h.page.data.refundRecoveryLoaded,false);assert.ok(h.page.data.refundRecoveryStatus);
  }
});
for(const [name,start] of Object.entries(starts))for(const change of ['order','unload','reauth','scene','customer','user'])for(const outcome of ['success','error']){
  test(`${name} late ${outcome} after ${change} cannot populate another order or identity`,async()=>{
    const h=await ready(),p=h.page,pending=start(p);
    if(change==='order')p.inputReference({detail:{value:'order2'}});
    if(change==='unload')p.onUnload();
    if(change==='reauth')await p.session.login();
    if(change==='scene')p.scene='shop2';
    if(change==='customer')p.setData({projectCustomerId:'customer2'});
    if(change==='user')p.setData({userId:'user2'});
    const count=h.writes.length;outcome==='success'?h.reply(0,results[name]()):h.fail(0);await pending;
    assert.equal(p.data.orderDetails,null);assert.equal(p.data.refundCurrent,null);assert.equal(p.data.refundApplication,'');
    assert.equal(p.data.orderDetailsStatus,'');assert.equal(p.data.refundRecoveryStatus,'');
    if(change==='unload'||change==='order')assert.equal(h.writes.length,count);
    assert.equal(h.calls.length,1);assert.equal(h.logins(),change==='reauth'?2:1);
  });
}
for(const [name,start] of Object.entries(starts))test(`${name} newer request ownership survives old finally, and same-order ABA switch is stale`,async()=>{
  const h=await ready(),p=h.page,old=start(p);
  p.inputReference({detail:{value:'order2'}});p.inputReference({detail:{value:'order1'}});
  const fresh=start(p);h.fail(0);await old;
  assert.equal(p.data[name==='details'?'orderDetailsPending':'refundRecoveryPending'],true);
  h.reply(1,results[name]());await fresh;assert.equal(p.data[name==='details'?'orderDetailsPending':'refundRecoveryPending'],false);
});
for(const [name,start] of Object.entries(starts))test(`${name} double click is ignored and failure allows explicit read-only retry`,async()=>{
  const h=await ready(),pending=start(h.page);await start(h.page);assert.equal(h.calls.length,1);
  h.fail(0);await pending;const retry=start(h.page);assert.equal(h.calls.length,2);h.reply(1,results[name]());await retry;
  assert.ok(h.page.data[name==='details'?'orderDetails':'refundCurrent']);
  assert.equal(h.calls.every(c=>['commerce.purchase_read','commerce.refund_current'].includes(c.data.operation)),true);
});
test('editing refund form during recovery keeps new draft and never starts refund execution',async()=>{
  const h=await ready(),pending=h.page.recoverRefundApplication();h.page.inputRefund({currentTarget:{dataset:{field:'refundReason'}},detail:{value:'New draft'}});
  h.reply(0,application());await pending;assert.equal(h.page.data.refundReason,'New draft');assert.equal(h.page.data.refundApplication,'');
  assert.equal(h.page.data.refundRecoveryPending,false);assert.equal(h.calls.length,1);
});
test('new selection clears displayed details and recovered application before any new request',async()=>{
  const h=await ready();let pending=h.page.loadOrderDetails();h.reply(0,basket());await pending;
  pending=h.page.recoverRefundApplication();h.reply(1,application());await pending;
  h.page.selectOrder(event({reference:'order2'}));assert.equal(h.page.data.orderDetails,null);assert.equal(h.page.data.refundCurrent,null);
  assert.equal(h.page.data.refundApplication,'');assert.equal(h.page.data.refundAmount,'');assert.equal(h.page.data.refundReason,'');assert.equal(h.calls.length,2);
});
test('detail/recovery errors cannot change payment status or release a payment pending flag',async()=>{
  const h=await ready(),pending=h.page.loadOrderDetails();h.page.setData({status:'Original payment outcome',pending:true});h.fail(0);await pending;
  assert.equal(h.page.data.status,'Original payment outcome');assert.equal(h.page.data.pending,true);
});
test('WXML exposes frozen totals, read-only fulfillment and separate recovery without completion action',()=>{
  const markup=fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8');
  for(const token of ['loadOrderDetails','recoverRefundApplication','item.unit_minor','item.subtotal_minor','orderDetails.fulfillment_state','refundCurrent.status'])assert.ok(markup.includes(token));
  assert.ok(markup.includes('不作为支付核验或财务核销凭证'));assert.ok(markup.includes('不会执行退款'));
  assert.doesNotMatch(markup,/bindtap="(?:order_complete|refund_execute|refund_decide)"/);
});

for(const suppliedId of ['', 'ra_existing_request'])for(const settleFirst of [false,true])test(`late refund read cannot erase ${suppliedId?'supplied':'generated'} application identity ${settleFirst?'after timeout':'while submitting'}`,async()=>{
  const h=await ready(),p=h.page;p.setData({refundApplication:suppliedId,refundAmount:'125',refundReason:'New requested reason'});
  const read=p.recoverRefundApplication();const submit=p.requestRefund();const applicationId=p.data.refundApplication;
  assert.ok(applicationId);assert.equal(h.calls[1].data.operation,'commerce.refund_apply');
  if(settleFirst){h.fail(1);await submit;}
  h.reply(0,{reference:'order1',application:null});await read;
  assert.equal(p.data.refundApplication,applicationId);assert.equal(p.data.refundAmount,'125');assert.equal(p.data.refundReason,'New requested reason');
  assert.equal(p.data.refundRecoveryLoaded,false);assert.equal(p.data.refundRecoveryPending,false);
  if(!settleFirst){assert.equal(p.data.pending,true);h.fail(1);await submit;}
  assert.equal(p.data.refundApplication,applicationId);assert.match(p.data.status,/保留原申请编号/);
});
test('a changed refund form through setData also invalidates a late recovery receipt',async()=>{
  const h=await ready(),p=h.page,read=p.recoverRefundApplication();
  p.setData({refundApplication:'ra_new_draft',refundAmount:'200',refundReason:'New reason'});
  h.reply(0,application());await read;
  assert.equal(p.data.refundApplication,'ra_new_draft');assert.equal(p.data.refundAmount,'200');assert.equal(p.data.refundReason,'New reason');
});
