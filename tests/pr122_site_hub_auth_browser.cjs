'use strict';
// Real Chromium UI with synthetic HTTP only. No real mail, backend or customer data.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const origin='https://wenwenwenyiyiyi.work',base='/customer/center/';
const ui=path.join(__dirname,'..','deploy/pr122-customer-center/ui');
async function check(browser,width){
 const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();
 const calls=[],queues=new Map(),errors=[];let release,holdReady,announceHold;
 page.on('pageerror',e=>errors.push(String(e)));
 function reply(op,status,body){if(body.hold)holdReady=new Promise(resolve=>{announceHold=resolve;});const q=queues.get(op)||[];q.push({status,body});queues.set(op,q);}
 const count=op=>calls.filter(x=>x.op===op).length;
 await context.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url());assert.equal(url.origin,origin,'No external network');
  if(url.pathname.startsWith(base+'api/')){
   const op=url.pathname.slice((base+'api/').length);calls.push({op,body:req.postData()?JSON.parse(req.postData()):null});
   const r=queues.get(op)?.shift();
   if(!r){assert.equal(op,'me','Unexpected API call '+op);return route.fulfill({status:403,json:{error:'fixture unauthenticated'}});}
   if(r.body.hold)await new Promise(resolve=>{release=resolve;announceHold();});
   return route.fulfill({status:r.status,json:r.body});
  }
  const name=url.pathname===base?'index.html':url.pathname.slice(base.length);
  assert(['index.html','app.js','app.css'].includes(name),'Unexpected asset '+name);
  await route.fulfill({status:200,contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(path.join(ui,name))});
 });
 const notice=text=>page.waitForFunction(t=>document.getElementById('notice').textContent.includes(t),text);
 const fill=(form,name,value)=>page.locator('#'+form+' [name='+name+']').fill(value);
 const value=(form,name)=>page.locator('#'+form+' [name='+name+']').inputValue();
 async function submit(form){await page.locator('#'+form+' button').click();}
 async function duplicate(selector){await page.waitForFunction(s=>document.querySelector(s).disabled,selector);await page.locator(selector).evaluate(b=>b.click());}
 try{
  const initialSession=page.waitForResponse(r=>r.url()===origin+base+'api/me');await page.goto(origin+base);await initialSession;
  await fill('login','email','new-customer@example.com');await fill('login','password','short');
  await page.locator('#register').click();assert.equal(count('register'),0);
  await fill('login','password','fictional-password-123');reply('register',200,{status:'CHECK_VERIFICATION_CHANNEL',hold:true});
  await page.locator('#register').click();await duplicate('#register');await holdReady;assert.equal(count('register'),1);release();await notice('验证邮箱');
  assert.equal(await value('login','password'),'');assert(await page.locator('#workspace').isHidden());
  await page.reload();assert.equal(await value('login','password'),'');await page.locator('summary').click();
  await fill('verification','token','fixture-expired-token');await fill('verification','password','fictional-password-123');
  reply('verify',400,{error:'fixture token expired'});await submit('verification');await notice('fixture token expired');assert(await page.locator('#workspace').isHidden());
  await fill('verification','token','fixture-valid-token');reply('verify',200,{verified:true,hold:true});
  await submit('verification');await duplicate('#verification button');await holdReady;assert.equal(count('verify'),2);release();await notice('邮箱已验证，请登录。');
  assert.equal(await value('verification','token'),'');assert.equal(await value('verification','password'),'');assert(await page.locator('#workspace').isHidden());
  await fill('login','email','new-customer@example.com');reply('request_reset',200,{status:'CHECK_VERIFICATION_CHANNEL'});await page.locator('#reset-request').click();await notice('如该邮箱已注册');
  assert.deepEqual(calls.find(x=>x.op==='request_reset').body,{email:'new-customer@example.com'});
  await fill('reset','token','fixture-reset-token');await fill('reset','password','fictional-password-123');reply('reset',503,{error:'fixture reset unavailable'});await submit('reset');await notice('fixture reset unavailable');assert.equal(await value('reset','token'),'fixture-reset-token');
  await page.evaluate(()=>{sessionStorage.setItem('xj_csrf','fixture-old-csrf');csrf='fixture-old-csrf';});
  reply('reset',200,{reset:true,hold:true});await submit('reset');await duplicate('#reset button');await holdReady;assert.equal(count('reset'),2);release();await notice('密码已重置');
  assert.equal(await value('reset','token'),'');assert.equal(await value('reset','password'),'');assert.equal(await page.evaluate(()=>sessionStorage.getItem('xj_csrf')),null);assert(await page.locator('#workspace').isHidden());
  await page.reload();assert.equal(await value('reset','password'),'');assert(await page.locator('#workspace').isHidden());
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.deepEqual(errors,[]);
  return {width,registration_validation_and_repeat:'PASS',verification_failure_retry_and_repeat:'PASS',reset_failure_retry_and_repeat:'PASS',reload_secret_clearing:'PASS',overflow:false,js_errors:errors};
 }finally{if(release)release();await context.close();}
}
(async()=>{const browser=await chromium.launch({headless:true,chromiumSandbox:true,...(process.env.XJ_CHROMIUM_EXECUTABLE?{executablePath:process.env.XJ_CHROMIUM_EXECUTABLE}:{})});try{const checks=[];for(const width of [1440,390,320])checks.push(await check(browser,width));console.log(JSON.stringify({status:'PASS',browser_version:browser.version(),browser_executable:process.env.XJ_CHROMIUM_EXECUTABLE||'PLAYWRIGHT_BUNDLED',chromium_sandbox:true,scope:'Real UI, synthetic same-origin HTTP. Backend mail/token security and production HTTPS NOT_RUN',checks}));}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
