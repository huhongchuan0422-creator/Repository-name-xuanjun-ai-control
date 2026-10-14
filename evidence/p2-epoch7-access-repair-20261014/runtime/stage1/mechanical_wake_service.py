#!/usr/bin/python3 -Es
"""Run one inference-free recovery pass after the fixed GitHub intake scan."""
import json
import os
import socket
import sqlite3
import time
from pathlib import Path

from activation_control import ActivationStore
from execution_ledger import ExecutionLedger
from mechanical_wake import MechanicalWakeController

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
DESCRIPTOR = '/var/lib/xuanjun-development/activation/active.json'
EPOCHS = '/var/lib/xuanjun-development/activation/epochs.jsonl'
LOCK = '/var/lib/xuanjun-development/activation/activation.lock'
REPO = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'


class InstalledAdapter(object):
    """Only attests capabilities available to the installed non-root unit.

    The preceding ExecStart performed the real intake scan.  There is not yet
    a reviewed native-session resume API, so 10/15 minute actions remain a
    visible HOLD rather than using comments or spawning a second writer.
    """
    def recover_intake(self, context):
        return {'state': 'RECEIVER_RESCAN_COMPLETED'}

    def inspect_writer(self, context):
        return {'state': 'UNKNOWN', 'same_attempt': True, 'fence_stale': False}

    def resume_original(self, context):
        return {'state': 'HOLD_NATIVE_RESUME_API_UNAVAILABLE'}

    def controlled_recovery(self, context):
        return {'state': 'HOLD_NATIVE_TAKEOVER_API_UNAVAILABLE'}


def main():
    if os.geteuid() == 0 or socket.gethostname().split('.')[0] != HOST:
        raise SystemExit('STOP_NONROOT_UK_ONLY')
    activation = ActivationStore(DESCRIPTOR, EPOCHS, LOCK)
    active = activation.read(require_active=True)
    ledger=ExecutionLedger(active['db_path'],[REPO],activation_store=activation)
    inventory=ledger.record_inventory_notices()
    db = sqlite3.connect(Path(active['db_path']).resolve().as_uri() + '?mode=ro',
                         uri=True, timeout=5)
    try:
        task_ids = [row[0] for row in db.execute(
            "SELECT task_id FROM supervised_runs WHERE status NOT IN ('COMPLETED','HOLD') ORDER BY task_id")]
    finally:
        db.close()
    controller = MechanicalWakeController(active['db_path'], time.time,
                                          InstalledAdapter())
    results = [controller.evaluate(task_id) for task_id in task_ids]
    # Existing intake oneshot calls the peer-authenticated Gateway relay, no model.
    from native_gateway_controller import RelayController
    try:
        owner_delivery=RelayController({'relay_socket':'/run/xuanjun-development/p2-gateway.sock',
            'server_user':'xuanjun_dev','client_group':'xuanjun-dispatcher'}).owner_cycle()
    except Exception:
        owner_delivery={'state':'HOLD_OWNER_DELIVERY_NOT_READY','receiver_ack':False,'model_calls':0}
    print(json.dumps({'state': 'RECOVERY_PASS_COMPLETE',
                      'native_resume_api': 'UNAVAILABLE',
                      'inventory': inventory, 'owner_delivery': owner_delivery,
                      'model_calls': 0, 'results': results},
                     sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
