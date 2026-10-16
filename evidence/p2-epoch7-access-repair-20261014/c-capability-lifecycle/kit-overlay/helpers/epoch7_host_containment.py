"""Finite retained Gateway restore and independently attempted containment."""
import copy
import os
import subprocess
import time

import epoch7_delta as d
import epoch7_protected_fs as fs
from epoch7_snapshot import decode
from epoch7_host_phases import HostPhaseFilesystem, need, sha
from epoch7_command_runner import ExactCommandRunner
from epoch7_recovery_sequence import (STOP_UNITS, CLEANUP_METHODS, check_observation,
                                      observation, BoundedDiagnostics)
from legacy_host_adapter import LegacyHostAdapter
import p2_auxiliary_isolation as auxiliary

GATEWAY = 'xuanjun-uk-openclaw.service'
COORDINATOR = 'xuanjun-uk-stage1-minimal.service'
ENV = {'PATH':'/usr/bin:/bin', 'LANG':'C'}


class BoundLegacyFiles(LegacyHostAdapter):
    """Reuse only the frozen direct-file restore; never preflight/stop/DB flow."""
    def __init__(self, io, context, legacy_receipt_sha256, forward_guard,
                 cleanup_guard, diagnostics, executable_check):
        need(isinstance(io, HostPhaseFilesystem) and isinstance(diagnostics, BoundedDiagnostics),
             'LEGACY_PROTECTED_ADAPTERS')
        need(all(callable(x) for x in (forward_guard, cleanup_guard, executable_check)),
             'LEGACY_LIVE_CHECKS')
        d.hash_value(legacy_receipt_sha256)
        self.io, self.context = io, copy.deepcopy(context)
        self.receipt_sha = legacy_receipt_sha256
        self.forward, self.cleanup, self.executable = forward_guard, cleanup_guard, executable_check
        self.diagnostics, self.cleaning = diagnostics, False
        self.restored, self.remasked = False, False
        self.restoration = None
        super(BoundLegacyFiles, self).__init__(fs.TRANSACTION, run=self._bounded_run)

    def preflight(self, *args, **kwargs): raise ValueError('EPOCH7_LEGACY_PREFLIGHT_REPLAY_FORBIDDEN')
    def stop_and_inhibit(self, *args, **kwargs): raise ValueError('EPOCH7_LEGACY_STOP_REPLAY_FORBIDDEN')
    def measure_quiescence(self, *args, **kwargs): raise ValueError('EPOCH7_USE_FRESH_BOUNDED_OBSERVER')

    def _guard(self):
        self.io.authority.receipt()
        if self.cleaning:
            need(self.cleanup(self.context, 'preserve_legacy_masks', None) is True,
                 'LEGACY_CLEANUP_AUTHORITY')
        else:
            self.io.require_phase('activate_new_services')
            need(self.forward(self.context, 'activate_new_services') is True,
                 'LEGACY_FORWARD_AUTHORITY')
        return True

    def _authority(self):
        self._guard()
        super(BoundLegacyFiles, self)._authority()

    def _state(self):
        raw, meta = self.io.read_exact(fs.TRANSACTION + '/legacy-units.json')
        need(sha(raw) == self.receipt_sha and meta['mode'] == 0o600 and meta['nlink'] == 1,
             'LEGACY_RETAINED_RECEIPT_CHANGED')
        result = super(BoundLegacyFiles, self)._state()
        need(self.io.read_exact(fs.TRANSACTION + '/legacy-units.json') == (raw, meta),
             'LEGACY_RECEIPT_READ_RACE')
        return result

    def _restored_file(self):
        # No phase guard here: the guard itself reads this owned proof. Every
        # byte and inode is checked directly under the already-held claim.
        self.io.authority.receipt()
        raw, meta = self.io.read_exact(fs.TRANSACTION + '/legacy-units.json')
        need(sha(raw) == self.receipt_sha and
             (meta['uid'], meta['gid'], meta['mode'], meta['nlink']) == (0, 0, 0o600, 1),
             'GATEWAY_RESTORATION_RETAINED_RECEIPT')
        state = decode(raw)
        need(set(state) == {'schema','units','source_before'} and state['schema'] == 1 and
             set(state['units']) == {GATEWAY,COORDINATOR}, 'GATEWAY_RESTORATION_RECEIPT_SCHEMA')
        wanted = state['units'][GATEWAY]
        need(set(wanted) == {'path','backup','sha256','mode','uid','gid','was_active'} and
             wanted['path'] == '/etc/systemd/system/' + GATEWAY and
             wanted['backup'] == fs.TRANSACTION + '/' + GATEWAY + '.backup',
             'GATEWAY_RESTORATION_FIXED_BACKUP')
        rows = {}
        for path in (wanted['backup'], wanted['path'], '/etc/systemd/system/' + COORDINATOR):
            parent, leaf = self.io._parent(path)
            try: rows[path] = self.io._read_at(parent,leaf,allow_mask=True)[0]
            finally: os.close(parent)
        backup, actual = rows[wanted['backup']], rows[wanted['path']]
        need(backup['kind'] == 'FILE' and backup['sha256'] == wanted['sha256'] and
             (backup['uid'],backup['gid'],backup['mode'],backup['nlink']) == (0,0,0o600,1),
             'GATEWAY_RESTORATION_BACKUP_CHANGED')
        need(actual['kind'] == 'FILE' and actual['nlink'] == 1 and
             all(actual[k] == wanted[k] for k in ('sha256','uid','gid','mode')),
             'GATEWAY_RESTORATION_FILE_CHANGED')
        mask = rows['/etc/systemd/system/' + COORDINATOR]
        need(mask['kind'] == 'MASK' and mask['link'] == '/dev/null',
             'GATEWAY_RESTORATION_COORDINATOR_MASK')
        need(self.io.read_exact(fs.TRANSACTION + '/legacy-units.json') == (raw,meta),
             'GATEWAY_RESTORATION_RECEIPT_RACE')
        return actual

    def restoration_evidence(self):
        if self.restoration is None:return None
        need(self.restoration['context_sha256'] == self.context['context_sha256'] and
             self.restoration['legacy_receipt_sha256'] == self.receipt_sha and
             self._restored_file() == self.restoration['observed_after'],
             'GATEWAY_OWN_RESTORATION_DRIFT')
        return copy.deepcopy(self.restoration)

    def _bounded_run(self, argv, **kwargs):
        need(argv == ['/usr/bin/systemctl','daemon-reload'] and kwargs ==
             {'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL,'timeout':45,'check':False},
             'LEGACY_ONLY_DAEMON_RELOAD')
        if not self.cleaning:
            need(self.restored and self.restoration is None, 'GATEWAY_OWN_RESTORE_ONCE')
            self.io.require_phase('activate_new_services')
            self.restoration = {'context_sha256':self.context['context_sha256'],
                'legacy_receipt_sha256':self.receipt_sha,
                'observed_after':self._restored_file(),'reload':None}
        need(self.executable('/usr/bin/systemctl') is True, 'LEGACY_SYSTEMCTL_PIN')
        contract = {'reload': {'phase':'activate_new_services','operation':'daemon_reload',
            'argv':argv,'env':ENV,'cwd':'/','timeout':45,'accepted_returncodes':[0]}}
        result = ExactCommandRunner(contract,self._guard,self.diagnostics).run('reload')
        if not self.cleaning:
            from epoch7_service_roles import argv_hash
            need(result.returncode == 0, 'GATEWAY_RELOAD_SUCCESS_REQUIRED')
            self.restoration['reload'] = {'context_sha256':self.context['context_sha256'],
                'phase':'activate_new_services','operation':'daemon_reload',
                'argv_sha256':argv_hash(argv),'sequence':self.diagnostics.sequence,'returncode':0}
            self.restoration_evidence()
        need(self.executable('/usr/bin/systemctl') is True, 'LEGACY_SYSTEMCTL_AFTER_PIN')
        return result

    def restore_gateway(self, context, diagnostics):
        need(context == self.context and diagnostics is self.diagnostics and
             not self.restored, 'GATEWAY_RESTORE_ONE_ATTEMPT')
        self.restored = True; self.cleaning = False
        self._guard()
        result = super(BoundLegacyFiles, self).restore_legacy_files(gateway_only=True)
        need(result == {'unit_files_restored':True,'services_restarted':False}, 'GATEWAY_RESTORE_RESULT')
        self._verify_files(False)
        return result

    def restore_masks(self, context, diagnostics):
        need(context == self.context and diagnostics is self.diagnostics and
             not self.remasked, 'LEGACY_MASK_ONE_ATTEMPT')
        self.remasked = True; self.cleaning = True
        self._guard()
        result = super(BoundLegacyFiles, self).restore_legacy_files(preserve_mask=True)
        need(result == {'unit_files_restored':True,'services_restarted':False,'masks_preserved':True},
             'LEGACY_MASK_RESULT')
        self._verify_files(True)
        return result

    def _verify_files(self, masked):
        state = self._state()
        for unit, wanted in state['units'].items():
            parent, name = self.io._parent(wanted['path'])
            try:
                actual, raw = self.io._read_at(parent,name,allow_mask=True)
                if masked or unit == COORDINATOR:
                    need(actual['kind'] == 'MASK' and actual['link'] == '/dev/null', 'LEGACY_MASK_READBACK')
                else:
                    need(actual['kind'] == 'FILE' and all(actual[k] == wanted[k] for k in
                         ('sha256','uid','gid','mode')) and actual['nlink'] == 1, 'GATEWAY_FILE_READBACK')
            finally: os.close(parent)


class BoundedContainmentScanner(object):
    """Frozen containment scanner with a fresh independent cleanup budget.

    The reviewed bounded inventory is finite; synchronous kernel calls cannot be
    hard-preempted. No failed forward phase deadline is reused for containment.
    """
    def __init__(self, census, authority):
        from epoch7_host_observer import LinuxProcessCensus
        need(isinstance(census, LinuxProcessCensus), 'CONTAINMENT_REAL_CENSUS_REQUIRED')
        self.census, self.authority = census, authority
        self.deadline, self.scope = None, None

    def begin(self, operation, unit):
        need(operation in ('observe_stopped_before','observe_stopped_after') and
             unit in STOP_UNITS, 'CONTAINMENT_OBSERVATION_SCOPE')
        self.authority.cleanup(operation, unit)
        self.scope = (operation, unit)
        self.deadline = time.monotonic() + 30

    def _check(self):
        need(self.scope is not None and time.monotonic() < self.deadline,
             'CONTAINMENT_SCANNER_DEADLINE')
        self.authority.cleanup(*self.scope)

    def verify_systemd_controller_mount(self):
        self._check()
        # _read is the actual bounded, no-follow census reader, but its clock
        # belongs to this cleanup operation instead of the previous phase.
        self.census.deadline = self.deadline
        self.census.verify_systemd_controller_mount()
        self._check()

    def bounded_file_inventory(self, *args, **kwargs):
        self._check()
        result = self.census.bounded_file_inventory(*args, **kwargs)
        self._check()
        return result


class HostContainment(object):
    """All52 outer cleanup calls stay independent; no failed-forward gate reuse."""
    def __init__(self, io, context, core, runtime, legacy, cleanup_guard, observer):
        need(isinstance(io, HostPhaseFilesystem) and isinstance(legacy, BoundLegacyFiles)
             and callable(cleanup_guard), 'CONTAINMENT_CONCRETE_ADAPTERS')
        self.io, self.context = io, copy.deepcopy(context)
        self.core, self.runtime, self.legacy = core, runtime, legacy
        self.guard, self.observer = cleanup_guard, observer
        self.attempted = set()

    def _owner_masks(self):
        # Validate BOTH current files before replacing either. The only permitted
        # regular bytes are exact reviewed replacements for originally masked units.
        for path in sorted(d.OWNER_MASKS):
            need(self.core.snapshot['targets'][path]['kind'] == 'MASK', 'OWNER_ORIGINAL_MASK')
            parent, leaf = self.io._parent(path)
            try:
                row, raw = self.io._read_at(parent, leaf, allow_mask=True)
                if row['kind'] == 'FILE':
                    wanted = self.core.candidate['targets'][path]
                    need(all(row[k] == wanted[k] for k in ('sha256','uid','gid','mode')) and
                         row['nlink'] == 1, 'OWNER_UNEXPECTED_TARGET_HOLD')
            finally: os.close(parent)
        result = {}
        for path in sorted(d.OWNER_MASKS):
            self.io.authority.receipt()
            auxiliary.restore_mask(path)
            parent, leaf = self.io._parent(path)
            try:
                row, raw = self.io._read_at(parent,leaf,allow_mask=True)
                need(row['kind'] == 'MASK', 'OWNER_MASK_PUBLICATION_UNKNOWN')
                result[path] = row
            finally: os.close(parent)
        # The following independent preserve_legacy_masks operation performs
        # the bounded daemon-reload. No failure here suppresses that operation.
        return result

    def run(self, context, operation, unit, diagnostics):
        need(context == self.context and operation in CLEANUP_METHODS and
             (operation,unit) not in self.attempted, 'CONTAINMENT_FIXED_ONCE')
        need(unit in STOP_UNITS if operation in ('stop_unit','observe_stopped_before','observe_stopped_after')
             else unit is None, 'CONTAINMENT_UNIT_SCOPE')
        self.attempted.add((operation,unit))
        self.io.authority.receipt()
        value = self.io.authority.validate_outer(self.io.read_journal('epoch7-recovery-sequence-successor-a5602f7e70e22edba.json')['data'])
        need(value['state'].get('admission') == 'ADMITTED', 'CONTAINMENT_ADMITTED_CLAIM')
        need(self.guard(context,operation,unit) is True, 'CONTAINMENT_LIVE_AUTHORITY')
        label = operation if unit is None else operation + ':' + unit
        if operation == 'fence':
            actual = self.core.store.read()
            allowed = [self.core.snapshot['activation'], self.core.candidate['activation']]
            need(any(all(actual[k] == row[k] for k in actual if k != 'state') for row in allowed) and
                 actual['state'] in ('PREPARED','QUIESCED','ACTIVE'), 'FENCE_IDENTITY_SCOPE')
            result = self.core.store.fence(actual['epoch'],actual['instance'])
            need(result['state'] == 'PREPARED' and result['epoch'] == actual['epoch'] + 1 and
                 all(result[k] == actual[k] for k in actual if k not in ('state','epoch')),
                 'FENCE_READBACK')
            self.core.current = result
        elif operation == 'stop_unit':
            result = check_observation(self.runtime.stop_unit(context,unit,diagnostics),context,label)
        elif operation in ('observe_stopped_before','observe_stopped_after'):
            # Runtime uses the frozen ServiceContainment.observe_one with the
            # bounded systemctl proxy and real systemd/cgroup scanner.
            if isinstance(self.runtime.containment_scanner, BoundedContainmentScanner):
                self.runtime.containment_scanner.begin(operation, unit)
            result = check_observation(self.runtime.observe_stopped(context,operation,unit,diagnostics),context,label)
        elif operation == 'preserve_boot_inhibition':
            result = check_observation(self.runtime.preserve_boot_inhibition(context,diagnostics),context,operation)
        elif operation == 'restore_exact_owner_masks': result = self._owner_masks()
        elif operation == 'preserve_legacy_masks': result = self.legacy.restore_masks(context,diagnostics)
        elif operation == 'restore_owned_epoch7_sandbox':
            result = check_observation(self.runtime.restore_owned_epoch7_sandbox(context,diagnostics),context,operation)
        elif operation == 'verify_legacy_exclusion': result = self.observer.legacy_exclusion()
        elif operation == 'verify_retained_tls':
            self.observer.begin_guard(time.monotonic()+30)
            result = self.observer.tls_contents()
            need(result == {k:self.core.snapshot['tls'][k] for k in
                 ('certificate_sha256','tree_fingerprint_sha256')}, 'CONTAINMENT_RETAINED_TLS')
        else: raise ValueError('EPOCH7_CONTAINMENT_UNIMPLEMENTED_OPERATION')
        need(type(result) is dict and bool(result), 'CONTAINMENT_EVIDENCE_REQUIRED')
        return observation(context,label,d.digest(result))


def services_with_gateway(legacy, runtime):
    def activate(context, diagnostics):
        legacy.restore_gateway(context,diagnostics)
        return runtime.activate_new_services(context,diagnostics)
    return activate
