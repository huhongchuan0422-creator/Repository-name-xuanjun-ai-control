'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const script=fs.readFileSync(__dirname+'/pages/merchant-join/index.js','utf8');
const context={require:path=>{if(path==='../../session')return {};if(path==='../../customer-auth')return {};throw Error('unused dependency');},Page(){}};
vm.createContext(context);vm.runInContext(script,context);
const prepare=context.prepareMerchantImage;
function fixture(options={}){
 const source='original.jpg',sizes={[source]:options.size||12000000},calls=[];let valid=true,index=0;
 const api={getFileSystemManager(){return {stat(o){calls.push(['stat',o.path]);if(options.statFailure)return o.fail({});o.success({stats:{size:sizes[o.path]}});},readFile(o){calls.push(['read',o.filePath]);if(options.readFailure)return o.fail({});if(options.invalidateRead)valid=false;o.success({data:options.badBase64?'?':Buffer.alloc(sizes[o.filePath]+(options.drift?1:0)).toString('base64')});}};},getImageInfo(o){calls.push(['info',o.src]);o.success(options.dimensions||{width:4000,height:3000});},compressImage(o){calls.push(['compress',o.src,o.quality,o.compressedWidth,o.compressedHeight]);if(options.invalidateCompression)valid=false;if(options.compressionFailure)return o.fail({});if(options.samePath)return o.success({tempFilePath:source});const path='compressed-'+index;const list=options.outputs||[900000];sizes[path]=list[Math.min(index++,list.length-1)];o.success({tempFilePath:path});}};
 if(options.noCompress)delete api.compressImage;if(options.noInfo)delete api.getImageInfo;
 return {api,source,calls,sizes,current:()=>valid,run:()=>prepare(api,source,()=>valid,x=>calls.push(['progress',x]))};
}
test('12MB original uses stat/compression before any base64 read and retains original',async()=>{const f=fixture();const r=await f.run();assert.equal(r.size,900000);assert.equal(r.originalPath,f.source);assert.equal(f.sizes[f.source],12000000);assert.deepEqual(f.calls.filter(x=>x[0]==='read'),[['read','compressed-0']]);assert.equal(r.targetReached,true);});
test('no original business-size ceiling: 80MB metadata enters compression',async()=>{const f=fixture({size:80000000});assert.equal((await f.run()).size,900000);});
test('already small source is not recompressed',async()=>{const f=fixture({size:700000});const r=await f.run();assert.equal(r.path,f.source);assert.equal(f.calls.some(x=>x[0]==='compress'),false);});
test('1MB target is not a 1MB admission gate',async()=>{const f=fixture({size:2000000,outputs:[1500000],dimensions:{width:1600,height:1200}});const r=await f.run();assert.equal(r.size,1500000);assert.equal(r.targetReached,false);assert.equal(f.calls.filter(x=>x[0]==='compress').length,3);});
test('exact 5MB save boundary remains admitted if compression is unavailable',async()=>{const f=fixture({size:5000000,noCompress:true});assert.equal((await f.run()).size,5000000);});
test('5MB plus one never enters readFile when no smaller output exists',async()=>{const f=fixture({size:5000001,compressionFailure:true});await assert.rejects(f.run(),/IMAGE_SAVE_LIMIT/);assert.equal(f.calls.some(x=>x[0]==='read'),false);});
test('compression unavailable above boundary gives explicit processing failure',async()=>{const f=fixture({noCompress:true});await assert.rejects(f.run(),/IMAGE_COMPRESSION_FAILED/);});
test('all compression rounds originate at original, never previous lossy output',async()=>{const f=fixture({outputs:[5000000,4000000,3000000,1500000,950000]});const r=await f.run();assert.equal(r.size,950000);const rounds=f.calls.filter(x=>x[0]==='compress');assert.equal(rounds.length,5);assert.ok(rounds.every(x=>x[1]===f.source));assert.deepEqual(rounds.slice(0,3).map(x=>x[2]),[90,80,70]);assert.ok(rounds.slice(3).every(x=>Math.min(x[3],x[4])>=1600));});
test('larger compression output never replaces a smaller original',async()=>{const f=fixture({size:1600000,outputs:[2000000],dimensions:{width:1000,height:1000}});assert.equal((await f.run()).path,f.source);});
test('compression errors below save limit preserve valid original',async()=>{const f=fixture({size:2000000,compressionFailure:true});assert.equal((await f.run()).path,f.source);});
test('PNG no-op above save limit is rejected explicitly, not falsely called compressed',async()=>{const f=fixture({outputs:[12000000]});await assert.rejects(f.run(),/IMAGE_SAVE_LIMIT/);assert.equal(f.calls.some(x=>x[0]==='read'),false);});
test('compressImage returning original path is not treated as a new safe image',async()=>{const f=fixture({samePath:true});await assert.rejects(f.run(),/IMAGE_SAVE_LIMIT/);});
test('revocation during compression does not read or upload content',async()=>{const f=fixture({invalidateCompression:true});await assert.rejects(f.run(),/IMAGE_CANCELLED/);assert.equal(f.calls.some(x=>x[0]==='read'),false);});
test('revocation during file read discards completed data',async()=>{const f=fixture({invalidateRead:true});await assert.rejects(f.run(),/IMAGE_CANCELLED/);});
test('stat failure is explicit and does not start compression',async()=>{const f=fixture({statFailure:true});await assert.rejects(f.run(),/IMAGE_INFO_FAILED/);assert.equal(f.calls.some(x=>x[0]==='compress'),false);});
test('file changes after stat cannot bypass saved-file identity/size check',async()=>{const f=fixture({drift:true});await assert.rejects(f.run(),/IMAGE_FILE_CHANGED/);});
test('base64 read failure does not turn into a request',async()=>{const f=fixture({readFailure:true});await assert.rejects(f.run(),/IMAGE_READ_FAILED/);});
test('malformed base64 rejected',async()=>{const f=fixture({badBase64:true});await assert.rejects(f.run(),/IMAGE_READ_FAILED/);});
test('wx.getFileInfo fallback remains supported without reading source bytes',async()=>{const f=fixture();const original=f.api.getFileSystemManager;f.api.getFileSystemManager=()=>{const manager=original();delete manager.stat;return manager;};f.api.getFileInfo=o=>o.success({size:f.sizes[o.filePath]});assert.equal((await f.run()).size,900000);});
test('page still restricts automatic OCR to original document types',()=>{assert.match(script,/const ocrKind=kind==='business_license'\?'business_license':kind==='identity_front'\?'id_front':kind==='identity_back'\?'id_back':''/);});

for(const size of [1499999,1500000])test('original '+size+' bytes does not trigger size compression',async()=>{const f=fixture({size});const r=await f.run();assert.equal(r.size,size);assert.equal(r.path,f.source);assert.equal(f.calls.some(x=>x[0]==='compress'),false);});
test('original 1500001 bytes triggers automatic compression',async()=>{const f=fixture({size:1500001});const r=await f.run();assert.equal(r.size,900000);assert.equal(f.calls.some(x=>x[0]==='compress'),true);});

for(const size of [10000000,20000000])test('original '+size+' bytes compresses before any original base64 read',async()=>{const f=fixture({size});const r=await f.run();assert.equal(r.size,900000);assert.equal(f.calls.some(x=>x[0]==='read'&&x[1]===f.source),false);});
