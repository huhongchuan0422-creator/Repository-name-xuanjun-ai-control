"""Apply the native snapshot ACL fix only to exact frozen source snippets."""
import pathlib, shutil, sys

def replace_once(path, old, new):
    text=path.read_text()
    if text.count(old)!=1:raise ValueError('NATIVE_SNAPSHOT_SOURCE_DRIFT:'+path.name)
    path.write_text(text.replace(old,new))

def apply(source):
    here=pathlib.Path(__file__).resolve().parent
    shutil.copy2(str(here/'native_snapshot_access.py'),str(source/'stage1/native_snapshot_access.py'))
    pipeline=source/'stage1/development_pipeline.py'
    replace_once(pipeline,
        "                 github_lock_path=None):",
        "                 github_lock_path=None, snapshot_access=None):")
    replace_once(pipeline,
        "        self.github_lock_path = github_lock_path\n",
        "        self.github_lock_path = github_lock_path\n"
        "        self.snapshot_access = snapshot_access\n"
        "        if snapshot_access is not None:\n"
        "            from native_snapshot_access import NativeSnapshotAccess\n"
        "            if not isinstance(snapshot_access, NativeSnapshotAccess) or snapshot_access.root != workspace_root:\n"
        "                raise ValueError('BOUND_NATIVE_SNAPSHOT_ACCESS_REQUIRED')\n")
    replace_once(pipeline,
        "            self._fsync_dir(root)\n        finally:\n            os.umask(old)\n",
        "            self._fsync_dir(root)\n"
        "            access = getattr(self, 'snapshot_access', None)\n"
        "            if access is not None:\n"
        "                access.share(root)\n"
        "                self._fsync_dir(root)\n"
        "        finally:\n            os.umask(old)\n")
    replace_once(pipeline,
        "        def walk(dirfd, prefix):\n            directory_before = os.fstat(dirfd)\n",
        "        def walk(dirfd, prefix):\n"
        "            directory_before = os.fstat(dirfd)\n"
        "            access = getattr(self, 'snapshot_access', None)\n"
        "            if access is not None:\n"
        "                access.validate(dirfd, directory=True)\n")
    replace_once(pipeline,
        "                    if physical_mode not in (0o600, 0o700):\n"
        "                        raise UnknownEffect('unsupported snapshot mode')\n"
        "                    mode = 0o100755 if physical_mode == 0o700 else 0o100644\n",
        "                    allowed_modes = (0o600, 0o700) if access is None else (0o640, 0o660, 0o750, 0o770)\n"
        "                    if physical_mode not in allowed_modes:\n"
        "                        raise UnknownEffect('unsupported snapshot mode')\n"
        "                    mode = 0o100755 if physical_mode in (0o700, 0o750, 0o770) else 0o100644\n")
    old="                    try:\n                        before = os.fstat(fd)\n                        if ((info.st_dev, info.st_ino, info.st_mode, info.st_nlink) !="
    # The file read block has this exact unique indentation in _scan_snapshot.
    replace_once(pipeline,old,
        "                    try:\n"
        "                        before = os.fstat(fd)\n"
        "                        if access is not None:\n"
        "                            if access.validate(fd) != mode:\n"
        "                                raise UnknownEffect('snapshot ACL mode mismatch')\n"
        "                        if ((info.st_dev, info.st_ino, info.st_mode, info.st_nlink) !=")
    replace_once(pipeline,
        "if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=\n"
        "                            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):",
        "if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_uid, before.st_mode) !=\n"
        "                            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_uid, after.st_mode)):")
    service=source/'stage1/development_service.py'
    replace_once(service,
        "                         github_lock_path=config['github_writer_lock'])",
        "                         github_lock_path=config['github_writer_lock'])\n"
        "    from native_snapshot_access import NativeSnapshotAccess\n"
        "    dispatcher_uid=pwd.getpwnam('xuanjun-dispatcher').pw_uid\n"
        "    if os.geteuid()!=dispatcher_uid:\n"
        "        raise ValueError('NATIVE_SNAPSHOT_DISPATCHER_UID_REQUIRED')\n"
        "    backend.snapshot_access=NativeSnapshotAccess(config['workspace_root'],dispatcher_uid,\n"
        "                                                pwd.getpwnam('xuanjun_dev').pw_uid)")
    print('NATIVE_SNAPSHOT_ACL_OVERLAY_APPLIED')

if __name__=='__main__':apply(pathlib.Path(sys.argv[1]).resolve())
