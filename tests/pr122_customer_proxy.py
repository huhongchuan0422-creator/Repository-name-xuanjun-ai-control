"""Real isolated Nginx->Unix peer/source and multi-client rate regression.
Requires disposable Hosted root only; no production service/config access.
"""
import concurrent.futures
import http.client
import json
import os
import pathlib
import pwd
import socketserver
import subprocess
import tempfile
import threading
import time
from scripts.pr122_customer_core import Center
from scripts.pr122_customer_http import App
from scripts.pr122_customer_source import TrustedNginxSource
from scripts.pr122_customer_providers import Providers
from tests.test_pr122_customer_center import CustomerTests

def main():
    fixture=CustomerTests();fixture.setUp();server=None;nginx=None
    try:
        with tempfile.TemporaryDirectory(prefix='pr122-proxy-') as folder:
            root=pathlib.Path(folder);root.chmod(0o755);sock=root/'app.sock';uid=pwd.getpwnam('www-data').pw_uid
            def factory():return Center(fixture.root,{'v1':fixture.key},'v1',clock=lambda:fixture.now,mail_ready=True,scanner=lambda b:True)
            server=socketserver.UnixStreamServer(str(sock),App(factory,Providers({}),'https://wenwenwenyiyiyi.work','deploy/pr122-customer-center/ui',source_identity=TrustedNginxSource(uid)).handler());sock.chmod(0o666)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            snippet=pathlib.Path('deploy/pr122-customer-center/locations.conf').read_text().replace('/run/xuanjun-customer-api/http.sock',str(sock))
            conf=root/'nginx.conf';conf.write_text('user www-data; pid '+str(root/'nginx.pid')+'; error_log '+str(root/'error.log')+' crit; events {} http { access_log off; server { listen 127.0.0.1:18796; '+snippet.replace('/var/log/nginx/xuanjun-customer-error.log',str(root/'proxy-errors.log'))+' } }')
            subprocess.run(['/usr/sbin/nginx','-t','-c',str(conf)],check=True,capture_output=True)
            nginx=subprocess.Popen(['/usr/sbin/nginx','-c',str(conf),'-g','daemon off;'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            def request(source,addr,password=None):
                c=http.client.HTTPConnection('127.0.0.1',18796,timeout=5,source_address=(source,0));body={'email':addr};op='request_reset'
                if password:op='login';body['password']=password
                c.request('POST','/customer/center/api/'+op,json.dumps(body),{'Host':'wenwenwenyiyiyi.work','Origin':'https://wenwenwenyiyiyi.work','Content-Type':'application/json','X-Xuanjun-Client-IP':'203.0.113.100','X-Forwarded-For':'198.51.100.200'})
                r=c.getresponse();status=r.status;r.read();c.close();return status
            for _ in range(50):
                try:
                    if request('127.0.0.2','probe@example.com')==200:break
                except OSError:time.sleep(.05)
            else:raise AssertionError('NGINX_NOT_READY')
            # source .2 consumed one request above. Different emails cannot reset
            # that source's total budget, spoofed client headers cannot change it.
            for i in range(39):assert request('127.0.0.2','unknown'+str(i)+'@example.com')==200
            assert request('127.0.0.2','overquota@example.com')==403
            assert request('127.0.0.3','owner@example.com','correct-password-123')==200
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                statuses=list(pool.map(lambda i:request('127.0.0.'+str(i+10),'parallel'+str(i)+'@example.com'),range(8)))
            assert statuses==[200]*8,statuses
            # Same opaque account with independent origins is not a sitewide key.
            keys=[x[0] for x in fixture.c.db.execute('SELECT k FROM rate_limits')]
            assert fixture.c.idx('auth-source:127.0.0.2') in keys
            assert fixture.c.idx('auth-source:203.0.113.100') not in keys
            report={'status':'PASS','scope':'Disposable root Nginx/Unix peer, real HTTP, 10 loopback source IPs; NOT production','malicious_source_limited':True,'other_source_login':True,'parallel_clients':8,'spoofed_forwarded_headers_ignored':True,'real_so_peercred':True}
            output=pathlib.Path(os.environ.get('XJ_CUSTOMER_REPORT_DIR','/tmp/pr122-customer'));output.mkdir(exist_ok=True);(output/'CUSTOMER_PROXY_REPORT.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
    finally:
        if nginx:nginx.terminate();nginx.wait(timeout=5)
        if server:server.shutdown();server.server_close();thread.join()
        fixture.c.db.close();fixture.tmp.cleanup()
if __name__=='__main__':main()
