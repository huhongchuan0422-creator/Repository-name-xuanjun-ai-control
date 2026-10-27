"""OAuth 2.1/PKCE authorization records for the task-center MCP resource.

The browser session remains the user authentication source.  MCP access
tokens are audience/scope bound and stored only as SHA-256 digests in the
canonical SQLite database.
"""
from __future__ import print_function

import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode,urlsplit


SCOPES=frozenset(('task:read','task:submit'))


def _hash(value):return hashlib.sha256(value.encode()).hexdigest()
def _b64sha(value):
    return base64.urlsafe_b64encode(hashlib.sha256(value.encode()).digest()).decode().rstrip('=')


class MCPAuthorizationStore(object):
    def __init__(self,connection_factory,tenant_id,issuer,resource,clock=time.time):
        self.connect=connection_factory;self.tenant_id=tenant_id
        self.issuer=issuer.rstrip('/');self.resource=resource;self.clock=clock
        db=self.connect()
        try:
            db.execute('''CREATE TABLE IF NOT EXISTS mcp_oauth_clients(
              tenant_id TEXT NOT NULL,client_id TEXT NOT NULL,
              redirect_uris_json TEXT NOT NULL,client_name TEXT NOT NULL,
              created_at REAL NOT NULL,PRIMARY KEY(tenant_id,client_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS mcp_oauth_codes(
              tenant_id TEXT NOT NULL,code_hash TEXT NOT NULL,client_id TEXT NOT NULL,
              redirect_uri TEXT NOT NULL,code_challenge TEXT NOT NULL,
              resource TEXT NOT NULL,scope_json TEXT NOT NULL,
              principal_id TEXT NOT NULL,project_id TEXT NOT NULL,
              expires_at REAL NOT NULL,used_at REAL,
              PRIMARY KEY(tenant_id,code_hash))''')
            db.execute('''CREATE TABLE IF NOT EXISTS mcp_oauth_tokens(
              tenant_id TEXT NOT NULL,token_hash TEXT NOT NULL,client_id TEXT NOT NULL,
              principal_id TEXT NOT NULL,project_id TEXT NOT NULL,
              resource TEXT NOT NULL,scope_json TEXT NOT NULL,
              created_at REAL NOT NULL,expires_at REAL NOT NULL,revoked_at REAL,
              PRIMARY KEY(tenant_id,token_hash))''')
            db.execute('''CREATE TABLE IF NOT EXISTS mcp_oauth_client_grants(
              tenant_id TEXT NOT NULL,client_id TEXT NOT NULL,grant_type TEXT NOT NULL,
              PRIMARY KEY(tenant_id,client_id,grant_type))''')
            db.execute('''CREATE TABLE IF NOT EXISTS mcp_oauth_refresh_tokens(
              tenant_id TEXT NOT NULL,token_hash TEXT NOT NULL,client_id TEXT NOT NULL,
              principal_id TEXT NOT NULL,project_id TEXT NOT NULL,
              resource TEXT NOT NULL,scope_json TEXT NOT NULL,
              created_at REAL NOT NULL,expires_at REAL NOT NULL,used_at REAL,
              PRIMARY KEY(tenant_id,token_hash))''')
            db.commit()
        finally:db.close()

    @staticmethod
    def _redirect(uri):
        if not isinstance(uri,str):
            raise ValueError('CHATGPT_REDIRECT_URI_REQUIRED')
        parsed=urlsplit(uri)
        if (parsed.scheme!='https' or parsed.hostname!='chatgpt.com' or
                parsed.username or parsed.password or parsed.fragment):
            raise ValueError('CHATGPT_REDIRECT_URI_REQUIRED')
        allowed=(parsed.path=='/connector_platform_oauth_redirect' or
                 parsed.path.startswith('/connector/oauth/'))
        if not allowed:raise ValueError('CHATGPT_REDIRECT_URI_REQUIRED')
        return uri

    def register(self,value):
        if not isinstance(value,dict):raise ValueError('DCR_OBJECT_REQUIRED')
        uris=value.get('redirect_uris')
        if not isinstance(uris,list) or not uris or len(uris)>4:
            raise ValueError('DCR_REDIRECT_URIS_REQUIRED')
        uris=[self._redirect(x) for x in uris]
        if value.get('token_endpoint_auth_method','none')!='none':
            raise ValueError('PUBLIC_PKCE_CLIENT_REQUIRED')
        grants=value.get('grant_types',['authorization_code'])
        if (not isinstance(grants,list) or
                any(not isinstance(grant,str) for grant in grants) or
                len(grants)!=len(set(grants)) or
                set(grants) not in ({'authorization_code'},
                                    {'authorization_code','refresh_token'})):
            raise ValueError('DCR_GRANT_TYPES_REJECTED')
        grants=['authorization_code']+(
          ['refresh_token'] if 'refresh_token' in grants else [])
        if value.get('response_types',['code'])!=['code']:
            raise ValueError('CODE_RESPONSE_ONLY')
        client_id='mcp-client-'+secrets.token_urlsafe(24)
        name=str(value.get('client_name') or 'ChatGPT MCP')[:96]
        now=self.clock();db=self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO mcp_oauth_clients VALUES (?,?,?,?,?)',(
              self.tenant_id,client_id,json.dumps(uris,separators=(',',':')),
              name,now))
            db.executemany('INSERT INTO mcp_oauth_client_grants VALUES (?,?,?)',
              [(self.tenant_id,client_id,grant) for grant in grants]);db.commit()
        except Exception:db.rollback();raise
        finally:db.close()
        return {'client_id':client_id,'client_id_issued_at':int(now),
          'redirect_uris':uris,'grant_types':grants,
          'response_types':['code'],'token_endpoint_auth_method':'none'}

    def authorize(self,session,params):
        required=('response_type','client_id','redirect_uri','code_challenge',
                  'code_challenge_method','state','resource')
        if any(not params.get(x) for x in required):
            raise ValueError('OAUTH_AUTHORIZE_PARAMETERS_REQUIRED')
        if params['response_type']!='code' or params['code_challenge_method']!='S256':
            raise ValueError('OAUTH_PKCE_S256_REQUIRED')
        if params['resource']!=self.resource:raise ValueError('OAUTH_RESOURCE_MISMATCH')
        requested=set((params.get('scope') or 'task:read task:submit').split())
        if not requested or not requested.issubset(SCOPES):
            raise ValueError('OAUTH_SCOPE_REJECTED')
        db=self.connect()
        try:
            row=db.execute('''SELECT redirect_uris_json FROM mcp_oauth_clients
              WHERE tenant_id=? AND client_id=?''',(self.tenant_id,
              params['client_id'])).fetchone()
            if row is None or params['redirect_uri'] not in json.loads(row[0]):
                raise ValueError('OAUTH_CLIENT_OR_REDIRECT_REJECTED')
            code=secrets.token_urlsafe(32);now=self.clock()
            db.execute('INSERT INTO mcp_oauth_codes VALUES (?,?,?,?,?,?,?,?,?,?,NULL)',(
              self.tenant_id,_hash(code),params['client_id'],params['redirect_uri'],
              params['code_challenge'],self.resource,
              json.dumps(sorted(requested),separators=(',',':')),
              session['principal_id'],'project-mcp',now+300));db.commit()
        finally:db.close()
        query=urlencode({'code':code,'state':params['state'],'iss':self.issuer})
        return params['redirect_uri']+('?' if '?' not in params['redirect_uri'] else '&')+query

    def exchange(self,params):
        grant=params.get('grant_type')
        if grant=='refresh_token':return self._refresh(params)
        if grant!='authorization_code':raise ValueError('OAUTH_GRANT_REJECTED')
        required=('grant_type','code','client_id','redirect_uri','code_verifier','resource')
        if any(not params.get(x) for x in required):raise ValueError('OAUTH_TOKEN_PARAMETERS_REQUIRED')
        if params['resource']!=self.resource:raise ValueError('OAUTH_RESOURCE_MISMATCH')
        now=self.clock();db=self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('''SELECT * FROM mcp_oauth_codes WHERE tenant_id=?
              AND code_hash=?''',(self.tenant_id,_hash(params['code']))).fetchone()
            if (row is None or row['expires_at']<=now or
                    row['client_id']!=params['client_id'] or
                    row['redirect_uri']!=params['redirect_uri'] or
                    row['resource']!=self.resource or
                    _b64sha(params['code_verifier'])!=row['code_challenge']):
                raise ValueError('OAUTH_CODE_OR_PKCE_REJECTED')
            if row['used_at'] is not None:
                raise ValueError('OAUTH_CODE_REPLAY_REJECTED')
            changed=db.execute('''UPDATE mcp_oauth_codes SET used_at=? WHERE
              tenant_id=? AND code_hash=? AND used_at IS NULL''',(now,
              self.tenant_id,_hash(params['code']))).rowcount
            if changed!=1:raise ValueError('OAUTH_CODE_REPLAY_REJECTED')
            token=secrets.token_urlsafe(40);expires=now+3600
            db.execute('INSERT INTO mcp_oauth_tokens VALUES (?,?,?,?,?,?,?,?,?,NULL)',(
              self.tenant_id,_hash(token),row['client_id'],row['principal_id'],
              row['project_id'],self.resource,row['scope_json'],now,expires))
            grants={item[0] for item in db.execute('''SELECT grant_type FROM
              mcp_oauth_client_grants WHERE tenant_id=? AND client_id=?''',(
              self.tenant_id,row['client_id']))}
            refresh=(secrets.token_urlsafe(48) if 'refresh_token' in grants else None)
            if refresh is not None:
                db.execute('''INSERT INTO mcp_oauth_refresh_tokens VALUES
                  (?,?,?,?,?,?,?,?,?,NULL)''',(self.tenant_id,_hash(refresh),
                  row['client_id'],row['principal_id'],row['project_id'],
                  self.resource,row['scope_json'],now,now+2592000))
            db.commit()
        except Exception:db.rollback();raise
        finally:db.close()
        result={'access_token':token,'token_type':'Bearer','expires_in':3600,
          'scope':' '.join(json.loads(row['scope_json']))}
        if refresh is not None:result['refresh_token']=refresh
        return result

    def _refresh(self,params):
        required=('grant_type','refresh_token','client_id','resource')
        if any(not params.get(x) for x in required):
            raise ValueError('OAUTH_TOKEN_PARAMETERS_REQUIRED')
        if params['resource']!=self.resource:raise ValueError('OAUTH_RESOURCE_MISMATCH')
        now=self.clock();db=self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('''SELECT * FROM mcp_oauth_refresh_tokens WHERE
              tenant_id=? AND token_hash=?''',(self.tenant_id,
              _hash(params['refresh_token']))).fetchone()
            if (row is None or row['expires_at']<=now or
                    row['client_id']!=params['client_id'] or
                    row['resource']!=self.resource):
                raise ValueError('OAUTH_REFRESH_REJECTED')
            if row['used_at'] is not None:
                raise ValueError('OAUTH_REFRESH_REPLAY_REJECTED')
            changed=db.execute('''UPDATE mcp_oauth_refresh_tokens SET used_at=?
              WHERE tenant_id=? AND token_hash=? AND used_at IS NULL''',(now,
              self.tenant_id,_hash(params['refresh_token']))).rowcount
            if changed!=1:raise ValueError('OAUTH_REFRESH_REPLAY_REJECTED')
            access=secrets.token_urlsafe(40);refresh=secrets.token_urlsafe(48)
            db.execute('INSERT INTO mcp_oauth_tokens VALUES (?,?,?,?,?,?,?,?,?,NULL)',(
              self.tenant_id,_hash(access),row['client_id'],row['principal_id'],
              row['project_id'],self.resource,row['scope_json'],now,now+3600))
            db.execute('''INSERT INTO mcp_oauth_refresh_tokens VALUES
              (?,?,?,?,?,?,?,?,?,NULL)''',(self.tenant_id,_hash(refresh),
              row['client_id'],row['principal_id'],row['project_id'],self.resource,
              row['scope_json'],now,now+2592000));db.commit()
        except Exception:db.rollback();raise
        finally:db.close()
        return {'access_token':access,'refresh_token':refresh,'token_type':'Bearer',
          'expires_in':3600,'scope':' '.join(json.loads(row['scope_json']))}

    def authenticate(self,authorization,required_scope):
        if not authorization or not authorization.startswith('Bearer '):
            return None
        token=authorization[7:].strip();now=self.clock();db=self.connect()
        try:
            row=db.execute('''SELECT * FROM mcp_oauth_tokens WHERE tenant_id=?
              AND token_hash=?''',(self.tenant_id,_hash(token))).fetchone()
            if (row is None or row['revoked_at'] is not None or
                    row['expires_at']<=now or row['resource']!=self.resource):
                return None
            scopes=set(json.loads(row['scope_json']))
            if required_scope not in scopes:return None
            return {'tenant_id':self.tenant_id,'principal_id':row['principal_id'],
              'project_id':row['project_id'],'scopes':sorted(scopes),
              'expires_at':row['expires_at']}
        finally:db.close()

    def protected_resource_metadata(self):
        return {'resource':self.resource,'authorization_servers':[self.issuer],
          'scopes_supported':sorted(SCOPES),'bearer_methods_supported':['header']}

    def authorization_server_metadata(self,base):
        return {'issuer':self.issuer,
          'authorization_response_iss_parameter_supported':True,
          'authorization_endpoint':base+'/oauth/authorize',
          'token_endpoint':base+'/oauth/token','registration_endpoint':base+'/oauth/register',
          'token_endpoint_auth_methods_supported':['none'],
          'grant_types_supported':['authorization_code','refresh_token'],
          'response_types_supported':['code'],
          'code_challenge_methods_supported':['S256'],
          'scopes_supported':sorted(SCOPES)}
