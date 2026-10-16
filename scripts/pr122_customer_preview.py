"""Authenticated version-bound previews from encrypted, protected source history.

Only independently reviewed application frontend code may enter this source.
Customer uploads are never executable previews. No filesystem webroot or model API.
"""
import base64
import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit
from scripts.pr122_customer_core import canonical,digest,Denied,identifier
from scripts.pr122_customer_change_authority import load
from scripts.pr122_customer_changes import Changes

PREFIX='/customer/center/preview/'
TYPES={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'application/javascript; charset=utf-8','.json':'application/json; charset=utf-8','.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp','.svg':'image/svg+xml'}

def route(project,path,version):
    return PREFIX+identifier(project)+'/'+digest(path.encode())+'/'+version

def records(c,uid,project):
    p,_,_=c.project(uid,project,{'OWNER'});d=load(c)
    return d,[r for r in d['previews'] if r['project']==project and r['owner']==uid and r['project_revision']==p['revision']]

def listing(c,uid,project):
    _,rows=records(c,uid,project)
    return {'project':project,'pages':[{'path':r['page'],'sha256':r['page_sha256'],'url':route(project,r['page'],r['page_sha256'])} for r in rows if r['page'].endswith(('.html','/')) and r.get('execution_scope')=='TRUSTED_CUSTOMER_FRONTEND']}

def original(c,uid,project,page_key,version):
    d,rows=records(c,uid,project)
    found=next((r for r in rows if digest(r['page'].encode())==page_key and r['page_sha256']==version),None)
    if not found or found.get('execution_scope')!='TRUSTED_CUSTOMER_FRONTEND':raise Denied('CURRENT_TRUSTED_APPLICATION_PREVIEW_REQUIRED')
    row=c.db.execute('SELECT payload FROM change_authority_history WHERE revision=?',(d['revision'],)).fetchone()
    if not row:raise Denied('PREVIEW_SOURCE_HISTORY_REQUIRED')
    signed=json.loads(c.decrypt(row[0],'change-authority-source:'+str(d['revision'])))['payload']
    if digest(canonical(signed))!=d['source_sha256']:raise Denied('PREVIEW_SOURCE_DRIFT')
    for source in signed['previews']:
        if source['project']==project and source['manifest_sha256']==found['manifest_sha256']:
            raw=base64.b64decode(source['blobs'][version],validate=True)
            if digest(raw)!=version:raise Denied('PREVIEW_BYTES_DRIFT')
            return found,raw,rows
    raise Denied('PREVIEW_SOURCE_NOT_FOUND')

class Rewriter(HTMLParser):
    """Rewrites only registered asset/page URLs; preserves code as reviewed.
    Unknown local resource references fail closed rather than use mutable webroot.
    """
    def __init__(self,project,page,rows):
        super().__init__(convert_charrefs=False);self.project=project;self.page=page;self.rows=rows;self.out=[];self.scripts=[];self.styles=[];self.capture=None;self.text=[]
    def url(self,value,resource):
        from posixpath import normpath,dirname
        u=urlsplit(value)
        if u.scheme or u.netloc or u.query:raise Denied('PREVIEW_EXTERNAL_OR_MUTABLE_URL')
        if value.startswith('#'):return value
        path=normpath(u.path if u.path.startswith('/') else dirname(self.page.rstrip('/')+'/index.html' if self.page.endswith('/') else self.page)+'/'+u.path)
        record=next((r for r in self.rows if r['page']==path or r['page']==path+'/'),None)
        if not record:
            # Links out to the public site are navigation, never resource loading.
            if not resource and path in ('/','/customer/center/'):return path
            raise Denied('PREVIEW_RESOURCE_NOT_IN_MANIFEST')
        return route(self.project,record['page'],record['page_sha256'])+('#'+u.fragment if u.fragment else '')
    def handle_starttag(self,tag,attrs):
        if tag in ('base','iframe','object','embed','form'):raise Denied('PREVIEW_ACTIVE_EMBED_REQUIRES_ADAPTER')
        output=[]
        for key,value in attrs:
            if key.lower().startswith('on') or key in ('srcdoc','srcset','style','formaction'):raise Denied('PREVIEW_ATTRIBUTE_REQUIRES_ADAPTER')
            if value is not None and key in ('src','href','poster'):
                value=self.url(value,not(tag=='a' and key=='href'))
            output.append(key if value is None else key+'="'+html.escape(value,quote=True)+'"')
        self.out.append('<'+tag+(' '+' '.join(output) if output else '')+'>')
        if tag in ('script','style'):self.capture=tag;self.text=[]
    def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs);self.out[-1]=self.out[-1][:-1]+'/>'
    def handle_endtag(self,tag):
        if self.capture==tag:
            (self.scripts if tag=='script' else self.styles).append(''.join(self.text));self.capture=None
        self.out.append('</'+tag+'>')
    def handle_data(self,data):
        self.out.append(data)
        if self.capture:self.text.append(data)
    def handle_entityref(self,name):self.out.append('&'+name+';')
    def handle_charref(self,name):self.out.append('&#'+name+';')
    def handle_comment(self,data):self.out.append('<!--'+data+'-->')
    def handle_decl(self,decl):self.out.append('<!'+decl+'>')

def render(c,uid,project,page_key,version):
    found,raw,rows=original(c,uid,project,page_key,version)
    path=found['page'];suffix=next((x for x in TYPES if path.endswith(x)),'.html' if path.endswith('/') else None)
    if suffix not in TYPES:raise Denied('PREVIEW_MIME_NOT_ALLOWED')
    if suffix!='.html':
        # CSS url/import and JS module/fetch paths need a reviewed project adapter;
        # do not silently fall back to an unversioned public resource.
        if suffix in ('.css','.js') and re.search(rb'(?i)(url\s*\(|@import|\bimport\s|\bfetch\s*\(|XMLHttpRequest|WebSocket|serviceWorker)',raw):raise Denied('PREVIEW_NETWORK_ADAPTER_REQUIRED')
        return raw,TYPES[suffix],"default-src 'none'; frame-ancestors 'none'; sandbox"
    parser=Rewriter(project,path,rows);parser.feed(raw.decode('utf-8'));parser.close()
    if parser.capture:raise Denied('PREVIEW_INCOMPLETE_DOCUMENT')
    if any(re.search(r'(?i)(url\s*\(|@import)',css) for css in parser.styles):raise Denied('PREVIEW_INLINE_RESOURCE_ADAPTER_REQUIRED')
    body=''.join(parser.out)
    footer='<link rel="stylesheet" href="/customer/center/feedback.css">'+Changes(c).preview_footer(uid,project,path,version)
    # Server-generated context is outside source code; it is never a client claim.
    body=body.replace('</body>',footer+'</body>',1) if '</body>' in body else body+footer
    def hashes(items):return ' '.join("'sha256-"+base64.b64encode(bytes.fromhex(digest(x.encode()))).decode()+"'" for x in items)
    csp="default-src 'none'; script-src 'self' "+hashes(parser.scripts)+"; style-src 'self' "+hashes(parser.styles)+"; img-src 'self'; connect-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'; worker-src 'none'"
    # Feedback is same-origin API only. Preview code is trusted application code
    # (same privilege as customer app.js), never customer-supplied documents.
    csp=csp.replace("connect-src 'none'","connect-src https://wenwenwenyiyiyi.work/customer/center/api/")
    return body.encode(),TYPES['.html'],csp


def served(c,uid,project,page_key,version,rendered):
    """Called after a successful HTTP write, never from a customer POST.
    This proves authenticated bytes served, not browser visual acceptance/TLS.
    """
    import secrets
    with c.tx():
        found,_,_=original(c,uid,project,page_key,version)
        eid='pv_'+secrets.token_hex(16)
        payload={'project':project,'actor':uid,'page':found['page'],'page_sha256':version,'manifest_sha256':found['manifest_sha256'],'artifact_sha256':found['artifact_sha256'],'render_sha256':digest(rendered),'source_commit':found['source_commit'],'authority_revision':load(c)['revision'],'created':c.now(),'evidence':'AUTHENTICATED_HTTP_BYTES_SERVED','browser_acceptance':'NOT_ESTABLISHED','tls_acceptance':'NOT_ESTABLISHED'}
        c.db.execute('INSERT INTO preview_serves VALUES(?,?,?,?,?,?,?,?)',(eid,project,uid,found['manifest_sha256'],version,payload['render_sha256'],c.encrypt(canonical(payload),eid),c.now()))
        c.audit(project,uid,'PRIVATE_PREVIEW_SERVED',digest(canonical(payload)))
    return {'id':eid,'sha256':digest(canonical(payload))}
