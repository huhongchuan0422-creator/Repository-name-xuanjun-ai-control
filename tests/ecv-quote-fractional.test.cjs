'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const assets=path.join(__dirname,'../demos/xuanjun-site-hub/assets');
const {calculateQuote,TIERS}=require(path.join(assets,'ecv-quote.js'));
const quote=(ecvUnits,extra={})=>calculateQuote({listPriceCents:600000,creditCents:120000,ecvUnits,...extra});
test('all six thresholds compare exact decimal strings without rounding',()=>{
 let previous=100;
 for(const [minimum,rate] of TIERS){
  assert.equal(quote(`${minimum-1}.9999999999999999999999999999`).discountPercent,previous);
  for(const value of [String(minimum),`${minimum}.0000000000000000000001`,`${minimum}.5`])assert.equal(quote(value).discountPercent,rate);
  previous=rate;
 }
});
test('fractional gifts and leading zero decimals are accepted',()=>{
 for(const value of ['0.5',0.5,'1.5',1.5,1e-8,'0001.50'])assert.equal(quote(value).discountPercent,100);
 for(const value of ['2.5',2.5,'0002.50'])assert.equal(quote(value).discountPercent,90);
 assert.equal(quote('10.5').discountPercent,80);
 assert.equal(quote('150.5').cashDueCents,120000);
});
test('invalid holdings do not silently become zero or a valid tier',()=>{
 for(const value of ['', ' ', '-1','+2','2e1','0x20','Infinity','NaN','1.2.3','2.','.',null,undefined,true,[],{},-1,NaN,Infinity,Number.MAX_SAFE_INTEGER+1,'1'.repeat(4097)])assert.throws(()=>quote(value),RangeError);
});
test('amount arithmetic, ordinary cap, cost status and balance cap unchanged',()=>{
 const x=quote('150.5',{directCostCents:200000});
 assert.deepEqual([x.discountedCents,x.creditUsedCents,x.cashDueCents,x.grossProfitCents,x.referralAccrualStatus],[240000,120000,120000,-80000,'NO_POSITIVE_GROSS_PROFIT']);
 const ordinary=quote('150.5',{kind:'ordinary',creditCents:600000});
 assert.deepEqual([ordinary.discountPercent,ordinary.creditCapCents,ordinary.cashDueCents],[100,540000,60000]);
 assert.equal(quote('150.5',{creditCents:1}).creditUsedCents,1);
 assert.equal(quote('150.5').referralAccrualStatus,'COST_UNKNOWN');
});
function ui(lang,kind,ecvUnits){
 const elements={ecvQuote:{addEventListener(type,fn){this.submit=fn;}},quoteResult:{textContent:''},ecvUnits:{value:ecvUnits,step:'1'},listPrice:{value:'6000'},credit:{value:'1200'},serviceKind:{value:kind}};
 const context={document:{documentElement:{lang},getElementById:id=>elements[id]},calculateQuote};
 vm.runInNewContext(fs.readFileSync(path.join(assets,'ecv-quote-ui.js'),'utf8'),context);
 elements.ecvQuote.submit({preventDefault(){}});
 return elements;
}
test('UI preserves exact decimal input and removes browser integer step gate',()=>{
 const x=ui('zh-CN','custom','149.999999999999999999');
 assert.equal(x.ecvUnits.step,'any');
 assert.match(x.quoteResult.textContent,/开发折扣：5折/);
 assert.match(ui('zh-CN','custom','150.5').quoteResult.textContent,/开发折扣：4折/);
});
test('ordinary service labels are distinct in both languages',()=>{
 const zh=ui('zh-CN','ordinary','2.5').quoteResult.textContent;
 assert.match(zh,/合格自营服务费：¥6000.00/);assert.match(zh,/上限90%/);assert.doesNotMatch(zh,/开发折扣|折后开发费/);
 const en=ui('en','ordinary','2.5').quoteResult.textContent;
 assert.match(en,/Eligible in-house service fee: CNY 6000.00/);assert.match(en,/cap 90%/);assert.doesNotMatch(en,/development|discounted/);
 assert.match(ui('en','custom','150.5').quoteResult.textContent,/discounted development fee: CNY 2400.00/);
});
test('UI errors explain fractional points and never promise integer-only rights',()=>{
 const zh=ui('zh-CN','custom','-1').quoteResult.textContent;
 assert.match(zh,/10.5点权益值/);assert.doesNotMatch(zh,/整数份/);
 assert.match(ui('en','custom','NaN').quoteResult.textContent,/decimals allowed/);
});
