'use strict';
// Deterministic UI scheduling only. Real cookie/Center HTTP coverage lives in
// test_community_web_session_browser.py; this harness never claims identity acceptance.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[2],'utf8');
const flush=async()=>{for(let i=0;i<120;i++)await Promise.resolve();};
function harness(initial='',community=false){
 class Element{
  constructor(){this.value='';this.textContent='';this.disabled=false;this.children=[];this.events={};}
  setAttribute(name,value){this[name]=value;}
  addEventListener(name,fn){this.events[name]=fn;}
  replaceChildren(){this.children=[];this.value='';}
  append(child){this.children.push(child);if(this.children.length===1)this.value=child.value;}
 }
 const form=new Element(),email=new Element(),password=new Element(),login=new Element(),logout=new Element(),select=new Element(),message=new Element();
 form.querySelector=selector=>selector==='[name=password]'?password:null;
 form.reset=()=>{email.value='';password.value='';};
 const extra=[];
 const root={append:el=>extra.push(el),querySelector:selector=>({'form':form,'[role=status]':message,'select':select,'[data-logout]':logout}[selector]),querySelectorAll:()=>[login,logout]};
 const data=new Map(initial?[['community-original-csrf',initial]]:[]),requests=[],configured=[],homeContexts=[],messages=[];let channel;
 const locks={tail:Promise.resolve(),request(name,fn){assert.equal(name,'community-original-session');const p=this.tail.then(fn);this.tail=p.catch(()=>{});return p;}};
 const context={document:{getElementById:()=>root,createElement:()=>new Element()},location:{pathname:community?'/community-preview/community/portal':'/community-preview/merchant/workbench'},
  sessionStorage:{getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)},
  window:{communityHomeContext:value=>homeContexts.push(value?{...value}:null),configureCommunityWorkbench:value=>{configured.push(value?{...value}:null);form.reset();}},navigator:{locks},
  BroadcastChannel:class{constructor(name){assert.equal(name,'community-original-session');channel=this;}postMessage(value){messages.push(value);}},
  FormData:class{constructor(){this.data={email:email.value,password:password.value};}get(k){return this.data[k];}},
  fetch:(url,options)=>new Promise((resolve,reject)=>{requests.push({action:url.split('/').at(-1),options,
   reply:(result,status=200)=>resolve({ok:status===200,status,json:async()=>({result})}),reject});})};
 vm.runInNewContext(source,context);
 const submit=address=>{email.value=address;password.value='SyntheticPassword!';form.events.submit({preventDefault(){}});};
 const completeLogin=async(csrf,workspace)=>{const request=requests.filter(r=>r.action==='login').at(-1);request.reply({csrf,user_id:workspace});await flush();requests.filter(r=>r.action==='check').at(-1).reply({workspaces:[{kind:'MERCHANT',workspace}],reviewer:false});await flush();};
 return{requests,configured,homeContexts,messages,extra,form,email,password,login,logout,select,message,data,submit,completeLogin,
 notify:()=>channel.onmessage({data:'changed'}),csrf:()=>data.get('community-original-csrf')};
}
(async()=>{
 for(const result of ['failure','success']){
  const h=harness('old-csrf');await flush();const stale=h.requests[0];h.submit('new@example.org');await flush();
  await h.completeLogin('new-csrf','new-workspace');
  if(result==='failure')stale.reject(Error('old network failure'));
  else stale.reply({workspaces:[{kind:'MERCHANT',workspace:'old-workspace'}],reviewer:false});
  await flush();assert.equal(h.csrf(),'new-csrf','old startup '+result+' erased the newer CSRF');
  assert.equal(h.configured.at(-1).workspace,'new-workspace');assert(h.message.textContent.startsWith('已登录'));
 }
 {
  const h=harness();h.submit('one@example.org');await flush();assert.equal(h.login.disabled,true);
  h.submit('two@example.org');await flush();assert.equal(h.requests.filter(r=>r.action==='login').length,1,'duplicate login crossed single-flight guard');
  assert.equal(h.select.disabled,true);await h.completeLogin('csrf-one','merchant1');assert.equal(h.login.disabled,false);
  h.select.value='merchant1';h.select.events.change();assert.equal(h.configured.at(-1).workspace,'merchant1');
  h.select.value='client-invented';h.select.events.change();assert.equal(h.configured.at(-1).workspace,undefined);
 }
 {
  const h=harness();h.submit('one@example.org');await flush();await h.completeLogin('csrf-one','merchant1');
  h.logout.events.click();await flush();const pending=h.requests.at(-1);assert.equal(pending.action,'logout');
  assert.equal(pending.options.headers['X-CSRF-Token'],'csrf-one');assert.equal(h.login.disabled,true);
  h.submit('two@example.org');h.select.value='merchant1';h.select.events.change();await flush();
  assert.equal(h.requests.filter(r=>r.action==='login').length,1);assert.equal(h.configured.at(-1),null);
  pending.reply({logged_out:true});await flush();assert.equal(h.csrf(),undefined);assert.equal(h.message.textContent,'已退出登录。');
  h.submit('two@example.org');await flush();await h.completeLogin('csrf-two','merchant2');
  assert.equal(h.csrf(),'csrf-two');assert.equal(h.configured.at(-1).workspace,'merchant2');
 }
 {
  const h=harness();h.submit('one@example.org');await flush();const pending=h.requests[0];
  h.notify();h.password.value='NewlyTypedPassword!';pending.reject(Error('old failure'));await flush();
  assert.equal(h.password.value,'NewlyTypedPassword!','stale finally cleared newer input');
  assert.equal(h.csrf(),undefined);assert.equal(h.configured.at(-1),null);assert.equal(h.login.disabled,false);
  assert.equal(h.message.textContent,'其他窗口已变更原会话，请重新登录。');
 }
 {
  const h=harness();h.submit('one@example.org');await flush();h.requests[0].reject(Error('UNKNOWN'));
  await flush();assert.equal(h.requests.length,1,'UNKNOWN automatically replayed');assert.equal(h.csrf(),undefined);
  assert.equal(h.select.children.length,0);assert.equal(h.configured.at(-1),null);
  assert.equal(h.login.disabled,false);assert(h.message.textContent.includes('未自动重试'));
  assert.deepEqual(h.messages,['changed']);
 }
 {
  const h=harness('old-csrf',true);await flush();
  h.requests[0].reply({workspaces:[{kind:'COMMUNITY',workspace:'platform',role:'PLATFORM_OWNER'},{kind:'COMMUNITY',workspace:'community',role:'COMMUNITY_ADMIN'},{kind:'COMMUNITY',workspace:'legacy'},{kind:'COMMUNITY',workspace:'invalid',role:'OWNER'}],reviewer:true});await flush();
  assert.equal(h.configured.at(-1).role,'PLATFORM_OWNER');assert.deepEqual(h.homeContexts,h.configured);
  for(const [workspace,role]of [['community','COMMUNITY_ADMIN'],['legacy',null],['invalid',null],['invented',null]]){h.select.value=workspace;h.select.events.change();assert.equal(h.configured.at(-1).role,role);}
  h.select.value='platform';h.select.events.change();assert.equal(h.configured.at(-1).role,'PLATFORM_OWNER');
  h.notify();assert.equal(h.configured.at(-1),null);assert.deepEqual(h.homeContexts,h.configured);
 }
 {
  const h=harness('old-csrf',true);await flush();const stale=h.requests[0];h.notify();
  stale.reply({workspaces:[{kind:'COMMUNITY',workspace:'platform',role:'PLATFORM_OWNER'}],reviewer:true});await flush();assert.equal(h.configured.at(-1),null);
 }
 {
  const h=harness('old-csrf',true);await flush();h.requests[0].reply({workspaces:[{kind:'COMMUNITY',workspace:'platform',role:'PLATFORM_REVIEWER'}],reviewer:false});await flush();
  h.logout.events.click();await flush();assert.equal(h.configured.at(-1),null);h.requests.at(-1).reply({logged_out:true});await flush();assert.equal(h.configured.at(-1),null);
 }
 {
  const h=harness('original');await flush();h.requests[0].reply({workspaces:[{kind:'MERCHANT',workspace:'store',finance_options:{provider:[{workspace:'finance1'},{workspace:'finance2'}],merchant_bill:[{workspace:'bills'}]}},{kind:'MERCHANT',workspace:'legacy'}],reviewer:false});await flush();
  const provider=h.extra[0].children[0],bill=h.extra[1].children[0];
  assert.equal(h.configured.at(-1).providerWorkspace,undefined);assert.equal(h.configured.at(-1).merchantBillWorkspace,undefined);
  provider.value='finance2';provider.events.change();assert.equal(h.configured.at(-1).providerWorkspace,'finance2');assert.equal(h.configured.at(-1).merchantBillWorkspace,undefined);
  bill.value='bills';bill.events.change();assert.equal(h.configured.at(-1).merchantBillWorkspace,'bills');
  provider.value='invented';provider.events.change();assert.equal(h.configured.at(-1).providerWorkspace,undefined);
  h.select.value='legacy';h.select.events.change();assert.equal(provider.value,'');assert.equal(bill.value,'');assert.equal(h.configured.at(-1).merchantBillWorkspace,undefined);
  h.select.value='store';h.select.events.change();assert.equal(h.configured.at(-1).providerWorkspace,undefined);
  provider.value='finance1';provider.events.change();h.notify();assert.equal(h.configured.at(-1),null);assert.equal(provider.value,'');assert.equal(bill.value,'');
 }
 console.log('original web session race regression: race/state schedules PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
