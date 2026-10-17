'use strict';
/* Hosted-only browser regression: generated full-shell fixture, never production.
 * From repository root, after building XJ_HUB_STAGE with --browser-fixture:
 * XJ_HUB_STAGE=/tmp/hub-stage XJ_ECOLOGY_REPORT=/tmp/ecology-report \
 *   node tests/pr122_ecology_browser.cjs
 * Requires Playwright/Chromium and the existing pr122_site_hub_test_server.py.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const stage = path.resolve(process.env.XJ_HUB_STAGE || '');
assert(process.env.XJ_HUB_STAGE, 'Set XJ_HUB_STAGE to a generated Hosted fixture');
const manifest = JSON.parse(fs.readFileSync(path.join(stage, 'MANIFEST.json'), 'utf8'));
assert.equal(manifest.status, 'HOSTED_BROWSER_FIXTURE_ONLY', 'Only synthetic Hosted fixtures are accepted');
assert.equal(manifest.production_approved, false);
const reportDir = path.resolve(process.env.XJ_ECOLOGY_REPORT || 'ecology-browser-report');
fs.mkdirSync(reportDir, {recursive:true});
const widths = [320, 390, 1440];
const pages = ['ecosystem/', 'ecosystem/tiers/', 'ecosystem/profit-sharing/', 'ecosystem/activities/', 'ecosystem/ledger/', 'ecosystem/co-create/', 'customer/projects/'];
const results = [], errors = [], resources = [], blockedWrites = [], screenshots = [];
let server, browser;
function ready(child) {
  return new Promise((resolve, reject) => {
    let output = '', stderr = '';
    const timer = setTimeout(() => reject(Error('Loopback fixture startup timed out: '+stderr)), 20000);
    child.stderr.on('data', b => { stderr += b; });
    child.once('error', e => {clearTimeout(timer); reject(e);});
    child.once('exit', code => {clearTimeout(timer); reject(Error('Fixture exited '+code+': '+stderr));});
    child.stdout.on('data', b => {
      output += b;
      if (!output.includes('\n')) return;
      try {
        const state = JSON.parse(output.split('\n')[0]);
        assert.equal(state.status, 'LOOPBACK_TEST_ONLY');
        assert(Number.isInteger(state.port) && state.port > 0);
        clearTimeout(timer); resolve(state.port);
      } catch(e) {clearTimeout(timer); reject(e);}
    });
  });
}
async function rows(table) {
  return table.locator('tbody tr').evaluateAll(nodes => nodes.map(tr => [...tr.querySelectorAll('td')].map(td => td.textContent.trim())));
}
(async () => {
  server = spawn('python3', ['scripts/pr122_site_hub_test_server.py', '--stage', stage, '--port', '0'], {stdio:['ignore','pipe','pipe']});
  const base = 'http://127.0.0.1:' + await ready(server);
  browser = await chromium.launch({headless:true});
  const context = await browser.newContext({serviceWorkers:'block'});
  await context.route('**/*', route => {
    const req = route.request();
    if (new URL(req.url()).origin !== base) return route.abort();
    if (!['GET','HEAD'].includes(req.method())) {blockedWrites.push(req.method()+' '+req.url()); return route.abort();}
    return route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', e => errors.push(e.message));
  page.on('response', r => {if(r.url().startsWith(base) && r.status() >= 400 && /\.(css|js|mjs)(\?|$)/.test(r.url())) resources.push(r.url());});
  page.on('console', m => {if(m.type()==='error' && /Content Security Policy|Refused to/.test(m.text())) errors.push(m.text());});
  for (const width of widths) {
    await page.setViewportSize({width, height:1000});
    for (const locale of ['', 'zh-cn/', 'en/']) {
      const en = locale === 'en/';
      for (const relative of pages) {
        const url = base+'/'+locale+relative;
        const response = await page.goto(url);
        assert.equal(response.status(), 200, url);
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1 && document.body.scrollWidth <= innerWidth+1), 'Body overflow: '+url+' @'+width);
        const tables = page.locator('main table');
        for (const table of await tables.all()) {
          const geometry = await table.evaluate(t => {
            const wrap = t.parentElement, cs = getComputedStyle(wrap);
            return {display:getComputedStyle(t).display, wrapper:wrap.classList.contains('xj-table-scroll'), overflow:cs.overflowX, client:wrap.clientWidth, scroll:wrap.scrollWidth, table:t.getBoundingClientRect().width, header:t.querySelector('thead').getBoundingClientRect().width, caption:t.querySelector('caption').getBoundingClientRect().width, keyboard:wrap.tabIndex};
          });
          assert.equal(geometry.display, 'table', 'Semantic table layout: '+url);
          assert(geometry.wrapper && ['auto','scroll'].includes(geometry.overflow), 'Independent scroll wrapper: '+url);
          assert.equal(geometry.keyboard, 0, 'Table scroll region must be keyboard reachable');
          assert(geometry.header >= geometry.table-2 && geometry.caption >= geometry.table-2, 'Columns/caption must fill table: '+url);
          if (width <= 390) {
            assert(geometry.scroll > geometry.client, 'Mobile table should scroll inside wrapper: '+url);
            const moved = await table.evaluate(t => {const w=t.parentElement; w.scrollLeft=w.scrollWidth; const x=w.scrollLeft; w.scrollLeft=0; return x;});
            assert(moved > 0, 'Scroll region not operable: '+url);
          }
        }
        if (['ecosystem/', 'ecosystem/tiers/'].includes(relative)) {
          const values = [2,10,20,40,80,150];
          assert.deepEqual(await rows(tables.nth(0)), values.map((n,i) => [en?`≥ ${n} rights-value points`:`≥ ${n}点权益值`, en?`${90-i*10}% of quoted fee`:`${9-i}折`]));
          assert.equal(await tables.nth(1).locator('tbody tr').count(),3);
          const caps = await rows(tables.nth(1));
          assert.deepEqual(caps.map(r=>r[2]), ['90%','50%',en?'Not eligible':'不可抵扣']);
        }
        if (relative === 'ecosystem/profit-sharing/') {
          assert.deepEqual(await rows(tables.nth(0)), Array.from({length:8},(_,i)=>{const n=i+1; return [en?`≥ CNY ${n},000`:`≥ ${n},000元`, en?`≥ ${n*10} rights-value points`:`≥ ${n*10}点权益值`, `${n*10}%`];}));
          const main = await page.locator('main').innerText();
          assert(main.includes(en?'thresholds are both met':'两项条件共同满足'), 'Both eligibility thresholds must be explicit');
          assert(main.includes(en?'No fixed return is promised':'不承诺固定收益'));
        }
        if (relative.startsWith('ecosystem/')) {
          const expected = ['tiers/','profit-sharing/','activities/','co-create/'].map(s => '/'+locale+'ecosystem/'+s);
          assert.deepEqual(await page.locator('main .actions a').evaluateAll(as=>as.map(a=>a.getAttribute('href'))), expected, 'Localized ecology links: '+url);
        }
        if (relative === 'customer/projects/') {
          const cta = page.getByRole('link',{name:en?'Explore custom services':'了解定制服务',exact:true});
          assert.equal(await cta.getAttribute('href'), '/'+locale+'custom-ai', 'Custom-services CTA target');
          const [navigation] = await Promise.all([page.waitForNavigation(), cta.click()]);
          assert.equal(new URL(page.url()).pathname.replace(/\/$/,''), '/'+locale+'custom-ai');
          assert.equal(navigation.status(),200);
          assert.equal(await page.locator('main[data-fixture="custom-ai-navigation"] h1').innerText(), 'Synthetic Hosted navigation fixture');
          await page.goto(url);
        }
        if (relative === 'ecosystem/tiers/' || relative === 'ecosystem/profit-sharing/') {
          const file = `ECOLOGY_${locale.replace('/','')||'root'}_${relative.split('/')[1]}_${width}.png`;
          await page.screenshot({path:path.join(reportDir,file),fullPage:true}); screenshots.push(file);
        }
        results.push({locale:locale||'root',page:relative,width,status:'PASS'});
      }
    }
    // Exercise actual language controls, not only href strings.
    await page.goto(base+'/ecosystem/tiers/');
    await page.locator('.language>button').click();
    await page.locator('.language-panel a[lang="en"]').click();
    await page.waitForURL(base+'/en/ecosystem/tiers/');
    assert.equal(await page.locator('html').getAttribute('lang'),'en');
    await page.locator('.language>button').click();
    await page.locator('.language-panel a[lang="zh-CN"]').click();
    await page.waitForURL(base+'/zh-cn/ecosystem/tiers/');
  }
  assert.deepEqual(errors, []); assert.deepEqual(resources, []); assert.deepEqual(blockedWrites, []);
  fs.writeFileSync(path.join(reportDir,'ECOLOGY_BROWSER_REPORT.json'), JSON.stringify({status:'PASS',scope:'Generated Hosted fixture on isolated loopback only',production_browser:'NOT_RUN',viewports:widths,results,screenshots,errors,failed_assets:resources,blocked_writes:blockedWrites},null,2)+'\n');
})().catch(e => {
  fs.writeFileSync(path.join(reportDir,'ECOLOGY_BROWSER_REPORT.json'), JSON.stringify({status:'FAIL',error:e.stack,results,screenshots,errors,failed_assets:resources,blocked_writes:blockedWrites,production_browser:'NOT_RUN'},null,2)+'\n');
  console.error(e); process.exitCode=1;
}).finally(async()=>{if(browser) await browser.close(); if(server) server.kill('SIGTERM');});
