"""Local-only adapter for the first-party FunASR native two-pass WebSocket engine."""
import asyncio
from contextlib import suppress
import ipaddress
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

ROOT = Path(__file__).resolve().parent
PROVIDER = "funasr-local-2pass"
DEFAULT_URL = "ws://127.0.0.1:10095/"
TIMEOUT = 20  # Connect / EOF response deadline, not a recording duration limit.


class RecognitionError(Exception):
    pass


def local_endpoint(value):
    try:
        url = urlsplit(value)
        ip = ipaddress.ip_address(url.hostname or "")
        if url.scheme not in ("ws", "wss") or not ip.is_loopback or url.username or url.password or not url.port or url.fragment:
            raise ValueError
    except (ValueError, TypeError):
        raise RecognitionError("Configure a loopback-only ASR WebSocket engine") from None
    return value


class LocalConnect(connect):
    # An upstream redirect must never turn local audio transport into external traffic.
    def process_redirect(self, exc):
        return exc


async def check_engine(url):
    try:
        async with LocalConnect(local_endpoint(url), subprotocols=["binary"], proxy=None,
                                open_timeout=2, close_timeout=1):
            return True
    except (RecognitionError, WebSocketException, OSError, TimeoutError):
        return False


def start_message(words, name):
    words = list(dict.fromkeys(x.strip() for x in words if isinstance(x, str) and x.strip()))
    return {"mode": "2pass", "wav_name": name, "wav_format": "pcm",
            "audio_fs": 16000, "is_speaking": True, "chunk_size": [5, 10, 5],
            "chunk_interval": 10, "itn": False,
            "hotwords": json.dumps(dict.fromkeys(words, 20), ensure_ascii=False)}


class TwoPass:
    def __init__(self):
        self.committed = {}
        self.live = {}
        self.next_index = 0

    def result(self, done=False):
        confirmed = "".join(self.committed[i] for i in sorted(self.committed))
        temporary = "".join(self.live[i] for i in sorted(self.live))
        return {"type": "result", "confirmed": confirmed, "draft": temporary,
                "done": done, "secondPassSeen": bool(self.committed)}

    def consume(self, raw, stop_requested, name):
        if not isinstance(raw, str):
            raise RecognitionError("Expected a JSON reply from local model")
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("wav_name", name) != name:
            raise RecognitionError("Local model returned an unrelated result")
        txt, mode = data.get("text", ""), data.get("mode")
        if not isinstance(txt, str) or (txt and mode not in ("2pass-online", "2pass-offline")):
            raise RecognitionError("Unexpected local model reply")
        idx = data.get("index", self.next_index)
        if type(idx) is not int or idx < 0:
            raise RecognitionError("Invalid result index")
        if mode == "2pass-online" and txt and idx not in self.committed:
            # FunASR online text arrives as deltas, not cumulative sentences.
            self.live[idx] = self.live.get(idx, "") + txt
        elif mode == "2pass-offline":
            if txt and idx not in self.committed:
                # A second pass replaces only its sentence; never retract an earlier final.
                self.committed[idx] = txt
                self.live.pop(idx, None)
                self.next_index = max(self.next_index, idx+1)
        done = stop_requested and (data.get("is_final") is True or data.get("is_end") is True)
        return self.result(done)


async def stream_funasr(ws, endpoint, words, connector=LocalConnect):
    url, name = local_endpoint(endpoint), uuid4().hex
    async with connector(url, subprotocols=["binary"], proxy=None, open_timeout=TIMEOUT, close_timeout=2) as upstream:
        await upstream.send(json.dumps(start_message(words, name), ensure_ascii=False))
        await ws.send_json({"type": "ready"})
        state = TwoPass()
        stopped = False

        async def upload():
            nonlocal stopped
            sent_audio = False
            while True:
                incoming = await ws.receive()
                if incoming["type"] == "websocket.disconnect":
                    return False
                if incoming.get("text") == "stop":
                    if not sent_audio:
                        await ws.send_json(state.result(True))
                        return False
                    stopped = True
                    await upstream.send('{"is_speaking":false}')
                    return True
                incoming_audio = incoming.get("bytes")
                if not incoming_audio or len(incoming_audio) % 2:
                    raise RecognitionError("Invalid PCM frame")
                await upstream.send(incoming_audio)
                sent_audio = True

        async def download():
            async for raw in upstream:
                event = state.consume(raw, stopped, name)
                await ws.send_json(event)
                if event["done"]:
                    return
            raise RecognitionError("Local encoder ended before final response")

        writer, reader = asyncio.create_task(upload()), asyncio.create_task(download())
        try:
            await asyncio.wait((writer, reader), return_when=asyncio.FIRST_COMPLETED)
            if reader.done():
                await reader
            elif await writer:
                await asyncio.wait_for(reader, timeout=TIMEOUT)
        finally:
            for task in (writer, reader):
                if not task.done():
                    task.cancel()
            await asyncio.gather(writer, reader, return_exceptions=True)


def create_app(engine_url=None, transport=stream_funasr, probe=check_engine):
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    get_engine = engine_url or (lambda: os.environ.get("ASR_FUNASR_URL", DEFAULT_URL))

    @application.get("/asr/status")
    async def status():
        return {"available": await probe(get_engine()), "provider": PROVIDER}

    @application.websocket("/asr/stream")
    async def stream(ws: WebSocket):
        # Existing host authentication is applied by the embedding host, not reimplemented here.
        origin, host = ws.headers.get("origin"), ws.headers.get("host")
        if origin is not None and origin not in (f"http://{host}", f"https://{host}"):
            await ws.close(code=1008)
            return
        await ws.accept()
        try:
            options = await ws.receive_json()
            words = options.get("hotwords", [])
            if not isinstance(words, list):
                raise RecognitionError("Invalid speech options")
            await transport(ws, get_engine(), words)
        except (RecognitionError, WebSocketException, TimeoutError, OSError, ValueError,
                TypeError, AttributeError, KeyError, RuntimeError):
            with suppress(Exception):
                await ws.send_json({"type":"error", "message":"本地识别未完成，已保留已有文字，可继续手动修改。"})
        finally:
            with suppress(Exception):
                await ws.close()

    application.mount("/", StaticFiles(directory=ROOT/"web", html=True), name="preview")
    return application

app = create_app()
