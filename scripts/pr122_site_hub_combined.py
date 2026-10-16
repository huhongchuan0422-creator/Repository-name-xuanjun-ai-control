#!/usr/bin/env python3
"""PR122 fixed-host combined transaction. No production approval is bundled.

CLI is root/manual-operator only. Test injection is Python-only, never a CLI flag.
Interrupted apply is not resumable: inspect, then explicitly roll back this ID.
"""
from __future__ import annotations
import argparse
import base64
import ctypes
import datetime as dt
import fcntl
import gzip
import hashlib
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys
import tarfile
import time
from types import SimpleNamespace
import urllib.parse
import uuid

HERE=Path(__file__).resolve()
REPO=HERE.parents[1]
PINS_PATH=REPO/'deploy/pr122-site-hub-combined/HOST_PINS.json'
PREFLIGHT_PATH=REPO/'scripts/pr122_site_hub_host_preflight.py'
PREFLIGHT_SHA='6b6a8b5fab42c54970d49e41cd1572dfbc58683f0ab90ac993d43653d9f39138'
BASE=Path('/var/www/wenwenwenyiyiyi.work')
CONTROL=Path('/var/lib/xuanjun-pr122-site-hub')
RUNTIME=Path('/var/lib/xuanjun-site-hub-preview')
UNIT=Path('/etc/systemd/system/xuanjun-site-hub-preview.service')
ENABLE=Path('/etc/systemd/system/multi-user.target.wants/xuanjun-site-hub-preview.service')
INSTALLED_PUBLISHER=Path('/usr/local/libexec/pr122_website_release.py')
HTTPS=Path('/etc/nginx/conf.d/pr122-apex-https.conf')
LIMIT=Path('/etc/nginx/conf.d/pr122-site-hub-limit.conf')
LOCATIONS=Path('/etc/nginx/pr122-site-hub/locations.conf')
SERVICE='xuanjun-site-hub-preview.service'
HOST='wenwenwenyiyiyi.work'
RELEASE='pr122-site-hub-dd810410'
ANCHOR=b'include /etc/nginx/pr122-minimal-cutover/apex.locations.conf;'
INCLUDE=b'include /etc/nginx/pr122-site-hub/locations.conf;\n    '

class Hold(RuntimeError):pass

def sha(data):return hashlib.sha256(data).hexdigest()
def canonical(data):return (json.dumps(data,sort_keys=True,indent=2)+'\n').encode()
def need(ok,why):
    if not ok:raise Hold(why)
def exists(p):return p.exists() or p.is_symlink()
def sync_dir(p):
    fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)

def trusted(p,directory=False):
    p=Path(p)
    need(p.is_absolute() and '..' not in p.parts,'UNSAFE_ABSOLUTE_PATH')
    for ancestor in [p,*p.parents]:
        i=ancestor.lstat();mode=stat.S_IMODE(i.st_mode)
        need(not stat.S_ISLNK(i.st_mode) and i.st_uid==os.geteuid(),'UNTRUSTED_OWNER_OR_LINK:'+str(ancestor))
        need(not mode&0o022,'WRITABLE_TRUST_CHAIN:'+str(ancestor))
        if ancestor!=p:need(stat.S_ISDIR(i.st_mode),'NON_DIRECTORY_ANCESTRY')
    need(p.is_dir() if directory else p.is_file(),'WRONG_OBJECT_TYPE')
    return p

def read(p):
    trusted(p);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        need(before.st_size<=16000000,'INPUT_SIZE_LIMIT')
        with os.fdopen(os.dup(fd),'rb') as stream:data=stream.read(16000001)
        after=os.fstat(fd)
        need((before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns),'INPUT_CHANGED')
        return data
    finally:os.close(fd)

def mkdir(p,mode):
    if exists(p):trusted(p,True);need(stat.S_IMODE(p.stat().st_mode)==mode,'DIRECTORY_MODE_DRIFT:'+str(p));return
    trusted(p.parent,True);p.mkdir(mode=mode);sync_dir(p.parent)

def write(p,data,mode=0o644,expected=None):
    """Create absent objects exclusively, or compare-and-replace one pinned file."""
    trusted(p.parent,True)
    if expected is None:
        need(not exists(p),'NEW_OBJECT_COLLISION:'+str(p))
        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
        try:
            view=memoryview(data)
            while view:view=view[os.write(fd,view):]
            os.fsync(fd)
        finally:os.close(fd)
    else:
        need(sha(read(p))==expected,'COMPARE_REPLACE_DRIFT:'+str(p))
        temp=p.with_name('.'+p.name+'.'+uuid.uuid4().hex)
        write(temp,data,mode)
        need(sha(read(p))==expected,'COMPARE_REPLACE_DRIFT:'+str(p))
        os.replace(temp,p)
    sync_dir(p.parent)

def atomic(p,value):
    data=canonical(value)
    write(p,data,0o600,sha(read(p)) if exists(p) else None)

def load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def verified_entries(raw,pins):
    need(sha(raw)==pins['static_artifact_sha256'],'FROZEN_ARCHIVE_HASH')
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        members=archive.getmembers();need(len(members)==447,'ARCHIVE_COUNT')
        names=[m.name for m in members]
        need(len(set(names))==len(names),'ARCHIVE_DUPLICATES')
        need(all(m.isfile() and m.name.startswith('pr122-site-hub/') and '..' not in Path(m.name).parts and m.size<=1000000 for m in members),'ARCHIVE_TYPE_OR_PATH')
        data={m.name.removeprefix('pr122-site-hub/'):archive.extractfile(m).read() for m in members}
    manifest=data['PACKAGE_MANIFEST.json'];need(sha(manifest)==pins['package_manifest_sha256'],'PACKAGE_MANIFEST_HASH')
    records=json.loads(manifest)['files'];need(len(records)==446 and len({r['path'] for r in records})==446,'MANIFEST_COUNT')
    need(set(data)=={r['path'] for r in records}|{'PACKAGE_MANIFEST.json'},'MANIFEST_MEMBERS')
    for row in records:need(len(data[row['path']])==row['size'] and sha(data[row['path']])==row['sha256'],'MEMBER_HASH:'+row['path'])
    need(sha(data['bin/pr122_website_release.py'])==pins['publisher_sha256'],'PUBLISHER_HASH')
    return data

def locations(entries):
    """Only exact, manifest-bound files and their index aliases; no broad prefix."""
    new=[p for p,h in json.loads(entries['source-pin.json'])['overlay_baselines'].items() if h is None]
    need(len(new)==90,'NEW_FILE_COUNT')
    routes={}
    for name in new:
        need(re.fullmatch(r'[A-Za-z0-9_./-]+',name) is not None and '..' not in Path(name).parts,'ROUTE_PATH')
        routes['/'+name]=('file','/'+name)
        if name.endswith('/index.html'):
            directory='/'+name[:-10]
            routes[directory]=('file','/'+name)
            routes[directory.rstrip('/')]=('redirect',directory)
    text='# PR122 exact new public files only; preserve all original routes.\n'
    for route,(kind,target) in sorted(routes.items()):
        if kind=='redirect':text+='location = '+route+' { return 308 '+target+'; }\n'
        else:
            mime='    types { application/javascript js mjs; }\n    default_type application/javascript;\n' if target.endswith(('.js','.mjs')) else '    default_type text/css;\n' if target.endswith('.css') else '    default_type text/html;\n'
            text+='location = '+route+' {\n    include /etc/nginx/pr122-minimal-cutover/static-security.conf;\n'+mime+'    try_files '+target+' =404;\n}\n'
    text+=entries['runtime-config/server-location.conf'].decode()
    return text.encode(),routes

def approval(value,pins,wrapper_hash,pins_hash,transaction,now=None):
    now=time.time() if now is None else now
    fields={'decision':'RELEASE_APPROVED','operation':'PR122_COMBINED_WEBSITE','transaction_id':transaction,
            'source_head':pins['source_head'],'wrapper_sha256':wrapper_hash,'host_pins_sha256':pins_hash,
            'static_artifact_sha256':pins['static_artifact_sha256'],'package_manifest_sha256':pins['package_manifest_sha256']}
    for key,wanted in fields.items():need(value.get(key)==wanted,'RELEASE_GATE:'+key)
    need(value.get('independent_review')=='PASS' and value.get('reviewer_role')=='INDEPENDENT_AUDITOR','INDEPENDENT_GATE_REQUIRED')
    need(isinstance(value.get('review_comment_id'),int) and value['review_comment_id']>6207883697,'NEW_PACKAGING_REVIEW_REQUIRED')
    need(isinstance(value.get('release_comment_id'),int) and value['release_comment_id']>6207883697,'SEPARATE_RELEASE_DECISION_REQUIRED')
    issued=value.get('issued_unix');until=value.get('expires_unix')
    need(type(issued) is int and type(until) is int and issued<=now<until and 0<until-issued<=86400,'EXPIRED_OR_INVALID_GATE')
    return fields

class Ops:
    """Production effects are confined to these fixed commands and HTTPS probes."""
    def command(self,args):
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=25)
        need(p.returncode==0,'COMMAND_FAILED:'+args[0]+':'+str(p.returncode))
        return p.stdout
    def unit(self):
        fields=['LoadState','ActiveState','SubState','MainPID','FragmentPath','ControlGroup','DynamicUser','NoNewPrivileges','ProtectSystem','PrivateTmp','PrivateDevices','ProtectHome','IPAddressDeny','IPAddressAllow','RestrictAddressFamilies','MemoryMax','TasksMax']
        out=self.command(['/usr/bin/systemctl','show',SERVICE,*['--property='+x for x in fields]])
        return dict(line.split('=',1) for line in out.splitlines() if '=' in line)
    def vacant(self):
        out=self.command(['/usr/sbin/ss','-H','-lnt'])
        need(not re.search(r':18793\s',out),'PORT_CONFLICT')
    def nginx_test(self):self.command(['/usr/sbin/nginx','-t'])
    def nginx_identity(self):
        out=self.command(['/usr/bin/systemctl','show','nginx.service','--property=MainPID','--property=ActiveState'])
        fields=dict(line.split('=',1) for line in out.splitlines() if '=' in line)
        need(fields.get('ActiveState')=='active','NGINX_SERVICE_NOT_ACTIVE')
        pid=int(fields.get('MainPID','0'));need(pid>1,'NGINX_MAINPID_UNKNOWN')
        executable=os.readlink('/proc/'+str(pid)+'/exe');need(executable=='/usr/sbin/nginx','NGINX_EXECUTABLE_UNKNOWN')
        title=Path('/proc/'+str(pid)+'/cmdline').read_bytes().replace(b'\0',b' ').decode().strip()
        commands=['/usr/sbin/nginx','/usr/sbin/nginx -c /etc/nginx/nginx.conf','/usr/sbin/nginx -g daemon on; master_process on;']
        need(title in ['nginx: master process '+x for x in commands],'NGINX_CONFIG_COMMAND_UNRECOGNIZED')
        return {'master_pid':pid,'executable':executable,'default_config_command_bound':True,'memory_config_identity':'NOT_INTROSPECTABLE'}
    def verify_unit(self):self.command(['/usr/bin/systemd-analyze','verify',str(UNIT)])
    def reload_manager(self):self.command(['/usr/bin/systemctl','daemon-reload'])
    def start(self):
        self.command(['/usr/bin/systemctl','start',SERVICE])
        until=time.monotonic()+8
        while time.monotonic()<until:
            try:
                with socket.create_connection(('127.0.0.1',18793),timeout=.3):return
            except OSError:time.sleep(.1)
        raise Hold('RUNTIME_READINESS_TIMEOUT')
    def stop(self):self.command(['/usr/bin/systemctl','stop',SERVICE])
    def reload_nginx(self):self.command(['/usr/bin/systemctl','reload','nginx.service'])
    def sandbox(self):
        u=self.unit();need(u.get('ActiveState')=='active' and u.get('SubState')=='running','SERVICE_NOT_RUNNING')
        need(u.get('FragmentPath')==str(UNIT),'UNIT_FRAGMENT_IDENTITY')
        for key,value in {'DynamicUser':'yes','NoNewPrivileges':'yes','ProtectSystem':'strict','PrivateTmp':'yes','PrivateDevices':'yes','ProtectHome':'yes'}.items():need(u.get(key)==value,'SANDBOX_PROPERTY:'+key)
        need(u.get('MemoryMax')=='134217728' and u.get('TasksMax')=='16' and u.get('RestrictAddressFamilies')=='AF_INET','RESOURCE_OR_ADDRESS_FAMILY_POLICY')
        need('0.0.0.0/0' in u.get('IPAddressDeny','') and '127.0.0.0/8' in u.get('IPAddressAllow',''),'IP_POLICY_MISSING')
        pid=int(u['MainPID']);need(pid>1,'MAINPID_INVALID')
        cmdline=Path('/proc/'+str(pid)+'/cmdline').read_bytes().split(b'\0')
        need(str(RUNTIME/'current/scripts/pr122_site_hub_preview.py').encode() in cmdline,'RUNTIME_EXECUTABLE_IDENTITY')
        status=dict(line.split(':',1) for line in Path('/proc/'+str(pid)+'/status').read_text().splitlines() if ':' in line)
        need(all(int(x)>0 for x in status['Uid'].split()),'RUNTIME_ROOT_IDENTITY')
        need(status.get('NoNewPrivs','').strip()=='1' and int(status['CapEff'].strip(),16)==0,'RUNTIME_PRIVILEGES')
        need(os.stat('/proc/'+str(pid)+'/ns/mnt').st_ino!=os.stat('/proc/1/ns/mnt').st_ino,'MOUNT_SANDBOX_MISSING')
        ss=self.command(['/usr/sbin/ss','-H','-lntp'])
        listeners=[line for line in ss.splitlines() if re.search(r':18793\s',line)]
        need(len(listeners)==1 and '127.0.0.1:18793' in listeners[0] and ('pid='+str(pid)+',') in listeners[0],'LISTENER_IDENTITY')
        group=u.get('ControlGroup','');need(group.startswith('/system.slice/') and '..' not in Path(group).parts and group.endswith('/'+SERVICE),'CGROUP_IDENTITY')
        need(os.uname().machine=='x86_64','BPF_QUERY_ARCH_UNKNOWN')
        class Query(ctypes.Structure):
            _fields_=[('target_fd',ctypes.c_uint32),('attach_type',ctypes.c_uint32),('query_flags',ctypes.c_uint32),('attach_flags',ctypes.c_uint32),('prog_ids',ctypes.c_uint64),('prog_cnt',ctypes.c_uint32),('pad',ctypes.c_uint32)]
        fd=os.open('/sys/fs/cgroup'+group,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        counts=[]
        try:
            libc=ctypes.CDLL(None,use_errno=True)
            for kind in (0,1):
                for flags in (0,1):
                    q=Query(target_fd=fd,attach_type=kind,query_flags=flags)
                    result=libc.syscall(321,16,ctypes.byref(q),ctypes.sizeof(q))
                    need(result==0 and q.prog_cnt>0,'CGROUP_BPF_FILTER_UNPROVEN:'+str(kind)+':'+str(flags));counts.append(q.prog_cnt)
        finally:os.close(fd)
        return {'uid':status['Uid'].split()[0],'mainpid':pid,'bpf_direct_effective_ingress_egress_program_counts':counts,'mount_namespace_separate':True}
    def request(self,path,method='GET',data=None,cookie=None,origin=None,https=False,extra=None):
        connection=http.client.HTTPSConnection(HOST,443,timeout=8) if https else http.client.HTTPConnection('127.0.0.1',18793,timeout=5)
        headers={'Host':HOST,'X-Forwarded-Proto':'https','Sec-Fetch-Site':'same-origin'}
        if cookie:headers['Cookie']=cookie
        if origin:headers['Origin']=origin
        if extra:headers.update(extra)
        raw=None if data is None else json.dumps(data).encode()
        if raw is not None:headers['Content-Type']='application/json'
        try:
            connection.request(method,path,raw,headers);r=connection.getresponse();body=r.read(2000000)
            return r.status,dict((k.lower(),v) for k,v in r.getheaders()),body
        finally:connection.close()
    def preview_probe(self,https=False):
        prefix='/_preview/community-api';a=self.request(prefix+'/session',https=https);b=self.request(prefix+'/session',https=https)
        need(a[0]==b[0]==200,'SESSION_PROBE_FAILED')
        ca=a[1].get('set-cookie','').split(';')[0];cb=b[1].get('set-cookie','').split(';')[0]
        need(ca and cb and ca!=cb,'SESSION_COOKIE_ISOLATION')
        for r in (a,b):need(all(flag in r[1].get('set-cookie','') for flag in ('Secure','HttpOnly','SameSite=Strict')),'COOKIE_FLAGS')
        va=json.loads(a[2]);vb=json.loads(b[2]);need(va.get('simulation_only') is True and va.get('provider_connected') is False,'SIMULATION_SCOPE')
        need(va['merchant_demo_capability']!=vb['merchant_demo_capability'],'SESSION_CAPABILITY_ISOLATION')
        scope={'tenant_id':'tenant1','merchant_id':'merchant1','store_id':'store1','reference':'release_probe_'+uuid.uuid4().hex}
        origin='https://'+HOST
        need(self.request(prefix+'/orders','POST',{**scope,'amount_minor':123},ca,origin,https)[0]==200,'SYNTHETIC_ORDER_CREATE')
        need(self.request(prefix+'/orders/state','POST',scope,ca,origin,https)[0]==200,'OWN_ORDER_READ')
        need(self.request(prefix+'/orders/state','POST',scope,cb,origin,https)[0]==400,'CROSS_VISITOR_ORDER_ISOLATION')
        operation={'identity':{k:scope[k] for k in ('tenant_id','merchant_id','store_id')},'operation':{'item':{'id':'release_probe','name':'synthetic','status':'ACTIVE','sort':1}}}
        need(self.request(prefix+'/admin/item','POST',operation,cb,origin,https,{'X-Local-Admin-Capability':va['merchant_demo_capability']})[0]==403,'CROSS_VISITOR_ADMIN_ISOLATION')
        need(self.request(prefix+'/orders','POST',{'amount_minor':1},ca,'https://external.example',https)[0]==403,'ORIGIN_NEGATIVE')
        need(self.request(prefix+'/not-found',https=https)[0]==404,'PREVIEW_404')
        return {'two_independent_sessions':True,'cross_visitor_order_denied':True,'cross_visitor_admin_denied':True,'origin_negative':403,'unknown_path':404,'real_payment':False}
    def smoke(self,entries,routes):
        for route,(kind,target) in routes.items():
            if kind!='file':continue
            status,headers,body=self.request(route,https=True)
            expected=entries['overlay/public'+target]
            need(status==200 and sha(body)==sha(expected),'HTTPS_STATIC:'+route)
            need('content-security-policy' in headers and headers.get('x-content-type-options')=='nosniff','HTTPS_SECURITY_HEADERS:'+route)
        need(self.request('/visual/pr122-does-not-exist',https=True)[0]==404,'STATIC_NEGATIVE_404')
        self.preview_probe(True)
        return {'manifest_routes_checked':sum(kind=='file' for kind,_ in routes.values()),'real_https':True,'production_browser':'PENDING'}

class Transaction:
    def __init__(self,inputs,transaction,ops=None,pins=None):
        need(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,60}',transaction) is not None,'TRANSACTION_ID')
        self.inputs=Path(inputs);self.id=transaction;self.ops=ops or Ops()
        self.pins=pins or json.loads(read(PINS_PATH));self.folder=CONTROL/'transactions'/transaction;self.receipt=self.folder/'receipt.json'
        self.data=None;self.entries=None;self.pub=None;self.args=None
    def bind_inputs(self):
        trusted(self.inputs,True)
        self.entries=verified_entries(read(self.inputs/'PR122_SITE_HUB_REVIEW_ONLY.tar.gz'),self.pins)
        need(sha(read(self.inputs/'PR122_TOKYO_WEBROOT_MIGRATION_SOURCE_0363531ee2f8.tar.gz'))==self.pins['source_archive_sha256'],'SOURCE_ARCHIVE_HASH')
        return self.entries
    def load_publisher(self):
        bundle=self.folder/'bundle';need(sha(read(bundle/'bin/pr122_website_release.py'))==self.pins['publisher_sha256'],'SEALED_PUBLISHER_DRIFT')
        self.pub=load_module(bundle/'bin/pr122_website_release.py','pr122_combined_frozen_publisher')
        self.args=SimpleNamespace(webroot_base=BASE,bundle=bundle,source_archive=self.inputs/'PR122_TOKYO_WEBROOT_MIGRATION_SOURCE_0363531ee2f8.tar.gz',transaction_id=self.id,release_id=RELEASE,
                                  approved_package_manifest_sha256=self.pins['package_manifest_sha256'],lock_wait_seconds=5,deadline_seconds=120,allow_non_root_test=False)
    def step(self,name,action):
        need(time.monotonic()<self.deadline,'TRANSACTION_DEADLINE_INSPECT_THEN_ROLLBACK')
        self.data['intent']=name;atomic(self.receipt,self.data)
        result=action();self.data['completed'].append(name);self.data['intent']=None;atomic(self.receipt,self.data)
        return result
    def baseline(self):
        need(os.readlink(BASE/'current')==self.pins['previous_release'],'CURRENT_BASELINE_DRIFT')
        need(sha(read(INSTALLED_PUBLISHER))==self.pins['installed_publisher_sha256'],'INSTALLED_PUBLISHER_DRIFT')
        need(sha(read(PREFLIGHT_PATH))==PREFLIGHT_SHA,'PREFLIGHT_SOURCE_DRIFT')
        inventory=load_module(PREFLIGHT_PATH,'pr122_combined_inventory').nginx_source()
        need(inventory['status']=='SOURCE_INVENTORY_COMPLETE' and inventory['disk_config_trust'],'NGINX_SOURCE_UNTRUSTED')
        observed={p:v['sha256'] for p,v in inventory['files'].items()}
        need(observed==self.pins['nginx'],'NGINX_INCLUDE_SET_OR_HASH_DRIFT')
        need(not inventory['new_location_conflict'] and not inventory['new_zone_conflict'],'NGINX_CONFLICT')
        for p in (RUNTIME,UNIT,ENABLE,LIMIT,LOCATIONS):need(not exists(p),'PREEXISTING_NEW_OBJECT:'+str(p))
        need(self.ops.unit().get('LoadState')=='not-found','PREEXISTING_PREVIEW_SERVICE')
        self.ops.vacant();self.nginx_identity=self.ops.nginx_identity();self.ops.nginx_test()
        public=Path(self.pins['previous_release'])/'public';files={}
        for p in sorted(public.rglob('*')):
            need(not p.is_symlink(),'OLD_TREE_SYMLINK')
            if p.is_file():
                raw=read(p);files[p.relative_to(public).as_posix()]={'size':len(raw),'sha256':sha(raw)}
        digest=sha(json.dumps(files,sort_keys=True,separators=(',',':')).encode())
        need(len(files)==1187 and digest==self.pins['live_digest'],'LIVE_TREE_DRIFT')
        return files
    def backup(self,files):
        backup=self.folder/'backup';mkdir(backup,0o700);nginx={}
        for number,(name,expected) in enumerate(sorted(self.pins['nginx'].items())):
            raw=read(Path(name));need(sha(raw)==expected,'BACKUP_CONFIG_DRIFT')
            copy=backup/('config-'+str(number));write(copy,raw,0o600)
            nginx[name]={'copy':copy.name,'sha256':expected,'mode':stat.S_IMODE(Path(name).stat().st_mode)}
        entries={}
        old=Path(self.pins['previous_release'])
        for name,row in files.items():
            raw=read(old/'public'/name);need(sha(raw)==row['sha256'],'BACKUP_PUBLIC_DRIFT');entries['public/'+name]=raw
        entries['release-metadata/inline-csp.conf']=read(old/'release-metadata/inline-csp.conf')
        entries['release-metadata/inline-csp.json']=read(old/'release-metadata/inline-csp.json')
        stream=io.BytesIO()
        with gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as zipped,tarfile.open(fileobj=zipped,mode='w') as archive:
            for name,raw in sorted(entries.items()):
                member=tarfile.TarInfo(name);member.size=len(raw);member.mode=0o644;archive.addfile(member,io.BytesIO(raw))
        raw=stream.getvalue();write(backup/'previous-static.tar.gz',raw,0o600)
        with tarfile.open(fileobj=io.BytesIO(read(backup/'previous-static.tar.gz'))) as archive:
            members=archive.getmembers();need(len(members)==1189,'BACKUP_MEMBER_COUNT')
            for m in members:need(m.isfile() and archive.extractfile(m).read()==entries[m.name],'BACKUP_ROUNDTRIP')
        self.data.update(backup={'nginx':nginx,'static_sha256':sha(raw),'static_files':files,'archive_verified':True},previous_link=os.readlink(BASE/'current'))
    def seal_bundle(self):
        root=self.folder/'bundle';mkdir(root,0o700)
        for name,raw in self.entries.items():
            target=root/name
            for parent in reversed(target.parent.relative_to(root).parents):
                if parent!=Path('.'):mkdir(root/parent,0o755)
            # parents includes ancestors, but not target.parent itself.
            if target.parent!=root:mkdir(target.parent,0o755)
            write(target,raw)
        os.chmod(root,0o755);self.load_publisher()
    def install_runtime(self):
        mkdir(RUNTIME,0o755);version=RUNTIME/RELEASE;mkdir(version,0o755);mkdir(version/'scripts',0o755)
        for name,raw in self.entries.items():
            if name.startswith('runtime/scripts/'):write(version/'scripts'/Path(name).name,raw)
        self.runtime_identity()
        os.symlink(str(version),RUNTIME/'current');sync_dir(RUNTIME)
        write(UNIT,self.entries['runtime-config/'+SERVICE]);self.ops.verify_unit()
        need(ENABLE.parent.is_dir(),'SYSTEMD_ENABLE_PARENT_MISSING');trusted(ENABLE.parent,True)
        os.symlink(str(UNIT),ENABLE);sync_dir(ENABLE.parent);self.ops.reload_manager()
    def runtime_identity(self):
        expected={Path(name).name:sha(raw) for name,raw in self.entries.items() if name.startswith('runtime/scripts/')}
        directory=RUNTIME/RELEASE/'scripts';actual={}
        for p in directory.iterdir():
            need(p.is_file() and not p.is_symlink() and stat.S_IMODE(p.stat().st_mode)==0o644,'RUNTIME_OBJECT_DRIFT')
            actual[p.name]=sha(read(p))
        need(actual==expected,'SEALED_RUNTIME_MANIFEST_DRIFT')
    def nginx_files(self):
        old=read(self.folder/'backup'/self.data['backup']['nginx'][str(HTTPS)]['copy'])
        need(old.count(ANCHOR)==1,'HTTPS_INCLUDE_ANCHOR')
        snippet,_=locations(self.entries)
        return {HTTPS:old.replace(ANCHOR,INCLUDE+ANCHOR),LIMIT:self.entries['runtime-config/http-limit.conf'],LOCATIONS:snippet}
    def install_nginx(self):
        mkdir(LOCATIONS.parent,0o755)
        for p,raw in self.nginx_files().items():write(p,raw,expected=self.pins['nginx'][str(HTTPS)] if p==HTTPS else None)
    def verify_before_activation(self):
        approval(self.data['approval'],self.pins,sha(read(HERE)),sha(read(PINS_PATH)),self.id)
        need(os.readlink(BASE/'current')==self.data['previous_link'],'CURRENT_CHANGED_BEFORE_ACTIVATION')
        expected=dict(self.pins['nginx']);expected.update({str(p):sha(raw) for p,raw in self.nginx_files().items()})
        inventory=load_module(PREFLIGHT_PATH,'pr122_combined_inventory').nginx_source()
        need(inventory['disk_config_trust'] and {p:v['sha256'] for p,v in inventory['files'].items()}==expected,'STAGED_CONFIG_DRIFT')
        old=Path(self.data['previous_link'])/'public'
        observed={p.relative_to(old).as_posix():{'size':p.stat().st_size,'sha256':sha(read(p))} for p in sorted(old.rglob('*')) if p.is_file()}
        need(observed==self.data['backup']['static_files'],'LIVE_TREE_CHANGED_BEFORE_ACTIVATION')
        need(sha(read(INSTALLED_PUBLISHER))==self.pins['installed_publisher_sha256'],'INSTALLED_PUBLISHER_CHANGED')
    def publisher(self,action):
        with self.pub.Deadline(120) as deadline:
            with self.pub.lock(BASE,5,deadline,os.geteuid()):return getattr(self.pub,action)(self.args,deadline)
    def apply(self,gate_path):
        self.deadline=time.monotonic()+600
        self.bind_inputs();gate=json.loads(read(gate_path));need(stat.S_IMODE(gate_path.stat().st_mode)==0o600,'APPROVAL_MODE_MUST_BE_0600')
        approval(gate,self.pins,sha(read(HERE)),sha(read(PINS_PATH)),self.id)
        files=self.baseline()
        mkdir(self.folder,0o700)
        need(not exists(self.receipt),'TRANSACTION_EXISTS_NO_APPLY_RETRY')
        self.data={'schema':1,'transaction_id':self.id,'release_id':RELEASE,'state':'APPLYING','completed':[],'intent':None,
                   'wrapper_sha256':sha(read(HERE)),'pins_sha256':sha(read(PINS_PATH)),'approval':gate,'nginx_process':self.nginx_identity,'production_browser':'NOT_RUN'}
        atomic(self.receipt,self.data)
        try:
            self.step('BACKUP_VERIFIED',lambda:self.backup(files))
            self.step('SEALED_BUNDLE',self.seal_bundle)
            self.step('STATIC_PREPARED',lambda:self.publisher('prepare'))
            self.step('RUNTIME_INSTALLED',self.install_runtime)
            self.step('RUNTIME_STARTED',self.ops.start)
            self.data['sandbox']=self.step('RUNTIME_VERIFIED',self.ops.sandbox)
            self.data['loopback']=self.step('LOOPBACK_VERIFIED',self.ops.preview_probe)
            self.step('NGINX_STAGED',self.install_nginx)
            self.step('NGINX_VALIDATED',self.ops.nginx_test)
            # Existing publisher rechecks full old tree and captures old envelope.
            self.step('ACTIVATION_DRIFT_CHECK',self.verify_before_activation)
            self.step('STATIC_ACTIVATED',lambda:self.publisher('activate'))
            self.step('NGINX_RELOADED',self.ops.reload_nginx)
            self.data['https']=self.step('HTTPS_SMOKE',lambda:self.ops.smoke(self.entries,locations(self.entries)[1]))
            self.step('STATIC_CHECK',lambda:self.publisher('check'))
            self.data.update(state='HTTPS_SMOKE_PASS_AWAIT_BROWSER',production_browser='PENDING');atomic(self.receipt,self.data)
            return self.data
        except BaseException as error:
            self.data.update(state='HOLD_PARTIAL',failure=type(error).__name__)
            atomic(self.receipt,self.data);raise
    def load_receipt(self):
        self.data=json.loads(read(self.receipt))
        need(self.data.get('transaction_id')==self.id and self.data.get('wrapper_sha256')==sha(read(HERE)) and self.data.get('pins_sha256')==sha(read(PINS_PATH)),'RECEIPT_BINDING')
        return self.data
    def rollback(self):
        self.bind_inputs();self.load_receipt()
        need(self.data['state']!='ROLLED_BACK','ALREADY_ROLLED_BACK_USE_STATUS')
        need(self.data.get('backup',{}).get('archive_verified') is True,'NO_COMPLETE_BACKUP_NO_MUTATION_TO_RESTORE')
        # Verify backup and all target identities before any recovery mutation.
        backup=self.folder/'backup';need(sha(read(backup/'previous-static.tar.gz'))==self.data['backup']['static_sha256'],'BACKUP_ARCHIVE_DRIFT')
        desired=self.nginx_files()
        for name,row in self.data['backup']['nginx'].items():need(sha(read(backup/row['copy']))==row['sha256'],'BACKUP_CONFIG_DRIFT')
        for p,raw in desired.items():
            if exists(p):need(sha(read(p)) in ({sha(raw),self.pins['nginx'][str(p)]} if p==HTTPS else {sha(raw)}),'RECOVERY_CONFIG_IDENTITY_UNKNOWN:'+str(p))
        if exists(UNIT):need(sha(read(UNIT))==sha(self.entries['runtime-config/'+SERVICE]),'RECOVERY_UNIT_DRIFT')
        for p,target in ((ENABLE,str(UNIT)),(RUNTIME/'current',str(RUNTIME/RELEASE))):
            if exists(p):need(p.is_symlink() and p.lstat().st_uid==os.geteuid() and os.readlink(p)==target,'RECOVERY_LINK_DRIFT')
        observed=os.readlink(BASE/'current');need(observed in (self.data['previous_link'],str(BASE/'releases'/RELEASE)),'CURRENT_UNKNOWN_NO_RECOVERY')
        # Foreign service adoption must never be stopped by this wrapper.
        unit=self.ops.unit()
        need(unit.get('ActiveState') in ('active','inactive','failed'),'SERVICE_STATE_UNKNOWN_NO_RECOVERY')
        if unit.get('ActiveState')=='active':
            need(exists(UNIT) and unit.get('FragmentPath')==str(UNIT),'UNKNOWN_SERVICE_NO_STOP');self.runtime_identity()
        self.data.update(state='ROLLBACK_IN_PROGRESS',intent='ROLLBACK');atomic(self.receipt,self.data)
        if exists(self.folder/'bundle/bin/pr122_website_release.py'):
            self.load_publisher();pr=BASE/'transactions'/(self.id+'.json')
            if exists(pr):
                state=json.loads(read(pr))['state']
                if state in ('ACTIVATION_INTENT','UNKNOWN_AFTER_ACTIVATE'):state=self.publisher('reconcile')['state']
                if state in ('ACTIVATED','CHECKED','CHECK_FAILED','UNKNOWN_AFTER_CHECK','ROLLBACK_INTENT','ROLLBACK_PENDING'):self.publisher('rollback')
                elif state not in ('PREPARED','HOLD_PARTIAL','ROLLED_BACK'):raise Hold('PUBLISHER_RECOVERY_STATE_UNKNOWN:'+state)
        need(os.readlink(BASE/'current')==self.data['previous_link'],'PREVIOUS_POINTER_NOT_RESTORED')
        if unit.get('ActiveState')=='active':self.ops.stop()
        need(self.ops.unit().get('ActiveState')!='active','PREVIEW_STILL_ACTIVE')
        for p in (ENABLE,RUNTIME/'current'):
            if exists(p):p.unlink();sync_dir(p.parent)
        if exists(UNIT):UNIT.unlink();sync_dir(UNIT.parent)
        for p,raw in desired.items():
            if p==HTTPS:
                original=read(backup/self.data['backup']['nginx'][str(p)]['copy'])
                if sha(read(p))!=sha(original):write(p,original,expected=sha(raw))
            elif exists(p):p.unlink();sync_dir(p.parent)
        self.ops.reload_manager();self.ops.nginx_test();self.ops.reload_nginx()
        for name,row in self.data['backup']['nginx'].items():need(sha(read(Path(name)))==row['sha256'],'RESTORED_CONFIG_MISMATCH')
        old=Path(self.data['previous_link'])/'public'
        need({p.relative_to(old).as_posix() for p in old.rglob('*') if p.is_file()}==set(self.data['backup']['static_files']),'RESTORED_OLD_FILE_SET_DRIFT')
        for name,row in self.data['backup']['static_files'].items():need(sha(read(old/name))==row['sha256'],'RESTORED_OLD_BYTES_DRIFT')
        self.data.update(state='ROLLED_BACK',intent=None,rollback_verified={'old_pointer':True,'old_public_bytes':True,'config_hashes':True,'preview_inactive':True,'real_https_browser':'PENDING'})
        atomic(self.receipt,self.data);return self.data

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['apply','rollback','status','plan'])
    parser.add_argument('--inputs',type=Path,required=True);parser.add_argument('--transaction-id',required=True);parser.add_argument('--approval',type=Path)
    args=parser.parse_args()
    need(os.geteuid()==0 and os.uname().nodename=='iZvt5t8tlrm8oiZ','FIXED_HOST_ROOT_REQUIRED')
    trusted(HERE);trusted(PINS_PATH)
    tx=Transaction(args.inputs,args.transaction_id)
    if args.command=='plan':
        tx.bind_inputs();tx.baseline();print(json.dumps({'state':'PLAN_HOLD','new_file_count':90,'gate':'SEPARATE_RELEASE_APPROVAL_REQUIRED','production_mutations':0}));return
    if args.command=='status':print(json.dumps(tx.load_receipt(),sort_keys=True));return
    if args.command=='apply':need(args.approval is not None,'APPROVAL_REQUIRED')
    if args.command=='apply':
        tx.bind_inputs();approval(json.loads(read(args.approval)),tx.pins,sha(read(HERE)),sha(read(PINS_PATH)),tx.id)
    # The controller namespace is root-private; no Runner sudo capability exists.
    mkdir(CONTROL,0o700);mkdir(CONTROL/'transactions',0o700)
    lockpath=CONTROL/'transaction.lock'
    if not exists(lockpath):write(lockpath,b'',0o600)
    trusted(lockpath);fd=os.open(lockpath,os.O_RDWR|os.O_NOFOLLOW)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Hold('COMBINED_TRANSACTION_BUSY')
        signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(Hold('SIGTERM_RESULT_REQUIRES_INSPECTION')))
        result=tx.apply(args.approval) if args.command=='apply' else tx.rollback()
        # Root-private full receipt can contain synthetic details; public result is bounded.
        print(json.dumps({'state':result['state'],'transaction_id':tx.id,'receipt':str(tx.receipt),'production_browser':result.get('production_browser','NOT_RUN')},sort_keys=True))
    finally:os.close(fd)

if __name__=='__main__':
    try:main()
    except (RuntimeError,OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
        print(json.dumps({'state':'HOLD','reason':str(error)}),file=sys.stderr);sys.exit(2)
