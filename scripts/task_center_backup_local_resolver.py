"""Original-host DB/local-only selector for the reviewed backup component.

Installers supply protected inventory, never caller-supplied filesystem paths.
A matching inventory is not proof of credential restoration or COMPLETE.
"""
import copy, json, pathlib
from backup_component_hostcycle import HostContract

class LocalHostContract(HostContract):
    def __init__(self,host,policies):
        if not isinstance(policies,(list,tuple)):raise ValueError('TRUSTED_INVENTORY_REQUIRED')
        self.host=host;self.policies=copy.deepcopy(tuple(policies))
        required={'tenant_id','task_id','attempt_id','provider_ref','contract_sha256','resources'}
        for p in self.policies:
            if not isinstance(p,dict) or set(p)!=required or not isinstance(p['resources'],dict) or not p['resources']:
                raise ValueError('TRUSTED_INVENTORY_REQUIRED')
            for key,specs in p['resources'].items():
                if not isinstance(key,str) or not key or not isinstance(specs,(list,tuple)) or not specs:raise ValueError('TRUSTED_INVENTORY_REQUIRED')
                for spec in specs:
                    if (not isinstance(spec,(list,tuple)) or len(spec)!=3 or not isinstance(spec[0],str) or
                        not isinstance(spec[1],pathlib.Path) or not spec[1].is_absolute() or not isinstance(spec[2],str)):
                        raise ValueError('TRUSTED_INVENTORY_REQUIRED')
    def resolve(self,request):
        if not isinstance(request,dict):raise ValueError('BACKUP_BINDING_UNAVAILABLE')
        h=self.host
        keys=('task_id','attempt_id','provider_ref','contract_sha256')
        matches=[p for p in self.policies if p['tenant_id']==h.tenant_id and all(p[k]==request.get(k) for k in keys)]
        if len(matches)!=1:raise ValueError('BACKUP_BINDING_UNAVAILABLE')
        p=matches[0];task=h._current_task(p['task_id'],p['attempt_id'],h.clock())
        if sorted(p['resources'])!=json.loads(task['resource_scope_json']):raise ValueError('BACKUP_BINDING_UNAVAILABLE')
        if not h._mcp_registered(request) or h.role_contract is None:raise ValueError('BACKUP_BINDING_UNAVAILABLE')
        contract=h.role_contract.resolve(h.tenant_id,p['task_id'],p['attempt_id'],p['provider_ref'])
        if any(contract[k]!=request.get(k) for k in ('contract_id','contract_version','contract_sha256')):raise ValueError('BACKUP_BINDING_UNAVAILABLE')
        if request.get('applicability')!={k:contract[k] for k in ('role_id','role_version','role_scope','required_categories','not_applicable','required_checks')}:
            raise ValueError('BACKUP_BINDING_UNAVAILABLE')
        rows=h.db.execute("SELECT payload_json FROM events WHERE task_id=? AND attempt_id=? AND kind='HANDOFF_REFERENCE_ISSUED' LIMIT 2049",(p['task_id'],p['attempt_id'])).fetchall()
        if len(rows)>2048:raise ValueError('BACKUP_BINDING_UNAVAILABLE')
        try:refs=[json.loads(row['payload_json']) for row in rows]
        except (TypeError,ValueError):raise ValueError('BACKUP_BINDING_UNAVAILABLE')
        if not any(all(ref.get(k)==request.get(k) for k in ('task_id','attempt_id','handoff_id','handoff_version','backup_cycle_id')) and ref.get('tenant_id')==h.tenant_id and ref.get('issuer')==h.issuer and ref.get('fence')==task['fence'] and ref.get('epoch')==task['epoch'] for ref in refs):
            raise ValueError('BACKUP_BINDING_UNAVAILABLE')
        specs=[]
        for resource in sorted(p['resources']):
            group=p['resources'][resource]
            if 'SOURCE' in contract['required_categories'] and not any(spec[0]=='SOURCE' for spec in group):raise ValueError('BACKUP_BINDING_UNAVAILABLE')
            if any(spec[0] not in contract['required_categories'] for spec in group):raise ValueError('BACKUP_BINDING_UNAVAILABLE')
            specs.extend(group)
        keys=('backup_cycle_id','task_id','attempt_id','handoff_id','handoff_version','snapshot_digest','provider_ref','contract_id','contract_version','contract_sha256')
        binding={k:request[k] for k in keys};binding['tenant_id']=h.tenant_id
        return binding,specs
