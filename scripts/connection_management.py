"""Tenant-bound API key and OAuth2/PKCE connections in the canonical SQLite DB.

TEST_ONLY by default.  Tokens stay encrypted server-side and are never returned
by projection methods.  Endpoint and destination bindings are immutable per
configuration version; scope expansion requires an explicit replacement.
"""
from __future__ import print_function

import base64
import hashlib
import http.client
import ipaddress
import json
import secrets
import socket
import ssl
import time
from urllib.parse import urlencode, urlparse

from cryptography.fernet import Fernet, InvalidToken

from reusable_task_gateway import _text
from task_supervisor import canonical


AUTH_TYPES=frozenset(('API_KEY','OAUTH2_AUTH_CODE_PKCE'))
CONNECTION_PURPOSES=frozenset(('MODEL_INFERENCE','MCP_TOOL','CODEX_EXECUTION'))


def _safe_endpoint(value, allow_loopback=True):
    parsed=urlparse(_text(value,'endpoint'))
    host=(parsed.hostname or '').lower()
    loopback=(allow_loopback and parsed.scheme=='http' and host in
              ('127.0.0.1','localhost'))
    public=(parsed.scheme=='https' and '.' in host and host not in
            ('127.0.0.1','localhost','::1') and
            not host.endswith(('.local','.internal')))
    try:
        address=ipaddress.ip_address(host)
        if address.is_private or address.is_loopback or address.is_link_local:
            public=False
    except ValueError:pass
    if (parsed.username or parsed.password or parsed.fragment or
            not (loopback or public)):
        raise ValueError('FIXED_SAFE_ENDPOINT_REQUIRED')
    return parsed


def _origin(value):
    parsed=_safe_endpoint(value)
    port=parsed.port or (443 if parsed.scheme=='https' else 80)
    return '%s://%s:%d'%(parsed.scheme,parsed.hostname.lower(),port)


class OAuthProtocolError(Exception):pass


class PinnedOAuthAdapter(object):
    """No-redirect form POST using exactly the address resolved by policy."""
    def exchange(self, endpoint, form, timeout=5):
        parsed=_safe_endpoint(endpoint);port=parsed.port or (
          443 if parsed.scheme=='https' else 80)
        addresses=socket.getaddrinfo(parsed.hostname,port,type=socket.SOCK_STREAM)
        if not addresses:raise OAuthProtocolError('DNS_EMPTY')
        vetted=[]
        for item in addresses:
            address=ipaddress.ip_address(item[4][0])
            if parsed.scheme=='https' and (address.is_private or address.is_loopback
                    or address.is_link_local or address.is_multicast or
                    address.is_reserved or address.is_unspecified):
                raise OAuthProtocolError('UNSAFE_TOKEN_ENDPOINT')
            vetted.append(item)
        family,socktype,proto,_,sockaddr=vetted[0]
        raw=socket.socket(family,socktype,proto);raw.settimeout(timeout)
        connection=None
        try:
            raw.connect(sockaddr)
            if parsed.scheme=='https':
                raw=ssl.create_default_context().wrap_socket(
                  raw,server_hostname=parsed.hostname)
            connection=http.client.HTTPConnection(parsed.hostname,port,timeout=timeout)
            connection.sock=raw
            body=urlencode(form).encode('ascii')
            path=parsed.path or '/'
            if parsed.query:path+='?'+parsed.query
            connection.request('POST',path,body=body,headers={
              'Content-Type':'application/x-www-form-urlencoded',
              'Accept':'application/json','Host':parsed.netloc,
              'User-Agent':'Xuanjun-TEST-ONLY-OAuth'})
            response=connection.getresponse();payload=response.read(1024*1024+1)
            if response.status>=300:raise OAuthProtocolError('TOKEN_HTTP_%d'%response.status)
            if len(payload)>1024*1024:raise OAuthProtocolError('TOKEN_RESPONSE_TOO_LARGE')
            value=json.loads(payload.decode('utf-8'))
            if not isinstance(value,dict):raise TypeError()
            return value
        except OAuthProtocolError:raise
        except Exception as exc:raise OAuthProtocolError(type(exc).__name__)
        finally:
            if connection is not None:connection.close()
            else:
                try:raw.close()
                except Exception:pass


class ConnectionManager(object):
    def __init__(self,gateway,context,master_key,clock=None):
        self.gateway=gateway;self.db=gateway.db;self.context=context
        self.tenant_id=gateway.tenants.verify(context);self.clock=clock or time.time
        self.fernet=Fernet(master_key);self._schema()

    def _schema(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute('''CREATE TABLE IF NOT EXISTS service_connections(
              tenant_id TEXT NOT NULL,connection_id TEXT NOT NULL,
              provider_id TEXT NOT NULL,purpose TEXT NOT NULL,auth_type TEXT NOT NULL,
              destination_origin TEXT NOT NULL,issuer TEXT,
              authorization_endpoint TEXT,token_endpoint TEXT,revocation_endpoint TEXT,
              redirect_uri TEXT,client_id TEXT,scopes_json TEXT NOT NULL,
              supports_refresh INTEGER NOT NULL,status TEXT NOT NULL,
              config_version INTEGER NOT NULL,secret_cipher BLOB,secret_mask TEXT,
              refresh_cipher BLOB,access_expires_at REAL,refresh_lease TEXT,
              refresh_lease_until REAL,created_at REAL NOT NULL,updated_at REAL NOT NULL,
              PRIMARY KEY(tenant_id,connection_id))''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS oauth_flows(
              tenant_id TEXT NOT NULL,flow_id TEXT NOT NULL,connection_id TEXT NOT NULL,
              connection_version INTEGER NOT NULL,state_sha256 TEXT NOT NULL,
              verifier_cipher BLOB NOT NULL,redirect_uri TEXT NOT NULL,
              issuer TEXT NOT NULL,status TEXT NOT NULL,expires_at REAL NOT NULL,
              used_at REAL,created_at REAL NOT NULL,
              PRIMARY KEY(tenant_id,flow_id),UNIQUE(tenant_id,state_sha256))''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS connection_audit(
              audit_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,
              principal_id TEXT NOT NULL,action TEXT NOT NULL,target_id TEXT NOT NULL,
              detail_json TEXT NOT NULL,observed_at REAL NOT NULL)''')
            self.db.commit()
        except Exception:self.db.rollback();raise

    def _admin(self):
        principal=self.context['principal_id']
        if not principal.startswith('admin:'):raise ValueError('CONNECTION_ADMIN_REQUIRED')
        return principal

    def _audit(self,action,target,detail,now):
        principal=self.context['principal_id']
        safe={k:v for k,v in detail.items() if not any(mark in k.lower()
          for mark in ('secret','token','code','verifier','state'))}
        seed=canonical({'tenant':self.tenant_id,'principal':principal,
          'action':action,'target':target,'at':now,'detail':safe})
        self.db.execute('INSERT INTO connection_audit VALUES (?,?,?,?,?,?,?)',(
          hashlib.sha256(seed.encode()).hexdigest(),self.tenant_id,principal,
          action,target,canonical(safe),now))

    def upsert(self,config,credential=None,now=None):
        principal=self._admin();now=self.clock() if now is None else now
        required={'connection_id','provider_id','purpose','auth_type',
          'destination_origin','issuer','authorization_endpoint','token_endpoint',
          'revocation_endpoint','redirect_uri','client_id','scopes','supports_refresh'}
        if not isinstance(config,dict) or set(config)!=required:
            raise ValueError('EXACT_CONNECTION_CONFIG_REQUIRED')
        if config['auth_type'] not in AUTH_TYPES:raise ValueError('AUTH_TYPE_REQUIRED')
        if config['purpose'] not in CONNECTION_PURPOSES:
            raise ValueError('CONNECTION_PURPOSE_REQUIRED')
        if not isinstance(config['scopes'],list):raise ValueError('SCOPES_ARRAY_REQUIRED')
        scopes=sorted(set(_text(x,'scope') for x in config['scopes']))
        destination=_origin(config['destination_origin'])
        if config['auth_type']=='API_KEY':
            for key in ('issuer','authorization_endpoint','token_endpoint',
                        'revocation_endpoint','redirect_uri','client_id'):
                if config[key] is not None:raise ValueError('API_KEY_OAUTH_FIELDS_FORBIDDEN')
            if scopes:raise ValueError('API_KEY_SCOPES_FORBIDDEN')
        else:
            for key in ('issuer','authorization_endpoint','token_endpoint',
                        'redirect_uri','client_id'):_text(config[key],key)
            _safe_endpoint(config['issuer']);_safe_endpoint(config['authorization_endpoint'])
            _safe_endpoint(config['token_endpoint']);_safe_endpoint(config['redirect_uri'])
            if config['revocation_endpoint'] is not None:_safe_endpoint(config['revocation_endpoint'])
            if credential is not None:raise ValueError('OAUTH_CREDENTIAL_DIRECT_SET_FORBIDDEN')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            existing=self.db.execute('''SELECT * FROM service_connections WHERE
              tenant_id=? AND connection_id=?''',(self.tenant_id,
              config['connection_id'])).fetchone()
            if (existing and existing['status']=='REFRESHING' and
                    existing['refresh_lease_until'] is not None and
                    existing['refresh_lease_until']>now):
                raise ValueError('OAUTH_REFRESH_IN_PROGRESS')
            old_scopes=set(json.loads(existing['scopes_json'])) if existing else set()
            if existing and not set(scopes).issubset(old_scopes):
                raise ValueError('SCOPE_EXPANSION_REQUIRES_NEW_AUTHORIZATION')
            version=(existing['config_version']+1) if existing else 1
            secret_cipher=existing['secret_cipher'] if existing else None
            secret_mask=existing['secret_mask'] if existing else None
            refresh_cipher=existing['refresh_cipher'] if existing else None
            expires=existing['access_expires_at'] if existing else None
            status=existing['status'] if existing else 'CONFIGURED'
            if existing and existing['status']=='REFRESHING':
                # A stale/unknown refresh cannot be carried into a new
                # configuration version.  Force explicit re-authorization.
                secret_cipher=secret_mask=refresh_cipher=expires=None
                status='REAUTH_REQUIRED'
            old_binding=(existing['destination_origin'],existing['issuer'],
              existing['auth_type']) if existing else None
            new_binding=(destination,config['issuer'],config['auth_type'])
            if old_binding and old_binding!=new_binding:
                secret_cipher=secret_mask=refresh_cipher=expires=None;status='REAUTH_REQUIRED'
            if credential is not None:
                if (not isinstance(credential,str) or len(credential)<8 or
                        '\n' in credential or '\r' in credential):
                    raise ValueError('VALID_CONNECTION_CREDENTIAL_REQUIRED')
                secret_cipher=self.fernet.encrypt(credential.encode());secret_mask='••••'+credential[-4:]
                status='ACTIVE'
            created=existing['created_at'] if existing else now
            self.db.execute('''INSERT OR REPLACE INTO service_connections VALUES
              (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(
              self.tenant_id,config['connection_id'],config['provider_id'],
              config['purpose'],config['auth_type'],destination,config['issuer'],
              config['authorization_endpoint'],config['token_endpoint'],
              config['revocation_endpoint'],config['redirect_uri'],config['client_id'],
              canonical(scopes),int(bool(config['supports_refresh'])),status,version,
              secret_cipher,secret_mask,refresh_cipher,expires,None,None,created,now))
            self._audit('CONNECTION_UPSERT',config['connection_id'],{
              'config_version':version,'auth_type':config['auth_type'],
              'credential_replaced':credential is not None},now);self.db.commit()
        except Exception:self.db.rollback();raise
        return {'connection_id':config['connection_id'],'config_version':version,
          'status':status,'secret_mask':secret_mask}

    def begin_oauth(self,connection_id,now=None):
        self._admin();now=self.clock() if now is None else now
        row=self.db.execute('''SELECT * FROM service_connections WHERE tenant_id=?
          AND connection_id=? AND auth_type='OAUTH2_AUTH_CODE_PKCE' ''',(
          self.tenant_id,connection_id)).fetchone()
        if row is None:raise ValueError('OAUTH_CONNECTION_REQUIRED')
        state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(
          verifier.encode()).digest()).rstrip(b'=').decode()
        flow_id=hashlib.sha256(canonical({'tenant':self.tenant_id,
          'connection':connection_id,'state':state}).encode()).hexdigest()
        self.db.execute('''INSERT INTO oauth_flows VALUES
          (?,?,?,?,?,?,?,?,?,?,?,?)''',(self.tenant_id,flow_id,connection_id,
          row['config_version'],hashlib.sha256(state.encode()).hexdigest(),
          self.fernet.encrypt(verifier.encode()),row['redirect_uri'],row['issuer'],
          'PENDING',now+600,None,now));self.db.commit()
        query=urlencode({'response_type':'code','client_id':row['client_id'],
          'redirect_uri':row['redirect_uri'],'scope':' '.join(json.loads(row['scopes_json'])),
          'state':state,'code_challenge':challenge,'code_challenge_method':'S256'})
        return {'flow_id':flow_id,'authorization_url':
          row['authorization_endpoint']+('?' if '?' not in row['authorization_endpoint'] else '&')+query,
          'state':state,'expires_at':now+600}

    def complete_oauth(self,connection_id,flow_id,state,code,issuer,
                       redirect_uri,adapter=None,now=None):
        self._admin();now=self.clock() if now is None else now
        self.db.execute('BEGIN IMMEDIATE')
        try:
            flow=self.db.execute('''SELECT * FROM oauth_flows WHERE tenant_id=?
              AND flow_id=? AND connection_id=?''',(self.tenant_id,flow_id,
              connection_id)).fetchone()
            connection=self.db.execute('''SELECT * FROM service_connections WHERE
              tenant_id=? AND connection_id=?''',(self.tenant_id,connection_id)).fetchone()
            if flow is None or connection is None:raise ValueError('OAUTH_FLOW_REQUIRED')
            if flow['status']!='PENDING':raise ValueError('OAUTH_STATE_REPLAY')
            if now>=flow['expires_at']:raise ValueError('OAUTH_FLOW_EXPIRED')
            if hashlib.sha256(_text(state,'state').encode()).hexdigest()!=flow['state_sha256']:
                raise ValueError('OAUTH_STATE_MISMATCH')
            if issuer!=flow['issuer'] or issuer!=connection['issuer']:
                raise ValueError('OAUTH_ISSUER_MISMATCH')
            if redirect_uri!=flow['redirect_uri'] or redirect_uri!=connection['redirect_uri']:
                raise ValueError('OAUTH_REDIRECT_MISMATCH')
            if connection['config_version']!=flow['connection_version']:
                raise ValueError('OAUTH_CONFIG_VERSION_MISMATCH')
            changed=self.db.execute('''UPDATE oauth_flows SET status='EXCHANGING',
              used_at=? WHERE tenant_id=? AND flow_id=? AND status='PENDING' ''',(
              now,self.tenant_id,flow_id)).rowcount
            if changed!=1:raise ValueError('OAUTH_STATE_REPLAY')
            self.db.commit()
        except Exception:self.db.rollback();raise
        try:verifier=self.fernet.decrypt(flow['verifier_cipher']).decode()
        except InvalidToken:raise ValueError('OAUTH_VERIFIER_DECRYPT_FAILED')
        adapter=adapter or PinnedOAuthAdapter()
        try:value=adapter.exchange(connection['token_endpoint'],{
          'grant_type':'authorization_code','code':_text(code,'code'),
          'redirect_uri':redirect_uri,'client_id':connection['client_id'],
          'code_verifier':verifier})
        except Exception:
            self.db.execute('''UPDATE oauth_flows SET status='FAILED' WHERE
              tenant_id=? AND flow_id=? AND status='EXCHANGING' ''',(
              self.tenant_id,flow_id));self.db.commit();raise
        try:
            access=_text(value.get('access_token'),'access_token')
            token_type=value.get('token_type','Bearer')
            if token_type.lower()!='bearer':raise ValueError('OAUTH_BEARER_REQUIRED')
            granted=set(str(value.get('scope','')).split())
            requested=set(json.loads(connection['scopes_json']))
            if not requested.issubset(granted):raise ValueError('OAUTH_SCOPE_MISSING')
            expires_in=value.get('expires_in')
            if type(expires_in) not in (int,float) or expires_in<=0:
                raise ValueError('OAUTH_EXPIRY_REQUIRED')
            refresh=value.get('refresh_token')
            if refresh is not None and not connection['supports_refresh']:
                raise ValueError('OAUTH_REFRESH_NOT_SUPPORTED')
        except Exception:
            self.db.execute('''UPDATE oauth_flows SET status='FAILED' WHERE
              tenant_id=? AND flow_id=? AND status='EXCHANGING' ''',(
              self.tenant_id,flow_id));self.db.execute('''UPDATE service_connections
              SET status='REAUTH_REQUIRED',updated_at=? WHERE tenant_id=? AND
              connection_id=?''',(now,self.tenant_id,connection_id));self.db.commit()
            raise
        self.db.execute('BEGIN IMMEDIATE')
        try:
            changed=self.db.execute('''UPDATE service_connections SET
              secret_cipher=?,secret_mask=?,refresh_cipher=?,access_expires_at=?,
              status='ACTIVE',updated_at=? WHERE tenant_id=? AND connection_id=?
              AND config_version=? AND status!='REVOKED' AND EXISTS(SELECT 1 FROM
              oauth_flows f WHERE f.tenant_id=service_connections.tenant_id AND
              f.flow_id=? AND f.connection_id=service_connections.connection_id
              AND f.status='EXCHANGING')''',(self.fernet.encrypt(access.encode()),
              '••••'+access[-4:],self.fernet.encrypt(refresh.encode()) if refresh else None,
              now+expires_in,now,self.tenant_id,connection_id,
              connection['config_version'],flow_id)).rowcount
            if changed!=1:raise ValueError('OAUTH_FLOW_REVOKED_OR_CONFIG_CHANGED')
            self.db.execute('''UPDATE oauth_flows SET status='COMPLETED' WHERE
              tenant_id=? AND flow_id=? AND status='EXCHANGING' ''',(
              self.tenant_id,flow_id));self._audit('OAUTH_COMPLETED',connection_id,
              {'config_version':connection['config_version'],'scope_count':len(granted)},now)
            self.db.commit()
        except Exception:self.db.rollback();raise
        return {'connection_id':connection_id,'status':'ACTIVE',
          'expires_at':now+expires_in,'granted_scopes':sorted(granted)}

    def refresh(self,connection_id,adapter=None,now=None):
        self._admin();now=self.clock() if now is None else now
        lease=secrets.token_urlsafe(18)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('''SELECT * FROM service_connections WHERE
              tenant_id=? AND connection_id=?''',(self.tenant_id,connection_id)).fetchone()
            if row is None or row['auth_type']!='OAUTH2_AUTH_CODE_PKCE':
                raise ValueError('OAUTH_CONNECTION_REQUIRED')
            if not row['supports_refresh']:raise ValueError('OAUTH_REFRESH_NOT_SUPPORTED')
            if row['status'] not in ('ACTIVE','REFRESHING'):
                raise ValueError('OAUTH_REAUTH_REQUIRED')
            if row['refresh_cipher'] is None:raise ValueError('OAUTH_REFRESH_TOKEN_REQUIRED')
            if row['status']=='REFRESHING':
                if row['refresh_lease_until'] is not None and row['refresh_lease_until']>now:
                    raise ValueError('OAUTH_REFRESH_IN_PROGRESS')
                self.db.execute('''UPDATE service_connections SET
                  status='REAUTH_REQUIRED',refresh_cipher=NULL,refresh_lease=NULL,
                  refresh_lease_until=NULL,updated_at=? WHERE tenant_id=? AND
                  connection_id=?''',(now,self.tenant_id,connection_id))
                self.db.commit()
                raise ValueError('OAUTH_REFRESH_RECOVERY_REAUTH_REQUIRED')
            self.db.execute('''UPDATE service_connections SET status='REFRESHING',
              refresh_lease=?,refresh_lease_until=?,updated_at=? WHERE tenant_id=?
              AND connection_id=?''',(lease,now+30,now,self.tenant_id,connection_id))
            self.db.commit()
        except Exception:self.db.rollback();raise
        refresh=self.fernet.decrypt(row['refresh_cipher']).decode();adapter=adapter or PinnedOAuthAdapter()
        try:value=adapter.exchange(row['token_endpoint'],{'grant_type':'refresh_token',
          'refresh_token':refresh,'client_id':row['client_id']})
        except Exception:
            self.db.execute('''UPDATE service_connections SET status='REAUTH_REQUIRED',
              refresh_cipher=NULL,refresh_lease=NULL,refresh_lease_until=NULL WHERE tenant_id=? AND
              connection_id=? AND refresh_lease=?''',(self.tenant_id,connection_id,
              lease));self.db.commit();raise
        try:
            access=_text(value.get('access_token'),'access_token')
            if str(value.get('token_type','Bearer')).lower()!='bearer':
                raise ValueError('OAUTH_BEARER_REQUIRED')
            granted=set(str(value.get('scope',' '.join(
              json.loads(row['scopes_json'])))).split())
            if not set(json.loads(row['scopes_json'])).issubset(granted):
                raise ValueError('OAUTH_SCOPE_MISSING')
            expires=value.get('expires_in')
            if type(expires) not in (int,float) or expires<=0:
                raise ValueError('OAUTH_EXPIRY_REQUIRED')
            new_refresh=value.get('refresh_token') or refresh
        except Exception:
            self.db.execute('''UPDATE service_connections SET status='REAUTH_REQUIRED',
              refresh_cipher=NULL,refresh_lease=NULL,refresh_lease_until=NULL WHERE tenant_id=? AND
              connection_id=? AND refresh_lease=?''',(self.tenant_id,connection_id,
              lease));self.db.commit();raise
        changed=self.db.execute('''UPDATE service_connections SET secret_cipher=?,
          secret_mask=?,refresh_cipher=?,access_expires_at=?,status='ACTIVE',
          refresh_lease=NULL,refresh_lease_until=NULL,updated_at=? WHERE tenant_id=?
          AND connection_id=? AND refresh_lease=?''',(self.fernet.encrypt(access.encode()),
          '••••'+access[-4:],self.fernet.encrypt(new_refresh.encode()),now+expires,
          now,self.tenant_id,connection_id,lease)).rowcount;self.db.commit()
        if changed!=1:raise ValueError('OAUTH_REFRESH_LEASE_LOST')
        return {'connection_id':connection_id,'status':'ACTIVE','expires_at':now+expires}

    def revoke(self,connection_id,now=None):
        self._admin();now=self.clock() if now is None else now
        self.db.execute('BEGIN IMMEDIATE')
        try:
            changed=self.db.execute('''UPDATE service_connections SET status='REVOKED',
              secret_cipher=NULL,secret_mask=NULL,refresh_cipher=NULL,
              access_expires_at=NULL,refresh_lease=NULL,refresh_lease_until=NULL,
              config_version=config_version+1,updated_at=? WHERE tenant_id=? AND connection_id=?''',(
              now,self.tenant_id,connection_id)).rowcount
            if changed!=1:raise KeyError(connection_id)
            self.db.execute('''UPDATE oauth_flows SET status='REVOKED',used_at=? WHERE
              tenant_id=? AND connection_id=? AND status IN ('PENDING','EXCHANGING')''',
              (now,self.tenant_id,connection_id));self.db.commit()
        except Exception:self.db.rollback();raise
        return {'connection_id':connection_id,'status':'REVOKED',
          'external_revocation':'NOT_EXECUTED'}

    def credential(self,connection_id,required_origin,required_purpose,now=None):
        now=self.clock() if now is None else now
        row=self.db.execute('''SELECT * FROM service_connections WHERE tenant_id=?
          AND connection_id=?''',(self.tenant_id,connection_id)).fetchone()
        if row is None or row['status']!='ACTIVE' or row['secret_cipher'] is None:
            raise ValueError('ACTIVE_CONNECTION_REQUIRED')
        if row['destination_origin']!=_origin(required_origin):
            raise ValueError('CONNECTION_DESTINATION_MISMATCH')
        if row['purpose']!=_text(required_purpose,'required_purpose'):
            raise ValueError('CONNECTION_PURPOSE_MISMATCH')
        if row['auth_type']=='OAUTH2_AUTH_CODE_PKCE' and (
                row['access_expires_at'] is None or now>=row['access_expires_at']):
            raise ValueError('OAUTH_ACCESS_EXPIRED')
        try:return self.fernet.decrypt(row['secret_cipher']).decode(),row['config_version']
        except InvalidToken:raise ValueError('CONNECTION_CREDENTIAL_DECRYPT_FAILED')

    def projection(self):
        result=[]
        for row in self.db.execute('''SELECT connection_id,provider_id,purpose,
          auth_type,destination_origin,issuer,scopes_json,supports_refresh,status,
          config_version,secret_mask,access_expires_at,updated_at FROM
          service_connections WHERE tenant_id=? ORDER BY connection_id''',(
          self.tenant_id,)):
            item=dict(row);item['scopes']=json.loads(item.pop('scopes_json'))
            item['supports_refresh']=bool(item['supports_refresh']);result.append(item)
        return result
