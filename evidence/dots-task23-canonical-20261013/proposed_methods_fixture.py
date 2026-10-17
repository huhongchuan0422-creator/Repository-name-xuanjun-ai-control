"""TEST-ONLY exact proposed method excerpts; not an operational ledger."""
import json
SCHEMA = '\nCREATE TABLE IF NOT EXISTS supervised_runs(\n task_id TEXT PRIMARY KEY REFERENCES tasks(id), spec_hash TEXT NOT NULL,\n executor TEXT NOT NULL, run_id TEXT NOT NULL, session_id TEXT NOT NULL,\n workdir TEXT NOT NULL, artifact TEXT NOT NULL, dispatched_at REAL NOT NULL,\n start_deadline REAL NOT NULL, progress_deadline REAL NOT NULL,\n result_deadline REAL NOT NULL, native_state TEXT NOT NULL,\n accepted_at REAL, started_at REAL, last_progress REAL, terminal_receipt TEXT,\n effects TEXT NOT NULL, budget_key TEXT NOT NULL, budget_spent INTEGER NOT NULL,\n writer_fence INTEGER, writer_epoch INTEGER, start_receipt TEXT,\n resume_generation INTEGER NOT NULL DEFAULT 0, resume_base_fence INTEGER,\n status TEXT NOT NULL, checkpoint TEXT NOT NULL,\n checkpoint_version INTEGER NOT NULL DEFAULT 0, checkpoint_hash TEXT);\nCREATE TABLE IF NOT EXISTS supervision_events(\n event_key TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),\n sequence INTEGER NOT NULL, kind TEXT NOT NULL, created_at REAL NOT NULL,\n details TEXT NOT NULL, UNIQUE(task_id,sequence));\nCREATE TABLE IF NOT EXISTS supervision_delivery(\n event_key TEXT NOT NULL REFERENCES supervision_events(event_key),\n destination TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL,\n next_attempt_at REAL NOT NULL, claim_owner TEXT, claim_until REAL,\n claim_epoch INTEGER NOT NULL DEFAULT 0, authority_fence INTEGER NOT NULL,\n authority_epoch INTEGER NOT NULL, receipt_id TEXT, last_error TEXT,\n send_attempts INTEGER NOT NULL DEFAULT 0, sent_at REAL,\n reconciliation_owner TEXT, reconciliation_until REAL,\n reconciliation_epoch INTEGER NOT NULL DEFAULT 0, claim_token TEXT,\n claim_attempt INTEGER,\n PRIMARY KEY(event_key,destination));\n'
def _dump(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)

class ProposedMethods:
    def _event(self, db, task_id, kind, details,
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
        if key is not None and db.execute(
                'SELECT 1 FROM supervision_events WHERE event_key=?',
                (key,)).fetchone():
            return key
        sequence = db.execute('SELECT COUNT(*) FROM supervision_events WHERE task_id=?',
                              (task_id,)).fetchone()[0] + 1
        key = key or '%s:%s:%d' % (task_id, kind, sequence)
        now = float(self.clock())
        db.execute('INSERT INTO supervision_events VALUES(?,?,?,?,?,?)',
                   (key, task_id, sequence, kind, now, _dump(details)))
        task_fence = db.execute('SELECT fence FROM tasks WHERE id=?',
                                (task_id,)).fetchone()[0]
        authority_epoch = (self.activation_binding or {}).get('epoch', 0)
        for destination in destinations:
            db.execute("""INSERT INTO supervision_delivery
              (event_key,destination,state,attempts,next_attempt_at,claim_owner,
               claim_until,claim_epoch,authority_fence,authority_epoch,
               receipt_id,last_error,send_attempts,sent_at,
               reconciliation_owner,reconciliation_until,reconciliation_epoch)
              VALUES(?,?,'PENDING',0,?,NULL,NULL,0,?,?,NULL,NULL,0,NULL,NULL,NULL,0)""",
                       (key, destination, now, task_fence, authority_epoch))
        return key


    def record_inventory_notice(self, db, intent, activation_binding, ledger_identity):
        """Called only inside the existing owner's pinned canonical transaction.

        The caller must pin the DB/file identity, roll back on ANY exception,
        and validate activation when committing. This never dispatches/resumes.
        """
        from task_supervisor_runtime import canonical_inventory_page, assert_inventory_lineage
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

