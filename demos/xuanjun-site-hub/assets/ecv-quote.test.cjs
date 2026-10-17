"use strict";
const assert=require("node:assert/strict");
const {calculateQuote}=require("./ecv-quote.js");
const custom=calculateQuote({listPriceCents:600000,ecvUnits:150,creditCents:500000,directCostCents:200000});
assert.deepEqual([custom.discountPercent,custom.discountedCents,custom.creditCapCents,custom.creditUsedCents,custom.cashDueCents,custom.grossProfitCents,custom.referralAccrualStatus],[40,240000,120000,120000,120000,-80000,"NO_POSITIVE_GROSS_PROFIT"]);
assert.equal(calculateQuote({listPriceCents:10000,ecvUnits:150,creditCents:10000,kind:"ordinary"}).cashDueCents,1000);
assert.equal(calculateQuote({listPriceCents:10000,ecvUnits:150,creditCents:10}).creditUsedCents,10);
assert.equal(calculateQuote({listPriceCents:10000,ecvUnits:1,creditCents:0}).discountPercent,100);
assert.equal(calculateQuote({listPriceCents:10000,ecvUnits:2,creditCents:0}).discountPercent,90);
assert.equal(calculateQuote({listPriceCents:10000,ecvUnits:149,creditCents:0}).discountPercent,50);
assert.equal(calculateQuote({listPriceCents:10000,ecvUnits:150,creditCents:0}).discountPercent,40);
assert.equal(calculateQuote({listPriceCents:10000,ecvUnits:0,creditCents:0}).referralAccrualStatus,"COST_UNKNOWN");
for(const bad of [-1,NaN,Infinity,1.5])assert.throws(()=>calculateQuote({listPriceCents:bad,ecvUnits:0,creditCents:0}),RangeError);
assert.equal(calculateQuote({listPriceCents:Number.MAX_SAFE_INTEGER,ecvUnits:2,creditCents:0}).discountedCents,8106479329266892);
assert.equal(calculateQuote({listPriceCents:Number.MAX_SAFE_INTEGER,ecvUnits:150,creditCents:Number.MAX_SAFE_INTEGER,kind:'ordinary'}).creditCapCents,8106479329266891);
assert.equal(calculateQuote({listPriceCents:101,ecvUnits:2,creditCents:999}).cashDueCents,46);
assert.equal(calculateQuote({listPriceCents:100,ecvUnits:1.5,creditCents:0}).discountPercent,100);
console.log("ECV_QUOTE_REGRESSION_PASS: 16 assertions/groups (offline only)");

