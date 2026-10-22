"""HTTP01 regression; live-Nginx cases use isolated loopback only."""
import hashlib,json,http.client,os,shutil,socket,subprocess,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'deployment/cloud-connection/oauth'
FINAL='nginx-vhost.conf.candidate'
BOOT='nginx-http01-bootstrap.conf.candidate'
class Contract(unittest.TestCase):
    def test_location_scoped_redirect(self):
        s=(D/FINAL).read_text()
        self.assertNotIn('return 308',s.split('location ^~ /.well-known/acme-challenge/')[0])
        self.assertIn('location / {\n        return 308 https://cloud-auth.wenwenwenyiyiyi.work$request_uri;',s)
        self.assertIn('try_files $uri =404;',s)
    def test_bootstrap_closed(self):
        s=(D/BOOT).read_text();self.assertIn('location / { return 503; }',s)
        for x in ('proxy_pass','listen 443','return 308','ssl_certificate'):self.assertNotIn(x,s)
    def test_manifest(self):
        m={e['path']:e for e in json.loads((D/'SOURCE_MANIFEST.json').read_text())['files']}
        for n in (FINAL,BOOT):
            p='deployment/cloud-connection/oauth/'+n;b=(ROOT/p).read_bytes()
            self.assertEqual((len(b),hashlib.sha256(b).hexdigest()),(m[p]['bytes'],m[p]['sha256']))
    def test_boundaries_retained(self):
        s=(D/FINAL).read_text();p=(D/'nginx-proxy.conf.candidate').read_text()
        for x in ('location = /introspect','deny all;','location / { return 404; }','client_max_body_size 16k;'):self.assertIn(x,s)
        for h in ('Forwarded','X-Forwarded-For','X-Forwarded-Proto','X-Real-IP'):self.assertIn('proxy_set_header '+h+' "";',p)
N=shutil.which('nginx')
if os.environ.get('REQUIRE_NGINX_TESTS')=='1' and (not N or not shutil.which('openssl')):raise RuntimeError('Required Nginx/OpenSSL missing')
@unittest.skipUnless(N and shutil.which('openssl'),'Nginx/OpenSSL unavailable: NOT_RUN')
class RealNginx(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.b=Path(self.tmp.name);self.p=None
        self.web=self.b/'web';(self.web/'.well-known/acme-challenge').mkdir(parents=True)
        (self.web/'.well-known/acme-challenge/token').write_bytes(b'public-challenge')
    def tearDown(self):
        if self.p:
            self.p.terminate()
            try:self.p.wait(timeout=5)
            except subprocess.TimeoutExpired:self.p.kill();self.p.wait(timeout=5)
        self.tmp.cleanup()
    def port(self):
        with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
    def start(self,name):
        port=self.port();s=(D/name).read_text().replace('listen 80;','listen 127.0.0.1:%d;'%port).replace('/var/www/letsencrypt',str(self.web))
        if name==FINAL:
            cert=self.b/'cert';key=self.b/'key'
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=cloud-auth.wenwenwenyiyiyi.work','-keyout',str(key),'-out',str(cert)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
            s=s.replace('listen 443 ssl;','listen 127.0.0.1:%d ssl;'%self.port()).replace('include /etc/xuanjun-cloud-oauth/tls-approved.conf;','ssl_certificate %s; ssl_certificate_key %s;'%(cert,key)).replace('include /etc/xuanjun-cloud-oauth/proxy-approved.conf;',(D/'nginx-proxy.conf.candidate').read_text())
        conf=self.b/'nginx.conf';conf.write_text('daemon off; master_process off; pid %s; error_log stderr; events {} http { access_log off; client_body_temp_path %s/body; proxy_temp_path %s/proxy; fastcgi_temp_path %s/fastcgi; uwsgi_temp_path %s/uwsgi; scgi_temp_path %s/scgi; %s }'%((self.b/'pid',)+(str(self.b),)*5+(s,)))
        subprocess.run([N,'-t','-p',str(self.b),'-c',str(conf)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
        self.p=subprocess.Popen([N,'-p',str(self.b),'-c',str(conf)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        end=time.monotonic()+3
        while time.monotonic()<end:
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.1):return port
            except OSError:time.sleep(.01)
        self.fail('Nginx failed to start')
    def req(self,port,path,method='GET',host='cloud-auth.wenwenwenyiyiyi.work'):
        c=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
        try:c.request(method,path,headers={'Host':host});r=c.getresponse();return r.status,r.getheader('Location'),r.read()
        finally:c.close()
    def test_final_challenge(self):
        p=self.start(FINAL);self.assertEqual(self.req(p,'/.well-known/acme-challenge/token'),(200,None,b'public-challenge'));self.assertEqual(self.req(p,'/.well-known/acme-challenge/missing')[0],404)
    def test_final_fixed_redirect(self):
        p=self.start(FINAL)
        for h in ('cloud-auth.wenwenwenyiyiyi.work','attacker.invalid'):self.assertEqual(self.req(p,'/authorize?state=sample',host=h)[:2],(308,'https://cloud-auth.wenwenwenyiyiyi.work/authorize?state=sample'))
    def test_bootstrap(self):
        p=self.start(BOOT);self.assertEqual(self.req(p,'/.well-known/acme-challenge/token'),(200,None,b'public-challenge'));self.assertEqual(self.req(p,'/.well-known/acme-challenge/missing')[0],404);self.assertEqual(self.req(p,'/authorize')[0],503);self.assertEqual(self.req(p,'/.well-known/acme-challenge/token','POST')[0],405)
if __name__=='__main__':unittest.main()
