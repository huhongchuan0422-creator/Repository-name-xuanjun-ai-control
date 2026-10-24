import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import zlib from 'node:zlib';

function csvRows(text){
 const lines=text.trimEnd().split(/\r?\n/);
 const parse=line=>{const out=[];let s='',q=false;for(let i=0;i<line.length;i++){const c=line[i];if(q&&c==='"'&&line[i+1]==='"'){s+='"';i++;continue}if(c==='"'){q=!q;continue}if(c===','&&!q){out.push(s);s='';continue}s+=c}out.push(s);return out};
 const h=parse(lines[0]); return lines.slice(1).map(line=>Object.fromEntries(h.map((k,i)=>[k,parse(line)[i]])));
}
const csv=zlib.gunzipSync(fs.readFileSync(new URL('../spec/03_PAGE_TRACEABILITY.csv.gz',import.meta.url)));
const map=JSON.parse(zlib.gunzipSync(fs.readFileSync(new URL('../prototype-page-map.json.gz',import.meta.url))));
test('fixed traceability CSV hash and every one of 69 rows/26 fields matches source including owner_gap_task',()=>{
 assert.equal(crypto.createHash('sha256').update(csv).digest('hex'),'496624feab3ba3259e1e9bec78b07ecf1b54118b52a37ec2ed7aca7a13feb209');
 assert.equal(map.traceability_csv_sha256,'496624feab3ba3259e1e9bec78b07ecf1b54118b52a37ec2ed7aca7a13feb209');
 const rows=csvRows(csv.toString('utf8')); assert.equal(rows.length,69); assert.equal(map.pages.length,69); assert.deepEqual(map.fields,Object.keys(rows[0]));
 for(let i=0;i<69;i++){assert.deepEqual(map.pages[i],rows[i]);assert.ok(Object.hasOwn(map.pages[i],'owner_gap_task'))}
});
test('frozen mapping preserves HOLD/no-real-verified and exact key SaaS pages',()=>{
 assert.ok(map.pages.every(x=>x.real_verified==='NO'));
 for(const id of ['CUS-005','CUS-006','CUS-012','CUS-013','CUS-014']){const row=map.pages.find(x=>x.page_id===id);assert.ok(row);assert.equal(row.gate,'HOLD');assert.ok(row.owner_gap_task.startsWith('GAP-'))}
});
