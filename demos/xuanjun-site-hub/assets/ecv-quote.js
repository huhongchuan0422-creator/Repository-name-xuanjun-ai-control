"use strict";
const TIERS=[[2,90],[10,80],[20,70],[40,60],[80,50],[150,40]];
function int(value,name){if(!Number.isSafeInteger(value)||value<0)throw new RangeError(name+" must be a nonnegative safe integer");return value;}
function calculateQuote({listPriceCents,ecvUnits,creditCents,directCostCents=null,kind="custom"}){
 int(listPriceCents,"listPriceCents");int(ecvUnits,"ecvUnits");int(creditCents,"creditCents");
 if(directCostCents!==null)int(directCostCents,"directCostCents");
 if(!["custom","ordinary"].includes(kind))throw new RangeError("unknown service kind");
 let pct=100;
 if(kind==="custom")for(const [minimum,rate] of TIERS)if(ecvUnits>=minimum)pct=rate;
 const discounted=Number((BigInt(listPriceCents)*BigInt(pct)+50n)/100n);
 const cap=Number(BigInt(discounted)*BigInt(kind==="custom"?50:90)/100n);
 const deducted=Math.min(cap,creditCents);
 const cash=discounted-deducted;
 // This is an offline quote projection, not an authoritative Finance commission settlement.
 const grossProfit=directCostCents===null?null:cash-directCostCents;
 return {kind,discountPercent:pct,discountedCents:discounted,creditCapCents:cap,creditUsedCents:deducted,cashDueCents:cash,thirdPartyCostExcluded:true,grossProfitCents:grossProfit,referralAccrualStatus:grossProfit===null?"COST_UNKNOWN":grossProfit<=0?"NO_POSITIVE_GROSS_PROFIT":"FINANCE_SETTLEMENT_REQUIRED"};
}
if(typeof module!=="undefined")module.exports={calculateQuote,TIERS};
