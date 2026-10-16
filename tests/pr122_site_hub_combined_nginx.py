"""Actual isolated Nginx + frozen runtime, never production systemd or TLS."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import pr122_site_hub_combined as c

def main():
    root=Path(__file__).resolve().parents[1]
    frozen=root/'evidence/pr122-site-hub/PR122_SITE_HUB_REVIEW_ONLY.tar.gz'
    if not frozen.exists():frozen=root/'review-package-preview-final/PR122_SITE_HUB_REVIEW_ONLY.tar.gz'
    pins=json.loads((root/'deploy/pr122-site-hub-combined/HOST_PINS.json').read_text())
    entries=c.verified_entries(frozen.read_bytes(),pins);snippet,routes=c.locations(entries)
    nginx=shutil.which('nginx');assert nginx,'NGINX_BINARY_REQUIRED'
    with tempfile.TemporaryDirectory(prefix='pr122-nginx-fixture-') as folder:
        temp=Path(folder);os.chmod(temp,0o755)
        for name,raw in entries.items():
            if name.startswith(('overlay/public/','runtime/scripts/')):
                rel=name.removeprefix('overlay/') if name.startswith('overlay/') else name
                target=temp/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        security=temp/'security.conf';security.write_text('add_header Content-Security-Policy "default-src self" always;\nadd_header X-Content-Type-Options nosniff always;\n')
        snippet=snippet.replace(b'/etc/nginx/pr122-minimal-cutover/static-security.conf',str(security).encode())
        (temp/'locations.conf').write_bytes(snippet)
        (temp/'limit.conf').write_bytes(entries['runtime-config/http-limit.conf'])
        (temp/'nginx.conf').write_text('pid '+str(temp/'nginx.pid')+'; error_log '+str(temp/'error.log')+'; events {} http { access_log off; include /etc/nginx/mime.types; include '+str(temp/'limit.conf')+'; server { listen 127.0.0.1:18794; server_name '+c.HOST+'; root '+str(temp/'public')+'; include '+str(temp/'locations.conf')+'; location / { return 404; } location /p/ { return 418; } } }')
        subprocess.run([nginx,'-t','-c',str(temp/'nginx.conf')],check=True)
        runtime=subprocess.Popen([sys.executable,'-I','-B',str(temp/'runtime/scripts/pr122_site_hub_preview.py'),'--port','18793'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        server=None
        try:
            server=subprocess.Popen([nginx,'-c',str(temp/'nginx.conf'),'-g','daemon off;'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            ops=c.Ops();original_request=ops.request
            import http.client
            def request(path,method='GET',data=None,cookie=None,origin=None,https=False,extra=None):
                # This fixture intentionally uses plain loopback HTTP to Nginx.
                connection=http.client.HTTPConnection('127.0.0.1',18794,timeout=5)
                headers={'Host':c.HOST,'Sec-Fetch-Site':'same-origin'}
                if cookie:headers['Cookie']=cookie
                if origin:headers['Origin']=origin
                if extra:headers.update(extra)
                raw=None if data is None else json.dumps(data).encode()
                if raw is not None:headers['Content-Type']='application/json'
                try:
                    connection.request(method,path,raw,headers);r=connection.getresponse();return r.status,{k.lower():v for k,v in r.getheaders()},r.read()
                finally:connection.close()
            ops.request=request
            until=time.monotonic()+8
            while True:
                try:
                    assert original_request('/_preview/community-api/session')[0]==200
                    assert request('/visual/')[0]==200
                    break
                except (OSError,AssertionError):
                    if time.monotonic()>until:raise
                    time.sleep(.1)
            checked=0
            for route,(kind,target) in routes.items():
                status,headers,body=request(route)
                if kind=='redirect':assert status==308 and headers['location'].endswith(target);continue
                assert status==200,(route,status)
                assert c.sha(body)==c.sha(entries['overlay/public'+target]),route
                assert 'content-security-policy' in headers and headers['x-content-type-options']=='nosniff',route
                expected='application/javascript' if target.endswith(('.js','.mjs')) else 'text/css' if target.endswith('.css') else 'text/html'
                assert headers['content-type'].startswith(expected),(route,headers['content-type'])
                checked+=1
            assert request('/visual/unknown')[0]==404
            assert request('/customer/private/')[0]==404
            assert request('/p/legacy')[0]==418
            isolation=ops.preview_probe()
            print(json.dumps({'state':'PASS','scope':'Temporary Nginx and actual frozen preview; loopback HTTP, no systemd/TLS/domestic effects','exact_file_routes':checked,'redirect_routes':sum(k=='redirect' for k,_ in routes.values()),'negative_404':2,'prior_proxy_fixture':418,'mime_and_csp':True,'isolation':isolation},sort_keys=True))
        finally:
            for process in (server,runtime):
                if process is not None:
                    process.terminate()
                    try:process.communicate(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.communicate(timeout=5)

if __name__=='__main__':main()
