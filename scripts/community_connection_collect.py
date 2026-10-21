"""Community fixed read-only collectors for FUTURE public-worker enrollment.

No CLI, queue, approval, application import, DB connection or initialization.
The original worker must authenticate/enroll/pin the action and protected plan.
Passing a plan is input validation, never proof of authorization.
"""
import hashlib
import json
import os
import stat
from pathlib import PurePosixPath
from scripts.community_owner_readonly_supplement_20261021 import read_absolute
from scripts.community_preview_readiness import check

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
PROJECT = 'community-payment'
STORES = frozenset(('center','orders','merchants','ads','refunds','quotes','saas_orders','modules'))
MAX_CONFIG = 65536
MAX_REPORT = 65536


def require(value, code):
    if not value:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def absolute(value):
    require(type(value) is str and len(value)<=2048 and value.startswith('/')
            and not value.startswith('//') and '\x00' not in value
            and str(PurePosixPath(value))==value and '..' not in value.split('/')
            and value!='/', 'EXACT_ENROLLED_PATH_REQUIRED')
    return value


def metadata(path, owner):
    """Stat only; never read the contents of a business database."""
    parts=absolute(path).split('/')[1:]
    directory=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
            os.close(directory);directory=child
            parent=os.fstat(directory)
            require(parent.st_uid in (0,owner) and not parent.st_mode&0o022,'UNSAFE_ENROLLED_PARENT')
        parent=os.fstat(directory)
        require(parent.st_uid==owner and not parent.st_mode&0o077,'PRIVATE_ENROLLED_PARENT_REQUIRED')
        fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        try:
            item=os.fstat(fd)
            require(stat.S_ISREG(item.st_mode) and item.st_uid==owner
                    and not item.st_mode&0o077 and item.st_nlink==1,'PRIVATE_ENROLLED_FILE_REQUIRED')
            return dict(dev=item.st_dev,ino=item.st_ino,uid=item.st_uid,
                mode=stat.S_IMODE(item.st_mode),bytes=item.st_size,
                mtime_ns=item.st_mtime_ns,ctime_ns=item.st_ctime_ns)
        finally:os.close(fd)
    finally:os.close(directory)


def health():
    """Fixed public target only, using the original bounded health reader."""
    require(os.uname().nodename.split('.')[0]==HOST,'UK_HOST_REQUIRED')
    return check(profile='uk-path-candidate')


def runtime_metadata(plan):
    """Read one approved config and eight exact file metadata references.

    Roots/UID/SHA/scene digest must come from the protected project enrollment,
    not tool params. No source/receiver roots are discovered or guessed here.
    """
    require(os.uname().nodename.split('.')[0]==HOST,'UK_HOST_REQUIRED')
    fields={'schema','project','config_path','config_sha256','scene_sha256','service_uid','stores'}
    require(type(plan) is dict and set(plan)==fields and type(plan['schema']) is int
            and plan['schema']==1 and plan['project']==PROJECT,'EXACT_COMMUNITY_PLAN_REQUIRED')
    require(type(plan['service_uid']) is int and plan['service_uid']>=0,'ENROLLED_SERVICE_UID_REQUIRED')
    for key in ('config_sha256','scene_sha256'):
        value=plan[key]
        require(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value),'EXACT_ENROLLED_SHA_REQUIRED')
    require(type(plan['stores']) is dict and set(plan['stores'])==STORES,'EIGHT_ENROLLED_STORES_REQUIRED')
    paths=[absolute(plan['config_path'])]+[absolute(plan['stores'][k]) for k in sorted(STORES)]
    owner=plan['service_uid']
    before=metadata(paths[0],owner)
    require(0<before['bytes']<=MAX_CONFIG,'CONFIG_READ_BUDGET')
    raw=read_absolute(paths[0],MAX_CONFIG)
    require(metadata(paths[0],owner)==before,'CONFIG_CHANGED_DURING_READ')
    require(hashlib.sha256(raw).hexdigest()==plan['config_sha256'],'ENROLLED_CONFIG_SHA_MISMATCH')
    def unique(pairs):
        result={}
        for key,value in pairs:
            require(key not in result,'DUPLICATE_CONFIG_FIELD')
            result[key]=value
        return result
    def finite(_):raise ValueError('NONFINITE_CONFIG')
    try:config=json.loads(raw.decode('utf-8'),object_pairs_hook=unique,parse_constant=finite)
    except (ValueError,UnicodeError):raise ValueError('INVALID_ENROLLED_CONFIG') from None
    require(type(config) is dict and set(config)=={'version','appid','https_origin','scenes','stores'}
            and type(config['version']) is int and config['version']==1,'ORIGINAL_HOST_CONFIG_FIELDS')
    require(config['stores']==plan['stores'],'CONFIG_STORE_MAPPING_MISMATCH')
    require(type(config['scenes']) is dict and config['scenes'],'EXISTING_SCENE_BINDINGS_REQUIRED')
    require(hashlib.sha256(canonical(config['scenes'])).hexdigest()==plan['scene_sha256'],'ENROLLED_SCENE_SHA_MISMATCH')
    observed={key:metadata(plan['stores'][key],owner) for key in sorted(STORES)}
    for key,value in observed.items():
        value['path_sha256']=hashlib.sha256(plan['stores'][key].encode()).hexdigest()
    report=dict(schema=1,project=PROJECT,scope='CONFIG_AND_FILE_METADATA_ONLY',
        config_sha256=plan['config_sha256'],scene_sha256=plan['scene_sha256'],
        config_metadata=before,stores=observed,scene_count=len(config['scenes']),
        database_contents_read=False,application_imported=False,
        history_verified=False,identity_verified=False,runtime_verified=False,
        initialization_performed=False,production_acceptance=False)
    require(len(canonical(report))<=MAX_REPORT,'REPORT_BUDGET')
    return report
