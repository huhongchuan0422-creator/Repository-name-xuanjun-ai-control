/* Generated dynamic catalog and approved-source merchant integration, loopback only. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const stage=process.env.XJ_HUB_STAGE;
const showcase=process.env.XJ_SHOWCASE_PUBLIC;
fs.cpSync(path.join(showcase,'showcase'),path.join(stage,'public/showcase'),{recursive:true});
const server=spawn('python3',['scripts/pr122_site_hub_test_server.py','--stage',stage,'--port','18791'],{stdio:['ignore','pipe','pipe']});
const ready=new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.once('exit',c=>reject(Error('Server exit '+c)));});
const base='http://127.0.0.1:18791';
function htmlFiles(root,prefix='') {return fs.readdirSync(root,{withFileTypes:true}).flatMap(e=>e.isDirectory()?htmlFiles(path.join(root,e.name),prefix+e.name+'/'):e.name.endsWith('.html')?[prefix+e.name]:[]);}
(async()=>{
 await ready;const browser=await chromium.launch({headless:true});const errors=[],resources=[];
 try{
  const context=await browser.newContext();
  await context.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error'&&/Content Security Policy|Refused to/.test(m.text()))errors.push(m.text());});
  page.on('response',r=>{if(r.status()>=400&&/\.(css|js|mjs)(\?|$)/.test(r.url()))resources.push(r.url());});
  const pages=htmlFiles(path.join(showcase,'showcase'),'showcase/');
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:1000});
   for(const file of pages){
    const response=await page.goto(base+'/'+file);assert.equal(response.status(),200);
    assert.equal(await page.locator('footer a[href="https://beian.miit.gov.cn/"]').count(),1);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),file+' overflow '+width);
   }
  }
  await page.setViewportSize({width:1440,height:1000});await page.goto(base+'/showcase/projects/community-payment/');
  assert.equal(await page.locator('a[href="/showcase/projects/community-payment/views/merchant/v1/"]').count(),1);
  await page.screenshot({path:process.env.XJ_SHOWCASE_REPORT_DIR+'/SHOWCASE_PROJECT_DESKTOP.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:process.env.XJ_SHOWCASE_REPORT_DIR+'/SHOWCASE_PROJECT_MOBILE.png',fullPage:true});
  await page.goto(base+'/showcase/projects/community-payment/views/merchant/v1/');
  for(const merchant of ['grocer','cafe','home']){await page.locator('#merchantSelect').selectOption(merchant);assert.match(await page.locator('#merchantIdentity').innerText(),/模拟商家/);assert.equal(await page.locator('#orderRows tr').count(),3);}
  await page.screenshot({path:process.env.XJ_SHOWCASE_REPORT_DIR+'/SHOWCASE_MERCHANT_MOBILE.png',fullPage:true});
  assert.deepEqual(errors,[]);assert.deepEqual(resources,[]);
  fs.writeFileSync(process.env.XJ_SHOWCASE_REPORT_DIR+'/SHOWCASE_BROWSER_REPORT.json',JSON.stringify({status:'PASS',scope:'Generated catalog and self-contained merchant on loopback fixture; not production HTTPS',pages:pages.length,viewports:[1440,390],project_navigation:'PASS',three_simulated_merchants:'PASS',js_errors:errors,failed_assets:resources,production_browser:'NOT_RUN'},null,2)+'\n');
 } finally{await browser.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);server.kill('SIGTERM');process.exitCode=1;});
