import asyncio
import json
import unittest
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from asr import create_app, stream_funasr, RecognitionError, local_endpoint, TwoPass, check_engine


class LocalRuntimeDouble:
    def __init__(self, fail=False):
        self.incoming = asyncio.Queue()
        self.sent = []
        self.fail = fail

    async def send(self, msg):
        self.sent.append(msg)
        if len(self.sent) == 1:
            start = json.loads(msg)
            self.name = start.pop("wav_name")
            expected = {"mode":"2pass","wav_format":"pcm","audio_fs":16000,"is_speaking":True,
                        "chunk_size":[5,10,5],"chunk_interval":10,"itn":False}
            assert json.loads(start.pop("hotwords")) == {"示例三中":20}
            assert start == expected
        elif len(self.sent) == 2:
            assert msg == b"\x01\x00"
            await self.reply("2pass-online", "示例", 0)
        elif len(self.sent) == 3:
            assert msg == b"\x02\x00"
            if self.fail:
                await self.incoming.put('{"mode":"bad","text":"untrusted vendor text"}')
            else:
                await self.reply("2pass-online", "三种", 0)
                await self.reply("2pass-offline", "示例三中。", 0)
                await self.reply("2pass-online", "不是二中", 1)
        else:
            assert json.loads(msg) == {"is_speaking":False}
            await self.reply("2pass-offline", "不是示例二中。", 1, final=True)

    async def reply(self, mode, text, index, final=False):
        await self.incoming.put(json.dumps(
            {"wav_name":self.name,"mode":mode,"text":text,"index":index,"is_final":final}))

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.incoming.get()


def client_with_engine(fail=False):
    fake = LocalRuntimeDouble(fail)
    @asynccontextmanager
    async def dial(url, **kwargs):
        assert url == "ws://127.0.0.1:10095/"
        assert kwargs["proxy"] is None
        assert "additional_headers" not in kwargs
        yield fake
    async def transport(ws, url, words):
        await stream_funasr(ws, url, words, connector=dial)
    async def probe(url):
        return local_endpoint(url) == "ws://127.0.0.1:10095/"
    return TestClient(create_app(transport=transport, probe=probe)), fake


class ApiTests(unittest.TestCase):
    def test_ui_is_served(self):
        client, _ = client_with_engine()
        self.assertIn("开始录音", client.get("/").text)
        self.assertIn("registerProcessor", client.get("/pcm-worklet.js").text)
        self.assertEqual(client.get("/asr/status").json(), {"available":True, "provider":"funasr-local-2pass"})
        self.assertNotIn("豆包",client.get("/app.mjs").text)

    def test_two_sentence_ws_with_actual_asgi_no_repeated_or_overwritten_text(self):
        client, fake = client_with_engine()
        with client.websocket_connect("/asr/stream") as ws:
            ws.send_json({"hotwords":["示例三中","示例三中"]})
            self.assertEqual(ws.receive_json(),{"type":"ready"})
            ws.send_bytes(b"\x01\x00")
            self.assertEqual(ws.receive_json()["draft"],"示例")
            ws.send_bytes(b"\x02\x00")
            self.assertEqual(ws.receive_json()["draft"],"示例三种")
            e = ws.receive_json()
            self.assertEqual((e["confirmed"],e["draft"],e["done"]),("示例三中。","",False))
            e = ws.receive_json()
            self.assertEqual((e["confirmed"],e["draft"]),("示例三中。","不是二中"))
            ws.send_text("stop")
            self.assertEqual(ws.receive_json(), {"type":"result","confirmed":"示例三中。不是示例二中。",
                             "draft":"","done":True,"secondPassSeen":True})
        self.assertEqual(len(fake.sent),4)

    def test_no_audio_is_not_a_real_model_result(self):
        client, fake = client_with_engine()
        with client.websocket_connect("/asr/stream") as ws:
            ws.send_json({"hotwords":["示例三中"]})
            ws.receive_json()
            ws.send_text("stop")
            e = ws.receive_json()
            self.assertTrue(e["done"])
            self.assertFalse(e["secondPassSeen"])
            self.assertEqual(e["confirmed"],"")
        self.assertEqual(len(fake.sent),1)

    def test_backend_failure_never_claims_final(self):
        client, _ = client_with_engine(fail=True)
        with client.websocket_connect("/asr/stream") as ws:
            ws.send_json({"hotwords":["示例三中"]})
            ws.receive_json()
            ws.send_bytes(b"\x01\x00"); ws.receive_json()
            ws.send_bytes(b"\x02\x00")
            e = ws.receive_json()
            self.assertEqual(e["type"],"error")
            self.assertNotIn("untrusted",str(e))

    def test_cross_origin_is_not_an_allowed_relay(self):
        client, fake = client_with_engine()
        with self.assertRaises(WebSocketDisconnect):
            with client.websocket_connect("/asr/stream", headers={"origin":"https://outside.invalid"}):
                self.fail("must not accept")
        self.assertEqual(fake.sent,[])

    def test_cloud_env_does_not_enable_old_provider_and_external_url_never_dialed(self):
        client = TestClient(create_app(engine_url=lambda:"wss://sample.invalid:443/"))
        self.assertFalse(client.get("/asr/status").json()["available"])
        with client.websocket_connect("/asr/stream") as ws:
            ws.send_json({})
            self.assertEqual(ws.receive_json()["type"], "error")

    def test_loopback_literal_only(self):
        for ip in ("ws://127.0.0.1:10095/", "wss://[::1]:1234/"):
            self.assertEqual(local_endpoint(ip),ip)
        for url in ("wss://trial.invalid:443/","ws://localhost:10095/",
                    "ws://name@127.0.0.1:10095/","ws://192.168.1.1:10095/",
                    "file:///not-an-engine", "ws://127.0.0.1/"):
            with self.assertRaises(RecognitionError):
                local_endpoint(url)

    def test_empty_terminal_does_not_promote_unconfirmed_draft(self):
        s = TwoPass()
        e = s.consume('{"mode":"2pass-online","text":"甲","is_final":true}',False,"x")
        self.assertFalse(e["done"])
        e=s.consume('{"text":"","is_final":true}',True,"x")
        self.assertEqual((e["confirmed"],e["draft"],e["done"],e["secondPassSeen"]),("","甲",True,False))

    def test_old_index_cannot_overwrite_committed_sentence(self):
        s=TwoPass()
        encode=lambda mode,text,index:json.dumps(dict(mode=mode,text=text,index=index), ensure_ascii=False)
        s.consume(encode("2pass-offline","甲。",0),False,"x")
        s.consume(encode("2pass-online","甲 旧",0),False,"x")
        e=s.consume(encode("2pass-online","乙",1),False,"x")
        self.assertEqual((e["confirmed"],e["draft"]),("甲。","乙"))

class NativeSocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_loopback_socket_using_runtime_protocol_double_no_proxy(self):
        from unittest.mock import patch
        from websockets.asyncio.server import serve
        from websockets.exceptions import ConnectionClosed
        async def vendor(s):
            try:
                first = json.loads(await s.recv())
                self.assertEqual(first["mode"], "2pass")
                self.assertEqual(s.subprotocol, "binary")
                self.assertNotIn("X-Api-Key", s.request.headers)
                name = first["wav_name"]
                self.assertEqual(await s.recv(), b"\x01\x00")
                await s.send(json.dumps({"wav_name":name,"mode":"2pass-online","text":"三种"}))
                self.assertEqual(json.loads(await s.recv()), {"is_speaking":False})
                await s.send(json.dumps({"wav_name":name,"mode":"2pass-offline","text":"三中。","is_final":True}))
            except ConnectionClosed:  # /status's readiness connection sends no audio
                pass
        async with serve(vendor, "127.0.0.1", 0, subprotocols=["binary"]) as server:
            port = server.sockets[0].getsockname()[1]
            url = f"ws://127.0.0.1:{port}/"
            def exercise_client():
                client = TestClient(create_app(engine_url=lambda: url))
                self.assertTrue(client.get("/asr/status").json()["available"])
                with client.websocket_connect("/asr/stream") as s:
                    s.send_json({})
                    self.assertEqual(s.receive_json()["type"],"ready")
                    s.send_bytes(b"\x01\x00")
                    self.assertEqual(s.receive_json()["draft"],"三种")
                    s.send_text("stop")
                    finished=s.receive_json()
                    self.assertEqual((finished["confirmed"],finished["done"]),("三中。",True))
            with patch.dict("os.environ",{"ws_proxy":"http://127.0.0.1:1","no_proxy":"","NO_PROXY":""}):
                await asyncio.wait_for(asyncio.to_thread(exercise_client),5)

    async def test_upstream_redirect_not_followed(self):
        from http import HTTPStatus
        from websockets.asyncio.server import serve
        opened_elsewhere = asyncio.Event()

        async def catch_redirect_target(_):
            opened_elsewhere.set()

        async with serve(catch_redirect_target, "127.0.0.1", 0) as other:
            other_port = other.sockets[0].getsockname()[1]
            async def start_redirect(connection, request):
                result = connection.respond(HTTPStatus.FOUND,"This endpoint must never be followed")
                result.headers["Location"] = f"ws://127.0.0.1:{other_port}/"
                return result
            async with serve(catch_redirect_target, "127.0.0.1", 0, process_request=start_redirect) as server:
                url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/"
                self.assertFalse(await check_engine(url))
        self.assertFalse(opened_elsewhere.is_set())
