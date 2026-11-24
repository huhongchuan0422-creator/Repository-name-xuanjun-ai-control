"""Private application-result notices in the original Center notification store."""
import hashlib
import json
import re
from scripts.pr122_customer_core import canonical
from scripts.community_customer_profile import notify

KIND='MERCHANT_ONBOARDING_RESULT_V1'
RESULTS={'CORRECTION':('CORRECTION_REQUIRED','需要补充资料'),
         'REJECT':('REJECTED','申请已驳回'),
         'APPROVE':('APPROVED','平台入驻审核通过'),
         'REOPEN':('CORRECTION_REQUIRED','已重新开启补件')}


def message(event,revision):
    return '入驻申请第'+str(revision)+'版：'+RESULTS[event][1]+'。请在本申请的受保护详情查看说明；此结果不代表微信支付已开通。'


def load(center,application,owner,key,payload):
    value=json.loads(center.decrypt(payload,'community-notice:'+key))
    if (type(value) is not dict or set(value)!={'id','kind','reference','message','read','created_at'}
            or value['id']!=key or value['kind']!=KIND or type(value['reference']) is not str
            or type(value['read']) is not bool or type(value['created_at']) is not int
            or not 0<=value['created_at']<=253402300799):raise PermissionError('ONBOARDING_NOTICE_BINDING_CHANGED')
    match=re.fullmatch(re.escape(application)+':([1-9][0-9]{0,18})',value['reference'])
    if match is None:raise PermissionError('ONBOARDING_NOTICE_BINDING_CHANGED')
    revision=int(match[1])
    expected=hashlib.sha256(canonical([application,owner,KIND,value['reference']])).hexdigest()
    event=center.db.execute('SELECT event FROM onboarding_events WHERE tenant=? AND application=? AND revision=?',
        (owner,application,revision)).fetchone()
    if (expected!=key or event is None or event[0] not in RESULTS
            or value['message']!=message(event[0],revision)):
        raise PermissionError('ONBOARDING_NOTICE_BINDING_CHANGED')
    public=dict(value,application=application,revision=revision,status=RESULTS[event[0]][0],event=event[0])
    return value,public


def append(service,application,owner,revision,action):
    if action not in RESULTS:return
    c=service.center
    if not c.db.in_transaction:raise ValueError('ORIGINAL_ONBOARDING_TRANSACTION_REQUIRED')
    reference=application+':'+str(revision)
    notify(c,application,owner,KIND,reference,message(action,revision))
    key=hashlib.sha256(canonical([application,owner,KIND,reference])).hexdigest()
    row=c.db.execute("SELECT user_id,payload,active FROM links WHERE channel='COMMUNITY_NOTICE_V1' AND subject_idx=? AND project=?",(key,application)).fetchone()
    if row is None or row[0]!=owner or row[2]!=1:raise PermissionError('ONBOARDING_NOTICE_BINDING_CHANGED')
    load(c,application,owner,key,row[1])


def dispatch(service,session,csrf,operation,params):
    c=service.center;application=params['application']
    def authorize():
        uid=c.session(session,csrf)
        owner,_,_=service._load(application,uid)
        return uid,owner
    with c.tx():
        authority=authorize();uid,owner=authority
        c.limit('onboarding-notices:'+uid,60,60)
        if operation=='notices':
            after=params['after_id']
            if type(after) is not str or after and not re.fullmatch('[0-9a-f]{64}',after):raise ValueError('INVALID_NOTICE_CURSOR')
            rows=c.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_NOTICE_V1' AND user_id=? AND project=? AND active=1 AND subject_idx>? ORDER BY subject_idx LIMIT 51",(owner,application,after)).fetchall()
            records=[load(c,application,owner,key,payload)[1] for key,payload in rows[:50]]
            result=dict(application=application,records=records,has_more=len(rows)>50,next_cursor=rows[49][0] if len(rows)>50 else None,payment_enabled=False)
            c.audit(application,uid,'MERCHANT_ONBOARDING_NOTICES_READ',str(len(records)))
        else:
            key=params['notice_id']
            if type(key) is not str or not re.fullmatch('[0-9a-f]{64}',key):raise ValueError('INVALID_NOTICE_ID')
            row=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_NOTICE_V1' AND user_id=? AND project=? AND active=1 AND subject_idx=?",(owner,application,key)).fetchone()
            if row is None:raise PermissionError('OWN_ONBOARDING_NOTICE_REQUIRED')
            value,result=load(c,application,owner,key,row[0]);value['read']=True;result['read']=True
            c.db.execute("UPDATE links SET payload=? WHERE channel='COMMUNITY_NOTICE_V1' AND subject_idx=? AND project=? AND user_id=? AND active=1",(c.encrypt(canonical(value),'community-notice:'+key),key,application,owner))
            c.audit(application,uid,'MERCHANT_ONBOARDING_NOTICE_MARKED_READ',key)
        if authorize()!=authority:raise PermissionError('ONBOARDING_NOTICE_AUTHORITY_CHANGED')
        return result
