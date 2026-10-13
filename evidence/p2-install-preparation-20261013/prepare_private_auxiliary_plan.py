"""Seal auxiliary bootstrap intent and fresh facts; has no apply operation."""
import datetime, grp, hashlib, json, os, re, socket, stat, subprocess, sys
SEALED='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/plan-p2pkg-38394776168-1'
CORE_SHA='2857d55bc90ca6c4aa82495f9c3f9b95a6752c30bd75203dd6a1a9994225bcb9'
BOOT_SHA='dd0e1b98ecd264a008a6629003352fc072c183991d0a59ade2974f3ffb738499'
RELEASE='dbe785330e881224bd16c3554a45a0a38bd8f88cb777ffa16fa35440a881efaf'
def read(path):
    assert os.path.realpath(path)==path
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        info=os.fstat(f.fileno())
        assert stat.S_ISREG(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1
        raw=f.read(1048577);assert len(raw)<=1048576
        end=os.fstat(f.fileno())
        assert (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)==(end.st_dev,end.st_ino,end.st_size,end.st_mtime_ns,end.st_ctime_ns)
    return raw
def sha(raw):return hashlib.sha256(raw).hexdigest()
def checked(path,pin):
    raw=read(path);assert sha(raw)==pin;return json.loads(raw.decode())
def command(args):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10)
    assert p.returncode==0;return p.stdout
def main(run):
    assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ' and re.fullmatch(r'[0-9]+',run)
    info=os.lstat(SEALED);assert stat.S_ISDIR(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700
    core=checked(SEALED+'/protected-core-install-plan.json',CORE_SHA)
    boot=checked(SEALED+'/protected-bootstrap-candidate-receipt.json',BOOT_SHA)
    assert core['artifact']['manifest_sha256']==RELEASE and boot['artifact_id']==11810729039
    callback='/etc/xuanjun-owner-callback/'
    targets={callback+name:(1004,1006,0o600) for name in ('owner-user-id','owner-chat-id','owner-callback-auth','owner-callback-hmac','owner-dashboard-token')}
    targets.update({'/etc/xuanjun-development/github-intake-token':(1003,1003,0o600),'/etc/xuanjun-development/p2-native-binding.json':(0,0,0o644)})
    assert len(boot['files'])==7
    rows=[];seen=set()
    for item in boot['files']:
        target=item['target'];assert target in targets and target not in seen;seen.add(target)
        assert tuple(item[k] for k in ('owner_uid','group_gid','mode'))==targets[target]
        assert item['applied'] is False and item['requires_approved_bootstrap'] is True
        source=item['source'];assert os.path.dirname(source)==SEALED+'/private-bootstrap'
        assert sha(read(source))==item['sha256']
        assert not os.path.lexists(target),'HOLD_EXISTING_AUXILIARY_TARGET'
        parent=os.path.dirname(target)
        if os.path.lexists(parent):
            s=os.lstat(parent);assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022 and os.path.realpath(parent)==parent
        rows.append(dict(item,expected_previous='ABSENT',rollback='REMOVE_ONLY_IF_INSTALLED_HASH_AND_IDENTITY_MATCH'))
    assert seen==set(targets)
    services=[]
    for unit,binding in core['cutover']['legacy_bindings'].items():
        with open(binding['fragment_path'],'rb') as f:assert sha(f.read())==binding['sha256']
        raw=command(['systemctl','show',unit,'--property=Id,ActiveState,SubState,MainPID,ControlGroup']).decode()
        services.append(dict(line.split('=',1) for line in raw.splitlines() if '=' in line))
    try:grp.getgrgid(1007)
    except KeyError:pass
    else:raise ValueError('HOLD_CLIENT_GID_ALREADY_ALLOCATED')
    try:grp.getgrnam('xuanjun-ledger-client')
    except KeyError:pass
    else:raise ValueError('HOLD_CLIENT_GROUP_ALREADY_PRESENT')
    refs=core['tls']['references'];assert len(refs)==2
    for ref in refs:assert sha(read(ref['path']))==ref['sha256']
    cert,key=refs[0]['path'],refs[1]['path']
    hostname=command(['openssl','x509','-in',cert,'-noout','-checkhost','uk.wenwenwenyiyiyi.work']).decode()
    assert 'does match certificate' in hostname and 'does NOT match' not in hostname
    command(['openssl','x509','-in',cert,'-noout','-checkend','86400'])
    assert command(['openssl','x509','-in',cert,'-noout','-pubkey']).strip()==command(['openssl','pkey','-in',key,'-pubout']).strip()
    result={'schema':1,'state':'AUXILIARY_INTENT_SEALED_NOT_APPLIED','core_plan_sha256':CORE_SHA,'bootstrap_receipt_sha256':BOOT_SHA,
      'release_sha256':RELEASE,'transaction_id':core['transaction_id'],'files':rows,'observed_at_utc':datetime.datetime.utcnow().isoformat()+'Z',
      'legacy_services':services,'gid1007_free_observed_unreserved':True,'tls_candidate_host_validity_and_keypair_verified':True,
      'apply_preconditions':['INDEPENDENT_RELEASE_GRANTED','OWNER_INSTALL_AUTHORIZED','FRESH_IDENTITIES_AND_TARGETS_RECHECKED','LEGACY_WRITERS_QUIESCED_AND_EFFECTS_RECONCILED','PREREQUISITES_APPLIED'],
      'apply_hook':'NOT_IMPLEMENTED','rollback_hook':'NOT_IMPLEMENTED','mirror_and_github_auth_final_target':'NOT_CONNECTED',
      'real_relay_outbox_ack':'NOT_EXECUTED','installed_https_and_renewal':'NOT_VERIFIED',
      'production_changes':False,'writer_admission':False,'install':False,'model_calls':0}
    raw=(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode()
    path=SEALED+'/protected-auxiliary-intent-'+run+'.json'
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    print(json.dumps({'state':result['state'],'file_count':7,'auxiliary_intent_sha256':sha(raw),'intent_path':path,
      'legacy_services':services,'tls_candidate_verified':True,'gid1007_unreserved':True,'install':False,'model_calls':0},sort_keys=True))
if __name__=='__main__':main(sys.argv[1])
