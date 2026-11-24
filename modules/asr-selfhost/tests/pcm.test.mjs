import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
const source=readFileSync(new URL('../web/pcm-worklet.js',import.meta.url),'utf8');
for (const rate of [44100,48000,16000]) {
  test(`${rate} Hz streaming PCM resamples across 128-sample boundaries and flushes`,() => {
    let Worklet;
    const sent=[];
    runInNewContext(source,{sampleRate:rate,AudioWorkletProcessor:class{port={postMessage:(d)=>sent.push(d)}},registerProcessor:(name,T)=>Worklet=T});
    const w = new Worklet();
    for(let i=0;i<rate;i+=128) { const t=new Float32Array(Math.min(128,rate-i)).fill(.5); w.process([[t]]); }
    w.port.onmessage({data:'flush'});
    assert.equal(sent.pop(),'flushed');
    const b=Buffer.concat(sent.map(x=>Buffer.from(x)));
    assert.equal(b.length,32000);
    for(let i=0;i<b.length;i+=2) assert.equal(b.readInt16LE(i),16384);
  });
}
