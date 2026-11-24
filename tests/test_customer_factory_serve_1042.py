"""Real factory/core and full serve function; synthetic IO at Unix socket/OS boundary only.
No listener, production data/config, secrets or outbound provider calls.
"""
import base64,io,os,sqlite3,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import pr122_customer_ops as ops,pr122_customer_http as http
CONNECT=sqlite3.connect
class MemoryTransport:
 def __init__(self):
  self.input=io.BytesIO(b'GET /customer/center/api/me HTTP/1.1\r\nHost: wenwenwenyiyiyi.work\r\n\r\n');self.output=io.BytesIO()
 def makefile(self,*args,**kwargs):return self.input
 def sendall(self,data):self.output.write(data)
 def settimeout(self,value):pass
class SocketPath:
 def __init__(self,existing=False):self.existing=existing;self.unlinked=False
 def __str__(self):return '/run/xuanjun-customer-api/http.sock'
 def exists(self):return self.existing
 def is_symlink(self):return False
 def unlink(self,**kwargs):self.unlinked=True
class FactoryServe(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name);scan=root/'scan';scan.mkdir(mode=0o700);self.config={'keys':{'synthetic':base64.b64encode(b'k'*32).decode()},'active_key':'synthetic','providers':{}}
  self.addCleanup(patch.stopall);patch.object(ops,'ROOT',root/'center').start();scanner=ops.ClamScanner;patch.object(ops,'ClamScanner',side_effect=lambda:scanner(str(scan))).start();patch('sqlite3.connect',side_effect=lambda p,*a,**k:CONNECT(os.fspath(p),*a,**k)).start()
 def test_real_factory_constructs_pinned_center_without_providers(self):
  c=ops.factory(self.config)
  try:self.assertTrue((c.root/'center.sqlite').is_file());self.assertFalse(c.mail_ready);self.assertTrue(callable(c.session))
  finally:c.db.close()
 def test_full_serve_uses_real_factory_and_handler_with_cleanup(self):
  state={};socket=SocketPath();realpath=Path;factory_calls=[]
  def factory():factory_calls.append(1);return ops.factory(self.config)
  class Server:
   def __init__(self,path,handler):state['path']=path;self.handler=handler
   def serve_forever(self):
    wire=MemoryTransport();self.handler(wire,('synthetic',0),self);state['response']=wire.output.getvalue()
   def server_close(self):state['closed']=True
  with patch.object(http,'Path',side_effect=lambda p:socket if p=='/run/xuanjun-customer-api/http.sock' else realpath(p)),patch.object(http,'CustomerUnixServer',Server),patch('pwd.getpwnam',return_value=types.SimpleNamespace(pw_uid=1234)),patch('grp.getgrnam',return_value=types.SimpleNamespace(gr_gid=1234)),patch('os.chown') as chown,patch('os.chmod') as chmod:
   # Core creates only synthetic temp data; do not globally suppress its chmod/chown protections.
   chown.side_effect=lambda *a:None;chmod.side_effect=lambda p,m:None if p is socket else os_chmod(p,m)
   http.serve(factory,object(),'.')
  self.assertEqual(len(factory_calls),1);self.assertIn(b' 403 ',state['response'].split(b'\r\n',1)[0]);self.assertTrue(state['closed']);self.assertTrue(socket.unlinked)
 def test_existing_socket_refuses_before_factory_or_server(self):
  socket=SocketPath(True)
  with patch.object(http,'Path',return_value=socket),patch.object(http,'CustomerUnixServer') as server:
   with self.assertRaisesRegex(RuntimeError,'SOCKET_EXISTS_INSPECT_FIRST'):http.serve(lambda:self.fail('factory must not run'),object(),'.')
   server.assert_not_called();self.assertFalse(socket.unlinked)
os_chmod=os.chmod
if __name__=='__main__':unittest.main()
