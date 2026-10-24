"""Fixed B5 algorithm bridge; no enrollment, transport, or new authority.

The original protected DB, catalog, policy and request-local OAuth resource
must be supplied by their original owners. These functions do not establish
their provenance and must never be treated as an admission receipt by itself.
"""
import base64
import binascii
import hashlib

from production.cloud_connection.fixed_actions import ApprovedObjectsPolicy
from production.cloud_connection.private_transfer import bound_job
from production.cloud_connection.material_custody import ingest_approved_batch
from production.cloud_connection.oauth_resource import OAuthProjectResource
from production.cloud_connection.queue import Hold, canonical
from production.cloud_connection.archive_reader import read_archive_members


def success_set(db, policy, requests, recipient, catalog_sha, now):
    """Use the original bound_job for each exact distinct frozen request."""
    if (type(policy) is not ApprovedObjectsPolicy or
            type(requests) not in (list, tuple) or len(requests) != 19 or
            catalog_sha != policy.catalog.sha or
            recipient != policy.binding['recipient_id'] or
            len(policy.binding['requests']) != 19):
        raise Hold('B5_SUCCESS_SET_BINDING')
    seen_ids, seen_refs, invokes = set(), set(), []
    for request in requests:
        if type(request) is not dict or type(request.get('request_id')) is not str:
            raise Hold('B5_SUCCESS_REQUEST')
        item = policy.request_object(request)
        ref, rid = item['ref'], request['request_id']
        if rid in seen_ids or ref in seen_refs:
            raise Hold('B5_SUCCESS_DUPLICATE')
        policy.validate(request, 332398908, now)
        invoke = bound_job(db, policy.catalog, rid, ref, recipient)
        if type(invoke) is not str or not invoke:
            raise Hold('B5_SUCCESS_INVOKE')
        seen_ids.add(rid); seen_refs.add(ref); invokes.append(invoke)
    if (seen_ids != set(policy.binding['requests'].values()) or
            seen_refs != set(policy.catalog.objects) or
            len(set(invokes)) != 19 or
            sum(policy.catalog.objects[x]['bytes'] for x in seen_refs) != 93592):
        raise Hold('B5_SUCCESS_INCOMPLETE')
    return tuple(invokes)


def observe_original_ready(db, request):
    """Read READY on original queue; not proof that this caller POSTed it."""
    if type(request) is not dict or type(request.get('request_id')) is not str:
        raise Hold('B5_INTAKE_REQUEST')
    row = db.execute('SELECT state,request_json,request_sha,actor_id FROM '
                     'connection_jobs WHERE request_id=?',
                     (request['request_id'],)).fetchone()
    body = canonical(request)
    if (row is None or row[0] != 'READY' or row[1] != body or
            row[2] != hashlib.sha256(body.encode()).hexdigest() or
            type(row[3]) is not int or row[3] != 332398908):
        raise Hold('B5_INTAKE_PENDING_OR_UNKNOWN_NO_REPOST')
    return {'request_id': request['request_id'],
            'state': 'READY_OBSERVED_NOT_SUBMISSION_PROOF'}


def custody_set(db, policy, requests, recipient, catalog_sha, destination_root,
                destination_owner, now, clock):
    """Original Receiver/custody routine; no new DB and no inferred delivery."""
    success_set(db, policy, requests, recipient, catalog_sha, now)
    receipt = ingest_approved_batch(db, policy, destination_root,
                                    destination_owner, now, enabled=True,
                                    clock=clock)
    if (type(receipt) is not dict or receipt.get('state') !=
            'MATERIAL_CUSTODY_COMPLETE' or receipt.get('objects') != 19 or
            receipt.get('bytes') != 93592 or
            receipt.get('catalog_sha256') != catalog_sha or
            receipt.get('source_execution') is not False or
            receipt.get('analyst_receipt') != 'NOT_VERIFIED'):
        raise Hold('B5_CUSTODY_RESULT_UNKNOWN')
    return receipt


def original_archive_proof(policy, archive_root_ref, size, digest):
    """Original full-archive SHA and selected member verification, no writes."""
    if (type(policy) is not ApprovedObjectsPolicy or
            type(archive_root_ref) is not str or
            type(size) is not int or type(digest) is not str or
            archive_root_ref not in policy.binding.get('archives', {}) or
            archive_root_ref not in policy.binding['roots']):
        raise Hold('B5_ARCHIVE_BINDING')
    plan = policy.binding['archives'][archive_root_ref]
    if (plan['identity'][6] != size or plan['sha256'] != digest or
            sum(x['root_ref'] == archive_root_ref for x in
                policy.catalog.objects.values()) > 5):
        raise Hold('B5_ARCHIVE_IDENTITY')
    root, owner = policy.binding['roots'][archive_root_ref]
    items = [x for x in policy.catalog.objects.values()
             if x['root_ref'] == archive_root_ref]
    if not items:
        raise Hold('B5_ARCHIVE_EMPTY')
    found = read_archive_members(root, owner, items, plan)
    if set(found) != {x['ref'] for x in items}:
        raise Hold('B5_ARCHIVE_MEMBERS')
    return {'whole_sha_verified': True, 'source_bytes': size,
            'sha256': digest, 'member_count':len(items)}


def complete_original_chunk(resource, authorization, arguments, request, item,
                            policy, db, now):
    """One original OAuth read, one fully bound chunk, no EOF probe.

    In production `authorization` must originate from the original request
    accessor, never arguments, env, CLI or a caller-supplied recipient.
    """
    if type(resource) is not OAuthProjectResource or type(policy) is not ApprovedObjectsPolicy:
        raise Hold('B5_ORIGINAL_OAUTH_RESOURCE_REQUIRED')
    if (type(arguments) is not dict or set(arguments) !=
            {'manifest_sha256', 'request_id', 'object_ref', 'offset'} or
            type(arguments['offset']) is not int or arguments['offset'] != 0 or
            type(request) is not dict or type(item) is not dict):
        raise Hold('B5_ONE_CHUNK_ARGUMENTS')
    expected = policy.request_object(request)
    if (item.get('bytes') != expected['bytes'] or
            item.get('sha256') != expected['sha256'] or
            item.get('relative_path') != expected['relative_path'] or
            arguments['manifest_sha256'] != policy.catalog.sha or
            arguments['request_id'] != request['request_id'] or
            arguments['object_ref'] != expected['ref'] or
            type(expected['bytes']) is not int or expected['bytes'] > 65536):
        raise Hold('B5_ONE_CHUNK_BINDING')
    # The original resource authenticates the bearer with project.files.read
    # and derives recipient from its protected subject mapping.
    envelope = resource.read(authorization, arguments, now)
    recipient = resource.authenticator.authenticate(
        authorization, 'project.files.read', policy.catalog.value['project'], now)
    if recipient != policy.binding['recipient_id']:
        raise Hold('B5_AUTHENTICATED_RECIPIENT')
    invoke = bound_job(db, policy.catalog, request['request_id'], expected['ref'], recipient)
    fields = {'manifest_sha256', 'project', 'request_id', 'object_ref',
              'recipient_id', 'invoke_id', 'bytes', 'sha256', 'offset',
              'chunk_sha256', 'data'}
    pinned = {'manifest_sha256': policy.catalog.sha,
              'project': policy.catalog.value['project'],
              'request_id': request['request_id'], 'object_ref': expected['ref'],
              'recipient_id': recipient, 'invoke_id': invoke,
              'bytes': expected['bytes'], 'sha256': expected['sha256'], 'offset': 0}
    if (type(envelope) is not dict or set(envelope) != fields or
            any(envelope.get(k) != v or (k in ('bytes', 'offset') and
            type(envelope[k]) is not int) for k, v in pinned.items()) or
            type(envelope.get('data')) is not str or
            type(envelope.get('chunk_sha256')) is not str):
        raise Hold('B5_CHUNK_ENVELOPE_BINDING')
    try:
        raw = base64.b64decode(envelope['data'].encode('ascii'), validate=True)
    except (UnicodeError, ValueError, binascii.Error):
        raise Hold('B5_CHUNK_BASE64') from None
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) != expected['bytes'] or digest != envelope['chunk_sha256'] or digest != expected['sha256']:
        raise Hold('B5_CHUNK_WHOLE_SHA')
    return raw
