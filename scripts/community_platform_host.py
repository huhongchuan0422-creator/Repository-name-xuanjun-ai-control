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
OPTIONAL_FIELDS = {'registration_scenes','community_grants','provider_reader_config','commerce_provider_config'}


def _require_nonroot():
    if os.geteuid() == 0:
        raise PermissionError('NONROOT_PLATFORM_HOST_REQUIRED')


def _configuration(plan, key_material, wechat):
    if type(plan) is not dict or not FIELDS <= set(plan) <= FIELDS|OPTIONAL_FIELDS or type(plan['version']) is not int or plan['version'] != 1:
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
    for reference in ('provider_reader_config','commerce_provider_config'):
        if reference not in plan:continue
        ref = plan[reference]
        if (type(ref) is not str or not Path(ref).is_absolute()
                or str(Path(ref)) != ref or '..' in Path(ref).parts):
            raise ValueError('PROTECTED_PROVIDER_READER_CONFIG_REF_REQUIRED')
    if 'commerce_provider_config' in plan and (not plan['reviewers'] or 'provider_reader_config' not in plan):
        raise PermissionError('ORIGINAL_ONBOARDING_READER_REQUIRED_FOR_COMMERCE')
    if plan['reviewers'] and 'provider_reader_config' not in plan:
        raise PermissionError('PROTECTED_PROVIDER_READER_REQUIRED_FOR_ONBOARDING')
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


def _open_provider_reader(protected_path, clock):
    """Construct the original verified RSA Reader from an existing protected file.

    Never accepts an HTTP-supplied config, mock transport or relaxed Reader type.
    Credentials do not enter the platform plan, env, CLI arguments or logs.
    """
    from scripts.community_wechat_sp_readonly import PartnerOrderReader
    config = load_protected(protected_path)
    required = {'sp_mchid','merchant_serial','private_key_pem',
                'public_key_id','public_key_pem'}
    if (type(config) is not dict or set(config) != required
            or any(type(config[name]) is not str for name in required)):
        raise ValueError('EXACT_PROTECTED_PROVIDER_READER_CONFIG_REQUIRED')
    return PartnerOrderReader(config['sp_mchid'],config['merchant_serial'],
        config['private_key_pem'].encode('ascii'),
        config['public_key_id'],config['public_key_pem'].encode('ascii'),clock)


def _commerce_policy(protected_path):
    """Read existing protected opt-in only; no secret creation or provider IO.

    JSON arrays represent existing tuple scope keys without changing the original
    provider policy validator. Actual grants/product admissions stay explicit.
    """
    value=load_protected(protected_path)
    fields={'version','applyment_submission_enabled','provider_bindings',
            'payment_admissions','notifications','merchant_bill_grants'}
    if (type(value) is not dict or set(value)!=fields or type(value['version']) is not int
            or value['version']!=1 or type(value['applyment_submission_enabled']) is not bool
            or type(value['provider_bindings']) is not list
            or type(value['payment_admissions']) is not dict
            or type(value['merchant_bill_grants']) is not dict):
        raise ValueError('EXACT_PROTECTED_COMMERCE_POLICY_REQUIRED')
    bindings={}
    for item in value['provider_bindings']:
        if (type(item) is not dict or set(item)!={'scope','policy'}
                or type(item['scope']) is not dict
                or set(item['scope'])!={'tenant_id','merchant_id','store_id'}
                or any(type(v) is not str for v in item['scope'].values())
                or type(item['policy']) is not dict):
            raise ValueError('EXACT_PROVIDER_SCOPE_POLICY_REQUIRED')
        key=tuple(item['scope'][n] for n in ('tenant_id','merchant_id','store_id'))
        if key in bindings:raise ValueError('DUPLICATE_PROVIDER_SCOPE_POLICY')
        bindings[key]=item['policy']
    notification=value['notifications'];key=None
    if notification is not None:
        if (type(notification) is not dict or set(notification)!={'api_v3_key_base64','path'}
                or type(notification['api_v3_key_base64']) is not str
                or type(notification['path']) is not str):
            raise ValueError('EXACT_PROTECTED_NOTIFICATION_POLICY_REQUIRED')
        try:key=base64.b64decode(notification['api_v3_key_base64'],validate=True)
        except (ValueError,TypeError):raise ValueError('INVALID_PROTECTED_API_V3_KEY') from None
        if len(key)!=32:raise ValueError('INVALID_PROTECTED_API_V3_KEY')
        if not value['payment_admissions']:raise ValueError('PAYMENT_ADMISSIONS_REQUIRED_FOR_NOTIFICATIONS')
    if value['merchant_bill_grants'] and not bindings:
        raise ValueError('PROVIDER_BINDINGS_REQUIRED_FOR_BILLS')
    return value,bindings,key


def _wire_commerce(application,reader,policy):
    """Original capabilities, called before listen; all IO remains in original APIs."""
    value,bindings,key=policy
    if bindings:application.configure_provider_actions(reader,bindings)
    if value['payment_admissions']:
        application.configure_dynamic_payments_from_applyments(reader,value['payment_admissions'])
    if value['notifications'] is not None:
        application.configure_payment_notifications(key,value['notifications']['path'])
    if value['merchant_bill_grants']:
        application.configure_merchant_bills(value['merchant_bill_grants'])


class PlatformHost:
    """Own Center and PersistentRuntime; MiniApplication borrows both."""
    def __init__(self):
        self.center = None
        self.persistence = None
        self.application = None
        self.center_lock = None
        self.ocr = None
        self.ocr_lock = None

    @classmethod
    def open(cls, plan_path, keys_path, wechat_path):
        _require_nonroot()
        if hashlib.sha256(Path(__file__).with_name('pr122_customer_core.py').read_bytes()).hexdigest() != CORE_SHA256:
            raise PermissionError('PINNED_CENTER_SOURCE_REQUIRED')
        plan = load_protected(plan_path)
        key_material = load_protected(keys_path)
        wechat = load_protected(wechat_path)
        keys, principals, bindings, operations = _configuration(plan, key_material, wechat)
        commerce_policy = _commerce_policy(plan['commerce_provider_config']) if 'commerce_provider_config' in plan else None
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
                reader = _open_provider_reader(plan['provider_reader_config'], owner.center.now)
                owner.application.configure_wechat_applyment(reader,submission_enabled=commerce_policy[0]['applyment_submission_enabled'] if commerce_policy else False)
            owner.application.configure_operations(operations,consumer_only=not bool(operations))
            if plan.get('community_grants'):
                owner.application.configure_communities(plan['community_grants'])
            owner.application.configure_commerce()
            if commerce_policy is not None:_wire_commerce(owner.application,reader,commerce_policy)
            owner.plan = plan
            return owner
        except BaseException:
            owner.close()
            raise

    def configure_ocr(self, scene, api, store, *, applicant_mode=False):
        """Explicit protected Python opt-in; plan/env/HTTP cannot enable OCR.

        Uses existing Center and admitted encrypted store; no key generation,
        grant, new server, replacement identity or configuration migration.
        """
        if self.application is None or self.application.server is not None or self.ocr is not None:
            raise PermissionError('OCR_HOST_CONFIGURATION_DENIED')
        from scripts.community_mini_merchant import MiniMerchant
        from scripts.community_ocr_host import HostOcr
        app=self.application
        if app.onboarding is None:raise PermissionError('OCR_ONBOARDING_REQUIRED')
        app.center.db.execute('SELECT 1')  # Original owner thread, before opt-in.
        from scripts.community_ocr_bridge import compose
        # compose validates exact pinned dependency/store type before any use.
        # Protected original store must already exist; never initialize it here.
        if type(store) is not api.SecureSQLiteJobStore:raise PermissionError('OCR_ENCRYPTED_STORE_REQUIRED')
        _directory(str(Path(store.db_path).parent))
        store_info=_file(Path(store.db_path))
        original=[Path(self.plan['center_root'])/'center.sqlite']
        original += [Path(self.plan['runtime_directory'])/(name+'.sqlite') for name in NAMES]
        if any((store_info.st_dev,store_info.st_ino)==(info.st_dev,info.st_ino)
               for info in (_file(path) for path in original)):
            raise PermissionError('OCR_SEPARATE_STORE_REQUIRED')
        merchant=MiniMerchant(app.identity,app.onboarding,app.operations)
        self.ocr=HostOcr(merchant,scene,api,store,applicant_mode=applicant_mode)
        app.gateway.ocr=self.ocr
        return self.ocr

    @classmethod
    def preflight_applicant_ocr_plan(cls, plan_path, keys_path, wechat_path):
        """Protected config-only check before service replacement or host open.

        No writable DB, lock, listener, provider request or grant is created.
        Success is configuration validation, not installed OCR readiness.
        """
        _require_nonroot()
        plan = load_protected(plan_path)
        _configuration(plan, load_protected(keys_path), load_protected(wechat_path))
        if not plan['reviewers']:
            raise PermissionError('OCR_ONBOARDING_REQUIRED')
        if any(type(k) is not str or not k or type(v) is not str or not v
               for k, v in plan['reviewers'].items()):
            raise ValueError('ORIGINAL_REVIEWER_PROJECT_BINDING_REQUIRED')
        # Validate original protected Reader locally; construction has no IO.
        _open_provider_reader(plan['provider_reader_config'], lambda: 0)
        return 'OCR_CONFIGURATION_VALIDATED_NOT_ACTIVATED'

    def preflight_applicant_ocr(self):
        """No store construction or writes; retain the original opt-in gate."""
        if self.application is None or self.application.server is not None or self.ocr is not None:
            raise PermissionError('OCR_HOST_CONFIGURATION_DENIED')
        if self.application.onboarding is None:
            raise PermissionError('OCR_ONBOARDING_REQUIRED')
        self.application.center.db.execute('SELECT 1')

    def configure_applicant_ocr(self,key_reference,store_reference):
        """Explicit original-install opt-in using pre-existing protected inputs.

        Does not create keys/files, initialize a missing DB, infer secret paths,
        borrow Center keys, or add project roles. Never called by HTTP or env.
        """
        if self.application is None or self.application.server is not None or self.ocr is not None:
            raise PermissionError('OCR_HOST_CONFIGURATION_DENIED')
        self.preflight_applicant_ocr()  # Must precede key/model/store handling.
        _require_nonroot()
        key_path=Path(key_reference);db_path=Path(store_reference)
        for path in (key_path,db_path):
            if not path.is_absolute() or str(path)!=str(path.absolute()) or '..' in path.parts:
                raise ValueError('EXACT_ABSOLUTE_OCR_REFERENCE_REQUIRED')
            _directory(str(path.parent));_file(path)
        db_info=_file(db_path)
        originals=[Path(self.plan['center_root'])/'center.sqlite']
        originals += [Path(self.plan['runtime_directory'])/(name+'.sqlite') for name in NAMES]
        originals += [key_path]
        if any((db_info.st_dev,db_info.st_ino)==(i.st_dev,i.st_ino) for i in (_file(p) for p in originals)):
            raise PermissionError('OCR_SEPARATE_STORE_REQUIRED')
        material=load_protected(str(key_path))
        if type(material) is not dict or set(material)!={'ocr_encryption_key'} or type(material['ocr_encryption_key']) is not str:
            raise ValueError('EXISTING_OCR_KEY_REFERENCE_REQUIRED')
        from cryptography.fernet import Fernet
        try:
            Fernet(material['ocr_encryption_key'].encode('ascii'))
        except (ValueError, TypeError, UnicodeError):
            raise ValueError('INVALID_EXISTING_OCR_KEY') from None
        from services.ocr_engine import api,ocr_core
        ocr_core._verified_model_paths()  # Original immutable model hashes; no download.
        import json
        pins=json.loads(Path(__file__).with_name('community_ocr_dependency.json').read_text())
        for name,digest in pins['files'].items():
            if hashlib.sha256((Path(api.__file__).parent/name).read_bytes()).hexdigest()!=digest:
                raise PermissionError('OCR_PINNED_DEPENDENCY_REQUIRED')
        lock=os.open(str(db_path),os.O_RDWR|os.O_NOFOLLOW)
        try:
            if (os.fstat(lock).st_dev,os.fstat(lock).st_ino)!=(db_info.st_dev,db_info.st_ino):
                raise PermissionError('OCR_STORE_CHANGED')
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            # _file above requires this exact DB already exists. Constructor
            # may maintain original tables; this is activation, NOT a probe.
            store=api.SecureSQLiteJobStore(str(db_path),material['ocr_encryption_key'].encode('ascii'))
            result=self.configure_ocr('',api,store,applicant_mode=True)
            self.ocr_lock=lock
            return result
        except BaseException:
            os.close(lock);raise

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
        if self.ocr is not None:
            try:
                self.ocr.close()
                # Keep the independent DB lock until its last worker has exited.
                self.ocr.worker.shutdown(wait=True,cancel_futures=True)
            except BaseException as error:first=error
            if self.application is not None:self.application.gateway.ocr=None
            self.ocr=None
        if self.ocr_lock is not None:
            os.close(self.ocr_lock);self.ocr_lock=None
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
    parser.add_argument('--check-applicant-ocr-plan', action='store_true')
    parser.add_argument('--applicant-ocr-key-reference')
    parser.add_argument('--applicant-ocr-store-reference')
    args = parser.parse_args(argv)
    if bool(args.applicant_ocr_key_reference)!=bool(args.applicant_ocr_store_reference):
        parser.error('Both existing applicant OCR references are required')
    def stop(signum,frame):
        raise KeyboardInterrupt()
    previous = signal.signal(signal.SIGTERM,stop)
    try:
        if args.check_applicant_ocr_plan or args.applicant_ocr_key_reference:
            result = PlatformHost.preflight_applicant_ocr_plan(args.plan,args.center_keys,args.wechat_secret)
            if args.check_applicant_ocr_plan:
                print(result, flush=True)
                return 0
        with PlatformHost.open(args.plan,args.center_keys,args.wechat_secret) as host:
            if args.applicant_ocr_key_reference:
                host.configure_applicant_ocr(args.applicant_ocr_key_reference,args.applicant_ocr_store_reference)
            host.serve()
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        # Only fixed allowlisted codes; never arbitrary exception text.
        code = str(error)
        if code not in ('OCR_ONBOARDING_REQUIRED', 'OCR_HOST_CONFIGURATION_DENIED',
                        'INVALID_EXISTING_OCR_KEY', 'OCR_PINNED_DEPENDENCY_REQUIRED',
                        'PROTECTED_PROVIDER_READER_REQUIRED_FOR_ONBOARDING',
                        'ORIGINAL_REVIEWER_PROJECT_BINDING_REQUIRED',
                        'EXACT_PROTECTED_PROVIDER_READER_CONFIG_REQUIRED'):
            code = 'BACKEND_NOT_READY'
        print(code, flush=True)
        return 2
    finally:
        signal.signal(signal.SIGTERM,previous)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
