#!/usr/bin/env python3
"""Private canonical-ledger mutation socket; Owner decisions only."""
import argparse
import os
import pwd
import signal
import socket
import sys

from activation_control import ActivationStore
from development_service import load_config
from execution_ledger import ExecutionLedger
from uk_owner_callback_core import LedgerOwnerDecisionServer
from native_peer_identity import load_native_peer_identity
from owner_process_identity import load_owner_process_verifier, CALLBACK_UID, CALLBACK_USER


def build(config):
    activation=ActivationStore(config['activation_descriptor'],
                               config['activation_epoch_journal'],
                               config['activation_lock'])
    active=activation.read(require_active=True)
    # Validate mandatory process identities before any writable ledger open.
    if config['callback_user'] != CALLBACK_USER:
        raise ValueError('LEDGER_EXACT_CALLBACK_USER_REQUIRED')
    callback_uid=pwd.getpwnam(config['callback_user']).pw_uid
    if type(callback_uid) is not int or callback_uid != CALLBACK_UID:
        raise ValueError('LEDGER_EXACT_CALLBACK_UID_REQUIRED')
    native_identity=load_native_peer_identity()
    owner_verifier=load_owner_process_verifier(active['release_sha256'])
    if activation.read(require_active=True) != active:
        raise ValueError('LEDGER_IDENTITY_ACTIVATION_CHANGED')
    ledger=ExecutionLedger(active['db_path'],[config['control_repository']],
                           max_heavy=config['max_workers'],
                           approved_base_shas=[config['source_commit']],
                           activation_store=activation)
    from owner_feishu_ledger_endpoint import OwnerFeishuLedgerEndpoint
    ledger.owner_feishu_endpoint=OwnerFeishuLedgerEndpoint(ledger)
    return LedgerOwnerDecisionServer(activation,ledger,callback_uid,
                                     native_identity=native_identity,
                                     owner_process_verifier=owner_verifier)


def listener():
    if (int(os.environ.get('LISTEN_FDS','0') or '0')!=1
            or int(os.environ.get('LISTEN_PID','0') or '0')!=os.getpid()):
        raise ValueError('ledger service requires exactly one systemd socket')
    return socket.socket(fileno=3)


def main(argv=None):
    parser=argparse.ArgumentParser(); parser.add_argument('--config',required=True)
    args=parser.parse_args(argv); server=build(load_config(args.config)); sock=listener()
    stopping=[False]
    signal.signal(signal.SIGTERM,lambda *_:stopping.__setitem__(0,True))
    signal.signal(signal.SIGINT,lambda *_:stopping.__setitem__(0,True))
    sock.settimeout(1)
    while not stopping[0]:
        try: connection,_=sock.accept()
        except socket.timeout: continue
        with connection:
            try: server.serve_connection(connection)
            except Exception:
                try: connection.sendall(b'{"accepted":false}\n')
                except OSError: pass
    sock.close(); return 0


if __name__=='__main__': sys.exit(main())
