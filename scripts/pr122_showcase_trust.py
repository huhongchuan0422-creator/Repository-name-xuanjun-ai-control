"""Owner-enrolled exact review anchors; no enrollment or signing API.

This file is NOT a trust source. Only root-private operator policy outside the
checkout can authorize an independent subject and exact immutable comment bytes.
"""
import json
import os
from pathlib import Path
import stat
import time
from scripts.pr122_showcase import need, sha

TRUST = Path('/etc/xuanjun-showcase/INDEPENDENT_REVIEW_TRUST.json')
SCOPES = {'CONTENT', 'PUBLICATION', 'MECHANISM'}

def load():
    # Walk every ancestor without resolving links; source/CLI/env cannot select
    # another path. Non-root builders can read only via a protected operator.
    for path in reversed((TRUST, *TRUST.parents)):
        s = path.lstat()
        need(not stat.S_ISLNK(s.st_mode) and s.st_uid == 0 and not stat.S_IMODE(s.st_mode) & 0o022, 'OWNER_TRUST_PATH')
        if path != TRUST:
            need(stat.S_ISDIR(s.st_mode), 'OWNER_TRUST_DIRECTORY')
    fd = os.open(TRUST, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        s = os.fstat(stream.fileno())
        need(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and stat.S_IMODE(s.st_mode) == 0o600 and s.st_nlink == 1 and s.st_size <= 1000000, 'OWNER_TRUST_FILE')
        return json.loads(stream.read(1000001))

def verify(comment, scope, trust=None, now=None):
    # Explicit trust is only a dependency-injection seam for isolated tests.
    # Production callers always load the fixed root-private path above.
    trust = load() if trust is None else trust
    now = time.time() if now is None else now
    need(scope in SCOPES and type(trust) is dict and set(trust) == {'schema', 'source_writer_principal', 'reviewers', 'revoked_review_ids', 'anchors'} and trust['schema'] == 1, 'OWNER_TRUST_SCHEMA')
    need(type(trust['source_writer_principal']) is str and bool(trust['source_writer_principal']), 'SOURCE_WRITER_IDENTITY')
    identifier = comment['id']
    need(type(identifier) is int and identifier > 0 and identifier not in trust['revoked_review_ids'], 'REVIEW_REVOKED')
    anchor = trust['anchors'].get(str(identifier))
    need(type(anchor) is dict and set(anchor) == {'body_sha256', 'scope', 'reviewer_principal', 'custody_evidence_sha256', 'issued_unix', 'expires_unix'}, 'OWNER_REVIEW_ANCHOR_REQUIRED')
    reviewer = trust['reviewers'].get(anchor['reviewer_principal'])
    need(type(reviewer) is dict and set(reviewer) == {'status', 'custody_evidence_sha256'} and reviewer['status'] == 'ACTIVE' and anchor['reviewer_principal'] != trust['source_writer_principal'], 'INDEPENDENT_ENROLLED_REVIEWER')
    evidence = anchor['custody_evidence_sha256']
    need(type(evidence) is str and len(evidence) == 64 and all(c in '0123456789abcdef' for c in evidence) and reviewer['custody_evidence_sha256'] == evidence, 'INDEPENDENT_CUSTODY_EVIDENCE')
    need(anchor['scope'] == scope and anchor['body_sha256'] == sha(comment['body'].encode('utf-8')), 'EXACT_REVIEW_ANCHOR')
    start, end = anchor['issued_unix'], anchor['expires_unix']
    need(type(start) is int and type(end) is int and start <= now < end and 0 < end - start <= 7 * 86400, 'OWNER_REVIEW_ANCHOR_EXPIRED')
    return anchor
