"""Keyset pages of the original, authorized Center message archive.

Keep the original evidence guard and five-field customer projection. Reading a
page neither bypasses the bounded full-chain verification nor creates a second
message store, invents provider provenance, or changes historical records.
"""
import json

from scripts.community_merchant_contract import valid_id
from scripts.pr122_customer_evidence import authorized_records


def read_page(center, uid, project, params):
    if type(params) is not dict or set(params) - {'after_id'}:
        raise ValueError('INVALID_PROJECT_MESSAGE_FIELDS')
    after = params.get('after_id', '')
    if type(after) is not str or len(after) > 160:
        raise ValueError('INVALID_PROJECT_MESSAGE_CURSOR')
    cursor = None
    if after:
        try:
            cursor = json.loads(after)
        except (ValueError, TypeError):
            raise ValueError('INVALID_PROJECT_MESSAGE_CURSOR') from None
        if (type(cursor) is not list or len(cursor) != 2
                or type(cursor[0]) is not int or not -(2**53-1) <= cursor[0] <= 2**53-1
                or not valid_id(cursor[1])):
            raise ValueError('INVALID_PROJECT_MESSAGE_CURSOR')
    if not center.db.in_transaction:
        with center.tx():
            return read_page(center, uid, project, params)

    # This is also the original guard for legacy provenance, current project
    # membership, privacy policy, tenant/customer drift and corrupt ciphertext.
    # Verify every record even when the requested page would be empty.
    _, verified, heads = authorized_records(center, uid, project)
    records = {record['evidence']['message_id']: record for record in verified}
    where, args = 'project=?', [project]
    if cursor is not None:
        where += ' AND (created>? OR (created=? AND id>?))'
        args.extend((cursor[0], cursor[0], cursor[1]))
    rows = center.db.execute(
        'SELECT id,created FROM messages WHERE ' + where +
        ' ORDER BY created,id LIMIT 51', args).fetchall()
    page = []
    for row in rows[:50]:
        record = records[row['id']]
        evidence = record['evidence']
        page.append(dict(id=evidence['message_id'], channel=evidence['source_channel'],
                         body=record['body'], status=record['delivery_status'],
                         created=evidence['server_received_at']))
    center.audit(project, uid, 'MESSAGES_READ', heads.get(project, '0'*64))
    return dict(records=page, has_more=len(rows) > 50,
                next_cursor=json.dumps([rows[49]['created'], rows[49]['id']],
                                       separators=(',', ':')) if len(rows) > 50 else None,
                source='ORIGINAL_CENTER_ARCHIVE', provider_reply_verified=False)
