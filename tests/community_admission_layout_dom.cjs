'use strict';const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
class E{
 constructor(tag='div',id=''){this.tagName=tag;this.id=id;this.children=[];this.textContent='';this.hidden=false;this.open=false;this.events={};this.classList={add:x=>this.className=x}}
 append(...items){for(const n of items){if(n.parent)n.parent.children=n.parent.children.filter(x=>x!==n);n.parent=this;this.children.push(n)}}
 prepend(n){this.append(n);this.children=[n,...this.children.filter(x=>x!==n)]}
 replaceChildren(...items){this.children=[];this.append(...items)}
 contains(n){return this===n||this.children.some(c=>c.contains(n))}
 querySelector(sel){return this.children.find(n=>n.tagName===sel)||null}
 closest(sel){return this.tagName===sel?this:this.parent?.closest(sel)||null}
 addEventListener(kind,fn){this.events[kind]=fn}
 set innerHTML(x){throw Error('NO_HTML')}
}
const routePrefix=process.argv[3]||'';assert(['','/community-preview'].includes(routePrefix));const routePath=routePrefix+'/merchant/review',homePath=routePrefix+'/community/portal';
const source=fs.readFileSync(process.argv[2],'utf8'),fragment=source.match(/  \/\/ ADMISSION_REVIEW_LAYOUT_BEGIN[\s\S]*?  \/\/ ADMISSION_REVIEW_LAYOUT_END/);assert(fragment);
for(const mode of [false,true]){
 const nodes={},get=id=>nodes[id]??=new E('div',id),body=new E('body'),header=new E('span'),intro=new E('section'),row=new E('div'),state=get('applicationState'),filterLabel=new E('label');filterLabel.append(get('statusFilter'));intro.append(get('title'),new E('p'));row.append(get('applicationTitle'),state);get('queue').append(new E('h2'),get('reloadQueue'),get('applications'));get('detail').append(row,...['applicationVersion','summary','reviewNote','materials','reviewActions','applicationHistory','openingActions'].map(get));
 const originals=['materials','reviewActions','applicationHistory','openingActions','wechatApplication'].map(get),ctx={reviewMode:mode,reviewLayout:null,cursor:null,run:fn=>fn(),catalog:{materials:[]},states:{SUBMITTED:'待审核'},document:{body,querySelector:s=>s==='header > span'?header:intro,createElement:t=>new E(t)},$:get,button:(label,fn)=>Object.assign(new E('button'),{textContent:label,onclick:fn})};vm.runInNewContext(fragment[0],ctx);
 if(!mode){assert.equal(ctx.reviewLayout,null);assert.equal(get('detail').children.length,8);continue}
 assert.equal(header.textContent,'社区服务 · 平台');const r=ctx.reviewLayout;for(const e of originals)assert(r.controls.contains(e),'original control preserved '+e.id);assert(r.card.contains(state));assert.equal(r.top.href,homePath);assert.equal(new URL(r.top.href,'https://fixture.invalid'+routePath).pathname,homePath);assert.equal(intro.children[0],r.top);assert(r.filters.contains(get('statusFilter')));assert(r.filters.contains(get('reloadQueue')));
 ctx.syncReviewLayout({fields:{store_name:'Synthetic'},entity_type:'ENTERPRISE',delegated:false,required_materials:[],status:'SUBMITTED'});assert.equal(get('queue').hidden,true);assert.equal(get('title').textContent,'商家入驻审核 · 详情');assert(get('summary').children.some(n=>n.textContent.includes('未在本摘要核验')));assert.equal(r.filters.hidden,true);assert.equal(r.top.href,'#admission-list');assert.equal(new URL(r.top.href,'https://fixture.invalid'+routePath).pathname,routePath);
 r.controls.open=true;r.controls.events.toggle();assert.equal(get('title').textContent,'商家入驻审核 · 审核操作');assert.equal(r.card.hidden,true);assert.equal(r.back.hidden,true);assert(r.operationContext.contains(state));assert.equal(r.operationContext.hidden,false);assert.equal(r.contextFields.children.length,6);assert(originals.every(n=>r.controls.contains(n)));
 r.operationBack.onclick();assert.equal(get('title').textContent,'商家入驻审核 · 详情');assert.equal(r.card.hidden,false);assert(r.card.contains(state));
 r.controls.open=true;ctx.applyReviewStage();let prevented=false;r.top.events.click({preventDefault(){prevented=true}});assert(prevented);assert.equal(get('queue').hidden,false);assert.equal(get('detail').hidden,true);assert.equal(get('title').textContent,'商家入驻审核');assert.equal(r.top.href,homePath);assert.equal(r.filters.hidden,false);
 ctx.syncReviewLayout(null);assert.equal(r.controls.open,false);assert.equal(r.contextFields.children.length,0);assert.equal(r.operationContext.hidden,true);assert(originals.every(n=>r.controls.contains(n)));
}
console.log('SCOPED_DOM_PASS review-only real list/detail/operation navigation; original nodes preserved; no new permissions; context cleared; applicant unaffected');
