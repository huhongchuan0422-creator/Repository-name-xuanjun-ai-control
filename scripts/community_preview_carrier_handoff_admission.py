"""Issue76 old->new stopped V2 carrier: source-only authority constants.

This module does NOT authorize installation, rename, rollback, B, or C.
Current host identity, unique writer, existing intents, and durable handoff
state must be independently reviewed before a future site operation.
"""
import hashlib
import json
import re

HOST='iZd7oeikknn1z21sq6ji6zZ'
INSTALL_ROOT='/opt/xuanjun-community-preview/control-stopped-v1'
OLD_ARCHIVE='5107d2f762d018d067c22ca034e41e0e5ee9b8e529cfdfc0a3dbb80a2cc6f4a4'
OLD_MANIFEST='e09b7ab9432350cafac0c07e76966d1197056eee02d802c0a2b3be7460c1ac1a'
NEW_ARCHIVE='2418f4421262f509cd84c1c8465c918ea8bbd0c2ee1101d5f692176225bcd7ff'
NEW_MANIFEST='d1d3c92b4059c7e449ed38045be9c1a5bb52ce1795365f01b41d7bd0028019fd'

class Hold(RuntimeError):
    pass

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':')).encode('utf-8')

def verify_inputs(old_manifest,new_archive,new_manifest):
    if sha(old_manifest)!=OLD_MANIFEST:
        raise Hold('OLD_INSTALLED_MANIFEST_UNPROVEN')
    if sha(new_archive)!=NEW_ARCHIVE or sha(new_manifest)!=NEW_MANIFEST:
        raise Hold('NEW_CARRIER_DIGEST_UNPROVEN')
    try:
        value=json.loads(new_manifest.decode('utf-8'))
    except (ValueError,UnicodeError):
        raise Hold('NEW_MANIFEST_INVALID')
    if (new_manifest!=canonical(value) or type(value) is not dict or
        set(value)!={'format','mode','install_root','files','updates_enabled'} or
        value['format']!=1 or type(value['format']) is not int or
        value['mode']!='STOPPED_HANDOFF_V1' or
        value['install_root']!=INSTALL_ROOT or value['updates_enabled'] is not False):
        raise Hold('NEW_MANIFEST_SCOPE_INVALID')
    return {'state':'SOURCE_HASHES_VERIFIED_LIVE_HANDOFF_HOLD',
            'old_manifest_sha256':OLD_MANIFEST,
            'new_archive_sha256':NEW_ARCHIVE,
            'new_manifest_sha256':NEW_MANIFEST,
            'site_executed':False,'bc_executed':False,
            'live_identity_verified':False,'retry_safe':False}

def execute(*args,**kwargs):
    raise Hold('LIVE_HANDOFF_NOT_AUTHORIZED_OR_IMPLEMENTED')

def rollback(*args,**kwargs):
    raise Hold('ROLLBACK_OWNERSHIP_NOT_PROVEN')
