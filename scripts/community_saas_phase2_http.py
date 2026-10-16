"""Stage5 Phase2 offline loopback HTTP. Requires injected server-side principals.

No provider callbacks, production credentials, automatic grants or payment
execution. The socket binds only 127.0.0.1; never expose it to the internet.
"""
import hmac
import json
import math
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
from scripts.community_saas_phase2 import Principal,serialize_response

MAX_BODY=16384
def make_handler(service,principals):
    if not isinstance(principals,dict) or not principals:
        raise ValueError("NO_SERVER_PRINCIPAL_CONFIG")
    for token,principal in principals.items():
        if (type(token) is not str or len(token)<32 or not isinstance(principal,Principal)):
            raise ValueError("INVALID_SERVER_PRINCIPAL_CONFIG")
    class Handler(BaseHTTPRequestHandler):
        server_version="SaaSOffline/1"
        def log_message(self,*args):pass
        def do_GET(self):
            paths={"/offline/saas-panel":"saas-panel.html",
                   "/offline/saas-panel.mjs":"saas-panel.mjs"}
            host=self.headers.get("Host","")
            expected={"127.0.0.1:"+str(self.server.server_port),
                      "localhost:"+str(self.server.server_port)}
            if host not in expected:return self.answer(403,{"error":"HOST_DENIED"})
            asset=paths.get(self.path)
            if not asset:return self.answer(404,{"error":"NOT_FOUND"})
            path=Path(__file__).resolve().parents[1]/"demos"/"community-local-e2e"/asset
            if not path.is_file():return self.answer(404,{"error":"ASSET_NOT_FOUND"})
            blob=path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8" if asset.endswith(".html") else "text/javascript; charset=utf-8")
            self.send_header("Content-Length",str(len(blob)))
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Security-Policy","default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'")
            self.send_header("X-Content-Type-Options","nosniff")
            self.end_headers();self.wfile.write(blob)
        def do_POST(self):
            if self.path!="/offline/saas":
                return self.answer(404,{"error":"NOT_FOUND"})
            host=self.headers.get("Host","")
            expected={"127.0.0.1:"+str(self.server.server_port),"localhost:"+str(self.server.server_port)}
            origin=self.headers.get("Origin")
            if host not in expected or (origin is not None and origin!="http://"+host):
                return self.answer(403,{"error":"ORIGIN_DENIED"})
            token=self.headers.get("X-Offline-Token","")
            principal=next((p for t,p in principals.items() if hmac.compare_digest(t,token)),None)
            if principal is None:return self.answer(403,{"error":"FORBIDDEN"})
            typ=self.headers.get("Content-Type","").split(";",1)[0].strip().lower()
            if typ!="application/json":return self.answer(415,{"error":"JSON_REQUIRED"})
            try:
                length=int(self.headers.get("Content-Length",""))
                if not 0<length<=MAX_BODY:raise ValueError
            except ValueError:
                return self.answer(400,{"error":"INVALID_LENGTH"})
            self.connection.settimeout(3.0)
            try:
                raw=self.rfile.read(length)
                if len(raw)!=length:raise ValueError("TRUNCATED_BODY")
                def pairs(v):
                    result={}
                    for k,x in v:
                        if k in result:raise ValueError("DUPLICATE_JSON_KEY")
                        result[k]=x
                    return result
                def finite_float(token):
                    value=float(token)
                    if not math.isfinite(value):
                        raise ValueError("NONFINITE_JSON")
                    return value
                body=json.loads(raw,object_pairs_hook=pairs,parse_float=finite_float,
                                parse_constant=lambda x:(_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
                if type(body) is not dict or set(body)!={"operation","params","at"}:
                    raise ValueError("INVALID_PAYLOAD")
                value=service.dispatch(principal,body["operation"],body["params"],body["at"])
                return self.answer(200,{"result":value,"offline_only":True})
            except (ValueError,TypeError,KeyError,PermissionError) as error:
                return self.answer(400,{"error":str(error)})
            except TimeoutError:
                return self.answer(408,{"error":"TIMEOUT"})
        def answer(self,status,value):
            raw=serialize_response(value).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Content-Length",str(len(raw)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Security-Policy","default-src 'none'")
            self.end_headers();self.wfile.write(raw)
    return Handler

def serve(service,principals,port=0):
    if type(port) is not int or not (port==0 or 1024<=port<=65535):
        raise ValueError("INVALID_PORT")
    return HTTPServer(("127.0.0.1",port),make_handler(service,principals))
