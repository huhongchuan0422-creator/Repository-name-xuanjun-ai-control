"""Real Unix HTTP journey for isolated preview role entrypoints.

Synthetic fixture identities/data only. This proves redirect/cookie/CSRF/workspace
wiring, not real WeChat login, production auth, payment or deployment.
"""
import json,os,pathlib,socket,subprocess,tempfile,time,unittest,urllib.parse

ROOT=pathlib.Path(__file__).resolve().parents[1]
HOST='community-preview.wenwenwenyiyiyi.work'
ORIGIN='https://'+HOST

def request(sock_path,method,path,headers=None,body=b''):
    headers=dict(headers or {})
    headers.setdefault('Host',HOST)
    headers.setdefault('X-Xuanjun-Client-IP','127.0.0.1')
    headers.setdefault('Connection','close')
    if body:
        headers.setdefault('Content-Type','application/json')
        headers['Content-Length']=str(len(body))
    raw=(method+' '+path+' HTTP/1.1\r\n'+''.join(k+': '+v+'\r\n' for k,v in headers.items())+'\r\n').encode()+body
    s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(5);s.connect(str(sock_path));s.sendall(raw)
    chunks=[]
    while True:
        try:part=s.recv(65536)
        except ConnectionResetError:break
        if not part:break
        chunks.append(part)
    s.close();data=b''.join(chunks);head,_,payload=data.partition(b'\r\n\r\n')
    lines=head.decode('iso-8859-1').split('\r\n');status=int(lines[0].split()[1]);out={}
    for line in lines[1:]:
        k,_,v=line.partition(':')
        out.setdefault(k.lower(),[]).append(v.strip())
    return status,out,payload

class IsolatedPreviewHttpJourney(unittest.TestCase):
    def setUp(self):
        if os.getuid()==0:self.skipTest('Unix peer UID contract requires non-root hosted runner')
        self.tmp=tempfile.TemporaryDirectory();self.sock=pathlib.Path(self.tmp.name)/'preview.sock'
        env=dict(os.environ,COMMUNITY_PREVIEW_ORIGIN=ORIGIN,COMMUNITY_PREVIEW_SOCKET=str(self.sock),COMMUNITY_PREVIEW_NGINX_UID=str(os.getuid()))
        self.proc=subprocess.Popen(['python','-I','-B',str(ROOT/'deploy/community-preview/server.py')],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        for _ in range(100):
            if self.sock.exists():break
            if self.proc.poll() is not None:self.fail(self.proc.communicate()[1])
            time.sleep(.05)
        self.assertTrue(self.sock.exists())
    def tearDown(self):
        if hasattr(self,'proc'):
            self.proc.terminate()
            try:self.proc.wait(5)
            except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()
        if hasattr(self,'tmp'):self.tmp.cleanup()
    def enter(self,path):
        status,h,_=request(self.sock,'GET',path+'?ignored=1')
        self.assertEqual(status,302,(status,h))
        location=h['location'][0];cookie=h['set-cookie'][0].split(';',1)[0]
        parsed=urllib.parse.urlsplit(location)
        self.assertEqual(parsed.query,'')
        self.assertTrue(parsed.fragment.startswith('preview='))
        context=json.loads(urllib.parse.unquote(parsed.fragment[len('preview='):]))
        status,_,body=request(self.sock,'GET',parsed.path+'?cache_bust=1')
        self.assertEqual(status,200,(status,body[:200]))
        return parsed.path,cookie,context,body
    def post(self,path,cookie,csrf,workspace,operation,params):
        body=json.dumps({'workspace':workspace,'operation':operation,'params':params},separators=(',',':')).encode()
        return request(self.sock,'POST',path,{'Cookie':cookie,'X-CSRF-Token':csrf,'Origin':ORIGIN},body)
    def test_three_role_redirects_follow_to_operational_original_center_requests(self):
        target,cookie,ctx,body=self.enter('/merchant')
        self.assertEqual((target,ctx['workspace']),('/merchant/workbench','merchant'))
        self.assertIn(b'workbench',body.lower())
        status,_,payload=self.post('/community/operations',cookie,ctx['csrf'],'merchant','community.orders',{})
        self.assertEqual(status,200,payload)

        target,cookie,ctx,body=self.enter('/community')
        self.assertEqual((target,ctx['workspace']),('/community/portal','community'))
        self.assertIn(b'community',body.lower())
        status,_,payload=self.post('/community/directory',cookie,ctx['csrf'],'community','mine',{})
        self.assertEqual(status,200,payload)

        target,cookie,ctx,body=self.enter('/platform')
        self.assertEqual((target,ctx['workspace']),('/community/portal','platform'))
        status,_,payload=self.post('/community/directory',cookie,ctx['csrf'],'platform','platform_overview',{})
        self.assertEqual(status,200,payload)
        result=json.loads(payload)['result']
        self.assertEqual(result['finance_status'],'UNCONFIRMED')

    def test_production_cookie_and_duplicate_private_ip_are_rejected(self):
        status,h,_=request(self.sock,'GET','/merchant')
        cookie=h['set-cookie'][0].split(';',1)[0]
        context=json.loads(urllib.parse.unquote(urllib.parse.urlsplit(h['location'][0]).fragment[len('preview='):]))
        body=json.dumps({'workspace':'merchant','operation':'community.orders','params':{}}).encode()
        status,_,_=request(self.sock,'POST','/community/operations',{'Cookie':cookie+'; __Host-xj_customer=forbidden','X-CSRF-Token':context['csrf'],'Origin':ORIGIN},body)
        self.assertEqual(status,403)
        status,_,_=request(self.sock,'GET','/',{'X-Xuanjun-Client-IP':'127.0.0.1, 8.8.8.8'})
        self.assertEqual(status,403)

if __name__=='__main__':unittest.main()
