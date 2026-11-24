import {test} from 'node:test';
import assert from 'node:assert/strict';

const makeElement = () => ({value:'',textContent:'',hidden:false,disabled:false,focus(){},select(){}});
test('page consumes live UI events, protects typing, and falls back without clearing text', async (t) => {
  const names=['record','sample','transcript','status','count','phase','candidate','suggestion','append','copy-suggestion','copy','provider','hotwords'];
  const elements = new Map(names.map(n=>[n, makeElement()]));
  const el = (name) => elements.get(name);
  const tracks=[{stop: t.mock.fn()}];
  const sock=[];
  const pcm=[];
  const timers=[];
  let copied;
  const values = {
    document:{getElementById: el},
    navigator:{mediaDevices:{getUserMedia: async ()=>({getTracks:()=>tracks})},clipboard:{writeText:async text=>{copied=text}}},
    fetch:async ()=>({json:async()=>({available:true})}),
    location:{href:'https://test.invalid/voice/'},
    AudioContext:class{destination={}; audioWorklet={addModule:async()=>{}}; resume=async()=>{}; close=async()=>{}; createMediaStreamSource(){return {connect(){}}}},
    AudioWorkletNode:class{
      constructor(){pcm.push(this);}
      connect(){}
      port={postMessage:t.mock.fn()};
    },
    WebSocket:class{
      static OPEN=1;
      readyState=1;
      constructor(url){sock.push(this); this.url=url.href;}
      send=t.mock.fn();
      close=t.mock.fn();
    },
    setTimeout:(fn)=>{timers.push(fn);return timers.length;},
  };
  const prior = Object.entries(values).map(([k,v])=>[k,Object.getOwnPropertyDescriptor(globalThis,k),v]);
  for(const [k,,v] of prior) Object.defineProperty(globalThis,k,{value:v,configurable:true,writable:true});
  try {
    await import('../web/app.mjs');
    assert.equal(el('record').disabled,false);
    assert.match(el('provider').textContent,/自部署服务器/);
    assert.equal(sock.length,0);
    el('sample').onclick(); timers.splice(0).forEach(f=>f());
    assert.match(el('transcript').value,/示例三中/);
    assert.match(el('status').textContent,/不是实际录音/);
    assert.equal(sock.length,0);

    el('transcript').value=''; el('transcript').oninput();
    el('hotwords').value='示例三中\n语音';
    await el('record').onclick();
    const current = sock[0];
    assert.equal(current.url,'wss://test.invalid/voice/asr/stream');
    current.onopen();
    assert.deepEqual(JSON.parse(current.send.mock.calls[0].arguments[0]).hotwords,['示例三中','语音']);
    const emit=(e)=>current.onmessage({data:JSON.stringify(e)});
    emit({type:'ready'});
    emit({type:'result',confirmed:"",done:false,draft:'示例三种'});
    assert.equal(el('transcript').value,'示例三种');
    el('transcript').oncompositionstart();
    el('transcript').value='我亲自写的：示例三中';
    el('transcript').oninput();
    emit({type:'result',draft:"",done:false,confirmed:'示例三中，不是示例二中。'});
    el('transcript').oncompositionend();
    assert.equal(el('transcript').value,'我亲自写的：示例三中');
    assert.equal(el('append').hidden,true);
    await el('copy-suggestion').onclick();
    assert.equal(copied,'示例三中，不是示例二中。');

    await el('record').onclick();
    assert.equal(pcm[0].port.postMessage.mock.calls[0].arguments[0],'flush');
    const tail=new ArrayBuffer(4);
    pcm[0].port.onmessage({data:tail}); pcm[0].port.onmessage({data:'flushed'});
    assert.deepEqual(current.send.mock.calls.slice(1).map(c=>c.arguments[0]),[tail,'stop']);
    emit({type:'result',draft:"",confirmed:'示例三中，不是示例二中。',done:true});
    assert.equal(el('transcript').value,'我亲自写的：示例三中');
    await el('record').onclick();
    sock[1].onclose();
    assert.match(el('status').textContent,/仍可编辑/);
    assert.equal(el('transcript').value,'我亲自写的：示例三中');
    assert.equal(el('record').disabled,false);
  } finally {
    for(const [k,d] of prior) if(d) Object.defineProperty(globalThis,k,d); else delete globalThis[k];
  }
});
