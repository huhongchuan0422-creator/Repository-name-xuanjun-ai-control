'use strict';
// Execute the current source fragment, not a duplicated rendering implementation.
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),crypto=require('crypto');
const source=fs.readFileSync(process.argv[2],'utf8');
const marker='// ORIGINAL_UI_RESTORATION_BEGIN';assert.equal(source.split(marker).length,2);
const fragment=source.split(marker)[1].split('// ORIGINAL_UI_RESTORATION_END')[0].split('\n').slice(1).join('\n');
let observer=null,pending=false,mutations=0;
function mutate(){if(observer){pending=true;mutations++;}}
class Node{
 constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.parentNode=null;this._hidden=false;this._open=false;this._text='';this.listeners={};this.disabled=false;this.classes=new Set();this.classList={add:(...a)=>a.forEach(v=>this.classes.add(v)),toggle:(v,on)=>{if(on)this.classes.add(v);else this.classes.delete(v);}};}
 set hidden(v){v=!!v;if(this._hidden!==v){this._hidden=v;mutate();}}get hidden(){return this._hidden;}
 set open(v){v=!!v;if(this._open!==v){this._open=v;mutate();}}get open(){return this._open;}
 set textContent(v){v=String(v);if(this._text!==v){this._text=v;mutate();}}get textContent(){return this._text;}
 append(...nodes){for(const n of nodes){if(n.parentNode)n.parentNode.children.splice(n.parentNode.children.indexOf(n),1);this.children.push(n);n.parentNode=this;}mutate();}
 closest(q){let p=this;while(p){if(p.tagName===q.toUpperCase())return p;p=p.parentNode;}return null;}
 insertBefore(n,b){assert(this.children.includes(b),'insert target belongs to original parent');if(n.parentNode)n.parentNode.children.splice(n.parentNode.children.indexOf(n),1);this.children.splice(this.children.indexOf(b),0,n);n.parentNode=this;mutate();}
 addEventListener(k,fn){(this.listeners[k]??=[]).push(fn);}
 click(){if(this.disabled)return;if(this.onclick)this.onclick();for(const f of this.listeners.click||[])f();}
 querySelector(q){const all=this.children.flatMap(n=>[n,...n.all()]);return q==='h2'?all.find(n=>n.tagName==='H2'):q==='.snapshot-detail-action'?all.find(n=>n.className==='snapshot-detail-action'):null;}
 all(){return this.children.flatMap(n=>[n,...n.all()]);}
}
const names=['main','nav','pageTitle','back','profilePanel','openPanel','promotionPanel','memberPanel','customerPanel','reportPanel','platformPanel','receiverPanel','actions','openQuery','promotionQuery','memberQuery','reportControls','orderQuery','edit','reread','toList','backOpen','refreshOpen','promotionBack','memberBack','memberRefresh','profileForm','detail','openActions','openDetails','promotionActions','promotionDetail','memberDetail','customerForm','operationQuery','receiverQueryControls','customerBack','reviewBack','merchantBack','receiverActions','receiverQuery','receiverDetail','receiverBack','orderDetail','orderBack','operationBack','snapshotDetail'];
const c=Object.fromEntries(names.map(n=>[n,new Node(n.endsWith('Back')||n==='back'?'button':'div')]));
c.customerPanel.append(c.customerBack,c.customerForm);c.receiverPanel.append(c.receiverQueryControls,c.receiverActions);c.openPanel.append(c.openDetails,c.openActions);c.promotionPanel.append(c.promotionDetail,c.promotionActions);
const indices=['profile','open','promotion','member','customer','review','merchant','receiver','report'];indices.forEach((n,i)=>c[n+'Index']=i);
c.panels=indices.map(n=>c[n+'Panel']||new Node());c.panels.push(c.platformPanel);
c.activeIndex=null;c.customerMode=c.reviewMode=c.merchantMode=c.operationMode='list';c.snapshotMode='list';
const readProfile=new Node('button'),platformView=new Node('select');platformView.value='platform_orders';
const receiverHeading=new Node('h2');receiverHeading.textContent='平台配置社区分账接收关系';c.receiverPanel.append(receiverHeading);
const snapshotBack=new Node('button');snapshotBack.className='snapshot-detail-action';c.snapshotDetail.append(snapshotBack);
let selects=[],calls={};const count=n=>calls[n]=(calls[n]||0)+1;
c.select=i=>{selects.push(i);c.activeIndex=i;c.panels.forEach((p,j)=>p.hidden=j!==i);};
const receiverWorkspace=new Node('input'),receiverId=new Node('input'),listReceiverRelations=new Node('button'),workspaceLabel=new Node('label'),receiverLabel=new Node('label');workspaceLabel.append(receiverWorkspace);receiverLabel.append(receiverId);c.receiverQuery.append(workspaceLabel,listReceiverRelations);c.receiverActions.append(receiverLabel);
 c.document={createElement:t=>new Node(t),getElementById:id=>({readProfile,platformView,receiverWorkspace,receiverId,listReceiverRelations})[id]};
c.MutationObserver=class{constructor(fn){observer=fn;}observe(node,opts){assert.equal(node,c.main);assert.deepEqual(Array.from(opts.attributeFilter),['hidden','open']);}};
c.fetch=()=>{throw Error('presentation must not request HTTP');};
// Existing handler contracts are supplied as mocks; the source fragment selects them.
c.toList.onclick=()=>{count('profile');c.detail.hidden=true;c.profileForm.hidden=true;};
c.backOpen.onclick=()=>{count('open');c.openDetails.hidden=true;};
c.promotionBack.onclick=()=>{count('promotion');c.promotionDetail.hidden=true;};
c.memberBack.onclick=()=>{count('member');c.memberDetail.hidden=true;};
for(const n of ['customer','review','merchant','operation'])c[n+'Back'].onclick=()=>{count(n);c[n+'Mode']='list';mutate();};
c.receiverBack.onclick=()=>{count('receiver');c.receiverDetail.hidden=true;};
c.orderBack.onclick=()=>{count('order');c.orderDetail.hidden=true;};
snapshotBack.onclick=()=>{count('snapshot');c.snapshotMode='list';mutate();};
function reset(){for(const n of ['profileForm','detail','openDetails','promotionDetail','memberDetail','receiverDetail','orderDetail'])c[n].hidden=true;for(const n of ['openActions','promotionActions','receiverActions'])c[n].open=false;for(const n of ['customer','review','merchant','operation'])c[n+'Mode']='list';c.snapshotMode='list';platformView.value='platform_orders';c.activeIndex=null;}
reset();vm.createContext(c);vm.runInContext(fragment+'\nglobalThis.sync=syncRestoredPresentation;',c);
assert(c.customerPanel.children.indexOf(c.customerForm)<c.customerPanel.children.indexOf(c.customerBack),'original customer form precedes return');assert(c.receiverPanel.children.indexOf(c.receiverActions)<c.receiverPanel.children.indexOf(c.receiverQueryControls),'original receiver actions precede query controls');assert(c.operationQuery.classes.has('operation-query-action'));
function flush(){let loops=0;while(pending){assert(++loops<=15,'mutation observer loop');pending=false;observer();}return loops;}
function active(i){c.select(i);c.sync();flush();}
function returned(i,name){const n=calls[name]||0;const before=selects.length;c.back.click();flush();assert.equal(calls[name],n+1,name+' original handler');assert.equal(c.activeIndex,i,name+' stays same panel');assert.equal(selects.length,before,name+' no workspace select');}
function stable(){const old=mutations;c.sync();flush();assert.equal(mutations,old,'idempotent sync must not emit new observed mutations');}
const results=[];function test(name,f){try{reset();flush();f();stable();results.push({name,pass:true});}catch(e){results.push({name,pass:false,error:e.stack});}}
test('01 profile list/detail/edit topback same list',()=>{active(c.profileIndex);assert.equal(c.back.textContent,'‹ 返回工作台');c.detail.hidden=false;flush();assert.equal(c.pageTitle.textContent,'社区资料 · 详情');assert.equal(c.toList.hidden,false);c.profileForm.hidden=false;flush();assert.equal(c.pageTitle.textContent,'社区资料 · 编辑');returned(c.profileIndex,'profile');assert.equal(c.profileForm.hidden,true);assert.equal(c.pageTitle.textContent,'社区资料');});
test('02 open relationship actions close and original return',()=>{active(c.openIndex);c.openDetails.hidden=false;c.openActions.open=true;flush();assert.equal(c.pageTitle.textContent,'打开社区 · 关系操作');returned(c.openIndex,'open');assert.equal(c.openActions.open,false);assert.equal(c.back.textContent,'‹ 返回工作台');});
test('03 promotion edit cancellation',()=>{active(c.promotionIndex);c.promotionDetail.hidden=false;c.promotionActions.open=true;flush();assert.equal(c.pageTitle.textContent,'社区推广 · 编辑');returned(c.promotionIndex,'promotion');assert.equal(c.promotionActions.open,false);});
test('04 merchant membership detail return',()=>{active(c.memberIndex);c.memberDetail.hidden=false;flush();assert.equal(c.pageTitle.textContent,'社区商家成员 · 详情');returned(c.memberIndex,'member');assert.equal(c.memberBack.hidden,true);});
for(const [number,n]of [['05','customer'],['06','review'],['07','merchant']])test(number+' '+n+' detail/edit uses original handler',()=>{for(const mode of ['detail','edit']){active(c[n+'Index']);c[n+'Mode']=mode;c.sync();flush();assert.equal(c.back.textContent,'‹ 返回原列表');returned(c[n+'Index'],n);}});
test('08 receiver actions close and original list return',()=>{active(c.receiverIndex);c.receiverDetail.hidden=false;c.receiverActions.open=true;flush();assert.equal(c.pageTitle.textContent,'平台配置社区分账接收关系 · 编辑');returned(c.receiverIndex,'receiver');assert.equal(c.receiverActions.open,false);assert.equal(workspaceLabel.parentNode,c.receiverQuery);assert.equal(receiverWorkspace.parentNode,workspaceLabel);});
test('09 platform order detail only current panel',()=>{const i=c.panels.indexOf(c.platformPanel);active(i);c.orderDetail.hidden=false;flush();returned(i,'order');});
test('10 platform nonorder edit return',()=>{const i=c.panels.indexOf(c.platformPanel);platformView.value='platform_customers';active(i);c.operationMode='edit';c.sync();flush();assert(c.platformPanel.classes.has('restored-operation-editing'));returned(i,'operation');assert(!c.platformPanel.classes.has('restored-operation-editing'));});
test('11 snapshot detail preserves current panel',()=>{active(c.reportIndex);c.snapshotMode='detail';c.sync();flush();returned(c.reportIndex,'snapshot');assert.equal(c.snapshotMode,'list');});
test('12 reset/offpanel stale state never picks wrong handler',()=>{active(c.receiverIndex);c.receiverDetail.hidden=false;flush();active(c.profileIndex);assert.equal(c.back.textContent,'‹ 返回工作台');const before=calls.receiver||0;c.back.click();flush();assert.equal(c.activeIndex,null);assert.equal(calls.receiver||0,before);reset();active(c.receiverIndex);assert.equal(c.back.textContent,'‹ 返回工作台');c.back.click();flush();assert.equal(c.activeIndex,null);assert.equal(calls.receiver||0,before);});
console.log(JSON.stringify({source_sha256:crypto.createHash('sha256').update(source).digest('hex'),scope:'ACTUAL_SOURCE_FRAGMENT_MOCK_EXISTING_HANDLERS_NO_BROWSER_OR_HTTP',results},null,2));if(results.some(r=>!r.pass))process.exitCode=1;

for(const [panel,button,query]of [[c.profilePanel,c.toList,'profileQuery'],[c.openPanel,c.backOpen,'openQueryDisclosure'],[c.promotionPanel,c.promotionBack,'promotionQueryDisclosure'],[c.memberPanel,c.memberBack,'memberQueryDisclosure']]){const q=vm.runInContext(query,c);assert(panel.children.indexOf(button)<panel.children.indexOf(q),'primary return before auxiliary query');}
