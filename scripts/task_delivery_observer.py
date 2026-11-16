"""TEST_ONLY adapter over pre-existing offline metadata; no source authority."""
import os
from datetime import datetime, timezone
from task_delivery_ledger.core import Store, ident, parse_time

class Unavailable(Exception): pass

class MetadataReader(object):
    """Bound by the hosting test harness, never by an HTTP request."""
    def __init__(self,root,namespace,writer,tenant_id):
        self.root=os.path.realpath(root);self.namespace=ident(namespace);self.writer=ident(writer);self.tenant_id=ident(tenant_id)
    def _store(self):
        # Store.__init__ creates marker/directories; never call it from a GET.
        marker=os.path.join(self.root,'writer.id')
        if not os.path.isfile(marker) or not os.path.isdir(os.path.join(self.root,'events')): raise Unavailable()
        with open(marker,'r',encoding='utf8') as f:
            if f.read(130)!=self.writer+'\n': raise Unavailable()
        store=Store.__new__(Store);store.root=__import__('pathlib').Path(self.root);store.writer=self.writer
        return store
    def view(self):
        v=self._store().project(self.namespace);rows=[]
        for tid,t in v['tasks'].items():
            o=v['objects'].get('task:'+tid,{})
            linked=[x for x in v['objects'].values() if x.get('task_id')==tid]
            source=[x for x in linked if x.get('kind')=='source_artifact']
            hosts=[x for x in linked if x.get('kind')=='host_service']
            roles=[x for x in linked if x.get('kind')=='role']
            perms=[x for x in linked if x.get('kind')=='permission_ref']
            history=t['history']
            matches=[r for r in roles if r['id']==o.get('writer_role_id') and r['id']!='UNKNOWN']
            role_entry=matches[0].get('entry_ref','UNKNOWN') if len(matches)==1 else 'UNKNOWN'
            def latest(phase):
                hits=[e for e in history if e['type']==phase and e['event_id'] not in v['conflicts'] and e['event_id'] not in v['pending_dependencies']]
                return {'observed_at':hits[-1]['observed_at'],'validity':hits[-1]['validity'],'evidence':hits[-1]['evidence']} if hits else 'UNKNOWN'
            def permission(p):
                expiry=p.get('expires_at','UNKNOWN');status=p.get('validity','UNKNOWN')
                try:
                    if expiry not in ('UNKNOWN','UNAVAILABLE') and parse_time(expiry)<=datetime.now(timezone.utc):status='EXPIRED'
                except Exception:status='UNKNOWN'
                return {'validity':status,'scope':p.get('scope','UNKNOWN'),'expires_at':expiry,'denial':p.get('denial','UNKNOWN')}
            rows.append({'task_id':tid,'goal':o.get('goal','UNKNOWN'),'validity':o.get('validity','UNKNOWN'),
                'writer':o.get('writer_role_id','UNKNOWN'),'state':t['state'],'blocker':o.get('blocker','UNKNOWN'),
                'next_action':o.get('next_action','UNKNOWN'),'entry':role_entry,
                'roles':[{'role_id':r['id'],'session':r.get('verified_session_ref','UNKNOWN'),'validity':r['validity']} for r in roles],
                'receipt':{'sent':latest('send_accepted'),'received':latest('actual_received'),'started':latest('start'),
                           'progress':latest('progress'),'result':latest('result'),'review':latest('review'),'accept':latest('accept')},
                'sources':[{'repo':x.get('repo_ref','UNKNOWN'),'branch':x.get('branch','UNKNOWN'),'commit':x.get('commit','UNKNOWN'),
                            'tree':x.get('tree','UNKNOWN'),'manifest':x.get('manifest_ref','UNKNOWN'),'artifact':x.get('artifact_sha256','UNKNOWN'),
                            'build':x.get('build_ref','UNKNOWN'),'deploy':x.get('deploy_refs',[]),'validity':x['validity']} for x in source],
                'services':[{'class':x.get('service_class','UNKNOWN'),'host':x.get('host_ref','UNKNOWN'),
                             'build':x.get('build_ref','UNKNOWN'),'running':x.get('running_ref','UNKNOWN'),'validity':x['validity']} for x in hosts],
                'permissions':[permission(p) for p in perms],
                'handoffs':[{'id':h['handoff_id'],'version':h['version'],'status':h['handoff_status'],
                             'scope':h['scope_included'],'excluded':h['scope_excluded'],'gaps':h['unknown_items'],
                             'outgoing':h['outgoing'],'receiving':h['receiving'],'supervisor':h['supervisor'],
                             'summary':h['summary']} for h in v['handoffs'].values() if h['task_id']==tid]})
        return {'mode':'TEST_ONLY','source_trust':'UNAVAILABLE','writer_verification':'UNKNOWN',
                'namespace':self.namespace,'tasks':rows,'conflicts':v['conflicts'],
                'pending_dependencies':v['pending_dependencies'],'production_status':'NOT_IMPLEMENTED'}
    def export(self,task_id):
        return {'mode':'TEST_ONLY','source_trust':'UNAVAILABLE','writer_verification':'UNKNOWN',
                'handoff':self._store().handoff(self.namespace,ident(task_id))}

def observer_status():
    # Existing P2/P3 normalize() is TEST_ONLY and lacks actual transport proof.
    return {'state':'UNAVAILABLE','interface':'ExternalReceiptContract.normalize',
      'missing':['verified_sender_instance','verified_recipient_instance','trusted_actual_received',
                 'worker_start_receipt','independent_review_receipt','live_role_permission_scope_expiry'],
      'note':'TEST_ONLY VALIDATED_NOT_CONSUMED is not trusted production receipt; no import performed'}
