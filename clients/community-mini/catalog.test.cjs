const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const auth=require('./customer-auth');
const event=more=>({currentTarget:{dataset:{more}}});
const product=id=>({item_id:id,name:'Product '+id,revision:1,unit_minor:101,currency:'CNY',available:true});
function harness(){
 let definition,generation=1;const calls=[],writes=[];
 vm.runInNewContext(fs.readFileSync(__dirname+'/pages/checkout/index.js','utf8'),{Page:p=>definition=p,require:p=>p==='../../customer-auth'?auth:{},Set});
 const page={...definition,data:structuredClone(definition.data),setData(patch){writes.push(patch);Object.assign(this.data,patch);}};
 page._pageGeneration=1;page._authEpoch=auth.current();page.scene='shop1';page.session={getGeneration:()=>generation,commerce(scene,op,params){return new Promise((resolve,reject)=>calls.push({scene,op,params,resolve,reject}));},clear(){generation++;}};
 return {page,calls,writes,relogin(){generation++;}};
}
test('catalog continues beyond 100, preserves basket selection, refresh resets pagination',async()=>{
 const h=harness(),p=h.page;let request=p.reloadProducts();assert.equal(h.calls[0].op,'products');assert.equal(JSON.stringify(h.calls[0].params),'{}');
 h.calls[0].resolve({products:[product('first')],has_more:true,next_cursor:'[0,"first"]'});await request;
 p.quantity({currentTarget:{dataset:{id:'first'}},detail:{value:'2'}});
 request=p.reloadProducts(event('true'));assert.equal(h.calls[1].params.after_id,'[0,"first"]');
 h.calls[1].resolve({products:[product('first'),product('last')],has_more:false,next_cursor:null});await request;
 assert.equal(p.data.products.length,2);assert.equal(p.data.products[0].quantity,2);assert.equal(p.data.products[1].quantity,0);assert.equal(p.data.productsMore,false);
 request=p.reloadProducts();assert.equal(p.data.products.length,0);assert.equal(p.data.productCursor,null);
 h.calls[2].resolve({products:[product('fresh')],has_more:false,next_cursor:null});await request;assert.equal(p.data.products[0].item_id,'fresh');
});
test('sparse page remains reachable and does not perform automatic requests',async()=>{
 const h=harness();let request=h.page.reloadProducts();h.calls[0].resolve({products:[],has_more:true,next_cursor:'[0,"sparse"]'});await request;
 assert.equal(h.page.data.productsMore,true);assert.match(h.page.data.productsStatus,/后续/);assert.equal(h.calls.length,1);
 request=h.page.reloadProducts(event('true'));h.calls[1].resolve({products:[product('tail')],has_more:false,next_cursor:null});await request;assert.equal(h.page.data.products[0].item_id,'tail');
});
test('double click and purchase during listing do not start another operation',async()=>{
 const h=harness(),request=h.page.reloadProducts();await h.page.reloadProducts();h.page.client={};await h.page.checkout();assert.equal(h.calls.length,1);
 h.calls[0].resolve({products:[],has_more:false,next_cursor:null});await request;assert.equal(h.page.data.productsPending,false);
});
for(const change of ['unload','scene','user','customer','reauth'])for(const result of ['success','error'])test(`catalog ignores late ${result} after ${change}`,async()=>{
 const h=harness(),p=h.page,request=p.reloadProducts();
 if(change==='unload')p.onUnload();if(change==='scene')p.scene='shop2';if(change==='user')p.data.userId='other';if(change==='customer')p.data.projectCustomerId='other';if(change==='reauth')h.relogin();
 result==='success'?h.calls[0].resolve({products:[product('private')],has_more:true,next_cursor:'[0,"private"]'}):h.calls[0].reject(Error('private failure'));
 await request;assert.equal(p.data.products.length,0);assert.equal(p.data.productCursor,null);assert.equal(p.data.productsStatus,'');
});
test('new identity read owns state even when old request settles last',async()=>{
 const h=harness(),old=h.page.reloadProducts();h.relogin();const fresh=h.page.reloadProducts();h.calls[0].reject(Error('old'));await old;assert.equal(h.page.data.productsPending,true);
 h.calls[1].resolve({products:[product('fresh')],has_more:false,next_cursor:null});await fresh;assert.equal(h.page.data.products[0].item_id,'fresh');assert.equal(h.page.data.productsPending,false);
});
test('invalid or looping cursor never replaces successful prior page and read-only retry is explicit',async()=>{
 const h=harness();let request=h.page.reloadProducts();h.calls[0].resolve({products:[product('first')],has_more:true,next_cursor:'[0,"first"]'});await request;
 request=h.page.reloadProducts(event('true'));h.calls[1].resolve({products:[product('bad')],has_more:true,next_cursor:'[0,"first"]'});await request;
 assert.equal(h.page.data.products.length,1);assert.equal(h.page.data.products[0].item_id,'first');assert.match(h.page.data.productsStatus,/分页结果无效/);
 request=h.page.reloadProducts(event('true'));h.calls[2].resolve({products:[product('last')],has_more:false,next_cursor:null});await request;assert.equal(h.page.data.products.length,2);
});
test('legacy first-page response remains usable without invented continuation',async()=>{
 const h=harness(),request=h.page.reloadProducts();h.calls[0].resolve({products:[product('legacy')]});await request;assert.equal(h.page.data.productsMore,false);assert.equal(h.page.data.productCursor,null);
 const markup=fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8');assert.match(markup,/bindtap="reloadProducts" data-more="true"/);assert.match(markup,/productsPending/);
});
