"""Remote evidence preparation only; requires separately enrolled Owner trust.
Never enrolls keys, invokes the upgrader or installs customer services.
This is a new operation, not a replacement interpretation of a TTY-only permit.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import time
from scripts import pr122_owner_channel_custody as old
from scripts import pr122_owner_custody_envelope as evidence

ATTEMPT = 'pr122-owner-remote-custody-20261017'
ROOT = Path('/root') / ATTEMPT
TRUST = Path('/etc/xuanjun-customer-custody/REMOTE_TRUST.json')
REQUEST = Path('/etc/xuanjun-customer-custody/REMOTE_EVIDENCE.json')
PURPOSE = 'XUANJUN_PR122_REMOTE_CUSTODY_PREPARE'


def private_read(path):
    raw = old.read(path, limit=100000)
    info = path.lstat()
    old.need(info.st_gid == 0 and stat.S_IMODE(info.st_mode) == 0o400,
             'PRIVATE_INPUT_METADATA')
    return raw


def authorize(comment_id, body_sha, expected, envelope_sha, trust_sha, get):
    body = old.comment_body(get(comment_id), comment_id, body_sha)
    old.need(body.startswith(PURPOSE + '\n'), 'NEW_REMOTE_PERMISSION_REQUIRED')
    p = json.loads(body.split('\n', 1)[1])
    now = time.time()
    old.need(p['decision'] == 'REMOTE_CUSTODY_PREPARE_APPROVED'
             and p['attempt_id'] == ATTEMPT and p['host'] == old.HOST
             and p['binding'] == expected
             and p['envelope_sha256'] == envelope_sha
             and p['trust_sha256'] == trust_sha
             and p['executor_sha256'] == old.sha(old.read(Path(__file__).absolute()))
             and p['evidence_validator_sha256'] == old.sha(old.read(Path(evidence.__file__).absolute()))
             and p['package_validator_sha256'] == old.sha(old.read(Path(old.__file__).absolute()))
             and type(p['max_attempts']) is int and p['max_attempts'] == 1
             and p['channel_write_allowed'] is False and p['apply_allowed'] is False
             and type(p['issued_unix']) is int and type(p['expires_unix']) is int
             and p['issued_unix'] <= now < p['expires_unix']
             and 0 < p['expires_unix'] - p['issued_unix'] <= 7200,
             'REMOTE_PERMIT_SCOPE')
    return body


def prepare(comment_id, body_sha, get=old.fetch):
    old.need(os.getuid() == os.geteuid() == 0
             and os.uname().nodename == old.HOST, 'ROOT_HOST')
    os.umask(0o077)
    trust_raw = private_read(TRUST)
    request_raw = private_read(REQUEST)
    trust, request = json.loads(trust_raw), json.loads(request_raw)
    # Fixed operation binding comes from enrolled protected policy, not the request.
    expected = trust['binding']
    old.need(expected['attempt_id'] == ATTEMPT
             and expected['review_zip_sha256'] == old.ZIP_SHA
             and expected['audit_body_sha256'] == old.AUDIT_SHA, 'PROTECTED_BINDING')
    result = evidence.validate(request, trust['owner_key'], expected, time.time())
    approved = authorize(comment_id, body_sha, expected,
                         result['envelope_sha256'], old.sha(trust_raw), get)
    audit = old.comment_body(get(old.AUDIT_ID), old.AUDIT_ID, old.AUDIT_SHA)
    # Exclusive mkdir is the one-use ledger. Never remove it after an error.
    old.need(not os.path.lexists(ROOT), 'ATTEMPT_EXISTS_NO_RETRY')
    ROOT.mkdir(mode=0o700)
    old.sync(ROOT.parent)
    try:
        old.write(ROOT/'attempt.json', old.canonical({'attempt':ATTEMPT,
                  'approval_id':comment_id, 'approval_sha256':body_sha,
                  'state':'STARTED_NO_RETRY'}))
        helper, runtime = old.decode(old.read(old.STAGE, uid=1002))
        old.need(private_read(TRUST) == trust_raw
                 and private_read(REQUEST) == request_raw, 'PRIVATE_INPUT_DRIFT')
        evidence.validate(request, trust['owner_key'], expected, time.time())
        old.need(authorize(comment_id, body_sha, expected, result['envelope_sha256'],
                           old.sha(trust_raw), get) == approved, 'APPROVAL_DRIFT')
        old.need(old.comment_body(get(old.AUDIT_ID), old.AUDIT_ID, old.AUDIT_SHA)
                 == audit, 'AUDIT_DRIFT')
        for name, raw in {'OWNER_EVIDENCE.json':request_raw,
                          'TRUST_SNAPSHOT.json':trust_raw,
                          'approval.txt':approved.encode(), 'audit.txt':audit.encode(),
                          'approved-upgrade.py':helper, 'REVIEW_ARTIFACT.zip':runtime}.items():
            old.write(ROOT/name, raw)
        receipt = {'state':'REMOTE_EVIDENCE_PREPARED_AWAIT_INDEPENDENT_ACCEPTANCE',
                   'attempt':ATTEMPT, 'approval_id':comment_id,
                   'helper_executed':False, 'channel_changes':0,
                   'custody_independence_verified':False, 'retry_allowed':False}
        old.write(ROOT/'receipt.json', old.canonical(receipt))
        return receipt
    except BaseException:
        # The existing directory remains consumed even if this write itself fails.
        old.write(ROOT/'failure.json', old.canonical({'state':'HOLD',
                  'retry_allowed':False, 'channel_changes':0}))
        raise


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--approval-id',type=int,required=True)
    parser.add_argument('--approval-body-sha256',required=True)
    args=parser.parse_args()
    print(json.dumps(prepare(args.approval_id,args.approval_body_sha256),sort_keys=True))

if __name__ == '__main__':
    try:main()
    except BaseException:
        print('{"state":"HOLD","retry_allowed":false,"channel_changes":0}')
        raise SystemExit(2) from None
