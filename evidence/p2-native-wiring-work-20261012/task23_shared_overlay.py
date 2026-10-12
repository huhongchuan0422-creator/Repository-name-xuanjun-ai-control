"""Integrate reviewed DOTS task2/3 notice adapter into existing P2 package.

Fails closed unless the packaged shared source is the exact reviewed base.
Python 3.6 compatible; no DB/queue creation and no dispatch.
"""
from __future__ import print_function
import hashlib
import pathlib
import shutil
import sys

BASE_SHA256='4de3ad4210912ef79935aadb0d4b2de06159a38546a6aec3830d9b46dbef1d53'
PROPOSED_DOTS_PATCH_SHA256='c9acd93164d247d04aa95f681a70f0cca875973eaab6c2f9ad43c5ccf515f287'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def replace_once(path,old,new):
    text=path.read_text()
    if text.count(old)!=1:
        raise ValueError('TASK23_SHARED_SOURCE_DRIFT:'+old[:48])
    path.write_text(text.replace(old,new))

def main():
    source=pathlib.Path(sys.argv[1]).resolve()
    target=source/'stage1'/'execution_supervision.py'
    if sha(target)!=BASE_SHA256:
        raise ValueError('TASK23_SHARED_BASE_SHA256_MISMATCH')
    adapter_source=pathlib.Path(__file__).resolve().parent/'task_supervisor_inventory_adapter.py'
    adapter_target=source/'stage1'/'task_supervisor_inventory_adapter.py'
    shutil.copy2(str(adapter_source),str(adapter_target))

    replace_once(target,
"""    def _event(self, db, task_id, kind, details,
               destinations=('GITHUB_PR17', 'OWNER'), canonical=False):
        key = ('%s:terminal:%s' % (task_id, kind)) if canonical else None
""",
"""    def _event(self, db, task_id, kind, details,
               destinations=('GITHUB_PR17', 'OWNER'), canonical=False, dedupe_key=None):
        key = ('%s:terminal:%s' % (task_id, kind)) if canonical else None
        if dedupe_key is not None:
            if (not isinstance(dedupe_key, str) or len(dedupe_key) != 64
                    or any(c not in '0123456789abcdef' for c in dedupe_key)):
                raise ValueError('INVALID_INVENTORY_EVENT_KEY')
            key = '%s:inventory:%s' % (task_id, dedupe_key)
            previous = db.execute('SELECT kind,details FROM supervision_events WHERE event_key=?',
                                  (key,)).fetchone()
            if previous is not None:
                if previous['kind'] != kind or previous['details'] != _dump(details):
                    raise ValueError('INVENTORY_EVENT_KEY_COLLISION')
                return key
""")

    replace_once(target,
"""        return key

    def dispatch(self, task_id, spec_hash, executor, run_id, session_id, workdir,
""",
"""        return key

    def record_inventory_notice(self, db, intent, activation_binding, ledger_identity):
        """Notice-only mutation inside the caller-owned pinned canonical transaction."""
        from task_supervisor_inventory_adapter import canonical_inventory_page, assert_inventory_lineage
        if not db.in_transaction or self.activation_store is None:
            raise ValueError('ADMITTED_CANONICAL_TRANSACTION_REQUIRED')
        self._assert_activation()
        if activation_binding != self.activation_binding:
            raise ValueError('INVENTORY_ACTIVATION_CHANGED')
        if not isinstance(intent, dict) or not isinstance(intent.get('binding'), dict):
            raise ValueError('INVENTORY_INTENT_REQUIRED')
        task_id = intent['binding'].get('task_id')
        page = canonical_inventory_page(db, self.clock(), task_id=task_id,
            activation_binding=activation_binding, ledger_identity=ledger_identity)
        if len(page['tasks']) != 1:
            raise ValueError('INVENTORY_TASK_CHANGED')
        current = page['tasks'][0]
        assert_inventory_lineage(intent['binding'], current['binding'], notice_only=True)
        if (intent.get('decision_key') != current['decision_key']
                or intent.get('attention') != current['attention']
                or current['decision'] != 'HOLD_AND_NOTIFY_REQUIRES_ADMISSION'):
            raise ValueError('INVENTORY_DECISION_CHANGED')
        key = self._event(db, task_id, 'INVENTORY_NOTICE',
            {'decision_key': current['decision_key'], 'binding': current['binding'],
             'attention': current['attention'], 'dispatch_performed': False},
            dedupe_key=current['decision_key'])
        self._assert_activation()
        return {'state': 'NOTICE_RECORDED_NOT_DELIVERED', 'event_key': key,
                'dispatch_performed': False, 'receiver_ack': 'NOT_PROVEN'}

    def dispatch(self, task_id, spec_hash, executor, run_id, session_id, workdir,
""")
    print('P2_TASK23_SHARED_ADAPTER_APPLIED')

if __name__=='__main__':
    main()
