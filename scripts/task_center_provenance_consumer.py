"""In-process consumer, not an issuer or Node/Python authentication bridge.

Only trusted bootstrap injects source and mapper objects. SessionStore remains
the sole session authority. Ephemeral bindings contain no credentials; restart
loses formal status (never reconstruct it from a row or a string reference).
No registered production source or atomic cross-runtime bridge ships here.
"""
import copy
import json
import math
import time
from task_center_handoff_host import FormalHandoffIdentityProvider, ID
from task_center_session_auth import SessionStore


class GuardedProvenanceConsumer(FormalHandoffIdentityProvider):
    ERROR = 'FORMAL_PROVENANCE_UNAVAILABLE'
    FIELDS = {'source_ref','source_version','subject','incarnation',
              'tenant_id','principal_id','expires_at'}

    @classmethod
    def validate_source(cls, source, mapper):
        if not callable(mapper) or any(not callable(getattr(source, name, None)) for name in
                                      ('verify_login','current_provenance','assert_effect_current')):
            raise ValueError(cls.ERROR)

    def __init__(self, sessions, source, mapper, clock=time.time):
        if not isinstance(sessions, SessionStore):
            raise ValueError(self.ERROR)
        self.validate_source(source, mapper)
        self.sessions=sessions; self.source=source; self.mapper=mapper
        self.clock=clock; self._bindings={}

    def _binding(self, value):
        if (not isinstance(value, dict) or set(value)!=self.FIELDS
                or any(not isinstance(value[k], str) or not ID.fullmatch(value[k])
                       for k in self.FIELDS-{'expires_at'})
                or value['tenant_id']!=self.sessions.tenant_id
                or type(value['expires_at']) not in (int,float)
                or not math.isfinite(value['expires_at'])
                or value['expires_at']<=self.clock()):
            raise ValueError(self.ERROR)
        return copy.deepcopy(value)

    def _identity(self, binding):
        # Mapping is host-owned executable configuration, never request roles.
        identity=self.mapper(copy.deepcopy(binding))
        if (not isinstance(identity,dict)
                or set(identity)!={'tenant_id','principal_id','roles'}
                or any(identity[k]!=binding[k] for k in ('tenant_id','principal_id'))
                or not isinstance(identity['roles'],list) or not identity['roles']
                or any(not isinstance(r,str) or not ID.fullmatch(r) for r in identity['roles'])):
            raise ValueError(self.ERROR)
        return copy.deepcopy(identity)

    def verify(self, username, password):
        # Bare verify cannot safely carry a live capability across login/create.
        return None

    def _current(self, binding, session, expected_roles):
        binding=self._binding(binding)
        current=self._binding(self.source.current_provenance(
            copy.deepcopy(binding),copy.deepcopy(session)))
        identity=self._identity(current)
        if (current!=binding or identity['principal_id']!=session['principal_id']
                or set(identity['roles'])!=set(expected_roles)):
            raise ValueError(self.ERROR)
        return current

    def _guard(self):
        result=self.source.assert_effect_current()
        if result is not None:
            if callable(getattr(result,'close',None)):result.close()
            raise ValueError(self.ERROR)

    def guarded_login(self, sessions, username, password):
        try:
            if sessions is not self.sessions:raise ValueError(self.ERROR)
            binding=self._binding(self.source.verify_login(username,password))
            identity=self._identity(binding)
            def admission(session):
                self._current(binding,session,identity['roles'])
                # Must raise on invalidation. No await or source calls may be
                # inserted between this synchronous guard and DB commit.
                self._guard()
            result=sessions.create(identity,admission=admission)
            self._bindings[sessions._hash(result[0])]=binding
            return identity,result
        except Exception:
            raise ValueError(self.ERROR) from None

    def is_formal_session(self, session):
        try:
            key=session['session_hash']; binding=self._bindings.get(key)
            if binding is None:return False
            # Re-read the canonical row: caller snapshots never undo logout.
            db=self.sessions.connection_factory()
            try:
                row=db.execute('''SELECT principal_id,roles_json,expires_at,revoked_at
                  FROM task_center_sessions WHERE tenant_id=? AND session_hash=?''',
                  (self.sessions.tenant_id,key)).fetchone()
                if (row is None or row['revoked_at'] is not None
                        or row['principal_id']!=session['principal_id']
                        or row['expires_at']<=self.clock()
                        or session['tenant_id']!=self.sessions.tenant_id
                        or session['expires_at']<=self.clock()
                        or session['expires_at']>row['expires_at']):return False
            finally:db.close()
            roles=json.loads(row['roles_json'])
            if set(session['roles'])!=set(roles):return False
            self._current(binding,session,roles)
            self._guard()
            return True
        except Exception:return False
