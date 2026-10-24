"""B5-side verification of original HTTP read_project_chunk responses.

This does not take a bearer token or call the maintenance backend. The caller
must supply the actual request-local cloud tool, and the resulting data proof
is not by itself a close approval or an authenticated tool provenance record.
"""
import base64
import binascii

from successor_contract import Hold, require, sha, canonical


FIELDS = {'manifest_sha256','project','request_id','object_ref',
          'recipient_id','invoke_id','bytes','sha256','offset',
          'chunk_sha256','data'}


def receive_all(*, requests, objects, catalog_sha, project, recipient,
                success_invokes, custody, read_project_chunk):
    require(callable(read_project_chunk), 'ORIGINAL_CLOUD_READ_NOT_BOUND')
    require(type(requests) is list and type(objects) is list and
            len(requests) == len(objects) == 19 and
            type(success_invokes) is dict and len(success_invokes) == 19,
            'B5_READ_SET')
    require(type(custody) is dict and
            custody.get('state') == 'MATERIAL_CUSTODY_COMPLETE' and
            custody.get('objects') == 19 and custody.get('bytes') == 93592 and
            custody.get('catalog_sha256') == catalog_sha,
            'B5_ORIGINAL_CUSTODY_NOT_PROVEN')
    ids = [r['request_id'] for r in requests]
    require(len(set(ids)) == 19 and set(success_invokes) == set(ids),
            'B5_INVOKE_SET')
    rows = []
    for number, (request, item) in enumerate(zip(requests, objects), 1):
        ref = 'b5-material-%02d' % number
        rid = request['request_id']
        require(request.get('project') == project and
                request.get('operation') == 'fetch_approved_object' and
                request.get('arguments') == {
                    'manifest_sha256': catalog_sha,
                    'object_ref': ref, 'recipient_id': recipient} and
                type(item.get('bytes')) is int and 0 < item['bytes'] <= 65536 and
                type(item.get('sha256')) is str and len(item['sha256']) == 64 and
                type(success_invokes[rid]) is str and success_invokes[rid],
                'B5_FIXED_REQUEST_CHANGED')
        arguments = dict(manifest_sha256=catalog_sha,request_id=rid,
                         object_ref=ref,offset=0)
        envelope = read_project_chunk(**arguments)
        pinned = dict(manifest_sha256=catalog_sha,project=project,request_id=rid,
                      object_ref=ref,recipient_id=recipient,
                      invoke_id=success_invokes[rid],bytes=item['bytes'],
                      sha256=item['sha256'],offset=0)
        require(type(envelope) is dict and set(envelope) == FIELDS and
                all(envelope[k] == value and
                    (k not in ('bytes','offset') or type(envelope[k]) is int)
                    for k,value in pinned.items()) and
                type(envelope['data']) is str and
                type(envelope['chunk_sha256']) is str,
                'B5_HTTP_ENVELOPE_BINDING')
        try:
            raw = base64.b64decode(envelope['data'].encode('ascii'),validate=True)
        except (UnicodeError, ValueError, binascii.Error):
            raise Hold('B5_HTTP_BASE64') from None
        digest = sha(raw)
        require(len(raw) == item['bytes'] and
                digest == item['sha256'] == envelope['chunk_sha256'],
                'B5_HTTP_WHOLE_SHA')
        rows.append(dict(request_id=rid,object_ref=ref,invoke_id=success_invokes[rid],
                         bytes=len(raw),sha256=digest))
    require(sum(row['bytes'] for row in rows) == 93592, 'B5_TOTAL_BYTES')
    proof = dict(catalog_sha256=catalog_sha, project=project, recipient=recipient,
                 custody_receipt_sha256=sha(canonical(custody)), rows=rows)
    return {'state': 'B5_HTTP_BYTES_VALIDATED_SOURCE_ATTESTATION_PENDING',
            'proof_sha256': sha(canonical(proof)), 'bytes': 93592, 'objects': 19,
            'close_approval': 'NOT_PROVEN', 'installation': 'NOT_EXECUTED'}
