"""Read-only target-observation collector for the original workflow-request.

Emits the six fixed whole-workflow stage facts from real target environment
bytes so the operator can feed pr122_customer_release.py workflow-request.
Grants nothing: no permission, signature, enrollment, credential value or
customer record is read or emitted, and no install state is mutated. The only
filesystem effect is a bounded temporary venv enumeration (the same fixed
command the original protected_rebuild runs) under /var/lib, read by the
original runtime._runtime_tree reader and removed afterwards. Unproven
sections stay None; the request document lists them as missing inputs.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from scripts.pr122_customer_core import Denied, canonical, digest
from scripts import pr122_customer_release as release
from scripts import pr122_customer_workflow as workflow
from scripts import pr122_customer_workflow_request as request
from scripts import pr122_customer_workflow_apply as customer
from scripts import pr122_customer_workflow_operations as operations
from scripts import pr122_customer_runtime as runtime
from scripts import pr122_customer_channel_upgrade as channel
from scripts.pr122_account_admission import approved_account_prepare as account
from scripts.pr122_account_admission import domestic_bootstrap as bootstrap

UNPROVEN = (OSError, KeyError, ValueError, RuntimeError, subprocess.SubprocessError)
WHEEL_LIMIT = 15000000


def _section(produce, name, reports):
    try:
        return produce()
    except UNPROVEN as error:
        label = str(error) if isinstance(error, Denied) else type(error).__name__
        reports.append({'section': name, 'state': 'HOLD', 'reason': label})
        return None


def _sha_file(path):
    path = Path(path)
    if not path.is_file(): return None
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        return digest(stream.read(8192))


def live_platform(account_module):
    return account_module.OS().platform_preconditions()


def temp_venv_tree(runtime_module):
    root = Path(tempfile.mkdtemp(prefix='pr122-runtime-closure-', dir='/var/lib'))
    os.chmod(root, 0o700)
    try:
        subprocess.run([str(runtime_module.FIXED_INTERPRETER), '-I', '-B', '-S', '-m', 'venv',
                        '--copies', '--without-pip', str(root / 'venv')],
                       check=True, timeout=45, cwd='/',
                       env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'PYTHONDONTWRITEBYTECODE': '1'},
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return runtime_module._runtime_tree(root)
    finally:
        shutil.rmtree(root)


def stdlib_trees(runtime_module):
    out = {}
    for root in ('/usr/lib/python3.11', '/usr/lib64/python3.11'):
        if not os.path.isdir(root): continue
        runtime_module._root_chain(root)
        members = {}
        for base, dirs, names in os.walk(root, followlinks=False):
            for name in dirs: runtime_module._root_chain(Path(base) / name)
            for name in names:
                p = Path(base) / name
                members[str(p.relative_to(root))] = digest(runtime_module._protected_bytes(p))
        out[root] = members
    return out or None


def native_files(runtime_module):
    resolved = os.path.realpath(str(runtime_module.FIXED_INTERPRETER))
    result = subprocess.run(['/usr/bin/ldd', resolved], check=True, timeout=30,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
    out = {}
    for line in result.stdout.decode('utf-8', 'replace').splitlines():
        parts = line.split()
        if len(parts) < 3 or not parts[2].startswith('/'): continue
        path = Path(parts[2])
        if not any(str(path).startswith(x) for x in ('/usr/lib/', '/usr/lib64/', '/lib/', '/lib64/')):
            continue
        out[str(path)] = digest(runtime_module._protected_bytes(path))
    return out or None


def wheels_present(directory, runtime_module):
    for name, sha in runtime_module.WHEELS.items():
        with os.fdopen(os.open(Path(directory) / name, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
            raw = stream.read(WHEEL_LIMIT + 1)
        if len(raw) > WHEEL_LIMIT or digest(raw) != sha: raise Denied('VENDOR_WHEEL_PIN')
    return True


def collect(folder, *, wheel_directory='/root/pr122-runtime-wheels', artifact_zip_sha256=None,
            artifact_id=None, ci_run_id=None, release_module=None, runtime_module=None,
            account_module=None, bootstrap_module=None, channel_module=None,
            probe_receipt=None, platform=None, venv_tree=None, stdlib=None, native=None,
            reports=None):
    release_module = release_module or release
    runtime_module = runtime_module or runtime
    account_module = account_module or account
    bootstrap_module = bootstrap_module or bootstrap
    channel_module = channel_module or channel
    probe_receipt = Path(probe_receipt) if probe_receipt is not None else operations.PROBE_RECEIPT
    reports = [] if reports is None else reports
    observations = {'static_plan': None, 'inputs': None, 'artifact': None,
                    'adopt_receipts': {stage: None for stage in workflow.STAGES},
                    'recovery_actions': {stage: sorted(workflow.RECOVERY[stage]) for stage in workflow.STAGES}}
    plan_value = _section(lambda: release_module.plan(folder), 'static_plan', reports)
    bundle = _section(lambda: release_module.source(folder), 'source', reports)
    if plan_value is None or bundle is None: return observations
    static = {key: value for key, value in plan_value.items() if key not in customer.DYNAMIC_FIELDS}
    observations['static_plan'] = static
    manifest, raw, files = bundle
    adoption = observations['adopt_receipts']

    def probe():
        path = Path(probe_receipt)
        if not path.is_file(): return None
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
            return digest(stream.read(10_000_001))

    probe_sha = _section(probe, 'probe', reports)
    adoption['PROBE'] = probe_sha

    def account_input():
        value = platform() if platform is not None else live_platform(account_module)
        return {'account': account_module.ACCOUNT,
                'argv_sha256': digest(canonical(list(account_module.PROPOSED_ARGV))),
                'platform_sha256': digest(canonical(value))}

    adoption['ACCOUNT'] = _section(
        lambda: _sha_file(Path(account_module.ACCOUNT_RECEIPT) / 'ACCOUNT_CREATED_VERIFIED_NO_RETRY.json'),
        'account-adopt', reports)

    def runtime_input():
        _ = wheels_present(wheel_directory, runtime_module)
        tree = venv_tree() if venv_tree is not None else temp_venv_tree(runtime_module)
        members = stdlib() if stdlib is not None else stdlib_trees(runtime_module)
        natives = native() if native is not None else native_files(runtime_module)
        template = {'schema': 1, 'host': runtime_module.FIXED_HOST,
                    'source_commit': static['source_commit'],
                    'runtime_module_sha256': digest(files[request.IMPLEMENTATIONS['RUNTIME']]),
                    'wheel_directory': str(wheel_directory),
                    'interpreter_sha256': runtime_module.INTERPRETER_SHA256,
                    'stdlib_trees': members, 'native_files': natives,
                    'abi': {'python': '3.11', 'machine': 'x86_64', 'glibc_min': '2.34'},
                    'expected_venv_tree': tree, 'account_uid': None, 'account_gid': None}
        return {'runtime_template': template, 'account_binding': 'VERIFIED_ACCOUNT_CHECKPOINT'}

    def policy_input():
        control = bootstrap_module.CONTROL
        return {'transaction': control.name,
                'plan_sha256': bootstrap_module.sha(bootstrap_module.read(control / 'plan.json', 0o400)),
                'old_wrapper_sha256': bootstrap_module.sha(bootstrap_module.read(control / 'old-wrapper', 0o400)),
                'old_policy_sha256': bootstrap_module.sha(bootstrap_module.read(control / 'old-sudoers', 0o400))}

    adoption['POLICY_RESTORE'] = _section(
        lambda: _sha_file(bootstrap_module.CONTROL / 'ROLLED_BACK.json'), 'policy-adopt', reports)

    def channel_input():
        if artifact_zip_sha256 is None: raise ValueError('ARTIFACT_ZIP_REQUIRED')
        value = channel_module.plan(ignore_transaction=True, expected_zip_sha256=artifact_zip_sha256)
        return {'plan_sha256': channel_module.sha(channel_module.canonical(value)),
                'zip_sha256': artifact_zip_sha256}

    producers = {'PROBE': lambda: {'receipt_sha256': probe_sha}, 'ACCOUNT': account_input,
                 'RUNTIME': runtime_input, 'POLICY_RESTORE': policy_input,
                 'CHANNEL_REBIND': channel_input,
                 'CUSTOMER_APPLY': lambda: {'static_plan': json.loads(json.dumps(static))}}
    stages = {}
    for stage in workflow.STAGES:
        stages[stage] = _section(producers[stage], stage.lower(), reports)
    observations['inputs'] = {'schema': 1, 'stages': stages}
    if all(value is not None for value in (artifact_zip_sha256, artifact_id, ci_run_id)):
        artifact = {key: static[key] for key in
                    ('source_commit', 'source_tree', 'manifest_sha256', 'artifact_tar_sha256')}
        artifact.update(artifact_zip_sha256=artifact_zip_sha256, artifact_id=artifact_id, ci_run_id=ci_run_id)
        observations['artifact'] = artifact
    return observations


def main():
    os.umask(0o022)
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', required=True)
    ap.add_argument('--wheel-directory', default='/root/pr122-runtime-wheels')
    ap.add_argument('--artifact-zip')
    ap.add_argument('--artifact-id', type=int)
    ap.add_argument('--ci-run', type=int)
    a = ap.parse_args()
    reports = []
    value = collect(a.source, wheel_directory=a.wheel_directory, artifact_zip_sha256=a.artifact_zip,
                    artifact_id=a.artifact_id, ci_run_id=a.ci_run, reports=reports)
    for row in reports: print('OBSERVATION_HOLD ' + json.dumps(row, sort_keys=True), file=sys.stderr)
    print(json.dumps(value, sort_keys=True))


if __name__ == '__main__':
    main()
