/* Real Chromium over the exact generated new pages; old shell is a pinned fixture. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const stage=path.resolve(process.env.XJ_HUB_STAGE||'.test-stage');
const out=path.resolve(process.env.XJ_HUB_REPORT||'.test-browser-report.json');
const server=spawn('python3',['scripts/pr122_site_hub_test_server.py','--stage',stage,'--port','18792'],{env:process.env,stdio:['ignore','pipe','pipe']});
let serverErrors='';server.stderr.on('data',d=>serverErrors+=d);
const ready=new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.once('exit',code=>reject(Error('Server exited '+code+' '+serverErrors)));});
const origin='http://127.0.0.1:18792';
const roots=['marketplace/','marketplace/modules/','visual/','visual/catalog/','visual/community-payment/','ecosystem/','ecosystem/tiers/','ecosystem/co-create/','ecosystem/profit-sharing/','ecosystem/ledger/','ecosystem/activities/','ecosystem/governance/','customer/projects/','customer/projects/acceptance/'];
(async()=>{
 await ready;
 const browser=await chromium.launch({headless:true});
 const failures=[],resources=[],checks=[];
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  // The private 1187-file archive is not uploaded to Hosted CI. Image placeholders
  // are confined to the old shell fixture, never used for new CSS/JS or demo APIs.
  await context.route('**/assets/*.png',route=>route.fulfill({status:200,contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j/kcAAAAASUVORK5CYII=','base64')}));
  const page=await context.newPage();
  page.on('pageerror',e=>failures.push(e.message));
  page.on('console',m=>{if(m.type()==='error'&&/Content Security Policy|Refused to/.test(m.text()))failures.push(m.text());});
  page.on('response',r=>{if(r.status()>=400&&/\.(?:css|js|mjs)(?:\?|$)/.test(r.url()))resources.push({url:r.url(),status:r.status()});});
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:1000});
   for(const prefix of ['','zh-cn/','en/'])for(const route of roots){
    const r=await page.goto(origin+'/'+prefix+route);assert.equal(r.status(),200);
    assert.equal(await page.locator('.primary-nav .nav-group').count(),4);
    assert.equal(await page.locator('main h1').count(),1);
    const icp=page.locator('footer a[href="https://beian.miit.gov.cn/"]');
    assert.equal(await icp.count(),1);assert.equal(await icp.innerText(),'渝ICP备2026024862号');
    await icp.scrollIntoViewIfNeeded();assert.equal(await icp.isVisible(),true);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,`${width} ${prefix+route} horizontal overflow`);
    if(prefix==='en/')assert.doesNotMatch(await page.locator('main').innerText(),/[\u4e00-\u9fff]/);
   }
   checks.push({test:'all_42_content_pages',viewport:width,result:'PASS'});
  }
  await page.setViewportSize({width:1440,height:1000});await page.goto(origin+'/marketplace/');
  const gaps=await page.locator('.primary-nav .nav-group').evaluateAll(groups=>groups.map(g=>{
   const a=g.querySelector('a'),b=g.querySelector('button'),range=document.createRange();range.selectNodeContents(a);
   const arrow=document.createRange();arrow.selectNodeContents(b);return arrow.getBoundingClientRect().left-range.getBoundingClientRect().right;
  }));
  for(const gap of gaps)assert(gap>=4&&gap<=6,'Text-arrow gap '+gap);
  const first=page.locator('.primary-nav .nav-group').first(),button=first.locator('button');
  await first.locator('a').first().focus();await page.keyboard.press('Tab');assert.equal(await button.evaluate(e=>e===document.activeElement),true);
  await page.keyboard.press('Enter');assert.equal(await button.getAttribute('aria-expanded'),'true');
  await page.keyboard.press('Escape');assert.equal(await button.getAttribute('aria-expanded'),'false');
  checks.push({test:'keyboard_navigation_and_text_arrow_geometry',gap_pixels:gaps,result:'PASS'});
  await page.locator('#credit').fill('5000');await page.locator('#ecvQuote button').click();
  let text=await page.locator('#quoteResult').innerText();assert.match(text,/2400\.00/);assert.match(text,/1200\.00/);assert.match(text,/本单无正毛利/);
  await page.locator('#directCost').fill('');await page.locator('#ecvQuote button').click();assert.match(await page.locator('#quoteResult').innerText(),/成本未知，不可结算/);
  await page.locator('#serviceKind').selectOption('ordinary');await page.locator('#listPrice').fill('100');await page.locator('#credit').fill('100');await page.locator('#ecvQuote button').click();
  text=await page.locator('#quoteResult').innerText();assert.match(text,/上限90%/);assert.match(text,/预计实付：¥10\.00/);
  checks.push({test:'quote_6000_2400_1200_ordinary90_custom50_cost_unknown',result:'PASS'});
  await page.locator('.language>button').click();await page.locator('.language-panel a[lang="en"]').click();await page.waitForURL(origin+'/en/marketplace/');
  assert.equal(await page.locator('html').getAttribute('lang'),'en');assert.match(await page.locator('h1').innerText(),/Products/);
  await page.locator('#ecvQuote button').click();assert.match(await page.locator('#quoteResult').innerText(),/CNY 1200\.00/);
  checks.push({test:'route_preserving_English_switch_and_calculator',result:'PASS'});
  await page.setViewportSize({width:390,height:844});await page.goto(origin+'/');
  await page.locator('.mobile-toggle').click();assert(await page.locator('.primary-nav').isVisible());
  await page.locator('.nav-group').first().locator('button').click();assert(await page.locator('.nav-group').first().locator('.nav-panel').isVisible());
  checks.push({test:'mobile_navigation',result:'PASS'});
  for(const width of [320,390,780,1180,1440]){
   await page.setViewportSize({width,height:900});await page.goto(origin+'/');
   if(width<=1180){
    const bounds=await page.locator('.brand,.mobile-toggle,.language>button').evaluateAll(nodes=>nodes.filter(e=>e.getBoundingClientRect().width>0).map(e=>{const r=e.getBoundingClientRect();return {top:r.top+r.height/2,left:r.left,right:r.right};}));
    assert.equal(bounds.length,3);assert(Math.max(...bounds.map(r=>r.top))-Math.min(...bounds.map(r=>r.top))<=2,'Mobile header alignment '+width);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'Home overflow '+width);
    await page.locator('.mobile-toggle').click();
   }
   const second=page.locator('.primary-nav .nav-group').nth(1).locator('button');
   const before=await second.boundingBox();await second.click();await second.click();const after=await second.boundingBox();
   assert(Math.abs(before.y-after.y)<=1&&Math.abs(before.x-after.x)<=1,'Disclosure moved '+width);
   assert.equal(await second.getAttribute('aria-expanded'),'false');
   assert.equal(await page.locator('.primary-nav .nav-group').nth(1).locator('a[href*="/ecosystem/"]').count(),0);
   assert(await page.locator('#discover-ecosystem a[href="/ecosystem/"]').isVisible());
  }
  checks.push({test:'home_entry_hierarchy_header_alignment_disclosure_stationary',widths:[320,390,780,1180,1440],result:'PASS'});
  await page.goto(origin+'/visual/community-payment/merchant-dashboard/');
  for(const id of ['grocer','cafe','home']){
   await page.locator('#merchantSelect').selectOption(id);
   assert.match(await page.locator('#merchantIdentity').innerText(),/模拟商家/);
   assert.equal(await page.locator('#orderRows tr').count(),3);
   assert.equal(await page.locator('#metricOrders').innerText(),'3');
   assert.equal(await page.locator('#refundId').inputValue(),{'grocer':'DEMO-G101','cafe':'DEMO-C101','home':'DEMO-H101'}[id]);
  }
  await page.locator('[data-view="orders"]').click();await page.locator('#orderFilter').fill('不存在');assert(await page.locator('#orderEmpty').isVisible());
  await page.locator('#merchantSelect').selectOption('grocer');assert.equal(await page.locator('#orderRows tr').count(),3);
  checks.push({test:'three_explicit_demo_merchants_independent_fixture_views_and_search',result:'PASS'});
  const demo='/visual/community-local-e2e/';
  await page.goto(origin+demo);await page.waitForFunction(()=>document.querySelector('#demoSessionState').textContent.includes('已就绪'));await page.locator('#loadStorefront').click();await page.waitForFunction(()=>document.querySelector('#storefrontName').textContent.includes('Demo Merchant'));
  assert.match(await page.locator('#adAmount').innerText(),/DEMO APPROVED AMOUNT AD/);
  assert.equal(await page.locator('#successAd').isVisible(),false);
  await page.locator('#amount').fill('120');await page.locator('#create').click();await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('PENDING'));
  await page.locator('#complete').click();await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('SUCCESS'));assert(await page.locator('#successAd').isVisible());
  await page.reload();assert.equal(await page.locator('#successAd').isVisible(),false);
  checks.push({test:'consumer_amount_first_ad_simulated_payment_second_ad_refresh',result:'PASS'});
  await page.goto(origin+demo+'merchant.html');await page.locator('#load').click();await page.waitForFunction(()=>document.querySelector('#state').textContent.includes('SUCCESS'));
  assert.equal(await page.locator('#verified').innerText(),'否');
  await page.waitForFunction(()=>document.querySelector('#adminCapability').value.length>=32);await page.locator('#createAd').click();await page.waitForFunction(()=>document.querySelector('#adminStatus').textContent.startsWith('本地模拟操作完成'));
  await page.locator('#adVersion').fill('1');await page.locator('#submitAd').click();await page.waitForFunction(()=>document.querySelector('#adminStatus').textContent.includes('REVIEW'));
  await page.goto(origin+demo+'platform.html');await page.locator('#inspect').click();await page.waitForFunction(()=>document.querySelector('#state').textContent.includes('SUCCESS'));
  await page.waitForFunction(()=>document.querySelector('#adminCapability').value.length>=32);await page.locator('#approveCreative').click();await page.waitForFunction(()=>document.querySelector('#adminStatus').textContent.startsWith('本地模拟操作完成'));
  checks.push({test:'merchant_and_platform_read_views_and_fixture_ad_review',result:'PASS'});
  for(const role of ['community','beneficiary']){
   await page.goto(origin+demo+role+'.html');await page.locator('#inspect').click();assert.equal(await page.locator('#tasks li').count(),3);
   assert.match(await page.locator('#status').innerText(),/未向服务器/);
   await page.locator('nav a[href="/visual/community-payment/"]').first().click();await page.waitForURL(origin+'/visual/community-payment/');
  }
  await page.goto(origin+demo+'saas-panel.html');assert(await page.locator('#loadCatalog').isDisabled());
  checks.push({test:'community_beneficiary_returns_and_unconnected_saas_disabled',result:'PASS'});
  for(const file of ['index.html','merchant.html','platform.html','community.html','beneficiary.html','saas-panel.html']){
   await page.goto(origin+demo+file);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),file+' mobile overflow');
  }
  checks.push({test:'six_role_pages_mobile_layout',result:'PASS'});
  assert.equal((await page.request.get(origin+'/missing-test-path')).status(),404);
  assert.equal((await page.request.get(origin+'/.env')).status(),403);
  assert.equal((await page.request.get(origin+'/',{headers:{Host:'external.example'}})).status(),403);
  checks.push({test:'404_403_host_negative_paths',result:'PASS'});
  assert.deepEqual(failures,[]);assert.deepEqual(resources,[]);
  fs.writeFileSync(out,JSON.stringify({status:'PASS',scope:'Real generated new pages on pinned five-file old-shell fixture; ephemeral loopback demo service',old_shell_images:'TEST_PLACEHOLDERS',full_1187_file_browser_acceptance:'NOT_RUN',production_domain_https_acceptance:'NOT_RUN',checks,js_errors:failures,failed_script_style_resources:resources},null,2)+'\n');
 }finally{await browser.close();}
})().catch(e=>{fs.writeFileSync(out,JSON.stringify({status:'FAIL',error:e.stack,serverErrors},null,2)+'\n');console.error(e);process.exitCode=1;}).finally(()=>server.kill('SIGTERM'));
