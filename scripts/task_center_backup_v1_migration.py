"""Host-owned migration from the existing v1 backup consumer to v2 preflight.

The old adapter and producer are retained; policy is trusted host configuration,
not an MCP request. This wrapper grants no identity, role, or backup authority.
"""
import copy
from task_center_handoff_host import HostAuthAdapter, REQUIRED_CONTEXT
from task_center_backup_local_resolver import LocalHostContract
from task_center_backup_bridge import BackupAssessment
from task_center_backup_bridge_v2 import PreparedBackupAssessment
from backup_component_hostcycle import BackupComponent

class V1PreparedHostAdapter(HostAuthAdapter):
    """Keep existing authentication/ledger adapter; rebind v1 producer per DB."""
    def __init__(self,delegate,legacy,policies):
        if not isinstance(delegate,HostAuthAdapter) or type(delegate) is HostAuthAdapter:
            raise ValueError('TRUSTED_HOST_ADAPTER_REQUIRED')
        if type(legacy) is not BackupAssessment or type(legacy.component) is not BackupComponent:
            raise ValueError('EXACT_EXISTING_BACKUP_ASSESSMENT_REQUIRED')
        if legacy.required_context!=REQUIRED_CONTEXT or not isinstance(policies,(list,tuple)):
            raise ValueError('TRUSTED_INVENTORY_REQUIRED')
        self.delegate=delegate;self.legacy=legacy;self.policies=copy.deepcopy(tuple(policies))
    def authenticate_and_authorize(self,session,action,binding):
        return self.delegate.authenticate_and_authorize(session,action,binding)
    def assess_provider(self,binding):return self.delegate.assess_provider(binding)
    def assess_ledger_event(self,binding,event):return self.delegate.assess_ledger_event(binding,event)
    def verify_ledger_event_current(self,event,host_record):return self.delegate.verify_ledger_event_current(event,host_record)
    def assess_candidate_bundle(self,binding):return self.delegate.assess_candidate_bundle(binding)
    def prepare_backup_assessment(self,host):
        if host.tenant_id!=self.legacy.tenant_id:raise ValueError('BACKUP_TENANT_MISMATCH')
        # Share only original producer paths/lock, not its mutable resolver or
        # creator-thread DB connection. No directories, job or config changed.
        component=copy.copy(self.legacy.component)
        component.host=LocalHostContract(host,self.policies)
        return PreparedBackupAssessment(component,host.tenant_id,REQUIRED_CONTEXT,host.db,clock=self.legacy.clock)

def migrate_v1_consumer(delegate,policies):
    """Build an explicit host adapter from its already-installed v1 consumer.

    Original host assembly passes the returned adapter to HandoffHost before
    serving requests; no global adapter mutation, config write or service restart.
    """
    if not isinstance(delegate,HostAuthAdapter):raise ValueError('TRUSTED_HOST_ADAPTER_REQUIRED')
    return V1PreparedHostAdapter(delegate,delegate.assess_backup,policies)
