'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.value = ''; this.textContent = ''; this.hidden = false; }
  append(node) { this.children.push(node); }
  replaceChildren(...nodes) { this.children = nodes; this.textContent = ''; }
  remove() {}
  click() { if (this.tagName === 'a') downloads++; else if (!this.disabled && this.onclick) return this.onclick(); }
  set innerHTML(_) { throw Error('Unsafe DOM'); }
}
const ids = ['reviewNotice','reviewProject','reviewReload','reviewItems','reviewDetail','reviewSelected','reviewInstructions','reviewVersions','reviewForm','reviewReason','reviewBegin','reviewChanges','reviewApprove'];
const nodes = Object.fromEntries(ids.map(id => [id, new Element(id.match(/Reload|Begin|Changes|Approve$/) ? 'button' : 'div')]));
const walk = node => [node,...node.children.flatMap(walk)];
const document = {getElementById: id => nodes[id],createElement: tag => new Element(tag),body: new Element('body'),querySelectorAll: () => Object.values(nodes).flatMap(walk).filter(node => node.tagName === 'button')};
let downloads = 0, revision = 2, state = 'SUBMITTED', requests = [], hold = null, failNext = false;
const item = () => ({id:'document1', title:'<img src=x onerror=alert(1)>',state,revision,required:true,versions:[{seq:1,kind:'SAVE',details:{object_id:'o_test'}}]});
const checklist = workspace => ({project:workspace,overall:state,requirements_revision:1,items:[item()]});
const response = result => ({ok:true,status:200,json:async()=>({result})});
const context = {document,window:{},AbortController,Blob,Uint8Array,atob,setTimeout:fn=>fn(),URL:{createObjectURL:()=> 'blob:test',revokeObjectURL:()=>{}},fetch:async(url,options)=>{
  const body = JSON.parse(options.body); requests.push({url,options,body});
  if (failNext) { failNext=false; return {ok:false,status:409}; }
  if (hold) return new Promise(resolve=>{hold.resolve=resolve;});
  if (body.operation === 'checklist') return response(checklist(body.workspace));
  if (body.operation === 'download') return response({content_base64:'JVBERi0=',mime:'application/pdf',filename:'untrusted/filename'});
  assert.equal(body.params.revision, revision); revision++;
  state = {begin_review:'IN_REVIEW',request_changes:'NEEDS_CORRECTION',approve:'ACCEPTED'}[body.params.action];
  return response({state,revision});
}};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),context);
const configure=context.window.configureCommunityProjectReview;
const flush=async()=>{for(let i=0;i<50;i++) await Promise.resolve();};
const open=()=>nodes.reviewItems.children[0].children[0].click();
(async()=>{
  assert.equal(nodes.reviewReload.disabled,true);
  configure({csrf:'csrf-original',workspace:'project1'});await flush();open();
  assert(nodes.reviewSelected.textContent.includes('<img'));
  assert.equal(nodes.reviewBegin.hidden,false); assert.equal(nodes.reviewApprove.hidden,true);
  await nodes.reviewVersions.children[0].children[0].click();await flush();assert.equal(downloads,1);
  nodes.reviewBegin.click();await flush(); assert.equal(state,'IN_REVIEW');assert.equal(revision,3);
  const count=requests.length;nodes.reviewApprove.click();await flush();assert.equal(requests.length,count);assert(nodes.reviewNotice.textContent.includes('填写'));
  nodes.reviewReason.value='Reviewed synthetic file';nodes.reviewApprove.click();await flush();assert.equal(state,'ACCEPTED');assert.equal(nodes.reviewApprove.hidden,true);
  assert.equal(requests.filter(r=>r.body.operation==='project_review').length,2);
  for(const r of requests){assert.equal(r.options.credentials,'same-origin');assert.equal(r.options.headers['X-CSRF-Token'],'csrf-original');assert.equal(r.body.workspace,'project1');}
  // Current revision is forwarded unchanged; correction also reloads the list.
  state='IN_REVIEW';configure({csrf:'csrf-original',workspace:'project1'});await flush();open();nodes.reviewReason.value='Replace unreadable scan';nodes.reviewChanges.click();await flush();assert.equal(state,'NEEDS_CORRECTION');
  state='SUBMITTED';configure({csrf:'csrf-original',workspace:'project1'});await flush();open();failNext=true;nodes.reviewBegin.click();await flush();assert(nodes.reviewNotice.textContent.includes('409'));assert.equal(nodes.reviewDetail.hidden,true);assert.equal(nodes.reviewItems.children.length,0);
  nodes.reviewReload.click();await flush();assert.equal(nodes.reviewItems.children.length,1);
  // In-flight old project responses may neither render nor download after switch.
  hold={};configure({csrf:'old',workspace:'project1'});await flush();const old=hold;hold=null;
  configure({csrf:'new',workspace:'project2'});await flush();old.resolve(response(checklist('project1')));await flush();assert(nodes.reviewProject.textContent.includes('project2'));
  open();hold={};nodes.reviewVersions.children[0].children[0].click();await flush();const staleDownload=hold;hold=null;configure(null);
  staleDownload.resolve(response({content_base64:'JVBERi0=',mime:'application/pdf'}));await flush();assert.equal(downloads,1);assert.equal(nodes.reviewItems.children.length,0);assert.equal(nodes.reviewReason.value,'');assert.equal(nodes.reviewReload.disabled,true);
  assert(!fs.readFileSync(process.argv[2],'utf8').match(/localStorage|sessionStorage|innerHTML/));
  console.log('project review DOM: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
