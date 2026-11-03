'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.textContent='';this.value='';this.hidden=false;this.dataset={};this.nextElementSibling={hidden:false};}
 append(...n){this.children.push(...n);}replaceChildren(...n){this.children=n;this.textContent='';}
 addEventListener(type,fn){this['on'+type]=fn;}click(){if(!this.disabled&&this.onclick)return this.onclick();}closest(){return {hidden:false,firstChild:{},lastChild:{}};}querySelector(tag){this._query??={};return this._query[tag]??=new Element(tag);}focus(){}
 reset(){}set innerHTML(_){throw Error('unsafe DOM');}
}
const html=fs.readFileSync(process.argv[3],'utf8'),nodes=Object.fromEntries([...html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g)].map(m=>[m[2],new Element(m[1])]));
const walk=n=>[n,...n.children.flatMap(walk)],document={body:{classList:{add(){}}},getElementById:id=>{assert(nodes[id],id);return nodes[id];},createElement:tag=>new Element(tag),querySelectorAll:tag=>Object.values(nodes).flatMap(walk).filter(n=>n.tagName===tag)};
const profile={name:'Original profile',description:'Original description',contact:'Contact',status:'ACTIVE',version:1};
const response=result=>({ok:true,json:async()=>({result})});let calls=[],hold=null,fail=false;
const context={window:{},document,location:{search:'?embedded=1',hash:''},URLSearchParams,fetch:async(url,options)=>{
 const body=JSON.parse(options.body);calls.push({url,body,options});if(hold)return new Promise(resolve=>hold.resolve=resolve);
 if(fail){fail=false;return {ok:false,status:403,json:async()=>({})};}
 if(body.operation==='price_list')return response({records:[]});
 assert.equal(body.operation,'community.merchant_settings');
 return response({profile,items:[{id:body.params.after_id?'item_0200':'item_0000',name:'Product',status:'ACTIVE',sort:0}],has_more:!body.params.after_id,next_cursor:body.params.after_id?null:'item_0199'});
}};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),context);
const configure=context.window.configureCommunityWorkbench,settingsCalls=()=>calls.filter(call=>call.body.operation==='community.merchant_settings'),flush=async()=>{for(let i=0;i<60;i++)await Promise.resolve();};
(async()=>{
 configure({csrf:'original-csrf',workspace:'merchant'});nodes.catalogFilter.value='ALL';nodes.priceStatusFilter.value='ALL';assert(nodes.moreItems.hidden);
 nodes.loadSettings.click();await flush();assert.deepEqual(settingsCalls()[0].body.params,{});assert.equal(nodes.items.children.length,2);assert(!nodes.moreItems.hidden);
 nodes.name.value='Unsaved local profile';nodes.moreItems.click();await flush();assert.equal(settingsCalls()[1].body.params.after_id,'item_0199');assert.equal(nodes.items.children.length,3);assert.equal(nodes.name.value,'Unsaved local profile');assert(nodes.moreItems.hidden);
 nodes.items.children[2].children[6].children[1].click();await flush();assert.equal(nodes.itemId.value,'item_0200');assert.equal(settingsCalls().length,2);
 nodes.loadSettings.click();await flush();assert.equal(nodes.items.children.length,2);assert.equal(nodes.name.value,profile.name);
 fail=true;nodes.moreItems.click();await flush();assert.equal(nodes.items.children.length,2);assert(!nodes.moreItems.hidden);assert(nodes.notice.textContent.includes('当前操作不可用'));
 hold={};nodes.moreItems.click();await flush();nodes.moreItems.click();await flush();assert.equal(settingsCalls().length,5);const old=hold;hold=null;
 configure(null);old.resolve(response({profile,items:[{id:'private_item',name:'Private',status:'ACTIVE',sort:0}],has_more:true,next_cursor:'private_item'}));await flush();
 assert.equal(nodes.items.children.length,2);assert(!nodes.items.children.some(node=>String(node.textContent).includes('Private')));assert(nodes.moreItems.hidden);assert(nodes.loadSettings.disabled);
 for(const call of calls){assert.equal(call.body.workspace,'merchant');assert.equal(call.options.headers['X-CSRF-Token'],'original-csrf');assert.equal(call.options.credentials,'same-origin');}
 assert(!fs.readFileSync(process.argv[2],'utf8').match(/innerHTML|localStorage|sessionStorage/));console.log('Workbench original catalog pagination DOM: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
