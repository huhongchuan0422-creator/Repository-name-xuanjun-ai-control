"""Pure, bounded ACL delta planner. Never changes host permissions.

Only two access purposes are supported. Existing unrelated entries and effective
mask rights are preserved; defaults/ambiguous ACLs require reconciliation.
"""
import hashlib
import re


def parse_acl(raw):
    if not isinstance(raw,str) or len(raw.encode('utf-8'))>16384:
        raise ValueError('ACL_INPUT_BOUND')
    result={}
    for line in raw.splitlines():
        if not line.strip():continue
        if line.startswith('#'):continue
        if '#' in line or line!=line.strip():raise ValueError('ACL_AMBIGUOUS_LINE')
        parts=line.split(':')
        if len(parts)!=3:raise ValueError('ACL_SCHEMA')
        kind,identity,rights=parts
        if kind not in ('user','group','mask','other'):raise ValueError('ACL_KIND')
        if identity and (kind not in ('user','group') or not re.fullmatch(r'[0-9]{1,10}',identity)):
            raise ValueError('ACL_IDENTITY')
        if identity and (str(int(identity))!=identity or int(identity)>4294967294):
            raise ValueError('ACL_NONCANONICAL_IDENTITY')
        if not re.fullmatch(r'[r-][w-][x-]',rights):raise ValueError('ACL_RIGHTS')
        key=(kind,identity)
        if key in result:raise ValueError('ACL_DUPLICATE')
        result[key]=rights
    if not {('user',''),('group',''),('other','')}<=set(result):raise ValueError('ACL_BASE_REQUIRED')
    if any(k[1] for k in result) and ('mask','') not in result:raise ValueError('ACL_MASK_REQUIRED')
    return result


def serialize(entries):
    order={'user':0,'group':1,'mask':2,'other':3}
    keys=sorted(entries,key=lambda k:(order[k[0]],-1 if k[1]=='' else int(k[1])))
    return ''.join('%s:%s:%s\n'%(k[0],k[1],entries[k]) for k in keys)


def propose(raw,purpose,uids):
    before=parse_acl(raw)
    if purpose=='release_traversal':
        expected=('rwx','r-x','---'); grant='--x'; count=3
    elif purpose=='ledger_client_binding_read':
        expected=('rw-','r--','---'); grant='r--'; count=1
    else:raise ValueError('ACL_PURPOSE')
    if (not isinstance(uids,list) or len(uids)!=count
            or any(type(x) is not int or not 0<x<=4294967294 for x in uids)
            or len(set(uids))!=count):
        raise ValueError('ACL_CONSUMERS')
    actual=tuple(before[k] for k in (('user',''),('group',''),('other','')))
    if actual!=expected or before.get(('mask',''),expected[1])!=expected[1]:
        raise ValueError('ACL_UNEXPECTED_BASE_OR_MASK')
    after=dict(before)
    for uid in uids:
        key=('user',str(uid))
        if key in before and before[key]!=grant:raise ValueError('ACL_EXISTING_CONSUMER_RECONCILIATION')
        after[key]=grant
    after[('mask','')]=before.get(('mask',''),before[('group','')])
    # Mask never changes, so unrelated named user/group effective rights cannot expand.
    text=serialize(after)
    return {'purpose':purpose,'before_sha256':hashlib.sha256(raw.encode()).hexdigest(),
            'after_acl':text,'after_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'recursive':False,'default_acl':False,'permission_applied':False,
            'requires_exact_inode_owner_mode_and_approval':True}
