"""Generate the next controlled publisher version from an exact reviewed source.

Only explicit absent-baseline additions are new. The existing installed
publisher and its original repository package are never edited by this module.
"""
import hashlib
from pathlib import Path

BASE_SHA256='7253f3b86a6ad17dadc85c26deda17a5ccaaa8f76c65da21572be39658993895'
OLD='''                if target.is_symlink() or not target.is_file() or digest(target,deadline)!=baseline: raise Hold("OVERLAY_BASELINE_DRIFT:"+name)
                if overlay.is_symlink() or not overlay.is_file(): raise Hold("OVERLAY_MISSING:"+name)
                with open_trusted_file(overlay,uid,deadline) as (data_fd,_):
                    out=os.open(target,os.O_WRONLY|os.O_TRUNC|os.O_NOFOLLOW)
'''
NEW='''                added=baseline is None
                if added:
                    # Explicit additions are bound by the approved source pin and
                    # package; the final whole-tree manifest is verified before activation.
                    if target.exists() or target.is_symlink(): raise Hold("OVERLAY_ADDITION_COLLISION:"+name)
                elif target.is_symlink() or not target.is_file() or digest(target,deadline)!=baseline:
                    raise Hold("OVERLAY_BASELINE_DRIFT:"+name)
                if overlay.is_symlink() or not overlay.is_file(): raise Hold("OVERLAY_MISSING:"+name)
                with open_trusted_file(overlay,uid,deadline) as (data_fd,_):
                    if added: target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                    out=os.open(target,os.O_WRONLY|os.O_NOFOLLOW|(os.O_CREAT|os.O_EXCL if added else os.O_TRUNC),0o600)
'''

def publisher_source(root=None):
    root=Path(root) if root else Path(__file__).resolve().parents[1]
    raw=(root/'scripts/pr122_website_release.py').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=BASE_SHA256:
        raise ValueError('REVIEWED_PUBLISHER_BASE_DRIFT')
    text=raw.decode()
    if text.count(OLD)!=1:raise ValueError('PUBLISHER_DELTA_CONTEXT_DRIFT')
    return text.replace(OLD,NEW,1).encode()
