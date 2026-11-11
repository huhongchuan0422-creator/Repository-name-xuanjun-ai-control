// Preserve every tracked asset of the exact original Site, without a push/deploy.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import {createHash} from 'node:crypto';
const [root,out]=process.argv.slice(2);
if (!root || !out) throw new Error('PINNED_SOURCE_AND_OUTPUT_REQUIRED');
const git=(...args)=>execFileSync('git',['-C',root,...args],{encoding:'utf8'});
if (git('rev-parse','HEAD').trim()!=='16b6113d6d8c98eda8f646437d5ef1f54a9345ba') throw new Error('SITE_SOURCE_PIN');
git('diff','--exit-code','HEAD','--','dist');
const files=git('ls-files','-z','dist').split('\0').filter(Boolean).sort();
if (!files.length || files.length>1000) throw new Error('SITE_ASSET_BOUND');
const types={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8',
  '.js':'text/javascript; charset=utf-8','.json':'application/json','.svg':'image/svg+xml',
  '.png':'image/png','.jpg':'image/jpeg','.ico':'image/x-icon'};
const assets={}, hashes={}; let size=0;
for(const name of files){
  // Use repository bytes for binaries too; never rely on decoded Git show.
  const exact=execFileSync('git',['-C',root,'show','HEAD:'+name],{maxBuffer:4*1024*1024});
  size+=exact.length; if(size>4*1024*1024) throw new Error('SITE_ASSET_SIZE_BOUND');
  const route='/'+name.slice('dist/'.length);
  assets[route]={type:types[path.extname(name)]||'application/octet-stream',body:exact.toString('base64')};
  hashes[route]=createHash('sha256').update(exact).digest('hex');
}
const source=await readFile(new URL('./worker.mjs',import.meta.url),'utf8');
await mkdir(out,{recursive:true});
await writeFile(path.join(out,'index.mjs'),'const STATIC_FILES='+JSON.stringify(assets)+';\n'+source);
await writeFile(path.join(out,'preserved-assets.json'),JSON.stringify(hashes,null,2)+'\n');
console.log(JSON.stringify({asset_count:files.length,asset_bytes:size,source_pin:'16b6113d6d8c98eda8f646437d5ef1f54a9345ba',deployment:'NOT_RUN'}));
