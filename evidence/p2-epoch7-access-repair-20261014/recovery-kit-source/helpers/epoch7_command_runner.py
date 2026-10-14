"""Bounded exact-command adapter for an admitted driver; no CLI or host defaults.

Caller supplies an exact reviewed finite command contract and a live admission
check. Constructing this object grants no authority. No model or network API.
"""
import copy
import os
import subprocess
from protected_command_evidence import OPERATIONS, _signal_owned_group
from epoch7_recovery_sequence import PHASES, MAX_COMMANDS, BoundedDiagnostics, CommandFailure



def need(value, reason):
    if not value: raise ValueError('EPOCH7_COMMAND_'+reason)


def classify(error):
    if isinstance(error,KeyboardInterrupt):return 'KeyboardInterrupt'
    if isinstance(error,SystemExit):return 'SystemExit'
    if isinstance(error,OSError):return 'OSError'
    return 'Exception'


class ExactCommandRunner(object):
    def __init__(self, contract, admission_check, diagnostics, launcher=subprocess.Popen):
        need(type(contract) is dict and 0 < len(contract) <= 100, 'FINITE_CONTRACT')
        for key, spec in contract.items():
            need(type(key) is str and key and len(key) <= 64 and
                 all(c in 'abcdefghijklmnopqrstuvwxyz0123456789_' for c in key), 'CONTRACT_KEY')
            need(type(spec) is dict and set(spec) in ({'phase','operation','argv','env','timeout','accepted_returncodes'}, {'phase','operation','argv','env','timeout','accepted_returncodes','cwd'}), 'CONTRACT_FIELDS')
            need(spec.get('cwd') is None or (type(spec['cwd']) is str and spec['cwd'].startswith('/') and '\0' not in spec['cwd'] and os.path.normpath(spec['cwd']) == spec['cwd']), 'CWD')
            need(spec['phase'] in PHASES and spec['operation'] in OPERATIONS, 'FIXED_LABELS')
            need(type(spec['argv']) is list and 1 <= len(spec['argv']) <= 64 and
                 all(type(v) is str and v and '\0' not in v and len(v)<=8192 for v in spec['argv'])
                 and spec['argv'][0].startswith('/'), 'ARGV')
            need(type(spec['env']) is dict and len(spec['env'])<=16 and
                 all(type(k) is str and type(v) is str and k and '=' not in k
                     and '\0' not in k+v and len(k)+len(v)<=8192 for k,v in spec['env'].items()), 'ENV')
            need(type(spec['accepted_returncodes']) is list and 1 <= len(spec['accepted_returncodes']) <= 8 and
                 all(type(v) is int and 0 <= v <= 255 for v in spec['accepted_returncodes']) and
                 len(set(spec['accepted_returncodes'])) == len(spec['accepted_returncodes']), 'RETURN_CODE_CONTRACT')
            need(type(spec['timeout']) is int and 1 <= spec['timeout'] <= 60, 'TIMEOUT')
        need(callable(admission_check) and callable(launcher) and isinstance(diagnostics,BoundedDiagnostics), 'ADAPTERS')
        self.contract=copy.deepcopy(contract);self.check=admission_check
        self.diagnostics=diagnostics;self.launcher=launcher
        self.poisoned=False;self.last_summary=None

    def run(self, key):
        need(not self.poisoned, 'PREVIOUS_FAILURE_NO_RETRY')
        need(key in self.contract, 'UNKNOWN_OPERATION')
        need(self.diagnostics.sequence < MAX_COMMANDS and self.diagnostics.capture_allocation is None
             and self.diagnostics.scope_failure is None, 'DIAGNOSTIC_CAPACITY_OR_PENDING_FAILURE')
        need(self.check() is True, 'LIVE_ADMISSION')
        spec=copy.deepcopy(self.contract[key])
        self.poisoned=True
        try:
            process=self.launcher(spec['argv'],stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0,
                env=spec['env'],cwd=spec.get('cwd'),close_fds=True,start_new_session=True,shell=False)
        except BaseException as error:
            failure=self.diagnostics.record_adapter_failure(spec['phase'],spec['operation'],
                classify(error),'SPAWN_UNCONFIRMED')
            self.last_summary=copy.deepcopy(failure.summary)
            if isinstance(error,(KeyboardInterrupt,SystemExit)):raise
            raise failure from None
        try:
            result=self.diagnostics.capture_owned(process,spec['phase'],spec['operation'],
                timeout_seconds=spec['timeout'],cleanup_seconds=2,stream_limit=65536,
                accepted_returncodes=tuple(spec['accepted_returncodes']),return_output=True)
        except CommandFailure:
            # Shared diagnostics has already captured and latched the failure.
            # Outer sequence contains first, then publishes private evidence.
            raise
        except BaseException as error:
            failure=None;record_error=None
            try:
                failure=self.diagnostics.record_adapter_failure(spec['phase'],spec['operation'],
                    classify(error),'CAPTURE_UNCONFIRMED')
            except BaseException as failed_record:
                record_error=failed_record
            cleanup={};interrupt=error if isinstance(error,(KeyboardInterrupt,SystemExit)) else None
            if interrupt is None and isinstance(record_error,(KeyboardInterrupt,SystemExit)):
                interrupt=record_error
            for label, action in (
                    ('signal',lambda:_signal_owned_group(process)),
                    ('stdout_close',lambda:process.stdout.close()),
                    ('stderr_close',lambda:process.stderr.close()),
                    ('reap',lambda:process.wait(timeout=2))):
                try: action();cleanup[label]='ATTEMPTED'
                except BaseException as secondary:
                    cleanup[label]='UNKNOWN'
                    if interrupt is None and isinstance(secondary,(KeyboardInterrupt,SystemExit)):
                        interrupt=secondary
            self.last_summary={'failed_stage':spec['phase']+'_INTENT','operation':spec['operation'],
                'epoch':8,'reason':'CAPTURE_UNCONFIRMED','diagnostic_state':'UNAVAILABLE',
                'cleanup':cleanup,'descendants':'UNKNOWN'}
            if interrupt is not None:raise interrupt
            if failure is None:
                raise RuntimeError('EPOCH7_CAPTURE_FAILURE_RECORD_UNAVAILABLE') from None
            raise failure from None
        self.poisoned=False
        return result
