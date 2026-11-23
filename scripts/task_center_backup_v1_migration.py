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
    def __init__(self,delegate,legacy,policies,config_path=None,config_digest=None):
        if not isinstance(delegate,HostAuthAdapter) or type(delegate) is HostAuthAdapter:
            raise ValueError('TRUSTED_HOST_ADAPTER_REQUIRED')
        if type(legacy) is not BackupAssessment or type(legacy.component) is not BackupComponent:
            raise ValueError('EXACT_EXISTING_BACKUP_ASSESSMENT_REQUIRED')
        if legacy.required_context!=REQUIRED_CONTEXT or not isinstance(policies,(list,tuple)):
            raise ValueError('TRUSTED_INVENTORY_REQUIRED')
        self.delegate=delegate;self.legacy=legacy;self.policies=copy.deepcopy(tuple(policies));self.config_path=config_path;self.config_digest=config_digest
    def authenticate_and_authorize(self,session,action,binding):
        return self.delegate.authenticate_and_authorize(session,action,binding)
    def assess_provider(self,binding):return self.delegate.assess_provider(binding)
    def assess_ledger_event(self,binding,event):return self.delegate.assess_ledger_event(binding,event)
    def verify_ledger_event_current(self,event,host_record):return self.delegate.verify_ledger_event_current(event,host_record)
    def assess_candidate_bundle(self,binding):return self.delegate.assess_candidate_bundle(binding)
    def prepare_backup_assessment(self,host):
        if host.tenant_id!=self.legacy.tenant_id or self.delegate.assess_backup is not self.legacy:raise ValueError('BACKUP_TENANT_MISMATCH')
        # Share only original producer paths/lock, not its mutable resolver or
        # creator-thread DB connection. No directories, job or config changed.
        component=copy.copy(self.legacy.component)
        if self.config_path is not None:
            policies,version=_read_inventory_config(self.delegate,self.config_path)
            if policies is None or version[-1]!=self.config_digest:raise ValueError('BACKUP_CONFIG_CHANGED')
            component.host=_ConfigRecheckedContract(host,policies,self.delegate,self.legacy,self.config_path,version)
        else:
            component.host=LocalHostContract(host,self.policies)
        return PreparedBackupAssessment(component,host.tenant_id,REQUIRED_CONTEXT,host.db,clock=self.legacy.clock)

def migrate_v1_consumer(delegate,policies):
    """Build an explicit host adapter from its already-installed v1 consumer.

    Original host assembly passes the returned adapter to HandoffHost before
    serving requests; no global adapter mutation, config write or service restart.
    """
    if not isinstance(delegate,HostAuthAdapter):raise ValueError('TRUSTED_HOST_ADAPTER_REQUIRED')
    return V1PreparedHostAdapter(delegate,delegate.assess_backup,policies)

def _read_stable_owned_config(path):
    """Bounded, no-follow owner file read with before/after version checks."""
    import hashlib, os, stat
    flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)
    before=os.lstat(path)
    def valid(info):
        return stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o600 and info.st_size<=65536
    def stamp(info):return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
    if not valid(before):raise ValueError('BACKUP_CONFIG_INVALID')
    fd=os.open(path,flags)
    try:
        first=os.fstat(fd)
        if not valid(first) or stamp(first)!=stamp(before):raise ValueError('BACKUP_CONFIG_INVALID')
        chunks=[];remaining=65537
        while remaining:
            piece=os.read(fd,remaining)
            if not piece:break
            chunks.append(piece);remaining-=len(piece)
        content=b''.join(chunks);last=os.fstat(fd);current=os.lstat(path)
        if len(content)>65536 or len(content)!=last.st_size or not valid(last) or not valid(current) or stamp(first)!=stamp(last) or stamp(last)!=stamp(current):
            raise ValueError('BACKUP_CONFIG_INVALID')
        return content,stamp(current)+(hashlib.sha256(content).hexdigest(),)
    finally:os.close(fd)

class _ConfigRecheckedContract(LocalHostContract):
    """Recheck the same protected config version before each DB/local plan."""
    def __init__(self,host,policies,delegate,legacy,path,version):
        super().__init__(host,policies);self.delegate=delegate;self.legacy=legacy;self.path=path;self.version=version
    def assert_current(self):
        if self.delegate.assess_backup is not self.legacy:raise ValueError('BACKUP_CONFIG_CHANGED')
        policies,version=_read_inventory_config(self.delegate,self.path)
        if policies is None or version!=self.version:raise ValueError('BACKUP_CONFIG_CHANGED')
    def resolve(self,request):
        self.assert_current()
        return super().resolve(request)

def _read_inventory_config(delegate, config_path):
    """Read and validate one protected inventory version without mutation."""
    import json, pathlib, re
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError('DUPLICATE_BACKUP_CONFIG_KEY')
            result[k]=v
        return result
    try:
        if not isinstance(config_path,str) or not pathlib.Path(config_path).is_absolute():raise ValueError('BACKUP_CONFIG_UNAVAILABLE')
        content,version=_read_stable_owned_config(config_path)
        raw=json.loads(content.decode('utf-8'),object_pairs_hook=unique)
        if (not isinstance(raw,dict) or set(raw)!={'schema_version','enabled','policies'} or
            type(raw['schema_version']) is not int or raw['schema_version']!=1 or type(raw['enabled']) is not bool or
            not isinstance(raw['policies'],list) or len(raw['policies'])>128):raise ValueError('BACKUP_CONFIG_INVALID')
        if not raw['enabled']:
            if raw['policies']:raise ValueError('BACKUP_CONFIG_INVALID')
            return None,version
        if not raw['policies']:raise ValueError('BACKUP_CONFIG_INVALID')
        if not isinstance(delegate,HostAuthAdapter) or type(delegate.assess_backup) is not BackupAssessment:raise ValueError('BACKUP_CONFIG_INVALID')
        atom=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,100}$')
        seen=set();policies=[]
        for row in raw['policies']:
            fields={'tenant_id','task_id','attempt_id','provider_ref','contract_sha256','resources'}
            if not isinstance(row,dict) or set(row)!=fields or any(not isinstance(row[k],str) or not atom.fullmatch(row[k]) for k in ('tenant_id','task_id','attempt_id','provider_ref')) or row['tenant_id']!=delegate.assess_backup.tenant_id or not isinstance(row['contract_sha256'],str) or not re.fullmatch(r'[0-9a-f]{64}',row['contract_sha256']):raise ValueError('BACKUP_CONFIG_INVALID')
            key=tuple(row[k] for k in ('tenant_id','task_id','attempt_id','provider_ref','contract_sha256'))
            if key in seen:raise ValueError('BACKUP_CONFIG_INVALID')
            seen.add(key)
            if not isinstance(row['resources'],dict) or not 1<=len(row['resources'])<=128:raise ValueError('BACKUP_CONFIG_INVALID')
            resources={}
            for resource,specs in row['resources'].items():
                if not isinstance(resource,str) or not resource or len(resource)>256 or any(ord(c)<32 for c in resource) or not isinstance(specs,list) or not 1<=len(specs)<=256:raise ValueError('BACKUP_CONFIG_INVALID')
                parsed=[]
                for spec in specs:
                    if (not isinstance(spec,dict) or set(spec)!={'category','root','relative_path'} or spec['category'] not in ('SOURCE','ARTIFACT','CONTEXT','INSTALL','CONFIG_REFERENCE','AUTH_ENTRY') or
                        not isinstance(spec['root'],str) or len(spec['root'])>4096 or any(ord(c)<32 for c in spec['root']) or not pathlib.Path(spec['root']).is_absolute() or
                        not isinstance(spec['relative_path'],str) or not spec['relative_path'] or len(spec['relative_path'])>4096 or any(ord(c)<32 for c in spec['relative_path']) or
                        spec['relative_path'].startswith('/') or any(x in ('','.','..') for x in spec['relative_path'].split('/'))):raise ValueError('BACKUP_CONFIG_INVALID')
                    parsed.append((spec['category'],pathlib.Path(spec['root']),spec['relative_path']))
                resources[resource]=parsed
            policies.append(dict((k,row[k]) for k in fields-{'resources'}));policies[-1]['resources']=resources
        return policies,version
    except (OSError,ValueError,TypeError,KeyError):
        raise ValueError('BACKUP_INVENTORY_CONFIG_UNAVAILABLE_OR_INVALID') from None

def load_v1_consumer(delegate, config_path):
    """Load protected inventory; configured hosts revalidate every request."""
    if config_path is None:return delegate
    policies,version=_read_inventory_config(delegate,config_path)
    if policies is None:return delegate
    return V1PreparedHostAdapter(delegate,delegate.assess_backup,policies,config_path=config_path,config_digest=version[-1])

def build_v1_host(host,config_path):
    """Build the original HandoffHost with the protected configured adapter.

    Host assembly owns identity and DB; call before creating the existing
    ledger bridge/server. The original host and its adapter are never mutated.
    """
    import os
    from task_center_handoff_host import HandoffHost
    if type(host) is not HandoffHost or host.db.in_transaction:
        raise ValueError('EXACT_IDLE_HANDOFF_HOST_REQUIRED')
    adapter=load_v1_consumer(host.adapter,config_path)
    if adapter is host.adapter:return host
    readback=host._lifecycle_candidate_readback
    root=os.path.dirname(readback.artifacts) if readback is not None else None
    return HandoffHost(host.db,host.tenant_id,host.issuer,adapter,clock=host.clock,
                       mcp_config=host.mcp_config,role_contract=host.role_contract,
                       candidate_lifecycle_root=root)
