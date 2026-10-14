"""Fixed UK runtime provisioning for the unified P2 install transaction.

This module never discovers credentials, copies OAuth, installs packages, or
starts a legacy writer.  Every source/target/hash/uid/gid/mode is supplied by
the reviewed plan and checked before the first target mutation.
"""
import hashlib
import json
import os
import pwd
import grp
import re
import socket
import stat
import subprocess
import tempfile

from ledger_cutover_transaction import _atomic_receipt
from p2_prerequisites import Prerequisites
from p2_bootstrap_files import BootstrapFiles,private_read
from p2_publisher_bootstrap import PublisherBootstrap
from p2_sandbox_profile import SandboxProfile
from p2_rpm_prerequisites import RpmPrerequisites
import p2_auxiliary_isolation as Auxiliary
from p2_tls_lifecycle import TlsLifecycle,TIMER as TLS_TIMER,SERVICE as TLS_SERVICE


HOST = 'iZd7oeikknn1z21sq6ji6zZ'
SHA256 = re.compile(r'^[0-9a-f]{64}$')
TOKEN = re.compile(br'@@[A-Z0-9_]+@@')
ALLOWED_SERVICES = (
    'xj-root-broker.socket',
    'xj-root-broker.service',
    'xuanjun-ledger.socket',
    'xuanjun-ledger.service',
    'xuanjun-uk-owner-callback.service',
    'xuanjun-uk-owner-dashboard.service',
    'xuanjun-p2-gateway-relay.socket',
    'xuanjun-p2-gateway-relay.service',
    'xuanjun-development-dispatcher.service',
    'xuanjun-github-intake.timer',
)
STOP_SERVICES = (
    'xuanjun-github-intake.timer',
    'xuanjun-ledger.socket',
    'xj-root-broker.socket',
    'xuanjun-github-intake.service',
    'xuanjun-development-dispatcher.service',
    'xuanjun-p2-gateway-relay.service',
    'xuanjun-p2-gateway-relay.socket',
    'xuanjun-uk-owner-callback.service',
    'xuanjun-uk-owner-dashboard.service',
    'xuanjun-ledger.service',
    'xj-root-broker.service',
)
ALLOWED_TARGET_PREFIXES = (
    '/etc/xuanjun-development/',
    '/etc/systemd/system/',
    '/etc/nginx/conf.d/',
)
GATEWAY_SERVICE='xuanjun-uk-openclaw.service'
GATEWAY_DROPIN_DIR='/etc/systemd/system/xuanjun-uk-openclaw.service.d'
P2_PLUGIN_ID='xuanjun-p2-native-controller'
P2_PLUGIN_CONFIG_PATH='plugins.entries.xuanjun-p2-native-controller.config'


def _digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _read_regular(path, limit=1024 * 1024):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('UNSAFE_REGULAR_FILE_REFERENCE')
        data = b''
        while len(data) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(data)))
            if not chunk: break
            data += chunk
        if len(data) > limit: raise ValueError('REFERENCE_TOO_LARGE')
        return data, info
    finally:
        os.close(fd)


def _dropin_rollback_present(plugin_receipt, prepared):
    """The legacy receipt records creation intent, not completed mkdir.

    Missing owned directory is a no-effect state only when EVERY planned target
    still has its authenticated original state. Never create a directory merely
    to let rollback pass. Any installed/drifted target keeps the transaction HOLD.
    """
    if not plugin_receipt['dropin_parent_created']:
        return False
    if not os.path.lexists(GATEWAY_DROPIN_DIR):
        for item, unused in prepared:
            path, previous = item['target'], item['previous']
            if previous is None:
                if os.path.lexists(path):
                    raise ValueError('HOLD_MISSING_DROPIN_WITH_TARGET_EFFECT')
            elif previous.get('masked') is True:
                if not Auxiliary.is_mask(path):
                    raise ValueError('HOLD_MISSING_DROPIN_WITH_MASK_EFFECT')
            else:
                data, info = _read_regular(path)
                if (_digest_bytes(data), stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid) != (
                        previous['sha256'], previous['mode'], previous['uid'], previous['gid']):
                    raise ValueError('HOLD_MISSING_DROPIN_WITH_TARGET_DRIFT')
        return False
    info = os.lstat(GATEWAY_DROPIN_DIR)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != 0o755):
        raise ValueError('HOLD_GATEWAY_DROPIN_DIRECTORY_CHANGED')
    return True


class FixedHostRuntime(object):
    def __init__(self, transaction_directory, run=subprocess.run):
        if (not os.path.isabs(transaction_directory)
                or os.path.realpath(transaction_directory) != transaction_directory):
            raise ValueError('CANONICAL_RUNTIME_TRANSACTION_DIRECTORY_REQUIRED')
        self.directory = transaction_directory
        self.run = run
        self.receipt_path = os.path.join(transaction_directory, 'runtime-provisioning.json')
        self.prerequisites = Prerequisites(transaction_directory, run)

    def _authority(self):
        if os.geteuid() != 0 or socket.gethostname().split('.')[0] != HOST:
            raise ValueError('FIXED_UK_ROOT_RUNTIME_REQUIRED')
        info = os.lstat(self.directory)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise ValueError('PROTECTED_RUNTIME_TRANSACTION_DIRECTORY_REQUIRED')

    def _command(self, command):
        result = self.run(command, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=45, check=False)
        if result.returncode:
            raise RuntimeError('RUNTIME_COMMAND_FAILED')

    def _openclaw(self,runtime,args,allow_failure=False,capture=False):
        plugin=runtime['plugin']
        command=['/usr/sbin/runuser','--user',plugin['service_user'],'--',
                 plugin['openclaw_bin']]+list(args)
        result=self.run(command,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
                        env={'HOME':'/home/xuanjun_dev','PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},
                        timeout=60,check=False)
        SandboxProfile(self.directory).capture()
        if result.returncode and not allow_failure:
            raise RuntimeError('OPENCLAW_PLUGIN_COMMAND_FAILED')
        return result

    @staticmethod
    def _json_has_plugin(value,plugin_id):
        if isinstance(value,dict):
            if value.get('id')==plugin_id or value.get('pluginId')==plugin_id:return True
            return any(FixedHostRuntime._json_has_plugin(v,plugin_id) for v in value.values())
        if isinstance(value,list):
            return any(FixedHostRuntime._json_has_plugin(v,plugin_id) for v in value)
        return False

    def _plugin_present(self,runtime):
        result=self._openclaw(runtime,['plugins','list','--json'],capture=True)
        try:value=json.loads(result.stdout.decode('utf-8'))
        except Exception:raise ValueError('OPENCLAW_PLUGIN_INVENTORY_INVALID')
        return self._json_has_plugin(value,P2_PLUGIN_ID)

    def _stop_gateway(self):
        self._command(['/usr/bin/systemctl','stop',GATEWAY_SERVICE])
        result=self.run(['/usr/bin/systemctl','is-active','--quiet',GATEWAY_SERVICE],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=False)
        if result.returncode==0:raise RuntimeError('GATEWAY_STOP_UNCONFIRMED')

    def _start_gateway(self):
        self._command(['/usr/bin/systemctl','start',GATEWAY_SERVICE])
        self._command(['/usr/bin/systemctl','is-active','--quiet',GATEWAY_SERVICE])

    @staticmethod
    def _dropin_parent_state():
        if os.path.lexists(GATEWAY_DROPIN_DIR):
            info=os.lstat(GATEWAY_DROPIN_DIR)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_gid!=0
                    or stat.S_IMODE(info.st_mode)!=0o755):
                raise ValueError('UNSAFE_GATEWAY_DROPIN_DIRECTORY')
            return False
        return True

    @staticmethod
    def _create_dropin_parent():
        parent=os.path.dirname(GATEWAY_DROPIN_DIR)
        info=os.lstat(parent)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_gid!=0
                or info.st_mode&0o022):
            raise ValueError('UNSAFE_SYSTEMD_DIRECTORY')
        os.mkdir(GATEWAY_DROPIN_DIR,0o755)
        os.chown(GATEWAY_DROPIN_DIR,0,0)
        os.chmod(GATEWAY_DROPIN_DIR,0o755)
        fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)

    @staticmethod
    def _remove_created_dropin_parent():
        if not os.path.lexists(GATEWAY_DROPIN_DIR):return
        info=os.lstat(GATEWAY_DROPIN_DIR)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_gid!=0
                or stat.S_IMODE(info.st_mode)!=0o755 or os.listdir(GATEWAY_DROPIN_DIR)):
            raise ValueError('HOLD_GATEWAY_DROPIN_DIRECTORY_CHANGED')
        os.rmdir(GATEWAY_DROPIN_DIR)
        parent=os.path.dirname(GATEWAY_DROPIN_DIR)
        fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)

    def _install_plugin(self,release,runtime):
        plugin=runtime['plugin'];source=os.path.realpath(os.path.join(release,plugin['source']))
        if not source.startswith(release+'/') or not os.path.isdir(source):
            raise ValueError('P2_PLUGIN_SOURCE_REQUIRED')
        if self._plugin_present(runtime):raise ValueError('P2_PLUGIN_ALREADY_PRESENT')
        self._stop_gateway()
        try:
            SandboxProfile(self.directory).apply(runtime.get('sandbox_policy'))
            self._openclaw(runtime,['plugins','install',source,'--force','--no-enable','--accept-capabilities'])
            config=json.dumps({'bindingFile':plugin['binding_file'],'bindingSha256':plugin['binding_sha256']},
                              sort_keys=True,separators=(',',':'))
            self._openclaw(runtime,['config','set',P2_PLUGIN_CONFIG_PATH,config,'--strict-json'])
            self._openclaw(runtime,['plugins','enable',P2_PLUGIN_ID,'--accept-capabilities'])
            self._openclaw(runtime,['config','validate','--json'])
        except Exception:
            try:self._rollback_plugin(runtime,restart=False)
            except Exception:pass
            raise

    def _verify_plugin_runtime(self,runtime):
        inspected=self._openclaw(runtime,['plugins','inspect',P2_PLUGIN_ID,'--runtime','--json'],capture=True)
        value=json.loads(inspected.stdout.decode('utf-8','replace'))
        packed=json.dumps(value,sort_keys=True,separators=(',',':'))
        if (not self._json_has_plugin(value,P2_PLUGIN_ID)
                or 'xuanjun.execution.start' not in packed
                or 'xuanjun.execution.inspect' not in packed):
            raise ValueError('P2_PLUGIN_RUNTIME_REGISTRATION_UNPROVEN')

    def _rollback_plugin(self,runtime,restart):
        SandboxProfile(self.directory).rollback_check()
        self._stop_gateway()
        try:
            if self._plugin_present(runtime):
                self._openclaw(runtime,['plugins','uninstall',P2_PLUGIN_ID,'--force'])
            self._openclaw(runtime,['config','unset',P2_PLUGIN_CONFIG_PATH],allow_failure=True)
            self._openclaw(runtime,['config','unset','plugins.entries.'+P2_PLUGIN_ID],allow_failure=True)
            self._openclaw(runtime,['config','validate','--json'])
            SandboxProfile(self.directory).rollback()
        except Exception:
            raise
        else:
            if restart:self._start_gateway()

    @staticmethod
    def _reference(value):
        # Existing OAuth stores may be several MiB; still bounded and read-only.
        data, info = _read_regular(value['path'], limit=16*1024*1024)
        if (info.st_uid != value['owner_uid']
                or stat.S_IMODE(info.st_mode) != value['mode']
                or _digest_bytes(data) != value['sha256']):
            raise ValueError('REFERENCE_IDENTITY_MISMATCH')

    @staticmethod
    def _binding(binding, release, auxiliary=None):
        required = {'source', 'target', 'source_sha256', 'rendered_sha256',
                    'mode', 'owner_uid', 'group_gid', 'replacements'}
        if not isinstance(binding, dict) or set(binding) != required:
            raise ValueError('EXACT_PROVISIONING_BINDING_REQUIRED')
        source = os.path.realpath(os.path.join(release, binding['source']))
        target = binding['target']
        if (not isinstance(binding['source'], str) or binding['source'].startswith('/')
                or '..' in binding['source'].split('/')
                or not source.startswith(release + '/')
                or not isinstance(target, str) or (os.path.realpath(target) != target and not (auxiliary is not None and Auxiliary.is_mask(target)))
                or not any(target.startswith(prefix) for prefix in ALLOWED_TARGET_PREFIXES)
                or not SHA256.fullmatch(binding.get('source_sha256', ''))
                or not SHA256.fullmatch(binding.get('rendered_sha256', ''))
                or type(binding.get('mode')) is not int or binding['mode'] & 0o022
                or type(binding.get('owner_uid')) is not int
                or type(binding.get('group_gid')) is not int
                or not isinstance(binding.get('replacements'), dict)):
            raise ValueError('INVALID_PROVISIONING_BINDING')
        if Auxiliary.is_mask(target):Auxiliary.verify(auxiliary)
        for token, replacement in binding['replacements'].items():
            if (not isinstance(token, str) or not re.fullmatch(r'@@[A-Z0-9_]+@@', token)
                    or not isinstance(replacement, str) or '\x00' in replacement):
                raise ValueError('INVALID_RUNTIME_REPLACEMENT')
        return source, target

    def _verify_gateway_preflight(self,runtime):
        if 'legacy_cutover' in runtime:
            if not isinstance(runtime['legacy_cutover'],dict) or 'legacy_isolation' not in runtime['legacy_cutover']:
                raise ValueError('ADOPTED_GATEWAY_REFERENCE_REQUIRED')
            from legacy_host_adapter import LegacyHostAdapter
            if LegacyHostAdapter(self.directory).preflight(runtime['legacy_cutover']) is not True:
                raise ValueError('ADOPTED_GATEWAY_PREFLIGHT_FAILED')
            return
        result=self.run(['/usr/bin/systemctl','is-active','--quiet',GATEWAY_SERVICE],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=False)
        if result.returncode!=0:raise ValueError('GATEWAY_MUST_BE_ACTIVE_BEFORE_P2')

    def preflight(self, runtime, auth, tls):
        self._authority()
        if tuple(runtime['services']) != ALLOWED_SERVICES:
            raise ValueError('EXACT_RUNTIME_SERVICE_ORDER_REQUIRED')
        if os.path.lexists(self.receipt_path):
            raise ValueError('HOLD_EXISTING_RUNTIME_RECEIPT')
        if 'legacy_cutover' in runtime or 'auxiliary_isolation' in runtime:
            Auxiliary.verify(runtime.get('auxiliary_isolation'))
        if 'tls_renewal' in runtime:TlsLifecycle(self.directory).prepare(runtime['tls_renewal'])
        self.prerequisites.preflight(runtime['prerequisites'])
        BootstrapFiles(self.directory).prepare(runtime.get('bootstrap'),runtime['release_directory'])
        PublisherBootstrap(self.directory).prepare(runtime.get('publisher'))
        SandboxProfile(self.directory).prepare(runtime.get('sandbox_policy'))
        RpmPrerequisites(self.directory).prepare(runtime.get('rpm'),runtime['prerequisites'])
        plugin=runtime['plugin']
        if plugin['gateway_service']!=GATEWAY_SERVICE or plugin['id']!=P2_PLUGIN_ID:
            raise ValueError('P2_PLUGIN_POLICY')
        matches=[binding for binding in runtime['provisioning'] if binding.get('target')==plugin['binding_file']]
        clients=[binding for binding in runtime['provisioning'] if binding.get('target')==plugin['ledger_client_config']]
        dropins=[binding for binding in runtime['provisioning'] if binding.get('target')==plugin['docker_dropin']]
        relays=[binding for binding in runtime['provisioning'] if binding.get('target')==plugin['gateway_relay_config']]
        owners=[binding for binding in runtime['provisioning'] if binding.get('target')=='/etc/xuanjun-development/p2-owner-feishu-binding.json']
        if len(owners)!=1:raise ValueError('OWNER_FEISHU_PROVISIONING_REQUIRED')
        owner=owners[0];replacements=owner.get('replacements',{})
        if (owner.get('source')!='deploy/p2-owner-feishu-binding.json.template' or owner.get('owner_uid')!=0
                or owner.get('mode')!=0o640 or owner.get('group_gid')!=pwd.getpwnam('xuanjun_dev').pw_gid
                or set(replacements)!={'@@CHAT_ID@@','@@APP_ID@@','@@PACKAGE_SHA256@@'}
                or not re.fullmatch(r'oc_[A-Za-z0-9_-]{1,128}',replacements.get('@@CHAT_ID@@',''))
                or not re.fullmatch(r'cli_[A-Za-z0-9_-]{1,128}',replacements.get('@@APP_ID@@',''))
                or not SHA256.fullmatch(replacements.get('@@PACKAGE_SHA256@@',''))):
            raise ValueError('OWNER_FEISHU_PROVISIONING_BINDING_REJECTED')
        profiles=[reference for reference in auth['references'] if reference.get('path')=='/home/xuanjun_dev/.openclaw/openclaw.json']
        if (len(profiles)!=1 or profiles[0].get('owner_uid')!=pwd.getpwnam('xuanjun_dev').pw_uid
                or profiles[0].get('mode')!=0o600):raise ValueError('OWNER_FEISHU_EXISTING_PROFILE_REFERENCE_REQUIRED')
        if (len(matches)!=1 or matches[0].get('rendered_sha256')!=plugin['binding_sha256']
                or len(clients)!=1 or clients[0].get('rendered_sha256')!=plugin['ledger_client_sha256']
                or len(relays)!=1 or relays[0].get('rendered_sha256')!=plugin['gateway_relay_sha256']
                or len(dropins)!=1):
            raise ValueError('P2_PLUGIN_PROVISIONING_BINDING')
        self._verify_gateway_preflight(runtime)
        if self._plugin_present(runtime):raise ValueError('P2_PLUGIN_ALREADY_PRESENT')
        for reference in auth['references'] + tls['references']:
            self._reference(reference)
        release = '/opt/xuanjun-control-releases/' + runtime['release_directory']
        if os.path.realpath(release) != release:
            raise ValueError('NON_CANONICAL_RELEASE_DIRECTORY')
        seen = set()
        for binding in runtime['provisioning']:
            source, target = self._binding(binding, release, runtime.get('auxiliary_isolation'))
            if target in seen: raise ValueError('DUPLICATE_RUNTIME_TARGET')
            seen.add(target)
            # The immutable release does not exist on a first installation.
            # Its installer verifies every source hash before staging; verify
            # the installed bytes again in provision before target effects.
        return True

    @staticmethod
    def _render(source, binding):
        value = source
        for token in sorted(binding['replacements']):
            value = value.replace(token.encode('ascii'),
                                  binding['replacements'][token].encode('utf-8'))
        if TOKEN.search(value): raise ValueError('UNRESOLVED_RUNTIME_PLACEHOLDER')
        if _digest_bytes(value) != binding['rendered_sha256']:
            raise ValueError('RUNTIME_RENDERED_HASH_MISMATCH')
        return value

    @staticmethod
    def _atomic_target(path, data, mode, uid, gid):
        parent = os.path.dirname(path)
        info = os.lstat(parent)
        if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022:
            raise ValueError('UNSAFE_RUNTIME_TARGET_PARENT')
        fd, temporary = tempfile.mkstemp(prefix='.p2-runtime-', dir=parent)
        try:
            os.fchmod(fd, mode); os.fchown(fd, uid, gid)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    def prepare_prerequisites(self,runtime):
        self._authority()
        return self.prerequisites.apply(runtime['prerequisites'])

    def restore_prerequisites(self,runtime):
        if os.path.lexists(self.receipt_path):
            receipt=json.loads(private_read(self.prerequisites.path).decode())
            if receipt.get('restored') is not True:
                raise ValueError('HOLD_PROVISION_RECONCILIATION_BEFORE_NSS_ROLLBACK')
        return self.prerequisites.rollback(runtime['prerequisites'])

    def provision(self, release, runtime):
        self._authority()
        if 'legacy_cutover' in runtime or 'auxiliary_isolation' in runtime:
            Auxiliary.verify(runtime.get('auxiliary_isolation'))
        expected = '/opt/xuanjun-control-releases/' + runtime['release_directory']
        if release != expected: raise ValueError('RUNTIME_RELEASE_MISMATCH')
        prepared = []
        for number, binding in enumerate(runtime['provisioning']):
            source, target = self._binding(binding, release, runtime.get('auxiliary_isolation'))
            data, unused = _read_regular(source)
            if _digest_bytes(data) != binding['source_sha256']:
                raise ValueError('RUNTIME_SOURCE_HASH_MISMATCH')
            rendered = self._render(data, binding)
            previous = None
            if Auxiliary.is_mask(target):
                backup=os.path.join(self.directory,'target-%03d.backup'%number)
                previous=Auxiliary.mask_previous(runtime.get('auxiliary_isolation'),target,backup)
            elif os.path.lexists(target):
                old, info = _read_regular(target)
                backup = os.path.join(self.directory, 'target-%03d.backup' % number)
                fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             getattr(os, 'O_NOFOLLOW', 0), 0o600)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(old); stream.flush(); os.fsync(stream.fileno())
                previous = {'backup': backup, 'sha256': _digest_bytes(old),
                            'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid,
                            'gid': info.st_gid}
            prepared.append({'target': target, 'previous': previous,
                             'rendered_sha256': binding['rendered_sha256'],
                             'mode': binding['mode'], 'uid': binding['owner_uid'],
                             'gid': binding['group_gid'], 'data': rendered})
        if 'tls_renewal' in runtime:
            tls_value=TlsLifecycle(self.directory).prepare(runtime['tls_renewal'])
            configs=[item for item in prepared if item['target']=='/etc/xuanjun-development/tls-renewal.json']
            if len(configs)!=1 or json.loads(configs[0]['data'].decode())!=tls_value:raise ValueError('TLS_RENDERED_CONFIG_BINDING')
            required={'/etc/systemd/system/'+TLS_TIMER,'/etc/systemd/system/'+TLS_SERVICE,'/etc/systemd/system/nginx.service','/etc/xuanjun-development/nginx-main.conf'}
            if not required.issubset({item['target'] for item in prepared}):raise ValueError('TLS_TIMER_SERVICE_BINDING')
        create_dropin_parent=self._dropin_parent_state()
        receipt = {'schema': 1, 'targets': [dict(item, data=None) for item in prepared],
                   'services': list(ALLOWED_SERVICES), 'rollback_complete': True,
                   'prerequisites': runtime['prerequisites'],
                   'plugin': {'id': P2_PLUGIN_ID, 'previous': 'ABSENT',
                              'gateway_service': GATEWAY_SERVICE,
                              'dropin_parent_created': create_dropin_parent}}
        if 'auxiliary_isolation' in runtime:receipt['auxiliary_isolation']=runtime['auxiliary_isolation']
        if 'tls_renewal' in runtime:receipt['tls_renewal']=runtime['tls_renewal']
        packed = json.dumps(receipt, sort_keys=True,
                            separators=(',', ':')).encode('utf-8')
        reference = {'schema': 1, 'receipt_sha256': _digest_bytes(packed),
                     'rollback_complete': True}
        _atomic_receipt(self.receipt_path, receipt)
        try:
            RpmPrerequisites(self.directory).apply(runtime.get('rpm'),runtime['prerequisites'])
            BootstrapFiles(self.directory).apply(runtime.get('bootstrap'),runtime['release_directory'])
            PublisherBootstrap(self.directory).apply(runtime.get('publisher'))
            if 'tls_renewal' in runtime:TlsLifecycle(self.directory).apply(runtime['tls_renewal'])
            if create_dropin_parent:self._create_dropin_parent()
            for item in prepared:
                self._atomic_target(item['target'], item['data'], item['mode'],
                                    item['uid'], item['gid'])
            self._command(['/usr/bin/systemctl', 'daemon-reload'])
            if any(item['target'].startswith('/etc/nginx/') for item in prepared):
                self._command(['/usr/sbin/nginx', '-t', '-c', '/etc/xuanjun-development/nginx-main.conf'])
            self._install_plugin(release,runtime)
            return reference
        except Exception:
            # The receipt was durable before the first target effect. Restore
            # the exact previous bytes immediately; the outer transaction will
            # still enter HOLD/ROLLED_BACK and never restart a legacy writer.
            self.restore(reference)
            raise

    def reopen_database(self, descriptor):
        self._authority()
        path = descriptor.get('db_path')
        if (descriptor.get('state') != 'QUIESCED'
                or not isinstance(path, str)
                or not path.startswith('/var/lib/xuanjun-development/generations/')
                or os.path.realpath(path) != path):
            raise ValueError('QUIESCED_CANONICAL_DATABASE_REQUIRED')
        self._prepare_database_access(path)
        self._command(['/usr/sbin/runuser','--user','xuanjun-dispatcher','--',
                       '/usr/bin/python3', '-I', '-B', '-c',
                       'import sqlite3,sys,pathlib;d=sqlite3.connect(pathlib.Path(sys.argv[1]).as_uri()+"?mode=ro",uri=True);assert d.execute("PRAGMA quick_check").fetchone()[0]=="ok";d.close()',
                       path])
        return {'database_reopened': True}

    def _prepare_database_access(self,path):
        raw,info=_read_regular(self.receipt_path)
        if info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600:
            raise ValueError('PROTECTED_RUNTIME_RECEIPT_REQUIRED')
        plan=json.loads(raw.decode('utf-8'))['prerequisites']
        from p2_prerequisites import validate
        validate(plan)
        uid=plan['users']['xuanjun-dispatcher']['uid']
        gid=plan['groups']['xuanjun-control-db']
        if (pwd.getpwnam('xuanjun-dispatcher').pw_uid!=uid
                or grp.getgrnam('xuanjun-control-db').gr_gid!=gid):
            raise ValueError('LEDGER_CONSUMER_IDENTITY_MISMATCH')
        parent=os.path.dirname(path)
        declared=[x for x in plan['directories'] if x['path']==parent]
        if (len(declared)!=1 or declared[0]['uid']!=uid
                or declared[0]['gid']!=gid or declared[0]['mode']!=0o700):
            raise ValueError('PRIVATE_DECLARED_GENERATION_DIRECTORY_REQUIRED')
        self.prerequisites.directory_matches(declared[0])
        if any(os.path.lexists(path+suffix) for suffix in ('-wal','-shm')):
            raise ValueError('STAGED_LEDGER_SIDECAR_HOLD')
        journal=os.path.join(self.directory,'ledger-access.json')
        if os.path.lexists(journal):
            raise ValueError('HOLD_EXISTING_LEDGER_ACCESS_JOURNAL')
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            info=os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1
                    or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600):
                raise ValueError('FRESH_ROOT_STAGED_LEDGER_REQUIRED')
            receipt={'schema':1,'path':path,'device':info.st_dev,'inode':info.st_ino,
                     'previous_uid':info.st_uid,'previous_gid':info.st_gid,
                     'uid':uid,'gid':gid,'mode':0o600,'state':'INTENT'}
            _atomic_receipt(journal,receipt)
            os.fchown(fd,uid,gid)
            os.fsync(fd)
            after=os.fstat(fd)
            current=os.lstat(path)
            if ((after.st_uid,after.st_gid,stat.S_IMODE(after.st_mode))!=(uid,gid,0o600)
                    or (current.st_dev,current.st_ino)!=(info.st_dev,info.st_ino)):
                raise ValueError('HOLD_LEDGER_ACCESS_IDENTITY_CHANGED')
            receipt['state']='DONE';_atomic_receipt(journal,receipt)
        finally:
            os.close(fd)

    def _unit_enable_state(self, unit):
        result=self.run(['/usr/bin/systemctl','is-enabled',unit],
                        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                        timeout=15,check=False,env={'PATH':'/usr/bin:/bin','LANG':'C'})
        value=result.stdout.decode('ascii').strip()
        if ((value=='enabled' and result.returncode==0)
                or (value=='disabled' and result.returncode==1)):
            return value
        raise ValueError('HOLD_UNSUPPORTED_UNIT_ENABLE_STATE')

    def _boot_binding(self):
        raw,info=_read_regular(self.receipt_path)
        if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600:
            raise ValueError('UNSAFE_BOOT_PROVISION_RECEIPT')
        return _digest_bytes(raw)

    def _boot_units(self,binding):
        raw,info=_read_regular(self.receipt_path)
        if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600 or _digest_bytes(raw)!=binding:
            raise ValueError('BOOT_PROVISION_CHANGED')
        value=json.loads(raw.decode());targets=value.get('targets',[])
        if not isinstance(targets,list) or any(not isinstance(t,dict) or not isinstance(t.get('target'),str) for t in targets):
            raise ValueError('BOOT_TARGET_SCOPE')
        extra=('nginx.service',) if any(t['target'].startswith('/etc/nginx/') for t in targets) else ()
        if any(t['target']=='/etc/systemd/system/'+TLS_TIMER for t in targets):extra+=(TLS_TIMER,)
        return tuple(ALLOWED_SERVICES)+(GATEWAY_SERVICE,)+extra

    def _boot_read(self, binding):
        path=os.path.join(self.directory,'runtime-boot.json')
        raw,info=_read_regular(path)
        if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600:
            raise ValueError('UNSAFE_BOOT_JOURNAL')
        value=json.loads(raw.decode('utf-8'))
        if (not isinstance(value,dict)
                or set(value)!={'schema','provision_sha256','state','previous'}
                or type(value['schema']) is not int or value['schema']!=1
                or value['provision_sha256']!=binding
                or value['state'] not in ('ENABLE_REQUESTED','ENABLED','RESTORED')
                or not isinstance(value['previous'],dict)
                or set(value['previous'])!=set(self._boot_units(binding))
                or any(v not in ('enabled','disabled') for v in value['previous'].values())):
            raise ValueError('BOOT_JOURNAL_BINDING_MISMATCH')
        return value

    def _enable_boot(self):
        binding=self._boot_binding()
        path=os.path.join(self.directory,'runtime-boot.json')
        if os.path.lexists(path):
            value=self._boot_read(binding)
            if value['state']=='RESTORED':raise ValueError('BOOT_TRANSACTION_ALREADY_RESTORED')
        else:
            previous={unit:self._unit_enable_state(unit)
                      for unit in self._boot_units(binding)}
            value={'schema':1,'provision_sha256':binding,
                   'state':'ENABLE_REQUESTED','previous':previous}
            # Durable intent and all original states precede the first enable.
            _atomic_receipt(path,value)
        for unit in self._boot_units(binding):
            self._command(['/usr/bin/systemctl','enable',unit])
            if self._unit_enable_state(unit)!='enabled':
                raise ValueError('BOOT_ENABLE_UNPROVEN')
        value['state']='ENABLED';_atomic_receipt(path,value)

    def _restore_boot(self):
        path=os.path.join(self.directory,'runtime-boot.json')
        if not os.path.lexists(path):return
        binding=self._boot_binding();value=self._boot_read(binding)
        # Validate every observed state before any rollback effect. Only the
        # reviewed persistent enabled/disabled states are supported.
        for unit in self._boot_units(binding):
            self._unit_enable_state(unit)
        for unit in reversed(self._boot_units(binding)):
            previous=value['previous'][unit]
            if self._unit_enable_state(unit)!=previous:
                self._command(['/usr/bin/systemctl',
                               'enable' if previous=='enabled' else 'disable',unit])
            if self._unit_enable_state(unit)!=previous:
                raise ValueError('BOOT_ROLLBACK_UNPROVEN')
        value['state']='RESTORED';_atomic_receipt(path,value)

    def activate(self, runtime, descriptor):
        self._authority()
        if descriptor.get('state') != 'ACTIVE':
            raise ValueError('ACTIVE_DESCRIPTOR_REQUIRED_BEFORE_SERVICES')
        from owner_feishu_https import installed_binding
        if installed_binding()['package_sha256']!=descriptor.get('release_sha256'):
            raise ValueError('OWNER_FEISHU_ACTIVE_PACKAGE_MISMATCH')
        self._enable_boot()
        # The caller restored only the Gateway unit after cutover. Start that
        # admitted parent before relay/dispatcher preflight, never the old coordinator.
        self._start_gateway()
        self._verify_plugin_runtime(runtime)
        for service in ALLOWED_SERVICES:
            self._command(['/usr/bin/systemctl', 'start', service])
            self._command(['/usr/bin/systemctl', 'is-active', '--quiet', service])
        if any(binding['target'].startswith('/etc/nginx/')
               for binding in runtime['provisioning']):
            self._command(['/usr/sbin/nginx', '-t', '-c', '/etc/xuanjun-development/nginx-main.conf'])
            self._command(['/usr/bin/systemctl', 'start', 'nginx.service'])
            self._command(['/usr/bin/systemctl', 'is-active', '--quiet',
                           'nginx.service'])
        if 'tls_renewal' in runtime:
            self._command(['/usr/bin/systemctl','start',TLS_TIMER])
            self._command(['/usr/bin/systemctl','is-active','--quiet',TLS_TIMER])
        return {'services_active': True}

    def stop_new(self, runtime):
        self._authority()
        if 'tls_renewal' in runtime:
            self._command(['/usr/bin/systemctl','stop',TLS_TIMER])
            self._command(['/usr/bin/systemctl','stop',TLS_SERVICE])
        if any(item['target'].startswith('/etc/nginx/') for item in runtime.get('provisioning',[])):
            self._command(['/usr/bin/systemctl','stop','nginx.service'])
        for service in STOP_SERVICES:
            self._command(['/usr/bin/systemctl', 'stop', service])
        self._stop_gateway()
        return True

    def restore(self, provision):
        self._authority()
        data, unused = _read_regular(self.receipt_path)
        receipt = json.loads(data.decode('utf-8'))
        packed = json.dumps(receipt, sort_keys=True,
                            separators=(',', ':')).encode('utf-8')
        if _digest_bytes(packed) != provision['receipt_sha256']:
            raise ValueError('RUNTIME_ROLLBACK_RECEIPT_MISMATCH')
        plugin_receipt=receipt.get('plugin')
        if (not isinstance(plugin_receipt,dict)
                or set(plugin_receipt)!={'id','previous','gateway_service','dropin_parent_created'}
                or plugin_receipt.get('id')!=P2_PLUGIN_ID
                or plugin_receipt.get('previous')!='ABSENT'
                or plugin_receipt.get('gateway_service')!=GATEWAY_SERVICE
                or type(plugin_receipt.get('dropin_parent_created')) is not bool):
            raise ValueError('P2_PLUGIN_ROLLBACK_RECEIPT_MISMATCH')
        aux_snapshot=Auxiliary.verify(receipt['auxiliary_isolation'],masked=False) if 'auxiliary_isolation' in receipt else None
        # Validate every backup and current target before any rollback effect.
        # A failed provision may leave either old or installed bytes in place.
        prepared = []
        seen = set()
        for item in reversed(receipt['targets']):
            target = item['target']
            masked_previous=isinstance(item.get('previous'),dict) and item['previous'].get('masked') is True
            if masked_previous and (not Auxiliary.scoped(target) or aux_snapshot is None or item['previous'].get('sha256')!=aux_snapshot['unit_hashes'][os.path.basename(target)] or (item['previous'].get('mode'),item['previous'].get('uid'),item['previous'].get('gid'))!=(0o644,0,0)):raise ValueError('AUX_ROLLBACK_MASK_BINDING')
            if (not isinstance(target, str) or not os.path.isabs(target)
                    or (os.path.realpath(target) != target and not (masked_previous and Auxiliary.is_mask(target))) or target in seen
                    or not any(target.startswith(p) for p in ALLOWED_TARGET_PREFIXES)):
                raise ValueError('UNSAFE_RUNTIME_ROLLBACK_TARGET')
            seen.add(target)
            previous = item['previous']
            if not os.path.exists(os.path.dirname(target)) and previous is None and not os.path.lexists(target):
                prepared.append((item, None))
                continue
            parent = os.lstat(os.path.dirname(target))
            if (not stat.S_ISDIR(parent.st_mode) or parent.st_mode & 0o022):
                raise ValueError('UNSAFE_RUNTIME_TARGET_PARENT')
            previous = item['previous']
            old = None
            if previous is not None:
                backup = previous['backup']
                if (os.path.dirname(backup) != self.directory
                        or os.path.realpath(backup) != backup):
                    raise ValueError('UNSAFE_RUNTIME_ROLLBACK_BACKUP')
                old, info = _read_regular(backup)
                if _digest_bytes(old) != previous['sha256']:
                    raise ValueError('RUNTIME_ROLLBACK_BACKUP_CHANGED')
            if masked_previous and Auxiliary.is_mask(target):
                prepared.append((item,old));continue
            if os.path.lexists(target):
                current, info = _read_regular(target)
                observed = (_digest_bytes(current), stat.S_IMODE(info.st_mode),
                            info.st_uid, info.st_gid)
                allowed = [(item['rendered_sha256'], item['mode'], item['uid'], item['gid'])]
                if previous is not None:
                    allowed.append((previous['sha256'], previous['mode'],
                                    previous['uid'], previous['gid']))
                if observed not in allowed:
                    raise ValueError('RUNTIME_ROLLBACK_TARGET_CHANGED')
            elif previous is not None:
                raise ValueError('RUNTIME_ROLLBACK_TARGET_MISSING')
            prepared.append((item, old))
        dropin_present = _dropin_rollback_present(plugin_receipt, prepared)
        if 'tls_renewal' in receipt:TlsLifecycle(self.directory).rollback_check()
        BootstrapFiles(self.directory).rollback_rows()
        PublisherBootstrap(self.directory).rollback_rows()
        SandboxProfile(self.directory).rollback_check()
        RpmPrerequisites(self.directory).rollback_rows()
        self._restore_boot()
        # All receipt, backup, target and service-drop-in evidence has passed.
        # External rollback effects may start only after this point.
        self._rollback_plugin({'plugin': {'id':P2_PLUGIN_ID,'service_user':'xuanjun_dev',
            'openclaw_bin':'/home/xuanjun_dev/.openclaw/bin/openclaw'}},restart=False)
        for item, old in prepared:
            previous = item['previous']
            if previous is None:
                if os.path.lexists(item['target']):
                    os.unlink(item['target'])
                    directory = os.open(os.path.dirname(item['target']),
                                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                    try: os.fsync(directory)
                    finally: os.close(directory)
            elif previous.get('masked') is True:
                Auxiliary.restore_mask(item['target'])
            else:
                self._atomic_target(item['target'], old, previous['mode'],
                                    previous['uid'], previous['gid'])
        if dropin_present:
            self._remove_created_dropin_parent()
        PublisherBootstrap(self.directory).rollback()
        BootstrapFiles(self.directory).rollback()
        if 'tls_renewal' in receipt:TlsLifecycle(self.directory).rollback()
        RpmPrerequisites(self.directory).rollback()
        self.prerequisites.rollback(receipt['prerequisites'])
        self._command(['/usr/bin/systemctl', 'daemon-reload'])
        return {'restored': True, 'services_restarted': False}
