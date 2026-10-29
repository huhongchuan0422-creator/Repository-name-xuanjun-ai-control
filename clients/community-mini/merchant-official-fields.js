'use strict';
const areas=require('./merchant-official-areas.json'),industries=require('./merchant-official-industries.json');
function industriesFor(entity){return industries.rows.filter(x=>x.subject===entity);}
function selectedIndustry(entity,profile){const info=profile&&profile.settlement_info||{};return industriesFor(entity).find(x=>x.settlement_id===info.settlement_id&&x.qualification_type===info.qualification_type)||null;}
function regionColumns(indices=[0,0,0]){
 const provinces=[...new Set(areas.rows.map(x=>x[1]))];let p=Number.isInteger(indices[0])?Math.max(0,Math.min(provinces.length-1,indices[0])):0;
 const cities=[...new Set(areas.rows.filter(x=>x[1]===provinces[p]).map(x=>x[2]))];let c=Number.isInteger(indices[1])?Math.max(0,Math.min(cities.length-1,indices[1])):0;
 const rows=areas.rows.filter(x=>x[1]===provinces[p]&&x[2]===cities[c]);let d=Number.isInteger(indices[2])?Math.max(0,Math.min(rows.length-1,indices[2])):0;
 return {columns:[provinces,cities,rows.map(x=>x[3])],indices:[p,c,d],row:rows[d]};
}
function regionForCode(code){const row=areas.rows.find(x=>x[0]===code);if(!row)return null;const a=regionColumns();const p=a.columns[0].indexOf(row[1]),b=regionColumns([p,0,0]),c=b.columns[1].indexOf(row[2]),z=regionColumns([p,c,0]),d=z.columns[2].indexOf(row[3]);return regionColumns([p,c,d]);}
module.exports={industriesFor,selectedIndustry,regionColumns,regionForCode};
