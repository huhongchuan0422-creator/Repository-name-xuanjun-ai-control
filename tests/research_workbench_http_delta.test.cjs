'use strict';
const assert=require('assert'),vm=require('vm'),fs=require('fs');
const workbench=require('../demos/task-center-digital-twin/research-workbench/workbench.js');
const app={innerHTML:'',addEventListener(){},contains(){return true;}};let updates=[];
const window={XuanjunResearchWorkbench:{mount(el,opts){const m=workbench.mount(el,opts);return {update(d,t,l){updates.push([d,t,l]);m.update(d,t,l);}};}},XuanjunPublicProjection:{mount(){return {refresh(){}};}}};
const document={baseURI:process.argv[2]+'research-workbench/',getElementById(id){return id==='app'?app:{};}};
const requests=[];
function fetchTracked(url,opts){return fetch(url,opts).then(r=>{requests.push([url,r.status]);return r;});}
vm.runInNewContext(fs.readFileSync('demos/task-center-digital-twin/research-workbench/preview.js','utf8'),{window,document,URL,Promise,fetch:fetchTracked});
(async()=>{await new Promise((resolve,reject)=>{let n=0;let timer=setInterval(()=>{if(updates.length>=2){clearInterval(timer);resolve();}else if(++n>100){clearInterval(timer);reject(Error('timeout'));}},20);});assert.equal(requests.find(r=>r[0].endsWith('/api/projection'))[1],200);assert.equal(requests.find(r=>r[0].endsWith('/api/admin/digital-twin'))[1],403);assert.equal(requests.find(r=>r[0].endsWith('/api/admin/delivery-ledger'))[1],403);assert.equal(updates.at(-1)[0].mode,'TEST_ONLY');assert.equal(updates.at(-1)[0].tenant_id,'tenant-fixture');assert.equal(updates.at(-1)[1],null);assert(!app.innerHTML.includes('已授权只读数据未接入'));console.log('real HTTP preview chain passed');})().catch(e=>{console.error(e);process.exitCode=1;});
