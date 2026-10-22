"""Stateless JSON Streamable HTTP MCP application, loopback host only.

Factory is disabled by default. No worker/dispatch/cloud SDK or arbitrary path
tool. Standard issuer discovery is separate from MCP transport discovery.
"""
import json
import re
import time
from urllib.parse import urlsplit
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException
from .queue import Hold, unique
from .private_mcp import TOOLS, PROTOCOLS
from .oauth_resource import OAuthProjectResource

FILE_TOOL = {'name':'read_project_chunk',
    'description':'Read one approved project object chunk from an existing SUCCESS task. No arbitrary paths or execution.',
    'inputSchema': {'type':'object','properties': {
        'manifest_sha256':{'type':'string'},'request_id':{'type':'string'},
        'object_ref':{'type':'string'},'offset':{'type':'integer','minimum':0}},
        'required':['manifest_sha256','request_id','object_ref','offset'], 'additionalProperties':False},
    'annotations':{'readOnlyHint':True,'destructiveHint':False,'openWorldHint':False}}


def create_resource_app(authenticator, backend_factory, catalogs, audience,
                        enabled=False, clock=time.time):
    if enabled is not True:
        raise Hold('OAUTH_HTTP_DISABLED')
    u = urlsplit(audience)
    if u.scheme != 'https' or not u.hostname or u.username or u.query or u.fragment or u.path != '/mcp':
        raise Hold('OAUTH_RESOURCE_URL')
    metadata_url = u.scheme+'://'+u.netloc+'/.well-known/oauth-protected-resource'
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=16384, TRUSTED_HOSTS=['127.0.0.1','localhost'])

    @app.after_request
    def private(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    def refusal(status=401):
        response=jsonify(error='unauthorized' if status==401 else 'temporarily_unavailable')
        response.status_code=status
        if status==401:
            response.headers['WWW-Authenticate']='Bearer resource_metadata="'+metadata_url+'"'
        return response

    @app.get('/.well-known/oauth-protected-resource')
    @app.get('/.well-known/oauth-protected-resource/mcp')
    def metadata():
        return jsonify(resource=audience, authorization_servers=[authenticator.issuer],
            scopes_supported=['connection.status','project.files.read'],
            bearer_methods_supported=['header'])

    @app.route('/mcp',methods=['GET','POST','DELETE'])
    def mcp():
        if request.headers.get('Origin') or request.args:
            return jsonify(error='invalid_request'),400
        version=request.headers.get('MCP-Protocol-Version')
        if version is not None and not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',version):
            return jsonify(error='invalid_request'),400
        header=request.headers.get('Authorization','')
        try:
            if request.method != 'POST':
                authenticator.authenticate(header,None,None,int(clock()))
                return '',405,{'Allow':'POST'}
            if request.mimetype != 'application/json':
                return jsonify(error='invalid_request'),415
            raw=request.get_data(cache=False)
            if len(raw)>16384:return jsonify(error='invalid_request'),413
            try:message=json.loads(raw.decode(),object_pairs_hook=unique)
            except (Hold,ValueError,UnicodeError):return jsonify(error='invalid_request'),400
            if (type(message) is not dict or message.get('jsonrpc')!='2.0'
                    or set(message)-{'jsonrpc','id','method','params'}
                    or type(message.get('method')) is not str):raise ValueError()
            mid=message.get('id')
            if mid is not None and type(mid) not in (int,str):raise ValueError()
            params=message.get('params',{})
            if type(params) is not dict:raise ValueError()
            method=message['method']
            if version is not None and version not in PROTOCOLS and method!='initialize':
                return jsonify(error='invalid_request'),400
            if method=='tools/call' and 'id' in message:
                if set(params)-{'_meta'} != {'name','arguments'} or (
                        '_meta' in params and type(params['_meta']) is not dict):raise ValueError()
                name,args=params['name'],params['arguments']
                if name=='read_project_chunk':
                    # Authenticate before opening even the original queue DB.
                    entry=catalogs.get(args.get('manifest_sha256')) if type(args) is dict and type(args.get('manifest_sha256')) is str else None
                    if entry is None:raise Hold('OAUTH_CATALOG')
                    authenticator.authenticate(header,'project.files.read',entry[0].value['project'],int(clock()))
                    backend=backend_factory()
                    try:
                        resource=OAuthProjectResource(backend.db,catalogs,authenticator,True,clock)
                        value=resource.read(header,args,int(clock()))
                        result={'content':[{'type':'text','text':json.dumps(value,sort_keys=True)}],
                                'structuredContent':value,'isError':False}
                    finally:backend.close()
                elif name in ('connection_status','read_result_file'):
                    authenticator.authenticate(header,'connection.status',None,int(clock()))
                    backend=backend_factory()
                    try:
                        _,_,original=backend.lookup(args)
                        authenticator.authenticate(header,'connection.status',original['project'],int(clock()))
                        result=backend.call(name,args)
                    finally:backend.close()
                else:
                    authenticator.authenticate(header,None,None,int(clock()))
                    raise Hold('TOOL_NOT_ENROLLED')
            else:
                authenticator.authenticate(header,None,None,int(clock()))
                if method=='notifications/initialized' and 'id' not in message:return '',202
                if 'id' not in message:raise ValueError()
                if method=='initialize':
                    proposed=params.get('protocolVersion')
                    if type(proposed) is not str or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',proposed):raise ValueError()
                    negotiated=proposed if proposed in PROTOCOLS else PROTOCOLS[-1]
                    result={'protocolVersion':negotiated,'capabilities':{'tools':{}},
                            'serverInfo':{'name':'xuanjun-oauth-connection','version':'1.0.0'}}
                elif method=='ping':result={}
                elif method=='tools/list':result={'tools':TOOLS+[FILE_TOOL]}
                else:return jsonify(jsonrpc='2.0',id=mid,error={'code':-32601,'message':'Method not found'})
            return jsonify(jsonrpc='2.0',id=mid,result=result)
        except Hold as error:
            return refusal(503 if str(error) in ('OAUTH_INTROSPECTION_UNAVAILABLE','OAUTH_CLIENT_SECRET_UNAVAILABLE') else 401)
        except (ValueError,TypeError,KeyError):
            return jsonify(error='invalid_request'),400
        except HTTPException as error:
            return jsonify(error='invalid_request'),error.code
        except Exception:
            # Never render underlying SQL/filesystem/provider exceptions.
            return jsonify(error='HOLD_PRIVATE_TOOL'),503
    return app
