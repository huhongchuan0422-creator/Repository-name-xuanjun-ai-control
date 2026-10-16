"""Real isolated Nginx regression for the deployed apex URL contract.

Loopback HTTP only; no production TLS/systemd or target-machine acceptance.
"""
import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import pr122_site_hub_experience_release as r


def main():
    repo=Path(__file__).resolve().parents[1]
    pins=json.loads(r.PINS.read_text())
    data=r.entries((repo/'evidence/pr122-site-hub-experience/PR122_SITE_HUB_REVIEW_ONLY.tar.gz').read_bytes(),pins)
    nginx=shutil.which('nginx')
    assert nginx,'REAL_NGINX_REQUIRED'
    with tempfile.TemporaryDirectory(prefix='pr122-ui-nginx-') as folder:
        temp=Path(folder);temp.chmod(0o755)
        for name,raw in data.items():
            if name.startswith('overlay/public/'):
                p=temp/name.removeprefix('overlay/')
                p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        security=temp/'security.conf'
        security.write_text('add_header Content-Security-Policy "default-src self" always;\nadd_header X-Content-Type-Options nosniff always;\n')
        snippet,new_routes=r.routes(data)
        snippet=snippet.replace(b'/etc/nginx/pr122-minimal-cutover/static-security.conf',str(security).encode())
        (temp/'new.conf').write_bytes(snippet)
        # These are the actual apex canonical aliases observed on the target.
        aliases=('about','capabilities','contact','custom-ai','features','guides',
                 'integrations','labs','privacy','search','solutions','terms','use-cases')
        legacy='location = / { include '+str(security)+'; try_files /index.html =404; }\n'
        for name in aliases:
            legacy+='location = /'+name+' { include '+str(security)+'; try_files /'+name+'.html =404; }\n'
        for prefix in ('about','capabilities','custom-ai','guides','solutions','labs',
                       'assets','zh-cn','en','zh-tw','ja','ko','es','fr','de'):
            legacy+='location ^~ /'+prefix+'/ { include '+str(security)+'; try_files $uri $uri.html $uri/index.html =404; }\n'
        legacy+='location / { return 404; }\nlocation /p/ { return 418; }\n'
        (temp/'legacy.conf').write_text(legacy)
        (temp/'limit.conf').write_bytes(data['runtime-config/http-limit.conf'])
        config=temp/'nginx.conf'
        config.write_text('pid '+str(temp/'nginx.pid')+'; error_log '+str(temp/'error.log')+'; events {} http { access_log off; include /etc/nginx/mime.types; include '+str(temp/'limit.conf')+'; server { listen 127.0.0.1:18795; root '+str(temp/'public')+'; include '+str(temp/'new.conf')+'; include '+str(temp/'legacy.conf')+'; } }')
        subprocess.run([nginx,'-t','-c',str(config)],check=True)
        server=subprocess.Popen([nginx,'-c',str(config),'-g','daemon off;'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        def request(path):
            conn=http.client.HTTPConnection('127.0.0.1',18795,timeout=5)
            try:
                conn.request('GET',path);response=conn.getresponse()
                return response.status,dict(response.getheaders()),response.read()
            finally:conn.close()
        try:
            until=time.monotonic()+8
            while True:
                try:
                    assert request('/')[0]==200;break
                except (OSError,AssertionError):
                    if time.monotonic()>until:raise
                    time.sleep(.1)
            expected=r.smoke_routes(data)
            assert '/about.html' not in expected and expected['/about']==('file','/about.html')
            assert request('/about.html')[0]==404,'Baseline intentionally denies raw root HTML URL'
            checked=0
            for route,(kind,target) in expected.items():
                status,headers,body=request(route)
                if kind=='redirect':
                    assert status==308 and headers['Location'].endswith(target),(route,status)
                    continue
                assert status==200,(route,status)
                assert body==data['overlay/public'+target],route
                assert 'Content-Security-Policy' in headers and headers['X-Content-Type-Options']=='nosniff',route
                checked+=1
            assert request('/p/legacy')[0]==418
            for path in ('/not-approved.html','/customer/private/','/visual/unknown'):
                assert request(path)[0]==404,path
            print(json.dumps({'state':'PASS','scope':'Hosted isolated real Nginx HTTP only',
                              'file_routes':checked,'canonical_root_aliases':14,
                              'raw_about_denied':True,'new_routes':len(new_routes),
                              'overlay_files':sum(n.startswith('overlay/public/') for n in data),
                              'production_changes':0},sort_keys=True))
        finally:
            server.terminate()
            try:server.communicate(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.communicate(timeout=5)


if __name__=='__main__':main()
