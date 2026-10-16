'use strict';
const {spawn}=require('node:child_process');
const readline=require('node:readline'),fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {chromium,request}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const child=spawn(process.env.PYTHON||'python3',['-m','tests.pr122_customer_edit_pipeline_server'],{stdio:['ignore','pipe','inherit']});
 let browser,api;
 try{
  const lines=readline.createInterface({input:child.stdout});
  const first=await new Promise((resolve,reject)=>{lines.once('line',resolve);child.once('exit',()=>reject(Error('fixture stopped')));});
  const {api_port,render_port,case:caseId,before_sha256}=JSON.parse(first);
  api=await request.newContext({baseURL:'http://127.0.0.1:'+api_port,extraHTTPHeaders:{Host:'wenwenwenyiyiyi.work',Origin:'https://wenwenwenyiyiyi.work'}});
  const login=await api.post('/customer/center/api/login',{data:{email:'reviewer@example.com',password:'correct-password-123'}});
  assert.equal(login.status(),200);
  const session=await login.json();
  const headers={Cookie:login.headers()['set-cookie'].split(';')[0],'X-CSRF-Token':session.csrf};
  const queued=await api.post('/customer/center/api/change_small_edit',{headers,data:{project:'project-a',case:caseId}});
  assert.equal(queued.status(),200);
  const {id}=await queued.json();let candidate;
  for(let i=0;i<100;i++){
   const response=await api.get('/customer/center/api/edit_candidate/project-a/'+id,{headers});assert.equal(response.status(),200);
   const state=await response.json();if(state.state==='CANDIDATE_READY'){candidate=state;break;}assert.equal(state.state==='QUEUED'||state.state==='PROCESSING',true);await new Promise(r=>setTimeout(r,50));
  }
  assert(candidate);assert.equal(candidate.production_published,false);
  const artifact=candidate.result.artifact,receipt=artifact.receipt,body=Buffer.from(artifact.page_base64,'base64');
  assert.equal(receipt.before_sha256,before_sha256);assert.equal(crypto.createHash('sha256').update(body).digest('hex'),receipt.after_sha256);
  assert.equal(receipt.model_api_calls,0);assert.equal(receipt.historical_contract_lookups,0);
  browser=await chromium.launch({headless:true});const checks=[];
  for(const width of [1440,390]){
   const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
   const response=await page.goto('http://127.0.0.1:'+render_port+'/candidate');assert.equal(response.status(),200);
   assert.equal(response.headers()['x-candidate-sha256'],receipt.after_sha256);assert.equal(await page.locator('p').innerText(),'Welcomes to Xuanjun');
   assert.equal(await page.evaluate(()=>document.documentElement.dataset.fixture),'ready');assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(errors.length,0);
   checks.push({width,exact_candidate_sha256:receipt.after_sha256,text:'PASS',original_script:'PASS',overflow:false,javascript_errors:errors});await context.close();
  }
  const dir=process.env.XJ_CUSTOMER_REPORT_DIR||'/tmp/pr122-customer';fs.mkdirSync(dir,{recursive:true});
  fs.writeFileSync(dir+'/EDIT_PIPELINE_BROWSER_REPORT.json',JSON.stringify({status:'PASS',job:id,candidate_artifact_sha256:candidate.result.artifact_sha256,checks,scope:'ISOLATED_LOOPBACK_CANDIDATE_NOT_PRODUCTION',tls_verified:false,production_signature_issued:false,production_published:false},null,2));
 }finally{if(api)await api.dispose();if(browser)await browser.close();child.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
