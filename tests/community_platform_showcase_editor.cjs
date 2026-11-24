'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[2],'utf8');
const block=source.split('// BEGIN_PLATFORM_SHOWCASE_EDITOR')[1].split('// END_PLATFORM_SHOWCASE_EDITOR')[0];
class Node{constructor(tag){this.tag=tag;this.children=[];this.style={};this.value='';this.checked=false;}setAttribute(k,v){this[k]=v;}append(...n){this.children.push(...n);}prepend(...n){this.children.unshift(...n);}replaceChildren(...n){this.children=[...n];}reset(){for(const n of this.children)if(n.tag==='input')n.value='';}}
function harness(initial=null){let stored=initial,writes=0;const calls=[],container=new Node('div');let intercept=null;
 const sandbox={document:{createElement:tag=>new Node(tag)}};vm.createContext(sandbox);vm.runInContext(block+';globalThis.factory=createPlatformShowcaseEditor;',sandbox);
 const request=async(workspace,operation,params)=>{calls.push({workspace,operation,params:JSON.parse(JSON.stringify(params))});if(intercept)return intercept(workspace,operation,params);
  assert.equal(workspace,'platform_showcase');if(operation==='community.merchant_settings')return{label:'爱心商城',record:stored};
  assert.equal(operation,'community.item');writes++;assert.equal(params.expected_version,stored?stored.version:0);stored={...params,version:params.expected_version+1};delete stored.expected_version;return{version:stored.version,published:stored.published};};
 const editor=sandbox.factory(container,request);return{editor,calls,container,get stored(){return stored;},get writes(){return writes;},set intercept(v){intercept=v;}};
}
const draft=()=>({id:'POMELO-WHITE-M2',name:'白肉蜜柚',description:'10元两只/份',image_data:'data:image/jpeg;base64,/9j/AA==',gallery:['data:image/jpeg;base64,/9j/AA==','data:image/jpeg;base64,/9j/AB==','data:image/jpeg;base64,/9j/AC==','data:image/jpeg;base64,/9j/AD=='],quantity:100,unit_minor:1000,published:true});
const configure=h=>h.editor.configure({workspace:'platform_showcase',display_only:true});
(async()=>{
 let count=0;
 {const h=harness();await assert.rejects(h.editor.read());assert.equal(h.calls.length,0);assert.equal(h.container.children[0].hidden,true);count++;}
 {const h=harness();configure(h);const summary=h.editor.loadDraft(draft());assert.equal(summary.gallery_count,4);assert.equal(h.calls.length,0);const result=await h.editor.publishDraft();assert.equal(result.record.quantity,100);assert.equal(result.record.unit_minor,1000);assert.equal(result.record.gallery.length,4);assert.equal(h.writes,1);assert.deepEqual(h.calls.map(c=>c.operation),['community.merchant_settings','community.item','community.merchant_settings']);assert(!h.calls.some(c=>c.workspace==='owner_merchant'||c.operation==='price_set'||c.params.item));await h.editor.publishDraft();assert.equal(h.writes,1);count++;}
 {const h=harness();configure(h);await h.editor.publishDraft({...draft(),published:false});assert.equal(h.stored.published,true,'explicit publish must not preserve unpublished draft flag');count++;}
 {const h=harness({...draft(),quantity:99,version:7});configure(h);await h.editor.publishDraft(draft());assert.equal(h.calls.find(c=>c.operation==='community.item').params.expected_version,7);assert.equal(h.stored.version,8);count++;}
 {const h=harness();configure(h);h.editor.loadDraft(draft());let writes=0;h.intercept=async(w,op)=>{if(op==='community.item'){writes++;throw Error('UNKNOWN');}return{record:null};};await assert.rejects(h.editor.publishDraft(),/UNKNOWN/);assert.equal(writes,1);assert.equal(h.calls.length,2);count++;}
 {const h=harness();configure(h);assert.throws(()=>h.editor.loadDraft({...draft(),gallery:draft().gallery.slice(0,3)}));assert.equal(h.calls.length,0);count++;}
 {const h=harness({...draft(),id:'OTHER',version:4});configure(h);await assert.rejects(h.editor.publishDraft(draft()));assert.equal(h.writes,0);count++;}
 {const h=harness();configure(h);let resolve;h.intercept=()=>new Promise(r=>{resolve=r;});const pending=h.editor.publishDraft(draft());await assert.rejects(h.editor.publishDraft(draft()));h.editor.configure(null);resolve({record:null});await assert.rejects(pending);assert.equal(h.calls.length,1);count++;}
 assert(source.includes('window.communityPlatformShowcase=Object.freeze({read:'));
 assert(!source.slice(source.indexOf('window.communityPlatformShowcase=')).split(';')[0].includes('csrf'));
 console.log('platform showcase editor: '+count+' directed cases PASS (synthetic UI, no credential extraction)');
})().catch(e=>{console.error(e);process.exitCode=1;});
