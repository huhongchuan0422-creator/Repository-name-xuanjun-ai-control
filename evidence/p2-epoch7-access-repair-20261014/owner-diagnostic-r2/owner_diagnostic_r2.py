#!/usr/bin/env python3
"""LOCAL REVIEW CANDIDATE. No permission or production admission is conveyed.

The Owner must independently authenticate this wrapper/interpreter and approve
its exact effects before manual execution. No CLI option changes source pins,
host, directories, tests, network destinations, or recovery authority.
"""
import argparse
import contextlib
import hashlib
import importlib
import json
import os
import re
import signal
import socket
import sys
import types
import unittest
import urllib.request

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
BASE = '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/complete-install-candidate-38503014520'
KIT = BASE + '/epoch7-recovery-candidate-r2'
OWNERS = ((0, 0),)
# Exact source and archive publications were independently read back by the parent.
READY = True
SOURCE = '4798cda235b24b31a18b57d3957fbc0d396d634b'
TREE = 'f050e9e6810decb7a4f62a14f3a5679908451c1f'
PUBLICATION = '965c0f8bd7e5145dc353a9145388c733e0660ab5'
REPOSITORY = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
PREFIX = 'https://raw.githubusercontent.com/' + REPOSITORY + '/'
ARCHIVE_PATH = 'evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-4798cda2.tar.gz'
ARCHIVE_URL = PREFIX + PUBLICATION + '/' + ARCHIVE_PATH
EXTRACTOR_URL = PREFIX + SOURCE + '/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/tools/extract_epoch7_kit.py'
ARCHIVE_SHA = '7c67ef5e1e2d756898b982bcce625fd9168e4c3d93c3ed2153d4ed8fd8e37d71'
EXTRACTOR_SHA = 'd8f1942bc82bb001d8282192e87b9b71e3b89c2f374c6c69d49589b025293b87'
ENTRY_SHA = '999803b505bbebdef8a2f3303954f8e773cdf6bb10f9c2855563d36b1f759dd2'
MANIFEST_SHA = '560d8bf9bae026ffd64b4b0fc43e87216a177070f2a0c948489c884a1296c8b3'
ARCHIVE_SIZE = 1009595
EXTRACTOR_SIZE = 9582
KIT_SOURCE_FILES = 245
PREREQUISITE_MODULE = 'epoch7_owner_prerequisite'
PREREQUISITE_SOURCE = 'helpers/epoch7_owner_prerequisite.py'
UK_TEST = 'tests/uk_exact_uid_acl/test_epoch7_exact_access_uk.py'
UK_TEST_SHA = '8984cdc5a77411051fb9c2d9d81aefcd8c662e206c14f25dfa90c349f6512635'
UK_ALIAS = 'test_epoch7_exact_access_uk'
UK_CASE = UK_ALIAS + '.ActualFDTests.test_actual_fd_acl_changes_only_two_named_access_sets'
SHA = re.compile(r'^[0-9a-f]{64}$')
ALARM_CLEANUP_INTERVAL = 1.0


class DiagnosticHold(ValueError):
    pass


class StageTimeout(KeyboardInterrupt):
    """Escape unittest's BaseException-to-error conversion."""
    pass


def need(value, code):
    if not value:
        raise DiagnosticHold(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def host_boundary():
    need(os.geteuid() == 0 and os.getegid() == 0 and
         socket.gethostname().split('.')[0] == HOST, 'FIXED_ROOT_HOST_REQUIRED')
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,
         'ISOLATED_NO_SITE_NO_BYTECODE_REQUIRED')
    need(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'EXISTING_TIMER_REFUSED')


@contextlib.contextmanager
def bounded_stage(seconds):
    """Only bootstrap/test phases; never leave an alarm around the probe."""
    need(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'EXISTING_TIMER_REFUSED')
    previous = signal.getsignal(signal.SIGALRM)
    def expired(unused_signum, unused_frame):
        raise StageTimeout()
    signal.signal(signal.SIGALRM, expired)
    primary = None
    try:
        # Repeated delivery remains armed during owned-context unwinding. A
        # slow Python cleanup cannot silently continue after the first expiry.
        signal.setitimer(signal.ITIMER_REAL, seconds, ALARM_CLEANUP_INTERVAL)
        yield
    except BaseException as error:
        primary = error
        raise
    finally:
        failed = False
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
        except BaseException:
            failed = True
        try:
            signal.signal(signal.SIGALRM, previous)
        except BaseException:
            failed = True
        if failed:
            if primary is not None:
                primary.diagnostic_timer_cleanup_failed = True
            else:
                raise DiagnosticHold('TIMER_CLEANUP_FAILED')


@contextlib.contextmanager
def preserve_cleanup(manager, label):
    """Preserve the primary outcome if a known context's cleanup also fails."""
    value = manager.__enter__()
    try:
        yield value
    except BaseException as primary:
        info = sys.exc_info()
        try:
            manager.__exit__(*info)
        except BaseException:
            setattr(primary, 'diagnostic_' + label + '_failed', True)
        raise
    else:
        manager.__exit__(None, None, None)


def bounded_reverify(entry):
    try:
        with bounded_stage(60):
            entry.verify_kit(KIT, MANIFEST_SHA)
    except BaseException as error:
        error.diagnostic_reverification_failed = True
        raise


@contextlib.contextmanager
def reverify_after(entry):
    try:
        yield
    except BaseException as primary:
        try:
            bounded_reverify(entry)
        except BaseException:
            primary.diagnostic_reverification_failed = True
        raise
    else:
        bounded_reverify(entry)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *unused, **unused_keywords):
        raise DiagnosticHold('DOWNLOAD_REDIRECT_REFUSED')


def download(url, size, digest):
    """Two fixed public HTTPS objects, no proxy, credentials, redirect or retry."""
    need((url, size, digest) in ((EXTRACTOR_URL, EXTRACTOR_SIZE, EXTRACTOR_SHA),
                                (ARCHIVE_URL, ARCHIVE_SIZE, ARCHIVE_SHA)), 'DOWNLOAD_SCOPE')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(url, headers={'Accept-Encoding': 'identity'})
    with bounded_stage(30):
        with opener.open(request, timeout=10) as response:
            need(response.status == 200 and response.geturl() == url, 'DOWNLOAD_RESPONSE')
            need(response.headers.get('Content-Encoding', 'identity') == 'identity', 'DOWNLOAD_ENCODING')
            length = response.headers.get('Content-Length')
            need(length is None or length == str(size), 'DOWNLOAD_LENGTH')
            data = response.read(size + 1)
    need(type(data) is bytes and len(data) == size and sha(data) == digest, 'DOWNLOAD_HASH')
    return data


def authenticated_module(raw, digest, name, filename):
    need(type(raw) is bytes and sha(raw) == digest, 'BOOTSTRAP_HASH')
    module = types.ModuleType(name)
    module.__file__ = filename
    exec(compile(raw, filename, 'exec'), module.__dict__)
    return module


def absent(tree, leaf):
    try:
        os.stat(leaf, dir_fd=tree.fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise DiagnosticHold('OUTPUT_OR_NONCE_ALREADY_EXISTS')


def check_outputs(extractor, identifier, nonce):
    with extractor.ProtectedDirectory(BASE, OWNERS) as tree:
        for name in ('epoch7-observation-' + identifier + '.private.json',
                     'epoch7-diagnostic-' + identifier + '.private.json'):
            absent(tree, name)
        tree.check()
    if nonce is not None:
        stem = 'xj-p2-proof-' + nonce
        with extractor.ProtectedDirectory('/run', OWNERS) as tree:
            absent(tree, stem)
            tree.check()
        with extractor.ProtectedDirectory('/run/systemd/system', OWNERS) as tree:
            for suffix in ('.socket', '.service', '-broker.service', '-dashboard.service',
                           '-callback.service', '-native.service'):
                absent(tree, stem + suffix)
            tree.check()


def stage_kit(extractor):
    with extractor.ProtectedDirectory(BASE, OWNERS) as tree:
        try:
            os.stat('epoch7-recovery-candidate-r2', dir_fd=tree.fd, follow_symlinks=False)
        except FileNotFoundError:
            present = False
        else:
            present = True
        tree.check()
    if not present:
        archive = download(ARCHIVE_URL, ARCHIVE_SIZE, ARCHIVE_SHA)
        with bounded_stage(60):
            extractor.extract(archive, KIT, ARCHIVE_SHA, ENTRY_SHA, MANIFEST_SHA)
    # Reuse the frozen anchored regular-file reader. A symlink, partial tree,
    # extra file or mismatched old candidate is rejected, never repaired.
    with bounded_stage(60):
        raw = extractor.read_archive(KIT + '/epoch7_recovery_entry.py', OWNERS)
        need(len(raw) <= 1024 * 1024, 'ENTRY_BOUND')
        entry = authenticated_module(raw, ENTRY_SHA, 'reviewed_epoch7_entry', KIT + '/epoch7_recovery_entry.py')
        kit = entry.verify_kit(KIT, MANIFEST_SHA)
    need(kit.manifest['kit_source_commit'] == SOURCE and kit.manifest['kit_source_tree'] == TREE and
         len(kit.cache) == KIT_SOURCE_FILES, 'EXACT_SOURCE_KIT_REQUIRED')
    return entry, kit, 'VERIFIED_EXISTING' if present else 'EXTRACTED_AND_VERIFIED'


class SilentResult(unittest.TestResult):
    """No exception text, host data, fixture pathname or traceback output."""
    def addError(self, test, error):
        self.errors.append((test.id(), 'FIXTURE_ERROR'))
    def addFailure(self, test, error):
        self.failures.append((test.id(), 'FIXTURE_ASSERTION_FAILED'))
    def addSkip(self, test, reason):
        self.skipped.append((test.id(), 'UID_MAPPING_UNAVAILABLE'))


def exact_uid_test(entry, kit):
    row = kit.manifest['test_suites']['uk_exact_uid_acl']
    need(row['tests'] == [UK_TEST] and row['imports'].get(UK_ALIAS) == UK_TEST and
         sha(kit.cache[UK_TEST]) == UK_TEST_SHA, 'EXACT_UK_TEST_REQUIRED')
    result = SilentResult()
    with reverify_after(entry):
        with bounded_stage(60):
            with preserve_cleanup(kit.test_workspace(), 'workspace_cleanup') as workspace:
                with preserve_cleanup(workspace.imports(row['imports']), 'import_cleanup'):
                    module = importlib.import_module(UK_ALIAS)
                    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
                    cases = list(suite)
                    need(len(cases) == 1 and cases[0].id() == UK_CASE, 'EXACT_ONE_TEST_REQUIRED')
                    suite.run(result)
    passed = (result.testsRun == 1 and result.wasSuccessful() and not result.skipped and
              not result.expectedFailures and not result.unexpectedSuccesses)
    return {'case': UK_CASE, 'source_sha256': UK_TEST_SHA, 'tests': result.testsRun,
            'errors': len(result.errors), 'failures': len(result.failures), 'skipped': len(result.skipped),
            'state': 'PASS_OBSERVED_FIXTURE_ONLY' if passed else 'HOLD', 'success': passed,
            'scope': 'TWO_DISPOSABLE_TARGET_ACLS_NOT_PRODUCTION_DAC_ACCEPTANCE'}


def public_observation(value):
    """Allow only fixed status values/digests from the already bounded entry."""
    allowed = {'operation': ('observe-only', 'observe-and-probe'),
        'kind': ('EPOCH7_OBSERVATION_ONLY_UNREVIEWED', 'EPOCH7_OBSERVATION_ONLY_HOLD'),
        'probe_stage': ('NOT_REQUESTED', 'HOLD_NOT_EXECUTED', 'HOLD_AFTER_ATTEMPT', 'RESULT_RECORDED'),
        'independent_acceptance': ('PENDING',), 'install_admission': ('NOT_GRANTED',),
        'production_resume': ('NOT_EXECUTED',)}
    result = {}
    for key, choices in allowed.items():
        need(value.get(key) in choices, 'OBSERVATION_STATUS')
        result[key] = value[key]
    for key in ('private_file_sha256', 'snapshot_sha256', 'policy_sha256', 'kit_manifest_sha256'):
        data = value.get(key)
        need((data is None and key in ('snapshot_sha256', 'policy_sha256')) or
             (type(data) is str and SHA.fullmatch(data)), 'OBSERVATION_DIGEST')
        result[key] = data
    need(result['kit_manifest_sha256'] == MANIFEST_SHA, 'OBSERVATION_KIT')
    for key in ('success', 'probe_observations_complete'):
        need(type(value.get(key)) is bool, 'OBSERVATION_BOOLEAN')
        result[key] = value[key]
    return result


def write_receipt(extractor, entry, identifier, result):
    raw = (json.dumps(result, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False) + '\n').encode('ascii')
    need(len(raw) <= 16384, 'DIAGNOSTIC_RECEIPT_BOUND')
    leaf = 'epoch7-diagnostic-' + identifier + '.private.json'
    with extractor.ProtectedDirectory(BASE, OWNERS) as tree:
        fd = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=tree.fd)
        try:
            offset = 0
            while offset < len(raw):
                count = os.write(fd, raw[offset:])
                need(count > 0, 'DIAGNOSTIC_RECEIPT_SHORT_WRITE')
                offset += count
            os.fchmod(fd, 0o600)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(tree.fd)
        tree.check()
    with entry.DescriptorTree(BASE) as tree:
        need(tree.read(leaf, 16384, private=True) == raw, 'DIAGNOSTIC_RECEIPT_READBACK')
        tree.recheck()
    return sha(raw)


def publication_gate():
    need(READY is True, 'IMMUTABLE_R2_PUBLICATION_NOT_READY')
    for value in (SOURCE,TREE,PUBLICATION):
        need(type(value) is str and re.fullmatch(r'[0-9a-f]{40}',value), 'IMMUTABLE_GIT_PIN')
    for value in (ARCHIVE_SHA,EXTRACTOR_SHA,ENTRY_SHA,MANIFEST_SHA):
        need(type(value) is str and SHA.fullmatch(value), 'IMMUTABLE_SOURCE_PIN')
    need(type(ARCHIVE_PATH) is str and re.fullmatch(
        r'evidence/p2-epoch7-access-repair-20261014/artifacts/[A-Za-z0-9_.-]+\.tar\.gz',ARCHIVE_PATH), 'IMMUTABLE_ARCHIVE_PATH')
    need(ARCHIVE_URL == PREFIX+PUBLICATION+'/'+ARCHIVE_PATH and
         EXTRACTOR_URL == PREFIX+SOURCE+'/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/tools/extract_epoch7_kit.py',
         'IMMUTABLE_DOWNLOAD_SCOPE')
    need(type(ARCHIVE_SIZE) is int and 0<ARCHIVE_SIZE<=32*1024*1024 and
         type(EXTRACTOR_SIZE) is int and 0<EXTRACTOR_SIZE<=1024*1024 and
         type(KIT_SOURCE_FILES) is int and 1<=KIT_SOURCE_FILES<=1024, 'IMMUTABLE_SIZE_PINS')


def prerequisite_summary(value):
    need(type(value) is dict and value.get('kind')=='EPOCH7_OWNER_PREREQUISITE' and
         value.get('stage') in ('HOLD','PARTIAL_HOLD','COMPLETE_PREREQUISITES_ONLY') and
         value.get('automatic_retry') is False and value.get('permission_widening_rollback') is False and
         value.get('production_admission')=='NOT_GRANTED' and
         value.get('service_actions')==value.get('database_writes')==0,'PREREQUISITE_RESULT_SCHEMA')
    targets=[ '/home/xuanjun_dev/.openclaw/'+suffix for suffix in ('bin','tools','tools/node-v24.21.0') ]
    need(value.get('authorized_targets')==targets and type(value.get('attempted')) is list and
         value['attempted']==targets[:len(value['attempted'])] and
         type(value.get('completed')) is list and value['completed']==targets[:len(value['completed'])] and
         len(value['completed'])<=len(value['attempted'])<=3,'PREREQUISITE_RESULT_TARGETS')
    need(value['stage']!='COMPLETE_PREREQUISITES_ONLY' or value['completed']==value['attempted']==targets,
         'PREREQUISITE_COMPLETE_TARGET_SET')
    summary={key:value[key] for key in ('kind','stage','authorized_targets','attempted','completed',
        'automatic_retry','permission_widening_rollback','production_admission','service_actions','database_writes')}
    summary['evidence_sha256']=sha((json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,
        allow_nan=False)+'\n').encode('ascii'))
    if 'failure_code' in value:
        need(type(value['failure_code']) is str and re.fullmatch(r'[A-Z0-9_]{1,128}',value['failure_code']), 'PREREQUISITE_FAILURE_LABEL')
        summary['failure_code']=value['failure_code']
    summary['cleanup_failed']=value.get('cleanup_failed') is True
    # Preserve fixed metadata/proof fields in the existing private diagnostic
    # receipt. These contain only fixed paths, stat fields and digests.
    for key in ('before','after','entry_before','entry_after','node_before','node_after','guard_before','guard_after'):
        if key in value:summary[key]=value[key]
    return summary



def prerequisite(entry,kit,acknowledged,result_sink=None):
    need(acknowledged is True,'EXPLICIT_THREE_DIRECTORY_ACK_REQUIRED')
    need(kit.manifest['modules'].get(PREREQUISITE_MODULE)==PREREQUISITE_SOURCE,
         'AUTHENTICATED_PREREQUISITE_MODULE_REQUIRED')
    # Store validated evidence before either owned context can fail on exit.
    # No caller-controlled callbacks, modes or paths reach the helper.
    with reverify_after(entry):
        with kit.imports():
            module=importlib.import_module(PREREQUISITE_MODULE)
            if result_sink is not None:result_sink['prerequisite_outcome']='UNKNOWN_AFTER_CALL'
            value=module.apply_reviewed_prerequisites(operator_acknowledged=True)
            summary=prerequisite_summary(value)
            if result_sink is not None:
                result_sink['prerequisite']=summary
                result_sink.pop('prerequisite_outcome',None)
    return summary


def run(identifier, nonce=None, execute_reviewed_diagnostic=False, execute_reviewed_probe=False,
        execute_reviewed_prerequisites=False):
    result={'schema':1,'kind':'OWNER_R2_PREREQUISITE_DIAGNOSTIC','stage':'PRECONDITIONS','success':False,
        'kit_source_commit':SOURCE,'kit_manifest_sha256':MANIFEST_SHA,'install_admission':'NOT_GRANTED',
        'production_resume':'NOT_EXECUTED','independent_acceptance':'PENDING','approval_obtained_by_wrapper':False}
    extractor=entry=None
    try:
        publication_gate()
        need(execute_reviewed_diagnostic is True,'EXPLICIT_DIAGNOSTIC_ACK_REQUIRED')
        need(execute_reviewed_prerequisites is True,'EXPLICIT_THREE_DIRECTORY_ACK_REQUIRED')
        need(type(identifier) is str and re.fullmatch(r'[0-9a-f]{16}',identifier),'OBSERVATION_ID')
        need(type(execute_reviewed_probe) is bool and
             ((nonce is None and not execute_reviewed_probe) or
              (type(nonce) is str and re.fullmatch(r'[0-9a-f]{32}',nonce) and execute_reviewed_probe)),
             'EXPLICIT_PROBE_SCOPE_REQUIRED')
        host_boundary();result['stage']='BOOTSTRAP_SOURCE'
        extractor=authenticated_module(download(EXTRACTOR_URL,EXTRACTOR_SIZE,EXTRACTOR_SHA),
            EXTRACTOR_SHA,'reviewed_epoch7_extractor','<authenticated-epoch7-extractor>')
        check_outputs(extractor,identifier,nonce);result['stage']='KIT_STAGE'
        entry,kit,state=stage_kit(extractor);result['kit_staging']=state
        result['stage']='EXACT_UID_FIXTURE';acl=exact_uid_test(entry,kit);result['exact_uid_acl']=acl
        need(acl['success'] is True,'EXACT_UID_FIXTURE_HOLD')
        result['stage']='APPROVED_THREE_DIRECTORY_PREREQUISITE'
        result['prerequisite']=prerequisite(entry,kit,execute_reviewed_prerequisites,result)
        need(result['prerequisite']['stage']=='COMPLETE_PREREQUISITES_ONLY','PREREQUISITE_HOLD')
        # Only this success path reaches the existing observation/probe API.
        # The helper has closed both locks and cleared its own alarm. Observation
        # reacquires its own locks and applies its unchanged complete admission.
        result['probe_requested']=execute_reviewed_probe;result['stage']='OBSERVATION_AND_OPTIONAL_PROBE'
        output=BASE+'/epoch7-observation-'+identifier+'.private.json'
        with reverify_after(entry):
            observed=kit.observe(output,nonce if execute_reviewed_probe else None,execute_reviewed_probe)
            result['observation']=public_observation(observed)
        result['success']=result['observation']['success']
        result['stage']='DIAGNOSTIC_RECORDED' if result['success'] else 'HOLD_RECORDED'
    except (KeyboardInterrupt,SystemExit) as error:
        result.update(success=False,failure_code='STAGE_DEADLINE' if isinstance(error,StageTimeout) else 'INTERRUPTED',
            outcome='POTENTIALLY_PARTIAL_NO_AUTOMATIC_RETRY');cleanup_failures(result,error)
    except Exception as error:
        code=error.args[0] if type(error) is DiagnosticHold and len(error.args)==1 else 'BOUNDARY_OR_DEPENDENCY_FAILED'
        if type(code) is not str or not re.fullmatch(r'[A-Z0-9_]{1,96}',code):code='BOUNDARY_OR_DEPENDENCY_FAILED'
        result.update(success=False,failure_code=code,outcome='POTENTIALLY_PARTIAL_NO_AUTOMATIC_RETRY');cleanup_failures(result,error)
    # One existing diagnostic receipt path, including partial chmod outcomes.
    # Failure to persist is secondary and never starts another attempt.
    if entry is not None:
        try:
            with bounded_stage(30):receipt=write_receipt(extractor,entry,identifier,result)
            result['diagnostic_receipt_sha256']=receipt
        except BaseException:
            result['success']=False;result['diagnostic_receipt']='FAILED_OR_INTERRUPTED'
    return result


def cleanup_failures(result, error):
    for label in ('reverification', 'workspace_cleanup', 'import_cleanup', 'timer_cleanup'):
        if getattr(error, 'diagnostic_' + label + '_failed', False) is True:
            result[label] = 'FAILED_OR_INTERRUPTED'


class ScopeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse otherwise repeats arbitrary unrecognized argument contents.
        raise DiagnosticHold('CLI_SCOPE')


def main(argv=None):
    parser = ScopeParser(description=__doc__)
    parser.add_argument('--observation-id', required=True)
    parser.add_argument('--nonce')
    parser.add_argument('--execute-reviewed-diagnostic', action='store_true')
    parser.add_argument('--execute-reviewed-probe', action='store_true')
    parser.add_argument('--execute-reviewed-prerequisites', action='store_true')
    try:
        args = parser.parse_args(argv)
    except DiagnosticHold:
        result = {'schema': 1, 'kind': 'OWNER_R2_PREREQUISITE_DIAGNOSTIC',
                  'stage': 'CLI', 'failure_code': 'CLI_SCOPE', 'success': False,
                  'install_admission': 'NOT_GRANTED', 'production_resume': 'NOT_EXECUTED'}
    else:
        result = run(args.observation_id, args.nonce, args.execute_reviewed_diagnostic, args.execute_reviewed_probe, args.execute_reviewed_prerequisites)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['success'] else 2


if __name__ == '__main__':
    sys.exit(main())
