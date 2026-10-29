'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
class Node{constructor(tag='div'){this.tagName=tag;this.children=[];this.value='';this.textContent='';this.hidden=false;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;this.textContent='';}closest(){return panel;}querySelector(){return panelHeading;}addEventListener(e,f){this['on'+e]=f;}set innerHTML(_){throw Error('UNSAFE_HTML');}classList={add(){}};}
const panelHeading={textContent:'平台运营查询',hidden:false};
const nodes={},panel=new Node('section'),get=id=>nodes[id]??=(new Node()),document={getElementById:get,createElement:t=>new Node(t)};
const pageTitle=new Node('h1');
const storage=new Map(),calls=[],context={panels:[panel],activeIndex:0,pageTitle,window:{},document,location:{hostname:'test',hash:''},localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},fetch:(url,opts)=>new Promise((resolve,reject)=>calls.push({url,body:JSON.parse(opts.body),resolve,reject}))};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),context);
const shell=fs.readFileSync(process.argv[3],'utf8');const begin=shell.indexOf(' // PLATFORM_ORDER_CARDS_BEGIN'),end=shell.indexOf(' // PLATFORM_ORDER_CARDS_END');assert(begin>=0&&end>begin);vm.runInNewContext(shell.slice(begin,end),context);
const flush=async()=>{for(let i=0;i<50;i++)await Promise.resolve();},reply=r=>({ok:true,json:async()=>({result:r})});
const walk=e=>[e,...e.children.flatMap(walk)],text=e=>walk(e).map(n=>n.textContent).join('|');
function select(id,v){get(id).value=v;get(id).onchange();}
async function start(id){const n=calls.length;get(id).onclick();await flush();assert.equal(calls.length,n+1);return calls.at(-1);}
const result=(reference='order1')=>({records:[{reference,scope:{tenant_id:'t',merchant_id:'m',store_id:'s'},amount_minor:101,currency:'USD',order_state:'PENDING',payment_evidence:null,finance_status:'UNCONFIRMED'}],has_more:true,next_cursor:51,coverage_complete:false,unavailable_mapping_count:1});
(async()=>{
 context.window.configureCommunityPortal({csrf:'original',workspace:'platform'});select('platformView','platform_orders');select('platformOrderStatus','ALL');assert.equal(pageTitle.textContent,'支付证据');assert.equal(panelHeading.hidden,true);
 let q=await start('readPlatformView');assert.equal(q.url,'/community/directory');assert.equal(q.body.operation,'platform_orders');q.resolve(reply(result()));await flush();
 const rows=panel.children.find(n=>n.className==='platform-order-rows'),detail=panel.children.find(n=>n.className==='platform-order-detail');
 assert(rows);assert.equal(panel.children.find(n=>n.tagName==='h3').hidden,true);assert(text(rows).includes('101 最小货币单位 · USD'));assert(!text(rows).includes('CNY'));assert.equal(get('platformViewResult').hidden,true);
 const open=rows.children[1].onclick,back=panel.children.find(n=>n.textContent==='返回原列表');const count=calls.length;open();assert.equal(calls.length,count);assert.equal(detail.hidden,false);assert.equal(pageTitle.textContent,'支付证据详情');assert(text(detail).includes('不据此断言未支付'));back.onclick();assert.equal(pageTitle.textContent,'支付证据');assert.equal(get('platformOrderStatus').value,'ALL');assert.equal(get('morePlatformView').hidden,false);
 q=await start('morePlatformView');assert.equal(q.body.params.after_id,51);q.resolve(reply(result('new-order')));await flush();open();assert.equal(detail.hidden,true);assert(text(rows).includes('new-order'));
 q=await start('readPlatformView');select('platformView','platform_audit');assert.equal(pageTitle.textContent,'平台运营查询');assert.equal(panelHeading.hidden,false);q.resolve(reply(result('stale-order')));await flush();assert.equal(rows.children.length,0);
 q=await start('readPlatformView');assert.equal(q.body.operation,'platform_audit');q.resolve(reply({records:[{event:'ORIGINAL_AUDIT'}],has_more:false}));await flush();assert(get('platformViewResult').textContent.includes('ORIGINAL_AUDIT'));assert.equal(get('platformViewResult').hidden,false);
 select('platformView','platform_orders');q=await start('readPlatformView');q.resolve(reply(result('<img src=x>')));await flush();assert(text(rows).includes('<img src=x>'));
 q=await start('readPlatformView');q.resolve({ok:false,json:async()=>({error:'ACCESS_DENIED'})});await flush();assert.equal(rows.children.length,0);assert.equal(detail.children.length,0);assert.equal(get('morePlatformView').hidden,true);
 context.activeIndex=null;pageTitle.textContent='其他页面';select('platformView','platform_orders');q=await start('readPlatformView');q.resolve(reply(result('offscreen')));await flush();assert.equal(pageTitle.textContent,'其他页面');rows.children[1].onclick();assert.equal(pageTitle.textContent,'其他页面');context.activeIndex=0;vm.runInNewContext('syncOrderPageTitle()',context);assert.equal(pageTitle.textContent,'支付证据详情');back.onclick();assert.equal(pageTitle.textContent,'支付证据');
 assert(calls.every(c=>['platform_orders','platform_audit'].includes(c.body.operation)));
 console.log('SCOPED_MOCK_DOM_PASS actual directory script + exact shell fragment; fields/detail/back/status/cursor/stale view/403/no funds');
})().catch(e=>{console.error(e);process.exitCode=1;});
