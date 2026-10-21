"""Protected target operator commands and isolated encrypted backup/restore.
Never invoked by HTTP. Does not install/reload production configuration.
"""
import argparse
import base64
import hashlib
import io
import json
import os
import sqlite3
import tarfile
import tempfile
from pathlib import Path
from scripts.pr122_customer_core import Center,Denied,canonical,digest,private_path,secure_write
from scripts.pr122_customer_providers import Providers,ClamScanner,SecretRefMetadata,load_config,drain_mail,drain_message
from scripts.pr122_customer_profile import FULL,LOGIN_ONLY,profile,validate_pair

HOST='iZvt5t8tlrm8oiZ'
ROOT=Path('/var/lib/xuanjun-customer-center')
CONFIG=Path('/etc/xuanjun-customer-center/config.json')

RUNTIME_CONTEXT_DEPTH = {'message_evidence_context':2, 'privacy_policy_context':1, 'privacy_processing_context':3}

def validate_runtime_contexts(config, runtime):
    """Bind optional noncredential context maps to the protected operator input."""
    from scripts.pr122_customer_core import valid_id
    from scripts.pr122_customer_evidence import CONTEXT_FIELDS
    from scripts.pr122_customer_privacy import POLICY_FIELDS
    fields={'message_evidence_context':set(CONTEXT_FIELDS), 'privacy_policy_context':set(POLICY_FIELDS),
            'privacy_processing_context':{'requester_id','project_id','tenant_id','customer_id','request_id','revision','status','status_ref','actor_ref','occurred_at','outcome_ref'}}
    required={'keys','active_key','providers'}
    if type(runtime) is not dict or not required <= set(runtime) or set(runtime)-required-set(RUNTIME_CONTEXT_DEPTH)-{'deployment_profile','identity_authorization'}:
        raise Denied('RUNTIME_CREDENTIAL_MINIMUM')
    selected=validate_pair(config,runtime)
    from scripts.pr122_customer_identity import boundary_from_config
    if 'identity_authorization' in runtime or 'identity_authorization' in config:
        if selected!=FULL:raise Denied('LOGIN_ONLY_IDENTITY_SCOPE')
        if canonical(config.get('identity_authorization'))!=canonical(runtime.get('identity_authorization')):raise Denied('IDENTITY_RUNTIME_BINDING')
        boundary_from_config(config);boundary_from_config(runtime)
    if selected==LOGIN_ONLY and canonical(config['providers'])!=canonical(runtime['providers']):
        raise Denied('RUNTIME_PROVIDER_BINDING')
    def mapping(value, depth, allowed, integer_fields):
        if type(value) is not dict:raise Denied('RUNTIME_CONTEXT_MAPPING')
        if depth:
            for key,child in value.items():
                if not valid_id(key):raise Denied('RUNTIME_CONTEXT_ID')
                mapping(child,depth-1,allowed,integer_fields)
        elif set(value)-allowed or any(type(v) not in ((int,) if k in integer_fields else (str,type(None))) for k,v in value.items()):
            raise Denied('RUNTIME_CONTEXT_FIELDS')
    for key,depth in RUNTIME_CONTEXT_DEPTH.items():
        protected=config.get(key,{})
        supplied=runtime.get(key,{})
        integer_fields={'revision','occurred_at'} if key=='privacy_processing_context' else set()
        mapping(protected,depth,fields[key],integer_fields);mapping(supplied,depth,fields[key],integer_fields)
        if canonical(protected)!=canonical(supplied):raise Denied('RUNTIME_CONTEXT_BINDING')
    return True


def factory(config):
    selected=profile(config)
    validate_pair(config,config)
    scan=Path('/run/xuanjun-customer-scan')
    if selected==FULL and scan.exists() and scan.stat().st_uid==os.geteuid():os.chmod(scan,0o700)
    keys={k:base64.b64decode(v,validate=True) for k,v in config['keys'].items()}
    return Center(ROOT,keys,config['active_key'],mail_ready=bool(config.get('providers',{}).get('smtp')),scanner=ClamScanner() if selected==FULL else None,secretref=SecretRefMetadata(config['providers']['secretref']['socket'],config['providers']['secretref']['peer_uid']) if selected==FULL and config.get('providers',{}).get('secretref') else None,evidence_context=(lambda uid,pid:config.get('message_evidence_context',{}).get(pid,{}).get(uid,{})) if selected==FULL else None,privacy_policy_context=(lambda uid,pid:config.get('privacy_policy_context',{}).get(pid,{})) if selected==FULL else None,privacy_processing_context=(lambda uid,pid,rid:config.get('privacy_processing_context',{}).get(pid,{}).get(uid,{}).get(rid,{})) if selected==FULL else None)

def backup(center,output,backup_key,key_ref):
    if type(backup_key) is not bytes or len(backup_key)!=32 or not key_ref:raise Denied('SEPARATE_BACKUP_KEY_REQUIRED')
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    center.check_integrity(); blobs={}
    # One reserved writer transaction prevents metadata/object divergence. Separate
    # read connection sees committed snapshot, objects are immutable and encrypted.
    with center.tx():
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'copy.sqlite'; src=sqlite3.connect(center.root/'center.sqlite'); dst=sqlite3.connect(path)
            try:src.backup(dst)
            finally:src.close();dst.close()
            blobs['center.sqlite']=path.read_bytes()
        for p in sorted(center.objects.iterdir()):
            private_path(p)
            if not p.is_file() or not p.name.startswith('o_'):raise Denied('OBJECT_STORE_DRIFT')
            blobs['objects/'+p.name]=p.read_bytes()
        manifest={'schema':1,'key_ref':key_ref,'active_key':center.key_id,'index_key':center.index_key,'audit_head':center.check_integrity()['audit_head'],'files':[{'path':p,'sha256':digest(b),'size':len(b)} for p,b in blobs.items()]}
        blobs['BACKUP_MANIFEST.json']=canonical(manifest)
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w:gz') as t:
            for p,b in blobs.items():
                info=tarfile.TarInfo(p);info.size=len(b);info.mode=0o600;info.mtime=0;t.addfile(info,io.BytesIO(b))
        nonce=os.urandom(12);encrypted=nonce+AESGCM(backup_key).encrypt(nonce,stream.getvalue(),b'PR122_CUSTOMER_BACKUP_V1')
        secure_write(output,encrypted);center.audit('','operator','BACKUP_CREATED',digest(encrypted))
    return {'sha256':digest(encrypted),'key_ref':key_ref,'files':len(manifest['files']),'contains_keys':False}

def restore_key_material(config):
    """Decode only the key material already required by Center/backup restore."""
    keys=config.get('keys')
    active_key=config.get('active_key')
    if type(keys) is not dict or not keys or type(active_key) is not str:
        raise Denied('KMS_KEYS_REQUIRED')
    decoded={}
    from scripts.pr122_customer_core import identifier
    for key,value in keys.items():
        try: name=identifier(key); raw=base64.b64decode(value,validate=True)
        except (TypeError,ValueError,base64.binascii.Error):
            raise Denied('KMS_KEYS_REQUIRED')
        if len(raw)!=32:raise Denied('KMS_KEYS_REQUIRED')
        decoded[name]=raw
    if active_key not in decoded:raise Denied('KMS_KEYS_REQUIRED')
    try: backup_key=base64.b64decode(config.get('backup_key'),validate=True)
    except (TypeError,ValueError,base64.binascii.Error):
        raise Denied('SEPARATE_BACKUP_KEY_REQUIRED')
    if len(backup_key)!=32:raise Denied('SEPARATE_BACKUP_KEY_REQUIRED')
    return decoded,active_key,backup_key

def restore(backup_file,target,backup_key,keys,active_key):
    """Restore into NEW isolated directory, never live replacement. Every old
    session/grant/link is invalidated and maintenance remains on until a fresh
    current canonical authority snapshot is imported by protected operator.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    target=private_path(target)
    normalized=Path(os.path.abspath(os.path.normpath(os.fspath(target))))
    live=Path(os.path.abspath(os.path.normpath(os.fspath(ROOT))))
    if normalized==live:raise Denied('RESTORE_LIVE_ROOT_FORBIDDEN')
    if target.exists():raise Denied('RESTORE_NEW_DIRECTORY_ONLY')
    raw=private_path(backup_file).read_bytes()
    if len(raw)>200_000_000:raise Denied('BACKUP_SIZE')
    plain=AESGCM(backup_key).decrypt(raw[:12],raw[12:],b'PR122_CUSTOMER_BACKUP_V1')
    blobs={};total=0
    with tarfile.open(fileobj=io.BytesIO(plain),mode='r:gz') as t:
        for m in t:
            if not m.isfile() or m.name in blobs or m.name.startswith('/') or '..' in Path(m.name).parts or m.size>100_000_000:raise Denied('BACKUP_MEMBER')
            if m.name not in ('center.sqlite','BACKUP_MANIFEST.json') and not __import__('re').fullmatch(r'objects/o_[a-f0-9]{32}',m.name):raise Denied('BACKUP_PATH')
            total+=m.size
            if total>200_000_000 or len(blobs)>10000:raise Denied('BACKUP_LIMIT')
            blobs[m.name]=t.extractfile(m).read()
    manifest=json.loads(blobs['BACKUP_MANIFEST.json'])
    if len(blobs)!=len(manifest['files'])+1 or len({x['path'] for x in manifest['files']})!=len(manifest['files']):raise Denied('BACKUP_MANIFEST')
    for x in manifest['files']:
        if len(blobs[x['path']])!=x['size'] or digest(blobs[x['path']])!=x['sha256']:raise Denied('BACKUP_HASH')
    target.mkdir(mode=0o700)
    (target/'objects').mkdir(mode=0o700)
    for name,b in blobs.items():
        if name!='BACKUP_MANIFEST.json':secure_write(target/name,b)
    c=Center(target,keys,active_key)
    try:
        check=c.check_integrity()
        if check['audit_head']!=manifest['audit_head']:raise Denied('RESTORE_AUDIT')
        with c.tx():
            c.db.execute("UPDATE settings SET v='1' WHERE k='maintenance'")
            c.db.execute('UPDATE accounts SET epoch=epoch+1');c.db.execute('DELETE FROM sessions');c.db.execute('UPDATE members SET active=0');c.db.execute('UPDATE links SET active=0');c.db.execute('UPDATE challenges SET used=1')
            for message in c.db.execute("SELECT id,project FROM messages WHERE status='PENDING' ORDER BY created,id").fetchall():
                c.db.execute("UPDATE messages SET status='UNKNOWN' WHERE id=?",(message['id'],))
                c.audit(message['project'],'operator','OUTBOUND_RESTORE_UNKNOWN',message['id'])
            c.db.execute("UPDATE outbox SET status='UNKNOWN' WHERE status='PENDING'")
            c.audit('','operator','ISOLATED_RESTORE',digest(raw))
        return {**check,'restored':'ISOLATED_MAINTENANCE','fresh_authority_required':True,'old_sessions_invalid':True,'old_grants_invalid':True}
    finally:c.db.close()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=('serve','worker','publisher','import-authority','import-identity-mapping','import-change-authority','issue-preview-delivery','integrity','backup','restore-isolated'));ap.add_argument('--input');ap.add_argument('--output');args=ap.parse_args()
    if os.geteuid()!=0 and args.action not in ('serve','worker'):raise SystemExit('HOLD: PROTECTED_OPERATOR_REQUIRED')
    if os.uname().nodename!=HOST:raise SystemExit('HOLD: WRONG_HOST')
    config=None
    if args.action not in ('serve','worker'):
        # Read the protected scope before publisher import, input-file reads,
        # privilege changes, factory construction or any database access.
        config=load_config(CONFIG)
        selected=profile(config);validate_pair(config,config)
        if selected==LOGIN_ONLY and args.action not in ('integrity','backup','restore-isolated'):
            raise Denied('LOGIN_ONLY_OPERATOR_SCOPE')
    if args.action=='publisher':
        from scripts.pr122_customer_publication_worker import main_worker
        print(json.dumps(main_worker(),sort_keys=True));return
    delivery_input=None
    mapping_input=None;mapping_evidence={}
    if args.action=='import-identity-mapping':
        from scripts.pr122_customer_identity import load_operator_mapping
        mapping_input,mapping_evidence=load_operator_mapping(args.input)
    if args.action=='issue-preview-delivery':
        path=private_path(args.input)
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as stream:
            import stat
            st=os.fstat(stream.fileno())
            if st.st_uid!=0 or not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or st.st_mode&0o077 or st.st_size>1000000:raise Denied('ROOT_PRIVATE_DELIVERY_INPUT_REQUIRED')
            delivery_input=json.loads(stream.read(1000001))
    if args.action in ('serve','worker'):

        if os.geteuid()==0:raise SystemExit('HOLD: NON_ROOT_RUNTIME_REQUIRED')
        cred=Path(os.environ.get('CREDENTIALS_DIRECTORY','/nonexistent'))/'runtime.json'
        private_path(cred)
        st=cred.stat()
        if st.st_uid!=os.geteuid() or st.st_mode&0o077:raise SystemExit('HOLD: SYSTEMD_CREDENTIAL_REQUIRED')
        config=json.loads(cred.read_bytes())
        validate_runtime_contexts(config,config)
    else:
        # Protected root admission, then perform data I/O as the one runtime
        # identity so WAL/object ownership cannot drift after operator backup.
        import pwd
        account=pwd.getpwnam('xuanjun-customer')
        if account.pw_uid<=0:raise SystemExit('HOLD: NON_ROOT_ACCOUNT_REQUIRED')
        os.umask(0o077);os.setgroups([]);os.setgid(account.pw_gid);os.setuid(account.pw_uid)
    if args.action=='restore-isolated':
        # Reuse the original isolated restore path without constructing the live Center.
        # Root/host/profile checks and privilege drop above remain mandatory.
        keys,active_key,backup_key=restore_key_material(config)
        result=restore(args.input,args.output,backup_key,keys,active_key)
        print(json.dumps(result,ensure_ascii=False))
        return
    c=factory(config)
    selected=profile(config)
    try:
        if args.action=='serve':
            from scripts.pr122_customer_http import serve
            from scripts.pr122_customer_identity import boundary_from_config
            c.db.close();serve(lambda:factory(config),Providers(config.get('providers',{})),Path(__file__).resolve().parent.parent/'deploy/pr122-customer-center/ui',deployment_profile=selected,identity_boundary=boundary_from_config(config));return
        if args.action=='worker':
            p=Providers(config.get('providers',{}));result={'mail':drain_mail(c,p,'https://wenwenwenyiyiyi.work')}
            if selected==FULL:result['message']=drain_message(c,p)
        elif args.action=='import-authority':
            result=c.import_authority(json.loads(private_path(args.input).read_bytes()),base64.b64decode(config['authority_verify_key'],validate=True))
        elif args.action=='import-identity-mapping':
            from scripts.pr122_customer_identity import import_mapping
            result=import_mapping(c,mapping_input,base64.b64decode(config['authority_verify_key'],validate=True),config.get('identity_mapping_confirmers'),mapping_evidence.__getitem__)
            # Resume is a separate reviewed operator decision after restore; CLI
            # import alone intentionally does not clear maintenance.
        elif args.action=='import-change-authority':
            from scripts.pr122_customer_change_authority import import_snapshot
            result=import_snapshot(c,json.loads(private_path(args.input).read_bytes()),base64.b64decode(config['authority_verify_key'],validate=True))
        elif args.action=='issue-preview-delivery':
            from scripts.pr122_customer_delivery_source import issue
            incoming=delivery_input
            if set(incoming)!={'project','case','serve_id','report'}:raise Denied('DELIVERY_INPUT_FIELDS')
            result=issue(c,incoming['project'],incoming['case'],incoming['serve_id'],incoming['report'],config['preview_test_trust'],base64.b64decode(config['authority_verify_key'],validate=True))
        elif args.action=='integrity':result=c.check_integrity()
        elif args.action=='backup':result=backup(c,args.output,base64.b64decode(config['backup_key'],validate=True),config['backup_key_ref'])
        else:result=restore(args.input,args.output,base64.b64decode(config['backup_key'],validate=True),c.keys,c.key_id)
        print(json.dumps(result,ensure_ascii=False))
    finally:c.db.close()
if __name__=='__main__':main()
