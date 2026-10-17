'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const script=fs.readFileSync(require('path').join(__dirname,'../demos/work-community-experience/role.js'),'utf8');
function run(search){
 const paths=['/visual/community-payment/','/marketplace/','/visual/community-payment/mobile/platform.html','https://evil.test/visual/community-payment/','#home','/visual/legal/privacy.html'];
 paths.splice(2,0,'http://[invalid');
 const anchors=paths.map(href=>({href,getAttribute(){return this.href},setAttribute(k,v){this.href=v}}));
 const location={search,href:'https://example.test/visual/community-payment/mobile/community.html'+search,origin:'https://example.test'};
 vm.runInNewContext(script,{URL,URLSearchParams,location,document:{body:{dataset:{previewRole:'community'},classList:{toggle(){}}},querySelectorAll(){return anchors}}});
 assert.equal(anchors[2].href,'http://[invalid');
 return anchors.filter((_,i)=>i!==2).map(a=>a.href);
}
assert.deepEqual(run('?lang=en&return=https://evil.test'),['/en/visual/community-payment/','/en/marketplace/','/visual/community-payment/mobile/platform.html?lang=en','https://evil.test/visual/community-payment/','#home','/visual/legal/privacy.html']);
assert.equal(run('?lang=zh-cn')[0],'/zh-cn/visual/community-payment/');
for(const query of ['','?lang=EN','?lang=//evil.test','?lang=%22%3E%3Cscript%3E','?return=https://evil.test'])assert.equal(run(query)[0],'/visual/community-payment/');
console.log('Role language navigation: whitelist, external links, fragments and malicious return cases passed');
