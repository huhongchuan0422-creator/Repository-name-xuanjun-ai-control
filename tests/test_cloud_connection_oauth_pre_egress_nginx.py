"""Exact pre-egress config; real isolated Nginx, synthetic upstream, no live hosts."""
import hashlib,http.client,json,os,shutil,socket,ssl,subprocess,tempfile,threading,time,unittest
from http.server import BaseHTTPRequestHandler,HTTPServer
from socketserver import ThreadingMixIn
class ThreadingHTTPServer(ThreadingMixIn,HTTPServer):
 daemon_threads=True
from pathlib import Path
D=Path(__file__).resolve().parents[1]/'deployment/cloud-connection/oauth'
N=shutil.which('nginx')
if os.environ.get('REQUIRE_NGINX_TESTS')=='1' and not N:raise RuntimeError('Nginx required')
class Contract(unittest.TestCase):
 def test_exact_candidate(self):
  raw=(D/'nginx-vhost-pre-egress.conf.candidate').read_bytes()
  self.assertEqual(hashlib.sha256(raw).hexdigest(),'3084db85240b330699c06809dc29466303d8c65990c024199825b2ac94ef86b5')
  base=(D/'nginx-vhost.conf.candidate').read_text()
  old='        allow 8.208.119.115;\n        allow 127.0.0.1;\n        deny all;\n        include /etc/xuanjun-cloud-oauth/proxy-approved.conf;'
  self.assertEqual(raw.decode(),base.replace(old,'        return 403;'))
@unittest.skipUnless(N and shutil.which('openssl'),'Nginx/OpenSSL unavailable: NOT_RUN')
class Real(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.b=Path(self.tmp.name);self.p=None;self.hits=[]
  hits=self.hits
  class Handler(BaseHTTPRequestHandler):
   def do_GET(s):
    hits.append((s.command,s.path,dict(s.headers)));s.send_response(200);s.end_headers();s.wfile.write(b'upstream')
   do_POST=do_GET
   def log_message(*a):pass
  self.up=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.thread=threading.Thread(target=self.up.serve_forever,daemon=True);self.thread.start()
  self.http=self.port();self.https=self.port();self.nonce='a'*64
  self.web=self.b/'web';(self.web/'.well-known/acme-challenge').mkdir(parents=True);(self.web/'.well-known/acme-challenge/token').write_bytes(b'challenge')
  self.cert=self.b/'cert';self.key=self.b/'key';self.log=self.b/'peer.jsonl'
  subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=cloud-auth.wenwenwenyiyiyi.work','-keyout',str(self.key),'-out',str(self.cert)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
 def tearDown(self):
  self.stop();self.up.shutdown();self.up.server_close();self.thread.join(timeout=2);self.tmp.cleanup()
 def stop(self):
  if self.p:
   self.p.terminate()
   try:self.p.wait(timeout=3)
   except subprocess.TimeoutExpired:self.p.kill();self.p.wait(timeout=3)
   self.p=None
 def port(self):
  with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
 def start(self,observe=False,expired=False):
  self.stop();s=(D/'nginx-vhost-pre-egress.conf.candidate').read_text()
  s=s.replace('listen 80;','listen 127.0.0.1:%s;'%self.http).replace('listen 443 ssl;','listen 127.0.0.1:%s ssl;'%self.https).replace('/var/www/letsencrypt',str(self.web))
  s=s.replace('include /etc/xuanjun-cloud-oauth/tls-approved.conf;','ssl_certificate %s; ssl_certificate_key %s;'%(self.cert,self.key))
  proxy=(D/'nginx-proxy.conf.candidate').read_text().replace('127.0.0.1:18770','127.0.0.1:%s'%self.up.server_port)
  s=s.replace('include /etc/xuanjun-cloud-oauth/proxy-approved.conf;',proxy)
  extra=''
  if observe:
   start=int(time.time())-120 if expired else int(time.time())-2
   extra=(D/'peer-observation.http.conf.template').read_text().replace('__NONCE__',self.nonce).replace('__SECONDS_PATTERN__','|'.join(str(i) for i in range(start,start+60)))
   loc=(D/'peer-observation.location.conf.template').read_text().replace('__NONCE__',self.nonce).replace('__PRIVATE_LOG__',str(self.log))
   s=s.replace('    location = /introspect {',loc+'\n    location = /introspect {')
  conf=self.b/'nginx.conf';conf.write_text('daemon off; master_process off; pid %s; error_log stderr; events {} http { access_log off; client_body_temp_path %s/body; proxy_temp_path %s/proxy; fastcgi_temp_path %s/fastcgi; uwsgi_temp_path %s/uwsgi; scgi_temp_path %s/scgi; %s %s }'%((self.b/'pid',)+(str(self.b),)*5+(extra,s)))
  subprocess.run([N,'-t','-p',str(self.b),'-c',str(conf)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
  self.p=subprocess.Popen([N,'-p',str(self.b),'-c',str(conf)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  end=time.monotonic()+3
  while time.monotonic()<end:
   try:
    with socket.create_connection(('127.0.0.1',self.https),timeout=.1):return
   except OSError:time.sleep(.01)
  self.fail('Nginx did not start')
 def req(self,path,method='GET',tls=True,headers=None):
  # Ephemeral test cert only; no production TLS validation is bypassed.
  c=http.client.HTTPSConnection('127.0.0.1',self.https,timeout=2,context=ssl._create_unverified_context()) if tls else http.client.HTTPConnection('127.0.0.1',self.http,timeout=2)
  try:
   h={'Host':'cloud-auth.wenwenwenyiyiyi.work'};h.update(headers or {});c.request(method,path,headers=h);r=c.getresponse();return r.status,r.getheader('Location'),r.read()
  finally:c.close()
 def denied(self):
  for method in ('GET','POST'):
   for path in ('/introspect','/introspect?token=synthetic'):
    self.assertEqual(self.req(path,method,headers={'X-Forwarded-For':'8.208.119.115','X-Real-IP':'127.0.0.1','Authorization':'Bearer synthetic'})[0],403)
  self.assertEqual(self.hits,[])
 def test_introspect_methods_queries_headers_zero_upstream(self):self.start();self.denied()
 def test_other_routes_and_http01(self):
  self.start()
  for path in ('/authorize','/login','/github/callback','/consent','/token','/revoke','/.well-known/oauth-authorization-server'):self.assertEqual(self.req(path)[0],200)
  self.assertEqual(self.req('/not-allowed')[0],404)
  self.assertEqual(self.req('/.well-known/acme-challenge/token',tls=False),(200,None,b'challenge'))
  self.assertEqual(self.req('/.well-known/acme-challenge/missing',tls=False)[0],404)
  self.assertEqual(self.req('/.well-known/acme-challenge/token','POST',False)[0],405)
  self.assertEqual(self.req('/login',tls=False)[:2],(308,'https://cloud-auth.wenwenwenyiyiyi.work/login'))
 def test_observation_raw_peer_no_secrets_and_withdrawal(self):
  self.start(observe=True);path='/_xuanjun-connection-peer/'+self.nonce
  self.assertEqual(self.req(path,headers={'X-Forwarded-For':'8.208.119.115','Authorization':'Bearer DO_NOT_LOG'})[0],204)
  self.assertEqual(self.hits,[])
  row=json.loads(self.log.read_text().splitlines()[0]);self.assertEqual(set(row),{'nonce','utc','peer','method','status'});self.assertEqual(row['peer'],'127.0.0.1');self.assertEqual(row['nonce'],self.nonce);self.assertEqual(row['status'],204)
  self.assertNotIn('DO_NOT_LOG',self.log.read_text());self.denied()
  self.start();before=self.log.read_bytes();self.assertEqual(self.req(path)[0],404);self.assertEqual(self.log.read_bytes(),before);self.denied()
 def test_observation_method_query_wrong_nonce(self):
  self.start(observe=True);path='/_xuanjun-connection-peer/'+self.nonce
  for method in ('POST','HEAD'):self.assertEqual(self.req(path,method)[0],405)
  self.assertEqual(self.req(path+'?secret=synthetic')[0],400)
  self.assertEqual(self.req('/_xuanjun-connection-peer/'+'b'*64)[0],404);self.assertEqual(self.hits,[])
 def test_expired_window_fail_closed(self):
  self.start(observe=True,expired=True)
  self.assertEqual(self.req('/_xuanjun-connection-peer/'+self.nonce)[0],410)
  self.assertFalse(self.log.exists() and self.log.stat().st_size);self.denied()
if __name__=='__main__':unittest.main()
