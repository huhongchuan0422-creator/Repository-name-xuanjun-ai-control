"""Synthetic HTTP media failure classification; no provider IO or new authority."""
import json
import http.server
import urllib.request
import urllib.error
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from test_community_h5_recovery import H5Recovery
from scripts.community_h5 import make_handler
from scripts.community_wechat_applyment import WechatMediaPending


class MediaUnknown(unittest.TestCase):
    def test_exact_pending_is_409_without_private_details_or_session_loss(self):
        f = H5Recovery(); f.setUp()
        server = http.server.HTTPServer(('127.0.0.1', 0), make_handler(f.h, Path('clients/community-h5/dist')))
        server.timeout = 3
        def send(path, body):
            req = urllib.request.Request('http://127.0.0.1:' + str(server.server_port) + path,
                data=json.dumps(body).encode(), headers={**dict(f.headers.items()), 'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(req, timeout=5) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as error:
                return error.code, json.load(error)
        try:
            with ThreadPoolExecutor(1) as pool:
                for error, expected_status, expected_code in [
                    (WechatMediaPending('private transport detail'), 409, 'WECHAT_MEDIA_RESULT_UNKNOWN'),
                    (PermissionError('WECHAT_MEDIA_RESULT_UNKNOWN'), 403, 'ACCESS_DENIED')]:
                    with patch.object(f.h, 'dispatch', side_effect=error) as dispatch:
                        future = pool.submit(send, '/h5/merchant', {'scene':'shop1','operation':'onboarding',
                            'params':{'operation':'wechat_media','params':{'application':'synthetic','kind':'business_license'}}})
                        server.handle_request()
                        self.assertEqual(future.result(), (expected_status, {'error':expected_code}))
                        self.assertEqual(dispatch.call_count, 1)
                    future = pool.submit(send, '/h5/session/check', {})
                    server.handle_request()
                    status, body = future.result()
                    self.assertEqual(status, 200)
                    self.assertEqual(body['result']['user_id'], f.f.fx.uid1)
        finally:
            server.server_close(); f.tearDown()
