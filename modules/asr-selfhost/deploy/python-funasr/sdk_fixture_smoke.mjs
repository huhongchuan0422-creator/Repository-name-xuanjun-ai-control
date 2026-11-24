import {createAsrClient} from '../../web/sdk.mjs';
import {readFileSync} from 'node:fs';
import {setTimeout as sleep} from 'node:timers/promises';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';

const wav=readFileSync(process.argv[2] || 'fixture.wav');
const base=process.argv[3] || 'http://127.0.0.1:18097/';
let pcm;
for(let i=12;i+8<=wav.length;){
  let len=wav.readUInt32LE(i+4);
  if(wav.toString('ascii',i,i+4)==='data') { pcm=wav.subarray(i+8,i+8+len); break; }
  i+=8+len+(len%2);
}
assert.equal(wav.toString('ascii',0,4),'RIFF');
assert(pcm && pcm.length && pcm.length%2===0);
const whole=Buffer.concat([pcm,Buffer.alloc(16000*2*2),pcm]);
const digest=(b)=>createHash('sha256').update(b).digest('hex');
const client=createAsrClient({baseUrl:base});
assert.equal((await client.status()).available,true);
let emitted=0, earlier, latestBeforeStop='', beforeEnd, stopped=false, started=0, firstDraft=null, firstConfirmed=null;
const output=await new Promise((resolve,reject)=>{
  const terminalTimeout=globalThis.setTimeout(()=>{scope.cancel();reject(new Error('real SDK pipeline timed out'))},35000);
  const fail=(error)=>{clearTimeout(terminalTimeout);reject(error)};
  const finish=(e)=>{
    clearTimeout(terminalTimeout);
    try {
      assert(firstDraft!==null && firstConfirmed!==null);
      assert(earlier?.length>0 && beforeEnd === true);
      assert(e.secondPassSeen && e.done && !e.draft);
      assert(e.confirmed.startsWith(earlier));
      const repeatedMatch = e.confirmed.slice(earlier.length) === earlier;
      if (process.env.STRICT_REPEAT === "1") assert(repeatedMatch, "Identical PCM yielded different recognized text");
      resolve({fixture_sha256:digest(wav),real_audio_frames:whole.length/2,
        samples_per_clip:pcm.length/2, inserted_pause_ms:2000,
        real_events:emitted, first_draft_ms:firstDraft, first_confirmed_ms:firstConfirmed,
        completed_before_stop:beforeEnd, first_sentence_chars:[...earlier].length,
        final_chars:[...e.confirmed].length,entire_session_confirmed:e.done,
        exact_repeated_audio_transcript_match:repeatedMatch,second_pass_seen:e.secondPassSeen,
        elapsed_ms:Math.round(performance.now()-started)});
    } catch(err) { reject(err); }
  };
  const scope=client.open({
    onReady:async ()=>{
      started=performance.now();
      try{
        for(let i=0;i<whole.length;i+=5120){
          const frame=whole.subarray(i,i+5120);
          assert(scope.pushPCM(frame));
          await sleep(Math.max(0,started+(i+frame.length)/32-performance.now()));
        }
        stopped=true;
        assert(scope.stop());
      } catch(error){ scope.cancel(); fail(error); }
    },
    onResult:e=>{
      emitted++;
      let now=Math.round(performance.now()-started);
      if(e.draft && firstDraft===null) firstDraft=now;
      if(e.confirmed && firstConfirmed===null){
        firstConfirmed=now; beforeEnd=!stopped; earlier=e.confirmed;
      }
      if (!stopped) latestBeforeStop=e.confirmed;
      if(e.done) finish(e);
    },
    onError:fail,
  });
});
console.log(JSON.stringify(output,null,2));
