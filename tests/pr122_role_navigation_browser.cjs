'use strict';
/* Hosted navigation only. Build XJ_HUB_STAGE using --browser-fixture AND
 * --derive-navigation. No payment/order/login controls are exercised.
 * XJ_HUB_STAGE=/tmp/pr122-site-navigation XJ_ROLE_NAV_REPORT=/tmp/role-navigation \
 * PLAYWRIGHT_MODULE=.../node_modules/playwright node tests/pr122_role_navigation_browser.cjs
 */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
assert(process.env.XJ_HUB_STAGE,'XJ_HUB_STAGE required');
const stage=path.resolve(process.env.XJ_HUB_STAGE);
const manifest=JSON.parse(fs.readFileSync(path.join(stage,'MANIFEST.json'),'utf8'));
assert.equal(manifest.status,'HOSTED_BROWSER_FIXTURE_ONLY');
assert.equal(manifest.production_approved,false);
assert.equal(manifest.navigation_derivation?.navigation_derivation?.state,'NEW_CANDIDATE_PENDING_REVIEW','Build with --derive-navigation');
assert.equal(manifest.navigation_derivation.real_payment,false);
const mobile='/visual/community-payment/mobile/';
const roles={consumer:mobile,merchant:mobile+'merchant.html',community:mobile+'community.html',beneficiary:mobile+'beneficiary.html',platform:mobile+'platform.html'};
const roleByPath=new Map(Object.entries(roles).map(([r,p])=>[p,r]));
roleByPath.set(mobile+'index.html','consumer');
for(const file of ['index.html','merchant.html','community.html','beneficiary.html','platform.html','role.js']){
 const relative=mobile.slice(1)+file;
 const actual=crypto.createHash('sha256').update(fs.readFileSync(path.join(stage,'public',relative))).digest('hex');
 assert.equal(manifest.files[relative],actual,'Final stage manifest must bind '+relative);
}
const reportDir=path.resolve(process.env.XJ_ROLE_NAV_REPORT||'role-navigation-report');
fs.mkdirSync(reportDir,{recursive:true});
const results=[],edges=[],screenshots=[],errors=[],failedAssets=[],blockedWrites=[];
let server,browser;
function ready(child){return new Promise((resolve,reject)=>{
 let stdout='',stderr='';
 const timer=setTimeout(()=>reject(Error('Loopback startup timeout: '+stderr)),20000);
 child.stderr.on('data',b=>stderr+=b);
 child.once('error',e=>{clearTimeout(timer);reject(e);});
 child.once('exit',c=>{clearTimeout(timer);reject(Error('Loopback exited '+c+': '+stderr));});
 child.stdout.on('data',b=>{stdout+=b;if(!stdout.includes('\n'))return;try{
  const state=JSON.parse(stdout.split('\n')[0]);assert.equal(state.status,'LOOPBACK_TEST_ONLY');assert(state.port>0);clearTimeout(timer);resolve(state.port);
 }catch(e){clearTimeout(timer);reject(e);}});
});}
function contextSuffix(locale){return locale?'?lang='+locale:'';}
function hubPath(locale){return '/'+(locale?locale+'/':'')+'visual/community-payment/';}
async function clickNavigation(page,selector,base,expected){
 const target=page.locator(selector).first();assert(await target.isVisible(),'Navigation target must be visible: '+selector);
 const [response]=await Promise.all([page.waitForNavigation(),target.click()]);
 assert.equal(response.status(),200,expected);assert.equal(page.url(),base+expected);
}
async function verifyRole(page,role,locale,base){
 const current=new URL(page.url());assert.equal(current.origin,base);assert.equal(roleByPath.get(current.pathname),role);
 assert.equal(current.searchParams.get('lang'),locale||null);
 // Every page, including the consumer, must load the shared context adapter.
 assert.equal(await page.locator('script[src="./role.js"]').count(),1);
 // Role implementations intentionally remain Chinese. No English translation claim.
 const returnSelector=role==='consumer'?'.preview-bar>a':'.device-role-tools>a';
 assert.equal(await page.locator(returnSelector).first().getAttribute('href'),hubPath(locale));
 const links=await page.locator('a[href]').evaluateAll(as=>as.map(a=>({raw:a.getAttribute('href'),url:a.href})));
 const targets=[];
 for(const link of links){
  const url=new URL(link.url);if(url.origin!==base||link.raw.startsWith('#'))continue;
  const next=roleByPath.get(url.pathname);
  if(next){assert.equal(url.searchParams.get('lang'),locale||null,'Role switch loses language: '+link.raw);targets.push({role:next,href:url.pathname+url.search+url.hash});}
  assert(!/^\/visual\/community-local-e2e\/(?:index\.html|merchant\.html|community\.html|beneficiary\.html|platform\.html)?$/.test(url.pathname),'Legacy role anchor survived: '+link.raw);
 }
 return {returnSelector,targets:[...new Map(targets.map(t=>[t.href,t])).values()]};
}
(async()=>{
 server=spawn('python3',['scripts/pr122_site_hub_test_server.py','--stage',stage,'--port','0'],{stdio:['ignore','pipe','pipe']});
 const base='http://127.0.0.1:'+await ready(server);
 browser=await chromium.launch({headless:true});
 const context=await browser.newContext({serviceWorkers:'block'});
 await context.route('**/*',route=>{
  const req=route.request();if(new URL(req.url()).origin!==base)return route.abort();
  if(!['GET','HEAD'].includes(req.method())){blockedWrites.push(req.method()+' '+new URL(req.url()).pathname);return route.abort();}
  return route.continue();
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 page.on('response',r=>{if(r.url().startsWith(base)&&r.status()>=400&&/\.(?:js|css|mjs)(?:\?|$)/.test(r.url()))failedAssets.push(r.url());});
 for(const width of [320,390,1440]){
  await page.setViewportSize({width,height:1000});
  for(const locale of ['','en','zh-cn']){
   for(const [role,rolePath] of Object.entries(roles)){
    const hub=hubPath(locale),target=rolePath+contextSuffix(locale);
    assert.equal((await page.goto(base+hub)).status(),200);
    const selector='main a[href='+JSON.stringify(target)+']';
    assert.equal(await page.locator(selector).count(),1,'Exactly one reviewed project entry for '+role);
    await clickNavigation(page,selector,base,target);
    const checked=await verifyRole(page,role,locale,base);
    if(width!==390){
     const name=`ROLE_NAV_${locale||'root'}_${role}_${width}.png`;
     await page.screenshot({path:path.join(reportDir,name),fullPage:true});screenshots.push(name);
    }
    // Exercise only real role-to-role anchors found in the generated page.
    // Consumer need not invent switches absent from its reviewed structure.
    if(['community','beneficiary'].includes(role)){
     assert(checked.targets.some(t=>t.role==='merchant'),'Expected reviewed merchant switch');
     assert(checked.targets.some(t=>t.role==='platform'),'Expected reviewed platform switch');
    }
    if(role==='platform')assert(checked.targets.some(t=>t.role==='consumer'),'Expected reviewed consumer switch');
    for(const next of checked.targets.filter(t=>t.role!==role)){
     await page.goto(base+target);
     await verifyRole(page,role,locale,base);
     await clickNavigation(page,'a[href='+JSON.stringify(next.href)+']',base,next.href);
     const destination=await verifyRole(page,next.role,locale,base);
     await clickNavigation(page,destination.returnSelector,base,hub);
     edges.push({width,locale:locale||'root',from:role,to:next.role,returned_to:hub});
    }
    await page.goto(base+target);
    const restored=await verifyRole(page,role,locale,base);
    await clickNavigation(page,restored.returnSelector,base,hub);
    results.push({width,locale:locale||'root',role,hub_entry:'PASS',shared_role_script:'PASS',language_context_return:'PASS'});
   }
  }
 }
 assert.deepEqual(errors,[]);assert.deepEqual(failedAssets,[]);
 fs.writeFileSync(path.join(reportDir,'ROLE_NAVIGATION_BROWSER_REPORT.json'),JSON.stringify({status:'PASS',scope:'Synthetic Hosted loopback navigation; Chinese role bodies unchanged',production_browser:'NOT_RUN',payment_order_login_controls:'NOT_CLICKED',viewports:[320,390,1440],results,edges,screenshots,errors,failedAssets,blockedWrites},null,2)+'\n');
})().catch(e=>{
 fs.writeFileSync(path.join(reportDir,'ROLE_NAVIGATION_BROWSER_REPORT.json'),JSON.stringify({status:'FAIL',error:e.stack,results,edges,screenshots,errors,failedAssets,blockedWrites,production_browser:'NOT_RUN'},null,2)+'\n');
 console.error(e);process.exitCode=1;
}).finally(async()=>{if(browser)await browser.close();if(server)server.kill('SIGTERM');});
