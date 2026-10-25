"""Strict local secret-file input shared by TEST_ONLY entry points."""
from __future__ import print_function

import os
import stat


def read_owned_secret_file(path, label):
    """Read a small secret only from a caller-owned, mode-0600 regular file."""
    info = os.lstat(path)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
            info.st_uid != os.geteuid()):
        raise ValueError('OWNED_REGULAR_%s_FILE_REQUIRED' % label)
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError('%s_FILE_MODE_0600_REQUIRED' % label)
    flags = os.O_RDONLY
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or
                opened.st_uid != os.geteuid() or
                stat.S_IMODE(opened.st_mode) != 0o600 or
                (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)):
            raise ValueError('SECURE_%s_FILE_CHANGED' % label)
        if opened.st_size > 65536:
            raise ValueError('%s_FILE_TOO_LARGE' % label)
        with os.fdopen(descriptor, 'r') as stream:
            descriptor = None
            return stream.read()
    finally:
        if descriptor is not None:
            os.close(descriptor)
