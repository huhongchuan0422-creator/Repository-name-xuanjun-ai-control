'use strict';
const assert=require('assert'),fs=require('fs'),vm=require('vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const ui=require('../demos/task-center-digital-twin/research-workbench/workbench.js');
let refresh,updates=[],fail=false;
const app={innerHTML:'',addEventListener(){},contains(){return true;}};
const window={XuanjunResearchWorkbench:{mount(el,opts){refresh=opts.onRefresh;const mounted=ui.mount(el,opts);return {update(...args){updates.push(args);mounted.update(...args);}};}},XuanjunPublicProjection:{mount(){return {refresh(){}};}}};
const context={window,document:{baseURI:'http://localhost/task-center-test/research-workbench/',getElementById(id){return id==='app'?app:{};}},URL,Promise,fetch(url){let k=url.endsWith('/projection')?'projection':url.endsWith('/digital-twin')?'twin':'ledger';return Promise.resolve({ok:!(fail&&k==='ledger')&&(k!=='twin'||input.twinStatus===200),json:()=>Promise.resolve(input[k])});}};
(async()=>{vm.runInNewContext(fs.readFileSync('demos/task-center-digital-twin/research-workbench/preview.js','utf8'),context);await new Promise(r=>setImmediate(r));assert.strictEqual(updates.at(-1)[2],input.ledger);assert.match(app.innerHTML,/现时权限 UNKNOWN/);assert.match(app.innerHTML,/历史开发交接/);fail=true;await refresh();assert.strictEqual(updates.at(-1)[2],null);assert.doesNotMatch(app.innerHTML,/历史开发交接/);assert.match(app.innerHTML,/无权查看/);})().catch(e=>{console.error(e.message);process.exitCode=1;});
