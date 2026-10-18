"""Original customer install transaction's durable admission ledger.
No command runner or retry loop. Caller must hold the original transaction lock.
Only proven pre-activation failures can be considered on a later manual call.
"""
import json
import os
import stat
import time
from pathlib import Path
from scripts.pr122_customer_core import Denied, canonical, digest, secure_write, private_path

POLICY = 'CONTROLLED_PREACTIVATION_V1'
SAFE_ERRORS = {'HOLD:SOURCE_HASH', 'HOLD:SOURCE_PATH', 'HOLD:SOURCE_DUPLICATE',
               'HOLD:ACTIVATION_DRIFT'}


def need(ok, message):
    if not ok:
        raise Denied('HOLD:' + message)


def protected_directory(path):
    for item in (private_path(path), *Path(path).parents):
        info = item.lstat()
        need(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
             'ATTEMPT_DIRECTORY_TRUST')


def read_private(path):
    protected_directory(Path(path).parent)
    fd = os.open(private_path(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        need(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
             and stat.S_IMODE(info.st_mode) == 0o600, 'ATTEMPT_FILE_TRUST')
        raw = stream.read(65537)
    need(len(raw) <= 65536, 'ATTEMPT_SIZE')
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'ATTEMPT_DUPLICATE_KEY')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: need(False, 'ATTEMPT_NONFINITE'))


def validate_approval(approval):
    count = approval.get('max_executions')
    need(type(count) is int and 1 <= count <= 5, 'ATTEMPT_LIMIT')
    need(count == 1 or approval.get('attempt_policy') == POLICY, 'EXPLICIT_NEW_ATTEMPT_POLICY')
    return count


class Attempts:
    def __init__(self, state, transaction, approval, comment, plan, save, config):
        self.state, self.transaction = Path(state), transaction
        self.path = self.state / (transaction + '.attempts.json')
        self.approval, self.save, self.config = approval, save, Path(config)
        self.limit = validate_approval(approval)
        self.binding = {'transaction': transaction, 'approval_comment': comment,
                        'approval_sha256': digest(canonical(approval)),
                        'plan_sha256': digest(canonical(plan)),
                        'host': os.uname().nodename, 'executor_uid': os.geteuid()}
        need(os.geteuid() == 0, 'ATTEMPT_ROOT')
        need(type(approval['issued_unix']) is int and type(approval['expires_unix']) is int
             and approval['issued_unix'] <= time.time() < approval['expires_unix'], 'ATTEMPT_EXPIRY')
        # Any old transaction, including successful/rolled-back or unknown state,
        # remains sealed. No legacy permit is revived by the new ledger.
        need(not os.path.lexists(self.state / transaction), 'EXISTING_TRANSACTION_SEALED')
        if self.state.exists():
            protected_directory(self.state)
        else:
            protected_directory(self.state.parent)
            self.state.mkdir(mode=0o700)
            parent_fd = os.open(self.state.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try: os.fsync(parent_fd)
            finally: os.close(parent_fd)
        if os.path.lexists(self.path):
            self.data = read_private(self.path)
            need(set(self.data) == {'schema', 'binding', 'attempts'} and type(self.data['schema']) is int and self.data['schema'] == 1
                 and self.data['binding'] == self.binding, 'ATTEMPT_BINDING')
            rows = self.data['attempts']
            need(type(rows) is list and 1 <= len(rows) <= self.limit, 'ATTEMPT_HISTORY')
            parent = None
            for number, row in enumerate(rows, 1):
                need(type(row) is dict and type(row.get('number')) is int and row.get('number') == number
                     and row.get('previous_sha256') == parent, 'ATTEMPT_CHAIN')
                parent = digest(canonical(row))
            need(len(rows) < self.limit, 'ATTEMPT_EXHAUSTED')
            last = rows[-1]
            need(last.get('state') == 'SAFE_PREACTIVATION_FAILURE'
                 and last.get('error') in SAFE_ERRORS, 'ATTEMPT_UNRESOLVED_OR_FINISHED')
            evidence = read_private(self.config / 'INSTALL_RETRY_EVIDENCE.json')
            expected = {'schema', 'previous_attempt_sha256', 'binding_sha256',
                        'diagnosis', 'recovery', 'no_install_effects', 'checked_unix'}
            need(set(evidence) == expected and type(evidence['schema']) is int and evidence['schema'] == 1
                 and evidence['previous_attempt_sha256'] == parent
                 and evidence['binding_sha256'] == digest(canonical(self.binding))
                 and evidence['no_install_effects'] is True, 'RETRY_EVIDENCE_BINDING')
            need(type(evidence['checked_unix']) is int and last['ended_unix'] <= evidence['checked_unix']
                 <= time.time() < approval['expires_unix'], 'RETRY_EVIDENCE_TIME')
            for key in ('diagnosis', 'recovery'):
                need(type(evidence[key]) is str and 1 <= len(evidence[key]) <= 2000,
                     'RETRY_DIAGNOSIS_AND_RECOVERY_REQUIRED')
            diagnosis_sha = digest(evidence['diagnosis'].encode())
            need(all(row.get('diagnosis_sha256') != diagnosis_sha for row in rows),
                 'REPEATED_ROOT_CAUSE_HOLD')
            self.diagnosis_sha = diagnosis_sha
            self.recovery_sha = digest(canonical(evidence))
        else:
            self.data = {'schema': 1, 'binding': self.binding, 'attempts': []}
            self.recovery_sha = None
            self.diagnosis_sha = None
        number = len(self.data['attempts']) + 1
        self.row = {'number': number, 'attempt_id': transaction + '-%02d' % number,
                    'previous_sha256': digest(canonical(self.data['attempts'][-1])) if number > 1 else None,
                    'recovery_evidence_sha256': self.recovery_sha,
                    'diagnosis_sha256': self.diagnosis_sha,
                    'started_unix': int(time.time()), 'state': 'STARTED_UNKNOWN'}
        self.data['attempts'].append(self.row)
        # Persist consumption before source recheck, backup, or installation.
        if number == 1:
            secure_write(self.path, canonical(self.data))
            fd = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try: os.fsync(fd)
            finally: os.close(fd)
        else:
            self.save(self.path, self.data)

    def finish(self, state, error=None):
        need(self.row['state'] == 'STARTED_UNKNOWN', 'ATTEMPT_ALREADY_FINISHED')
        need(state in {'SAFE_PREACTIVATION_FAILURE', 'HOLD_UNKNOWN_OR_PARTIAL',
                       'HTTPS_SMOKE_PASS_AWAIT_14_REAL_ACCEPTANCE'}, 'ATTEMPT_STATE')
        if state == 'SAFE_PREACTIVATION_FAILURE':
            need(error in SAFE_ERRORS, 'UNCLASSIFIED_FAILURE')
        self.row.update(state=state, ended_unix=int(time.time()))
        if error is not None: self.row['error'] = error
        self.save(self.path, self.data)
