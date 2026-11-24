"""GEO domain in the original Center, not a second identity/backend service.
No provider calls. Signed entitlement admission is protected operator-only.
"""
import hashlib
import hmac
import json
from scripts.pr122_customer_core import Denied, Conflict, Unavailable, canonical, identifier, safe_text

ACTIONS = ('SAVE_BRAND', 'REFRESH_DIAGNOSIS', 'ADVANCE_OPTIMIZATION',
           'ADD_VERSION_COMMENT', 'APPROVE_VERSION', 'CREATE_NEXT_ROUND')
DDL = '''
CREATE TABLE IF NOT EXISTS geo_authority(project TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS geo_brand(project TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS geo_commands(project TEXT NOT NULL, actor TEXT NOT NULL, request_id TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL, result BLOB, PRIMARY KEY(project,actor,request_id));
'''

def install(center):
    center.db.executescript(DDL)
    center.geo = Geo(center)
    return center.geo

def import_authority(center, document, key):
    """Same authority signing key/convention as original import-authority.
    No browser grant API. Per-project monotonic signed entitlement, never inferred
    from membership, email, UI plan text or fabricated provider responses.
    """
    if type(key) is not bytes or len(key) < 32 or type(document) is not dict or set(document) != {'payload', 'signature'}:
        raise Denied('GEO_AUTHORITY_REQUIRED')
    data = document['payload']
    if type(document['signature']) is not str or not hmac.compare_digest(hmac.new(key, canonical(data), hashlib.sha256).hexdigest(), document['signature']):
        raise Denied('GEO_AUTHORITY_SIGNATURE')
    fields = {'project_id', 'tenant_id', 'customer_id', 'revision', 'enabled', 'plan', 'valid_until', 'quota', 'remaining', 'source_ref'}
    if type(data) is not dict or set(data) != fields:
        raise ValueError('GEO_AUTHORITY_FIELDS')
    for k in ('project_id', 'tenant_id', 'customer_id', 'source_ref'):
        identifier(data[k])
    if type(data['revision']) is not int or data['revision'] < 1 or type(data['enabled']) is not bool:
        raise ValueError('GEO_AUTHORITY_REVISION')
    if type(data['valid_until']) is not int or data['valid_until'] <= center.now():
        raise Denied('GEO_AUTHORITY_EXPIRED')
    safe_text(data['plan'], 150)
    if any(type(data[k]) is not int or data[k] < 0 for k in ('quota', 'remaining')) or data['remaining'] > data['quota']:
        raise ValueError('GEO_QUOTA')
    with center.tx():
        p = center.db.execute('SELECT * FROM projects WHERE id=? AND active=1', (data['project_id'],)).fetchone()
        if not p or p['expires'] <= center.now() or (p['tenant'], p['customer']) != (data['tenant_id'], data['customer_id']):
            raise Denied('GEO_AUTHORITY_SUBJECT')
        old = center.db.execute('SELECT revision FROM geo_authority WHERE project=?', (p['id'],)).fetchone()
        if old and old[0] >= data['revision']:
            raise Conflict('GEO_AUTHORITY_REPLAY')
        center.db.execute('INSERT OR REPLACE INTO geo_authority VALUES(?,?,?)', (p['id'], data['revision'], center.encrypt(canonical(data), 'geo-authority:'+p['id'])))
        center.audit(p['id'], 'authority', 'GEO_AUTHORITY_SYNC', str(data['revision']))
    return {'project_id': data['project_id'], 'revision': data['revision']}

class Geo:
    def __init__(self, center):
        self.c = center

    def subject(self, uid, body, write=False):
        p, role, _ = self.c.project(uid, body['project_id'], ('OWNER', 'EDITOR') if write else ('OWNER', 'EDITOR', 'VIEWER'))
        if p['tenant'] != body['tenant_id'] or ('customer_id' in body and body['customer_id'] != p['customer']):
            raise Denied('GEO_SUBJECT_MISMATCH')
        return p, role

    def entitlement(self, p):
        row = self.c.db.execute('SELECT payload FROM geo_authority WHERE project=?', (p['id'],)).fetchone()
        missing = {'enabled':False, 'plan':None, 'valid_until':None, 'quota':None, 'remaining':None, 'source_ref':None}
        if not row:
            return missing
        data = json.loads(self.c.decrypt(row[0], 'geo-authority:'+p['id']))
        if (data['tenant_id'],data['customer_id']) != (p['tenant'],p['customer']):
            raise Denied('GEO_AUTHORITY_SUBJECT')
        return {**{k:data[k] for k in missing}, 'enabled':data['enabled'] and data['valid_until'] > self.c.now()}

    def snapshot(self, uid, body):
        if type(body) is not dict or set(body) != {'project_id','tenant_id','customer_id'}:
            raise ValueError('GEO_SNAPSHOT_FIELDS')
        with self.c.tx():
            p, role = self.subject(uid, body)
            ent = self.entitlement(p)
            actions = {k:False for k in ACTIONS}
            actions['SAVE_BRAND'] = ent['enabled'] and role in ('OWNER','EDITOR')
            result = {'tenant_id':p['tenant'], 'project_id':p['id'], 'customer_id':p['customer'], 'connection':'CONNECTED', 'entitlement':ent, 'actions':actions,
                      'approval_required':False, 'approval_state':'UNKNOWN'}
            if ent['enabled']:
                result['usage'] = {'status':'READY', 'plan':ent['plan'], 'quota':ent['quota'], 'remaining':ent['remaining'], 'used':ent['quota']-ent['remaining'], 'valid_until':ent['valid_until'], 'source':ent['source_ref']}
            row = self.c.db.execute('SELECT revision,payload FROM geo_brand WHERE project=?', (p['id'],)).fetchone()
            if row and ent['enabled']:
                result['brand'] = {**json.loads(self.c.decrypt(row['payload'], 'geo-brand:'+p['id'])), 'status':'READY', 'revision':row['revision']}
            # Missing real sampling/version/usage providers stay missing, not mock READY.
            for domain in ('diagnosis','task','versions','results','next_round','billing_usage'):
                result[domain] = {'status':'NOT_CONNECTED'}
            row = self.c.db.execute('SELECT request_id,state FROM geo_commands WHERE project=? AND actor=? ORDER BY rowid DESC LIMIT 1', (p['id'],uid)).fetchone()
            result['last_command'] = dict(row) if row else None
            return result

    def command(self, uid, body):
        required = {'type','project_id','tenant_id','idempotency_key'}
        if type(body) is not dict or not required <= set(body) or set(body)-required-{'form','args','comment'}:
            raise ValueError('GEO_COMMAND_FIELDS')
        identifier(body['idempotency_key'])
        if body['type'] not in ACTIONS:
            raise ValueError('GEO_COMMAND_TYPE')
        with self.c.tx():
            p, role = self.subject(uid, body, True)
            if not self.entitlement(p)['enabled']:
                raise Denied('GEO_ENTITLEMENT_REQUIRED')
            digest = hashlib.sha256(canonical(body)).hexdigest()
            old = self.c.db.execute('SELECT * FROM geo_commands WHERE project=? AND actor=? AND request_id=?', (p['id'],uid,body['idempotency_key'])).fetchone()
            if old:
                if old['digest'] != digest:
                    raise Conflict('GEO_IDEMPOTENCY_CONFLICT')
                if old['state'] != 'SUCCEEDED':
                    return {'state':'UNKNOWN','query_required':True,'idempotency_key':body['idempotency_key']}
                return json.loads(self.c.decrypt(old['result'], 'geo-command:'+p['id']+':'+uid+':'+body['idempotency_key']))
            if self.c.db.execute("SELECT 1 FROM geo_commands WHERE project=? AND actor=? AND state!='SUCCEEDED'", (p['id'],uid)).fetchone():
                raise Conflict('GEO_UNKNOWN_QUERY_REQUIRED')
            if body['type'] != 'SAVE_BRAND':
                # No real executor/version authority bound. Do not queue fake work,
                # grant approval, publish or mark sampling/optimization successful.
                raise Unavailable('GEO_DOMAIN_NOT_CONNECTED')
            form = body.get('form')
            if type(form) is not dict or set(form) != {'name','website'}:
                raise ValueError('GEO_BRAND_FIELDS')
            safe_text(form['name'],150)
            if form['website'] != '':safe_text(form['website'],2000)
            if not form['name'].strip() or (form['website'] and not form['website'].startswith('https://')):
                raise ValueError('GEO_BRAND_INPUT')
            old_brand = self.c.db.execute('SELECT revision FROM geo_brand WHERE project=?', (p['id'],)).fetchone()
            revision = old_brand[0]+1 if old_brand else 1
            self.c.db.execute('INSERT OR REPLACE INTO geo_brand VALUES(?,?,?)', (p['id'],revision,self.c.encrypt(canonical(form), 'geo-brand:'+p['id'])))
            result = {'state':'SUCCEEDED','revision':revision,'idempotency_key':body['idempotency_key']}
            self.c.db.execute('INSERT INTO geo_commands VALUES(?,?,?,?,?,?)', (p['id'],uid,body['idempotency_key'],digest,'SUCCEEDED',self.c.encrypt(canonical(result), 'geo-command:'+p['id']+':'+uid+':'+body['idempotency_key'])))
            self.c.audit(p['id'],uid,'GEO_BRAND_SAVED',body['idempotency_key'])
            return result

    def handle(self, uid, method, operation, body):
        if method != 'POST':
            return 405, {'error':'POST_REQUIRED'}
        if operation == 'geo/snapshot':
            return 200, self.snapshot(uid,body)
        if operation == 'geo/command':
            result = self.command(uid,body)
            return (202 if result['state']=='UNKNOWN' else 200), result
        return 404, {'error':'NOT_FOUND'}
