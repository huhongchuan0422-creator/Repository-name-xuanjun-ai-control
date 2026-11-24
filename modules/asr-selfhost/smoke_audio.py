"""Send an approved WAV to the loopback UI bridge and time actual output."""
import argparse
import asyncio
import json
from pathlib import Path
from time import monotonic
import wave
from asr import LocalConnect, local_endpoint

async def transcribe(url, infile, terms):
    async with LocalConnect(local_endpoint(url), proxy=None, open_timeout=3) as ws:
        await ws.send(json.dumps({"hotwords": terms}, ensure_ascii=False))
        reply = json.loads(await asyncio.wait_for(ws.recv(),30))
        if reply.get("type") != "ready":
            raise RuntimeError("本地 ASR 没有就绪")
        started = monotonic()
        first = second = stopped = None
        n_samples = 0

        async def send():
            nonlocal n_samples, stopped
            while True:
                pcm = infile.readframes(2560)  # 160 ms chunks as delivered by the browser
                if not pcm:
                    break
                await ws.send(pcm)
                n_samples += len(pcm)//2
                await asyncio.sleep(max(0, started+n_samples/16000-monotonic()))
            stopped = monotonic()
            await ws.send("stop")

        async def receive():
            nonlocal first, second
            async for wire in ws:
                message = json.loads(wire)
                if message.get("type") != "result":
                    raise RuntimeError("本地 ASR 未完成识别")
                now = monotonic()
                if (message["draft"] or message["confirmed"]) and first is None:
                    first = round(1000*(now-started))
                if message["secondPassSeen"] and second is None:
                    second = round(1000*(now-started))
                if message["done"]:
                    remaining = round(1000*(now-stopped)) if stopped is not None else None
                    return {"audio_ms":round(n_samples/16), "first_text_ms":first,
                            "first_confirmed_ms":second,"stop_to_final_ms":remaining,
                            "confirmed":message["confirmed"],"unconfirmed":message["draft"],
                            "second_pass_seen":message["secondPassSeen"]}
            raise RuntimeError("识别未返回定稿信号")

        send_task, recv_task = asyncio.create_task(send()), asyncio.create_task(receive())
        try:
            done, _ = await asyncio.wait((send_task,recv_task),return_when=asyncio.FIRST_COMPLETED)
            if recv_task in done:
                return await recv_task
            await send_task
            return await asyncio.wait_for(recv_task,timeout=25)
        finally:
            for task in (send_task,recv_task):
                task.cancel()
            await asyncio.gather(send_task, recv_task, return_exceptions=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    parser.add_argument("--bridge",default="ws://127.0.0.1:8011/asr/stream")
    parser.add_argument("--hotword",action="append",default=[])
    args=parser.parse_args()
    with wave.open(str(args.wav),"rb") as audio:
        if (audio.getnchannels(),audio.getsampwidth(),audio.getframerate()) != (1,2,16000):
            parser.error("仅接受 16 kHz、单声道、16 位 PCM WAV")
        print(json.dumps(asyncio.run(transcribe(args.bridge,audio,args.hotword)),ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
