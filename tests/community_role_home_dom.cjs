'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
class E{
 constructor(tag='div'){this.tagName=tag;this.children=[];this.textContent='';this.listeners={};this.value='';this.hidden=false;this.style={};}
 append(...v){this.children.push(...v);}
 insertBefore(n,ref){const i=this.children.indexOf(ref);this.children.splice(i<0?0:i,0,n);}
 replaceChildren(...v){this.children=v;this.textContent='';}
 setAttribute(name,value){this[name]=value;}
 addEventListener(n,f){this.listeners[n]=f;}
 click(){if(this.onclick)return this.onclick();if(this.listeners.click)return this.listeners.click({preventDefault(){}});}
}
const nodes={},calls=[],get=id=>nodes[id]??=Object.assign(new E(),{onclick(){calls.push(id);},onchange(){calls.push(id+':change');}});
const platformPanel={},buttons=Array.from({length:11},()=>new E('button'));
const ctx={window:{},document:{createElement:t=>new E(t),getElementById:get},home:new E(),cards:new E(),intro:new E(),heading:new E(),pageTitle:new E(),activeIndex:null,platformBrandText:new E(),platformBrandOriginal:'社区分账管理后台',platformBrandSubtitle:new E(),platformBrandSubtitleOriginal:'社区工作台',panels:[platformPanel],platformPanel,orderQuery:{},buttons,homeButton:new E('button'),adNav:new E('a'),adNewNav:new E('a'),userListNav:new E('a'),mallLinks:Array.from({length:4},()=>new E('a')),splitSettingsNav:new E('a'),pointsTierNav:new E('a'),merchantReviewNav:new E('button'),authorityIndex:10,syncOrderPageTitle(){},syncOperationsTitle(){},refreshNavigationGroups(){},setWorkspaceRoute(){},navigationHashTargets:new Map(),applyWorkspaceRoute(){},queueMicrotask:fn=>fn(),select(i){ctx.activeIndex=i;calls.push(['select',i]);if(i===null)vm.runInContext('syncHomeTitle()',ctx);},openMerchantReview(){calls.push('openMerchantReview');},memberIndex:8,reportIndex:4,customerIndex:0,profileIndex:1,openIndex:2,promotionIndex:7,reviewIndex:3,merchantIndex:6,receiverIndex:9,snapshotNav:Object.assign(new E(),{onclick(){calls.push('snapshotNav');}}),refundNav:Object.assign(new E(),{onclick(){calls.push('refundNav');}}),readRefundObservations:Object.assign(new E(),{onclick(){calls.push('readRefunds');}})};
ctx.openMerchantWorkbench=(target,title)=>calls.push(['openMerchantWorkbench',target,title]);
ctx.window.communityReadRefunds=()=>calls.push('readRefunds');
vm.createContext(ctx);
const source=fs.readFileSync(process.argv[2],'utf8'),fragment=source.match(/ \/\/ ROLE_HOME_BEGIN[\s\S]*? \/\/ ROLE_HOME_END/)[0];
vm.runInContext(fragment,ctx);
const titles=()=>ctx.cards.children.map(g=>g.children[1].children.map(c=>c.children[0].textContent));
const find=t=>ctx.cards.children.flatMap(g=>g.children[1].children).find(c=>c.children[0].textContent===t);
const visible=()=>buttons.map((b,i)=>b.hidden?null:i).filter(i=>i!==null);

assert.equal(ctx.cards.children.length,0);assert.deepEqual(visible(),[]);assert.equal(ctx.heading.textContent,'总览');
ctx.window.communityHomeContext({csrf:'x',workspace:'same',role:'COMMUNITY_ADMIN'});
assert.deepEqual(titles().map(g=>g.length),[4,4,3]);assert.deepEqual(visible(),[0,4,8]);assert.equal(ctx.snapshotNav.hidden,false);assert.equal(ctx.refundNav.hidden,false);assert.equal(ctx.heading.textContent,'总览');
assert.equal(ctx.merchantReviewNav.hidden,true);
assert(ctx.mallLinks.every(link=>link.hidden===false));
const old=find('社区订单');old.click();assert.deepEqual(calls.slice(-2),[['select',4],'communityOrders']);find('分账明细').click();assert.deepEqual(calls.slice(-2),['snapshotNav','communityEarnings']);find('退款记录').click();assert.deepEqual(calls.slice(-2),['refundNav','readRefunds']);find('社区商家').click();assert.deepEqual(calls.slice(-2),[['select',8],'queryMerchantMembers']);

ctx.window.communityHomeContext({csrf:'x',workspace:'platform',role:'PLATFORM_REVIEWER',reviewer:true});
assert.deepEqual(titles().map(g=>g.length),[4,1]);assert.deepEqual(visible(),[3]);assert.equal(ctx.snapshotNav.hidden,true);assert.equal(ctx.refundNav.hidden,true);assert.equal(ctx.heading.textContent,'总览');assert.equal(ctx.platformBrandText.textContent,'社区分账管理后台');assert.equal(ctx.platformBrandSubtitle.textContent,'平台管理者后台');assert.equal(ctx.merchantReviewNav.hidden,false);
assert(ctx.mallLinks.every(link=>link.hidden===true));
let count=calls.length;old.click();assert.equal(calls.length,count,'retained prior identity card cannot execute');find('商家入驻审核').click();assert.equal(calls.at(-1),'openMerchantReview');

ctx.window.communityHomeContext({csrf:'x',workspace:'platform',role:'PLATFORM_OWNER'});
assert(ctx.mallLinks.every(link=>link.hidden===false));
assert.deepEqual(titles().map(g=>g.length),[4,5,1,3,2]);assert.deepEqual(visible(),[6]);assert.equal(ctx.merchantReviewNav.hidden,true);find('订单管理').click();assert.equal(get('platformView').value,'platform_orders');assert.equal(calls.at(-1),'readPlatformView');find('用户管理').click();assert.equal(get('platformView').value,'platform_customers');find('退款管理').click();assert.deepEqual(calls.at(-1),['openMerchantWorkbench','orderDetails','退款管理']);assert(find('退款管理').children[1].textContent.includes('查看当前商家分账记录'));

ctx.window.communityHomeContext({csrf:'x',admin:{kind:'ROOT',capabilities:['/community/admin#list']}});
assert.deepEqual(titles().map(g=>g.length),[8,2]);assert.deepEqual(visible(),[0,4,6,8,10]);assert.equal(ctx.snapshotNav.hidden,false);assert.equal(ctx.refundNav.hidden,false);assert.equal(ctx.adNav.hidden,false);assert.equal(ctx.splitSettingsNav.hidden,false);assert.equal(ctx.merchantReviewNav.hidden,true);assert.equal(find('设置管理员'),undefined);assert.deepEqual(titles()[0],['待审核商家数','今日交易金额','今日交易笔数','今日分账金额','今日分账笔数','今日退款金额','今日退款笔数','今日广告数据']);find('今日广告数据').click();assert.deepEqual(calls.at(-1),['openMerchantWorkbench','advertising','广告管理']);assert.equal(ctx.cards.children[1].children[0].textContent,'近 7 日趋势分析');assert.equal(find('今日广告数据').children[3].textContent,'◉');
const dailySeries=Array.from({length:7},(_,i)=>({day_start:i*86400,transaction_amount_minor:i*100,completed_split_minor:i*20,confirmed_refund_minor:i*10,ad_impression_count:i*5,ad_click_count:i}));ctx.window.communityHomeMetrics({kind:'daily',pending_merchant_count:3,transaction_amount_minor:1234,transaction_count:2,completed_split_minor:100,completed_split_count:2,confirmed_refund_minor:50,confirmed_refund_count:1,ad_impression_count:20,ad_click_count:2,active_ad_count:4,daily_series:dailySeries,currency:'CNY',finance_status:'UNCONFIRMED'});assert.equal(ctx.cards.children[0].children[1].children[0].children[1].textContent,'3');assert.equal(ctx.cards.children[0].children[1].children[1].children[1].textContent,'¥12.34 CNY');assert.equal(find('今日退款笔数').children[1].textContent,'1');assert.equal(find('今日广告数据').children[1].textContent,'20 次浏览');assert.equal(find('今日广告数据').children[2].textContent,'2 次点击 · 点击率 10.00% · 投放中 4 条');assert.equal(ctx.cards.children[1].children[1].children[0].children[1].children.length,7);assert.equal(ctx.cards.children[1].children[1].children[1].children[1].children.length,7);
ctx.window.communityHomeContext({csrf:'x',workspace:'same',role:'COMMUNITY_ADMIN',admin:{kind:'DELEGATE',capabilities:['/community/directory#mine']}});
assert.deepEqual(visible(),[0,10]);assert.equal(ctx.snapshotNav.hidden,true);assert.equal(ctx.refundNav.hidden,true);

ctx.window.communityHomeContext(null);assert.equal(ctx.cards.children.length,0);assert.deepEqual(visible(),[]);assert.equal(ctx.heading.textContent,'总览');
for(const value of [{role:'PLATFORM_OWNER'},{csrf:'x',role:'PLATFORM_OWNER'},{csrf:'x',workspace:'p',role:'OWNER'},{csrf:'x',workspace:'p',role:null}]){ctx.window.communityHomeContext(value);assert.equal(ctx.cards.children.length,0);assert.deepEqual(visible(),[]);}
assert(source.includes('navigationGroupFor(title).items.append(button);buttons.push(button);'),'grouped module navigation retained');assert(!fragment.includes('fetch('));
const hero=ctx.home.children[0];ctx.window.communityHomeContext({csrf:'x',workspace:'p',role:'PLATFORM_OWNER'});assert.equal(hero.children[0].textContent,'平台首页');assert.equal(hero.children[1].textContent,'');assert.equal(hero.children[1].hidden,true);assert.equal(hero.children[3].children.length,1);hero.children[3].children[0].click();assert.equal(get('platformView').value,'platform_orders');
ctx.window.communityHomeContext({csrf:'x',workspace:'c',role:'COMMUNITY_ADMIN'});assert.equal(hero.children[0].textContent,'社区首页');assert.equal(hero.children[1].hidden,true);assert.equal(ctx.cards.children[1].children[0].children[0].textContent,'4 项');assert.equal(find('社区订单').children[2].textContent,'查看社区订单');

for(const value of [null,{role:'PLATFORM_OWNER'},{csrf:'x',workspace:'p',role:'UNKNOWN'}]){ctx.window.communityHomeContext(value);assert.equal(ctx.pageTitle.hidden,false);assert.equal(hero.children[1].hidden,true);assert.equal(ctx.pageTitle.textContent,'总览');}
for(const role of ['COMMUNITY_ADMIN','PLATFORM_REVIEWER','PLATFORM_OWNER']){ctx.window.communityHomeContext({csrf:'x',workspace:'p',role,...(role==='PLATFORM_REVIEWER'?{reviewer:true}:{})});assert.equal(ctx.pageTitle.hidden,false);assert.equal(hero.children[1].hidden,true);ctx.select(1);ctx.select(null);assert.equal(ctx.pageTitle.hidden,false);}
ctx.window.communityHomeContext(null);assert.equal(ctx.pageTitle.hidden,false);assert.equal(hero.children[1].hidden,true);
console.log('PASS role-scoped home and sidebar: community, reviewer, owner, ROOT-only, delegate capability filter, stale identity clear');
