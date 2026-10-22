"""Explicit first customer-platform storage initialization, no seeded identities.

Only for an approved NEW installation: reuse original Center and business schemas.
The original project table records a platform realm, NOT a fabricated SaaS order,
verified contract, person, merchant approval or financial entitlement.
"""
import os
import hashlib
from pathlib import Path
from scripts.pr122_customer_core import Center, identifier, safe_text, canonical
from scripts.community_persistent_runtime import PersistentRuntime, _directory

SYSTEM_OWNER = 'system_community_platform'


def _require_nonroot():
    if os.geteuid()==0:raise PermissionError('NONROOT_PLATFORM_INITIALIZATION_REQUIRED')


class FirstInstallation:
    def __init__(self):
        self.center = None
        self.persistence = None

    @classmethod
    def initialize(cls, directory, keys, active_key, realm, bindings, *, clock):
        _require_nonroot()
        if hashlib.sha256(Path(__file__).with_name('pr122_customer_core.py').read_bytes()).hexdigest()!='cfd3c9d634ddd41d4b59dd4a3ca374d1f1bbcec009c22878e9560d21ae9365b0':
            raise PermissionError('PINNED_CENTER_SOURCE_REQUIRED')
        if (type(realm) is not dict or set(realm) != {'project','tenant','customer','title','expires','authority_ref'}
                or type(realm['expires']) is not int or not callable(clock)):
            raise ValueError('EXPLICIT_PLATFORM_REALM_REQUIRED')
        for key in ('project','tenant','customer','authority_ref'):
            identifier(realm[key])
        safe_text(realm['title'],150)
        if not realm['title'].strip():raise ValueError('PLATFORM_TITLE_REQUIRED')
        now=clock()
        if type(now) is not int or not 0 <= now < realm['expires'] <= 253402300799:
            raise ValueError('EXPLICIT_FUTURE_REALM_EXPIRY_REQUIRED')
        if (type(keys) is not dict or not keys or active_key not in keys
                or any(type(k) is not str or type(v) is not bytes or len(v)!=32 for k,v in keys.items())):
            raise ValueError('ORIGINAL_CENTER_KEYS_REQUIRED')
        for key in keys:identifier(key)
        PersistentRuntime._bindings(bindings,clock)
        if any(p.tenant_id!=realm['tenant'] for p in bindings):
            raise PermissionError('SINGLE_PLATFORM_REALM_REQUIRED')
        path=Path(directory)
        if not path.is_absolute() or str(path)!=os.fspath(directory) or '..' in path.parts:
            raise ValueError('NEW_ABSOLUTE_PLATFORM_ROOT_REQUIRED')
        _directory(str(path.parent))
        path.mkdir(mode=0o700)  # Existing or partial installation must never reset.
        owner=cls()
        try:
            owner.center=Center(path/'identity',keys,active_key,clock=clock)
            owner.persistence=PersistentRuntime.initialize(str(path/'runtime'),bindings,clock=owner.center.now)
            payload=dict(kind='COMMUNITY_PLATFORM_REALM',title=realm['title'],requirements=[],
                source='OWNER_APPROVED_FIRST_INSTALL',authority_ref=realm['authority_ref'])
            c=owner.center
            with c.tx():
                encoded=c.encrypt(canonical(payload),'project:'+realm['project'])
                c.db.execute('INSERT INTO projects VALUES(?,?,?,?,?,1,?,?,1)',
                    (realm['project'],realm['tenant'],realm['customer'],SYSTEM_OWNER,
                     realm['authority_ref'],realm['expires'],encoded))
                c.db.execute('INSERT INTO project_history VALUES(?,1,?)',(realm['project'],encoded))
                c.audit(realm['project'],SYSTEM_OWNER,'COMMUNITY_PLATFORM_FIRST_INSTALL',realm['authority_ref'])
            return owner
        except BaseException:
            owner.close()  # Preserve partial files; no deletion or automatic retry.
            raise

    def close(self):
        first=None
        for target in (self.center,self.persistence):
            if target is None:continue
            try:
                if type(target) is Center:target.db.close()
                else:target.close()
            except BaseException as error:
                if first is None:first=error
        self.center=self.persistence=None
        if first is not None:raise first

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
