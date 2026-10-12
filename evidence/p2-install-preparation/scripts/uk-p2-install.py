#!/usr/bin/env python3
"""Concrete fixed-host CLI for one admitted P2 install transaction."""
import argparse
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'stage1'))

from activation_control import ActivationStore
from ledger_cutover_transaction import LedgerCutoverTransaction
from legacy_host_adapter import LegacyHostAdapter
from p2_fixed_host_runtime import FixedHostRuntime
from p2_install_entrypoint import P2InstallEntrypoint


def _installer(path):
    spec=importlib.util.spec_from_file_location('uk_integration_install',path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    def install(artifact):
        return module.install(artifact['root'],artifact['manifest'],
          artifact['source_commit'],artifact['manifest_sha256'],artifact['releases'],
          enforce_root=True,expected_tree=artifact['source_tree'])
    return install


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--plan',required=True)
    parser.add_argument('--receipt',required=True)
    parser.add_argument('--transaction-directory',required=True)
    parser.add_argument('--release-installer',required=True)
    args=parser.parse_args(argv)
    with open(args.plan) as stream: plan=json.load(stream)
    activation=ActivationStore(
      '/var/lib/xuanjun-development/activation/active.json',
      '/var/lib/xuanjun-development/activation/epochs.jsonl',
      '/var/lib/xuanjun-development/activation/activation.lock')
    legacy=LegacyHostAdapter(args.transaction_directory)
    cutover=LedgerCutoverTransaction(
      os.path.join(args.transaction_directory,'ledger-cutover.json'),legacy)
    runtime=FixedHostRuntime(args.transaction_directory)
    result=P2InstallEntrypoint(args.receipt,_installer(args.release_installer),
                               cutover,activation,runtime).execute(plan)
    print(json.dumps(result,sort_keys=True,separators=(',',':')))
    return 0


if __name__=='__main__': raise SystemExit(main())
