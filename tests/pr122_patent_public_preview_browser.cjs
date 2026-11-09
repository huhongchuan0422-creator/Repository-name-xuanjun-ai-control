// Actual Chromium compatibility test with the observed, unchanged site policy.
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const candidate=path.resolve(process.argv[2]),original=path.resolve('demos/pr122-patent-preview/original');
const observed=JSON.parse(fs.readFileSync(path.join(candidate,'OBSERVED_SITE_POLICY.json')));
const stages=['overview','materials','search','compare','ideas','documents','review','filing','response','deadlines','blueprint','models','cnipa'];
const props=['margin-top','font-size','color','text-align','width'];
let server,browser;
(async()=>{
 server=http.createServer((req,res)=>{let relative=decodeURIComponent(new URL(req.url,'http://fixture').pathname);const baseline=relative.startsWith('/baseline/');const strictOriginal=relative.startsWith('/strict-original/');
  const root=baseline||strictOriginal?original:path.join(candidate,'public/labs/patent-20261109');
  relative=relative.replace(/^\/(baseline|strict-original|candidate)\//,'')||'index.html';
  if(relative.includes('..')||!['index.html','app.js','style.css','preview.html'].includes(relative)){res.writeHead(404);res.end();return;}
  const file=path.join(root,relative);if(!fs.existsSync(file)){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',relative.endsWith('.js')?'application/javascript':relative.endsWith('.css')?'text/css':'text/html; charset=utf-8');
  if(!baseline){res.setHeader('Content-Security-Policy',observed.csp);res.setHeader('X-Frame-Options',observed.x_frame_options);}
  res.end(fs.readFileSync(file));
 });await new Promise(resolve=>server.listen(process.argv[3]==='--serve-only'?4173:0,'0.0.0.0',resolve));
 if(process.argv[3]==='--serve-only'){console.log('PATENT_CSP_FIXTURE_READY_PORT_4173');await new Promise(()=>{});}
 const origin='http://127.0.0.1:'+server.address().port;
 browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox']});
 const result={scope:'ISOLATED_CHROMIUM_NOT_PRODUCTION',observed_policy_unchanged:true,routes:[],external_requests:[],errors:[]};
 for(const width of [1440,390]){
  const context=await browser.newContext({viewport:{width,height:900}});const before=await context.newPage(),after=await context.newPage();
  after.on('pageerror',error=>result.errors.push(String(error)));after.on('console',message=>{if(message.type()==='error'&&/Content Security Policy|Refused to/.test(message.text()))result.errors.push(message.text());});
  after.on('request',request=>{if(!request.url().startsWith(origin))result.external_requests.push(request.url());});
  for(const stage of stages){
   await before.goto(origin+'/baseline/index.html#'+stage);await after.goto(origin+'/candidate/index.html#'+stage);
   await before.locator('#main h1').waitFor();await after.locator('#main h1').waitFor();
   assert.equal(await after.locator('#main').innerText(),await before.locator('#main').innerText(),stage+' business text');
   const collect=async(page,selector)=>page.locator(selector).evaluateAll((nodes,props)=>nodes.map(node=>({tag:node.tagName,values:props.map(key=>getComputedStyle(node).getPropertyValue(key))})),props);
   assert.deepEqual(await collect(after,'[class*="xj-patent-inline-"]'),await collect(before,'[style]'),stage+' exact computed styles at '+width);
   result.routes.push({width,stage,business_text:'IDENTICAL',computed_styles:'IDENTICAL'});
  }
  await after.locator('#review-open').click();await after.locator('#review-text').fill('仅隔离测试的原型意见');await after.locator('#review-save').click();await after.reload();await after.locator('#review-open').click();assert.equal(await after.locator('#review-text').inputValue(),'仅隔离测试的原型意见');
  await context.close();
 }
 assert.deepEqual(result.errors,[]);assert.deepEqual(result.external_requests,[]);
 result.prototype_notes='BROWSER_LOCAL_ONLY_NOT_BACKEND_COMMENTS';result.status='PASS';
 fs.writeFileSync(path.join(candidate,'CHROMIUM_COMPATIBILITY.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({status:'PASS',rendered_states:result.routes.length,viewports:[1440,390],external_requests:0,csp_violations:0,production_changes:0}));
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)await new Promise(resolve=>server.close(resolve));});
