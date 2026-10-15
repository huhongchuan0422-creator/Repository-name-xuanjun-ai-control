"""Opt-in schema2 service roles; schema1 exact command-line roles are unchanged.

Only reviewed nginx/OpenClaw families and the exact dispatcher startup Git
family may use manager/ancestry delivery.
Executable/title matches alone never authorize a process. Trusted readers must
supply stable inode/parent/title evidence, complete same-unit cgroups, current
source pins, and successful commands from this attempt's sole bounded runner.
"""
import copy
import hashlib
import re

UNITS = frozenset(('nginx.service','xuanjun-uk-openclaw.service','xuanjun-development-dispatcher.service',
                  'xuanjun-p2-gateway-relay.service'))
IDENTITY_KEYS = frozenset(('uids','gids','groups','executable','executable_sha256'))
META_KEYS = frozenset(('ppid','parent_starttime','executable_dev','executable_ino','cmdline_title','cmdline_size'))
RECEIPT_KEYS = frozenset(('context_sha256','phase','operation','argv_sha256','sequence','returncode'))
CONTRACT_KEYS = frozenset(('schema','units'))
UNIT_KEYS = frozenset(('sources','topology_source_sha256','roles'))
ROLE_KEYS = frozenset(('unit','name','identity','executable_dev','executable_ino','command','parent','maximum','main'))


def need(value,label):
    if not value: raise ValueError('EPOCH7_ROLE_'+label)


def _hash(value): need(type(value) is str and re.fullmatch(r'[0-9a-f]{64}',value) is not None,'SHA256')
def _int(value,minimum=0): need(type(value) is int and minimum<=value<2**63,'INTEGER')


def argv_hash(argv):
    return hashlib.sha256(b'\0'.join(x.encode('utf-8') for x in argv)+b'\0').hexdigest()


def normalized_title(raw):
    """Raw argv hash remains separately recorded; normalize terminal NULs only.

    Do not split on whitespace, ignore arguments, remove internal NULs or match
    prefixes. Multi-argument argv is not a process-title match.
    """
    need(type(raw) is bytes and 0<len(raw)<=16384,'TITLE_RAW_BOUND')
    value=raw.rstrip(b'\0')
    need(value and b'\0' not in value and all(32<=x<=126 for x in value),'TITLE_LITERAL_BYTES')
    return value.decode('ascii')


def validate_contract(contract,digest,path_validator,role_validator):
    need(type(contract) is dict and set(contract)==CONTRACT_KEYS and
         type(contract['schema']) is int and contract['schema']==1,'CONTRACT_SCHEMA')
    units=contract['units']
    need(type(units) is dict and 1<=len(units)<=4 and set(units)<=UNITS,'EXACT_UNIT_SCOPE')
    by_hash={}
    for unit,block in units.items():
        need(type(block) is dict and UNIT_KEYS<=set(block)<=UNIT_KEYS|{'quiet_startup'},'UNIT_CONTRACT_SCHEMA')
        if 'quiet_startup' in block:
            need(unit in ('xuanjun-uk-openclaw.service','xuanjun-p2-gateway-relay.service'),'QUIET_POLICY_UNIT_SCOPE')
            from epoch7_openclaw_recipe import validate_quiet_startup
            validate_quiet_startup(block['quiet_startup'])
        sources=block['sources']
        need(type(sources) is dict and 2<=len(sources)<=48,'SOURCE_PIN_BOUND')
        for path,pin in sources.items():path_validator(path);_hash(pin)
        required = ({'/etc/systemd/system/nginx.service','/etc/xuanjun-development/nginx-main.conf',
                     '/etc/nginx/conf.d/xuanjun-p2-owner.conf'} if unit=='nginx.service' else
                    {'/etc/systemd/system/xuanjun-uk-openclaw.service',
                     '/home/xuanjun_dev/.openclaw/bin/openclaw',
                     '/etc/xuanjun-development/p2-native-controller.binding.json'} if unit=='xuanjun-uk-openclaw.service' else
                    {'/etc/systemd/system/xuanjun-development-dispatcher.service',
                     '/etc/xuanjun-development/dispatcher.json','/usr/bin/git'} if unit=='xuanjun-development-dispatcher.service' else
                    {'/etc/systemd/system/xuanjun-p2-gateway-relay.service',
                     '/etc/xuanjun-development/p2-gateway-relay.json','/home/xuanjun_dev/.openclaw/bin/openclaw'})
        need(required <= set(sources),'UNIT_LAUNCHER_CONFIG_SOURCE_REQUIRED')
        _hash(block['topology_source_sha256'])
        need(block['topology_source_sha256'] in sources.values(),'TOPOLOGY_SOURCE_REQUIRED')
        roles=block['roles'];need(type(roles) is list and 1<=len(roles)<=8,'ROLE_BOUND')
        names={r.get('name') for r in roles if type(r) is dict}
        need(len(names)==len(roles) and sum(r.get('main') is True for r in roles)==1,'ONE_MAIN_UNIQUE_ROLES')
        lookup={r['name']:r for r in roles}
        for role in roles:
            need(set(role)==ROLE_KEYS and role['unit']==unit and type(role['name']) is str and
                 re.fullmatch(r'[a-z][a-z0-9_]{0,31}',role['name']) is not None,'ROLE_SCHEMA')
            ident=role['identity'];need(type(ident) is dict and set(ident)==IDENTITY_KEYS,'ROLE_IDENTITY')
            role_validator(dict(ident,argv_sha256='0'*64,unit=unit))
            need(sources.get(ident['executable'])==ident['executable_sha256'],'EXECUTABLE_SOURCE_PIN')
            _int(role['executable_dev']);_int(role['executable_ino'],1)
            _int(role['maximum'],1);need(role['maximum']<=256 and type(role['main']) is bool,'ROLE_COUNT')
            command=role['command']
            need(type(command) is dict and command.get('mode') in ('EXACT_ARGV_SHA256','EXACT_NUL_PADDED_TITLE',
                 'EXACT_ARGV_OR_NUL_PADDED_TITLES'),'COMMAND_RULE')
            if command['mode']=='EXACT_ARGV_SHA256':
                need(set(command)=={'mode','sha256'},'COMMAND_RULE_FIELDS');_hash(command['sha256'])
            else:
                union=command['mode']=='EXACT_ARGV_OR_NUL_PADDED_TITLES'
                need(set(command)==({'mode','sha256','values'} if union else {'mode','values'}) and type(command['values']) is list and
                     1<=len(command['values'])<=4 and len(set(command['values']))==len(command['values']), 'TITLE_SET')
                if union:
                    _hash(command['sha256'])
                    need((unit=='xuanjun-uk-openclaw.service' and role['name'] in ('main','compile_cache_child') and
                         command['values']==['openclaw','openclaw-gateway'] or
                         unit=='xuanjun-p2-gateway-relay.service' and role['name']=='cli_respawn' and
                         command['values']==['openclaw']) and role['maximum']==1,
                         'GATEWAY_FINITE_BOOTSTRAP_UNION')
                for title in command['values']:
                    need(type(title) is str and 1<=len(title)<=4096 and all(32<=ord(x)<=126 for x in title), 'TITLE_LITERAL')
            parent=role['parent']
            if role['main']:
                need(parent=={'kind':'MANAGER','pid':1} and role['maximum']==1,'MAIN_MANAGER_PARENT')
                need(ident['uids']==([0]*4 if unit=='nginx.service' else [1002]*4 if unit in
                     ('xuanjun-uk-openclaw.service','xuanjun-p2-gateway-relay.service') else [1003]*4),'MAIN_UID_SCOPE')
            else:
                need(type(parent) is dict and set(parent)=={'kind','role'} and parent['kind']=='ROLE' and
                     parent['role'] in names and parent['role']!=role['name'],'CHILD_PARENT_ROLE')
            if unit=='nginx.service':
                need(len(roles)==2 and role['name'] in ('main','worker'),'NGINX_EXACT_ROLE_SET')
                if not role['main']:
                    need(role['name']=='worker' and parent=={'kind':'ROLE','role':'main'} and
                         len(set(ident['uids']))==1 and ident['uids'][0]>0 and
                         ident['executable']==lookup['main']['identity']['executable'] and
                         ident['executable_sha256']==lookup['main']['identity']['executable_sha256'], 'NGINX_WORKER_SCOPE')
            elif unit=='xuanjun-uk-openclaw.service':
                need(ident['uids']==[1002]*4 and role['maximum']<=8,'GATEWAY_ROLE_SCOPE')
            elif unit=='xuanjun-development-dispatcher.service':
                need(len(roles)==2 and set(names)=={'main','startup_git'} and ident['uids']==[1003]*4 and
                     role['maximum']==1 and command['mode']=='EXACT_ARGV_SHA256','DISPATCHER_FINITE_STARTUP_ROLES')
                if not role['main']:
                    need(role['name']=='startup_git' and parent=={'kind':'ROLE','role':'main'} and
                         ident['executable']=='/usr/bin/git' and command['sha256']==argv_hash(
                            ['git','-c','core.hooksPath=/dev/null','rev-parse','HEAD']) and
                         all(ident[k]==lookup['main']['identity'][k] for k in ('uids','gids','groups')),
                         'EXACT_READONLY_STARTUP_GIT')
            else:
                need(set(names)=={'main','cli','cli_respawn'} and ident['uids']==[1002]*4 and
                     role['maximum']==1,'RELAY_FINITE_PREFLIGHT_ROLES')
                need(command['mode']==('EXACT_ARGV_OR_NUL_PADDED_TITLES' if role['name']=='cli_respawn' else
                     'EXACT_ARGV_SHA256'),'RELAY_EXACT_COMMAND_MODES')
                if not role['main']:
                    need(parent=={'kind':'ROLE','role':'main' if role['name']=='cli' else 'cli'} and
                         all(ident[k]==lookup['main']['identity'][k] for k in ('uids','gids','groups')),
                         'RELAY_PREFLIGHT_ANCESTRY_CREDENTIALS')
                if role['name']=='cli_respawn':
                    need(ident==lookup['cli']['identity'] and all(role[k]==lookup['cli'][k] for k in
                         ('executable_dev','executable_ino')),'RELAY_SAME_NODE_RESPAWN')
            # No cycles, external siblings, or arbitrarily deep delegated trees.
            seen=set();current=role
            while not current['main']:
                need(current['name'] not in seen and len(seen)<4,'PARENT_GRAPH_CYCLE_OR_DEPTH')
                seen.add(current['name']);current=lookup[current['parent']['role']]
            key=digest(role);need(key not in by_hash,'DUPLICATE_ROLE');by_hash[key]=role
        unions=[r for r in roles if r['command']['mode']=='EXACT_ARGV_OR_NUL_PADDED_TITLES']
        from epoch7_openclaw_recipe import DIRECT_WRAPPER_SHA
        direct=sources.get('/home/xuanjun_dev/.openclaw/bin/openclaw')==DIRECT_WRAPPER_SHA
        if unions or direct:
            need('quiet_startup' in block,'SOURCE_BACKED_QUIET_POLICY_REQUIRED')
            from epoch7_openclaw_recipe import source_hashes, DIRECT_WRAPPER_SHA, DIRECT_PACKAGE_ROOT, DIRECT_NODE_PATH, SOURCE_HASHES
            root=block['quiet_startup']['package_root']
            direct=sources.get('/home/xuanjun_dev/.openclaw/bin/openclaw')==DIRECT_WRAPPER_SHA
            pins=source_hashes(sources.get('/home/xuanjun_dev/.openclaw/bin/openclaw'))
            need(all(sources.get(root+'/'+name)==pin for name,pin in pins.items()),
                 'EXACT_OPENCLAW_BOOTSTRAP_SOURCE_PROFILE')
        if (unions or direct) and unit=='xuanjun-uk-openclaw.service':
            if direct:
                main=lookup['main'];bridge=lookup.get('bridge_main')
                need(root==DIRECT_PACKAGE_ROOT and block['topology_source_sha256']==SOURCE_HASHES['dist/entry.js'] and
                     set(names)=={'main','bridge_main'} and {r['name'] for r in unions}=={'main'} and
                     main['identity']['executable']==DIRECT_NODE_PATH,'GATEWAY_DIRECT_ENTRY_ROLE_SET')
                need(bridge is not None and not bridge['main'] and bridge['maximum']==1 and
                     bridge['parent']=={'kind':'ROLE','role':'main'} and
                     bridge['command']['mode']=='EXACT_ARGV_SHA256' and
                     bridge['identity']['executable']!=main['identity']['executable'] and
                     all(bridge['identity'][k]==main['identity'][k] for k in ('uids','gids','groups')),
                     'GATEWAY_DIRECT_BRIDGE_IDENTITY_AND_PARENT')
                continue
            need({r['name'] for r in unions}=={'main','compile_cache_child'},'GATEWAY_BOOTSTRAP_ROLE_SET')
            main=lookup['main'];child=lookup['compile_cache_child']
            need(main['main'] and not child['main'] and child['parent']=={'kind':'ROLE','role':'main'} and
                 child['identity']==main['identity'] and
                 all(child[k]==main[k] for k in ('executable_dev','executable_ino')) and
                 all(r in unions or r['identity']['executable']!=main['identity']['executable'] for r in roles),
                 'GATEWAY_TWO_NODE_IDENTITY_AND_PARENT')
    return by_hash


def _receipt(value,context_sha,operation,unit=None):
    need(type(value) is dict and set(value)==RECEIPT_KEYS,'SUCCESS_RECEIPT_SCHEMA')
    argv=['/usr/bin/systemctl','daemon-reload'] if operation=='daemon_reload' else ['/usr/bin/systemctl','start',unit]
    need(value['context_sha256']==context_sha and value['phase']=='activate_new_services' and
         value['operation']==operation and value['argv_sha256']==argv_hash(argv) and
         type(value['returncode']) is int and value['returncode']==0,'OWN_SUCCESS_RECEIPT_BINDING')
    _int(value['sequence'],1)
    need(value['sequence']<=9999,'SUCCESS_RECEIPT_SEQUENCE_BOUND')


def validate_evidence(value,contract,checkpoint,rows,memberships,unit_rows,context_sha,digest,allow_pending=False):
    """Return PID->role hash after complete structural and delivery validation."""
    need(type(value) is dict and set(value)=={'context_sha256','units','processes'},'EVIDENCE_SCHEMA')
    need(type(allow_pending) is bool,'PENDING_BOOLEAN')
    blocks=contract['units']
    active={u for u in blocks if checkpoint['units'][u]['properties']['ActiveState']=='active'}
    need(type(value['units']) is dict and set(value['units'])==active,'ACTIVE_PROVENANCE_SET')
    scoped={pid for pid,unit in memberships.items() if unit in blocks}
    need(type(value['processes']) is dict and set(value['processes'])=={str(p) for p in scoped}, 'COMPLETE_SCOPED_ANCESTRY')
    if active:
        _hash(context_sha);need(value['context_sha256']==context_sha,'CURRENT_ATTEMPT_CONTEXT')
    else:
        need(value['context_sha256'] is None and not scoped,'STOPPED_EVIDENCE_SCOPE')
    meta={}
    for text,pair in value['processes'].items():
        need(type(pair) is dict and set(pair)=={'before','after'} and pair['before']==pair['after'], 'ANCESTRY_IDENTITY_RACE')
        row=pair['before'];need(type(row) is dict and set(row)==META_KEYS,'ANCESTRY_FIELDS')
        _int(row['ppid'],1);_int(row['parent_starttime'],1)
        _int(row['executable_dev']);_int(row['executable_ino'],1);_int(row['cmdline_size'],1)
        need(row['cmdline_size']<=16384,'CMDLINE_SIZE_BOUND')
        need(row['cmdline_title'] is None or type(row['cmdline_title']) is str and
             0<len(row['cmdline_title'])<=4096 and all(32<=ord(x)<=126 for x in row['cmdline_title']), 'OBSERVED_TITLE')
        meta[int(text)]=row
    assigned={};names={};counts={}
    for unit in active:
        evidence=value['units'][unit]
        expected={'sources','reload','start','persistence'}
        if 'quiet_startup' in blocks[unit]:expected.add('quiet_startup')
        need(type(evidence) is dict and set(evidence)==expected and
             evidence['sources']==blocks[unit]['sources'],'CURRENT_SOURCE_PINS')
        if 'quiet_startup' in blocks[unit]:
            need(evidence['quiet_startup']==blocks[unit]['quiet_startup'],'CURRENT_QUIET_STARTUP_PROJECTION')
        need(evidence['persistence'] in ('OWN_CAPTURE_PENDING_PUBLICATION','PERSISTED'),'RECEIPT_PERSISTENCE')
        need(allow_pending or evidence['persistence']=='PERSISTED','PERSISTED_BOUNDARY_REQUIRED')
        _receipt(evidence['reload'],context_sha,'daemon_reload')
        _receipt(evidence['start'],context_sha,'service_start',unit)
        need(evidence['reload']['sequence']<evidence['start']['sequence'],'RELOAD_BEFORE_START')
        roles=blocks[unit]['roles'];main_pid=unit_rows[unit]['before']['MainPID']
        for pid in sorted(p for p in scoped if memberships[p]==unit):
            identity=rows[str(pid)]['before'];observed=meta[pid];matches=[]
            for role in roles:
                if any(identity[k]!=v for k,v in role['identity'].items()):continue
                if any(observed[k]!=role[k] for k in ('executable_dev','executable_ino')):continue
                if role['main'] is not (pid==main_pid):continue
                if role['name'] in ('bridge_main','bridge_child'):
                    # Exact main-vs-descendant ancestry also distinguishes the
                    # two mutually exclusive, otherwise identical bridge roles.
                    if (role['parent']['role']=='main') is not (observed['ppid']==main_pid):continue
                command=role['command']
                if command['mode']=='EXACT_ARGV_SHA256':
                    if identity['argv_sha256']!=command['sha256']:continue
                elif not (command['mode']=='EXACT_ARGV_OR_NUL_PADDED_TITLES' and
                          identity['argv_sha256']==command['sha256']):
                    title=observed['cmdline_title']
                    if title not in command['values']:continue
                    raw=title.encode('ascii')
                    if len(raw)>observed['cmdline_size']:continue
                    raw+=b'\0'*(observed['cmdline_size']-len(raw))
                    if hashlib.sha256(raw).hexdigest()!=identity['argv_sha256']:continue
                matches.append(role)
            need(len(matches)==1,'UNREVIEWED_OR_AMBIGUOUS_PROCESS_ROLE')
            role=matches[0];key=digest(role);assigned[pid]=key;names[pid]=role
            counts[key]=counts.get(key,0)+1;need(counts[key]<=role['maximum'],'ROLE_COUNT_EXCEEDED')
        for pid,role in list(names.items()):
            if role['unit']!=unit:continue
            parent=meta[pid]['ppid']
            need(str(parent) in rows and meta[pid]['parent_starttime']==rows[str(parent)]['before']['starttime'],
                 'PARENT_STARTTIME_BINDING')
            if role['main']:
                need(parent==1 and '1' in rows and memberships.get(1) is None,'MAIN_MANAGER_ANCESTRY')
                need(assigned[pid]==checkpoint['units'][unit]['main_role_sha256'],'MAIN_ROLE_BINDING')
            else:
                need(parent in names and memberships.get(parent)==unit and
                     names[parent]['name']==role['parent']['role'],'CHILD_SAME_CGROUP_PARENT')
            visited=set();current=pid
            while current!=main_pid:
                need(current not in visited and len(visited)<4,'PROCESS_ANCESTRY_CYCLE_OR_DEPTH')
                visited.add(current);current=meta[current]['ppid']
                need(current in meta and memberships.get(current)==unit,'ANCESTRY_ESCAPED_UNIT')
        need(main_pid in assigned,'SCOPED_MAIN_MISSING')
        if unit=='xuanjun-uk-openclaw.service' and any(
                r['command']['mode']=='EXACT_ARGV_OR_NUL_PADDED_TITLES' for r in roles):
            cache=[pid for pid,r in names.items() if r['unit']==unit and r['name']=='compile_cache_child']
            if cache:
                main=next(r for r in roles if r['main'])
                need(rows[str(main_pid)]['before']['argv_sha256']==main['command']['sha256'],
                     'CACHE_PARENT_MUST_RETAIN_INITIAL_ARGV')
            bridges=[pid for pid,r in names.items() if r['unit']==unit and r['name'] in ('bridge_main','bridge_child')]
            need(len(bridges)<=1,'ONE_NATIVE_BRIDGE_OVERALL')
            for pid in bridges:
                need(meta[meta[pid]['ppid']]['cmdline_title']=='openclaw-gateway',
                     'BRIDGE_PARENT_MUST_BE_SERVING_GATEWAY')
    return assigned
