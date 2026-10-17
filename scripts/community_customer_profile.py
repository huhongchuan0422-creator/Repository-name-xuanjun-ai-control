"""Customer profile, explicit referrals and private in-app notices in Center."""
import hashlib
import json
import re
import secrets
from scripts.pr122_customer_core import canonical


def notify(center, project, user_id, kind, reference, message):
    """Internal transaction participant; never sends external messages."""
    key = hashlib.sha256(canonical([project, user_id, kind, reference])).hexdigest()
    row = center.db.execute("SELECT 1 FROM links WHERE channel='COMMUNITY_NOTICE_V1' AND subject_idx=? AND project=?", (key, project)).fetchone()
    if row is None:
        value = dict(id=key, kind=kind, reference=reference, message=message, read=False, created_at=center.now())
        center.db.execute("INSERT INTO links VALUES('COMMUNITY_NOTICE_V1',?,?,?,?,1)", (key, user_id, project, center.encrypt(canonical(value), 'community-notice:' + key)))


class CustomerProfile:
    module = {'id': 'XJ-CUSTOMER-PROFILE-001', 'version': '1.0.0', 'author': '玄钧AI实验室',
              'dependencies': ['original-center'], 'description': 'Profiles, opt-in referral binding and private notices'}

    def __init__(self, communities=None, *, identity=None):
        from scripts.community_center_communities import CenterCommunities
        from scripts.community_mini_center_identity import CenterIdentity
        if (communities is None)==(identity is None) or communities is not None and type(communities) is not CenterCommunities or identity is not None and type(identity) is not CenterIdentity:raise ValueError('ONE_ORIGINAL_IDENTITY_BOUNDARY_REQUIRED')
        self.communities,self.identity=communities,identity
        self.center=communities.center if communities is not None else identity.center

    def _read(self, g, kind, key):
        row = self.center.db.execute('SELECT user_id,payload FROM links WHERE channel=? AND subject_idx=? AND project=? AND active=1', (kind, key, g['project'])).fetchone()
        return None if row is None else (row[0], json.loads(self.center.decrypt(row[1], kind + ':' + key)))

    def dispatch(self, session, csrf, workspace, op, p):
        fields = {'profile_read': set(), 'profile_update': {'nickname', 'contact', 'expected_version'},
                  'referral_code': set(), 'referral_bind': {'code'}, 'notices': {'after_id'}, 'notice_read': {'notice_id'}}
        if op not in fields or type(p) is not dict or set(p) != fields[op]:
            raise ValueError('INVALID_CUSTOMER_PROFILE_FIELDS')
        if self.communities is None:raise PermissionError('WEB_PROFILE_BOUNDARY_REQUIRED')
        g = self.communities.authorize(session, csrf, workspace)
        return self._run(g,op,p)

    def consumer(self,token,scene,op,p):
        if self.identity is None:raise PermissionError('MINI_PROFILE_BOUNDARY_REQUIRED')
        fields={'profile_read':set(),'profile_update':{'nickname','contact','expected_version'},'referral_code':set(),'referral_bind':{'code'},'notices':{'after_id'},'notice_read':{'notice_id'}}
        if type(op) is not str or op not in fields or type(p) is not dict or set(p)!=fields[op]:raise ValueError('INVALID_CUSTOMER_PROFILE_FIELDS')
        self.identity._time(self.center.now())
        uid,project,principal=self.identity._resolve(token,scene)
        return self._run(dict(user_id=uid,project=project,tenant=principal.tenant_id),op,p)

    def _run(self,g,op,p):
        c, uid = self.center, g['user_id']
        user_key = c.idx('community-profile:' + g['project'] + ':' + uid)
        with c.tx():
            c.limit('community-profile:' + uid, 60, 60)
            if op in ('profile_read', 'profile_update'):
                prior = self._read(g, 'COMMUNITY_CUSTOMER_PROFILE', user_key)
                record = prior[1] if prior else dict(user_id=uid, nickname='', contact='', version=0)
                if prior and prior[0] != uid:
                    raise PermissionError('PROFILE_OWNER_REQUIRED')
                if op == 'profile_update':
                    if (type(p['expected_version']) is not int or p['expected_version'] != record['version']
                            or any(type(p[k]) is not str or len(p[k]) > maximum or any(ord(ch) < 32 for ch in p[k]) for k, maximum in (('nickname', 80), ('contact', 200)))):
                        raise ValueError('INVALID_PROFILE_OR_VERSION')
                    record = dict(user_id=uid, nickname=p['nickname'], contact=p['contact'], version=record['version']+1)
                    c.db.execute("INSERT INTO links VALUES('COMMUNITY_CUSTOMER_PROFILE',?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload", (user_key, uid, g['project'], c.encrypt(canonical(record), 'COMMUNITY_CUSTOMER_PROFILE:' + user_key)))
                # Original CRM-authorized project provides the customer identifier.
                project, _, _ = c.project(uid, g['project'], ('OWNER', 'EDITOR', 'REVIEWER'))
                result = dict(record, tenant_id=project['tenant'], project_customer_id=project['customer'])
                referral = self._read(g, 'COMMUNITY_CUSTOMER_REFERRER', user_key)
                result['referrer_user_id'] = referral[1]['referrer_user_id'] if referral else None
            elif op == 'referral_code':
                prior = self._read(g, 'COMMUNITY_REFERRAL_OWNER', user_key)
                if prior:
                    result = prior[1]
                else:
                    code = secrets.token_urlsafe(24)
                    result = dict(code=code)
                    c.db.execute("INSERT INTO links VALUES('COMMUNITY_REFERRAL_OWNER',?,?,?,?,1)", (user_key, uid, g['project'], c.encrypt(canonical(result), 'COMMUNITY_REFERRAL_OWNER:' + user_key)))
                    code_key = c.idx('community-referral:' + code)
                    c.db.execute("INSERT INTO links VALUES('COMMUNITY_REFERRAL_CODE',?,?,?,?,1)", (code_key, uid, g['project'], c.encrypt(canonical(dict(tenant=g['tenant'])), 'COMMUNITY_REFERRAL_CODE:' + code_key)))
            elif op == 'referral_bind':
                if type(p['code']) is not str or not re.fullmatch('[A-Za-z0-9_-]{32}', p['code']):
                    raise ValueError('INVALID_REFERRAL_CODE')
                code_key = c.idx('community-referral:' + p['code'])
                source = self._read(g, 'COMMUNITY_REFERRAL_CODE', code_key)
                if source is None or source[0] == uid or source[1]['tenant'] != g['tenant']:
                    raise PermissionError('VALID_SAME_PROJECT_REFERRER_REQUIRED')
                c.project(source[0], g['project'], ('OWNER', 'EDITOR', 'REVIEWER'))
                prior = self._read(g, 'COMMUNITY_CUSTOMER_REFERRER', user_key)
                if prior:
                    if prior[1]['referrer_user_id'] != source[0]:
                        raise PermissionError('REFERRER_ALREADY_BOUND')
                    result = prior[1]
                else:
                    cursor = source[0]
                    for _ in range(100):
                        if cursor == uid:
                            raise PermissionError('REFERRAL_CYCLE_DENIED')
                        parent = self._read(g, 'COMMUNITY_CUSTOMER_REFERRER', c.idx('community-profile:' + g['project'] + ':' + cursor))
                        if parent is None:
                            break
                        cursor = parent[1]['referrer_user_id']
                    else:
                        raise ValueError('REFERRAL_DEPTH_REQUIRES_REVIEW')
                    result = dict(referrer_user_id=source[0], bound_at=c.now())
                    c.db.execute("INSERT INTO links VALUES('COMMUNITY_CUSTOMER_REFERRER',?,?,?,?,1)", (user_key, uid, g['project'], c.encrypt(canonical(result), 'COMMUNITY_CUSTOMER_REFERRER:' + user_key)))
            elif op == 'notices':
                after = p['after_id']
                if type(after) is not str or after and not re.fullmatch('[0-9a-f]{64}', after):
                    raise ValueError('INVALID_NOTICE_CURSOR')
                rows = c.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_NOTICE_V1' AND user_id=? AND project=? AND active=1 AND subject_idx>? ORDER BY subject_idx LIMIT 51", (uid, g['project'], after)).fetchall()
                result = dict(records=[json.loads(c.decrypt(r[1], 'community-notice:' + r[0])) for r in rows[:50]], has_more=len(rows)>50, next_cursor=rows[49][0] if len(rows)>50 else None)
            else:
                key = p['notice_id']
                if type(key) is not str or not re.fullmatch('[0-9a-f]{64}', key):
                    raise ValueError('INVALID_NOTICE_ID')
                row = c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_NOTICE_V1' AND subject_idx=? AND project=? AND user_id=? AND active=1", (key, g['project'], uid)).fetchone()
                if row is None:
                    raise PermissionError('OWN_NOTICE_REQUIRED')
                result = dict(json.loads(c.decrypt(row[0], 'community-notice:' + key)), read=True)
                c.db.execute("UPDATE links SET payload=? WHERE channel='COMMUNITY_NOTICE_V1' AND subject_idx=? AND project=? AND user_id=?", (c.encrypt(canonical(result), 'community-notice:' + key), key, g['project'], uid))
            c.audit(g['project'], uid, 'CUSTOMER_' + op.upper(), user_key)
        return result
