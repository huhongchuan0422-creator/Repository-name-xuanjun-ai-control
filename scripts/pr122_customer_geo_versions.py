"""Read-only GEO projection of an explicitly bound canonical accepted version.
No new version ledger, signer, client-selected document or publication action.
"""
import json
from scripts.pr122_customer_core import Denied, identifier
from scripts.pr122_customer_change_authority import load


def accepted_version(center, project):
    row = center.db.execute('SELECT payload FROM geo_authority WHERE project=?', (project['id'],)).fetchone()
    if not row:
        return {'status':'NOT_CONNECTED', 'reason':'GEO_AUTHORITY_NOT_ADMITTED'}
    grant = json.loads(center.decrypt(row[0], 'geo-authority:'+project['id']))
    document_id = grant.get('version_document_id')
    if document_id is None:
        return {'status':'NOT_CONNECTED', 'reason':'VERSION_DOCUMENT_BINDING_REQUIRED'}
    identifier(document_id)
    try:
        source = load(center)
    except Denied as error:
        if str(error) in ('CHANGE_AUTHORITY_NOT_CONNECTED','CHANGE_AUTHORITY_EXPIRED'):
            return {'status':'NOT_CONNECTED', 'reason':str(error)}
        raise
    record = next((d for d in source['documents'] if d['id']==document_id), None)
    if record is None:
        return {'status':'NOT_CONNECTED', 'reason':'BOUND_VERSION_DOCUMENT_NOT_IN_CURRENT_SOURCE'}
    # The original protected import checked actual signed document bytes, hashes,
    # owner and canonical contract. Recheck live subject/revision here, not a
    # customer's page/title or an unrelated project's newest document.
    if (record['project'] != project['id'] or record['project_revision'] != project['revision']
            or record['contract_ref'] != project['authority_ref'] or record['confirmed_by'] != project['owner']):
        raise Denied('GEO_VERSION_SOURCE_BINDING')
    if record['kind'] != 'ACCEPTED_VERSION':
        raise Denied('GEO_ACCEPTED_VERSION_REQUIRED')
    if type(record['version']) is not int or record['version'] < 1 or not 0 < record['confirmed_at'] <= center.now():
        raise Denied('GEO_VERSION_SOURCE_INVALID')
    return {'status':'READY', 'current_version':record['version'], 'confirmation_state':'APPROVED',
            'comments_status':'NOT_CONNECTED', 'publication_status':'UNKNOWN',
            'source':{'kind':'PR122_CHANGE_AUTHORITY_V1', 'authority_revision':source['revision'],
                      'project_revision':record['project_revision'], 'document_id':record['id'],
                      'document_sha256':record['document_sha256'], 'version_sha256':record['version_sha256'],
                      'confirmed_at':record['confirmed_at']}}
