"""Exact 42-file plus runtime-manifest source, no authority or CLI."""
import os
from pathlib import Path

import pr17_b5_successor_binder as binder
from successor_contract import Hold, require, sha
from successor_source_loader import read_exact_42, _read_one


class SourceHold(Hold):
    pass


def read_fixed_local_source(spec, root):
    root = Path(root)
    require(root.is_absolute() and not root.is_symlink(), 'SOURCE_ROOT_SCOPE')
    # The actual approved source root is a separate host admission fact. The
    # original site caller must bind it; a passed path is not authorization.
    manifest_name = binder.MANIFEST_PATH
    try:
        fd = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            # This file is fixed by the external binder and is not counted as
            # one of the 42 runtime rows.
            st = os.stat(manifest_name, dir_fd=fd, follow_symlinks=False)
            raw = _read_one(fd, manifest_name, st.st_size, binder.MANIFEST)
        finally:
            os.close(fd)
        sources = read_exact_42(str(root), raw)
        sources[manifest_name] = raw
        binder.verify_supplied_source(spec, sources)
        return sources
    except (OSError, Hold):
        raise SourceHold('SUCCESSOR_SOURCE_NOT_BOUND') from None


def production_inputs_unavailable():
    raise SourceHold('PRODUCTION_BASELINE_AND_AUTHORITY_NOT_CONNECTED')
