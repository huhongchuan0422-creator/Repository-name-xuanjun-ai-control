"""Offline Python FunASR CPU engine with the native two-pass WebSocket contract."""
import argparse
import asyncio
import hashlib
import ipaddress
import json
import logging
import os
from pathlib import Path
import sys

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

RATE, VAD_BYTES, STREAM_BYTES = 16000, 6400, 19200

def block_nonlocal_socket(event, arguments):
    """Runtime inference never needs DNS or a non-loopback peer."""
    if event in ("socket.connect", "socket.getaddrinfo", "socket.sendto"):
        value = arguments[0] if event == "socket.getaddrinfo" else arguments[1]
        if event != "socket.getaddrinfo" and not isinstance(value, tuple):
            return  # UNIX-domain IPC
        host = value[0] if isinstance(value, tuple) else value
        try:
            if ipaddress.ip_address(host).is_loopback:
                return
        except (TypeError, ValueError):
            pass
        raise PermissionError("FunASR runtime has no external network")

def verified_paths(root, lock):
    required = {"streaming", "offline", "vad"}
    if not required <= lock.keys():
        raise ValueError("Explicit lock for each checkpoint is required")
    for role in required:
        folder = (root/role).resolve(strict=True)
        files = lock[role]["files"]
        if not folder.is_relative_to(root) or not {"model.pt","configuration.json","config.yaml"} <= files.keys():
            raise ValueError("Incomplete role lock: "+role)
        for name, checksum in files.items():
            file = (folder/name).resolve(strict=True)
            if not file.is_relative_to(folder):
                raise ValueError("Checkpoint asset outside stage")
            with file.open("rb") as handle:
                if hashlib.file_digest(handle,"sha256").hexdigest() != checksum:
                    raise ValueError("Checksum mismatch: "+file.name)
        yield role, folder

class SpeechSession:
    def __init__(self, models, words):
        self.models, self.words = models, words
        self.buff, self.audio = bytearray(), bytearray()
        self.base, self.end, self.pos, self.index = 0, 0, 0, 0
        self.start = None
        self.vcache, self.scache = {}, {}

    def samples(self, a, b):
        import numpy as np
        raw = self.audio[max(0,a-self.base)*2:max(0,b-self.base)*2]
        return np.frombuffer(raw,dtype="<i2").astype("float32")/32768.0

    def online(self, end, last=False):
        while self.pos+STREAM_BYTES//2 < end or (last and self.pos < end):
            new_pos=min(self.pos+STREAM_BYTES//2,end)
            text=self.models["streaming"].generate(input=self.samples(self.pos,new_pos),
                cache=self.scache,is_final=last and new_pos==end,chunk_size=[0,10,5],
                encoder_chunk_look_back=4,decoder_chunk_look_back=1,disable_pbar=True)[0].get("text","")
            self.pos=new_pos
            if text:
                yield {"mode":"2pass-online","index":self.index,"text":text}

    def finish(self, end):
        if self.start is None: return
        if os.environ.get("ASR_ACCEPTANCE_TIMING") == "1":
            print(f"segment_timing index={self.index} a_ms={self.start//16} b_ms={end//16}",flush=True)
        # The final full-sentence pass uses original PCM, not the draft text.
        yield from self.online(end,last=True)
        audio=self.samples(self.start,end)
        if len(audio):
            text=self.models["offline"].generate(input=audio,disable_pbar=True,itn=False,
                       **({"hotword":" ".join(self.words)} if self.words else {}))[0].get("text","")
            if text:
                yield {"mode":"2pass-offline","index":self.index,"text":text}
        self.index+=1
        self.start, self.scache=None, {}
        trim=max(0,end-self.base)
        del self.audio[:trim*2]
        self.base+=trim

    def chunk(self, pcm, last):
        p0=self.end
        self.audio+=pcm
        self.end+=len(pcm)//2
        if pcm or last:
            if not pcm:
                # Give the fbank a small masked tail to flush its cached state.
                import numpy as np
                input_pcm=np.zeros(3200,dtype=np.float32)
            else:
                input_pcm=self.samples(p0,self.end)
            spans=self.models["vad"].generate(input=input_pcm,cache=self.vcache,chunk_size=200,
                  is_final=last,disable_pbar=True)[0].get("value",[])
            for a,b in spans:
                if a >= 0 and self.start is None:
                    self.start=self.pos=max(self.base,min(self.end,a*16-3200))
                if b >= 0:
                    yield from self.finish(max(self.pos,min(self.end,b*16)))
        if self.start is not None:
            if last:
                yield from self.finish(self.end)
            else:
                yield from self.online(self.end)

    def step(self, pcm, last=False):
        self.buff+=pcm
        while len(self.buff)>VAD_BYTES or (len(self.buff)==VAD_BYTES and not last):
            item=bytes(self.buff[:VAD_BYTES])
            del self.buff[:VAD_BYTES]
            yield from self.chunk(item,False)
        if last:
            if self.end or self.buff:
                # Equivalent to waiting through a pause: a short zero PCM tail
                # lets VAD close the last spoken sentence instead of clipping
                # the non-streaming pass at the exact stop-button edge.
                self.buff += b"\0" * (RATE * 2)
                while len(self.buff) > VAD_BYTES:
                    item = bytes(self.buff[:VAD_BYTES])
                    del self.buff[:VAD_BYTES]
                    yield from self.chunk(item, False)
                yield from self.chunk(bytes(self.buff),True)
            self.buff.clear()

async def run(models, port):
    model_lock=asyncio.Lock()
    async def handler(sock):
        try:
            init=json.loads(await sock.recv())
            name=init.get("wav_name","")
            if init.get("mode")!="2pass" or init.get("audio_fs")!=RATE or init.get("wav_format")!="pcm":
                await sock.close(1003,"Expected PCM16 16kHz two-pass audio"); return
            hotwords=json.loads(init.get("hotwords","{}"))
            if not isinstance(hotwords,dict):
                await sock.close(1003,"Invalid hotwords"); return
            state=SpeechSession(models,list(hotwords))
            async for packet in sock:
                last=isinstance(packet,str) and json.loads(packet).get("is_speaking") is False
                if not last and (not isinstance(packet,bytes) or len(packet)%2):
                    await sock.close(1003,"Invalid PCM"); return
                async with model_lock:
                    events=await asyncio.to_thread(lambda: list(state.step(b"" if last else packet,last)))
                for event in events:
                    await sock.send(json.dumps({**event,"wav_name":name,"is_final":False},ensure_ascii=False))
                if last:
                    await sock.send(json.dumps({"text":"","wav_name":name,"is_final":True}))
                    return
        except (ConnectionClosed, ValueError, TypeError, AttributeError):
            return
        except Exception as e:
            logging.error("local ASR inference failed: %s",type(e).__name__)
            await sock.close(1011,"Local inference failed")

    async with serve(handler,"127.0.0.1",port,subprotocols=["binary"]):
        print(f"local_fun_asr_ready port={port}",flush=True)
        await asyncio.Future()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("models",type=Path)
    p.add_argument("lock",type=Path)
    p.add_argument("--port",type=int,default=10095)
    p.add_argument("--threads",type=int,default=2)
    args=p.parse_args()
    os.environ.update(HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1")
    sys.addaudithook(block_nonlocal_socket)
    logging.basicConfig(level=logging.WARNING)
    import torch
    from funasr import AutoModel
    torch.set_num_threads(args.threads)
    models={r:AutoModel(model=str(path),device="cpu",disable_update=True,trust_remote_code=False)
           for r,path in verified_paths(args.models.resolve(strict=True),json.loads(args.lock.read_text()))}
    asyncio.run(run(models,args.port))

if __name__=="__main__":
    main()
