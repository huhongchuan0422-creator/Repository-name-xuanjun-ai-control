"""Durable zero-model candidate jobs for the protected testing pipeline.

Only JSON artifacts are exported, never executable preview routes or approvals.
The existing credential-isolated worker runs this queue without a new root verb.
"""
import base64
import json
from scripts.pr122_customer_core import canonical, digest, Denied
from scripts.pr122_customer_changes import Changes
from scripts.pr122_customer_change_authority import load
from scripts.pr122_customer_preview import original
from scripts.pr122_customer_small_edit import build_candidate


def enqueue(c, actor, project, case):
    c.project(actor, project, {'REVIEWER'})
    events = Changes(c)._events(actor, project, case)
    last = events[-1]
    if last['kind'] != 'ASSESSMENT' or last['payload'].get('state') != 'FREE_APPROVED' or last['payload'].get('category') != 'IN_SCOPE_SMALL':
        raise Denied('CURRENT_FREE_SMALL_ASSESSMENT_REQUIRED')
    packet = {'project': project, 'case': case, 'request_sha256': Changes(c)._request_sha(events), 'assessment_event_id': last['id']}
    key = digest(canonical({'actor': actor, 'packet': packet}))
    with c.tx():
        c.project(actor, project, {'REVIEWER'})
        c.limit('small-edit:' + actor + ':' + project, 20, 3600)
        c.db.execute('INSERT OR IGNORE INTO preview_edit_jobs VALUES(?,?,?,?,?,?,?)', (key, project, actor, 'QUEUED', c.encrypt(canonical(packet), key), c.now(), None))
        c.audit(project, actor, 'SMALL_EDIT_QUEUED', key)
    state = c.db.execute('SELECT state FROM preview_edit_jobs WHERE id=?', (key,)).fetchone()[0]
    from scripts.pr122_customer_publication_worker import notify
    return {'id': key, 'state': state, 'notification_sent': notify() if state == 'QUEUED' else False, 'production_published': False}


def bundle(c, job, candidate):
    receipt = candidate['receipt']
    source = load(c)
    if source['source_sha256'] != receipt['authority_sha256']:
        raise Denied('EDIT_RESOURCE_SOURCE_CHANGED')
    row = c.db.execute('SELECT payload FROM change_authority_history WHERE revision=?', (source['revision'],)).fetchone()
    payload = json.loads(c.decrypt(row[0], 'change-authority-source:' + str(source['revision'])))['payload']
    if digest(canonical(payload)) != source['source_sha256']:
        raise Denied('EDIT_RESOURCE_SOURCE_IDENTITY')
    entry = next((x for x in payload['previews'] if x['project'] == receipt['project'] and x['manifest_sha256'] == receipt['manifest_sha256']), None)
    if not entry:
        raise Denied('EDIT_RESOURCE_MANIFEST_REQUIRED')
    files = []
    size = 0
    for page in entry['manifest']['pages']:
        body = base64.b64decode(entry['blobs'][page['sha256']], validate=True)
        if digest(body) != page['sha256']:
            raise Denied('EDIT_RESOURCE_BYTES_CHANGED')
        if page['path'] == receipt['page']:
            body = candidate['page_bytes']
        size += len(body)
        if size > 2000000:
            raise Denied('SMALL_EDIT_RESOURCE_CLOSURE_TOO_LARGE')
        files.append({'path': page['path'], 'sha256': digest(body), 'base64': base64.b64encode(body).decode()})
    return {'schema': 'PR122_PRIVATE_EDIT_ARTIFACT_V1', 'job': job, 'receipt': receipt, 'receipt_sha256': candidate['receipt_sha256'], 'page_base64': base64.b64encode(candidate['page_bytes']).decode(), 'source_manifest_original': entry['manifest'], 'files': files, 'modified_files': [receipt['page']], 'testing_scope': 'UNSIGNED_CANDIDATE_REQUIRES_ISOLATED_TESTS_AND_INDEPENDENT_APPROVAL'}


def drain(c):
    done = held = 0
    rows = c.db.execute("SELECT * FROM preview_edit_jobs WHERE state='QUEUED' ORDER BY created,id LIMIT 4").fetchall()
    for row in rows:
        with c.tx():
            if c.db.execute("UPDATE preview_edit_jobs SET state='PROCESSING' WHERE id=? AND state='QUEUED'", (row['id'],)).rowcount != 1:
                continue
        try:
            c.project(row['actor'], row['project'], {'REVIEWER'})
            packet = json.loads(c.decrypt(row['payload'], row['id']))
            events = Changes(c)._events(row['actor'], row['project'], packet['case'])
            if Changes(c)._request_sha(events) != packet['request_sha256'] or events[-1]['id'] != packet['assessment_event_id']:
                raise Denied('QUEUED_ASSESSMENT_CHANGED')
            candidate = build_candidate(c, row['actor'], row['project'], packet['case'])
            artifact = bundle(c, row['id'], candidate)
            result = {'artifact': artifact, 'artifact_sha256': digest(canonical(artifact)), 'production_published': False}
            state = 'CANDIDATE_READY'
            done += 1
        except BaseException:
            result = {'state': 'HOLD_INVALID_OR_UNKNOWN', 'retry_allowed': False, 'production_published': False}
            state = 'HOLD_UNKNOWN'
            held += 1
        with c.tx():
            c.db.execute('UPDATE preview_edit_jobs SET state=?,result=? WHERE id=?', (state, c.encrypt(canonical(result), 'edit-result:' + row['id']), row['id']))
            c.audit(row['project'], 'candidate-worker', 'SMALL_EDIT_' + state, row['id'])
    unknown = c.db.execute("SELECT COUNT(*) FROM preview_edit_jobs WHERE state IN ('PROCESSING','HOLD_UNKNOWN')").fetchone()[0]
    return {'done': done, 'held': held, 'unknown': unknown, 'model_api_calls': 0, 'production_published': False, 'automatic_retry': False}


def get(c, actor, project, job):
    c.project(actor, project, {'REVIEWER'})
    row = c.db.execute('SELECT * FROM preview_edit_jobs WHERE id=? AND project=?', (job, project)).fetchone()
    if not row:
        raise Denied('EDIT_JOB_NOT_FOUND')
    c.project(row['actor'], project, {'REVIEWER'})
    result = json.loads(c.decrypt(row['result'], 'edit-result:' + job)) if row['result'] else None
    if row['state'] == 'CANDIDATE_READY':
        artifact = result['artifact']
        receipt = artifact['receipt']
        if artifact['job'] != job or digest(canonical(artifact)) != result['artifact_sha256'] or digest(canonical(receipt)) != artifact['receipt_sha256'] or digest(base64.b64decode(artifact['page_base64'], validate=True)) != receipt['after_sha256']:
            raise Denied('EDIT_ARTIFACT_IDENTITY')
        p, _, _ = c.project(actor, project, {'REVIEWER'})
        events = Changes(c)._events(actor, project, receipt['case'])
        found, _, _ = original(c, p['owner'], project, digest(receipt['page'].encode()), receipt['before_sha256'])
        if receipt['contract_ref'] != p['authority_ref'] or receipt['request_sha256'] != Changes(c)._request_sha(events) or receipt['assessment_event_id'] != events[-1]['id'] or receipt['manifest_sha256'] != found['manifest_sha256']:
            raise Denied('EDIT_CANDIDATE_NO_LONGER_CURRENT')
    return {'id': job, 'state': row['state'], 'result': result, 'production_published': False}
