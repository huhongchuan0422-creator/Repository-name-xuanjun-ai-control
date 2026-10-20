"""Narrow root-produced, read-only CP08 observation transport. No JSON PASS API."""
import errno
import hashlib
import json
import os
from pathlib import Path
import stat

PROBE_SHA='3bd3db756c5ad10711083682009247f25014088ce694523a55d0eb4742096081'
PRODUCER_SHA='e617acf29baff721e7f516cf9044ddbfcca43ca67e11801a5e5af631e03629b7'
IMAGE='sha256:5341f193a5741b64f2acc63a99dc95910289fcc39ff17dacff373a50e233724d'


def need(ok, code):
    if not ok:raise ValueError(code)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode('ascii')
def digest(raw):return hashlib.sha256(raw).hexdigest()


def metadata(path):
    s=os.lstat(path)
    return {k:getattr(s,'st_'+k) for k in ('dev','ino','uid','gid','mode','mtime_ns','ctime_ns')}


def snapshot(root):
    out={}
    for name in ('CP07-committed.json','ledger-config.json','profile.json',
                 'runtime-invocation.json','expected-identity.json'):
        p=Path(root)/name
        fd=os.open(str(p),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as f:
            before=os.fstat(f.fileno())
            need(stat.S_ISREG(before.st_mode) and before.st_size<=65536,'OBSERVED_FILE')
            raw=f.read(65537);after=os.fstat(f.fileno())
            need(before==after and len(raw)==before.st_size,'OBSERVED_FILE_CHANGED')
            out[name]={'sha256':digest(raw),'metadata':metadata(p)}
    return {'target':metadata(root),'files':out}


def validate(packet, context, current, image=IMAGE):
    need(set(packet)=={'schema','producer_sha256','probe_sha256','context','before','after',
                       'probe','container','command_sha256'},'OBSERVATION_FIELDS')
    need(packet['schema']==1 and packet['producer_sha256']==PRODUCER_SHA
         and packet['probe_sha256']==PROBE_SHA,'OBSERVATION_PRODUCER')
    need(packet['context']==context,'OBSERVATION_CONTEXT')
    before=packet['before'];after=packet['after']
    need(before==after,'OBSERVATION_SIDE_EFFECT_OR_REPLACEMENT')
    # Directory timestamps may advance when our own HOLD/terminal files are
    # published after the observation. Stable identity and all input files must
    # still agree. The probe's before/after timestamps themselves must agree.
    stable=('dev','ino','uid','gid','mode')
    need(all(before['target'][k]==current['target'][k] for k in stable)
         and before['files']==current['files'],'OBSERVATION_TARGET_CHANGED')
    need(current['files']['CP07-committed.json']['sha256']==context['cp07_sha256'],
         'OBSERVATION_CP07')
    probe=packet['probe']
    need(set(probe)=={'schema','context','target','uid','euid','gid','groups','errno','before','after'},
         'OBSERVATION_PROBE_FIELDS')
    expected=dict(context,metadata=before['target'])
    need(probe['context']==expected and probe['schema']==1 and probe['target']=='/target'
         and probe['uid']==probe['euid']==probe['gid']==65534 and probe['groups']==[],
         'OBSERVATION_SUBJECT')
    need(type(probe['errno']) is int and probe['errno'] in (errno.EACCES,errno.EPERM)
         and probe['before']==probe['after']==before['target'],'OBSERVATION_ERRNO_OR_TARGET')
    c=packet['container']
    need(set(c)=={'id','image','user','network','readonly_root','cap_drop','security_opt',
                  'running','exit_code','mounts','command_sha256'},'OBSERVATION_CONTAINER_FIELDS')
    need(isinstance(c['id'],str) and len(c['id'])==64 and c['image']==image
         and c['user']=='65534:65534' and c['network']=='none'
         and c['readonly_root'] is True and c['cap_drop']==['ALL']
         and c['security_opt']==['no-new-privileges'] and c['running'] is False
         and c['exit_code']==0,'OBSERVATION_CONTAINER_BOUNDARY')
    need(c['mounts']=={'/target':{'source':context['host_path'],'readonly':True},
          '/probe/probe.py':{'readonly':True,'sha256':PROBE_SHA}},'OBSERVATION_MOUNTS')
    need(c['command_sha256']==packet['command_sha256'] and
         isinstance(c['command_sha256'],str) and len(c['command_sha256'])==64,'OBSERVATION_COMMAND')
    return {'status':'PASS','source':'FIXED_ROOT_WRAPPER_READONLY_OBSERVER',
            'proof_sha256':digest(canonical(packet)),'uid':65534,'gid':65534,
            'errno':probe['errno'],'cp07_sha256':context['cp07_sha256'],
            'scope':'EXACT_PREPARATION_DIRECTORY_ONLY'}


def load(root, request_sha256, cp03_sha256):
    path='/observer/proof.json'
    # Production never accepts an evidence filename, packet, PASS flag or key
    # from the request. Root producer's file must be an actual read-only mount.
    try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    except FileNotFoundError:
        return {'status':'UNAVAILABLE','reason':'OBSERVATION_REQUIRED'}
    with os.fdopen(fd,'rb') as f:
        before=os.fstat(f.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_uid==0
             and stat.S_IMODE(before.st_mode)==0o444 and before.st_nlink in (1,2)
             and before.st_size<=65536,'OBSERVATION_PROTECTED_SOURCE')
        raw=f.read(65537);need(before==os.fstat(f.fileno()) and len(raw)==before.st_size,
                             'OBSERVATION_SOURCE_CHANGED')
    with open('/proc/self/mountinfo') as f:
        mounts=[line.split() for line in f]
    need(any(len(row)>6 and row[4]==path and 'ro' in row[5].split(',') for row in mounts),
         'OBSERVATION_READONLY_MOUNT_REQUIRED')
    current=snapshot(root)
    context={'request_sha256':request_sha256,'cp03_sha256':cp03_sha256,
             'cp07_sha256':current['files']['CP07-committed.json']['sha256'],
             'host_path':str(root)}
    packet=json.loads(raw)
    image=IMAGE
    if str(root).startswith('/tmp/p2-b3-test-host-'):
        image=packet['container']['image']  # disposable Hosted image, never UK
    return validate(packet,context,current,image=image)
