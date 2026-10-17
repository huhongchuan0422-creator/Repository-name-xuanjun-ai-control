/* Generated dynamic catalog and approved-source merchant integration, loopback only. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawn,execFileSync}=require('node:child_process');
const os=require('node:os');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const sourceStage=process.env.XJ_HUB_STAGE;
const showcase=process.env.XJ_SHOWCASE_PUBLIC;
// Synthetic proofs stay inside this temporary loopback fixture, never the registry.
const fixtureRoot=fs.mkdtempSync(path.join(os.tmpdir(),'xj-role-fixture-'));
const fixtureOutput=path.join(fixtureRoot,'public');
const stage=path.join(fixtureRoot,'stage');
try {
 fs.cpSync(sourceStage,stage,{recursive:true});
 fs.cpSync(path.join(showcase,'showcase'),path.join(stage,'public/showcase'),{recursive:true});
 execFileSync('python3',['-m','tests.pr122_showcase_role_fixture','--output',fixtureOutput,'--stage',stage],{stdio:'pipe'});
 for(const prefix of ['', 'en/'])fs.cpSync(path.join(fixtureOutput,'showcase',prefix,'projects/synthetic-role-fixture'),path.join(stage,'public/showcase',prefix,'projects/synthetic-role-fixture'),{recursive:true});
} catch(e) {fs.rmSync(fixtureRoot,{recursive:true,force:true});throw e;}
const server=spawn('python3',['scripts/pr122_site_hub_test_server.py','--stage',stage,'--port','18791'],{stdio:['ignore','pipe','pipe']});
const ready=new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.once('exit',c=>reject(Error('Server exit '+c)));});
const base='http://127.0.0.1:18791';
function htmlFiles(root,prefix='') {return fs.readdirSync(root,{withFileTypes:true}).flatMap(e=>e.isDirectory()?htmlFiles(path.join(root,e.name),prefix+e.name+'/'):e.name.endsWith('.html')?[prefix+e.name]:[]);}
(async()=>{
 await ready;const browser=await chromium.launch({headless:true});const errors=[],resources=[];
 try{
  const context=await browser.newContext();
  await context.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
  await context.route('**/assets/*.png',route=>route.fulfill({status:200,contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j/kcAAAAASUVORK5CYII=','base64')}));
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error'&&/Content Security Policy|Refused to/.test(m.text()))errors.push(m.text());});
  page.on('response',r=>{if(r.status()>=400&&/\.(css|js|mjs)(\?|$)/.test(r.url()))resources.push(r.url());});
  const fixturePages=htmlFiles(path.join(fixtureOutput,'showcase'),'showcase/').filter(file=>file.includes('/projects/synthetic-role-fixture/'));
  const pages=[...htmlFiles(path.join(showcase,'showcase'),'showcase/'),...fixturePages];
  const rolePages=fixturePages.filter(file=>file.includes('/roles/'));
  assert.equal(rolePages.length,12,'Six roles must generate both languages');
  for(const width of [320,390,1440]){
   await page.setViewportSize({width,height:1000});
   for(const file of pages){
    const response=await page.goto(base+'/'+file);assert.equal(response.status(),200);
    if(file.includes('/roles/')){
     assert.equal(await page.locator('.primary-nav').count(),0,'Role shell must remain local');
     assert.equal(await page.locator('header nav[aria-label="Language"] a').count(),2);
    }else if(!file.includes('/views/'))assert.equal(await page.locator('.primary-nav .nav-group').count(),4);
    assert.equal(await page.locator('footer a[href="https://beian.miit.gov.cn/"]').count(),1);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),file+' overflow '+width);
   }
  }
  for(const width of [320,390,1440]){
   await page.setViewportSize({width,height:1000});
   for(const file of rolePages.filter(file=>!file.startsWith('showcase/en/'))){
    const route='/'+file.replace(/index\.html$/,'');
    const english=route.replace('/showcase/','/showcase/en/');
    const role=file.split('/roles/')[1].split('/')[0];
    await page.goto(base+route);
    assert.equal(await page.locator('body>nav a').count(),1);
    assert.equal(await page.locator('body>nav a').getAttribute('href'),'#feature-'+role+'-feature');
    const implementation='/showcase/projects/synthetic-role-fixture/views/'+role+'/v1/';
    assert.equal(await page.locator('main a').getAttribute('href'),implementation);
    await page.locator('header a[lang="en"]').click();await page.waitForURL(base+english);
    assert.equal(await page.locator('html').getAttribute('lang'),'en');
    assert.equal(await page.locator('header a[lang="en"]').getAttribute('aria-current'),'page');
    assert.equal(await page.locator('main a').getAttribute('href'),implementation,'Reviewed implementation identity must not be rewritten');
    assert.equal(await page.locator('header>a').getAttribute('href'),'/showcase/en/projects/synthetic-role-fixture/');
    await page.goBack();await page.waitForURL(base+route);
    await page.goForward();await page.waitForURL(base+english);
    await page.locator('header a[lang="zh-CN"]').click();await page.waitForURL(base+route);
    await page.locator('main a').click();await page.waitForURL(base+implementation);
    assert.match(await page.locator('main h1').innerText(),new RegExp('Synthetic '+role+'$'));
   }
   for(const prefix of ['', 'en/']){
    await page.goto(base+'/showcase/'+prefix+'ecosystem/');
    const links=await page.locator('main>nav:not(.showcase-subnav) a').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('href')));
    assert.deepEqual(links,['','tiers/','ledger/','profit-sharing/'].map(suffix=>'/'+prefix+'ecosystem/'+suffix));
   }
  }
  await page.setViewportSize({width:1440,height:1000});await page.goto(base+'/showcase/projects/community-payment/');
  assert.equal(await page.locator('a[href="/showcase/projects/community-payment/views/merchant/v1/"]').count(),1);
  assert.deepEqual(await page.locator('.primary-nav .nav-group>a').allTextContents(),['解决方案','功能市场','定制与交付','共创生态']);
  await page.locator('.language>button').click();await page.locator('.language-panel a[lang="en"]').click();await page.waitForURL(base+'/showcase/en/projects/community-payment/');
  assert.equal(await page.locator('html').getAttribute('lang'),'en');assert.doesNotMatch(await page.locator('main').innerText(),/[\u4e00-\u9fff]/);
  await page.locator('.language>button').click();await page.locator('.language-panel a[lang="zh-CN"]').click();await page.waitForURL(base+'/showcase/projects/community-payment/');
  await page.screenshot({path:process.env.XJ_SHOWCASE_REPORT_DIR+'/SHOWCASE_PROJECT_DESKTOP.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.locator('.mobile-toggle').click();assert(await page.locator('.primary-nav').isVisible());await page.locator('.mobile-toggle').click();await page.screenshot({path:process.env.XJ_SHOWCASE_REPORT_DIR+'/SHOWCASE_PROJECT_MOBILE.png',fullPage:true});
  await page.goto(base+'/showcase/projects/community-payment/views/merchant/v1/');
  for(const merchant of ['grocer','cafe','home']){await page.locator('#merchantSelect').selectOption(merchant);assert.match(await page.locator('#merchantIdentity').innerText(),/模拟商家/);assert.equal(await page.locator('#orderRows tr').count(),3);}
  await page.screenshot({path:process.env.XJ_SHOWCASE_REPORT_DIR+'/SHOWCASE_MERCHANT_MOBILE.png',fullPage:true});
  assert.deepEqual(errors,[]);assert.deepEqual(resources,[]);
  fs.writeFileSync(process.env.XJ_SHOWCASE_REPORT_DIR+'/SHOWCASE_BROWSER_REPORT.json',JSON.stringify({status:'PASS',scope:'Generated catalog and self-contained merchant on loopback fixture; not production HTTPS',pages:pages.length,viewports:[320,390,1440],project_navigation:'PASS',synthetic_role_pages:rolePages.length,role_language_and_isolation:'PASS',ecosystem_language:'PASS',official_header:'PASS',old_shell_images:'TEST_PLACEHOLDERS',three_simulated_merchants:'PASS',js_errors:errors,failed_assets:resources,production_browser:'NOT_RUN'},null,2)+'\n');
 } finally{await browser.close();server.kill('SIGTERM');fs.rmSync(fixtureRoot,{recursive:true,force:true});}
})().catch(e=>{console.error(e);server.kill('SIGTERM');fs.rmSync(fixtureRoot,{recursive:true,force:true});process.exitCode=1;});
