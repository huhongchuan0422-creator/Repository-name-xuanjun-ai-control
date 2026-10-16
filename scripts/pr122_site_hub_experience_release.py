#!/usr/bin/env python3
"""PR122 static UI delta over deployed r2. No Runtime install/stop or DNS operations.

Requires a new independent review and a new one-use release decision. Failed apply
is never resumed; inspect and use this transaction's explicit rollback command.
"""
import argparse
import fcntl
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import stat
import sys
import tarfile
import time

HERE=Path(__file__).resolve()
ROOT=HERE.parents[1]
PINS=ROOT/'deploy/pr122-site-hub-experience/HOST_PINS.json'
HELPER=ROOT/'scripts/pr122_site_hub_combined.py'
HELPER_SHA='8c403aac42253612c41465dbfdd3b9f43861449b2526a072ebd87bf02227cad3'

def digest(raw):return hashlib.sha256(raw).hexdigest()
def need(ok,reason):
    if not ok:raise RuntimeError(reason)

# Authenticate code before importing its root-capable helpers.
need(digest(HELPER.read_bytes())==HELPER_SHA,'HELPER_SOURCE_DRIFT')
spec=importlib.util.spec_from_file_location('pr122_ui_frozen_helper',HELPER)
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


def entries(raw,pins):
    need(digest(raw)==pins['static_artifact_sha256'],'STATIC_PACKAGE_HASH')
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        members=archive.getmembers()
        need(len(members)==449 and len({m.name for m in members})==449,'ARCHIVE_MEMBERS')
        need(all(m.isfile() and m.name.startswith('pr122-site-hub/') and '..' not in Path(m.name).parts and m.size<=8000000 for m in members),'ARCHIVE_PATH_TYPE')
        result={m.name.removeprefix('pr122-site-hub/'):archive.extractfile(m).read() for m in members}
    need(digest(result['PACKAGE_MANIFEST.json'])==pins['package_manifest_sha256'],'PACKAGE_MANIFEST_HASH')
    rows=json.loads(result['PACKAGE_MANIFEST.json'])['files']
    need(len(rows)==448 and len({r['path'] for r in rows})==448 and {r['path'] for r in rows}==set(result)-{'PACKAGE_MANIFEST.json'},'MANIFEST_MEMBERS')
    for row in rows:
        raw=result[row['path']];need(len(raw)==row['size'] and digest(raw)==row['sha256'],'MANIFEST_FILE:'+row['path'])
    need(digest(result['candidate-manifest.json'])==pins['candidate_manifest_sha256'],'CANDIDATE_HASH')
    need(digest(result['bin/pr122_website_release.py'])==pins['publisher_sha256'],'PUBLISHER_HASH')
    need(len(json.loads(result['candidate-manifest.json'])['files'])==1279,'PUBLIC_COUNT')
    return result


def routes(data):
    # Reuse the reviewed exact-location algorithm, changing only its bound count.
    names=[p for p,h in json.loads(data['source-pin.json'])['overlay_baselines'].items() if h is None]
    need(len(names)==92,'NEW_PUBLIC_COUNT')
    # Its old fixed 90 count is deliberately not disabled or globally patched.
    route_map={};text='# PR122 exact new public files only; preserve all original routes.\n'
    for name in names:
        need(c.re.fullmatch(r'[A-Za-z0-9_./-]+',name) and '..' not in Path(name).parts,'ROUTE_PATH')
        route_map['/'+name]=('file','/'+name)
        if name.endswith('/index.html'):
            directory='/'+name[:-10];route_map[directory]=('file','/'+name);route_map[directory.rstrip('/')]=('redirect',directory)
    for path,(kind,target) in sorted(route_map.items()):
        if kind=='redirect':text+='location = '+path+' { return 308 '+target+'; }\n'
        else:
            mime='    types { application/javascript js mjs; }\n    default_type application/javascript;\n' if target.endswith(('.js','.mjs')) else '    default_type text/css;\n' if target.endswith('.css') else '    default_type text/html;\n'
            text+='location = '+path+' {\n    include /etc/nginx/pr122-minimal-cutover/static-security.conf;\n'+mime+'    try_files '+target+' =404;\n}\n'
    return (text+data['runtime-config/server-location.conf'].decode()).encode(),route_map


def gate(value,pins):
    fields={'decision':'RELEASE_APPROVED','operation':'PR122_STATIC_EXPERIENCE','transaction_id':pins['transaction_id'],
            'source_head':pins['source_head'],'wrapper_sha256':digest(c.read(HERE)),'host_pins_sha256':digest(c.read(PINS)),
            'static_artifact_sha256':pins['static_artifact_sha256'],'package_manifest_sha256':pins['package_manifest_sha256'],
            'previous_receipt_sha256':pins['previous_receipt_sha256'],'rollback_approved':True,'max_executions':1}
    for key,value_expected in fields.items():need(value.get(key)==value_expected,'RELEASE_GATE:'+key)
    need(value.get('independent_review')=='PASS' and value.get('reviewer_role')=='INDEPENDENT_AUDITOR','INDEPENDENT_REVIEW_REQUIRED')
    for key in ('review_comment_id','release_comment_id'):need(type(value.get(key)) is int and value[key]>6209244057,'NEW_DECISION_REQUIRED:'+key)
    start=value.get('issued_unix');end=value.get('expires_unix')
    need(type(start) is int and type(end) is int and start<=time.time()<end and 0<end-start<=7200,'GATE_EXPIRED')


class Transaction(c.Transaction):
    def __init__(self,inputs,ops=None,pins=None):
        pins=pins or json.loads(c.read(PINS))
        super().__init__(inputs,pins['transaction_id'],ops,pins)
    def bind_inputs(self):
        c.trusted(self.inputs,True)
        self.entries=entries(c.read(self.inputs/'PR122_SITE_HUB_REVIEW_ONLY.tar.gz'),self.pins)
        need(digest(c.read(self.inputs/'PR122_TOKYO_WEBROOT_MIGRATION_SOURCE_0363531ee2f8.tar.gz'))==self.pins['source_archive_sha256'],'SOURCE_ARCHIVE_HASH')
    def load_publisher(self):
        super().load_publisher();self.args.release_id=self.pins['release_id']
    def inventory(self,expected):
        need(digest(c.read(c.PREFLIGHT_PATH))==c.PREFLIGHT_SHA,'PREFLIGHT_SOURCE_DRIFT')
        inv=c.load_module(c.PREFLIGHT_PATH,'pr122_ui_inventory').nginx_source()
        need(inv['status']=='SOURCE_INVENTORY_COMPLETE' and inv['disk_config_trust'],'NGINX_SOURCE_TRUST')
        need({p:r['sha256'] for p,r in inv['files'].items()}==expected,'NGINX_INCLUDE_OR_HASH_DRIFT')
    def snapshot(self):
        public=Path(self.pins['previous_release'])/'public';result={}
        for path in sorted(public.rglob('*')):
            need(not path.is_symlink(),'OLD_PUBLIC_SYMLINK')
            if path.is_file():
                raw=c.read(path);result[path.relative_to(public).as_posix()]={'size':len(raw),'sha256':digest(raw)}
        return result
    def runtime(self):
        # Existing r2 Runtime is verified, never installed, stopped or replaced.
        need(self.ops.unit().get('ActiveState')=='active','EXISTING_RUNTIME_NOT_ACTIVE')
        self.runtime_identity()
        need(c.read(c.UNIT)==self.entries['runtime-config/'+c.SERVICE],'RUNTIME_UNIT_DRIFT')
        need(c.RUNTIME.joinpath('current').is_symlink() and os.readlink(c.RUNTIME/'current')==str(c.RUNTIME/c.RELEASE),'RUNTIME_LINK_DRIFT')
        return self.ops.sandbox()
    def baseline(self):
        previous=c.CONTROL/'transactions/pr122-hub-icp-20261016-r2/receipt.json'
        raw=c.read(previous);need(digest(raw)==self.pins['previous_receipt_sha256'],'R2_RECEIPT_DRIFT')
        need(json.loads(raw)['state']=='HTTPS_SMOKE_PASS_AWAIT_BROWSER','R2_STATE_DRIFT')
        need(os.readlink(c.BASE/'current')==self.pins['previous_release'],'CURRENT_DRIFT')
        need(digest(c.read(c.INSTALLED_PUBLISHER))==self.pins['installed_publisher_sha256'],'INSTALLED_PUBLISHER_DRIFT')
        self.inventory(self.pins['nginx']);self.nginx_identity=self.ops.nginx_identity();self.ops.nginx_test()
        self.sandbox=self.runtime()
        old_manifest=c.read(self.inputs/'R2_CANDIDATE_MANIFEST.json')
        need(digest(old_manifest)==self.pins['previous_manifest_sha256'],'R2_MANIFEST_HASH')
        expected={r['path']:{'size':r['size'],'sha256':r['sha256']} for r in json.loads(old_manifest)['files']}
        files=self.snapshot();need(len(files)==1277 and files==expected,'R2_PUBLIC_DRIFT');return files
    def backup(self,files):
        directory=self.folder/'backup';c.mkdir(directory,0o700);configs={}
        for i,(name,expected) in enumerate(sorted(self.pins['nginx'].items())):
            raw=c.read(Path(name));need(digest(raw)==expected,'BACKUP_CONFIG_DRIFT')
            copy='config-'+str(i);c.write(directory/copy,raw,0o600)
            configs[name]={'copy':copy,'sha256':expected,'mode':stat.S_IMODE(Path(name).stat().st_mode)}
        data={}
        for name,row in files.items():
            raw=c.read(Path(self.pins['previous_release'])/'public'/name);need(digest(raw)==row['sha256'],'BACKUP_BYTES_DRIFT');data['public/'+name]=raw
        for name in ('inline-csp.conf','inline-csp.json'):data['release-metadata/'+name]=c.read(Path(self.pins['previous_release'])/'release-metadata'/name)
        stream=io.BytesIO()
        with gzip.GzipFile(fileobj=stream,mode='wb',mtime=0) as zipped,tarfile.open(fileobj=zipped,mode='w') as archive:
            for name,raw in sorted(data.items()):
                member=tarfile.TarInfo(name);member.size=len(raw);member.mode=0o644;archive.addfile(member,io.BytesIO(raw))
        c.write(directory/'previous-static.tar.gz',stream.getvalue(),0o600)
        with tarfile.open(fileobj=io.BytesIO(c.read(directory/'previous-static.tar.gz'))) as archive:
            members=archive.getmembers();need(len(members)==1279 and {m.name for m in members}==set(data),'BACKUP_MEMBERS')
            for m in members:need(m.isfile() and archive.extractfile(m).read()==data[m.name],'BACKUP_VERIFY')
        self.data.update(backup={'nginx':configs,'static_sha256':digest(stream.getvalue()),'static_files':files,'archive_verified':True},previous_link=self.pins['previous_release'])
    def before_activation(self):
        gate(self.data['approval'],self.pins)
        need(os.readlink(c.BASE/'current')==self.pins['previous_release'],'ACTIVATION_CURRENT_DRIFT')
        need(self.snapshot()==self.data['backup']['static_files'],'ACTIVATION_PUBLIC_DRIFT')
        self.inventory({**self.pins['nginx'],str(c.LOCATIONS):digest(routes(self.entries)[0])})
        need(self.ops.nginx_identity()==self.nginx_identity,'NGINX_PROCESS_DRIFT');self.runtime()
    def apply(self,path):
        self.deadline=time.monotonic()+600;self.bind_inputs()
        approval=json.loads(c.read(path));need(stat.S_IMODE(path.stat().st_mode)==0o600,'APPROVAL_MODE');gate(approval,self.pins)
        need(not c.exists(self.folder) and not c.exists(c.BASE/'transactions'/(self.id+'.json')) and not c.exists(c.BASE/'releases'/self.pins['release_id']),'TRANSACTION_ALREADY_EXISTS')
        files=self.baseline();c.mkdir(self.folder,0o700)
        self.data={'schema':1,'transaction_id':self.id,'release_id':self.pins['release_id'],'wrapper_sha256':digest(c.read(HERE)),'pins_sha256':digest(c.read(PINS)),
                   'state':'APPLYING','completed':[],'intent':None,'approval':approval,'sandbox':self.sandbox,'production_browser':'NOT_RUN'}
        c.atomic(self.receipt,self.data)
        try:
            self.step('BACKUP_VERIFIED',lambda:self.backup(files));self.step('SEALED_BUNDLE',self.seal_bundle)
            self.step('STATIC_PREPARED',lambda:self.publisher('prepare'))
            self.step('NGINX_STAGED',lambda:c.write(c.LOCATIONS,routes(self.entries)[0],expected=self.pins['nginx'][str(c.LOCATIONS)]))
            self.step('NGINX_VALIDATED',self.ops.nginx_test);self.step('ACTIVATION_DRIFT_CHECK',self.before_activation)
            self.step('STATIC_ACTIVATED',lambda:self.publisher('activate'));self.step('NGINX_RELOADED',self.ops.reload_nginx)
            self.data['https']=self.step('HTTPS_SMOKE',lambda:self.ops.smoke(self.entries,{**routes(self.entries)[1],**{'/'+p.removeprefix('overlay/public/'):('file','/'+p.removeprefix('overlay/public/')) for p in self.entries if p.startswith('overlay/public/')}}))
            self.step('STATIC_CHECK',lambda:self.publisher('check'))
            self.data.update(state='HTTPS_SMOKE_PASS_AWAIT_BROWSER',production_browser='PENDING');c.atomic(self.receipt,self.data);return self.data
        except BaseException as error:
            self.data.update(state='HOLD_PARTIAL',failure=type(error).__name__);c.atomic(self.receipt,self.data);raise
    def load_receipt(self):
        self.data=json.loads(c.read(self.receipt))
        need(self.data.get('transaction_id')==self.id and self.data.get('wrapper_sha256')==digest(c.read(HERE)) and self.data.get('pins_sha256')==digest(c.read(PINS)),'RECEIPT_BINDING')
        return self.data
    def rollback(self):
        self.bind_inputs();self.load_receipt();need(self.data['state']!='ROLLED_BACK','ALREADY_ROLLED_BACK')
        need(self.data.get('backup',{}).get('archive_verified') is True,'BACKUP_NOT_VERIFIED')
        backup=self.folder/'backup';need(digest(c.read(backup/'previous-static.tar.gz'))==self.data['backup']['static_sha256'],'BACKUP_HASH')
        for row in self.data['backup']['nginx'].values():need(digest(c.read(backup/row['copy']))==row['sha256'],'BACKUP_CONFIG_HASH')
        new=digest(routes(self.entries)[0]);old=self.pins['nginx'][str(c.LOCATIONS)]
        need(digest(c.read(c.LOCATIONS)) in (old,new),'FOREIGN_NGINX_CONFIG')
        need(os.readlink(c.BASE/'current') in (self.pins['previous_release'],str(c.BASE/'releases'/self.pins['release_id'])),'FOREIGN_CURRENT')
        expected={**self.pins['nginx'],str(c.LOCATIONS):digest(c.read(c.LOCATIONS))}
        # CSP inventory follows current; compare the new file only when active.
        old_csp=str(Path(self.pins['previous_release'])/'release-metadata/inline-csp.conf')
        if os.readlink(c.BASE/'current')!=self.pins['previous_release']:
            expected.pop(old_csp);p=c.BASE/'releases'/self.pins['release_id']/'release-metadata/inline-csp.conf'
            self.load_publisher()
            with self.pub.Deadline(120) as deadline:self.pub.receipt_for(self.args,{'ACTIVATED','CHECKED','CHECK_FAILED','UNKNOWN_AFTER_CHECK','ACTIVATION_INTENT','UNKNOWN_AFTER_ACTIVATE','ROLLBACK_INTENT','ROLLBACK_PENDING'},deadline)
            expected[str(p)]=digest(c.read(p))
        self.inventory(expected);self.runtime()
        self.data.update(state='ROLLBACK_IN_PROGRESS',intent='ROLLBACK');c.atomic(self.receipt,self.data)
        if c.exists(self.folder/'bundle/bin/pr122_website_release.py'):
            self.load_publisher();pr=c.BASE/'transactions'/(self.id+'.json')
            if c.exists(pr):
                state=json.loads(c.read(pr))['state']
                if state in ('ACTIVATION_INTENT','UNKNOWN_AFTER_ACTIVATE'):state=self.publisher('reconcile')['state']
                if state in ('ACTIVATED','CHECKED','CHECK_FAILED','UNKNOWN_AFTER_CHECK','ROLLBACK_INTENT','ROLLBACK_PENDING'):self.publisher('rollback')
                elif state not in ('PREPARED','HOLD_PARTIAL','ROLLED_BACK'):raise RuntimeError('UNKNOWN_PUBLISHER_STATE:'+state)
        need(os.readlink(c.BASE/'current')==self.pins['previous_release'],'POINTER_NOT_RESTORED')
        if digest(c.read(c.LOCATIONS))!=old:
            row=self.data['backup']['nginx'][str(c.LOCATIONS)];c.write(c.LOCATIONS,c.read(backup/row['copy']),expected=new)
        self.ops.nginx_test();self.ops.reload_nginx();self.inventory(self.pins['nginx'])
        need(self.snapshot()==self.data['backup']['static_files'],'RESTORED_BYTES_DRIFT');self.runtime()
        self.data.update(state='ROLLED_BACK',intent=None,rollback_verified={'old_pointer':True,'old_public_bytes':True,'config_hashes':True,'runtime_preserved':True,'real_https_browser':'PENDING'})
        c.atomic(self.receipt,self.data);return self.data


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('apply','rollback','status'));parser.add_argument('--inputs',type=Path,required=True);parser.add_argument('--approval',type=Path)
    args=parser.parse_args();need(os.geteuid()==0 and os.uname().nodename=='iZvt5t8tlrm8oiZ','FIXED_HOST_ROOT_REQUIRED')
    os.umask(0o022)
    for path in (HERE,PINS,HELPER):c.trusted(path)
    tx=Transaction(args.inputs)
    if args.command=='status':print(json.dumps(tx.load_receipt()));return
    # Same lock as r1/r2 prevents concurrent controller operations.
    lock=c.CONTROL/'transaction.lock';c.trusted(lock);fd=os.open(lock,os.O_RDWR|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(RuntimeError('INTERRUPTED_INSPECT_REQUIRED')))
        if args.command=='apply':need(args.approval is not None,'APPROVAL_REQUIRED')
        result=tx.apply(args.approval) if args.command=='apply' else tx.rollback()
        print(json.dumps({'state':result['state'],'receipt':str(tx.receipt),'production_browser':result.get('production_browser','NOT_RUN')}))
    finally:os.close(fd)

if __name__=='__main__':
    try:main()
    except (RuntimeError,OSError,ValueError,KeyError) as error:
        print(json.dumps({'state':'HOLD','reason':str(error)}),file=sys.stderr);sys.exit(2)
