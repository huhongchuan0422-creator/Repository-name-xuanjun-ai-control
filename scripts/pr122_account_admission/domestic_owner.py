"""Reviewed Owner-only enroll/execute/export stages; inert import, no default action."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import pwd
import re
import stat
import subprocess
import types

HOST = 'iZvt5t8tlrm8oiZ'
BASE = '/var/lib/xuanjun-customer-channel'
CONTROL = BASE + '/readonly-bootstrap-20261017'
HELPER = BASE + '/readonly-admission.py'
TRUST = BASE + '/READONLY_ADMISSION_TRUST.json'
RECEIPT = BASE + '/readonly-admission-20261017'
INPUT = '/root/pr122-readonly-admission-inputs'
INTENT = CONTROL + '/OWNER_EXECUTE_INTENT.json'
COMMAND = ('/usr/bin/sudo', '-n', '-u', 'githubrunner', '/usr/bin/sudo', '-n',
           '/usr/local/libexec/xuanjun-customer-channel', 'inspect-account-once')


def need(ok, reason):
    if not ok: raise ValueError(reason)


def strict_json(raw):
    def pairs(items):
        out = {}
        for k,v in items:
            need(k not in out, 'DUPLICATE_KEY');out[k]=v
        return out
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('JSON_CONSTANT')))


def owner():
    need(os.getuid() == os.geteuid() == 0 and os.uname().nodename == HOST and
         os.environ.get('SUDO_UID') != '1002', 'OWNER_ROOT_REQUIRED')


def read_fixed(path, mode):
    parent = os.path.dirname(path)
    while True:
        s=os.lstat(parent)
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022, 'UNSAFE_PARENT')
        if parent == '/': break
        parent=os.path.dirname(parent)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        a=os.fstat(fd)
        need(stat.S_ISREG(a.st_mode) and a.st_uid == 0 and a.st_nlink == 1 and
             stat.S_IMODE(a.st_mode) == mode and a.st_size <= 2000000, 'UNSAFE_FILE')
        with os.fdopen(fd,'rb',closefd=False) as stream: raw=stream.read(2000001)
        b=os.fstat(fd);c=os.lstat(path)
        keys=('st_dev','st_ino','st_uid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        need(len(raw)<=2000000 and all(getattr(a,k)==getattr(b,k)==getattr(c,k) for k in keys),'FILE_DRIFT')
        return raw
    finally:os.close(fd)


def load_helper():
    owner()
    plan=strict_json(read_fixed(CONTROL+'/plan.json',0o400))
    manifest=plan['manifest']
    need(manifest['schema']==1 and manifest['scope']=='DOMESTIC_READONLY_BOOTSTRAP_20261017','MANIFEST_SCOPE')
    staged=strict_json(read_fixed(INPUT+'/domestic-bootstrap-manifest.json',0o400))
    need(staged==manifest,'STAGED_MANIFEST_DRIFT')
    owner_raw=read_fixed(INPUT+'/domestic_owner.py',0o400)
    need(manifest['files']['domestic_owner.py']=={'sha256':hashlib.sha256(owner_raw).hexdigest(),'size':len(owner_raw)},'OWNER_MANIFEST_HASH')
    raw=read_fixed(HELPER,0o400)
    need(manifest['files']['domestic-readonly-helper.py']=={'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)},'HELPER_MANIFEST_HASH')
    module=types.ModuleType('fixed_installed_domestic_helper')
    exec(compile(raw,HELPER,'exec'),module.__dict__)
    need(module.HOST==HOST and module.BASE==BASE and module.HELPER==HELPER and module.TRUST==TRUST and module.RECEIPT==RECEIPT,'FIXED_HELPER_SCOPE')
    bootstrap_raw=read_fixed(INPUT+'/domestic_bootstrap.py',0o400)
    need(manifest['files']['domestic_bootstrap.py']=={'sha256':hashlib.sha256(bootstrap_raw).hexdigest(),'size':len(bootstrap_raw)},'BOOTSTRAP_MANIFEST_HASH')
    bootstrap=types.ModuleType('fixed_staged_domestic_bootstrap')
    bootstrap.__file__=INPUT+'/domestic_bootstrap.py'
    exec(compile(bootstrap_raw,bootstrap.__file__,'exec'),bootstrap.__dict__)
    need(bootstrap.HOST==HOST and str(bootstrap.BASE)==BASE,'BOOTSTRAP_SCOPE')
    expected_plan_raw=read_fixed(CONTROL+'/plan.json',0o400)
    need(strict_json(expected_plan_raw)==plan,'PLAN_DRIFT')
    def owner_check_baseline():
        owner()
        need(read_fixed(CONTROL+'/plan.json',0o400)==expected_plan_raw,'PLAN_DRIFT')
        need(bootstrap.baseline()==plan['baseline'],'OWNER_BASELINE_DRIFT')
    module._owner_check_baseline=owner_check_baseline
    return module


@contextlib.contextmanager
def locks(paths):
    handles=[]
    try:
        for path,mode in paths:
            read_fixed(path,mode)
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW);handles.append(fd)
            a=os.fstat(fd)
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            b=os.lstat(path)
            need((a.st_dev,a.st_ino)==(b.st_dev,b.st_ino),'LOCK_DRIFT')
        yield
    finally:
        for fd in reversed(handles):os.close(fd)


def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def create_fixed(path,value,mode):
    need(path in (TRUST,INTENT),'FIXED_WRITE_PATH')
    raw=(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:
        os.fchmod(stream.fileno(),mode);stream.write(raw);stream.flush();os.fsync(stream.fileno())
    sync(os.path.dirname(path))


def absent(path):
    need(not os.path.lexists(path),'PREEXISTING_STATE_NO_RETRY')


def pin_from_comment(h,cid,body_sha,custody_sha):
    need(type(cid) is int and cid>0,'COMMENT_ID')
    for value in (body_sha,custody_sha):need(type(value) is str and re.fullmatch('[0-9a-f]{64}',value),'EXTERNAL_HASH')
    comment=h.fetch_comment(cid)
    body=comment.get('body')
    need(type(body) is str and hashlib.sha256(body.encode()).hexdigest()==body_sha and body.startswith(h.PREFIX),'EXTERNAL_BODY_PIN')
    permit=h.strict_json(body[len(h.PREFIX):])
    need(type(permit) is dict and set(permit)==h.PERMIT_FIELDS,'PERMIT_SCHEMA')
    pin={k:permit[k] for k in h.PIN_FIELDS-{'comment_id','body_sha256'}}
    pin.update(comment_id=cid,body_sha256=body_sha)
    need(pin['custody_evidence_sha256']==custody_sha,'EXTERNAL_CUSTODY_PIN')
    h.validate_pin(pin,h.now());h.validate_comment(pin,comment);h.check_files(pin)
    return pin


def enroll(cid,body_sha,custody_sha):
    h=load_helper()
    with locks(((BASE+'/.upgrade-lock',0o600),(BASE+'/channel.py',0o444))):
        h._owner_check_baseline()
        absent(TRUST);absent(RECEIPT);absent(INTENT)
        pin=pin_from_comment(h,cid,body_sha,custody_sha)
        h.validate_comment(pin,h.fetch_comment(cid));h.check_files(pin);h.check_time(pin,h.now())
        create_fixed(TRUST,pin,0o600)
    return {'state':'OWNER_PIN_ENROLLED','comment_id':cid,'probe_executed':False}


def execute():
    h=load_helper()
    with locks(((BASE+'/.upgrade-lock',0o600),)):
        with locks(((BASE+'/channel.py',0o444),)):
            h._owner_check_baseline()
            absent(RECEIPT);absent(INTENT)
            need(pwd.getpwnam('githubrunner').pw_uid == 1002, 'RUNNER_UID_DRIFT')
            pin=h.strict_json(read_fixed(TRUST,0o600));h.validate_pin(pin,h.now())
            h.validate_comment(pin,h.fetch_comment(pin['comment_id']));h.check_files(pin);h.check_time(pin,h.now())
            # Independent one-attempt marker, durable before dispatch. Never cleared.
            create_fixed(INTENT,{'state':'OWNER_DISPATCH_INTENT','comment_id':pin['comment_id'],
                                'nonce':pin['nonce'],'retry_allowed':False},0o400)
        # Release channel lock so fixed helper acquires it once; keep upgrade lock.
        # Outer sudo sets real UID1002. Inner sudo observes caller UID1002 and sets
        # SUDO_UID1002, satisfying existing fixed wrapper/helper contract.
        try:
            result=subprocess.run(COMMAND,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,timeout=180,shell=False,
                                  env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C'})
            need(result.returncode==0 and len(result.stdout)<=2000000 and len(result.stderr)<=65536,'UNKNOWN_DISPATCH_NO_RETRY')
            return export_result()
        except Exception:
            raise ValueError('UNKNOWN_DISPATCH_NO_RETRY') from None


def metadata(value, identity=False):
    if type(value) is not dict:return {'state':'UNKNOWN'}
    out={}
    if value.get('state') in ('ABSENT','PRESENT','UNKNOWN','OBSERVED'):out['state']=value['state']
    for key in ('uid','gid','mode','nlink','dev','ino') + (('size',) if identity else ()):
        if type(value.get(key)) is int and 0<=value[key]<2**64:out[key]=value[key]
    if identity and type(value.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}',value['sha256']):out['sha256']=value['sha256']
    return out


def sanitize_result(value):
    need(type(value) is dict,'RESULT_SCHEMA')
    states={'READONLY_OBSERVED_ACCOUNT_CREATION_HOLD','UNKNOWN_CONSUMED_NO_RETRY'}
    need(value.get('state') in states,'RESULT_STATE')
    out={'state':value['state'],'retry_allowed':False,'creation_authorized':False}
    if value['state']=='UNKNOWN_CONSUMED_NO_RETRY':return out
    need(value.get('hostname')==HOST and value.get('account')=='xuanjun-customer','RESULT_SCOPE')
    out.update(hostname=HOST,account='xuanjun-customer')
    for key in ('absence_snapshot_stable','fixture_preconditions_satisfied'):
        if type(value.get(key)) is bool:out[key]=value[key]
    for key in ('account_absence','group_absence'):
        if value.get(key) in ('ABSENT','PRESENT','UNKNOWN'):out[key]=value[key]
    adm=value.get('admission',{})
    if type(adm) is dict and type(adm.get('comment_id')) is int:out['comment_id']=adm['comment_id']
    out['github_job_identity']='NOT_ATTESTED'
    path_allowlist=('/', '/usr', '/usr/sbin', '/etc', '/usr/sbin/useradd', '/usr/sbin/nologin',
                    '/nonexistent','/home','/home/xuanjun-customer','/var','/var/mail',
                    '/var/mail/xuanjun-customer','/var/spool','/var/spool/mail','/var/spool/mail/xuanjun-customer')
    paths=value.get('paths',{})
    if type(paths) is dict:out['paths']={p:metadata(paths[p]) for p in path_allowlist if p in paths}
    tools=value.get('tools',{})
    if type(tools) is dict:
        out['tools']={}
        for p in ('/usr/sbin/useradd','/usr/sbin/nologin','/usr/bin/passwd','/usr/bin/sudo'):
            row=tools.get(p)
            if type(row) is dict:out['tools'][p]={'metadata':metadata(row.get('metadata')),'identity':metadata(row.get('identity'),True)}
    hooks=value.get('hooks',{})
    if type(hooks) is dict:out['hooks']={p:metadata(hooks[p]) for p in ('/etc/shadow-maint/useradd-pre.d','/etc/shadow-maint/useradd-post.d','/etc/useradd.d') if p in hooks}
    platform=value.get('platform',{})
    if type(platform) is dict:
        out['platform']={}
        for key in ('fixed_useradd_flags_supported','no_account_creation_hooks','no_supplementary_group_defaults','ranges_ordered'):
            if type(platform.get(key)) is bool or platform.get(key)=='UNKNOWN':out['platform'][key]=platform[key]
        for key in ('uid_min','uid_max','gid_min','gid_max'):
            if type(platform.get(key)) is int and 0<platform[key]<2**32 or platform.get(key)=='UNKNOWN':out['platform'][key]=platform[key]
    out['receipt']=metadata(value.get('receipt'))
    out['channel_identity']=metadata(value.get('channel_identity'),True)
    lock=value.get('canonical_lock',{})
    if type(lock) is dict:
        out['canonical_lock']={'metadata':metadata(lock.get('metadata'))}
        for key in ('acquired_at_observation','named_inode_stable'):
            if type(lock.get(key)) is bool:out['canonical_lock'][key]=lock[key]
    package=value.get('target_package_identity',{})
    if type(package) is dict:
        out['target_package_identity']={}
        for key in ('name','version','release','arch','digest_algorithm'):
            if type(package.get(key)) is str and re.fullmatch(r'[A-Za-z0-9_.+~:-]{1,100}',package[key]):out['target_package_identity'][key]=package[key]
        if package.get('state') in ('OBSERVED','UNKNOWN'):out['target_package_identity']['state']=package['state']
        if type(package.get('actual_digest_matches')) is bool:out['target_package_identity']['actual_digest_matches']=package['actual_digest_matches']
        if type(package.get('recorded_sha256')) is str and re.fullmatch('[0-9a-f]{64}',package['recorded_sha256']):out['target_package_identity']['recorded_sha256']=package['recorded_sha256']
    for key,allowed in {'global_writer_exclusion':('UNKNOWN',),'sts_identity':('UNKNOWN',),
                        'registered_trigger':('UNKNOWN',),'password_status':('NOT_QUERIED',),
                        'sudo_privileges':('NOT_QUERIED',),
                        'target_mail_subid_semantics':('UNKNOWN','INFERRED_DOCUMENTED_SYSTEM_ACCOUNT_NO_F_NOT_EXPERIMENTALLY_TESTED')}.items():
        if value.get(key) in allowed:out[key]=value[key]
    # Fixed metadata only; no arbitrary paths, records, raw stderr or stdout.
    return out


def export_result():
    owner()
    return sanitize_result(strict_json(read_fixed(RECEIPT+'/result.json',0o600)))


def main():
    parser=argparse.ArgumentParser(description='Owner reviewed fixed stages; no automatic execution')
    sub=parser.add_subparsers(dest='stage',required=True)
    enroll_parser=sub.add_parser('enroll')
    enroll_parser.add_argument('--comment-id',required=True,type=int)
    enroll_parser.add_argument('--body-sha256',required=True)
    enroll_parser.add_argument('--custody-sha256',required=True)
    sub.add_parser('execute');sub.add_parser('export')
    args=parser.parse_args()
    if args.stage=='enroll':result=enroll(args.comment_id,args.body_sha256,args.custody_sha256)
    elif args.stage=='execute':result=execute()
    else:result=export_result()
    print(json.dumps(result,sort_keys=True))
    if result.get('state','').startswith('UNKNOWN'):raise SystemExit(1)


if __name__=='__main__':
    try:main()
    except Exception:
        print('{"state":"HOLD_OR_UNKNOWN","retry_allowed":false}')
        raise SystemExit(1)
