const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const sessionModule=require('./session');
const auth=require('./customer-auth');
const event=dataset=>({currentTarget:{dataset}});
function basket(reference='original') {return {reference,user_id:'user1',amount_minor:202,currency:'CNY',
  lines:[{item_id:'item1',name:'Frozen title',revision:1,quantity:2,unit_minor:101,subtotal_minor:202}],
  order:{state:'PENDING',amount_minor:202,currency:'CNY',provider_settlement_verified:false}};}
function harness(){
  let definition,logins=0;const calls=[],writes=[],money=[];
  const wx={login(o){logins++;o.success({code:'fixture'});},request(o){
    // Independent startup directory read; original test queue retains only the operation under test.
    if(o.data&&o.data.operation==='customer.directory')return o.success({statusCode:200,data:{payment_enabled:false,result:{records:[],categories:[],has_more:false,next_cursor:null,visibility:'CURRENT_AUTHORIZED_PROJECT_TENANT',storefront_photo_supported:false}}});

    if(o.url.endsWith('/mini/login'))o.success({statusCode:200,data:{payment_enabled:false,result:{
      session_token:String(logins).repeat(32),expires_at:Math.floor(Date.now()/1000)+1000,
      provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});
    else calls.push(o);
  },requestPayment(){money.push('provider-payment');}};
  vm.runInNewContext(fs.readFileSync(__dirname+'/pages/checkout/index.js','utf8'),{Page:p=>{definition=p;},wx,
    getApp:()=>({globalData:{mode:'CONNECTED',baseUrl:'https://fixture.invalid'}}),
    require:path=>path==='../../customer-auth'?auth:path==='../../session'?sessionModule:path==='../../client'?{makeClient:()=>({reset(){},
      storefront:async()=>({merchant:{name:'fixture'},ads:{}})})}:{createPaymentFlow:()=>({reset(){},pay(){money.push('pay');}})}
  });
  const page={...definition,data:structuredClone(definition.data),setData(patch){writes.push(patch);Object.assign(this.data,patch);}};
  return {page,calls,writes,money,logins:()=>logins,
    reply(index,result){calls[index].success({statusCode:200,data:{payment_enabled:false,result}});},
    fail(index){calls[index].fail({errMsg:'fixture failure'});}};
}
async function ready(){const h=harness();await h.page.onLoad({scene:'shop1'});h.page.setData({commerceEnabled:true,
  reference:'original',userId:'user1',projectCustomerId:'customer1',products:[{item_id:'item1',unit_minor:999,revision:9,quantity:3}],
  orders:[{scene:'shop1',reference:'original',order:{state:'CREATION_UNKNOWN_RECOVER_SAME_REFERENCE'}}]});return h;}
test('explicit recovery sends only original reference and keeps frozen price without another checkout or payment',async()=>{
  const h=await ready(),p=h.page;
  p.selectOrder(event({reference:'original'}));
  const pending=p.recoverPurchase(),call=h.calls[0];
  assert.equal(call.data.operation,'commerce.purchase_recover');
  assert.deepEqual(Object.keys(call.data.params),['reference']);assert.equal(call.data.params.reference,'original');
  assert.equal(call.header['X-Community-Session'],'1'.repeat(32));assert.equal(call.data.scene,'shop1');
  h.reply(0,basket());await pending;
  assert.equal(p.data.amount,'202');assert.equal(p.data.orders[0].order.state,'PENDING');
  assert.equal(p.data.orders[0].lines[0].revision,1);assert.equal(p.data.products[0].unit_minor,999);
  assert.equal(p.data.products[0].quantity,3);assert.equal(p.data.pending,false);assert.match(p.data.status,/未发起支付/);
  assert.equal(h.calls.length,1);assert.equal(h.money.length,0);assert.equal(h.logins(),1);
});
test('unknown result keeps original reference and only explicit retry sends a second request',async()=>{
  const h=await ready();let pending=h.page.recoverPurchase();await h.page.recoverPurchase();assert.equal(h.calls.length,1);
  h.fail(0);await pending;assert.equal(h.page.data.pending,false);assert.equal(h.page.data.reference,'original');
  assert.match(h.page.data.status,/可再次显式恢复/);assert.equal(h.calls.length,1);
  pending=h.page.recoverPurchase();assert.equal(h.calls.length,2);h.reply(1,basket());await pending;
  assert.equal(h.calls.every(call=>call.data.operation==='commerce.purchase_recover'&&call.data.params.reference==='original'),true);
});
test('terminal original state remains terminal and never starts another payment',async()=>{
  const h=await ready();const result=basket();result.order.state='CANCELLED';
  const pending=h.page.recoverPurchase();h.reply(0,result);await pending;
  assert.equal(h.page.data.orders[0].order.state,'CANCELLED');assert.match(h.page.data.status,/CANCELLED/);assert.equal(h.money.length,0);
});
for(const change of ['order','unload','reauth','scene','customer','user'])for(const outcome of ['success','error']){
  test(`recovery ${outcome} after ${change} cannot populate or release another context`,async()=>{
    const h=await ready(),p=h.page,pending=p.recoverPurchase();
    if(change==='order')p.inputReference({detail:{value:'another'}});
    if(change==='unload')p.onUnload();
    if(change==='reauth')await p.session.login();
    if(change==='scene')p.scene='shop2';
    if(change==='customer')p.setData({projectCustomerId:'customer2'});
    if(change==='user')p.setData({userId:'user2'});
    const before=JSON.stringify(p.data),count=h.writes.length;
    outcome==='success'?h.reply(0,basket()):h.fail(0);await pending;
    assert.equal(JSON.stringify(p.data),before);assert.equal(h.writes.length,count);assert.equal(h.calls.length,1);
  });
}
test('same-reference ABA selection and late finally do not release a newer recovery',async()=>{
  const h=await ready(),p=h.page,old=p.recoverPurchase();
  p.inputReference({detail:{value:'another'}});p.inputReference({detail:{value:'original'}});
  const fresh=p.recoverPurchase();assert.equal(h.calls.length,2);h.fail(0);await old;assert.equal(p.data.pending,true);
  h.reply(1,basket());await fresh;assert.equal(p.data.pending,false);assert.equal(p.data.amount,'202');
});
test('mismatched reference owner amount or frozen lines cannot replace order view',async()=>{
  for(const patch of [{reference:'other'},{user_id:'other-user'},{amount_minor:203},{lines:[]},
    {lines:[{...basket().lines[0],subtotal_minor:1}]},{order:{...basket().order,state:'UNTRUSTED'}}]){
    const h=await ready(),pending=h.page.recoverPurchase();h.reply(0,{...basket(),...patch});await pending;
    assert.equal(h.page.data.amount,'');assert.match(h.page.data.status,/恢复结果未确认/);assert.equal(h.page.data.pending,false);
    assert.equal(h.page.data.orders[0].order.state,'CREATION_UNKNOWN_RECOVER_SAME_REFERENCE');
  }
});
test('empty reference disconnected unloaded and non-commerce page cannot invoke recovery',async()=>{
  for(const change of ['empty','session','unload','commerce']){
    const h=await ready();
    if(change==='empty')h.page.setData({reference:''});
    if(change==='session')h.page.session=null;
    if(change==='unload')h.page.onUnload();
    if(change==='commerce')h.page.setData({commerceEnabled:false});
    await h.page.recoverPurchase();assert.equal(h.calls.length,0);
  }
});
test('native page exposes explicit original-order recovery button',()=>{
  const source=fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8');
  assert.match(source,/bindtap="recoverPurchase"/);assert.match(source,/恢复原商品订单（不重新占库存）/);
});
