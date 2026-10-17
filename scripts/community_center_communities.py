"""Community registration, review and membership in the original encrypted Center.

Uses original accounts/projects/links/audit, not a second identity database.
Membership never authorizes payouts or changes merchant permissions.
"""
import hashlib
import json
import re
import secrets
from scripts.pr122_customer_core import Center, canonical

CHANNEL = 'COMMUNITY_DIRECTORY_V1'
MEMBERS = 'COMMUNITY_RELATION_V1'


def text(value, maximum, required=True):
    if type(value) is not str or len(value) > maximum or (required and not value.strip()) or any(ord(c) < 32 for c in value):
        raise ValueError('INVALID_COMMUNITY_TEXT')
    return value.strip()


class CenterCommunities:
    module = {'id': 'XJ-COMMUNITY-DIRECTORY-001', 'version': '1.0.0',
              'author': '玄钧AI实验室', 'dependencies': ['original-center'],
              'description': 'Community review and explicit customer/merchant relationships'}

    def __init__(self, center, grants):
        if type(center) is not Center or type(grants) is not dict or not grants:
            raise ValueError('ORIGINAL_CENTER_AND_PROTECTED_GRANTS_REQUIRED')
        self.commerce=None;self.provider_actions=None
        self.center = center
        self.grants = {}
        for name, grant in grants.items():
            if (type(name) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}', name)
                    or type(grant) is not dict or set(grant) != {'user_id', 'project', 'tenant', 'role'}
                    or grant['role'] not in ('CUSTOMER', 'COMMUNITY_ADMIN', 'MERCHANT_ADMIN', 'PLATFORM_REVIEWER', 'PLATFORM_OWNER')
                    or any(type(grant[k]) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}', grant[k]) for k in ('user_id', 'project', 'tenant'))):
                raise ValueError('INVALID_COMMUNITY_GRANT')
            self.grants[name] = dict(grant)

    def authorize(self, session, csrf, workspace):
        if type(csrf) is not str or not csrf:
            raise PermissionError('CENTER_CSRF_REQUIRED')
        uid = self.center.session(session, csrf)
        grant = self.grants.get(workspace)
        if grant is None or grant['user_id'] != uid:
            raise PermissionError('COMMUNITY_WORKSPACE_REQUIRED')
        roles = ('OWNER',) if grant['role'] == 'PLATFORM_OWNER' else ('OWNER', 'EDITOR', 'REVIEWER')
        project, _, _ = self.center.project(uid, grant['project'], roles)
        if project['tenant'] != grant['tenant']:
            raise PermissionError('COMMUNITY_TENANT_DENIED')
        return grant

    def key(self, tenant, reference):
        return hashlib.sha256(canonical([tenant, reference])).hexdigest()

    def read(self, grant, reference):
        if type(reference) is not str or not re.fullmatch('co_[0-9a-f]{32}', reference):
            raise ValueError('INVALID_COMMUNITY_ID')
        key = self.key(grant['tenant'], reference)
        row = self.center.db.execute('SELECT payload FROM links WHERE channel=? AND subject_idx=? AND project=? AND active=1',
            (CHANNEL, key, grant['project'])).fetchone()
        if row is None:
            raise PermissionError('COMMUNITY_NOT_ACCESSIBLE')
        record = json.loads(self.center.decrypt(row[0], 'community-directory:' + key))
        if record['tenant'] != grant['tenant']:
            raise PermissionError('COMMUNITY_TENANT_DENIED')
        return record

    def write(self, grant, record, previous=None):
        c = self.center
        key = self.key(grant['tenant'], record['id'])
        payload = c.encrypt(canonical(record), 'community-directory:' + key)
        if previous is None:
            c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)', (CHANNEL, key, record['owner'], grant['project'], payload))
        else:
            current = self.read(grant, record['id'])
            if current != previous:
                raise ValueError('COMMUNITY_VERSION_CONFLICT')
            changed = c.db.execute('UPDATE links SET payload=? WHERE channel=? AND subject_idx=? AND project=? AND active=1',
                (payload, CHANNEL, key, grant['project']))
            if changed.rowcount != 1:
                raise ValueError('COMMUNITY_VERSION_CONFLICT')

    def dispatch(self, session, csrf, body):
        if type(body) is dict and set(body)=={'workspace','operation','params'} and type(body['operation']) is str and body['operation'] in ('platform_overview','platform_orders','platform_customers','platform_audit'):
            if self.commerce is None:raise PermissionError('ORIGINAL_COMMUNITY_COMMERCE_REQUIRED')
            from scripts.community_platform_views import PlatformViews
            return PlatformViews(self).dispatch(session,csrf,body)
        if type(body) is dict and set(body)=={'workspace','operation','params'} and type(body['operation']) is str and body['operation'] in ('promotion_create','promotions','promotion_state'):
            if self.commerce is None:raise PermissionError('ORIGINAL_COMMUNITY_COMMERCE_REQUIRED')
            from scripts.community_consumer_communities import CommunityPromotions
            return CommunityPromotions(self).dispatch(session,csrf,body)
        if type(body) is dict and set(body)=={'workspace','operation','params'} and type(body['operation']) is str and body['operation'] in ('platform_merchants','platform_merchant_state'):
            if self.commerce is None:raise PermissionError('ORIGINAL_COMMUNITY_COMMERCE_REQUIRED')
            from scripts.community_platform_merchants import PlatformMerchants
            return PlatformMerchants(self).dispatch(session,csrf,body)
        if type(body) is dict and set(body)=={'workspace','operation','params'} and type(body['operation']) is str and body['operation'] in ('community_orders','community_earnings','community_receiver_bind'):
            if self.commerce is None:raise PermissionError('ORIGINAL_COMMUNITY_COMMERCE_REQUIRED')
            from scripts.community_reports import CommunityReports
            return CommunityReports(self,self.commerce,self.provider_actions).dispatch(session,csrf,body)
        if type(body) is dict and set(body)=={'workspace','operation','params'} and type(body['operation']) is str and body['operation'] in ('profile_read','profile_update','referral_code','referral_bind','notices','notice_read'):
            from scripts.community_customer_profile import CustomerProfile
            return CustomerProfile(self).dispatch(session,csrf,body['workspace'],body['operation'],body['params'])
        fields = {'register': {'name', 'description', 'contact'},
                  'update': {'community_id', 'expected_version', 'name', 'description', 'contact'},
                  'submit': {'community_id', 'expected_version'},
                  'review': {'community_id', 'expected_version', 'decision', 'opinion'},
                  'status': {'community_id'}, 'list': {'after_id', 'status'},
                  'join': {'community_id', 'kind'}, 'leave': {'community_id', 'kind'},
                  'members': {'community_id', 'after_id'}, 'mine': {'after_id'}}
        if type(body) is not dict or set(body) != {'workspace', 'operation', 'params'}:
            raise ValueError('INVALID_COMMUNITY_REQUEST')
        op, p = body['operation'], body['params']
        if (type(op) is not str or op not in fields or type(p) is not dict
                or (set(p) != fields[op] and not (op == 'mine' and not p))):
            raise ValueError('INVALID_COMMUNITY_FIELDS')
        g = self.authorize(session, csrf, body['workspace'])
        c = self.center
        platform = g['role'] in ('PLATFORM_REVIEWER', 'PLATFORM_OWNER')
        # Authorization, version checks and writes share the original Center transaction.
        with c.tx():
            c.limit('community-directory:' + g['user_id'], 60, 60)
            if op == 'register':
                if g['role'] != 'COMMUNITY_ADMIN':
                    raise PermissionError('COMMUNITY_ADMIN_REQUIRED')
                rows = c.db.execute('SELECT subject_idx FROM links WHERE channel=? AND user_id=? AND project=? AND active=1 LIMIT 101',
                    (CHANNEL, g['user_id'], g['project'])).fetchall()
                if len(rows) >= 100:
                    raise ValueError('COMMUNITY_REGISTRATION_LIMIT')
                result = dict(id='co_' + secrets.token_hex(16), tenant=g['tenant'], owner=g['user_id'],
                    name=text(p['name'], 120), description=text(p['description'], 2000, False),
                    contact=text(p['contact'], 200), state='DRAFT', version=1, opinion='', updated_at=c.now())
                self.write(g, result)
            elif op in ('list', 'mine'):
                after = p.get('after_id', '')
                if type(after) is not str or after and not re.fullmatch('[0-9a-f]{64}', after):
                    raise ValueError('INVALID_COMMUNITY_CURSOR')
                if op == 'list' and not platform:
                    raise PermissionError('COMMUNITY_REVIEWER_REQUIRED')
                status = p.get('status', 'ALL')
                if status not in ('ALL', 'DRAFT', 'PENDING', 'CORRECTION', 'REJECTED', 'APPROVED', 'PAUSED'):
                    raise ValueError('INVALID_COMMUNITY_STATUS')
                sql = 'SELECT subject_idx,payload FROM links WHERE channel=? AND project=? AND active=1 AND subject_idx>?'
                args = [CHANNEL, g['project'], after]
                if op == 'mine':
                    sql += ' AND user_id=?'
                    args.append(g['user_id'])
                rows = c.db.execute(sql + ' ORDER BY subject_idx LIMIT 51', args).fetchall()
                records = [json.loads(c.decrypt(r[1], 'community-directory:' + r[0])) for r in rows[:50]]
                result = dict(records=[r for r in records if r['tenant'] == g['tenant'] and (status == 'ALL' or r['state'] == status)],
                    has_more=len(rows) > 50, next_cursor=rows[49][0] if len(rows) > 50 else None)
            else:
                record = self.read(g, p['community_id'])
                owner = record['owner'] == g['user_id'] and g['role'] == 'COMMUNITY_ADMIN'
                if op == 'status':
                    if not (owner or platform) and record['state'] != 'APPROVED':
                        raise PermissionError('COMMUNITY_PRIVATE')
                    result = record if owner or platform else {k: record[k] for k in ('id', 'name', 'description', 'state', 'version')}
                elif op in ('update', 'submit', 'review'):
                    if type(p['expected_version']) is not int or p['expected_version'] != record['version']:
                        raise ValueError('COMMUNITY_VERSION_CONFLICT')
                    result = dict(record, version=record['version'] + 1, updated_at=c.now())
                    if op == 'review':
                        if not platform or record['owner'] == g['user_id']:
                            raise PermissionError('INDEPENDENT_COMMUNITY_REVIEWER_REQUIRED')
                        transitions = {'PENDING': ('APPROVED', 'CORRECTION', 'REJECTED'),
                                       'APPROVED': ('PAUSED',), 'PAUSED': ('APPROVED', 'CORRECTION')}
                        if p['decision'] not in transitions.get(record['state'], ()):
                            raise ValueError('INVALID_COMMUNITY_REVIEW_TRANSITION')
                        result.update(state=p['decision'], opinion=text(p['opinion'], 1000))
                    else:
                        if not owner or record['state'] not in ('DRAFT', 'CORRECTION', 'REJECTED'):
                            raise PermissionError('COMMUNITY_OWNER_EDIT_DENIED')
                        if op == 'submit':
                            result.update(state='PENDING', opinion='')
                        else:
                            result.update(name=text(p['name'], 120), description=text(p['description'], 2000, False), contact=text(p['contact'], 200))
                    self.write(g, result, record)
                    if op=='review':
                        from scripts.community_customer_profile import notify
                        notify(c,g['project'],record['owner'],'COMMUNITY_REVIEW',record['id']+':'+str(result['version']),result['state']+'：'+result['opinion'])
                elif op in ('join', 'leave'):
                    if p['kind'] not in ('CUSTOMER', 'MERCHANT') or g['role'] != {'CUSTOMER': 'CUSTOMER', 'MERCHANT': 'MERCHANT_ADMIN'}[p['kind']]:
                        raise PermissionError('COMMUNITY_RELATION_ROLE_DENIED')
                    if op == 'join' and record['state'] != 'APPROVED':
                        raise PermissionError('APPROVED_COMMUNITY_REQUIRED')
                    # One active community per member kind/project; replacement is explicit leave/join.
                    member_key = self.key(g['tenant'], p['kind'] + ':' + g['user_id'])
                    old = c.db.execute('SELECT payload,active FROM links WHERE channel=? AND subject_idx=? AND project=?',
                        (MEMBERS, member_key, g['project'])).fetchone()
                    if old:
                        prior = json.loads(c.decrypt(old[0], 'community-relation:' + member_key))
                        if old[1] and prior['community_id'] != record['id']:
                            raise ValueError('LEAVE_EXISTING_COMMUNITY_FIRST')
                        if op == 'leave' and prior['community_id'] != record['id']:
                            raise PermissionError('COMMUNITY_MEMBERSHIP_REQUIRED')
                    elif op == 'leave':
                        raise PermissionError('COMMUNITY_MEMBERSHIP_REQUIRED')
                    relation = dict(community_id=record['id'], tenant=g['tenant'], user_id=g['user_id'], kind=p['kind'], updated_at=c.now())
                    c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,?) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload,active=excluded.active',
                        (MEMBERS, member_key, g['user_id'], g['project'], c.encrypt(canonical(relation), 'community-relation:' + member_key), int(op == 'join')))
                    result = dict(community_id=record['id'], active=op == 'join')
                elif op == 'members':
                    if not (owner or platform):
                        raise PermissionError('COMMUNITY_MEMBERS_PRIVATE')
                    after = p['after_id']
                    if type(after) is not str or after and not re.fullmatch('[0-9a-f]{64}', after):
                        raise ValueError('INVALID_RELATION_CURSOR')
                    rows = c.db.execute('SELECT subject_idx,payload FROM links WHERE channel=? AND project=? AND active=1 AND subject_idx>? ORDER BY subject_idx LIMIT 51',
                        (MEMBERS, g['project'], after)).fetchall()
                    relations = [json.loads(c.decrypt(r[1], 'community-relation:' + r[0])) for r in rows[:50]]
                    result = dict(records=[r for r in relations if r['tenant'] == g['tenant'] and r['community_id'] == record['id']],
                        has_more=len(rows) > 50, next_cursor=rows[49][0] if len(rows) > 50 else None)
                else:
                    raise ValueError('UNKNOWN_COMMUNITY_OPERATION')
            c.audit(g['project'], g['user_id'], 'COMMUNITY_DIRECTORY_' + op.upper(), hashlib.sha256(canonical(body)).hexdigest())
        return result
