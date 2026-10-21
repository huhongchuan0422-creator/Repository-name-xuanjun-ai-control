"""Validate protected host config against already open persistent stores.

No filesystem/database creation, secret loading, network IO or deployment.
"""
import os,re,stat
from pathlib import Path
from scripts.pr122_customer_core import Center,private_path
from scripts.community_stage_runtime import StageRuntime
from scripts.community_saas_phase2 import Principal
from scripts.community_mini_login import APPID

def stores(center,runtime):
    return dict(center=center.db,orders=runtime.demo.db,merchants=runtime.demo.merchant_db,
                ads=runtime.demo.ad_db,refunds=runtime.demo.refund_db,
                quotes=runtime.saas.quotes,saas_orders=runtime.saas.orders,modules=runtime.saas.modules)

def validate(center,runtime,principals,config):
    if type(center) is not Center or type(runtime) is not StageRuntime:
        raise ValueError('EXISTING_CENTER_AND_RUNTIME_REQUIRED')
    if (type(config) is not dict or set(config)!={'version','appid','https_origin','scenes','stores'}
            or type(config['version']) is not int or config['version']!=1):
        raise ValueError('EXACT_HOST_CONFIG_REQUIRED')
    if (type(config['appid']) is not str or not APPID.fullmatch(config['appid'])
            or type(config['https_origin']) is not str
            or not re.fullmatch(r'https://[a-z0-9]+(?:[.-][a-z0-9]+)*',config['https_origin'])):
        raise ValueError('APPID_AND_HTTPS_ORIGIN_REQUIRED')
    if type(principals) is not dict or type(config['scenes']) is not dict or not config['scenes']:
        raise ValueError('HOST_SCENE_MAPPING_REQUIRED')
    if type(config['stores']) is not dict or set(config['stores'])!=set(stores(center,runtime)):
        raise ValueError('COMPLETE_PERSISTENT_STORE_MANIFEST_REQUIRED')
    for name,db in stores(center,runtime).items():
        expected=config['stores'][name]
        if type(expected) is not str or not Path(expected).is_absolute():
            raise ValueError('ABSOLUTE_PERSISTENT_STORE_PATH_REQUIRED')
        path=private_path(Path(expected))
        info=path.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o077
                or path.parent.stat().st_uid!=os.geteuid() or path.parent.stat().st_mode&0o077):
            raise PermissionError('PRIVATE_HOST_OWNED_STORE_REQUIRED')
        actual=[row[2] for row in db.execute('PRAGMA database_list') if row[1]=='main']
        if len(actual)!=1 or not actual[0] or Path(actual[0]).absolute()!=path:
            raise PermissionError('EXISTING_PERSISTENT_STORE_BINDING_MISMATCH')
    scenes={}
    for scene,binding in config['scenes'].items():
        if (type(scene) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,32}',scene)
                or type(binding) is not dict or set(binding)!={'project','principal'}
                or type(binding['principal']) is not str or type(binding['project']) is not str):
            raise ValueError('EXACT_HOST_SCENE_REQUIRED')
        principal=principals.get(binding['principal'])
        if type(principal) is not Principal or principal.role!='CUSTOMER' or principal not in runtime.bindings:
            raise PermissionError('REGISTERED_CUSTOMER_REQUIRED')
        row=center.db.execute('SELECT tenant,active,expires FROM projects WHERE id=?',(binding['project'],)).fetchone()
        if (row is None or row[1]!=1 or row[2]<=center.now()
                or row[0]!=runtime.bindings[principal]['tenant_id']):
            raise PermissionError('ACTIVE_ORIGINAL_PROJECT_SCENE_REQUIRED')
        scenes[scene]=dict(project=binding['project'],principal=principal)
    return scenes
