"""Fixed read-only caller. Import is inert; no CLI or arbitrary path inputs."""
import hashlib
import json
import os
import stat
import datetime
import re

APPROVED_SHA = '885b850864465a554d99adbdfb4b4d4e33abf5dc52e7dcf84f27597c247c0818'
TOOLS = ('/usr/sbin/useradd', '/usr/sbin/nologin', '/usr/bin/passwd', '/usr/bin/sudo')
HOOKS = ('/etc/shadow-maint/useradd-pre.d', '/etc/shadow-maint/useradd-post.d', '/etc/useradd.d')
BOOLS = ('fixed_useradd_flags_supported', 'no_account_creation_hooks', 'no_supplementary_group_defaults')
RANGES = ('uid_min', 'uid_max', 'gid_min', 'gid_max')

def load_approved(raw):
    if hashlib.sha256(raw).hexdigest() != APPROVED_SHA:
        raise ValueError('APPROVED_HASH')
    ns = {'__name__': 'approved_account_payload_readonly'}
    exec(compile(raw, 'approved-account-payload', 'exec'), ns)
    return ns

def meta(ns, path):
    # The only callers supply fixed constants or approved fixture paths.
    try:
        ns['secure'](os.path.dirname(path) or '/', directory=True)
        s = os.lstat(path)
        return dict(state='PRESENT', uid=s.st_uid, gid=s.st_gid,
                    mode=s.st_mode, nlink=s.st_nlink, dev=s.st_dev, ino=s.st_ino)
    except FileNotFoundError:
        # Missing parent cannot prove child absence. Revalidate parent.
        try: ns['secure'](os.path.dirname(path) or '/', directory=True)
        except Exception: return {'state': 'UNKNOWN'}
        return {'state': 'ABSENT'}
    except Exception:
        return {'state': 'UNKNOWN'}

def identity(ns, path):
    try:
        if path in ('/usr/bin/passwd', '/usr/bin/sudo'):
            ns['secure_postcheck_tool'](path)
        else:
            ns['secure'](path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as f:
            before = os.fstat(f.fileno())
            named = os.lstat(path)
            if (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino):
                raise ValueError('INODE')
            if not stat.S_ISREG(before.st_mode) or before.st_size > 16777216:
                raise ValueError('SIZE')
            h = hashlib.sha256()
            total = 0
            while True:
                block = f.read(65536)
                if not block: break
                total += len(block)
                if total > 16777216: raise ValueError('SIZE')
                h.update(block)
            after = os.fstat(f.fileno())
            keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            if any(getattr(before,k) != getattr(after,k) for k in keys):
                raise ValueError('DRIFT')
            named = os.lstat(path)
            if any(getattr(after,k) != getattr(named,k) for k in keys):
                raise ValueError('PATH_DRIFT')
        return dict(state='OBSERVED', sha256=h.hexdigest(), size=total,
                    dev=before.st_dev, ino=before.st_ino)
    except Exception: return {'state': 'UNKNOWN'}

def package_identity(ops, binary):
    # Fixed RPM reads. Capture bounded arrays, export only the useradd entry.
    try:
        fmt = '%{NAME}\n%{VERSION}\n%{RELEASE}\n%{ARCH}\n%{FILEDIGESTALGO}\n'
        r = ops.command(('/usr/bin/rpm','-qf','--qf',fmt,'/usr/sbin/useradd'))
        if r.returncode != 0: raise ValueError('RPM')
        fields = r.stdout.decode('ascii').splitlines()
        if len(fields)!=5 or not all(re.fullmatch(r'[A-Za-z0-9_.+~:-]{1,100}',x) for x in fields):
            raise ValueError('SCHEMA')
        if fields[4]!='8': raise ValueError('DIGEST_ALGORITHM')
        r = ops.command(('/usr/bin/rpm','-qf','--qf','[%{FILENAMES}\t%{FILEDIGESTS}\n]','/usr/sbin/useradd'))
        if r.returncode != 0: raise ValueError('RPM')
        matches=[line.split('\t')[1] for line in r.stdout.decode('utf-8').splitlines() if line.startswith('/usr/sbin/useradd\t') and len(line.split('\t'))==2]
        if len(matches)!=1 or re.fullmatch('[0-9a-f]{64}',matches[0]) is None: raise ValueError('RECORD')
        return dict(state='OBSERVED', name=fields[0], version=fields[1], release=fields[2], arch=fields[3],
                    digest_algorithm='SHA256', recorded_sha256=matches[0],
                    actual_digest_matches=binary.get('state')=='OBSERVED' and binary.get('sha256')==matches[0])
    except Exception: return {'state':'UNKNOWN'}

def run(ns):
    # OS verifies fixed host plus real/effective root. Never invoke payload main.
    ops = ns['OS']()
    result = dict(schema=1, state='READONLY_OBSERVED_ACCOUNT_CREATION_HOLD',
                  hostname=ns['HOST'], account=ns['ACCOUNT'], uid=ops.uid, euid=ops.euid,
                  approved_payload_sha256=APPROVED_SHA, mutations=0,
                  creation_authorized=False, global_writer_exclusion='UNKNOWN',
                  target_package_identity={'state':'UNKNOWN'}, target_mail_subid_semantics='UNKNOWN',
                  password_status='NOT_QUERIED', sudo_privileges='NOT_QUERIED',
                  sts_identity='UNKNOWN', registered_trigger='UNKNOWN')
    with ops.lock_existing(ns['ORIGINAL_LOCK']):
        result['observed_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        lock_before = meta(ns, ns['ORIGINAL_LOCK'])
        fixture = ns['collect_fixture'](ops)
        result['account_absence'] = fixture['account']
        result['group_absence'] = fixture['group']
        result['paths'] = fixture['paths']  # Fixed metadata only, never NSS records.
        result['fixture_preconditions_satisfied'] = not ns['plan'](fixture)['precondition_failures']
        result['receipt'] = meta(ns, ns['ACCOUNT_RECEIPT'])  # Existence only; no read/mkdir.
        result['tools'] = {p: {'metadata': meta(ns,p), 'identity': identity(ns,p)} for p in TOOLS}
        result['hooks'] = {p: meta(ns,p) for p in HOOKS}
        try:
            platform = ops.platform_preconditions()  # Only useradd --help plus public defaults.
            result['platform'] = {k: platform[k] if type(platform.get(k)) is bool else 'UNKNOWN' for k in BOOLS}
            result['platform'].update({k: platform[k] if type(platform.get(k)) is int and platform[k]>0 else 'UNKNOWN' for k in RANGES})
            result['platform']['ranges_ordered'] = all(type(platform.get(k)) is int and platform[k]>0 for k in RANGES) and platform['uid_min']<=platform['uid_max'] and platform['gid_min']<=platform['gid_max']
        except Exception:
            result['platform'] = {k:'UNKNOWN' for k in BOOLS + RANGES + ('ranges_ordered',)}
        result['target_package_identity'] = package_identity(ops,result['tools']['/usr/sbin/useradd']['identity'])
        package = result['target_package_identity']
        if package.get('name')=='shadow-utils' and package.get('actual_digest_matches') is True and result['platform']['fixed_useradd_flags_supported'] is True:
            result['target_mail_subid_semantics'] = 'INFERRED_DOCUMENTED_SYSTEM_ACCOUNT_NO_F_NOT_EXPERIMENTALLY_TESTED'
        result['channel_identity'] = identity(ns, ns['ORIGINAL_LOCK'])
        lock_after = meta(ns, ns['ORIGINAL_LOCK'])
        result['canonical_lock'] = {'acquired_at_observation':True, 'metadata':lock_after,
                                    'named_inode_stable': lock_before == lock_after and lock_after.get('state')=='PRESENT'}
        # Repeat absence under the same lock after bounded observations.
        second = ns['collect_fixture'](ops)
        result['absence_snapshot_stable'] = fixture == second and result['receipt'] == meta(ns,ns['ACCOUNT_RECEIPT'])
    return result
