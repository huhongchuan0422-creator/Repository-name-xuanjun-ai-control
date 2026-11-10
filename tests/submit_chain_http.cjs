// Actual native controllers + actual session transport to the original Python HTTP services.
const fs=require('node:fs'),vm=require('node:vm'),http=require('node:http'),assert=require('node:assert/strict');
const root=process.cwd()+'/clients/community-mini',session=require(root+'/session'),auth=require(root+'/customer-auth'),form=require(root+'/merchant-form');
let code=0;const base=process.env.COMMUNITY_TEST_ORIGIN;
const app={globalData:{baseUrl:base}},trace=[];let lastCredential,platformAck=false;
const image=Buffer.from('\x89PNG\r\n\x1a\nSynthetic test document','binary');
const responseErrors=[];const navigations=[];const wx={chooseMedia(o){assert.equal(o.mediaType.join(','),'image');o.success({tempFiles:[{tempFilePath:'isolated-fixture.png',size:image.length}]});},getFileSystemManager(){return {stat(o){assert.equal(o.path,'isolated-fixture.png');o.success({stats:{size:image.length}});},readFile(o){assert.equal(o.filePath,'isolated-fixture.png');o.success({data:image.toString('base64')});}}},login(o){o.success({code:'controller-code-'+(++code)});},request(o){if(process.env.CASE==='legacy'&&o.data.params?.operation==='wechat_apply')delete o.data.params.params.application_revision;if(process.env.CASE==='original-gap'&&platformAck&&o.data.params?.operation==='read'){o.fail({errMsg:'synthetic post-platform read loss'});return;}trace.push({path:new URL(o.url).pathname,operation:o.data.operation,child:o.data.params?.operation,scene:o.header['X-Community-Scene']||''});lastCredential=o.header['X-Community-Session']||lastCredential;const u=new URL(o.url),raw=JSON.stringify(o.data);assert.equal(u.origin,base,'NON_LOOPBACK_DENIED');const req=http.request(u,{method:o.method,headers:{...o.header,'Content-Length':Buffer.byteLength(raw)}},res=>{let body='';res.on('data',v=>body+=v);res.on('end',()=>{try{const data=JSON.parse(body);if(o.data.params?.operation==='submit'&&res.statusCode<400)platformAck=true;if(res.statusCode>=400)responseErrors.push({operation:o.data.operation,child:o.data.params?.operation,error:data.error});o.success({statusCode:res.statusCode,data});}catch(e){o.fail({errMsg:'invalid reply'});}});});req.on('error',()=>o.fail({errMsg:'transport unknown'}));req.end(raw);},navigateTo(o){navigations.push(o.url);o.success?.();o.complete?.();},redirectTo(o){navigations.push(o.url);o.success?.();o.complete?.();}};
function page(name){let definition;vm.runInNewContext(fs.readFileSync(root+'/pages/'+name+'/index.js','utf8'),{Page:p=>definition=p,wx,getApp:()=>app,require:p=>p==='../../merchant-submit'&&process.env.CASE==='original-gap'?require(process.cwd()+'/tests/original_a1a6_submit.cjs'):p==='../../session'?session:p==='../../customer-auth'?auth:p==='../../merchant-form'?form:(p.startsWith('.')?require(require('node:path').resolve(root+'/pages/'+name,p)):require(p)),encodeURIComponent,setTimeout,clearTimeout});return {...definition,data:structuredClone(definition.data),setData(p,cb){Object.assign(this.data,p);if(cb)cb();}};}
(async()=>{
 const join=page('merchant-join');await join.onLoad({scene:'shop1'});assert.equal(join.data.ready,true,join.data.status);
 await join.load(process.env.SYNTHETIC_APPLICATION);
 await join.submitAllReview();
 const which=process.env.CASE;
 if(which==='original-gap'){
  assert.equal(trace.filter(x=>x.child==='submit').length,1);
  assert.equal(trace.filter(x=>x.child==='wechat_apply').length,0);
 }else{
  assert.equal(trace.filter(x=>x.child==='submit').length,0);
  assert.equal(trace.filter(x=>x.child==='wechat_apply').length,1);
  if(which==='success')assert.equal(join.reviewState,'SUBMITTED_TO_PROVIDER',join.data.status);
  if(which==='unknown'){
   await join.refreshApplication();await join.submitAllReview();
   assert.equal(trace.filter(x=>x.child==='wechat_apply').length,1);
   assert.equal(join.reviewState,'SUBMISSION_UNKNOWN');
  }
 }
 console.log(JSON.stringify({case:which,client_platform_calls:trace.filter(x=>x.child==='submit').length,apply_calls:trace.filter(x=>x.child==='wechat_apply').length,review:join.reviewState}));
 join.onUnload();
})().catch(e=>{console.error(e);process.exitCode=1;});
