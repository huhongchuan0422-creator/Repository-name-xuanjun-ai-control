"""Fixed original static phases on the existing Coordinator's single lease.

Importing this adapter does not import the root-capable release helpers. The
protected caller supplies an original Transaction object, never an ops name or
command from JSON. Read-only reconciliation does not call publisher.check,
publisher.reconcile, nginx -t, reload, or the synthetic-order smoke helper.

Checkpoint receipt hashes bind an immutable, canonical phase projection of the
original child receipt. Hashing the whole mutable receipt would invalidate every
earlier checkpoint after the next original step. This projection is not a new
receipt, ledger, permission, or attempt counter.

Admission requires at least 600 seconds of authorization before every original
phase. Private execution namespaces also check the same lease immediately before
each filesystem effect and completion write. An already admitted blocking OS
call cannot be forcibly undone; no subsequent effect is admitted after expiry
or fence loss. HTTP acceptance is fixed GET-only; business E2E remains pending.
"""
import copy
import builtins
from contextlib import contextmanager
import fcntl
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import time
import types

from scripts.pr122_customer_core import Denied, canonical, digest
from scripts.pr122_customer_workflow import need

STATIC_STAGES = (
    'BACKUP_VERIFIED', 'SEALED_BUNDLE', 'STATIC_PREPARED', 'NGINX_STAGED',
    'NGINX_VALIDATED', 'ACTIVATION_DRIFT_CHECK', 'STATIC_ACTIVATED',
    'NGINX_RELOADED', 'HTTPS_SMOKE', 'STATIC_CHECK',
)
STATIC_RECOVERY = {stage: frozenset({'RECONCILE_STATIC'}) for stage in STATIC_STAGES}
PHASE_ADMISSION_SECONDS = 600
STATIC_SUCCESS = 'STATIC_READONLY_HTTP_COMPLETE_AWAIT_BROWSER'


def _guarded_namespace(module, guard):
    """Private, source-fixed execution namespace; never patch shared modules.

    Original function code objects are retained. Only filesystem effects are
    redirected through local lease checks, including exception receipt paths.
    No module, method, backend or command is selected by request JSON.
    """
    mutations = frozenset({'write', 'writev', 'pwrite', 'pwritev', 'fsync', 'fdatasync',
        'mkdir', 'makedirs', 'rmdir', 'removedirs', 'unlink', 'remove', 'rename', 'renames',
        'replace', 'symlink', 'link', 'chmod', 'fchmod', 'chown', 'fchown', 'lchown',
        'truncate', 'ftruncate', 'utime'})

    class GuardedOS:
        def __getattr__(self, name):
            value = getattr(os, name)
            if name == 'open':
                def opened(path, flags, *args, **kwargs):
                    if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND): guard()
                    return value(path, flags, *args, **kwargs)
                return opened
            if name == 'fdopen':
                def fdopened(fd, mode='r', *args, **kwargs):
                    need(not any(flag in mode for flag in 'wa+x'), 'STATIC_BUFFERED_WRITE_FORBIDDEN')
                    return value(fd, mode, *args, **kwargs)
                return fdopened
            if name in mutations:
                def changed(*args, **kwargs):
                    guard(); return value(*args, **kwargs)
                return changed
            return value

    guarded_os = GuardedOS()

    class GuardedPath(type(Path())):
        __slots__ = ()
        def mkdir(self, *args, **kwargs): guard(); return super().mkdir(*args, **kwargs)
        def chmod(self, *args, **kwargs): guard(); return super().chmod(*args, **kwargs)
        def unlink(self, *args, **kwargs): guard(); return super().unlink(*args, **kwargs)
        def rmdir(self, *args, **kwargs): guard(); return super().rmdir(*args, **kwargs)
        def rename(self, *args, **kwargs): guard(); return super().rename(*args, **kwargs)
        def replace(self, *args, **kwargs): guard(); return super().replace(*args, **kwargs)
        def symlink_to(self, *args, **kwargs): guard(); return super().symlink_to(*args, **kwargs)
        def hardlink_to(self, *args, **kwargs): guard(); return super().hardlink_to(*args, **kwargs)
        def touch(self, *args, **kwargs): raise Denied('HOLD:STATIC_UNEXPECTED_TOUCH')
        def open(self, mode='r', *args, **kwargs):
            # Buffered close/finalization can flush after expiry. Frozen writer
            # needs only write_text, implemented below as guarded raw writes.
            need(not any(flag in mode for flag in 'wa+x'), 'STATIC_BUFFERED_WRITE_FORBIDDEN')
            return super().open(mode, *args, **kwargs)
        def write_bytes(self, data):
            raw = memoryview(data); written = 0
            fd = guarded_os.open(self, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o666)
            try:
                while raw:
                    count = guarded_os.write(fd, raw)
                    need(count > 0, 'STATIC_ZERO_LENGTH_WRITE')
                    written += count; raw = raw[count:]
            finally: os.close(fd)
            return written
        def write_text(self, data, encoding=None, errors=None, newline=None):
            need(type(data) is str and encoding in (None, 'utf-8', 'utf8')
                 and errors in (None, 'strict') and newline is None, 'STATIC_FIXED_TEXT_WRITE')
            self.write_bytes(data.encode('utf-8')); return len(data)

    original = vars(module)
    namespace = dict(original)
    namespace.update(os=guarded_os, Path=GuardedPath)
    protected_builtins = dict(vars(builtins))
    def opened(file, mode='r', *args, **kwargs):
        need(not any(flag in mode for flag in 'wa+x'), 'STATIC_BUFFERED_WRITE_FORBIDDEN')
        return builtins.open(file, mode, *args, **kwargs)
    protected_builtins['open'] = opened
    namespace['__builtins__'] = protected_builtins

    def clone(function):
        wrapped = getattr(function, '__wrapped__', None)
        if isinstance(wrapped, types.FunctionType) and wrapped.__globals__ is original:
            return contextmanager(clone(wrapped))
        result = types.FunctionType(function.__code__, namespace, function.__name__,
                                    function.__defaults__, function.__closure__)
        result.__kwdefaults__ = function.__kwdefaults__
        return result

    for name, value in original.items():
        if isinstance(value, types.FunctionType) and (value.__globals__ is original or
                getattr(getattr(value, '__wrapped__', None), '__globals__', None) is original):
            namespace[name] = clone(value)
    # These are the frozen publisher's only non-exception implementation classes.
    for name in ('Deadline', 'InlineCollector'):
        cls = original.get(name)
        if isinstance(cls, type):
            methods = {key: clone(value) for key, value in vars(cls).items()
                       if isinstance(value, types.FunctionType)}
            namespace[name] = type(name, (cls,), methods)
    if 'mkdir' in namespace:
        original_mkdir = namespace['mkdir']
        def mkdir(path, mode): guard(); return original_mkdir(GuardedPath(path), mode)
        namespace['mkdir'] = mkdir
    return namespace


class OriginalStaticOperations:
    """Concrete adapter. There is deliberately no injectable production backend."""
    def __init__(self, transaction, plan, inputs):
        # Lazy import: ordinary review/test discovery never loads root helpers.
        from scripts import pr122_site_hub_unified_release as original
        need(type(transaction) is original.Transaction and type(transaction.ops) is original.c.Ops,
             'STATIC_ORIGINAL_IMPLEMENTATION_REQUIRED')
        self.t, self.u, self.c = transaction, original, original.c
        self.plan = copy.deepcopy(plan)
        need(type(inputs) is dict and set(inputs) == {'schema', 'stages'} and inputs['schema'] == 1
             and type(inputs['stages']) is dict and set(inputs['stages']) == set(STATIC_STAGES),
             'STATIC_FIXED_INPUTS')
        self.inputs = copy.deepcopy(inputs['stages'])
        self.coordinator = None
        self._bind_source()
        for stage in STATIC_STAGES:
            need(self.inputs[stage] == self.expected_input(stage), 'STATIC_INPUT_BINDING')

    def attach(self, coordinator):
        need(self.coordinator is None, 'STATIC_ADAPTER_ALREADY_BOUND')
        need(tuple(coordinator.STAGES) == STATIC_STAGES, 'STATIC_COORDINATOR_STAGE_SCOPE')
        self.coordinator = coordinator

    def _stage(self, stage):
        need(stage in STATIC_STAGES, 'STATIC_FIXED_STAGE')
        return STATIC_STAGES.index(stage)

    def _bind_source(self):
        t, c, u = self.t, self.c, self.u
        pins_raw = c.read(u.PINS)
        need(t.pins == json.loads(pins_raw) and t.id == t.pins['transaction_id'], 'STATIC_EXACT_HOST_PINS')
        baseline = {key: t.pins[key] for key in (
            'previous_release', 'previous_receipt_sha256', 'previous_manifest_sha256', 'nginx')}
        need(self.plan.get('host_pins_sha256') == digest(pins_raw)
             and self.plan.get('static_baseline_sha256') == digest(canonical(baseline)),
             'STATIC_SIGNED_BASELINE_BINDING')
        need(t.folder == c.CONTROL / 'transactions' / t.id and t.receipt == t.folder / 'receipt.json',
             'STATIC_FIXED_CHILD_PATH')
        need(digest(c.read(u.HELPER)) == u.HELPER_SHA, 'STATIC_HELPER_DRIFT')
        need(digest(c.read(c.PREFLIGHT_PATH)) == c.PREFLIGHT_SHA, 'STATIC_PREFLIGHT_DRIFT')
        return {'pins_sha256': digest(pins_raw), 'wrapper_sha256': digest(c.read(u.HERE))}

    def expected_input(self, stage):
        self._stage(stage)
        return {'stage': stage, 'transaction_id': self.t.id, 'release_id': self.t.pins['release_id'],
                **self._bind_source(), **{key: self.t.pins[key] for key in (
                    'static_artifact_sha256', 'package_manifest_sha256', 'source_archive_sha256')}}

    def input(self, stage):
        self._stage(stage)
        return copy.deepcopy(self.inputs[stage])

    def implementation(self, stage):
        self._stage(stage)
        # Closure identity, not a JSON-selected implementation or command.
        return canonical({'adapter': digest(self.c.read(Path(__file__).resolve())),
                          'wrapper': digest(self.c.read(self.u.HERE)),
                          'helper': digest(self.c.read(self.u.HELPER)),
                          'preflight': digest(self.c.read(self.c.PREFLIGHT_PATH)),
                          'publisher': self.t.pins['publisher_sha256']})

    def _public_transport(self):
        # Only the already validated explicit static authority can consolidate
        # duplicate no-effect checks. Legacy and login behavior stay unchanged.
        return (getattr(getattr(self.coordinator, "r", None), "authorization_mode", None) == "STATIC_GITHUB_DUAL_APPROVAL"
                and self.plan.get("github_transport", {}).get("mode") == "PUBLIC_GITHUB")

    def _bound(self, stage, lease=None, *, online=True):
        self._stage(stage)
        need(self.coordinator is not None, 'STATIC_COORDINATOR_REQUIRED')
        if lease is not None:
            lease.assert_fence()
            if online: lease.authority()
            else: lease.assert_active()
            lease.verify_inputs(stage)
        need(self.expected_input(stage) == self.inputs[stage], 'STATIC_INPUT_DRIFT')
        self.t.bind_inputs()

    def _load(self):
        t, c = self.t, self.c
        raw = c.read(t.receipt)
        need(stat.S_IMODE(t.receipt.lstat().st_mode) == 0o600, 'STATIC_CHILD_RECEIPT_MODE')
        data = json.loads(raw)
        bound = self._bind_source()
        need(data.get('schema') == 1 and data.get('transaction_id') == t.id
             and data.get('release_id') == t.pins['release_id']
             and all(data.get(key) == value for key, value in bound.items())
             and data.get('workflow_approval_sha256') == digest(canonical(self.coordinator.approval))
             and data.get('approval') == self.coordinator.approval
             and data.get('source_commit') == self.plan['source_commit'], 'STATIC_CHILD_PERMISSION_BINDING')
        need(data.get('state') in ('APPLYING', 'HOLD_PARTIAL', STATIC_SUCCESS),
             'STATIC_CHILD_STATE')
        completed = data.get('completed')
        need(type(completed) is list and completed == list(STATIC_STAGES[:len(completed)])
             and len(completed) <= len(STATIC_STAGES), 'STATIC_CHILD_COMPLETED_PREFIX')
        intent = data.get('intent')
        need(intent is None or (len(completed) < len(STATIC_STAGES)
             and intent == STATIC_STAGES[len(completed)]), 'STATIC_CHILD_INTENT_ORDER')
        need(type(data.get('nginx_identity')) is dict and type(data.get('sandbox')) is dict,
             'STATIC_PROCESS_EVIDENCE_REQUIRED')
        t.data = copy.deepcopy(data)
        t.nginx_identity = copy.deepcopy(data['nginx_identity'])
        return data

    def _pointer(self, expected):
        p = self.c.BASE / 'current'
        info = p.lstat()
        need(stat.S_ISLNK(info.st_mode) and info.st_uid == os.geteuid()
             and os.readlink(p) == expected, 'STATIC_CURRENT_IDENTITY')
        return expected

    def _runtime(self, data):
        # Original runtime() only observes files, systemctl show, sockets and BPF.
        need(self.t.runtime() == data['sandbox'], 'STATIC_RUNTIME_PROCESS_DRIFT')
        need(self.t.ops.nginx_identity() == data['nginx_identity'], 'STATIC_NGINX_PROCESS_DRIFT')
        return {'sandbox': data['sandbox'], 'nginx_identity': data['nginx_identity']}

    def _backup(self, data):
        t, c = self.t, self.c
        backup = data.get('backup', {})
        need(backup.get('archive_verified') is True and data.get('previous_link') == t.pins['previous_release'],
             'STATIC_VERIFIED_BACKUP_REQUIRED')
        old_raw = c.read(t.inputs / 'R2_CANDIDATE_MANIFEST.json')
        need(digest(old_raw) == t.pins['previous_manifest_sha256'], 'STATIC_PREVIOUS_MANIFEST_DRIFT')
        schema = t.pins.get('package_schema', 'LEGACY_UNIFIED_V1')
        need(schema in ('LEGACY_UNIFIED_V1', 'FULL_STATIC_REVIEW_V1'), 'STATIC_BACKUP_PACKAGE_SCHEMA')
        count = t.pins.get('previous_file_count') if schema == 'FULL_STATIC_REVIEW_V1' else 1279
        need(type(count) is int and 1 <= count <= 10000, 'STATIC_PREVIOUS_FILE_COUNT')
        old = {r['path']: {'size': r['size'], 'sha256': r['sha256']} for r in json.loads(old_raw)['files']}
        need(len(old) == count and backup.get('static_files') == old, 'STATIC_BACKUP_MANIFEST')
        need(type(backup.get('nginx')) is dict and set(backup['nginx']) == set(t.pins['nginx']),
             'STATIC_BACKUP_CONFIG_SET')
        directory = t.folder / 'backup'
        c.trusted(directory, True)
        need(stat.S_IMODE(directory.lstat().st_mode) == 0o700, 'STATIC_BACKUP_MODE')
        configs = {}
        for number, (name, expected) in enumerate(sorted(t.pins['nginx'].items())):
            row = backup['nginx'][name]
            need(row.get('copy') == 'config-' + str(number) and row.get('sha256') == expected,
                 'STATIC_BACKUP_CONFIG_BINDING')
            path = directory / row['copy']
            need(stat.S_IMODE(path.lstat().st_mode) == 0o600 and digest(c.read(path)) == expected,
                 'STATIC_BACKUP_CONFIG_DRIFT')
            configs[name] = expected
        path = directory / 'previous-static.tar.gz'; raw = c.read(path)
        need(stat.S_IMODE(path.lstat().st_mode) == 0o600 and digest(raw) == backup.get('static_sha256'),
             'STATIC_BACKUP_ARCHIVE_DRIFT')
        expected_names = {'public/' + name for name in old} | {
            'release-metadata/inline-csp.conf', 'release-metadata/inline-csp.json'}
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
            members = archive.getmembers()
            need(len(members) == count + 2 and {m.name for m in members} == expected_names
                 and all(m.isfile() and 0 <= m.size <= 8000000 for m in members), 'STATIC_BACKUP_MEMBERS')
            for member in members:
                payload = archive.extractfile(member).read()
                if member.name.startswith('public/'):
                    need({'size': len(payload), 'sha256': digest(payload)} == old[member.name[7:]],
                         'STATIC_BACKUP_CONTENT')
                else:
                    need(payload == c.read(Path(t.pins['previous_release']) / member.name),
                         'STATIC_PREVIOUS_METADATA_DRIFT')
        return {'archive_sha256': digest(raw), 'configs': configs, 'manifest_sha256': digest(canonical(old))}

    def _bundle(self):
        root = self.t.folder / 'bundle'; self.c.trusted(root, True)
        need(stat.S_IMODE(root.lstat().st_mode) == 0o755, 'STATIC_SEALED_BUNDLE_MODE')
        observed = {}
        for path in root.rglob('*'):
            self.c.trusted(path, path.is_dir())
            info = path.lstat()
            need(stat.S_IMODE(info.st_mode) == (0o755 if path.is_dir() else 0o644), 'STATIC_BUNDLE_MODE')
            if path.is_file(): observed[path.relative_to(root).as_posix()] = self.c.read(path)
        need(observed == self.t.entries, 'STATIC_SEALED_BUNDLE_DRIFT')
        return {'package_manifest_sha256': self.t.pins['package_manifest_sha256'],
                'members_sha256': digest(canonical({name: digest(raw) for name, raw in observed.items()}))}

    @contextmanager
    def _publisher_read_lock(self):
        # Unlike publisher.lock(), never create its directory or lock file.
        path = self.c.BASE / '.release.lock'; self.c.trusted(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd); named = path.lstat()
            need(stat.S_IMODE(info.st_mode) == 0o600 and
                 (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino), 'STATIC_PUBLISHER_LOCK_DRIFT')
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            named = path.lstat()
            need((info.st_dev, info.st_ino) == (named.st_dev, named.st_ino), 'STATIC_PUBLISHER_LOCK_REPLACED')
            yield
        finally:
            os.close(fd)

    def _publisher(self, states):
        self._bundle(); self.t.load_publisher()
        path = self.c.BASE / 'transactions' / (self.t.id + '.json')
        with self._publisher_read_lock(), self.t.pub.Deadline(120) as deadline:
            need(stat.S_IMODE(path.lstat().st_mode) == 0o600, 'STATIC_PUBLISHER_RECEIPT_MODE')
            self.c.read(path)
            _, receipt, _, _ = self.t.pub.receipt_for(self.t.args, states, deadline)
            need(receipt.get('trusted_manifest') == json.loads(self.t.entries['candidate-manifest.json'])
                 and receipt.get('source_archive_sha256') == self.t.pins['source_archive_sha256'],
                 'STATIC_PUBLISHER_MANIFEST_BINDING')
            return copy.deepcopy(receipt)

    def _prepared(self, receipt):
        return {key: receipt[key] for key in ('release', 'candidate_manifest_sha256', 'source_pin_sha256',
                'package_manifest_sha256', 'source_archive_sha256', 'release_envelope', 'csp_inventory')}

    def _nginx(self):
        t, c = self.t, self.c
        staged = digest(self.u.routes(t.entries)[0])
        expected = {**t.pins['nginx'], str(c.LOCATIONS): staged}
        target = str(c.BASE / 'releases' / t.pins['release_id'])
        current = os.readlink(c.BASE / 'current')
        need(current in (t.pins['previous_release'], target), 'STATIC_FOREIGN_CURRENT')
        self._pointer(current)
        if current == target:
            publisher = self._publisher({'ACTIVATION_INTENT', 'UNKNOWN_AFTER_ACTIVATE', 'ACTIVATED', 'CHECKED'})
            expected.pop(str(Path(t.pins['previous_release']) / 'release-metadata/inline-csp.conf'))
            expected[str(Path(target) / 'release-metadata/inline-csp.conf')] = publisher['release_envelope']['csp_conf']['sha256']
        t.inventory(expected)
        return {'locations_sha256': staged, 'original_nginx_sha256': digest(canonical(t.pins['nginx']))}

    def _activated(self):
        publisher = self._publisher({'ACTIVATED', 'CHECKED'})
        target = str(self.c.BASE / 'releases' / self.t.pins['release_id'])
        self._pointer(target)
        need(publisher.get('target_current') == target
             and publisher.get('previous_current', {}).get('link') == self.t.pins['previous_release'],
             'STATIC_ACTIVATION_BINDING')
        need(not os.path.lexists(self.c.BASE / ('.current-' + self.t.id)), 'STATIC_ACTIVATION_TEMP_PRESENT')
        return self._prepared(publisher)

    def _static_https(self, lease=None):
        # GET-only half of the original smoke contract. Never call preview_probe.
        routes = self.u.smoke_routes(self.t.entries)
        for route, (kind, target) in routes.items():
            if kind != 'file': continue
            if lease is not None: lease.assert_active()
            status, headers, body = self.t.ops.request(route, https=True)
            need(status == 200 and digest(body) == digest(self.t.entries['overlay/public' + target])
                 and 'content-security-policy' in headers and headers.get('x-content-type-options') == 'nosniff',
                 'STATIC_HTTPS_DRIFT')
        if lease is not None: lease.assert_active()
        need(self.t.ops.request('/visual/pr122-does-not-exist', https=True)[0] == 404,
             'STATIC_HTTPS_NEGATIVE_DRIFT')
        if lease is not None: lease.assert_active()
        return {'manifest_routes_checked': sum(kind == 'file' for kind, _ in routes.values()),
                'real_https': True, 'production_browser': 'PENDING',
                'state': 'STATIC_READONLY_HTTP_COMPLETE', 'business_e2e': 'PENDING', 'preview_post': 'PENDING'}

    def _observe(self, stage):
        index = self._stage(stage); data = self._load()
        need(stage in data['completed'], 'STATIC_DURABLE_COMPLETION_REQUIRED')
        if stage == 'BACKUP_VERIFIED': effect = self._backup(data)
        elif stage == 'SEALED_BUNDLE': effect = self._bundle()
        elif stage == 'STATIC_PREPARED':
            effect = self._prepared(self._publisher({'PREPARED', 'ACTIVATION_INTENT',
                                                    'UNKNOWN_AFTER_ACTIVATE', 'ACTIVATED', 'CHECKED'}))
        elif stage in ('NGINX_STAGED', 'NGINX_VALIDATED', 'ACTIVATION_DRIFT_CHECK'):
            effect = self._nginx()
            if stage != 'NGINX_STAGED': effect.update(self._runtime(data))
            if stage == 'ACTIVATION_DRIFT_CHECK':
                need(self.t.snapshot() == data['backup']['static_files'], 'STATIC_PREVIOUS_PUBLIC_DRIFT')
        elif stage == 'STATIC_ACTIVATED': effect = self._activated()
        elif stage == 'NGINX_RELOADED':
            effect = {'prepared': self._activated(), 'nginx': self._nginx(), **self._runtime(data)}
        elif stage == 'HTTPS_SMOKE':
            effect = {'prepared': self._activated(), 'nginx': self._nginx(), **self._runtime(data)}
            observed = self._static_https()
            need(data.get('https') == observed, 'STATIC_SMOKE_DURABLE_RESULT_REQUIRED')
            effect['https'] = observed
        elif stage == 'STATIC_CHECK':
            publisher = self._publisher({'CHECKED'}); self._activated()
            effect = self._prepared(publisher)
        projection = {'schema': 'STATIC_PHASE_RECEIPT_V1', 'transaction_id': self.t.id,
                      'release_id': self.t.pins['release_id'], **self._bind_source(),
                      'workflow_approval_sha256': data['workflow_approval_sha256'],
                      'source_commit': data['source_commit'], 'stage': stage,
                      'completed_prefix': list(STATIC_STAGES[:index + 1]), 'effect': effect}
        return {'state': 'COMPLETE', 'receipt_sha256': digest(canonical(projection)),
                'effect_sha256': digest(canonical(effect)), 'source_commit': data['source_commit']}

    def inherited(self, stage):
        self._bound(stage)
        return self._observe(stage)

    def verify(self, stage, checkpoint):
        self._bound(stage)
        return self._observe(stage) == checkpoint

    def _fresh_absent(self):
        t, c = self.t, self.c
        return all(not os.path.lexists(path) for path in (
            t.folder, c.BASE / 'transactions' / (t.id + '.json'),
            c.BASE / 'releases' / t.pins['release_id'], c.BASE / ('.staging-' + t.id),
            c.BASE / ('.current-' + t.id)))

    def _initialize(self, lease):
        t, c = self.t, self.c
        need(self._fresh_absent(), 'STATIC_EXISTING_TRANSACTION_NO_TAKEOVER')
        self._admit(lease, online=not self._public_transport())
        files = self._original_action('baseline', lease)
        self._admit(lease, public_calls_needed=46)
        need(self._fresh_absent(), 'STATIC_INITIALIZATION_COLLISION')
        guarded = self._effect_helpers(lease)
        guarded.mkdir(t.folder, 0o700)
        t.data = {'schema': 1, 'transaction_id': t.id, 'release_id': t.pins['release_id'],
                  **self._bind_source(), 'state': 'APPLYING', 'completed': [], 'intent': None,
                  'approval': copy.deepcopy(self.coordinator.approval),
                  'workflow_approval_sha256': digest(canonical(self.coordinator.approval)),
                  'source_commit': self.plan['source_commit'], 'sandbox': t.sandbox,
                  'nginx_identity': t.nginx_identity, 'production_browser': 'NOT_RUN'}
        guarded.atomic(t.receipt, t.data)
        return files

    def _effect_helpers(self, lease):
        return types.SimpleNamespace(**_guarded_namespace(self.c, lease.assert_active))

    def _original_action(self, name, lease, *args):
        need(name in ('baseline', 'backup', 'seal_bundle'), 'STATIC_FIXED_ORIGINAL_ACTION')
        helper = _guarded_namespace(self.c, lease.assert_active)
        wrapper = dict(vars(self.u))
        wrapper.update(c=types.SimpleNamespace(**helper), os=helper['os'], Path=helper['Path'],
                       __builtins__=helper['__builtins__'])
        function = getattr(type(self.t), name)
        need(function.__globals__ is vars(self.c) or function.__globals__ is vars(self.u),
             'STATIC_ORIGINAL_ACTION_SOURCE')
        namespace = helper if function.__globals__ is vars(self.c) else wrapper
        action = types.FunctionType(function.__code__, namespace, function.__name__,
                                    function.__defaults__, function.__closure__)
        original_ops = self.t.ops
        class FixedOps:
            def __getattr__(inner, method):
                need(method in ('unit', 'nginx_identity', 'nginx_test', 'sandbox', 'request',
                                'reload_nginx', 'command'), 'STATIC_UNEXPECTED_OPERATION')
                original = getattr(original_ops, method)
                def guarded(*values, **options):
                    lease.assert_active(); return original(*values, **options)
                return guarded
        transaction = copy.copy(self.t); transaction.ops = FixedOps()
        lease.assert_active(); result = action(transaction, *args)
        for attribute in ('data', 'pub', 'args', 'sandbox', 'nginx_identity'):
            if hasattr(transaction, attribute): setattr(self.t, attribute, getattr(transaction, attribute))
        return result

    def _publisher_action(self, action, lease):
        need(action in ('prepare', 'activate', 'check'), 'STATIC_FIXED_PUBLISHER_ACTION')
        self.t.load_publisher()
        publisher = _guarded_namespace(self.t.pub, lease.assert_active)
        lease.assert_active()
        with publisher['Deadline'](120) as deadline:
            with publisher['lock'](publisher['Path'](self.c.BASE), 5, deadline, os.geteuid()):
                return publisher[action](self.t.args, deadline)

    def _step(self, stage, action, lease):
        """Original intent protocol with guards on every write and completion."""
        lease.assert_active()
        need(time.monotonic() < self.t.deadline, 'STATIC_PHASE_DEADLINE')
        guarded = self._effect_helpers(lease)
        pending = copy.deepcopy(self.t.data); pending['intent'] = stage
        guarded.atomic(self.t.receipt, pending); self.t.data = pending
        result = action()
        # Never clear the durable intent after an expired/lost child lease.
        lease.assert_active()
        completed = copy.deepcopy(pending)
        completed['completed'].append(stage); completed['intent'] = None
        if stage == 'HTTPS_SMOKE': completed['https'] = result
        if stage == 'STATIC_CHECK':
            completed.update(state=STATIC_SUCCESS, production_browser='PENDING',
                             business_e2e='PENDING', preview_post='PENDING')
        guarded.atomic(self.t.receipt, completed); self.t.data = completed
        return result

    def _admit(self, lease, *, online=True, public_calls_needed=None):
        if online: lease.authority()
        else: lease.assert_fence()
        lease.assert_active()
        if online and self._public_transport():
            from scripts.pr122_static_github_approval import require_public_budget
            # Exact success-path suffix plus 13 read-only failure-convergence
            # calls. This is a local bound, not a reservation of shared IP quota.
            suffix = (45, 42, 39, 36, 33, 30, 24, 21, 18, 15)
            needed = suffix[self._stage(lease._stage)] if public_calls_needed is None else public_calls_needed
            require_public_budget(self.plan, needed)
        remaining = self.coordinator.approval['expires_unix'] - time.time()
        need(remaining >= PHASE_ADMISSION_SECONDS, 'STATIC_PHASE_AUTHORIZATION_WINDOW')
        now = time.monotonic()
        self.t.deadline = min(now + PHASE_ADMISSION_SECONDS, now + remaining)

    def _before_activation(self, lease):
        # Same original checks, with the signed Coordinator authority replacing
        # the incompatible legacy one-use gate. No scope or operation is added.
        lease.authority(); lease.assert_active()
        self._pointer(self.t.pins['previous_release'])
        need(self.t.snapshot() == self.t.data['backup']['static_files'], 'STATIC_ACTIVATION_PUBLIC_DRIFT')
        self.t.inventory({**self.t.pins['nginx'],
                          str(self.c.LOCATIONS): digest(self.u.routes(self.t.entries)[0])})
        self._runtime(self.t.data)

    def execute(self, stage, lease):
        public = self._public_transport()
        self._bound(stage, lease, online=not public)
        self._admit(lease, online=not public)
        t, c = self.t, self.c
        files = None
        if stage == 'BACKUP_VERIFIED' and not os.path.lexists(t.folder):
            files = self._initialize(lease)
        data = self._load(); index = self._stage(stage)
        need(data['completed'] == list(STATIC_STAGES[:index]) and data['intent'] is None,
             'STATIC_ORIGINAL_STEP_ALREADY_STARTED')
        if stage == 'BACKUP_VERIFIED':
            # A created child folder/receipt without backup intent is still an
            # existing transaction. No reinitialization or assumed empty backup.
            need(files is not None, 'STATIC_INITIALIZATION_INTERRUPTED')
        guarded = self._effect_helpers(lease)
        actions = {
            'BACKUP_VERIFIED': lambda: self._original_action('backup', lease, files),
            'SEALED_BUNDLE': lambda: self._original_action('seal_bundle', lease),
            'STATIC_PREPARED': lambda: self._publisher_action('prepare', lease),
            'NGINX_STAGED': lambda: guarded.write(c.LOCATIONS, self.u.routes(t.entries)[0],
                                          expected=t.pins['nginx'][str(c.LOCATIONS)]),
            'NGINX_VALIDATED': lambda: (lease.assert_active(), t.ops.nginx_test())[1],
            'ACTIVATION_DRIFT_CHECK': lambda: self._before_activation(lease),
            'STATIC_ACTIVATED': lambda: self._publisher_action('activate', lease),
            'NGINX_RELOADED': lambda: (lease.assert_active(), t.ops.reload_nginx())[1],
            'HTTPS_SMOKE': lambda: self._static_https(lease),
            'STATIC_CHECK': lambda: self._publisher_action('check', lease),
        }
        try:
            self._admit(lease)
        except Denied as error:
            # This admission is immediately before the stage effect.  Preserve
            # the original budget rejection semantics, but expose one exact
            # machine-readable stop only when the child transaction is still at
            # the clean next-step boundary and no stage effect has begun.
            if (public and str(error) == 'HOLD:STATIC_GITHUB_PUBLIC_PHASE_BUDGET'
                    and data['completed'] == list(STATIC_STAGES[:index])
                    and data['intent'] is None):
                raise Denied('HOLD:STATIC_SAFE_RETRY_PUBLIC_BUDGET') from None
            raise
        # Revalidate the immediate activation conditions again, not just a prior
        # completed pre-activation check, before the actual pointer-switch intent.
        if stage == 'STATIC_ACTIVATED':
            self._before_activation(lease)
            self._admit(lease)
        self._step(stage, actions[stage], lease)
        lease.authority(); lease.assert_active()
        return self._observe(stage)

    def reconcile(self, stage, intent, checkpoint, lease):
        self._bound(stage, lease)
        proof = {'status': 'UNKNOWN', 'action': 'RECONCILE_STATIC',
                 'evidence_sha256': digest(canonical({'stage': stage, 'result': 'UNPROVEN'})),
                 'checkpoint': None}
        try:
            observed = self._observe(stage)
            proof.update(status='COMPLETE', checkpoint=observed, evidence_sha256=digest(canonical(observed)))
        except (Denied, OSError, RuntimeError, ValueError, KeyError, TypeError, tarfile.TarError):
            # Only an absent first transaction or an exact next-step boundary
            # proves the original action was never admitted. Intent is never
            # treated as permission, even for apparently harmless operations.
            safe = stage == 'BACKUP_VERIFIED' and self._fresh_absent()
            if stage != 'BACKUP_VERIFIED':
                try:
                    data = self._load(); index = self._stage(stage)
                    safe = data['completed'] == list(STATIC_STAGES[:index]) and data['intent'] is None
                    if safe:
                        for earlier in STATIC_STAGES[:index]: self._observe(earlier)
                except (Denied, OSError, RuntimeError, ValueError, KeyError, TypeError, tarfile.TarError): safe = False
            if safe:
                proof.update(status='SAFE_TO_RETRY', evidence_sha256=digest(canonical({
                    'stage': stage, 'original_step_not_started': True, 'input': self.input(stage)})))
        lease.assert_fence(); lease.authority()
        return proof
