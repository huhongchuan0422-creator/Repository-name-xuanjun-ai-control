"""PR17 c53: offline, pinned source-input reader ONLY.

This module is NOT a production loader or authority provider. It never reads
UK baselines, starts workers, opens queues, calls connectors, or grants access.
"""
import hashlib
import os
import stat
import zipfile
from pathlib import Path

import pr17_c53_r2_transaction_candidate as binder

ZIP_NAME = "b5-c53-source-bytes-32(1).zip"
ZIP_BYTES = 76745
ZIP_SHA256 = "83404877b0480c98adb88cdcd605afda9e7f6028ef0222495b5b25df23999dbc"
MANIFEST_NAME = "b5-c53-source-manifest-original(1).json"
MANIFEST_BYTES = 6904
MANIFEST_SHA256 = "e528eea2f8d5be5f6214ec85d914c3bcb9905be40669ce06b9a77d2b5736d76f"

class SourceHold(Exception):
    pass

def _read_bound(path, size, digest):
    fd = None
    try:
        fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size!=size:
            raise SourceHold("SOURCE_INPUT_METADATA")
        chunks=[];count=0
        while count<size:
            piece=os.read(fd,min(65536,size-count))
            if not piece:raise SourceHold("SOURCE_INPUT_SHORT_READ")
            chunks.append(piece);count+=len(piece)
        after=os.fstat(fd)
        named=os.stat(str(path),follow_symlinks=False)
        identity=lambda st:(st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,
                            st.st_nlink,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        if identity(before)!=identity(after) or identity(before)!=identity(named):
            raise SourceHold("SOURCE_INPUT_REPLACED")
        raw=b"".join(chunks)
        if hashlib.sha256(raw).hexdigest()!=digest:
            raise SourceHold("SOURCE_INPUT_SHA")
        return raw
    except SourceHold:
        raise
    except OSError:
        raise SourceHold("SOURCE_INPUT_UNAVAILABLE") from None
    finally:
        if fd is not None:os.close(fd)

def read_fixed_local_source(spec, root):
    """Reads only two exact approved input filenames under the supplied root."""
    root=Path(root)
    if not root.is_absolute() or root.is_symlink():
        raise SourceHold("SOURCE_ROOT_SCOPE")
    zipped=_read_bound(root/ZIP_NAME,ZIP_BYTES,ZIP_SHA256)
    manifest=_read_bound(root/MANIFEST_NAME,MANIFEST_BYTES,MANIFEST_SHA256)
    try:
        import io
        with zipfile.ZipFile(io.BytesIO(zipped)) as z:
            records={x["path"]:x for x in spec["source"]["source_records"]}
            if len(records)!=32 or len(z.namelist())!=32 or set(z.namelist())!=set(records):
                raise SourceHold("SOURCE_MEMBER_SCOPE")
            if len(set(z.namelist()))!=32 or z.testzip() is not None:
                raise SourceHold("SOURCE_MEMBER_DUPLICATE_OR_CRC")
            values={}
            for name,meta in records.items():
                info=z.getinfo(name)
                if info.file_size!=meta["bytes"] or info.file_size>30000:
                    raise SourceHold("SOURCE_MEMBER_LENGTH")
                raw=z.read(name)
                if len(raw)!=meta["bytes"] or hashlib.sha256(raw).hexdigest()!=meta["sha256"]:
                    raise SourceHold("SOURCE_MEMBER_SHA")
                values[name]=raw
        values[binder.MANIFEST_PATH]=manifest
        binder.verify_supplied_source(spec,values)
        return values
    except (zipfile.BadZipFile,KeyError,ValueError,EOFError):
        raise SourceHold("SOURCE_ARCHIVE_INVALID") from None

def production_inputs_unavailable():
    """No baseline/grant/ACK interface in this offline source-only adapter."""
    raise SourceHold("PRODUCTION_BASELINE_AND_AUTHORITY_NOT_CONNECTED")
