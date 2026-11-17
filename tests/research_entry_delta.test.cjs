'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const code=fs.readFileSync('demos/task-center-digital-twin/task-center.js','utf8');
async function check(session,expected){
 const els={researchEntry:{hidden:true},reload:{},logout:{},dataMode:{},app:{}};
 const calls=[]; const fetch=(url,opts)=>{calls.push([url,opts]);return Promise.resolve(url==='api/session'?session:{ok:true,json:()=>Promise.resolve({mode:'TEST_ONLY',boards:[]})});};
 vm.runInNewContext(code,{document:{getElementById:id=>els[id],cookie:''},fetch,location:{},Error,Array,String,decodeURIComponent});
 await new Promise(resolve=>setImmediate(resolve));
 assert.strictEqual(els.researchEntry.hidden,!expected);assert.strictEqual(calls[0][0],'api/session');assert.strictEqual(calls[0][1].credentials,'same-origin');
}
(async()=>{await check({ok:true,json:()=>Promise.resolve({roles:['TASK_CENTER_ADMIN']})},true);await check({ok:true,json:()=>Promise.resolve({roles:['TASK_EXECUTOR']})},false);await check({ok:false},false);console.log('entry role checks passed');})().catch(e=>{console.error(e);process.exitCode=1;});
