"""Bounded wire transport for the existing standard Authlib GitHub client.

No grant/token protocol, identities or project execution here. Parent deadline
spans token exchange and user retrieval; blocked wire work is cancellable.
"""
import http.client
import math
import multiprocessing
import os
import socket
import signal
import ssl
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from authlib.integrations.requests_client import OAuth2Session
from authlib.integrations.flask_client import FlaskOAuth2App
from flask import g
from requests import Response
from requests.structures import CaseInsensitiveDict
from .queue import Hold

# Child-to-parent error protocol is one byte of status and one fixed enum.
WIRE_REASONS=frozenset(('DNS','TLS','TIMEOUT','HTTP_STATUS','REDIRECT',
                        'LIMIT','OTHER'))


def _wire_reason(error):
    if isinstance(error, socket.gaierror): return 'DNS'
    if isinstance(error, (ssl.SSLError, ssl.CertificateError)): return 'TLS'
    if isinstance(error, (TimeoutError, socket.timeout)): return 'TIMEOUT'
    if isinstance(error, urllib.error.HTTPError):
        return 'REDIRECT' if 300 <= error.code < 400 else 'HTTP_STATUS'
    if isinstance(error, urllib.error.URLError):
        reason=error.reason
        if isinstance(reason, socket.gaierror): return 'DNS'
        if isinstance(reason, (ssl.SSLError, ssl.CertificateError)): return 'TLS'
        if isinstance(reason, (TimeoutError, socket.timeout)): return 'TIMEOUT'
    if isinstance(error, Hold):
        code=error.args[0] if len(error.args)==1 else None
        return {'GITHUB_REDIRECT_FORBIDDEN':'REDIRECT',
                'GITHUB_HTTP_STATUS':'HTTP_STATUS',
                'GITHUB_HEADER_LIMIT':'LIMIT',
                'GITHUB_BODY_LIMIT':'LIMIT'}.get(code,'OTHER')
    return 'OTHER'


TARGETS={
    ('POST','https://github.com/login/oauth/access_token'):16384,
    ('GET','https://api.github.com/user'):65536,
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise Hold('GITHUB_REDIRECT_FORBIDDEN')


def _wire(channel,url,method,data,headers,limit,budget,ca_file):
    try:
        # Limits are child-local, never mutate the HTTP server's parser.
        http.client._MAXLINE=8192
        http.client._MAXHEADERS=32
        context=ssl.create_default_context(cafile=ca_file)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),
            NoRedirect(),urllib.request.HTTPSHandler(context=context))
        req=urllib.request.Request(url,data=data,headers=headers,method=method)
        with opener.open(req,timeout=budget) as response:
            if response.getcode()!=200:raise Hold('GITHUB_HTTP_STATUS')
            if sum(len(k)+len(v)+4 for k,v in response.headers.items())>16384:
                raise Hold('GITHUB_HEADER_LIMIT')
            length=response.headers.get('Content-Length')
            if length is not None and (not length.isdecimal() or int(length)>limit):
                raise Hold('GITHUB_BODY_LIMIT')
            raw=response.read(limit+1)
            if len(raw)>limit:raise Hold('GITHUB_BODY_LIMIT')
        channel.send_bytes(b'1'+raw)
    except BaseException as error:
        # Fixed ASCII only, no raw upstream data or exception text crosses Pipe.
        channel.send_bytes(b'0'+_wire_reason(error).encode('ascii'))
    finally:channel.close()


class GithubNetwork:
    def __init__(self, offline_route=None, ca_file=None):
        # These are trusted test-harness transport dependencies, never fields
        # accepted by the production configuration loader or HTTP request.
        if offline_route is not None:
            u=urlsplit(offline_route)
            if u.scheme!='https' or u.hostname!='localhost' or u.path or u.query or u.fragment:
                raise Hold('OFFLINE_GITHUB_LOOPBACK_ONLY')
        elif ca_file is not None:
            raise Hold('GITHUB_PRODUCTION_TRUST_STORE')
        self.offline_route,self.ca_file=offline_route,ca_file

    def send(self,prepared,deadline):
        limit=TARGETS.get((prepared.method,prepared.url))
        if limit is None:raise Hold('GITHUB_FIXED_TARGET')
        remaining=deadline-time.monotonic()
        if not math.isfinite(remaining) or not 0<remaining<=5:
            raise Hold('GITHUB_TOTAL_DEADLINE')
        url=prepared.url
        if self.offline_route:
            url=self.offline_route+urlsplit(url).path
        headers={k:v for k,v in prepared.headers.items()
                 if k.lower() in ('authorization','content-type','accept','user-agent')}
        headers['Accept']='application/json'
        data=prepared.body
        if type(data) is str:data=data.encode()
        if data is not None and (type(data) is not bytes or len(data)>16384):
            raise Hold('GITHUB_REQUEST_BOUND')
        ctx=multiprocessing.get_context('spawn')
        receiving,sending=ctx.Pipe(duplex=False)
        child=ctx.Process(target=_wire,args=(sending,url,prepared.method,data,headers,
                                          limit,remaining,self.ca_file))
        try:
            child.start();sending.close()
            remaining=deadline-time.monotonic()
            if remaining<=0 or not receiving.poll(remaining):raise Hold('GITHUB_TOTAL_DEADLINE')
            raw=receiving.recv_bytes(max(limit+1, 1+max(map(len, WIRE_REASONS))))
            if time.monotonic()>=deadline:raise Hold('GITHUB_TOTAL_DEADLINE')
            if raw[:1]==b'0':
                reason=raw[1:].decode('ascii') if all(c<128 for c in raw[1:]) else ''
                if reason not in WIRE_REASONS:reason='OTHER'
                raise Hold('GITHUB_WIRE_'+reason)
            if raw[:1]!=b'1':raise Hold('GITHUB_WIRE_OTHER')
            response=Response()
            response.status_code=200;response.url=prepared.url;response.request=prepared
            response.headers=CaseInsensitiveDict({'Content-Type':'application/json'})
            response._content=raw[1:];response._content_consumed=True
            response.encoding='utf-8'
            return response
        finally:
            receiving.close();sending.close()
            if child.pid is not None:
                if child.is_alive():child.terminate()
                child.join(timeout=0.1)
                if child.is_alive():os.kill(child.pid,signal.SIGKILL);child.join(timeout=0.1)


class GithubSession(OAuth2Session):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.trust_env=False

    def send(self,prepared,**kwargs):
        # Authlib still validates state/PKCE, constructs and parses the standard
        # token exchange. Only Requests' wire send is replaced, not auth logic.
        deadline=getattr(g,'github_deadline',None)
        network=getattr(g,'github_network',None)
        if deadline is None or network is None:raise Hold('GITHUB_CALLBACK_CONTEXT')
        return network.send(prepared,deadline)


class GithubApp(FlaskOAuth2App):
    client_cls=GithubSession
