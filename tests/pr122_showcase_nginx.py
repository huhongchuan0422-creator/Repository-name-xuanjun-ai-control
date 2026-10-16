"""Hosted/local isolated Nginx HTTP acceptance; never installs production config."""
import argparse
import http.client
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from scripts.pr122_showcase import need,CSP


def verify(public,report):
    nginx=shutil.which('nginx');need(nginx is not None,'NGINX_REQUIRED')
    with tempfile.TemporaryDirectory(prefix='showcase-nginx-') as td:
        root=Path(td);root.chmod(0o755);shutil.copytree(public/'showcase',root/'public/showcase')
        test=root/'public/showcase/assets/probe.mjs';test.write_text('export const simulationOnly=true;')
        source=Path('deploy/pr122-showcase/locations.conf').read_text()
        source=source.replace('/var/lib/xuanjun-showcase/current/public',str(root/'public'))
        snippet=root/'showcase.conf';snippet.write_text(source)
        config=root/'nginx.conf';config.write_text('daemon off; pid '+str(root/'nginx.pid')+'; error_log '+str(root/'error.log')+'; events {} http { access_log off; server { listen 127.0.0.1:18795; server_name localhost; include '+str(snippet)+'; } }')
        subprocess.run([nginx,'-t','-c',str(config)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        process=subprocess.Popen([nginx,'-c',str(config)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        def request(path,method='GET'):
            client=http.client.HTTPConnection('127.0.0.1',18795,timeout=2)
            try:client.request(method,path);r=client.getresponse();return r.status,dict(r.getheaders()),r.read()
            finally:client.close()
        try:
            for attempt in range(40):
                try:
                    if request('/showcase/')[0]==200:break
                except OSError:time.sleep(.05)
            else:raise RuntimeError('ISOLATED_NGINX_NOT_READY')
            checked=0
            for file in (root/'public/showcase').rglob('*'):
                if not file.is_file():continue
                status,headers,raw=request('/'+file.relative_to(root/'public').as_posix())
                need(status==200 and raw==file.read_bytes(),'NGINX_PUBLIC_BYTES')
                need(headers.get('Content-Security-Policy')==CSP and headers.get('X-Content-Type-Options')=='nosniff','NGINX_SECURITY_HEADERS');checked+=1
            for path in ('/showcase','/showcase/en','/showcase/projects','/showcase/projects/community-payment','/showcase/projects/community-payment/views/merchant/v1'):
                status,headers,_=request(path);need(status==308 and headers['Location'].endswith(path+'/'),'DIRECTORY_CANONICAL_REDIRECT')
            need(request('/showcase/assets/probe.mjs')[1]['Content-Type']=='application/javascript','MJS_MIME')
            need(request('/showcase/nonexistent-test-resource')[0]==404,'UNKNOWN_PATH_404')
            need(request('/showcase/','POST')[0]==403,'POST_DENIED')
            result={'status':'PASS','scope':'Isolated real Nginx on loopback HTTP; not production TLS','files_checked':checked,'redirects':5,'mjs_mime':'PASS','404':True,'403':True,'production_changes':0}
            report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
        finally:process.terminate();process.wait(timeout=10)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--public',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();verify(a.public,a.report)
