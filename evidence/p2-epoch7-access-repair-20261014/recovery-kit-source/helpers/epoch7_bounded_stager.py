"""Frozen stager source, isolated namespace, exact bounded subprocess proxy."""
import hashlib
import os
import re
import stat
import subprocess
import types

from epoch7_command_runner import ExactCommandRunner
from epoch7_recovery_sequence import BoundedDiagnostics

INSTALLER_SHA = '943f4d04861d8b580008af457d90187622a9de2d1c8cd66c93a721b8ac2be0f3'
SMOKES = ('stage1/development_service.py', 'stage1/owner_callback_server.py',
          'stage1/owner_dashboard.py', 'stage1/root_broker.py',
          'stage1/github_issue_consumer.py', 'stage1/ledger_service.py')
GIT_ENV = {'HOME': '/nonexistent', 'PATH': '/usr/bin:/bin',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
SMOKE_ENV = {'HOME': '/nonexistent', 'PATH': '/usr/bin:/bin',
             'LANG': 'C', 'LC_ALL': 'C', 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'}


def need(value, reason):
    if not value: raise ValueError('EPOCH7_STAGER_' + reason)


class BoundedStagerSubprocess(object):
    PIPE = subprocess.PIPE
    DEVNULL = subprocess.DEVNULL
    def __init__(self, source_root, python_path, admission_check, executable_check,
                 diagnostics, runner_factory=ExactCommandRunner):
        need(os.path.isabs(source_root) and os.path.normpath(source_root) == source_root,
             'EXACT_SOURCE_ROOT')
        need(type(python_path) is str and python_path.startswith('/') and
             os.path.normpath(python_path) == python_path and
             callable(admission_check) and callable(executable_check) and
             isinstance(diagnostics, BoundedDiagnostics), 'EXPLICIT_PROTECTED_ADAPTERS')
        self.root, self.python = source_root, python_path
        self.admission, self.executable = admission_check, executable_check
        self.diagnostics, self.factory = diagnostics, runner_factory
        self.failed = False
        self.stage = None
        self.next_smoke = 0
        self.git_calls = 0

    def run(self, argv, **kwargs):
        need(not self.failed, 'PREVIOUS_FAILURE_NO_RETRY')
        need(type(argv) is list and kwargs.get('timeout') == 10 and
             kwargs.get('check') is False, 'EXACT_CALL_CONTRACT')
        git = ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', 'rev-parse',
               'HEAD', 'HEAD^{tree}', 'HEAD^']
        if argv == git:
            need(kwargs == {'cwd': self.root, 'stdout': self.PIPE, 'stderr': self.DEVNULL,
                 'timeout': 10, 'check': False, 'env': GIT_ENV} and self.git_calls < 4,
                 'GIT_EXACT_ARGV_AND_OPTIONS')
            operation, env, cwd = 'stage_source_verify', GIT_ENV, self.root
            self.git_calls += 1
        else:
            need(len(argv) == 3 and argv[0] == self.python and argv[2] == '--help' and
                 self.next_smoke < len(SMOKES), 'SMOKE_EXACT_ARGV')
            suffix = '/' + SMOKES[self.next_smoke]
            need(argv[1].endswith(suffix), 'SMOKE_FIXED_ORDER')
            stage = argv[1][:-len(suffix)]
            need(re.fullmatch(r'/opt/xuanjun-control-releases/\.integration-[0-9a-f]{16}', stage),
                 'STAGING_PATH_SCOPE')
            need(kwargs == {'cwd': stage + '/stage1', 'stdout': self.DEVNULL,
                 'stderr': self.PIPE, 'timeout': 10, 'check': False}, 'SMOKE_EXACT_OPTIONS')
            # Frozen stager made this protected temporary directory and already
            # verified every source byte. Keep one directory identity for all six.
            info = os.lstat(stage)
            need(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and
                 stat.S_IMODE(info.st_mode) == 0o700 and os.path.realpath(stage) == stage,
                 'STAGING_DIRECTORY_AUTHORITY')
            identity = (stage, info.st_dev, info.st_ino)
            if self.stage is None: self.stage = identity
            need(self.stage == identity, 'STAGING_DIRECTORY_CHANGED')
            self.next_smoke += 1
            operation, env, cwd = 'stage_smoke_check', SMOKE_ENV, stage + '/stage1'
        need(self.executable(argv[0]) is True, 'EXECUTABLE_PIN_CHANGED')
        spec = {'phase': 'stage_exact_release', 'operation': operation, 'argv': list(argv),
                'env': dict(env), 'cwd': cwd, 'timeout': 10, 'accepted_returncodes': [0]}
        self.failed = True
        result = self.factory({'stager': spec}, self.admission, self.diagnostics).run('stager')
        need(self.executable(argv[0]) is True, 'EXECUTABLE_CHANGED_AFTER_COMMAND')
        self.failed = False
        return result


class FrozenBoundedInstaller(object):
    """Only the exact frozen renderer/stager bytes can execute in this namespace."""
    def __init__(self, source, source_root, python_path, admission_check,
                 executable_check, diagnostics, runner_factory=ExactCommandRunner):
        need(type(source) is bytes and hashlib.sha256(source).hexdigest() == INSTALLER_SHA,
             'FROZEN_SOURCE_HASH')
        self.proxy = BoundedStagerSubprocess(source_root, python_path, admission_check,
            executable_check, diagnostics, runner_factory)
        namespace = {'__name__': 'epoch7_isolated_frozen_stager'}
        exec(compile(source, '<pinned-frozen-stager>', 'exec'), namespace)
        # No global monkeypatch. All commands from the immutable helper must
        # pass its only two exact call patterns above or fail closed.
        namespace['subprocess'] = self.proxy
        namespace['sys'] = types.SimpleNamespace(executable=python_path)
        self.namespace = namespace
        self.installed = False

    def verify(self, *args, **kwargs):
        return self.namespace['verify'](*args, **kwargs)

    def install(self, *args, **kwargs):
        need(not self.installed, 'ONE_STAGING_ATTEMPT')
        self.installed = True
        result = self.namespace['install'](*args, **kwargs)
        need(self.proxy.next_smoke == len(SMOKES), 'ALL_SIX_SMOKES_REQUIRED')
        return result
