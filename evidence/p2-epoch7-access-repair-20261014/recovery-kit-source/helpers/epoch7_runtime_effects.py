"""Finite epoch7 -> epoch8 runtime effects. No entrypoint or admission defaults.

This deliberately does not inherit FixedHostRuntime or RetainedEpoch5Runtime:
provision/TLS/prerequisite replay and generic restore cannot be reached here.
Original sandbox policy/read/publish primitives and exact DB access checks are
retained. Every child process goes through ExactCommandRunner and the one
sequence-owned BoundedDiagnostics. Imported code must be authenticated by loader.
"""
import copy
import grp
import hashlib
import json
import os
import pwd
import re
import socket
import stat

import epoch7_delta as delta
import p2_sandbox_profile as profile
from epoch7_command_runner import ExactCommandRunner
from epoch7_recovery_sequence import (BoundedDiagnostics, STOP_UNITS,
                                      check_observation, observation, error_class)
from ledger_cutover_transaction import _atomic_receipt
from p2_bootstrap_files import private_read
from p2_fixed_host_runtime import (ALLOWED_SERVICES, GATEWAY_SERVICE,
                                   HOST, P2_PLUGIN_ID, P2_PLUGIN_CONFIG_PATH)
from p2_prerequisites import Prerequisites, validate as validate_prerequisites
from p2_tls_lifecycle import TIMER as TLS_TIMER

MANIFEST = '0ac28c96636ee63364015b375202779e2ef1dd0bd9f1b81e77d4387b6754316c'
TRANSACTION = ('/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/'
               'legacy-isolation-' + delta.TX)
RELEASE = '/opt/xuanjun-control-releases/integration-' + MANIFEST[:16]
BOOT_UNITS = tuple(ALLOWED_SERVICES) + (GATEWAY_SERVICE, 'nginx.service', TLS_TIMER)
START_UNITS = (GATEWAY_SERVICE,) + tuple(ALLOWED_SERVICES) + ('nginx.service', TLS_TIMER)
JOURNALS = ('epoch7-sandbox-profile.json', 'epoch7-sandbox-profile-original.json',
            'epoch7-sandbox-profile-candidate.json', 'epoch7-plugin-effects.json',
            'ledger-access.json', 'runtime-boot.json')
DB_CODE = ('import sqlite3,sys,pathlib;'
           'd=sqlite3.connect(pathlib.Path(sys.argv[1]).as_uri()+"?mode=ro",uri=True);'
           'assert d.execute("PRAGMA quick_check").fetchone()[0]=="ok";d.close()')
ENV = {'PATH':'/usr/bin:/bin', 'LANG':'C'}
PLUGIN_ENV = {'HOME':'/home/xuanjun_dev', 'PATH':'/usr/bin:/bin', 'LANG':'C.UTF-8'}


def need(value, label):
    if not value:
        raise ValueError('EPOCH7_RUNTIME_' + label)


def packed(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       allow_nan=False) + '\n').encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def constant(unused):
        raise ValueError('EPOCH7_RUNTIME_NONFINITE_JSON')
    try:
        need(type(raw) is bytes and len(raw) <= 1048576, 'JSON_BOUND')
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                          parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError('EPOCH7_RUNTIME_INVALID_PRIVATE_JSON') from None


def fsync_parent(path):
    fd = os.open(os.path.dirname(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def exclusive_private(path, raw):
    """Caller proves protected transaction directory and holds install lock."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    fsync_parent(path)
    need(private_read(path) == raw, 'EXCLUSIVE_PUBLICATION_UNCONFIRMED')


def metadata(info):
    return {'device':info.st_dev, 'inode':info.st_ino, 'uid':info.st_uid,
            'gid':info.st_gid, 'mode':stat.S_IMODE(info.st_mode),
            'size':info.st_size, 'mtime_ns':info.st_mtime_ns,
            'ctime_ns':info.st_ctime_ns, 'nlink':info.st_nlink}


class FreshSandboxProfile(profile.SandboxProfile):
    """Same narrow sandbox policy, fresh context-bound epoch7 recovery transaction only."""
    def __init__(self, directory, context_sha256, guard):
        super(FreshSandboxProfile, self).__init__(directory)
        self.journal = directory + '/' + JOURNALS[0]
        self.backup = directory + '/' + JOURNALS[1]
        self.candidate = directory + '/' + JOURNALS[2]
        self.binding = context_sha256
        self.guard = guard

    def authority(self):
        need(self.guard() is True, 'SANDBOX_LIVE_GUARD')
        super(FreshSandboxProfile, self).authority()

    def apply(self, ref):
        self.authority()
        need(not any(os.path.lexists(p) for p in
                     (self.journal, self.backup, self.candidate)), 'FRESH_SANDBOX_ALREADY_ATTEMPTED')
        old, new = self.prepare(ref)
        for path, raw in ((self.backup, old), (self.candidate, new)):
            exclusive_private(path, raw)
        row = {'schema':1, 'context_sha256':self.binding,
               'original_sha256':sha(old), 'candidate_sha256':sha(new),
               'current_sha256':sha(new), 'state':'APPLY_INTENT'}
        exclusive_private(self.journal, packed(row))
        need(profile.read_profile() == old, 'PROFILE_CHANGED_BEFORE_APPLY')
        profile.publish(new)
        need(profile.read_profile() == new, 'PROFILE_APPLY_UNCONFIRMED')
        row['state'] = 'APPLIED'
        _atomic_receipt(self.journal, row)
        self.row()

    def row(self):
        row, old, candidate = super(FreshSandboxProfile, self).row()
        need(type(row.get('schema')) is int and row['schema'] == 1 and
             re.fullmatch(r'[0-9a-f]{64}',row.get('current_sha256','')) and
             set(row) == {'schema','context_sha256','original_sha256','candidate_sha256',
                         'current_sha256','state'} and
             row['context_sha256'] == self.binding and
             row['state'] in ('APPLY_INTENT','APPLIED','CLI_CAPTURED','RESTORED'),
             'SANDBOX_CONTEXT_OR_STATE')
        return row, old, candidate


def command_contract(compiled, renewal_timer_authorized):
    """Pure exact argv compiler. No arbitrary command input or host effects."""
    need(type(renewal_timer_authorized) is bool, 'TIMER_AUTHORIZATION_BOOLEAN')
    runtime = compiled['runtime']
    plugin = runtime['plugin']
    need(compiled['manifest_sha256'] == MANIFEST and
         runtime['release_directory'] == 'integration-' + MANIFEST[:16], 'EXACT_RELEASE')
    need(tuple(runtime['services']) == tuple(ALLOWED_SERVICES), 'EXACT_SERVICE_ORDER')
    need(plugin['id'] == P2_PLUGIN_ID and plugin['gateway_service'] == GATEWAY_SERVICE and
         plugin['openclaw_bin'] == '/home/xuanjun_dev/.openclaw/bin/openclaw' and
         plugin['service_user'] == 'xuanjun_dev' and
         plugin['source'] == 'plugins/p2-native-controller', 'EXACT_PLUGIN')
    need(plugin['binding_file'] == '/etc/xuanjun-development/p2-native-controller.binding.json'
         and re.fullmatch(r'[0-9a-f]{64}', plugin['binding_sha256']), 'PLUGIN_BINDING')
    forward, cleanup = {}, {}
    def add(table, key, phase, operation, argv, codes=(0,), timeout=45, env=ENV):
        table[key] = {'phase':phase, 'operation':operation, 'argv':list(argv),
                      'env':dict(env), 'timeout':timeout, 'accepted_returncodes':list(codes), 'cwd':'/'}
    def claw(table, key, phase, operation, args, codes=(0,)):
        add(table, key, phase, operation,
            ['/usr/sbin/runuser','--user','xuanjun_dev','--',plugin['openclaw_bin']] + args,
            codes=codes, timeout=60, env=PLUGIN_ENV)
    add(forward, 'gateway_stop', 'apply_fresh_sandbox', 'service_stop',
        ['/usr/bin/systemctl','stop',GATEWAY_SERVICE])
    add(forward, 'gateway_stopped', 'apply_fresh_sandbox', 'service_is_active',
        ['/usr/bin/systemctl','is-active','--quiet',GATEWAY_SERVICE], codes=(3,), timeout=15)
    phase = 'install_verified_plugin'
    claw(forward, 'inventory', phase, 'plugin_inventory', ['plugins','list','--json'])
    claw(forward, 'install', phase, 'plugin_install',
         ['plugins','install',RELEASE+'/'+plugin['source'],'--force','--no-enable','--accept-capabilities'])
    config = json.dumps({'bindingFile':plugin['binding_file'], 'bindingSha256':plugin['binding_sha256']},
                        sort_keys=True, separators=(',', ':'))
    claw(forward, 'config_set', phase, 'plugin_config_set',
         ['config','set',P2_PLUGIN_CONFIG_PATH,config,'--strict-json'])
    claw(forward, 'plugin_enable', phase, 'plugin_enable',
         ['plugins','enable',P2_PLUGIN_ID,'--accept-capabilities'])
    claw(forward, 'config_validate', phase, 'plugin_config_validate', ['config','validate','--json'])
    claw(forward, 'inventory_installed', phase, 'plugin_inventory', ['plugins','list','--json'])
    add(forward, 'database_reopen', 'reopen_existing_database', 'database_reopen',
        ['/usr/sbin/runuser','--user','xuanjun-dispatcher','--','/usr/bin/python3',
         '-I','-B','-c',DB_CODE,delta.DB])
    add(forward, 'daemon_reload', 'activate_new_services', 'daemon_reload',
        ['/usr/bin/systemctl','daemon-reload'])
    add(forward, 'nginx_test', 'activate_new_services', 'nginx_config_test',
        ['/usr/sbin/nginx','-t','-c','/etc/xuanjun-development/nginx-main.conf'])
    for phase, suffix in (('activate_new_services','activate'), ('post_install_checks','post')):
        claw(forward, 'inspect_'+suffix, phase, 'plugin_runtime_inspect',
             ['plugins','inspect',P2_PLUGIN_ID,'--runtime','--json'])
    for index, unit in enumerate(BOOT_UNITS):
        for prefix, verb, operation, codes in (
                ('boot_before','is-enabled','boot_is_enabled',(0,1)),
                ('boot_enable','enable','boot_enable',(0,)),
                ('boot_after','is-enabled','boot_is_enabled',(0,))):
            add(forward, prefix+'_%02d'%index, 'activate_new_services', operation,
                ['/usr/bin/systemctl',verb,unit], codes=codes, timeout=15 if verb=='is-enabled' else 45)
        add(cleanup, 'disable_%02d'%index, 'activate_new_services', 'boot_disable',
            ['/usr/bin/systemctl','disable',unit])
        add(cleanup, 'disabled_%02d'%index, 'activate_new_services', 'boot_is_enabled',
            ['/usr/bin/systemctl','is-enabled',unit], codes=(0,1), timeout=15)
    for index, unit in enumerate(START_UNITS):
        add(forward, 'start_%02d'%index, 'activate_new_services', 'service_start',
            ['/usr/bin/systemctl','start',unit])
        add(forward, 'active_%02d'%index, 'activate_new_services', 'service_is_active',
            ['/usr/bin/systemctl','is-active','--quiet',unit], timeout=15)
        add(forward, 'post_active_%02d'%index, 'post_install_checks', 'service_is_active',
            ['/usr/bin/systemctl','is-active','--quiet',unit], timeout=15)
    for index, unit in enumerate(STOP_UNITS):
        add(cleanup, 'stop_%02d'%index, 'activate_new_services', 'service_stop',
            ['/usr/bin/systemctl','stop',unit])
        add(cleanup, 'stopped_%02d'%index, 'activate_new_services', 'service_is_active',
            ['/usr/bin/systemctl','is-active','--quiet',unit], codes=(3,), timeout=15)
        add(cleanup, 'show_%02d'%index, 'activate_new_services', 'service_show',
            ['/usr/bin/systemctl','show',unit,
             '--property=LoadState,ActiveState,SubState,MainPID,ControlPID,ControlGroup'],
            codes=(0,1), timeout=15)
    phase = 'install_verified_plugin'
    for key, operation, args, codes in (
            ('cleanup_inventory','plugin_inventory',['plugins','list','--json'],(0,)),
            ('uninstall','plugin_uninstall',['plugins','uninstall',P2_PLUGIN_ID,'--force'],(0,)),
            ('unset_config','plugin_config_unset',['config','unset',P2_PLUGIN_CONFIG_PATH],(0,1)),
            ('unset_entry','plugin_config_unset',['config','unset','plugins.entries.'+P2_PLUGIN_ID],(0,1)),
            ('cleanup_validate','plugin_config_validate',['config','validate','--json'],(0,))):
        claw(cleanup, key, phase, operation, args, codes)
    need(len(forward) <= 100 and len(cleanup) <= 100, 'FINITE_COMMAND_COUNT')
    return forward, cleanup


class Epoch7RuntimeEffects(object):
    """Guarded effects, with required evidence callbacks for other adapters.

    phase_guard(context, phase), cleanup_guard(context, operation, unit) return
    literal True after verifying held lock/admitted attempt/evolving exact pins.
    descriptor_reader() returns the live descriptor; access/postcheck callbacks
    return a strict sequence observation and MUST do real bounded checks.
    database_before is exact fresh stat metadata, not a replayable default.
    boot_before is the reviewed enabled/disabled state map for all BOOT_UNITS.
    Cleanup undoes only this attempt's disabled-to-enabled changes; it never
    changes untouched baseline-enabled units.
    """
    def __init__(self, directory, compiled, context, descriptor_reader, phase_guard,
                 cleanup_guard, diagnostics, database_before, runtime_access_check,
                 postcheck, boot_before, activate_retained_renewal_timer=False,
                 runner_factory=ExactCommandRunner, sandbox_factory=FreshSandboxProfile,
                 containment_scanner=None):
        need(directory == TRANSACTION, 'EXACT_TRANSACTION')
        need(isinstance(diagnostics, BoundedDiagnostics), 'SHARED_DIAGNOSTICS')
        need(all(callable(x) for x in (descriptor_reader,phase_guard,cleanup_guard,
                                     runtime_access_check,postcheck,runner_factory,sandbox_factory)),
             'EXPLICIT_CALLBACKS_REQUIRED')
        need(context.get('runtime_manifest_sha256') == MANIFEST and
             context.get('transaction_id') == delta.TX and context.get('expected_epoch') == 7 and
             context.get('proposed_prepared_epoch') == 8 and
             re.fullmatch(r'[0-9a-f]{64}',context.get('context_sha256','')), 'EXACT_CONTEXT')
        need(set(database_before) == {'device','inode','uid','gid','mode','size','mtime_ns','ctime_ns','nlink'}
             and all(type(v) is int and v >= 0 for v in database_before.values()) and
             database_before['uid'] == 0 and database_before['mode'] == 0o600 and
             database_before['nlink'] == 1, 'EXACT_DATABASE_BEFORE')
        need(type(boot_before) is dict and set(boot_before) == set(BOOT_UNITS) and
             all(v in ('enabled','disabled') for v in boot_before.values()), 'REVIEWED_BOOT_INHIBITION_REQUIRED')
        self.directory, self.compiled, self.context = directory,copy.deepcopy(compiled),copy.deepcopy(context)
        self.runtime = self.compiled['runtime']
        self.read_descriptor, self.phase_guard, self.cleanup_guard = descriptor_reader,phase_guard,cleanup_guard
        self.diagnostics, self.database_before = diagnostics,copy.deepcopy(database_before)
        self.access_check, self.postcheck = runtime_access_check,postcheck
        self.containment_scanner = containment_scanner
        self.boot_before = copy.deepcopy(boot_before)
        self.timer_authorized = activate_retained_renewal_timer
        self.contract, self.cleanup_contract = command_contract(self.compiled, self.timer_authorized)
        self.runner_factory = runner_factory
        self.phase, self.cleanup_scope, self.attempted = None,None,set()
        self.cleanup_attempted = set()
        self.runner = runner_factory(self.contract,self._live_forward,diagnostics)
        self.sandbox = sandbox_factory(directory, context['context_sha256'], self._live_current)

    def _authority(self):
        need(os.geteuid() == 0 and socket.gethostname().split('.')[0] == HOST, 'FIXED_HOST_ROOT')
        info = os.lstat(self.directory)
        need(os.path.realpath(self.directory) == self.directory and stat.S_ISDIR(info.st_mode) and
             (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode)) == (0,0,0o700), 'PRIVATE_TRANSACTION')

    def _live_forward(self):
        self._authority()
        return self.phase_guard(copy.deepcopy(self.context),self.phase) is True

    def _live_current(self):
        if self.cleanup_scope is None:
            return self._live_forward()
        self._authority()
        op, unit = self.cleanup_scope
        return self.cleanup_guard(copy.deepcopy(self.context),op,unit) is True

    def _enter(self, context, diagnostics, phase):
        need(context == self.context and diagnostics is self.diagnostics, 'CALL_BINDING')
        need(phase not in self.attempted, 'PHASE_NO_RETRY')
        self.attempted.add(phase)
        self.phase, self.cleanup_scope = phase,None
        need(self._live_forward(), 'LIVE_PHASE_GUARD')

    def _result(self, operation, facts):
        return observation(self.context,operation,sha(packed(facts)))

    def _path(self, name):
        need(name in JOURNALS, 'JOURNAL_SCOPE')
        return self.directory + '/' + name

    def _create(self, name, row):
        need(self._live_current(), 'LIVE_JOURNAL_GUARD')
        row = dict(row, schema=1, context_sha256=self.context['context_sha256'])
        exclusive_private(self._path(name),packed(row))
        return row

    def _read(self, name):
        need(self._live_current(), 'LIVE_JOURNAL_GUARD')
        row = strict_json(private_read(self._path(name)))
        need(type(row) is dict and type(row.get('schema')) is int and row['schema'] == 1 and
             row.get('context_sha256') == self.context['context_sha256'], 'JOURNAL_BINDING')
        return row

    def _save(self, name, before, after):
        need(self._read(name) == before, 'JOURNAL_CHANGED')
        _atomic_receipt(self._path(name),after)
        need(self._read(name) == after, 'JOURNAL_PUBLICATION_UNCONFIRMED')

    def _descriptor(self, state):
        value = self.read_descriptor()
        expected = dict(self.compiled['activation_proposal'],state=state)
        need(value == expected and value['epoch'] == 8 and value['db_path'] == delta.DB,
             'LIVE_DESCRIPTOR_MISMATCH')
        return value

    def _command(self, key, runner=None, capture_profile=False):
        if runner is None:
            need(key in self.contract and self.contract[key]['phase'] == self.phase, 'COMMAND_PHASE_BINDING')
        try:
            return (runner or self.runner).run(key)
        finally:
            # CLI failure can still mutate the profile. The shared diagnostics
            # latches its first failure before this capture can itself fail.
            if capture_profile:
                self.sandbox.capture()

    def _inventory(self, key, runner=None):
        value = strict_json(self._command(key,runner,capture_profile=True).stdout)
        # Preserve the original inventory representation while rejecting invalid
        # JSON and pathological nesting rather than accepting text substrings.
        def contains(item, depth=0):
            need(depth <= 32, 'PLUGIN_INVENTORY_DEPTH')
            if type(item) is dict:
                if item.get('id') == P2_PLUGIN_ID or item.get('pluginId') == P2_PLUGIN_ID:
                    return True
                return any(contains(v,depth+1) for v in item.values())
            if type(item) is list:
                return any(contains(v,depth+1) for v in item)
            return False
        need(type(value) in (dict,list), 'PLUGIN_INVENTORY_SHAPE')
        return contains(value)

    def _inspect(self, key):
        value = strict_json(self._command(key,capture_profile=True).stdout)
        # Original registration contract, same IDs and exact operation names.
        def tokens(item, depth=0):
            need(depth <= 32, 'PLUGIN_INSPECTION_DEPTH')
            if type(item) is dict:
                for k,v in item.items():
                    yield k
                    for token in tokens(v,depth+1): yield token
            elif type(item) is list:
                for child in item:
                    for token in tokens(child,depth+1): yield token
            elif type(item) is str:
                yield item
        found = set(tokens(value))
        need({P2_PLUGIN_ID,'xuanjun.execution.start','xuanjun.execution.inspect'}.issubset(found),
             'PLUGIN_RUNTIME_REGISTRATION_UNPROVEN')

    def apply_fresh_sandbox(self, context, diagnostics):
        self._enter(context,diagnostics,'apply_fresh_sandbox')
        self._descriptor('QUIESCED')
        self._command('gateway_stop')
        self._command('gateway_stopped')
        self.sandbox.apply(self.runtime['sandbox_policy'])
        return self._result(self.phase,{'fresh_sandbox_applied':True})

    def install_verified_plugin(self, context, diagnostics):
        self._enter(context,diagnostics,'install_verified_plugin')
        self._descriptor('QUIESCED')
        self.sandbox.rollback_check()
        source = RELEASE + '/' + self.runtime['plugin']['source']
        need(os.path.realpath(source) == source and os.path.isdir(source), 'PLUGIN_SOURCE')
        name = JOURNALS[3]
        row = self._create(name,{'state':'INVENTORY_INTENT','previous':'UNKNOWN'})
        need(not self._inventory('inventory'), 'PLUGIN_ALREADY_PRESENT')
        updated = dict(row,state='INSTALL_INTENT',previous='ABSENT')
        self._save(name,row,updated); row = updated
        for key in ('install','config_set','plugin_enable','config_validate'):
            self._command(key,capture_profile=True)
        need(self._inventory('inventory_installed'), 'PLUGIN_INSTALL_UNPROVEN')
        self._save(name,row,dict(row,state='INSTALLED'))
        return self._result(self.phase,{'plugin_absent_refreshed':True,'plugin_installed':True,
                                      'plugin_configured':True,'plugin_enabled':True})

    def _database_identity(self):
        plan = self.runtime['prerequisites']
        validate_prerequisites(plan)
        uid = plan['users']['xuanjun-dispatcher']['uid']
        gid = plan['groups']['xuanjun-control-db']
        need((pwd.getpwnam('xuanjun-dispatcher').pw_uid,grp.getgrnam('xuanjun-control-db').gr_gid)
             == (uid,gid) == (1003,1006), 'DATABASE_CONSUMER_IDENTITY')
        rows = [x for x in plan['directories'] if x['path'] == delta.GENERATION]
        need(len(rows) == 1 and (rows[0]['uid'],rows[0]['gid'],rows[0]['mode']) ==
             (uid,gid,0o700), 'GENERATION_POLICY')
        need(os.path.realpath(delta.GENERATION) == delta.GENERATION, 'GENERATION_ALIAS')
        Prerequisites.directory_matches(rows[0])
        return uid,gid

    def reopen_existing_database(self, context, diagnostics):
        self._enter(context,diagnostics,'reopen_existing_database')
        self._descriptor('QUIESCED')
        uid,gid = self._database_identity()
        need(os.path.realpath(delta.DB) == delta.DB and
             not any(os.path.lexists(delta.DB+s) for s in ('-wal','-shm')), 'DATABASE_PATH_OR_SIDECAR')
        name = JOURNALS[4]
        need(not os.path.lexists(self._path(name)), 'DATABASE_ALREADY_ATTEMPTED')
        fd = os.open(delta.DB,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            need(stat.S_ISREG(info.st_mode) and metadata(info) == self.database_before,
                 'DATABASE_FRESH_IDENTITY')
            row = self._create(name,{'state':'ACCESS_INTENT','path':delta.DB,
                                    'before':self.database_before,'uid':uid,'gid':gid,'mode':0o600})
            need(metadata(os.lstat(delta.DB)) == self.database_before, 'DATABASE_PATH_CHANGED')
            need(self._live_forward(), 'LIVE_DATABASE_CHOWN_GUARD')
            os.fchown(fd,uid,gid); os.fsync(fd)
            after = os.fstat(fd); current = os.lstat(delta.DB)
            need((after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_nlink) ==
                 (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,1) and
                 (after.st_uid,after.st_gid,stat.S_IMODE(after.st_mode)) == (uid,gid,0o600) and
                 metadata(after) == metadata(current), 'DATABASE_ACCESS_CHANGED')
            updated = dict(row,state='ACCESS_DONE',after=metadata(after))
            self._save(name,row,updated); row = updated
        finally:
            os.close(fd)
        self._command('database_reopen')
        need(not any(os.path.lexists(delta.DB+s) for s in ('-wal','-shm')), 'DATABASE_REOPEN_SIDECAR')
        need(metadata(os.lstat(delta.DB)) == row['after'], 'DATABASE_REOPEN_IDENTITY_DRIFT')
        self._save(name,row,dict(row,state='REOPENED'))
        return self._result(self.phase,{'database_reopened':True,'access_transferred':True})

    def verify_runtime_access(self, context, diagnostics):
        self._enter(context,diagnostics,'verify_runtime_access')
        self._descriptor('QUIESCED')
        need(self._read(JOURNALS[4]).get('state') == 'REOPENED', 'DATABASE_REOPEN_REQUIRED')
        return check_observation(self.access_check(copy.deepcopy(context),diagnostics),
                                 context,self.phase)

    @staticmethod
    def _enabled(result):
        try: value = result.stdout.decode('ascii').strip()
        except UnicodeError: raise ValueError('EPOCH7_RUNTIME_UNIT_STATE_ENCODING') from None
        need((value,result.returncode) in (('enabled',0),('disabled',1)), 'UNIT_ENABLE_STATE')
        return value

    def _enable_boot(self):
        name = JOURNALS[5]
        need(not os.path.lexists(self._path(name)), 'BOOT_ALREADY_ATTEMPTED')
        before = {unit:self._enabled(self._command('boot_before_%02d'%i))
                  for i,unit in enumerate(BOOT_UNITS)}
        need(before == self.boot_before, 'BOOT_BASELINE_CHANGED')
        row = self._create(name,{'state':'ENABLE_INTENT','previous':before,'units':list(BOOT_UNITS)})
        for index,unit in enumerate(BOOT_UNITS):
            self._command('boot_enable_%02d'%index)
            need(self._enabled(self._command('boot_after_%02d'%index)) == 'enabled', 'BOOT_ENABLE_UNPROVEN')
        self._save(name,row,dict(row,state='ENABLED'))

    def activate_new_services(self, context, diagnostics):
        self._enter(context,diagnostics,'activate_new_services')
        need(self.timer_authorized is True, 'RENEWAL_TIMER_REVIEW_REQUIRED')
        self._descriptor('ACTIVE')
        from owner_feishu_https import installed_binding
        need(installed_binding()['package_sha256'] == MANIFEST, 'OWNER_BINDING_RELEASE')
        self._command('daemon_reload'); self._command('nginx_test')
        self._enable_boot()
        for index,unit in enumerate(START_UNITS):
            self._command('start_%02d'%index); self._command('active_%02d'%index)
            if unit == GATEWAY_SERVICE:
                self._inspect('inspect_activate')
        return self._result(self.phase,{'services_active':True,'retained_renewal_timer_scheduled':True,
                                      'direct_tls_issue_renew_dry_run_commands':0})

    def post_install_checks(self, context, diagnostics):
        self._enter(context,diagnostics,'post_install_checks')
        self._descriptor('ACTIVE')
        for index,unit in enumerate(START_UNITS):
            self._command('post_active_%02d'%index)
        self._inspect('inspect_post')
        # Never reuse the frozen postchecker: it emits a stale claim that this
        # recovery performed ACME issuance/dry-run and has unbounded subprocesses.
        return check_observation(self.postcheck(copy.deepcopy(context),diagnostics),context,self.phase)

    def _cleanup_enter(self, context, diagnostics, operation, unit=None):
        need(context == self.context and diagnostics is self.diagnostics, 'CLEANUP_BINDING')
        need((operation,unit) not in self.cleanup_attempted, 'CLEANUP_NO_RETRY')
        self.cleanup_attempted.add((operation,unit))
        self.cleanup_scope = (operation,unit)
        need(self._live_current(), 'LIVE_CLEANUP_GUARD')
        # Independent runner per outer cleanup item; a prior forward failure or
        # another unit's failure must not suppress this operation.
        return self.runner_factory(self.cleanup_contract,self._live_current,diagnostics)

    def stop_unit(self, context, unit, diagnostics):
        need(unit in STOP_UNITS, 'STOP_UNIT_SCOPE')
        runner = self._cleanup_enter(context,diagnostics,'stop_unit',unit)
        self._command('stop_%02d'%STOP_UNITS.index(unit),runner)
        return self._result('stop_unit:' + unit,{'unit':unit,'stop_requested':True})

    def observe_stopped(self, context, operation, unit, diagnostics):
        need(operation in ('observe_stopped_before','observe_stopped_after') and unit in STOP_UNITS,
             'STOP_OBSERVATION_SCOPE')
        runner = self._cleanup_enter(context,diagnostics,operation,unit)
        need(self.containment_scanner is not None and
             callable(getattr(self.containment_scanner,'verify_systemd_controller_mount',None)) and
             callable(getattr(self.containment_scanner,'bounded_file_inventory',None)),
             'REVIEWED_CONTAINMENT_SCANNER_REQUIRED')
        from epoch3_service_containment import ServiceContainment, UNITS
        need(unit in UNITS, 'FROZEN_CONTAINMENT_UNIT_SCOPE')
        key = 'show_%02d'%STOP_UNITS.index(unit)
        def bounded_show(argv, **unused):
            need(argv == self.cleanup_contract[key]['argv'], 'EXACT_CONTAINMENT_SHOW')
            return self._command(key,runner)
        # Reuse the frozen before/after unit state + exact cgroup FD inventory
        # primitive, replacing only its process boundary with our finite runner.
        evidence = ServiceContainment(self.containment_scanner,run=bounded_show).observe_one(unit)
        return self._result(operation + ':' + unit,evidence)

    def preserve_boot_inhibition(self, context, diagnostics):
        self._cleanup_enter(context,diagnostics,'preserve_boot_inhibition')
        name = JOURNALS[5]
        if not os.path.lexists(self._path(name)):
            # No owned enable intent: no need or authority to change boot state.
            return self._result('preserve_boot_inhibition',{'owned_boot_effects':False})
        row = self._read(name)
        need(row.get('units') == list(BOOT_UNITS) and row.get('previous') == self.boot_before and
             row.get('state') in ('ENABLE_INTENT','ENABLED','INHIBITED'), 'BOOT_CLEANUP_JOURNAL')
        failures = []
        outer_scope, outer_failure = diagnostics.scope,diagnostics.scope_failure
        first_command_failure = None
        try:
            for index,unit in enumerate(BOOT_UNITS):
                # Each unit is an independent cleanup scope, while the same
                # diagnostics owns the monotonic global command counter.
                diagnostics.start_scope(str(outer_scope) + ':boot:' + unit)
                runner = self.runner_factory(self.cleanup_contract,self._live_current,diagnostics)
                try:
                    if row['previous'][unit] == 'disabled':
                        self._command('disable_%02d'%index,runner)
                    need(self._enabled(self._command('disabled_%02d'%index,runner)) == row['previous'][unit],
                         'BOOT_INHIBITION_UNPROVEN')
                except BaseException as error:
                    if diagnostics.capture_allocation is not None:
                        phase,operation,unused_sequence = diagnostics.capture_allocation
                        diagnostics.record_adapter_failure(phase,operation,error_class(error),'CAPTURE_UNCONFIRMED')
                    failures.append(error)
                finally:
                    if first_command_failure is None and diagnostics.scope_failure is not None:
                        first_command_failure = diagnostics.scope_failure
        finally:
            diagnostics.scope = outer_scope
            diagnostics.scope_failure = outer_failure or first_command_failure
        if failures:
            for error in failures:
                if isinstance(error,(SystemExit,KeyboardInterrupt)): raise error
            raise first_command_failure or failures[0]
        self._save(name,row,dict(row,state='INHIBITED'))
        return self._result('preserve_boot_inhibition',{'boot_inhibited':True})

    def restore_owned_epoch7_sandbox(self, context, diagnostics):
        runner = self._cleanup_enter(context,diagnostics,'restore_owned_epoch7_sandbox')
        if not os.path.lexists(self.sandbox.journal):
            need(not any(os.path.lexists(p) for p in (self.sandbox.backup,self.sandbox.candidate)),
                 'PARTIAL_SANDBOX_BACKUP_HOLD')
            return self._result('restore_owned_epoch7_sandbox',{'owned_sandbox_effects':False})
        self.sandbox.rollback_check()
        if os.path.lexists(self._path(JOURNALS[3])):
            row = self._read(JOURNALS[3])
            need(row.get('previous') == 'ABSENT' and row.get('state') in
                 ('INSTALL_INTENT','INSTALLED','RESTORED'), 'PLUGIN_OWNERSHIP_UNPROVEN')
            if row['state'] != 'RESTORED':
                if self._inventory('cleanup_inventory',runner):
                    self._command('uninstall',runner,capture_profile=True)
                for key in ('unset_config','unset_entry','cleanup_validate'):
                    self._command(key,runner,capture_profile=True)
                need(not self._inventory('cleanup_inventory',runner), 'PLUGIN_UNINSTALL_UNPROVEN')
                self.sandbox.rollback()
                self._save(JOURNALS[3],row,dict(row,state='RESTORED'))
            else:
                self.sandbox.rollback()
        else:
            self.sandbox.rollback()
        return self._result('restore_owned_epoch7_sandbox',{'fresh_sandbox_restored':True})
