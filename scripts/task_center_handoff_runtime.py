"""Trusted in-process bootstrap for the original app, not an HTTP auth system.

The host imports main and supplies its existing identity authority and evidence
consumers. No CLI/env module loader, keys, role grants or synthetic identities.
Backend results contain only non-secret references. Missing dependencies deny.
"""
import copy
import math
import os
import time
from task_center_handoff_host import (FormalHandoffIdentityProvider,
    HostAuthAdapter,HandoffHost,ACTIONS,ID)
from task_center_handoff_ledger import HandoffLedgerBridge
from task_center_session_auth import SessionStore


def _future(value,now):
    return type(value) in (int,float) and math.isfinite(value) and value>now


class HostIdentityProvider(FormalHandoffIdentityProvider):
    """Use the host's existing login verifier and live session authority.

    current_session(session) must validate current provenance/revocation and
    return tenant_id, principal_id, session_hash, session_id, expires_at.
    Nothing here converts a development owner grant into handoff authority.
    """
    def __init__(self,tenant_id,backend,clock=time.time):
        if not isinstance(tenant_id,str) or not ID.fullmatch(tenant_id):
            raise ValueError('FORMAL_HOST_TENANT_REQUIRED')
        if backend is None or any(not callable(getattr(backend,k,None))
                for k in ('verify','current_session','authorize')):
            raise ValueError('FORMAL_IDENTITY_BACKEND_UNAVAILABLE')
        self.tenant_id=tenant_id;self.backend=backend;self.clock=clock

    @property
    def guarded_login(self):
        # Preserve legacy injected providers; the new consumer owns its login
        # transaction rather than losing provenance through verify's dict.
        return getattr(self.backend,'guarded_login',None)

    def verify(self,username,password):
        # Credentials stay in the original login path; never log backend errors.
        try:identity=self.backend.verify(username,password)
        except Exception:return None
        if (not isinstance(identity,dict) or set(identity)!={'tenant_id','principal_id','roles'}
                or identity['tenant_id']!=self.tenant_id
                or not isinstance(identity['principal_id'],str) or not ID.fullmatch(identity['principal_id'])
                or not isinstance(identity['roles'],list) or not identity['roles']
                or any(not isinstance(r,str) or not ID.fullmatch(r) for r in identity['roles'])):
            return None
        return copy.deepcopy(identity)

    def current(self,session):
        if (not isinstance(session,dict) or session.get('tenant_id')!=self.tenant_id
                or not _future(session.get('expires_at'),self.clock())
                or not isinstance(session.get('session_hash'),str)):
            return None
        try:current=self.backend.current_session(copy.deepcopy(session))
        except Exception:return None
        fields={'tenant_id','principal_id','session_hash','session_id','expires_at'}
        if (not isinstance(current,dict) or set(current)!=fields
                or any(current[k]!=session.get(k) for k in ('tenant_id','principal_id','session_hash'))
                or any(not isinstance(current[k],str) or not ID.fullmatch(current[k]) for k in ('tenant_id','principal_id','session_id'))
                or not _future(current['expires_at'],self.clock())
                or current['expires_at']>session['expires_at']):
            return None
        return copy.deepcopy(current)

    def is_formal_session(self,session):
        return self.current(session) is not None


class HostActionAdapter(HostAuthAdapter):
    """Exact-action authority plus original host evidence consumers.

    authorize(current,action,binding) returns {'binding':exact input,
    'claims':the existing HandoffHost claim shape}, or None. Every call rechecks
    current session; request bodies, role labels and old grants are not proof.
    """
    def __init__(self,identity,issuer,evidence=None):
        if type(identity) is not HostIdentityProvider:
            raise ValueError('HOST_IDENTITY_PROVIDER_REQUIRED')
        if not isinstance(issuer,str) or not ID.fullmatch(issuer) or issuer.upper().startswith('TEST'):
            raise ValueError('NON_TEST_HOST_ISSUER_REQUIRED')
        self.identity=identity;self.issuer=issuer;self.evidence=evidence

    def authenticate_and_authorize(self,session,action,binding):
        if action not in set(ACTIONS)|{'ISSUE','READ'} or not isinstance(binding,dict):return None
        if (any(not isinstance(binding.get(k),str) or not ID.fullmatch(binding[k]) for k in ('task_id','attempt_id'))
                or type(binding.get('handoff_version')) is not int or binding['handoff_version']<1):return None
        current=self.identity.current(session)
        if current is None:return None
        try:result=self.identity.backend.authorize(copy.deepcopy(current),action,copy.deepcopy(binding))
        except Exception:return None
        fields={'issuer','tenant_id','principal_id','session_id','role_id','expires_at','scope'}
        if (not isinstance(result,dict) or set(result)!={'binding','claims'} or result['binding']!=binding
                or not isinstance(result['claims'],dict) or set(result['claims'])!=fields):return None
        claims=result['claims']
        if (any(not isinstance(claims[k],str) or not ID.fullmatch(claims[k]) for k in fields-{'expires_at'})
                or claims['issuer']!=self.issuer or claims['scope']!='handoff:'+action
                or any(claims[k]!=current[k] for k in ('tenant_id','principal_id','session_id'))
                or not _future(claims['expires_at'],self.identity.clock())
                or claims['expires_at']>current['expires_at']):return None
        return copy.deepcopy(claims)

    @property
    def assess_backup(self):
        # The original v1 loader requires the exact live consumer, not a
        # forwarding callback. Resolve on each access so replacement revokes it.
        return getattr(self.evidence,'assess_backup',super().assess_backup)

    def _evidence(self,name,args,default=None):
        fn=getattr(self.evidence,name,None)
        if not callable(fn):return default
        # Do not reinterpret missing/failed consumer as COMPLETE or CONNECTED.
        try:return fn(*args)
        except Exception:return default

    def prepare_backup_assessment(self,host):
        return self._evidence('prepare_backup_assessment',(host,))
    def assess_provider(self,binding):
        return self._evidence('assess_provider',(binding,))
    def assess_ledger_event(self,binding,event):
        return self._evidence('assess_ledger_event',(binding,event),False) is True
    def verify_ledger_event_current(self,event,host_record):
        return self._evidence('verify_ledger_event_current',(event,host_record),False) is True
    def assess_candidate_bundle(self,binding):
        return self._evidence('assess_candidate_bundle',(binding,))


def main(argv=None, *, db=None,tenant_id=None,issuer=None,identity_backend=None,identity_provider=None,
         session_store=None,evidence=None,role_contract=None,mcp_config=None,
         lifecycle_root=None,ledger_root=None,namespace=None,writer=None,
         gateway_runtime=None,mcp_claim_host=None,mcp_development_host=None,
         execution_provider=None,provenance_source=None,principal_mapper=None):
    """Original host startup calls this with custodied objects, never RPC data.

    SessionStore uses the existing canonical DB. app.main performs its existing
    tenant/DB/CSRF/MCP checks; no listener can bind with absent authority.
    """
    if provenance_source is not None or principal_mapper is not None:
        if identity_backend is not None or identity_provider is not None:
            raise ValueError('SINGLE_IDENTITY_SOURCE_REQUIRED')
        from task_center_provenance_consumer import GuardedProvenanceConsumer
        identity_provider=GuardedProvenanceConsumer(
            session_store,provenance_source,principal_mapper)
    if identity_backend is None and identity_provider is not None:
        from task_center_handoff_backend import CanonicalHandoffBackend
        identity_backend=CanonicalHandoffBackend(session_store,identity_provider,issuer,db)
    identity=HostIdentityProvider(tenant_id,identity_backend)
    if not isinstance(session_store,SessionStore) or session_store.tenant_id!=tenant_id:
        raise ValueError('HOST_SESSION_STORE_REQUIRED')
    if db is None or role_contract is None:
        raise ValueError('HOST_DATABASE_AND_ROLE_CONTRACT_REQUIRED')
    if (not isinstance(lifecycle_root,str) or not os.path.isabs(lifecycle_root)
            or not os.path.isdir(os.path.join(lifecycle_root,'artifacts'))):
        raise ValueError('EXISTING_CANDIDATE_LIFECYCLE_ROOT_REQUIRED')
    if not all(isinstance(x,str) and x for x in (ledger_root,namespace,writer)):
        raise ValueError('HOST_LEDGER_BINDING_REQUIRED')
    host=HandoffHost(db,tenant_id,issuer,HostActionAdapter(identity,issuer,evidence),
        mcp_config=mcp_config,role_contract=role_contract,candidate_lifecycle_root=lifecycle_root)
    bridge=HandoffLedgerBridge(host,ledger_root,namespace,writer)
    from task_center_app import main as app_main
    return app_main(argv,gateway_runtime,identity_provider=identity,session_store=session_store,
        handoff_host=host,ledger_bridge=bridge,mcp_claim_host=mcp_claim_host,
        mcp_development_host=mcp_development_host,execution_provider=execution_provider)


if __name__=='__main__':
    # Direct script invocation has no custodied backend; do not import arbitrary
    # configuration modules or silently fall back to FileTestIdentityProvider.
    raise SystemExit('FORMAL_HOST_BOOTSTRAP_DEPENDENCIES_REQUIRED')
