const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {createSession,getSharedSession,parseScene}=require('./session');
const auth=require('./customer-auth');
const fixture=Buffer.from('%PDF-1.4\nsynthetic fixture only\n').toString('base64');
const version='v_'+'a'.repeat(32);
const boundedFile=size=>{const bytes=Buffer.alloc(size,1);bytes.write('%PDF-1.4');return bytes.toString('base64');};
const params=()=>({item:'material1',revision:1,filename:'fixture.pdf',content_base64:fixture});
const event=(item='material1',revision=1)=>({currentTarget:{dataset:{item,revision}}});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function harness(){
  let definition,choose,read,loginCount=0;
  const requests=[],writes=[],reads=[];
  const wx={login(o){loginCount++;o.success({code:'fixture-code'});},request(o){
    // Independent startup directory read; original test queue retains only the operation under test.
    if(o.data&&o.data.operation==='customer.directory')return o.success({statusCode:200,data:{payment_enabled:false,result:{records:[],categories:[],has_more:false,next_cursor:null,visibility:'CURRENT_AUTHORIZED_PROJECT_TENANT',storefront_photo_supported:false}}});

    if(o.url.endsWith('/mini/login'))o.success({statusCode:200,data:{payment_enabled:false,result:{
      session_token:String(loginCount).repeat(32),expires_at:Math.floor(Date.now()/1000)+1000,
      provider:'WECHAT_MINIPROGRAM',payment_enabled:false}}});else requests.push(o);
  },chooseMessageFile(o){choose=o;},getFileSystemManager(){return {readFile(o){reads.push(o);read=o;}};}};
  vm.runInNewContext(fs.readFileSync(__dirname+'/pages/checkout/index.js','utf8'),{
    Page:p=>{definition=p;},wx,getApp:()=>({globalData:{mode:'CONNECTED',baseUrl:'https://fixture.invalid'}}),
    require:path=>path==='../../customer-auth'?auth:path==='../../session'?{createSession,getSharedSession,parseScene}:path==='../../client'?{
      makeClient:()=>({reset(){},storefront:async()=>({merchant:{name:'fixture'},ads:{}})})
    }:{createPaymentFlow:()=>({reset(){}})}
  });
  const page={...definition,data:structuredClone(definition.data),setData(patch){writes.push(patch);Object.assign(this.data,patch);}};
  function reply(result={version,revision:2,state:'PARTIAL'},index=0){requests[index].success({statusCode:200,data:{payment_enabled:false,result}});}
  return {page,wx,requests,writes,reads,reply,loginCount:()=>loginCount,
    choose:()=>choose,read:()=>read,
    pick(file={name:'fixture.pdf',path:'/synthetic/fixture.pdf',size:Buffer.from(fixture,'base64').length}){choose.success({tempFiles:[file]});},
    readSuccess(content=fixture){read.success({data:content});}};
}
async function ready(){const h=harness();await h.page.onLoad({scene:'shop1'});h.page.setData({projectCustomerId:'customer1',
  projectChecklist:[{id:'material1',revision:1,state:'MISSING',submission_type:'PRIVATE_DOCUMENT'},
    {id:'reference2',revision:3,state:'PARTIAL',submission_type:'OAUTH'}]});return h;}

test('document session sends only four fields on dedicated route with bearer and scene; preserves partial state',async()=>{
  const h=await ready(),s=h.page.session,p=params(),pending=s.projectDocument('shop1',p,s.getGeneration());
  assert.equal(h.requests.length,1);const request=h.requests[0];
  assert.equal(request.url,'https://fixture.invalid/mini/project-materials');
  assert.equal(request.header['X-Community-Session'],'1'.repeat(32));assert.equal(request.header['X-Community-Scene'],'shop1');
  assert.deepEqual(request.data,p);h.reply();assert.deepEqual(await pending,{version,revision:2,state:'PARTIAL'});
});
test('document session rejects invalid fields, filenames, encoding, and oversize before transmission',async()=>{
  const h=await ready(),s=h.page.session;
  const invalid=[{scan_state:'CLEAN'},{project:'foreign'},{path:'/tmp/file'},
    {item:'../material'},{item:'a'.repeat(65)},{revision:-1},{revision:1.1},{revision:Number.MAX_SAFE_INTEGER+1},
    {filename:'../fixture.pdf'},{filename:'x\\fixture.pdf'},{filename:'x:fixture.pdf'},
    {filename:' fixture.pdf'},{filename:'fixture.pdf '},{filename:'x\u202efile.pdf'},{filename:'x\x00.pdf'},
    {filename:'x'.repeat(181)+'.pdf'},{filename:'fixture.exe'},
    {filename:'fixture.png'},{content_base64:Buffer.from('executable fixture').toString('base64')},{content_base64:''},{content_base64:'abc'},{content_base64:'YQ=\n'},{content_base64:'YR=='},
    {content_base64:'YWJ='},{content_base64:'YQ==='},{content_base64:'Y=Q='},
    {content_base64:Buffer.alloc(5000001,1).toString('base64')}];
  for(const patch of invalid)await assert.rejects(s.projectDocument('shop1',{...params(),...patch}),/INVALID_PROJECT_DOCUMENT/);
  await assert.rejects(s.projectDocument('bad/scene',params()),/INVALID_PROJECT_DOCUMENT/);
  assert.equal(h.requests.length,0);
});
test('document session accepts exact 5MB bound, but never accepts malformed server receipts',async()=>{
  const h=await ready(),p={...params(),content_base64:boundedFile(5000000)};
  const pending=h.page.session.projectDocument('shop1',p);h.reply();await pending;
  for(const result of [{version,revision:3,state:'PARTIAL'},{version:'bad',revision:2,state:'PARTIAL'},
    {version,revision:2,state:'APPROVED'},{version,revision:2,state:'PARTIAL',scanner:'client'}]){
    const request=h.page.session.projectDocument('shop1',params());h.reply(result,h.requests.length-1);
    await assert.rejects(request,/UNTRUSTED_PROJECT_DOCUMENT_REPLY/);
  }
});
test('document session rejects old auth generation before sending and late results after clear',async()=>{
  const h=await ready(),s=h.page.session,generation=s.getGeneration();await s.login();
  await assert.rejects(s.projectDocument('shop1',params(),generation),/STALE_SESSION/);assert.equal(h.requests.length,0);
  const pending=s.projectDocument('shop1',params());s.clear();h.reply();await assert.rejects(pending,/STALE_SESSION/);
  await assert.rejects(s.projectDocument('shop1',params()),/SESSION_EXPIRED/);
});
test('upload button selects one fixture, reads base64, saves a version, then waits for separate submit',async()=>{
  const h=await ready(),p=h.page,pending=p.uploadProjectDocument(event());
  assert.equal(h.choose().count,1);assert.equal(h.choose().type,'file');assert.deepEqual(Array.from(h.choose().extension),['pdf','png','jpg','jpeg']);
  h.pick();await tick();assert.equal(h.read().encoding,'base64');assert.equal(h.read().filePath,'/synthetic/fixture.pdf');
  h.readSuccess();await tick();assert.equal(h.requests.length,1);h.reply();await pending;
  assert.equal(p.data.pending,false);assert.equal(p.data.projectChecklist[0].revision,2);assert.equal(p.data.projectChecklist[0].state,'PARTIAL');
  assert.match(p.data.status,/需单独提交审核/);assert.equal(h.requests.length,1);
  assert.ok(!JSON.stringify(p.data).includes(fixture));assert.ok(!JSON.stringify(p.data).includes('/synthetic/'));
  const submit=p.submitProjectItem(event('material1',2));assert.equal(h.requests[1].data.operation,'commerce.project_submit');
  assert.equal(h.requests[1].data.params.revision,2);h.reply({state:'SUBMITTED'},1);await tick();h.reply({items:[]},2);await submit;
});
for(const stage of ['choose','read','upload'])for(const change of ['switch','unload','reauth'])for(const outcome of ['success','error']){
  test(`${stage} late ${outcome} after ${change} cannot read/send old file or overwrite state`,async()=>{
    const h=await ready(),p=h.page,pending=p.uploadProjectDocument(event());
    if(stage!=='choose'){h.pick();await tick();}
    if(stage==='upload'){h.readSuccess();await tick();}
    if(change==='unload')p.onUnload();
    else if(change==='reauth')await p.session.login();
    else {p.setData({pending:false});p.selectProjectRequirement(event('reference2',3));p.setData({pending:true,status:'new selection'});}
    const writes=h.writes.length,reads=h.reads.length,requests=h.requests.length;
    if(stage==='choose')outcome==='success'?h.pick():h.choose().fail({errMsg:'chooseMessageFile:fail'});
    if(stage==='read')outcome==='success'?h.readSuccess():h.read().fail({errMsg:'readFile:fail'});
    if(stage==='upload')outcome==='success'?h.reply():h.requests[0].fail({errMsg:'request:fail'});
    await pending;
    assert.equal(h.writes.length,writes);assert.equal(h.reads.length,reads);assert.equal(h.requests.length,requests);
    assert.equal(h.loginCount(),change==='reauth'?2:1);
  });
}
test('cancel, invalid picker files, and read failures never upload',async()=>{
  for(const mode of ['cancel','bad-extension','too-big','empty','read-error']){
    const h=await ready(),pending=h.page.uploadProjectDocument(event());
    if(mode==='cancel')h.choose().fail({errMsg:'chooseMessageFile:fail cancel'});
    else {h.pick({name:mode==='bad-extension'?'fixture.exe':'fixture.pdf',path:'/synthetic/file',size:mode==='too-big'?5000001:mode==='empty'?0:20});await tick();
      if(mode==='read-error')h.read().fail({errMsg:'readFile:fail'});}
    await pending;assert.equal(h.requests.length,0);assert.equal(h.page.data.pending,false);
    if(mode==='cancel')assert.match(h.page.data.status,/取消/);
  }
});
test('wrong requirement type or stale revision cannot open a picker',async()=>{
  const h=await ready();await h.page.uploadProjectDocument(event('reference2',3));await h.page.uploadProjectDocument(event('material1',0));
  assert.equal(h.choose(),undefined);assert.equal(h.requests.length,0);
});
test('unknown upload result requests checklist refresh and does not resend or submit',async()=>{
  const h=await ready(),pending=h.page.uploadProjectDocument(event());h.pick();await tick();h.readSuccess();await tick();
  h.requests[0].fail({errMsg:'request:fail'});await pending;
  assert.match(h.page.data.status,/先刷新资料清单/);assert.equal(h.page.data.pending,false);
  assert.equal(h.requests.length,1);assert.equal(h.page.data.projectChecklist[0].revision,1);
});
test('consumer storefront excludes internal project document forms',()=>{
  // Current customer-pages contract separates community shoppers from delivery forms.
  // Upload/reference/submit authorization and failure behavior remain covered above/below.
  const markup=fs.readFileSync(__dirname+'/pages/checkout/index.wxml','utf8');
  assert.doesNotMatch(markup,/uploadProjectDocument|selectProjectRequirement|submitProjectItem/);
  assert.match(markup,/bindtap="loadOrders"/);
});

test('local document validation failure is not presented as an uncertain upload',async()=>{
  const h=await ready(),pending=h.page.uploadProjectDocument(event());h.pick();await tick();
  h.readSuccess(Buffer.from('not a PDF').toString('base64'));await pending;
  assert.equal(h.requests.length,0);assert.equal(h.page.data.pending,false);
  assert.match(h.page.data.status,/文件名称、格式或内容无效/);assert.doesNotMatch(h.page.data.status,/上传结果未确认/);
});
for(const [filename,bytes] of [['fixture.png',Buffer.from([137,80,78,71,13,10,26,10,0])],
  ['fixture.jpg',Buffer.from([255,216,255,224])],['fixture.jpeg',Buffer.from([255,216,255,225])]]){
  test(`valid ${filename} magic and extension are accepted`,async()=>{
    const h=await ready(),pending=h.page.session.projectDocument('shop1',{...params(),filename,content_base64:bytes.toString('base64')});
    assert.equal(h.requests.length,1);h.reply();await pending;
  });
}
