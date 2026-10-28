"""Original customer App extension: same auth/project/audit, no catalog service.
Host snapshots are server-controlled; customers never upload approval/context claims.
"""
from copy import deepcopy
import re
from scripts.pr122_customer_core import Denied
from scripts.saas_module_package_gate import manifest_digest
EVENT='SAAS_PACKAGE_REVIEW_REQUEST'

# HTTP output is a projection, not a dump of host/package diagnostic data.
# Even OWNER/REVIEWER must not receive manifest values, tenant IDs or private refs
# echoed after a diagnostic colon. Unknown future fields and codes are denied.
REASON_CODES=set('INVALID_INPUT INVALID_CONTEXT INVALID_AUTHORITIES MANIFEST_FIELDS SCHEMA_VERSION MODULE_ID EXACT_VERSION NAME SOURCE_REF OWNER_REF STATE_NOT_CANDIDATE CAPABILITIES TENANT_IDS REQUIRED_PERMISSIONS OFFER_REFS DEPENDENCIES DEPENDENCY_PIN DEPENDENCY_UNAVAILABLE FOUNDATION_REUSE FOUNDATION_BINDING ARTIFACT_DIGEST ARTIFACT_MISMATCH WRITER_UNCONFIRMED TENANT_DENIED PERMISSION_DENIED OFFER_NOT_APPROVED TRUSTED_TIME_REQUIRED EVIDENCE_MISSING_OR_INVALID UNKNOWN_CANONICAL_MODULE CANONICAL_CAPABILITY_MISMATCH CANONICAL_DEPENDENCY_MISMATCH CYCLE MISSING_MODULE MISSING_PACKAGE PACKAGE_IDENTITY_MISMATCH INVALID_DEPENDENCIES CATALOG_DEPENDENCY_MISMATCH PIN_MISMATCH'.split())
def reason_codes(values):
 if not isinstance(values,list):return ['UNCLASSIFIED_VALIDATION_ERROR']
 return sorted({v.split(':',1)[0] if isinstance(v,str) and v.split(':',1)[0] in REASON_CODES else 'UNCLASSIFIED_VALIDATION_ERROR' for v in values})

def project_view(view,catalog,role):
 canonical={r['id']:r for r in catalog};rows=[]
 for row in view['rows']:
  module=canonical.get(row.get('module_id'))
  if module is None:continue
  version=row.get('package_version')
  out={'module_id':module['id'],'title':module['title'],'package_version':version if isinstance(version,str) and re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)',version) else None,'dependencies':list(module['dependencies']),'listing_state':row['listing_state'] if row.get('listing_state') in ('UNPACKAGED','BLOCKED','LOCAL_REVIEW_ONLY') else 'BLOCKED','published':False,'review_request_recorded':row.get('review_request_recorded') is True}
  if role in ('OWNER','REVIEWER'):
   evidence=row.get('evidence');graph=row.get('dependency_graph') or {}
   out['capabilities']=list(module['capabilities'])
   out['dependency_graph']={'state':'SYNTHETIC_GRAPH_VALIDATED' if graph.get('state')=='SYNTHETIC_GRAPH_VALIDATED' else 'UNKNOWN','qualification_state':'SYNTHETIC_CLOSURE_REVIEW_ONLY' if graph.get('qualification_state')=='SYNTHETIC_CLOSURE_REVIEW_ONLY' else 'BLOCKED','errors':reason_codes(graph.get('errors',[])),'live_dependencies_verified':False}
   out['evidence']=None if not isinstance(evidence,dict) else {'qualification':{'local_qualification':'PENDING_LISTING_REVIEW' if (evidence.get('qualification') or {}).get('local_qualification')=='PENDING_LISTING_REVIEW' else 'BLOCKED','reasons':reason_codes((evidence.get('qualification') or {}).get('reasons',[])),'published':False,'production_ready':False,'entitlement_granted':False},'registration_state':'LOCAL_PROPOSAL_ONLY' if evidence.get('registration_state')=='LOCAL_PROPOSAL_ONLY' else 'BLOCKED','reasons':reason_codes(evidence.get('reasons',[]))}
  rows.append(out)
 return {'schema':'ecosystem-read-model-v1','source':'EXISTING_CATALOG_ADAPTER','scope':'SYNTHETIC_INTEGRATION_ONLY','rows':rows,'writer_lease':'UNKNOWN','http_wired':False,'publish_allowed':False}

class EcosystemHTTP:
 def __init__(self, snapshot_provider):
  self.snapshot_provider=snapshot_provider
 def handle(self,center,uid,method,operation,body):
  parts=operation.split('/')
  if len(parts)!=3 or parts[1] not in ('list','register'):return 404,{'error':'NOT_FOUND'}
  action,pid=parts[1:]
  if method!=('GET' if action=='list' else 'POST'):return 405,{'error':'METHOD_NOT_ALLOWED'}
  if action=='register' and (set(body)!={'module_id','version'} or not all(type(x) is str for x in body.values())):raise ValueError('INVALID_FIELDS')
  with center.tx():
   project,role,_=center.project(uid,pid,('OWNER',) if action=='register' else None)
   if role not in ('OWNER','EDITOR','VIEWER','REVIEWER'):raise Denied('PROJECT_ROLE_NOT_ALLOWED')
   # Host callback receives the authenticated project's tenant, never body identity.
   adapter,manifests,artifacts,contexts,receipts=self.snapshot_provider(project['tenant'],pid)
   view=adapter.listing(manifests,artifacts,contexts,receipts,project['tenant'])
   view=deepcopy(view);view['http_transport']='ISOLATED_ORIGINAL_APP_EXTENSION'
   view['project']=pid;view['tenant_authorization']='ORIGINAL_PROJECT_MEMBERSHIP_CHECKED'
   # v2 remains explicit: model execution, runtime permission and publication unverified.
   if action=='list':
    recorded={r[0] for r in center.db.execute('SELECT object_id FROM audit WHERE project=? AND event=?',(pid,EVENT))}
    for row in view['rows']:
     m=manifests.get(row['module_id']);row['review_request_recorded']=bool(m and manifest_digest(m) in recorded)
    view=project_view(view,adapter.modules.catalog(),role)
    view['http_transport']='ISOLATED_ORIGINAL_APP_EXTENSION';view['project']=pid;view['tenant_authorization']='ORIGINAL_PROJECT_MEMBERSHIP_CHECKED'
    view['field_scope']='PROJECT_INTERNAL_SUMMARY' if role in ('OWNER','REVIEWER') else 'PROJECT_MEMBER_SUMMARY'
    return 200,view
   mid=body['module_id'];m=manifests.get(mid)
   if not isinstance(m,dict) or m.get('version')!=body['version']:raise ValueError('UNKNOWN_PACKAGE_VERSION')
   row=next((r for r in view['rows'] if r['module_id']==mid),None)
   if row is None:raise ValueError('UNKNOWN_CANONICAL_MODULE')
   digest=manifest_digest(m)
   previous=center.db.execute('SELECT seq FROM audit WHERE project=? AND actor=? AND event=? AND object_id=?',(pid,uid,EVENT,digest)).fetchone()
   if not previous:center.audit(pid,uid,EVENT,digest)
   return 200,{'state':'REVIEW_REQUEST_RECORDED','module_registered':False,
     'published':False,'module_id':mid,'version':m['version'],'manifest_sha256':digest,
     'duplicate':previous is not None,'proposal_qualification':row['listing_state'],
     'writer_lease':'UNKNOWN','registration_blocker':'CANONICAL_PACKAGE_WRITER_ADAPTER_MISSING'}


class PendingEcosystemHTTP(EcosystemHTTP):
 """Opt-in pending extension; migration is an explicit host startup action."""
 def __init__(self,snapshot_provider):
  super().__init__(snapshot_provider)
  from scripts.saas_pending_packages import PendingPackages
  self.pending=PendingPackages(snapshot_provider)
 def handle(self,center,uid,method,operation,body):
  parts=operation.split('/')
  if len(parts)==3 and parts[0]=='ecosystem' and parts[1] in ('packages','register_pending'):
   action,pid=parts[1:]
   if method!=('GET' if action=='packages' else 'POST'):return 405,{'error':'METHOD_NOT_ALLOWED'}
   result=(self.pending.listing(center,uid,pid) if action=='packages' else self.pending.register(center,uid,pid,body))
   return 200,result
  if len(parts)==4 and parts[:2]==['ecosystem','receipts']:
   if method!='GET':return 405,{'error':'METHOD_NOT_ALLOWED'}
   return 200,self.pending.read_receipt(center,uid,parts[2],parts[3])
  return super().handle(center,uid,method,operation,body)
