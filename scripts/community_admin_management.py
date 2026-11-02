"""Administrator actions inside original community HTTP/session composition."""
import json
from scripts.community_admin_authority import CommunityAdminAuthority, CHANNEL
from scripts.pr122_customer_core import Denied, identifier

FIELDS={
 'self':set(),
 'catalog':set(),
 'list':{'after_uid'},
 'create':{'email','password','capabilities','workspace_scopes','request_id'},
 'grant':{'uid','capabilities','workspace_scopes','request_id','expected_revision'},
 'revoke':{'uid','expected_revision','request_id'},
}

def _daily_overview(center,project,tenant,operations=None):
 now=center.now();day_start=now-((now+8*3600)%86400)
 day_end=day_start+86400;window_start=day_start-6*86400
 series=[dict(day_start=window_start+i*86400,transaction_count=None,transaction_amount_minor=None,
  completed_split_minor=0,confirmed_refund_minor=0,ad_impression_count=None,ad_click_count=None) for i in range(7)]
 transaction_count=transaction_minor=None
 ad_impressions=ad_clicks=active_ads=None
 if operations is not None:
  if getattr(operations,'center',None) is not center:raise Denied('SAME_CENTER_OPERATIONS_REQUIRED')
  scopes={tuple(grant['scope'][key] for key in ('tenant_id','merchant_id','store_id')) for grant in operations.grants.values()
   if grant.get('project')==project and grant.get('tenant')==tenant and type(grant.get('scope')) is dict}
  # A consumer-only host still composes CenterOperations with zero business
  # grants.  Zero grants means "not readable", never zero orders/ads.
  if scopes:
   db=operations.runtime.demo.db;ad_db=operations.runtime.demo.ad_db
   transaction_count=transaction_minor=ad_impressions=ad_clicks=active_ads=0
   for item in series:item.update(transaction_count=0,transaction_amount_minor=0,ad_impression_count=0,ad_click_count=0)
   from scripts.community_order_provider_projection import provider_evidence
   for t,m,s,reference,amount,currency,state in db.execute("SELECT tenant_id,merchant_id,store_id,reference,amount_minor,currency,state FROM orders WHERE state IN ('SUCCESS','REFUNDED')"):
    if (t,m,s) not in scopes or currency!='CNY':continue
    identity=dict(tenant_id=t,merchant_id=m,store_id=s)
    if provider_evidence(db,identity,reference) is None:continue
    paid_times=[]
    for raw, in db.execute('SELECT evidence_source FROM order_events WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=?',(t,m,s,reference)):
     try:event=json.loads(raw)
     except (TypeError,ValueError):continue
     if type(event) is dict and event.get('source')=='WECHAT_SIGNED_PAYMENT_TIME' and type(event.get('paid_at')) is int:paid_times.append(event['paid_at'])
    if len(set(paid_times))==1 and window_start<=paid_times[0]<day_end:
     bucket=series[(paid_times[0]-window_start)//86400];bucket['transaction_count']+=1;bucket['transaction_amount_minor']+=amount
     if paid_times[0]>=day_start:transaction_count+=1;transaction_minor+=amount
   for scope in scopes:
    for kind,created_at in ad_db.execute("SELECT kind,created_at FROM metric_events WHERE tenant_id=? AND merchant_id=? AND store_id=? AND created_at>=? AND created_at<?",scope+(window_start,day_end)):
     key='ad_impression_count' if kind=='IMPRESSION' else 'ad_click_count';series[(created_at-window_start)//86400][key]+=1
     if created_at>=day_start:
      if kind=='IMPRESSION':ad_impressions+=1
      else:ad_clicks+=1
    active_ads+=ad_db.execute("SELECT count(*) FROM campaigns WHERE tenant_id=? AND merchant_id=? AND store_id=? AND status='ACTIVE' AND starts_at<=? AND ends_at>?",scope+(now,now)).fetchone()[0]
 split_minor=refund_minor=split_count=refund_count=0
 for key,payload in center.db.execute("SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_PROVIDER_ACTION' AND project=? AND active=1",(project,)):
  value=json.loads(center.decrypt(payload,'provider-action:'+key))
  if type(value) is not dict or type(value.get('at')) is not int or not window_start<=value['at']<day_end:continue
  result=value.get('result')
  if value.get('kind')=='SPLIT' and type(result) is dict and result.get('status')=='FINISHED':
   receivers=result.get('receivers')
   if type(receivers) is list:
    amount=sum(item['amount_minor'] for item in receivers if type(item) is dict and item.get('result')=='SUCCESS' and type(item.get('amount_minor')) is int);series[(value['at']-window_start)//86400]['completed_split_minor']+=amount
    if value['at']>=day_start:split_minor+=amount;split_count+=1
  elif value.get('kind')=='REFUND' and type(result) is dict and result.get('status')=='SUCCESS' and type(result.get('amount_minor')) is int:
   series[(value['at']-window_start)//86400]['confirmed_refund_minor']+=result['amount_minor']
   if value['at']>=day_start:refund_minor+=result['amount_minor'];refund_count+=1
 has_onboarding=center.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='onboarding'").fetchone() is not None
 pending_merchants=(center.db.execute("SELECT count(*) FROM onboarding WHERE tenant=? AND status IN ('SUBMITTED','IN_REVIEW')",(tenant,)).fetchone()[0]
  if has_onboarding else None)
 return dict(day_start=day_start,timezone='Asia/Shanghai',pending_merchant_count=pending_merchants,
 transaction_count=transaction_count,transaction_amount_minor=transaction_minor,
  ad_impression_count=ad_impressions,ad_click_count=ad_clicks,active_ad_count=active_ads,
  completed_split_minor=split_minor,completed_split_count=split_count,confirmed_refund_minor=refund_minor,
  confirmed_refund_count=refund_count,daily_series=series,currency='CNY',finance_status='UNCONFIRMED')

def dispatch(center,session,csrf,body,operations=None):
 api=getattr(center,'community_admin_authority',None)
 if type(api) is not CommunityAdminAuthority or api.c is not center:
  raise Denied('EXACT_COMMUNITY_AUTHORITY_COMPOSITION_REQUIRED')
 if type(body) is not dict or set(body)!={'operation','params'} or body['operation'] not in FIELDS or type(body['params']) is not dict or set(body['params'])!=FIELDS[body['operation']]:
  raise ValueError('EXACT_ADMIN_ACTION_FIELDS_REQUIRED')
 if type(csrf) is not str or not csrf:raise Denied('CSRF_REQUIRED')
 uid=center.session(session,csrf);authority=api.authority(uid)
 operation,params=body['operation'],body['params']
 if operation=='self':
  return {k:authority[k] for k in ('uid','project','tenant','kind','revision','capabilities','workspace_scopes')}
 if authority['kind']!='ROOT':raise Denied('ROOT_ADMIN_MANAGEMENT_REQUIRED')
 api.authorize(session,csrf,'/community/admin',operation)
 if operation=='catalog':
  return dict(capabilities=sorted(api.capabilities),workspace_scopes=sorted(api.workspace_scopes),manifest_sha=api.manifest_sha)
 if operation=='create':return api.create_subadmin(session,csrf,params['email'],params['password'],params['capabilities'],params['request_id'],params['workspace_scopes'])
 if operation=='grant':return api.delegate(session,csrf,params['uid'],params['capabilities'],params['request_id'],params['expected_revision'],params['workspace_scopes'])
 if operation=='revoke':return api.revoke(session,csrf,params['uid'],params['expected_revision'],params['request_id'])
 after=params['after_uid']
 if after!='':identifier(after)
 records=[]
 for row in center.db.execute('SELECT subject_idx,payload,active FROM links WHERE channel=? AND project=? AND subject_idx>? ORDER BY subject_idx LIMIT 51',(CHANNEL,api.project,after)):
  value=json.loads(center.decrypt(row['payload'],CHANNEL+':'+row['subject_idx']+':'+api.project))
  account=center.db.execute('SELECT email_enc FROM accounts WHERE id=?',(row['subject_idx'],)).fetchone()
  login_label=center.decrypt(account[0],row['subject_idx']).decode() if account else ''
  records.append(dict(uid=row['subject_idx'],login_label=login_label,kind=value['kind'],revision=value['revision'],active=bool(row['active']),capabilities=value['capabilities'],workspace_scopes=value['workspace_scopes']))
 return dict(records=records[:50],has_more=len(records)>50,next_cursor=records[49]['uid'] if len(records)>50 else None,
  daily_overview=_daily_overview(center,api.project,api.tenant,operations))
