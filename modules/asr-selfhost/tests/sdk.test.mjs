import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createAsrClient} from '../web/sdk.mjs';
class FakeSocket {
  static sockets=[];
  constructor(url) {this.url=url.href; FakeSocket.sockets.push(this);}
  readyState=0;
  sent=[];
  closed=0;
  send(value){this.sent.push(value);}
  close(){this.readyState=3; this.closed++; this.onclose();}
  open(){this.readyState=1; this.onopen();}
  emit(data){this.onmessage({data:JSON.stringify(data)});}
}
const client = (opts={})=>createAsrClient({baseUrl:'https://first-party.test/voice/',WebSocketImpl:FakeSocket,...opts});
test('status and websocket stay scoped to the explicit self-host mount',async ()=>{
  let got;
  const asr=client({fetchImpl:async (url, init)=>{got=[url.href,init];return {json:async()=>({available:false})};}});
  assert.deepEqual(await asr.status(),{available:false});
  assert.equal(got[0],'https://first-party.test/voice/asr/status');
  assert.equal(got[1].redirect,'error');
  const session=asr.open(), ws=FakeSocket.sockets.at(-1);
  assert.equal(ws.url,'wss://first-party.test/voice/asr/stream');
  session.cancel();
});
test('onReady, streamed PCM, results, stop and automatic close use stable contract',()=>{
  const result=[], errors=[];
  let ready=0;
  const session=client().open({hotwords:['示例三中'],onReady:()=>ready++,onResult:e=>result.push(e),onError:e=>errors.push(e)});
  const ws=FakeSocket.sockets.at(-1), pcm=new Int16Array([42]);
  assert.equal(session.pushPCM(pcm),false);
  ws.open();
  assert.deepEqual(JSON.parse(ws.sent[0]),{hotwords:['示例三中']});
  ws.emit({type:'ready'});
  assert.equal(ready,1);
  assert.equal(session.pushPCM(pcm),true);
  assert.equal(ws.sent[1],pcm);
  ws.emit({type:'result',confirmed:'',draft:'示例三种',done:false});
  assert.equal(result[0].draft,'示例三种');
  assert.equal(session.stop(),true);
  assert.equal(session.stop(),false);
  assert.equal(ws.sent.at(-1),'stop');
  assert.equal(session.pushPCM(pcm),false);
  ws.emit({type:'result',confirmed:'示例三中。',draft:'',done:true});
  assert.equal(session.state,'closed');
  assert.equal(ws.closed,1);
  assert.equal(result[1].confirmed,'示例三中。');
  assert.deepEqual(errors,[]);
});
test('invalid result and disconnect produce one error, with no fake final',()=>{
  const results=[], errors=[];
  const s=client().open({onResult:e=>results.push(e),onError:e=>errors.push(e)});
  const ws=FakeSocket.sockets.at(-1);
  ws.open(); ws.emit({type:'ready'});
  assert.throws(()=>s.pushPCM(new Uint8Array(1)),/PCM/);
  ws.emit({type:'result',confirmed:'valid',draft:123,done:true});
  ws.onerror();
  assert.equal(s.state,'closed');
  assert.equal(results.length,0);
  assert.equal(errors.length,1);
});
