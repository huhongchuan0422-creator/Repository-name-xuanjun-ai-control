"""Loopback-only browser harness; reuses existing ephemeral demo service.

This is a test adapter, not an Internet-facing preview service or installer.
"""
import argparse
import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlsplit
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.community_demo_api import serve_local

def serve(stage, port=0):
    stage=stage.resolve()
    if (stage/'MANIFEST.json').is_symlink():raise ValueError('UNSAFE_STAGE')
    manifest=json.loads((stage/'MANIFEST.json').read_text())
    if manifest.get('production_approved') is not False:raise ValueError('TEST_ONLY')
    public=(stage/'public').resolve()
    policy=json.loads((stage/'release-metadata/inline-csp.json').read_text())['policy']
    server=serve_local(port=port)
    parent=server.RequestHandlerClass
    class Handler(parent):
        def do_GET(self):
            expected='127.0.0.1:'+str(self.server.server_port)
            if self.headers.get('Host')!=expected:return self.send_json(403,{'error':'LOOPBACK_ONLY'})
            path=unquote(urlsplit(self.path).path)
            if '\\' in path or '\x00' in path or '..' in Path(path).parts:
                return self.send_json(403,{'error':'PATH_DENIED'})
            if any(part.startswith('.') for part in Path(path).parts if part!='/'):
                return self.send_json(403,{'error':'PATH_DENIED'})
            target=public/path.lstrip('/')
            options=[target/'index.html'] if path.endswith('/') else [target,Path(str(target)+'.html'),target/'index.html']
            target=next((p for p in options if p.is_file() and not p.is_symlink()),None)
            if target is None:return self.send_json(404,{'error':'NOT_FOUND'})
            if not target.resolve().is_relative_to(public):return self.send_json(403,{'error':'PATH_DENIED'})
            raw=target.read_bytes();self.send_response(200)
            self.send_header('Content-Type',mimetypes.guess_type(target)[0] or 'application/octet-stream')
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Content-Security-Policy',policy)
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers();self.wfile.write(raw)
    server.RequestHandlerClass=Handler
    return server

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);p.add_argument('--port',type=int,default=18792);a=p.parse_args()
    server=serve(a.stage,a.port)
    print(json.dumps({'status':'LOOPBACK_TEST_ONLY','port':server.server_port}),flush=True)
    try:server.serve_forever()
    finally:server.server_close()
