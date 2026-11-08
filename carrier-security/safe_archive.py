"""Safe carrier archive scanner. Does not install or execute archives."""
import hashlib, io, tarfile

def scan(data, expected):
    seen=set(); total=0
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:*') as t:
        for m in t:
            p=m.name
            if not p or p.startswith('/') or any(v in ('','.','..') for v in p.split('/')): raise ValueError('UNSAFE_PATH')
            if p in seen or not (m.isfile() or m.isdir()): raise ValueError('UNSAFE_MEMBER')
            seen.add(p)
            if m.isdir():
                if expected.get(p)!={'type':'directory'}:raise ValueError('DIRECTORY_MISMATCH')
            else:
                total+=m.size
                if m.size>67108864 or total>268435456:raise ValueError('SIZE_LIMIT')
                content=t.extractfile(m).read(m.size+1)
                if expected.get(p)!={'type':'file','size':len(content),'sha256':hashlib.sha256(content).hexdigest()} or len(content)!=m.size:raise ValueError('FILE_MISMATCH')
    if seen!=set(expected):raise ValueError('MEMBER_SET_MISMATCH')
    return seen
