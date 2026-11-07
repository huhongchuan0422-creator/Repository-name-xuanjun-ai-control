'use strict';
// Decode and hash private response bytes locally. No network, storage or identifiers.
function bytes(base64){
 if(typeof base64!=='string'||base64.length%4||! /^[A-Za-z0-9+/]*={0,2}$/.test(base64))throw Error('MATERIAL_PREVIEW_INVALID');
 const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',padding=base64.endsWith('==')?2:base64.endsWith('=')?1:0,out=new Uint8Array(base64.length/4*3-padding);let at=0;
 for(let i=0;i<base64.length;i+=4){const a=alphabet.indexOf(base64[i]),b=alphabet.indexOf(base64[i+1]),c=base64[i+2]==='='?0:alphabet.indexOf(base64[i+2]),d=base64[i+3]==='='?0:alphabet.indexOf(base64[i+3]);if(i===base64.length-4&&(padding===2&&(b&15)||padding===1&&(c&3)))throw Error('MATERIAL_PREVIEW_INVALID');const n=(a<<18)|(b<<12)|(c<<6)|d;if(at<out.length)out[at++]=(n>>>16)&255;if(at<out.length)out[at++]=(n>>>8)&255;if(at<out.length)out[at++]=n&255;}
 return out;
}
const K=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
const rr=(x,n)=>(x>>>n)|(x<<(32-n));
function sha256(input){
 const data=new Uint8Array(Math.ceil((input.length+9)/64)*64);data.set(input);data[input.length]=128;const bits=input.length*8;for(let i=0;i<8;i++)data[data.length-1-i]=Math.floor(bits/Math.pow(256,i))&255;
 const h=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19],w=new Uint32Array(64);
 for(let offset=0;offset<data.length;offset+=64){for(let i=0;i<16;i++){const p=offset+i*4;w[i]=(data[p]<<24)|(data[p+1]<<16)|(data[p+2]<<8)|data[p+3];}for(let i=16;i<64;i++){const x=w[i-15],y=w[i-2];w[i]=(w[i-16]+(rr(x,7)^rr(x,18)^(x>>>3))+w[i-7]+(rr(y,17)^rr(y,19)^(y>>>10)))>>>0;}let [a,b,c,d,e,f,g,z]=h;for(let i=0;i<64;i++){const t1=(z+(rr(e,6)^rr(e,11)^rr(e,25))+((e&f)^(~e&g))+K[i]+w[i])>>>0,t2=((rr(a,2)^rr(a,13)^rr(a,22))+((a&b)^(a&c)^(b&c)))>>>0;z=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;}for(const [i,v] of [a,b,c,d,e,f,g,z].entries())h[i]=(h[i]+v)>>>0;}
 return h.map(x=>x.toString(16).padStart(8,'0')).join('');
}
function verify(result){const raw=bytes(result.content_base64);if(raw.length!==result.size||sha256(raw)!==result.sha256)throw Error('MATERIAL_PREVIEW_INVALID');const png=[137,80,78,71,13,10,26,10].every((x,i)=>raw[i]===x),jpeg=raw[0]===255&&raw[1]===216&&raw[2]===255;if(result.mime!==(png?'image/png':jpeg?'image/jpeg':''))throw Error('MATERIAL_PREVIEW_INVALID');return true;}
module.exports={bytes,sha256,verify};
