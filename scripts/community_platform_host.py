"""Formal serial host for original community identity, stores and HTTPS proxy.

Run only inside an admitted project container. No fixture, registration bypass,
credential generation, deployment, DNS change or automatic initialization.
The three files are local protected inputs, never HTTP request parameters.
"""
import argparse
import base64
import hashlib
import os
import signal
import fcntl
from pathlib import Path
from scripts.community_mini_host_config import load_protected
from scripts.community_persistent_runtime import PersistentRuntime, NAMES, _directory, _file
from scripts.community_saas_phase2 import Principal
from scripts.pr122_customer_core import Center
from scripts.community_mini_application import MiniApplication

CORE_SHA256 = 'cfd3c9d634ddd41d4b59dd4a3ca374d1f1bbcec009c22878e9560d21ae9365b0'
FIELDS = {'version','center_root','runtime_directory','application_config',
          'principals','bindings','operations','reviewers','socket_path',
          'https_origin','nginx_uid','nginx_gid'}


def _require_nonroot():
    if os.geteuid() == 0:
        raise PermissionError('NONROOT_PLATFORM_HOST_REQUIRED')


def _configuration(plan, key_material, wechat):
    if type(plan) is not dict or not FIELDS <= set(plan) <= FIELDS|{'registration_scenes','community_grants'} or type(plan['version']) is not int or plan['version'] != 1:
        raise ValueError('EXACT_PLATFORM_HOST_PLAN_REQUIRED')
    if (type(key_material) is not dict or set(key_material) != {'active_key','keys'}
            or type(key_material['active_key']) is not str
            or type(key_material['keys']) is not dict or not key_material['keys']):
        raise ValueError('ORIGINAL_CENTER_KEY_MATERIAL_REQUIRED')
    keys = {}
    try:
        for name, encoded in key_material['keys'].items():
            if type(name) is not str or type(encoded) is not str:
                raise ValueError()
            keys[name] = base64.b64decode(encoded, validate=True)
            if len(keys[name]) != 32:
                raise ValueError()
    except Exception:
        raise ValueError('INVALID_CENTER_KEY_MATERIAL') from None
    if key_material['active_key'] not in keys:
        raise ValueError('ACTIVE_CENTER_KEY_REQUIRED')
    if (type(wechat) is not dict or set(wechat) != {'appid','app_secret'}
            or type(wechat['appid']) is not str or type(wechat['app_secret']) is not str):
        raise ValueError('EXACT_WECHAT_SECRET_INPUT_REQUIRED')
    from scripts.community_mini_login import WechatCodeClient
    WechatCodeClient(wechat['appid'], wechat['app_secret'])  # Validate; no provider IO.
    if type(plan['principals']) is not dict or not plan['principals'] or type(plan['bindings']) is not dict or set(plan['bindings']) != set(plan['principals']):
        raise ValueError('EXACT_SERVER_PRINCIPAL_BINDINGS_REQUIRED')
    principals = {}
    for name, value in plan['principals'].items():
        if type(name) is not str or type(value) is not dict or set(value) != {'tenant_id','role'}:
            raise ValueError('EXACT_HOST_PRINCIPAL_REQUIRED')
        principals[name] = Principal(value['tenant_id'], value['role'])
    bindings = {principals[name]:value for name,value in plan['bindings'].items()}
    PersistentRuntime._bindings(bindings, lambda:0)
    if type(plan['operations']) is not dict or type(plan['reviewers']) is not dict:
        raise ValueError('PROTECTED_OPERATION_GRANTS_REQUIRED')
    if 'community_grants' in plan and type(plan['community_grants']) is not dict:
        raise ValueError('PROTECTED_COMMUNITY_GRANTS_REQUIRED')
    operations = {}
    for name, value in plan['operations'].items():
        if type(value) is not dict or type(value.get('principal')) is not str or value['principal'] not in principals:
            raise ValueError('NAMED_REGISTERED_OPERATOR_REQUIRED')
        operations[name] = dict(value, principal=principals[value['principal']])
    for name in ('nginx_uid','nginx_gid'):
        if type(plan[name]) is not int or plan[name] < (1 if name == 'nginx_uid' else 0):
            raise ValueError('PINNED_PROXY_IDENTITY_REQUIRED')
    return keys, principals, bindings, operations


class PlatformHost:
    """Own Center and PersistentRuntime; MiniApplication borrows both."""
    def __init__(self):
        self.center = None
        self.persistence = None
        self.application = None
        self.center_lock = None

    @classmethod
    def open(cls, plan_path, keys_path, wechat_path):
        _require_nonroot()
        if hashlib.sha256(Path(__file__).with_name('pr122_customer_core.py').read_bytes()).hexdigest() != CORE_SHA256:
            raise PermissionError('PINNED_CENTER_SOURCE_REQUIRED')
        plan = load_protected(plan_path)
        key_material = load_protected(keys_path)
        wechat = load_protected(wechat_path)
        keys, principals, bindings, operations = _configuration(plan, key_material, wechat)
        config = load_protected(plan['application_config'])
        if type(config) is not dict or config.get('appid') != wechat['appid'] or config.get('https_origin') != plan['https_origin']:
            raise PermissionError('SAME_PROTECTED_APPID_AND_ORIGIN_REQUIRED')
        center_root = _directory(plan['center_root'])
        _file(center_root/'center.sqlite')  # Constructor may not silently create an identity DB.
        _directory(str(center_root/'objects'))
        for suffix in ('-wal','-shm','-journal'):
            sidecar = center_root / ('center.sqlite'+suffix)
            if sidecar.exists() or sidecar.is_symlink():
                _file(sidecar)
        for name in ('runtime_directory','socket_path'):
            value = plan[name]
            if type(value) is not str or not Path(value).is_absolute() or str(Path(value)) != value or '..' in Path(value).parts:
                raise ValueError('EXACT_ABSOLUTE_HOST_PATH_REQUIRED')
        # Ensure the protected Center cannot be aliased to any business store.
        database = (center_root/'center.sqlite').stat()
        runtime_root = _directory(plan['runtime_directory'])
        for name in NAMES:
            info = _file(runtime_root/(name+'.sqlite'))
            if (database.st_dev, database.st_ino) == (info.st_dev, info.st_ino):
                raise PermissionError('SEPARATE_CENTER_STORE_REQUIRED')
        owner = cls()
        try:
            # Cooperative host lock on existing Center, without a new lock file.
            owner.center_lock = os.open(str(center_root/'center.sqlite'), os.O_RDWR|os.O_NOFOLLOW)
            locked = os.fstat(owner.center_lock)
            if (locked.st_dev,locked.st_ino) != (database.st_dev,database.st_ino):
                raise PermissionError('CENTER_FILE_CHANGED')
            fcntl.flock(owner.center_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            # Original business lock is held before any Center constructor IO.
            owner.persistence = PersistentRuntime.open(plan['runtime_directory'],bindings,clock=lambda:owner.center.now())
            owner.center = Center(center_root, keys, key_material['active_key'])
            owner.application = MiniApplication.from_existing_runtime(owner.center,
                owner.persistence.runtime, principals, config, wechat['app_secret'])
            if 'registration_scenes' in plan:
                owner.application.identity.configure_registration(plan['registration_scenes'])
            if plan['reviewers']:
                owner.application.configure_onboarding(plan['reviewers'])
            owner.application.configure_operations(operations,consumer_only=not bool(operations))
            if plan.get('community_grants'):
                owner.application.configure_communities(plan['community_grants'])
            owner.application.configure_commerce()
            owner.plan = plan
            return owner
        except BaseException:
            owner.close()
            raise

    def serve(self):
        if self.application is None:
            raise RuntimeError('OPEN_PLATFORM_HOST_REQUIRED')
        p = self.plan
        server = self.application.listen_proxy(p['socket_path'],p['https_origin'],p['nginx_uid'],p['nginx_gid'])
        # Original serial UnixStreamServer keeps SQLite ownership in this thread.
        try:
            server.serve_forever(poll_interval=0.25)
        finally:
            self.close()

    def close(self):
        first = None
        for target, operation in ((self.application,'close'), (self.center,'db'), (self.persistence,'close')):
            if target is None:
                continue
            try:
                if operation == 'db':
                    target.db.close()
                else:
                    target.close()
            except BaseException as error:
                if first is None:
                    first = error
        self.application = self.center = self.persistence = None
        if self.center_lock is not None:
            os.close(self.center_lock)
            self.center_lock = None
        if first is not None:
            raise first

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Admitted original community platform host')
    parser.add_argument('--plan',required=True)
    parser.add_argument('--center-keys',required=True)
    parser.add_argument('--wechat-secret',required=True)
    args = parser.parse_args(argv)
    def stop(signum,frame):
        raise KeyboardInterrupt()
    previous = signal.signal(signal.SIGTERM,stop)
    try:
        with PlatformHost.open(args.plan,args.center_keys,args.wechat_secret) as host:
            host.serve()
    except KeyboardInterrupt:
        return 0
    except Exception:
        # No plan, keys, provider exception, source path or login details in logs.
        print('BACKEND_NOT_READY', flush=True)
        return 2
    finally:
        signal.signal(signal.SIGTERM,previous)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
