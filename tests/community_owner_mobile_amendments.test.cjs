'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');

test('consumer orders use one horizontal status strip and list rows',()=>{
 const markup=fs.readFileSync(path.join(root,'clients/community-mini/pages/checkout/index.wxml'),'utf8');
 const css=fs.readFileSync(path.join(root,'clients/community-mini/pages/checkout/index.wxss'),'utf8');
 const orders=markup.split("viewMode==='orders'")[1].split("viewMode==='services'")[0];
 assert.match(orders,/class="order-filter-strip"/);
 assert.match(orders,/class="filter-pills-row"/);
 assert.match(orders,/class="order-list-item"/);
 assert.doesNotMatch(orders,/class="order-row"/);
 assert.match(css,/\.filter-pills-row\{display:inline-flex/);
 assert.match(css,/\.filter-pills-row button\{[^}]*flex:0 0 auto;[^}]*width:auto/);
 assert.match(css,/\.order-list-main,\.order-list-footer\{display:flex/);
});

test('mobile admin drawer is a single column and keeps role switcher available',()=>{
 const css=fs.readFileSync(path.join(root,'demos/community-stage/admin-shell.css'),'utf8');
 assert.match(css,/\.admin-navigation-disclosure>#admin-sections\{display:grid;grid-template-columns:minmax\(0,1fr\);grid-auto-flow:row/);
 assert.match(css,/\.admin-navigation-disclosure #admin-sections \.admin-nav-group\{grid-column:1\/-1;width:100%;min-width:0\}/);
 assert.match(css,/\.admin-logged-in \.admin-session-tools label\{display:flex\}/);
 assert.doesNotMatch(css,/@media\(max-width:760px\)\{[^}]*\.admin-session-tools label,\.admin-logged-in \.admin-role-badge\{display:none\}/);
});

test('dashboard waits for authenticated context and clears every secondary highlight',()=>{
 const source=fs.readFileSync(path.join(root,'demos/community-stage/admin-shell.js'),'utf8');
 assert.match(source,/function applyWorkspaceRoute\(\)\{\s*if\(!homeContext\)return;/);
 assert.match(source,/orderSettlementNav\.removeAttribute\('aria-current'\);snapshotNav\.removeAttribute\('aria-current'\);refundNav\.removeAttribute\('aria-current'\);/);
 assert.match(source,/function merchantReviewAllowed\(\)\{return !!homeContext\?\.reviewer;\}/);
});

test('owner list filters and embedded pages have delivery-grade shells',()=>{
 const shell=fs.readFileSync(path.join(root,'demos/community-stage/admin-shell.js'),'utf8');
 const workbench=fs.readFileSync(path.join(root,'demos/community-stage/workbench.js'),'utf8');
 const workbenchCss=fs.readFileSync(path.join(root,'demos/community-stage/workbench.css'),'utf8');
 assert.match(shell,/reportQuery\.append\(reportKeywordLabel,reportStatusLabel,reportStartLabel,reportEndLabel,reportSearch,\.\.\.originalReportActions\)/);
 assert.doesNotMatch(shell,/reportReset/);
 assert.match(shell,/operationFilterButton\.textContent='查询'/);
 for(const label of ['用户编号','用户名称','用户类型','消费金额','积分余额','关联订单','推荐人','状态','操作'])assert.match(shell,new RegExp("'"+label+"'"));
 assert.match(shell,/workspaceRouteNavigation\.set\('platform-customers',userListNav\)/);
 assert.match(shell,/merchantWorkbenchHeading\.hidden=true/);
 assert.match(workbench,/embeddedNotice\.hidden=true/);
 assert.match(workbench,/message==='当前操作不可用，请联系管理员核对账号权限。'/);
 assert.match(workbenchCss,/\.embedded-workbench>main>header/);
});
