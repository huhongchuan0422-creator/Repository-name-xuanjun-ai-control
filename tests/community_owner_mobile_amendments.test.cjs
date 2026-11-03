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
