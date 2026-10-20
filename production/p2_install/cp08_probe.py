"""Read-only fixed-target probe for a separate unprivileged container."""
import errno
import json
import os
import stat
import sys


def metadata(path):
    s=os.lstat(path)
    if not stat.S_ISDIR(s.st_mode):raise ValueError('TARGET_NOT_DIRECTORY')
    return {k:getattr(s,'st_'+k) for k in ('dev','ino','uid','gid','mode','mtime_ns','ctime_ns')}


def main():
    raw=sys.stdin.buffer.read(65537)
    if len(raw)>65536:raise ValueError('INPUT_BOUND')
    expected=json.loads(raw)
    if set(expected)!={'request_sha256','cp03_sha256','cp07_sha256','host_path','metadata'}:
        raise ValueError('PROBE_FIELDS')
    before=metadata('/target');number=None
    try:
        fd=os.open('/target',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        os.close(fd)
    except OSError as exc:number=exc.errno
    after=metadata('/target')
    result={'schema':1,'context':expected,'target':'/target',
            'uid':os.getuid(),'euid':os.geteuid(),'gid':os.getgid(),
            'groups':os.getgroups(),'errno':number,'before':before,'after':after}
    print(json.dumps(result,sort_keys=True,separators=(',',':')))
    return 0 if (number in (errno.EACCES,errno.EPERM) and before==after==expected['metadata']
                 and os.getuid()==os.geteuid()==65534 and os.getgid()==65534
                 and os.getgroups() in ([],[65534])) else 2


if __name__=='__main__':sys.exit(main())
