#!/usr/bin/env python3
"""Concrete fixed-host CLI for one admitted P2 install transaction."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import stat
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'stage1'))

from activation_control import ActivationStore
from ledger_cutover_transaction import LedgerCutoverTransaction
from legacy_host_adapter import LegacyHostAdapter
from p2_fixed_host_runtime import FixedHostRuntime
from p2_install_entrypoint import P2InstallEntrypoint, validate_plan


def _installer(path):
    expected=os.path.join(ROOT,'scripts','uk-integration-install.py')
    if path!=expected or os.path.realpath(path)!=path:
        raise ValueError('FIXED_RELEASE_INSTALLER_REQUIRED')
    spec=importlib.util.spec_from_file_location('uk_integration_install',path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    def install(artifact):
        return module.install(artifact['root'],artifact['manifest'],
          artifact['source_commit'],artifact['manifest_sha256'],artifact['releases'],
          enforce_root=True,expected_tree=artifact['source_tree'])
    return install


def read_plan(path, expected_digest):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=0
                or stat.S_IMODE(info.st_mode)&0o022 or info.st_size>1048576):
            raise ValueError('ROOT_PROTECTED_BOUNDED_PLAN_REQUIRED')
        raw=stream.read(1048577)
    if hashlib.sha256(raw).hexdigest()!=expected_digest:
        raise ValueError('REVIEWED_PLAN_SHA256_MISMATCH')
    return json.loads(raw.decode('utf-8'))


def installation_lock():
    fd=os.open('/run/xuanjun-p2-install.lock',
               os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=0
                or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1):
            raise ValueError('UNSAFE_INSTALL_LOCK')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return fd
    except BaseException:
        os.close(fd)
        raise


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--operation',required=True,
                        choices=('verify-only','install','rollback'))
    parser.add_argument('--plan',required=True)
    parser.add_argument('--plan-sha256',required=True)
    parser.add_argument('--receipt',required=True)
    parser.add_argument('--transaction-directory',required=True)
    parser.add_argument('--release-installer',required=True)
    args=parser.parse_args(argv)
    if os.geteuid()!=0:
        raise ValueError('ROOT_REQUIRED')
    plan=read_plan(args.plan,args.plan_sha256)
    release_install=_installer(args.release_installer)
    lock_fd=installation_lock()
    activation=ActivationStore(
      '/var/lib/xuanjun-development/activation/active.json',
      '/var/lib/xuanjun-development/activation/epochs.jsonl',
      '/var/lib/xuanjun-development/activation/activation.lock')
    legacy=LegacyHostAdapter(args.transaction_directory)
    cutover=LedgerCutoverTransaction(
      os.path.join(args.transaction_directory,'ledger-cutover.json'),legacy)
    runtime=FixedHostRuntime(args.transaction_directory)
    try:
        entrypoint=P2InstallEntrypoint(args.receipt,release_install,
                                      cutover,activation,runtime)
        if args.operation=='verify-only':
            validate_plan(plan)
            if 'legacy_isolation' in plan['cutover']:
                if legacy.preflight(plan['cutover']) is not True:raise ValueError('CLI_ADOPTION_PREFLIGHT_FAILED')
            runtime.preflight(plan['runtime'],plan['auth'],plan['tls'])
            result={'schema':1,'stage':'VERIFIED_ONLY',
                    'transaction_id':plan['transaction_id'],
                    'plan_sha256':hashlib.sha256(json.dumps(
                        plan,sort_keys=True,separators=(',',':'),
                        allow_nan=False).encode('utf-8')).hexdigest(),
                    'effects':0,'oauth_copied':False,
                    'new_paid_api_usage':'NONE'}
        elif args.operation=='install':
            result=entrypoint.execute(plan)
        else:
            result=entrypoint.rollback(plan)
    finally:
        os.close(lock_fd)
    print(json.dumps(result,sort_keys=True,separators=(',',':')))
    return 0


if __name__=='__main__': raise SystemExit(main())
