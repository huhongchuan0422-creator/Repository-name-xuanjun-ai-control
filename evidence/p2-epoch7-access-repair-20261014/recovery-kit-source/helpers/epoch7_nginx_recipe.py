"""Pure nginx1.24 Linux quiet-start derivation, conditional on deployed proof.

Upstream source is an explicit reviewed profile, not evidence of the installed
Alibaba build. A source-match record is merely an input consistency check here;
the complete plan review must authenticate its vendor/isolated evidence.
"""
import copy
import re

UPSTREAM = '84cd7217778b8b3a2e395194b641ea14050344f1'
PROFILE = 'NGINX_1_24_0_LINUX_QUIET_START'
SOURCE_HASHES = {
    'src/os/unix/ngx_process_cycle.c':'12f65a244e852e0c5cd3054eeaff194e93d892401e347f03f4f9b096a0bfb70d',
    'src/os/unix/ngx_setproctitle.c':'d1002d64f9ee21703098d6f0f4074804baec5f64e4da76155ecc1fa2f822d617',
    'src/os/unix/ngx_setproctitle.h':'1224bd2e46ff4783f72a72724cb49b2509aaa9e5bf9d80e842fa541400c9ab86',
    'src/os/unix/ngx_daemon.c':'15a5ea8c7865650c6fa2b26f9a7c9c027f6d5bcd83dc91a65dc907aa12c93263',
    'src/os/unix/ngx_process.c':'067dff9590e6aa2285de1f661a67566b4027ff52917b8877ecadd04f822f27d5',
    'src/core/nginx.c':'46b9463b8b0be685f1c531879089cec0d3988dda7229561e06ecfa80ab0c6c28',
    'src/os/unix/ngx_posix_init.c':'286c9456401c7135dfd9137030484657cbc1afe2c47dcd3cf6c82acefb3a62e6',
}
SCOPES = sorted(('daemon_fork_parent_exit','linux_nul_padded_process_titles',
    'master_literal_argv_title','worker_direct_fork_and_title','worker_setgid_initgroups_setuid',
    'auto_worker_count_sysconf','no_extra_module_startup_children','systemd239_inherited_root_credentials'))
UNIT='/etc/systemd/system/nginx.service'
MAIN='/etc/xuanjun-development/nginx-main.conf'
OWNER='/etc/nginx/conf.d/xuanjun-p2-owner.conf'
MIME='/etc/nginx/mime.types'
VENDOR_NEVRA=['nginx','1','1.24.0','3.0.1.2.al8.1','x86_64']
VENDOR_ELF='43f7ec506105eba63a5ddd0c1311684f24ab77c11ea647353654b9a1b3a69d3f'
VENDOR_BINARY_RPM='8925aea0993ceaa857619c1616d42b5143c07a79c658cf1888fa0a2fe05eeedc'
VENDOR_SRPM='39909d5fdbf6a2dcdadeaa86beb187d2a1ca6b5d3c9098b6a31e88afd8f0a8fc'
VENDOR_SCOPE_REVIEW='e7ef9e92bc6509bd00172265a2c49dd44afc657c8106491343db731c10bde8ad'


def need(ok,label):
    if not ok:raise ValueError('EPOCH7_NGINX_'+label)


def profile():
    return {'schema':1,'name':PROFILE,'upstream_commit':UPSTREAM,
            'source_hashes':copy.deepcopy(SOURCE_HASHES),'reviewed_scopes':list(SCOPES)}


def vendor_profile():
    return {'method':'PINNED_OFFICIAL_VENDOR_BINARY_RPM','rpm_nevra':list(VENDOR_NEVRA),
            'elf_sha256':VENDOR_ELF,'elf_size':1475304,'binary_rpm_sha256':VENDOR_BINARY_RPM,
            'srpm_sha256':VENDOR_SRPM,'scope_review_sha256':VENDOR_SCOPE_REVIEW,
            'retrieval':'OFFICIAL_HTTPS','rpm_signature':'NOT_VERIFIED'}


def mime_mapping(raw):
    need(type(raw) is bytes and 0<len(raw)<=65536,'MIME_BOUND')
    text=raw.decode('ascii')
    text='\n'.join(line.split('#',1)[0] for line in text.splitlines())
    match=re.fullmatch(r'\s*types\s*\{([^{}]*)\}\s*',text)
    need(match is not None,'MIME_TYPES_ONLY')
    body=match.group(1);need(body.rstrip().endswith(';'),'MIME_TERMINATOR')
    rows=body.split(';');need(1<len(rows)<=4097 and not rows[-1].strip(),'MIME_ROW_BOUND')
    for row in rows[:-1]:
        parts=row.split()
        need(2<=len(parts)<=64 and re.fullmatch(r'[A-Za-z0-9.+_-]+/[A-Za-z0-9.+_-]+',parts[0]) and
             all(re.fullmatch(r'[A-Za-z0-9_.+-]+',x) for x in parts[1:]),'MIME_MAPPING_ONLY')


def check_source_match(value,binary,rpm,closure_sha,recipe_sha,digest,hash_value):
    """No network/review lookup: full-plan admission authenticates this record."""
    if value is None:
        # This exact official vendor payload was inspected offline, never run.
        # A version string alone is insufficient: the fresh executable bytes
        # must match as well. Complete plan review binds this pinned profile.
        return binary==VENDOR_ELF and rpm==VENDOR_NEVRA
    common={'schema','method','upstream_commit','source_profile_sha256','binary_sha256',
            'rpm_nevra','config_closure_sha256','recipe_sha256','reviewed_scopes','evidence'}
    need(type(value) is dict and set(value)==common and type(value['schema']) is int and
         value['schema']==1 and value['upstream_commit']==UPSTREAM and
         value['source_profile_sha256']==digest(profile()) and value['binary_sha256']==binary and
         value['rpm_nevra']==rpm and value['config_closure_sha256']==closure_sha and
         value['recipe_sha256']==recipe_sha and value['reviewed_scopes']==SCOPES,'DEPLOYED_SOURCE_BINDING')
    fields=({'vendor_srpm_sha256','patchset_sha256','scope_review_sha256'}
            if value['method']=='VENDOR_SRPM_PATCH_REVIEW' else
            {'observation_sha256','isolation_contract_sha256','scope_review_sha256'}
            if value['method']=='ISOLATED_EXACT_BINARY_STARTUP' else None)
    need(fields is not None and type(value['evidence']) is dict and set(value['evidence'])==fields,
         'DEPLOYED_SOURCE_METHOD')
    for pin in value['evidence'].values():hash_value(pin)
    return True


def derive_nginx_family(compiled,facts,manifest):
    # Local import avoids a compiler/helper import cycle and performs no effects.
    import epoch7_service_contract as sc
    import epoch7_service_roles as sr
    live,d=sc.live,sc.d
    measured=facts['nginx_recipe_evidence']
    need(type(measured) is dict and set(measured)=={'schema','online_cpu_count','manager_credentials',
         'mime_types','rpm_nevra','source_match'} and type(measured['schema']) is int and
         measured['schema']==1,'MEASURED_FACT_SCHEMA')
    count=measured['online_cpu_count'];live._integer(count,1);need(count<=256,'CPU_COUNT_BOUND')
    manager=measured['manager_credentials']
    need(type(manager) is dict and set(manager)=={'uids','gids','groups'} and
         manager['uids']==manager['gids']==[0]*4 and type(manager['groups']) is list and
         manager['groups']==sorted(set(manager['groups'])) and len(manager['groups'])<=128,
         'ACTUAL_MANAGER_CREDENTIALS_REQUIRED')
    for gid in manager['groups']:live._integer(gid)
    pin=sc._executable(facts,'/usr/sbin/nginx')
    need(pin['path']=='/usr/sbin/nginx','EXACT_EXECUTABLE_PATH')
    live._integer(pin['dev']);live._integer(pin['ino'],1)
    uid,gid,groups,unused=sc._groups(facts['nss'],'nginx','nginx',())
    need(uid>0,'UNPRIVILEGED_WORKER_REQUIRED')
    rpm=measured['rpm_nevra']
    need(type(rpm) is list and len(rpm)==5 and rpm[:3]==['nginx','1','1.24.0'] and
         rpm[4]=='x86_64' and type(rpm[3]) is str and
         re.fullmatch(r'[A-Za-z0-9.+_~-]{1,128}',rpm[3]),'MATCHED_VERSION_REQUIRED')
    targets=compiled['rendered_targets'];source=facts['source_bytes']
    inventory=facts['dropin_inventory']['nginx.service']
    roots={prefix+'/nginx.service.d' for prefix in ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system')}
    need(type(inventory) is dict and set(inventory)==roots and
         all(type(row) is dict and type(row.get('present')) is bool and row.get('files')=={} and
             row.get('state')!='UNKNOWN' for row in inventory.values()),'EMPTY_EFFECTIVE_DROPIN_CLOSURE')
    fixed={UNIT:'deploy/p2-nginx.service',MAIN:'deploy/p2-nginx-main.conf'}
    for path,relative in fixed.items():
        raw=sc.raw_bytes(source[relative])
        need(sc.sha(raw)==manifest['files'][relative] and sc.raw_bytes(targets[path])==raw,
             'FIXED_UNIT_MAIN_CONFIG')
    # The profile covers precisely this known non-dynamic main configuration.
    need(sc.sha(sc.raw_bytes(targets[MAIN]))==
         'e9b99ace3444e0eaa5a9cb5c6a975e7bed31bfc3cb3a15d2e54959b3fa9daef4',
         'EXACT_NO_CACHE_MAIN_PROFILE')
    need(sc.sha(sc.raw_bytes(targets[UNIT]))==
         'a1d6e0b8cabcfcbec8d834101b70056580135e6a235bb26e293bc904172db545','EXACT_UNIT_PROFILE')
    service=sc.unit_sections(sc.raw_bytes(targets[UNIT]))['Service']
    need(not set(service)&{'User','Group','SupplementaryGroups','DynamicUser','PAMName','RootDirectory',
         'RootImage','Environment','EnvironmentFile','PassEnvironment','UnsetEnvironment'},'INHERITED_MANAGER_ONLY')
    argv=sc.literal_argv(sc.one(service,'ExecStart'))
    need(argv==['/usr/sbin/nginx','-c',MAIN] and sc.one(service,'Type')=='forking','EXACT_FORKING_LAUNCH')
    relative='deploy/uk-owner-workbench/nginx.conf.template';template=sc.raw_bytes(source[relative])
    need(sc.sha(template)==manifest['files'][relative]==
         'f72349f30c7c6beb950522967a3ce6a274285d48a12fcb531615ac0f84c410ef','OWNER_TEMPLATE_SOURCE')
    row=next(r for r in compiled['runtime']['provisioning'] if r['target']==OWNER)
    values=row['replacements']
    need(type(values) is dict and set(values)=={'@@OWNER_HOST@@','@@TLS_CERT@@','@@TLS_KEY@@'},'OWNER_REPLACEMENTS')
    need(type(values['@@OWNER_HOST@@']) is str and len(values['@@OWNER_HOST@@'])<=253 and
         re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?',values['@@OWNER_HOST@@']), 'OWNER_HOST_LITERAL')
    for name in ('@@TLS_CERT@@','@@TLS_KEY@@'):
        live._path(values[name]);need(re.fullmatch(r'/[A-Za-z0-9_./+-]+',values[name]),'TLS_PATH_LITERAL')
    rendered=template.decode('utf-8')
    for name,value in values.items():rendered=rendered.replace(name,value)
    need(rendered.encode('utf-8')==sc.raw_bytes(targets[OWNER]) and '@@' not in rendered,'OWNER_RENDER_BINDING')
    # Exact known template excludes dynamic modules, script hooks and cache paths.
    need(not re.search(r'^\s*(?:include|load_module|[a-z_]*cache_path|perl|js_import|lua_[a-z_]+)\b',
                       rendered,re.M),'OWNER_STARTUP_SCOPE')
    mime=measured['mime_types']
    need(type(mime) is dict and set(mime)=={'path','sha256','raw'} and mime['path']==MIME,
         'FIXED_MIME_PROJECTION')
    raw=sc.raw_bytes(mime['raw']);need(sc.sha(raw)==mime['sha256'],'MIME_DIGEST');mime_mapping(raw)
    sources={path:sc.sha(sc.raw_bytes(targets[path])) for path in (UNIT,MAIN,OWNER)}
    sources.update({MIME:mime['sha256'],pin['path']:pin['sha256']})
    def role(name,ident,title,parent,maximum,main):
        return {'unit':'nginx.service','name':name,'identity':dict(ident,executable=pin['path'],
            executable_sha256=pin['sha256']),'executable_dev':pin['dev'],'executable_ino':pin['ino'],
            'command':{'mode':'EXACT_NUL_PADDED_TITLE','values':[title]},'parent':parent,
            'maximum':maximum,'main':main}
    main=role('main',manager,'nginx: master process '+' '.join(argv),{'kind':'MANAGER','pid':1},1,True)
    worker=role('worker',{'uids':[uid]*4,'gids':[gid]*4,'groups':groups},'nginx: worker process',
                {'kind':'ROLE','role':'main'},count,False)
    block={'sources':sources,'topology_source_sha256':sources[UNIT],'roles':[main,worker]}
    sr.validate_contract({'schema':1,'units':{'nginx.service':block}},live.digest,live._path,live._role)
    closure=d.digest({p:sources[p] for p in (UNIT,MAIN,OWNER,MIME)})
    matched=check_source_match(measured['source_match'],pin['sha256'],rpm,closure,d.digest(block),d.digest,d.hash_value)
    return {'block':block,'source_profile':profile(),'source_profile_sha256':d.digest(profile()),
            'config_closure_sha256':closure,'recipe_sha256':d.digest(block),'deployed_source_match':matched,
            'source_match_sha256':d.digest(measured['source_match'] or vendor_profile()) if matched else None,
            'vendor_profile':vendor_profile(),
            'production_acceptance':'NOT_VERIFIED'}
