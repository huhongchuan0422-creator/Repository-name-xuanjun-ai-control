#!/usr/bin/env python3
"""Hash-gated, bounded, no-overwrite extraction; never imports kit code.

This bootstrap script/interpreter must themselves be independently trusted.
Production CLI requires root-owned protected ancestry. No recovery execution.
"""
import argparse
import errno
import gzip
import hashlib
import io
import json
import os
import re
import stat
import sys
import tarfile

ROOT_NAME = 'epoch7-recovery-candidate-r7-claim-successor'
ENTRY = 'epoch7_recovery_entry.py'
MANIFEST = 'recovery-kit-manifest.json'
MAX_COMPRESSED = 32 * 1024 * 1024
MAX_EXPANDED = 144 * 1024 * 1024
MAX_FILE = 16 * 1024 * 1024
MODE_STATUS = {'REFUSED_UNCOMPOSED': 'SOURCE_KIT_GROUNDWORK_NOT_INSTALL_ADMISSION',
    'AUTHENTICATED_CLAIM_SUCCESSOR_APPROVAL_GATED_SINGLE_ATTEMPT': 'CLAIM_SUCCESSOR_CANDIDATE_REQUIRES_NEW_EXACT_APPROVAL'}


def need(value, code):
    if not value: raise ValueError('EPOCH7_EXTRACT_' + code)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def close_all(fds, primary=None):
    failed = False
    for fd in reversed(fds):
        try: os.close(fd)
        except BaseException: failed = True
    if failed:
        if primary is None:
            error = ValueError('EPOCH7_EXTRACT_CLOSE_FAILED')
            error.delivery_cleanup_failed = True
            raise error
        primary.delivery_cleanup_failed = True


def safe_name(name):
    need(type(name) is str and 0 < len(name) <= 512 and
         re.fullmatch(r'[A-Za-z0-9_.\-/]+', name) and
         all(p not in ('', '.', '..', '__pycache__') and not p.endswith(('.pyc','.pyo'))
             for p in name.split('/')), 'PATH')
    return name


def digest(value): need(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value), 'DIGEST')


def strict_json(raw):
    def pairs(items):
        result = {}
        for name, value in items:
            need(name not in result, 'DUPLICATE_JSON_KEY'); result[name] = value
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda unused: need(False, 'NONFINITE_JSON'))


def inspect_archive(raw, archive_sha, entry_sha, manifest_sha):
    for value in (archive_sha, entry_sha, manifest_sha): digest(value)
    need(type(raw) is bytes and len(raw) <= MAX_COMPRESSED and sha(raw) == archive_sha, 'ARCHIVE_HASH')
    with gzip.GzipFile(fileobj=io.BytesIO(raw), mode='rb') as stream:
        unpacked = stream.read(MAX_EXPANDED + 1)
    need(len(unpacked) <= MAX_EXPANDED, 'DECOMPRESSION_BOUND')
    files, dirs, seen = {}, set(), set()
    with tarfile.open(fileobj=io.BytesIO(unpacked), mode='r:') as archive:
        for member in archive:
            need(len(seen) < 2048, 'MEMBER_BOUND')
            safe_name(member.name)
            need(member.name not in seen, 'DUPLICATE_MEMBER'); seen.add(member.name)
            need(member.name == ROOT_NAME or member.name.startswith(ROOT_NAME + '/'), 'ROOT_SCOPE')
            need(not member.pax_headers and member.uid == member.gid == member.mtime == 0 and
                 member.uname == member.gname == '', 'ARCHIVE_METADATA')
            name = member.name[len(ROOT_NAME):].lstrip('/')
            if member.isdir():
                need(member.mode == 0o700 and member.size == 0, 'DIRECTORY_METADATA')
                dirs.add(name)
            else:
                need(member.isfile() and member.mode == 0o444 and name and
                     0 <= member.size <= MAX_FILE, 'FILE_TYPE_OR_BOUND')
                data = archive.extractfile(member).read(MAX_FILE + 1)
                need(len(data) == member.size, 'FILE_SIZE')
                files[name] = data
        need(not any(unpacked[archive.offset:]), 'TRAILING_TAR_CONTENT')
    need(ENTRY in files and MANIFEST in files and sha(files[ENTRY]) == entry_sha and
         sha(files[MANIFEST]) == manifest_sha, 'ENTRY_OR_MANIFEST_HASH')
    value = strict_json(files[MANIFEST])
    need(type(value) is dict and type(value.get('files')) is dict and
         set(files) == set(value['files']) | {MANIFEST} and
         type(value.get('production_resume')) is str and value['production_resume'] in MODE_STATUS and
         value.get('status') == MODE_STATUS[value['production_resume']], 'MANIFEST_SCOPE')
    for name, wanted in value['files'].items():
        safe_name(name); digest(wanted)
        need(sha(files[name]) == wanted, 'MEMBER_HASH')
    expected_dirs = {''}
    for name in files:
        parts = name.split('/')
        for index in range(1, len(parts)): expected_dirs.add('/'.join(parts[:index]))
    need(dirs == expected_dirs, 'EXTRA_OR_MISSING_DIRECTORY')
    return files, dirs


def metadata(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def authority(fd, directory, owners):
    info = os.fstat(fd)
    need((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)) and
         (info.st_uid,info.st_gid) in owners and not info.st_mode & 0o7022, 'AUTHORITY')
    if not directory: need(info.st_nlink == 1, 'HARDLINK')
    for key in ('system.posix_acl_access','system.posix_acl_default'):
        try: os.getxattr(fd,key)
        except OSError as error: need(error.errno in (errno.ENODATA,errno.ENOTSUP),'ACL_READ')
        else: need(False,'ACL_PRESENT')
    return info


class ProtectedDirectory(object):
    def __init__(self,path,owners):
        need(type(path) is str and path.startswith('/') and os.path.normpath(path)==path, 'ABSOLUTE_PATH')
        self.owners,self.rows=owners,[]
        try:
            fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            self.rows.append((fd,None,None,None))
            self.rows[-1]=(fd,None,None,metadata(authority(fd,True,owners)))
            for part in path[1:].split('/') if path!='/' else []:
                parent=fd;fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
                self.rows.append((fd,parent,part,None))
                stamp=metadata(authority(fd,True,owners));self.rows[-1]=(fd,parent,part,stamp)
                need(metadata(os.stat(part,dir_fd=parent,follow_symlinks=False))==stamp,'OPEN_RACE')
            self.fd=fd
        except BaseException as error:self.close(error);raise
    def check(self):
        for fd,parent,part,stamp in self.rows:
            need(metadata(authority(fd,True,self.owners))==stamp,'ANCESTRY_RACE')
            if parent is not None:
                need(metadata(os.stat(part,dir_fd=parent,follow_symlinks=False))==stamp,'BINDING_RACE')
    def close(self, primary=None):
        rows,self.rows=self.rows,[]
        close_all([row[0] for row in rows],primary)
    def __enter__(self):return self
    def __exit__(self,kind,error,traceback):self.close(error)


def read_archive(path,owners):
    parent,leaf=os.path.split(path)
    with ProtectedDirectory(parent,owners) as tree:
        fd=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=tree.fd)
        try:
            before=authority(fd,False,owners)
            need(before.st_size<=MAX_COMPRESSED,'COMPRESSED_BOUND')
            with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(MAX_COMPRESSED+1)
            after=authority(fd,False,owners);linked=os.stat(leaf,dir_fd=tree.fd,follow_symlinks=False)
            fingerprint=lambda row:metadata(row)+(row.st_nlink,row.st_size,row.st_mtime_ns,row.st_ctime_ns)
            need(fingerprint(before)==fingerprint(after)==fingerprint(linked) and len(raw)==before.st_size,'READ_RACE')
            tree.check();return raw
        finally:os.close(fd)


def extract(raw,output,archive_sha,entry_sha,manifest_sha,owners=((0,0),)):
    files,dirs=inspect_archive(raw,archive_sha,entry_sha,manifest_sha)
    need(type(output) is str and output.startswith('/') and os.path.normpath(output)==output
         and output!='/' and os.path.basename(output)==ROOT_NAME, 'ABSOLUTE_EXACT_OUTPUT')
    parent,leaf=os.path.split(output)
    with ProtectedDirectory(parent,owners) as tree:
        os.mkdir(leaf,0o700,dir_fd=tree.fd)
        out=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=tree.fd)
        opened={'':out};primary=None
        try:
            for name in sorted(dirs-{''},key=lambda x:(x.count('/'),x)):
                p,_,base=name.rpartition('/');os.mkdir(base,0o700,dir_fd=opened[p])
                opened[name]=os.open(base,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=opened[p])
            for name,data in sorted(files.items()):
                p,_,base=name.rpartition('/')
                fd=os.open(base,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=opened[p])
                file_primary=None
                try:
                    offset=0
                    while offset<len(data):
                        count=os.write(fd,data[offset:]);need(count>0,'SHORT_WRITE');offset+=count
                    os.fchmod(fd,0o444);os.fsync(fd)
                except BaseException as error:file_primary=error;raise
                finally:close_all([fd],file_primary)
            for fd in opened.values():os.fsync(fd)
            tree.check()
            need(metadata(os.fstat(out))==metadata(os.stat(leaf,dir_fd=tree.fd,follow_symlinks=False)),'OUTPUT_BINDING_RACE')
        except BaseException as error:primary=error;raise
        finally:close_all(list(opened.values()),primary)
    return {'stage':'EXTRACTED_HASH_VERIFIED','files':len(files),'archive_sha256':archive_sha,
            'entry_sha256':entry_sha,'kit_manifest_sha256':manifest_sha,
            'production_execution':'NOT_RUN','install_admission':'NOT_GRANTED'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','output','archive-sha256','entry-sha256','kit-manifest-sha256'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args(argv)
    need(os.geteuid()==0 and sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'ROOT_ISOLATED_NO_SITE_NO_BYTECODE')
    raw=read_archive(os.path.abspath(args.archive),((0,0),))
    result=extract(raw,os.path.abspath(args.output),args.archive_sha256,args.entry_sha256,args.kit_manifest_sha256)
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__':sys.exit(main())
