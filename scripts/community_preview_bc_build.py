"""Offline proposal builder. Builds only a NEW control carrier; never an image."""
import hashlib
import io
import json
import os
import re
import subprocess
import shlex
import zipfile
from pathlib import Path
from scripts import community_preview_stopped_handoff as h

ROOT=Path(__file__).resolve().parents[1]
def build():
    files={name:(ROOT/('scripts/community_preview_bc_loader.py' if name=='loader.py' else name)).read_bytes()
           for name in sorted(h.SOURCE_FILES)}
    manifest=dict(format=1,mode=h.MODE,install_root=h.CONTROL,updates_enabled=False,
        files={name:dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),uid=0,mode='0600')
               for name,b in files.items()})
    body=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for name,b in sorted(dict(files,**{'manifest.json':body}).items()):
            meta=zipfile.ZipInfo(name,(2026,10,24,0,0,0));meta.create_system=3;meta.external_attr=0o100600<<16;meta.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(meta,b)
    loader_sha=hashlib.sha256(files['loader.py']).hexdigest()
    manifest_sha=hashlib.sha256(body).hexdigest()
    bootstrap="""import os,stat,hashlib
path='/opt/xuanjun-community-preview/control-stopped-v1/loader.py'
fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
try:
 for part in path.split('/')[1:-1]:
  child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
  st=os.fstat(fd)
  assert st.st_uid==0 and not st.st_mode&0o022
 leaf=os.open('loader.py',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
 try:
  st=os.fstat(leaf)
  assert stat.S_ISREG(st.st_mode) and st.st_uid==0 and stat.S_IMODE(st.st_mode)==0o600 and st.st_nlink==1 and st.st_size<=131072
  raw=os.read(leaf,131073)
  def identity(v):return (v.st_dev,v.st_ino,v.st_mode,v.st_uid,v.st_gid,v.st_nlink,v.st_size,v.st_mtime_ns,v.st_ctime_ns)
  assert len(raw)==st.st_size and identity(st)==identity(os.fstat(leaf))==identity(os.stat('loader.py',dir_fd=fd,follow_symlinks=False))
 finally:os.close(leaf)
finally:os.close(fd)
assert hashlib.sha256(raw).hexdigest()==LOADER_SHA
ns={'__name__':'fixed_stopped_loader'};exec(compile(raw,path,'exec'),ns)
module=ns['load'](MANIFEST_SHA)
raise SystemExit(module.main([ACTION]))
"""
    commands={}
    for name,action in (('owner-bc','--owner-bc'),('resume-b-partial','--resume-b-partial'),('recover-known-failure','--recover-known-failure')):
        code=bootstrap.replace('LOADER_SHA',repr(loader_sha)).replace('MANIFEST_SHA',repr(manifest_sha)).replace('ACTION',repr(action))
        commands[name]=("""# SOURCE REVIEW ONLY; separate exact B/C approval required.
# Require Python BC_RESULT plus matching SUDO_CHILD_EXIT. Shell rc0 is NOT PASS.
if (
 set +e
 /usr/bin/sudo -n /usr/bin/python3 -I -B -S -c """+shlex.quote(code)+"""
 community_bc_exit=$?
 printf '{"record":"SUDO_CHILD_EXIT","child_exit":%s,"login_shell_preserved":true,"shell_exit_not_acceptance":true,"servertrust":false}\n' "$community_bc_exit"
 printf '{"record":"BC_OUTER_NOT_ACCEPTANCE","requires":["BC_RESULT","SUDO_CHILD_EXIT"],"shell_rc_is_acceptance":false}\n'
 exit "$community_bc_exit"
); then
 :
else
 :
fi
""").encode()
    return stream.getvalue(),body,commands

EXPECTED_SOURCE_FILES={'loader.py','scripts/community_preview_release_plan.py','scripts/community_preview_upgrade.py',
 'scripts/community_preview_version_inspect.py','scripts/community_preview_update_checkpoint.py',
 'scripts/community_preview_update_composition.py','scripts/community_preview_site_prepare.py',
 'scripts/community_preview_stopped_handoff.py','deploy/community-preview/f131-image-receipt.json'}
BUILD_INPUTS={'scripts/community_preview_bc_build.py','scripts/community_preview_bc_loader.py',
 'scripts/community_preview_bc_install.py','deploy/community-preview/install-stopped-v1.sh'}

def commit_binding():
    try:
        if h.SOURCE_FILES!=EXPECTED_SOURCE_FILES:return None
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        if re.fullmatch('[0-9a-f]{40}',head) is None:return None
        if os.environ.get('GITHUB_SHA') and os.environ['GITHUB_SHA']!=head:return None
        paths=BUILD_INPUTS|{('scripts/community_preview_bc_loader.py' if name=='loader.py' else name) for name in EXPECTED_SOURCE_FILES}
        for path in paths:
            if subprocess.check_output(['git','show',head+':'+path],cwd=ROOT,stderr=subprocess.DEVNULL)!=(ROOT/path).read_bytes():return None
        return head
    except (OSError,subprocess.SubprocessError):return None

if __name__=='__main__':
    target=ROOT/'deploy/community-preview/stopped-handoff-v1-delivery'
    # EXCL output prevents overwriting any prior delivery, especially A v1.
    target.mkdir(exist_ok=False)
    archive,manifest,commands=build()
    (target/'control-stopped-v1.zip').write_bytes(archive)
    (target/'manifest.json').write_bytes(manifest)
    for name,body in commands.items():(target/(name+'.sh')).write_bytes(body)
    report=dict(candidate_commit=commit_binding(),base_source='2853904258ca036a4abcdc2c829278634c45370b',
        status='SOURCE_CANDIDATE_NOT_SITE_AUTHORIZED',product_source='f13155ed63a3137d41766ee587d9b4b96a81477f',
        archive_bytes=len(archive),archive_sha256=hashlib.sha256(archive).hexdigest(),
        files={name:dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for name,b in commands.items()},
        install_candidate=dict(site_executed=False,install_executed=False,directory_mode='0700',file_mode='0600',
            no_extractall=True,requires_separate_root_review=True,install_root=h.CONTROL,
            installer_path='/opt/xuanjun-community-preview/install-stopped-v1.py',
            archive_sha256=hashlib.sha256(archive).hexdigest(),manifest_sha256=hashlib.sha256(manifest).hexdigest(),
            installer_sha256=hashlib.sha256((ROOT/'scripts/community_preview_bc_install.py').read_bytes()).hexdigest(),
            shell_sha256=hashlib.sha256((ROOT/'deploy/community-preview/install-stopped-v1.sh').read_bytes()).hexdigest(),
            publish_success_requires=['renameat2_noreplace','identity_reconcile','parent_fsync','final_identity','final_tree'],
            published_unknown=dict(target_published=True,retry_safe=False,parent_fsync_completed='boolean',
                publish_attempted=True,temp_identity_sha256='sha256'),
            nonpublished_hold=dict(retry_safe=False,publish_attempted='boolean',target_published=False),
            entry_consumption=dict(success_requires=['exactly_one_complete_success_receipt','child_exit_0'],
                otherwise='V2_INSTALL_ENTRY_UNKNOWN_INSPECT_ONLY',retry_safe=False,bc_admitted=False)),
        source_manifest_sha256=hashlib.sha256(manifest).hexdigest(),site_executed=False)
    (target/'delivery.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
