"""Ephemeral loopback HTTP only, isolated browser, synthetic form without OAuth data."""
import threading,json,time
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs
from playwright.sync_api import sync_playwright
counts={'post':0,'callback':0}
class Callback(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  if urlsplit(self.path).path!='/callback':self.send_response(404);self.end_headers();return
  counts['callback']+=1;self.send_response(200);self.end_headers();self.wfile.write(b'LOCAL SYNTHETIC CALLBACK')
second=ThreadingHTTPServer(('127.0.0.1',0),Callback);port2=second.server_port
allowed='http://127.0.0.1:'+str(port2)+'/callback'
class Form(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  mode=parse_qs(urlsplit(self.path).query).get('mode',['old'])[0]
  csp="default-src 'none'; form-action 'self'"+(' '+allowed if mode!='old' else '')+"; frame-ancestors 'none'"
  self.send_response(200);self.send_header('Content-Security-Policy',csp);self.send_header('Content-Type','text/html');self.end_headers()
  self.wfile.write(('<form method="post" action="/consent?mode='+mode+'"><button name="approve" value="yes">Allow synthetic test</button></form>').encode())
 def do_POST(self):
  counts['post']+=1;self.rfile.read(int(self.headers.get('Content-Length','0')))
  mode=parse_qs(urlsplit(self.path).query)['mode'][0]
  target=allowed if mode!='foreign' else allowed.replace('127.0.0.1','localhost')
  self.send_response(302);self.send_header('Location',target);self.end_headers()
first=ThreadingHTTPServer(('127.0.0.1',0),Form);port1=first.server_port
for server in (first,second):threading.Thread(target=server.serve_forever,daemon=True).start()
results=[]
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,chromium_sandbox=True,args=['--no-proxy-server','--disable-background-networking'])
  try:
   for mode in ('old','allowed','foreign'):
    context=browser.new_context(service_workers='block');context.set_default_timeout(5000);messages=[]
    def route(r):
     u=urlsplit(r.request.url)
     if u.scheme=='http' and u.hostname in ('127.0.0.1','localhost') and u.port in (port1,port2):r.continue_()
     else:r.abort()
    context.route('**/*',route);page=context.new_page();page.on('console',lambda message:messages.append(message.text))
    before=counts.copy();page.goto('http://127.0.0.1:'+str(port1)+'/form?mode='+mode);page.get_by_role('button',name='Allow synthetic test').click(no_wait_after=True)
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
     page.wait_for_timeout(50)
     posts=counts['post']-before['post'];callbacks=counts['callback']-before['callback'];violation=any('form-action' in x for x in messages)
     if mode=='allowed' and posts==1 and callbacks==1 and page.url==allowed:break
     if mode!='allowed' and posts==1 and callbacks==0 and violation:break
    result={'mode':mode,'posts':counts['post']-before['post'],'callbacks':counts['callback']-before['callback'],'csp_violation':any('form-action' in x for x in messages),'at_callback':page.url==allowed}
    assert result['posts']==1,result
    if mode=='allowed':assert result['callbacks']==1 and result['at_callback'] and not result['csp_violation'],result
    else:assert result['callbacks']==0 and not result['at_callback'] and result['csp_violation'],result
    results.append(result);context.close()
   print(json.dumps({'browser':browser.version,'transport':'isolated_loopback_http','real_oauth_data':False,'results':results},sort_keys=True))
  finally:browser.close()
finally:
 for server in (first,second):server.shutdown();server.server_close()
