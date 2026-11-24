"""Real factory/identity/mail and full HTTP handler; synthetic provider and Unix transport only."""
import base64,hashlib,io,json,os,socket,sqlite3,struct,tempfile,types,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from scripts import pr122_customer_ops as ops,pr122_customer_http as http
from scripts.community_mail_delivery import ProviderBinding
from scripts.pr122_customer_source import TrustedNginxSource
CONNECT=sqlite3.connect
class Transport:
 idempotent_submission=True
 def __init__(self):self.calls=[]
 def authenticated(self,b):return True
 def submit(self,b,message,aid,key):self.calls.append(aid);return {'outcome':'ACCEPTED','detail_code':'ACCEPTED_BY_PROVIDER','provider_ref':'synthetic-'+aid}
class Wire:
 family=socket.AF_UNIX
 def __init__(self,data):self.input=io.BytesIO(data);self.output=io.BytesIO()
 def makefile(self,*a,**k):return self.input
 def sendall(self,b):self.output.write(b)
 def settimeout(self,t):pass
 def getsockopt(self,*a):return struct.pack('3i',123,1234,1234)
class FactoryMail(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name);scan=root/'scan';scan.mkdir(mode=0o700);self.config={'keys':{'synthetic':base64.b64encode(b'k'*32).decode()},'active_key':'synthetic','providers':{}};self.addCleanup(patch.stopall)
  patch.object(ops,'ROOT',root/'center').start();scanner=ops.ClamScanner;patch.object(ops,'ClamScanner',side_effect=lambda:scanner(str(scan))).start();patch('sqlite3.connect',side_effect=lambda p,*a,**k:CONNECT(os.fspath(p),*a,**k)).start()
  self.transport=Transport();self.mail=([ProviderBinding('Resend','synthetic','HTTP','https://api.resend.com',{'daily':100,'monthly':3000},True)],{'Resend':self.transport})
 def test_default_factory_binds_identity_without_changing_legacy_mail(self):
  c=ops.factory(self.config)
  try:
   tables={x[0] for x in c.db.execute("SELECT name FROM sqlite_master WHERE type='table'")};self.assertTrue({'identity_mappings','identity_mapping_history','identity_grants'}<=tables);self.assertFalse(c.mail_ready)
  finally:c.db.close()
 def test_configured_factory_registers_original_outbox_and_reads_receipt(self):
  c=ops.factory(self.config,mail_configuration=self.mail)
  try:
   self.assertTrue(c.mail_ready);self.assertEqual(c.register('synthetic@example.invalid','SyntheticPassword123!')['status'],'CHECK_VERIFICATION_CHANNEL');self.assertEqual(len(self.transport.calls),1)
   uid=c.db.execute('SELECT id FROM accounts').fetchone()[0];receipt=c.mail_receipt(uid,'VERIFY');self.assertEqual(receipt['state'],'ACCEPTED');self.assertNotIn('email',receipt);self.assertNotIn('token',receipt)
  finally:c.db.close()
 def test_full_http_handler_calls_configured_factory_and_original_mail(self):
  body=json.dumps({'email':'http-synthetic@example.invalid','password':'SyntheticPassword123!'}).encode();wire=Wire(('POST /customer/center/api/register HTTP/1.1\r\nHost: wenwenwenyiyiyi.work\r\nOrigin: https://wenwenwenyiyiyi.work\r\nX-Xuanjun-Client-IP: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n'%len(body)).encode()+body)
  http.App(lambda:ops.factory(self.config,mail_configuration=self.mail),object(),'https://wenwenwenyiyiyi.work','.',source_identity=TrustedNginxSource(1234)).handler()(wire,('synthetic',0),object())
  head,result=wire.output.getvalue().split(b'\r\n\r\n',1);self.assertIn(b' 200 ',head.split(b'\r\n',1)[0]);self.assertEqual(json.loads(result)['status'],'CHECK_VERIFICATION_CHANNEL');self.assertEqual(len(self.transport.calls),1)
 def test_private_mail_config_binding_and_login_only_rejection(self):
  c=dict(self.config,mail_provider_config='/synthetic/mail-config.json');self.assertTrue(ops.validate_runtime_contexts(c,c))
  with self.assertRaisesRegex(Exception,'MAIL_RUNTIME_BINDING'):ops.validate_runtime_contexts(c,dict(c,mail_provider_config='/synthetic/other.json'))
  c=dict(c,deployment_profile='OFFICIAL_LOGIN_ONLY_V1',providers={'smtp':{'synthetic':True}})
  with self.assertRaisesRegex(Exception,'LOGIN_ONLY_MAIL_SCOPE'):ops.validate_runtime_contexts(c,c)
 def test_failed_extension_closes_center(self):
  center=types.SimpleNamespace(db=Mock())
  with patch.object(ops,'Center',return_value=center),patch('scripts.pr122_customer_identity.install',side_effect=RuntimeError('synthetic-install-failure')):
   with self.assertRaisesRegex(RuntimeError,'synthetic-install-failure'):ops.factory(self.config)
  center.db.close.assert_called_once_with()
if __name__=='__main__':unittest.main()
