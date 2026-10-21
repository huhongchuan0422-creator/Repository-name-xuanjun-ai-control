import os,sys,stat,json,hashlib,subprocess,signal,time,ast,tokenize,io,re,socket,ssl
HOST=os.uname().nodename.split('.')[0]
UK='iZd7oeikknn1z21sq6ji6zZ'; CN='iZvt5t8tlrm8oiZ'
if os.geteuid()!=0 or HOST not in (UK,CN):raise SystemExit('HOLD_HOST_OR_ROOT')
def deadline(*args):raise SystemExit('HOLD_120_SECONDS_PARTIAL_JSON_ABOVE')
signal.signal(signal.SIGALRM,deadline);signal.alarm(120)
def emit(k,v):print(json.dumps({'host':HOST,'item':k,'value':v},ensure_ascii=True),flush=True)
def read(p,n):
    p=os.path.abspath(p)
    parts=p.split('/');cur='/'
    for x in parts[1:]:
        cur=os.path.join(cur,x)
        if stat.S_ISLNK(os.lstat(cur).st_mode):raise ValueError('SYMLINK_NOT_READ')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        q=os.fstat(fd)
        if not stat.S_ISREG(q.st_mode) or q.st_size>n:raise ValueError('SIZE_OR_TYPE')
        b=os.read(fd,n+1)
        if len(b)>n:raise ValueError('SIZE_LIMIT')
        return b
    finally:os.close(fd)
def cmd(args,n=65536):
    import tempfile
    with tempfile.TemporaryFile() as f:
        p=subprocess.Popen(args,stdout=f,stderr=subprocess.DEVNULL,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C'},start_new_session=True)
        end=time.monotonic()+7
        while p.poll() is None:
            if time.monotonic()>end or os.fstat(f.fileno()).st_size>n:
                os.killpg(p.pid,9);p.wait();raise ValueError('COMMAND_BOUND')
            time.sleep(.05)
        if p.returncode:raise ValueError('COMMAND_EXIT_'+str(p.returncode))
        f.seek(0);b=f.read(n+1)
        if len(b)>n:raise ValueError('OUTPUT_BOUND')
        return b.decode('utf-8','replace')
def attempt(k,fn):
    try:emit(k,fn())
    except Exception as e:emit(k,{'status':'UNKNOWN','reason':type(e).__name__})
emit('begin',{'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'scope':'READ_ONLY','reservations':'UNKNOWN_NOT_INFERRED'})
if HOST==UK:
    emit('cpu',{'online':os.cpu_count(),'affinity':len(os.sched_getaffinity(0))})
    attempt('memory',lambda:'\n'.join(x for x in read('/proc/meminfo',32768).decode().splitlines() if x.split(':')[0] in ('MemTotal','MemAvailable','SwapTotal','SwapFree')))
    attempt('cgroups',lambda:read('/proc/cgroups',32768).decode())
    attempt('mounts',lambda:'\n'.join(x for x in read('/proc/mounts',65536).decode().splitlines() if 'cgroup' in x.split()[2]))
    for p in ['/sys/fs/cgroup/cpu/cpu.cfs_quota_us','/sys/fs/cgroup/cpu/cpu.cfs_period_us','/sys/fs/cgroup/memory/memory.limit_in_bytes','/sys/fs/cgroup/memory/memory.usage_in_bytes','/sys/fs/cgroup/pids/pids.max','/sys/fs/cgroup/pids/pids.current']:
        attempt(p,lambda p=p:read(p,4096).decode())
    for p in ['/','/var/lib/docker','/opt','/home']:
        def fs(p=p):
            v=os.statvfs(p);return {'available_bytes':v.f_bavail*v.f_frsize,'total_bytes':v.f_blocks*v.f_frsize,'available_inodes':v.f_favail}
        attempt('filesystem:'+p,fs)
    fmt='{{.Id}} {{.Name}} {{.State.Status}} {{.HostConfig.NanoCpus}} {{.HostConfig.CpuQuota}} {{.HostConfig.CpuPeriod}} {{.HostConfig.Memory}} {{.HostConfig.MemorySwap}} {{.HostConfig.PidsLimit}} {{.HostConfig.LogConfig.Type}} {{index .HostConfig.LogConfig.Config "max-size"}} {{index .HostConfig.LogConfig.Config "max-file"}}'
    def containers():
        ids=cmd(['docker','ps','-aq','--no-trunc'],8192).split()
        if len(ids)>48 or any(not re.fullmatch('[0-9a-f]{64}',x) for x in ids):raise ValueError('CONTAINER_COUNT')
        return cmd(['docker','inspect','--format',fmt]+ids,32768) if ids else 'NO_CONTAINERS'
    attempt('containers_whitelisted_limits',containers)
    attempt('filesystem_types',lambda:cmd(['findmnt','-rn','-o','TARGET,FSTYPE,OPTIONS','-T','/var/lib/docker'],8192))
    emit('budget',{'community_fraction_max':'1/5','video_fraction_max':'1/3','B5_P2_reserved':'UNKNOWN_REQUIRES_EXISTING_APPROVED_RECORD','limits_set':False,'quotas_enforceable':'UNKNOWN_REQUIRES_VOLUME_SPECIFIC_EVIDENCE'})
else:
    ROOT='/home/openclaw_ops/v8-domestic-operations/releases/domestic-real-ai-runtime-20261008-dual-channel-referral-r11/app'
    emit('source_root',ROOT)
    seen=0;dirs=0;total=0;hits=0
    # No followlinks, database contents, env, configuration bodies or application imports.
    for base,children,names in os.walk(ROOT,followlinks=False):
        dirs+=1
        if dirs>128:emit('scan_stop','DIRECTORY_LIMIT');break
        children[:]=sorted(x for x in children if x not in ('.git','__pycache__','node_modules','venv','.venv','runtime','logs','data') and not os.path.islink(os.path.join(base,x)))
        for name in sorted(names):
            if not name.endswith('.py'):continue
            seen+=1
            if seen>384 or total>=8388608:break
            p=os.path.join(base,name)
            try:b=read(p,262144);total+=len(b);s=b.decode('utf-8');t=ast.parse(s)
            except Exception:continue
            selected=[];routes=[]
            for node in ast.walk(t):
                if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)) and (node.name in ('CustomerSource','CustomerRepository','AuditRepository') or re.search('auth|session|wechat|openid|mapping|identity',node.name,re.I)):
                    selected.append({'name':node.name,'line':node.lineno})
                if isinstance(node,ast.Str) and re.fullmatch('/[A-Za-z0-9_/{}/.:-]{1,150}',node.s) and re.search('auth|login|session|wechat|identity',node.s,re.I):routes.append(node.s)
            if selected or routes or name in ('customer_context_core.py','internal_provider_neutral_bridge.py','pr122_customer_core.py'):
                hits+=1
                if hits>48:continue
                emit('source',{'path':os.path.relpath(p,ROOT),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'definitions':selected[:48],'route_literals':sorted(set(routes))[:24]})
                if name in ('models.py','repositories.py') or any(x['name'] in ('CustomerSource','CustomerRepository','AuditRepository') for x in selected):
                    # All string/comment contents removed; never export raw configuration or literals.
                    toks=[]
                    for tok in tokenize.generate_tokens(io.StringIO(s).readline):
                        if tok.type==tokenize.STRING:tok=tok._replace(string="'<REDACTED_LITERAL>'")
                        elif tok.type==tokenize.COMMENT:tok=tok._replace(string='# REDACTED')
                        toks.append(tok)
                    safe=tokenize.untokenize(toks)
                    if len(safe.encode())<=65536:emit('private_redacted_source',{'path':os.path.relpath(p,ROOT),'text':safe})
                    else:emit('source_gap','REDACTED_FILE_OVER_64K')
        if seen>384 or total>=8388608:emit('scan_stop','FILE_OR_BYTE_LIMIT');break
    emit('scan_summary',{'dirs':dirs,'files_seen':seen,'bytes_read':total,'hits':hits,'absence_scope':'BOUNDED_ROOT_ONLY_NOT_GLOBAL'})
    for rel in ['runtime/internal-bridge/tls/bridge.crt','runtime/internal-bridge/secrets/bridge_hmac.current']:
        p='/home/openclaw_ops/v8-domestic-operations/'+rel
        def meta(p=p):
            q=os.lstat(p);return {'uid':q.st_uid,'gid':q.st_gid,'mode':oct(stat.S_IMODE(q.st_mode)),'size':q.st_size,'symlink':stat.S_ISLNK(q.st_mode),'contents_read':False}
        attempt('config_metadata:'+rel,meta)
    def units():
        s=cmd(['systemctl','list-units','--type=service','--all','--plain','--no-legend'],65536)
        names=[x.split()[0] for x in s.splitlines() if re.search('customer|domestic|provider-neutral|community',x,re.I)]
        if len(names)>16:raise ValueError('UNIT_LIMIT')
        return cmd(['systemctl','show','--no-pager','-p','Id','-p','ActiveState','-p','SubState','-p','MainPID','-p','WorkingDirectory','-p','FragmentPath']+names,16384) if names else 'NO_MATCH_WITHIN_LIST'
    attempt('running_unit_metadata',units)
# Read only exact-domain server blocks; never dump complete nginx configuration.
def routes():
    import glob
    paths=['/etc/nginx/nginx.conf']+sorted(glob.glob('/etc/nginx/conf.d/*.conf'))+sorted(glob.glob('/etc/nginx/sites-enabled/*'))
    if len(paths)>48:raise ValueError('NGINX_FILE_LIMIT')
    found=[];used=0
    for path in paths:
        try:b=read(path,131072)
        except Exception:continue
        used+=len(b)
        if used>1048576:raise ValueError('NGINX_BYTE_LIMIT')
        text=b.decode('utf-8','replace')
        # Ignore comments, require balanced server blocks; no includes followed.
        text=re.sub(r'(?m)#.*$','',text)
        for m in re.finditer(r'\bserver\s*\{',text):
            start=m.end();depth=1;pos=start
            while pos<len(text) and depth:
                if text[pos]=='{':depth+=1
                elif text[pos]=='}':depth-=1
                pos+=1
            block=text[start:pos-1]
            if depth or not re.search(r'\bserver_name\s+[^;]*\bcommunity-preview\.wenwenwenyiyiyi\.work\s*;',block):continue
            fields=[]
            for item in re.finditer(r'\b(listen|server_name|location|proxy_pass)\s+([^;{}]+)[;{]',block):
                value=item.group(2).strip()
                if len(value)<=200 and re.fullmatch(r'[A-Za-z0-9_./:$*\[\] -]+',value):fields.append([item.group(1),value])
            found.append({'file':path,'sha256':hashlib.sha256(b).hexdigest(),'fields':fields[:32]})
    return {'blocks':found,'includes_not_followed':True,'no_match_means':'UNKNOWN_NOT_PROOF_OF_NO_ROUTE'}
attempt('verified_domain_route_fields',routes)
# Public domain only; fixed GET, no cookies/authorization/proxy/redirects.
DOMAIN='community-preview.wenwenwenyiyiyi.work'
attempt('public_dns',lambda:cmd(['getent','ahosts',DOMAIN],8192))
def health():
    import urllib.request,urllib.error
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    ctx=ssl.create_default_context()
    with socket.create_connection((DOMAIN,443),timeout=5) as s:
        with ctx.wrap_socket(s,server_hostname=DOMAIN) as q:
            emit('public_tls',{'sha256':hashlib.sha256(q.getpeercert(binary_form=True)).hexdigest(),'notAfter':q.getpeercert().get('notAfter'),'verified':True})
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ctx),NoRedirect())
    try:r=op.open('https://'+DOMAIN+'/community/health',timeout=5)
    except urllib.error.HTTPError as e:r=e
    with r:
        b=r.read(4097);status=r.code
        out={'http':status,'body_bytes_capped':len(b),'content_type':r.headers.get_content_type()}
        if len(b)<=4096:
            try:
                d=json.loads(b.decode())
                out['public_fields']={k:v for k,v in d.items() if k in ('status','scope','ready') and type(v) in (str,bool,int) and len(str(v))<=100}
            except Exception:out['json']='INVALID_OR_NOT_OBJECT'
        return out
attempt('public_health',health)
emit('end',{'state':'READ_ONLY_COLLECTION_FINISHED_NOT_ACCEPTANCE','mapping':'UNKNOWN_PENDING_SOURCE_REVIEW'})
signal.alarm(0)
