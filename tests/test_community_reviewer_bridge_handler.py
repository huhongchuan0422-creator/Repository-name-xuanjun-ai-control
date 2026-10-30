"""Actual original HTTP parser/dispatch with in-memory streams, NO real socket.
Unix peer proof is a synthetic test boundary, never production/transport proof.
"""
import io
import json
import os
import socket
import struct
import unittest
import test_community_reviewer_bridge as fixture
from scripts.community_mini_http import make_handler
from scripts.pr122_customer_source import TrustedNginxSource

class SyntheticUnixConnection:
    family=socket.AF_UNIX
    def settimeout(self, timeout): pass
    def getsockopt(self, level, key, size):
        assert (level,key,size)==(socket.SOL_SOCKET,socket.SO_PEERCRED,12)
        return struct.pack('3i',12345,os.getuid(),os.getgid())

class OriginalHandlerTests(unittest.TestCase):
    start=fixture.BridgeTests.start
    def setUp(self):
        fixture.BridgeTests.setUp(self)
        self.Handler=make_handler(self.fx.g,proxy_origin=fixture.ORIGIN,trusted_proxy=TrustedNginxSource(os.getuid()),onboarding=self.onboarding)
    def request(self,path,body,headers=None):
        payload=json.dumps(body).encode()
        fields=[('Host','uk.wenwenwenyiyiyi.work'),('X-Xuanjun-Client-IP','127.0.0.1'),('Content-Type','application/json'),('Content-Length',str(len(payload)))]
        fields += list((headers or {}).items()) if isinstance(headers,dict) or headers is None else headers
        raw=('POST '+path+' HTTP/1.1\r\n'+''.join(k+': '+v+'\r\n' for k,v in fields)+'\r\n').encode()+payload
        h=self.Handler.__new__(self.Handler);h.rfile=io.BytesIO(raw);h.wfile=io.BytesIO();h.connection=SyntheticUnixConnection();h.client_address=('fixture',0)
        h.close_connection=True;h.handle_one_request()
        header,body=h.wfile.getvalue().split(b'\r\n\r\n',1)
        lines=header.decode().split('\r\n');values=dict(line.split(': ',1) for line in lines[1:])
        return int(lines[0].split()[1]),values,json.loads(body)
    def test_complete_http_parse_dispatch_original_reviewer_check(self):
        status,h,value=self.request('/community/session/wechat',{'scene':'shop1','action':'BEGIN'},{'Origin':fixture.ORIGIN})
        self.assertEqual(status,200,value);began=value['result']
        browser=h['Set-Cookie'].split(';')[0]
        mini={'X-Community-Session':self.mini}
        body={'scene':'shop1','challenge':began['challenge'],'action':'DESCRIBE'}
        status,_,description=self.request('/mini/reviewer-login',body,mini);self.assertEqual(status,200,description)
        body.update(action='CONFIRM_THIS_BROWSER',verification=description['result']['verification'])
        self.assertEqual(self.request('/mini/reviewer-login',body,mini)[0],200)
        web={'Origin':fixture.ORIGIN,'Cookie':browser,'X-CSRF-Token':began['csrf']}
        status,h,value=self.request('/community/session/wechat',{'scene':'shop1','challenge':began['challenge'],'action':'FINISH'},web)
        self.assertEqual(status,200,value)
        web={'Origin':fixture.ORIGIN,'Cookie':h['Set-Cookie'].split(';')[0],'X-CSRF-Token':value['result']['csrf']}
        status,_,value=self.request('/community/session/check',{},web)
        self.assertEqual(status,200,value);self.assertTrue(value['result']['reviewer'])
        status,_,value=self.request('/merchant/onboarding',{'operation':'review_list','params':{}},web)
        self.assertEqual(status,200,value);self.assertEqual(value['result']['applications'],[])
        self.c.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.uid,))
        self.assertEqual(self.request('/merchant/onboarding',{'operation':'review_list','params':{}},web)[0],403)
    def test_origin_bearer_role_duplicate_cookie_csrf_rejected(self):
        body={'scene':'shop1','action':'BEGIN'}
        self.assertEqual(self.request('/community/session/wechat',body)[0],403)
        self.assertEqual(self.request('/community/session/wechat',body,{'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/community/session/wechat',dict(body,role='REVIEWER'),{'Origin':fixture.ORIGIN})[0],400)
        self.assertEqual(self.request('/community/session/wechat',body,{'Origin':fixture.ORIGIN,'X-Community-Session':self.mini})[0],403)
        mini={'scene':'shop1','challenge':self.challenge,'action':'DESCRIBE'}
        self.assertEqual(self.request('/mini/reviewer-login',mini,{'Origin':fixture.ORIGIN,'X-Community-Session':self.mini})[0],403)
        self.assertEqual(self.request('/mini/reviewer-login',mini,[('X-Community-Session',self.mini),('X-Community-Session',self.mini)])[0],400)
        self.assertEqual(self.request('/community/session/wechat',body,[('Origin',fixture.ORIGIN),('Cookie','a=b'),('Cookie','a=c')])[0],400)
        self.assertEqual(self.request('/community/session/wechat',{'scene':'shop1','challenge':self.challenge,'action':'FINISH'},{'Origin':fixture.ORIGIN,'Cookie':self.cookie.split(';')[0]})[0],403)
