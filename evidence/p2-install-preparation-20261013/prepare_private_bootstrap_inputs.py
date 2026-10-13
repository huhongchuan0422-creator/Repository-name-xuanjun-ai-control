"""Prepare P2 private bootstrap inputs; never writes runtime targets or starts services."""
import os, sys, stat, socket, json, hashlib, subprocess, secrets, re

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
DURABLE = '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
EXTRA = '/tmp/p2pkg-38372850075-1/protected-additional-install-inputs.json'
EXTRA_SHA = '88cde0b1be1b65679b6b7a45fba0ccd6e08b4a0ca6625d9c5b56a6c0f0ea9001'
RELEASE = '/opt/xuanjun-control-releases/integration-27b8d6c61f5cf459'

def read(path, uid=0, mode=0o600, limit=1048576):
    assert os.path.realpath(path) == path
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        info = os.fstat(f.fileno())
        assert stat.S_ISREG(info.st_mode) and info.st_uid == uid
        assert stat.S_IMODE(info.st_mode) == mode
        raw = f.read(limit + 1)
        assert len(raw) <= limit
    return raw

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def pack(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()

def prepare(package, output):
    assert os.geteuid() == 0 and socket.gethostname().split('.')[0] == HOST
    assert os.path.realpath(package) == package and os.path.isdir(package)
    assert re.fullmatch(r'/tmp/p2pkg-[0-9]+-[0-9]+/private-bootstrap-candidate', output)
    parent = os.path.dirname(output)
    info = os.lstat(parent)
    assert info.st_uid == 0 and stat.S_ISDIR(info.st_mode) and not info.st_mode & 0o022
    os.mkdir(output, 0o700)
    raw = read(EXTRA)
    assert digest(raw) == EXTRA_SHA
    inputs = json.loads(raw.decode())
    owner = str(inputs['owner_callback_user_id'])
    chat = str(inputs['owner_callback_chat_id'])
    assert re.fullmatch(r'[0-9]{1,32}', owner)
    assert re.fullmatch(r'-?[0-9]{1,32}', chat)
    token = read(DURABLE + '/github-intake-token.input')
    assert re.fullmatch(br'github_pat_[A-Za-z0-9_]+\n?', token)
    rows = []
    def stage(name, data, target, uid, gid, mode):
        path = output + '/' + name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        rows.append({'source': path, 'sha256': digest(data), 'target': target,
                     'owner_uid': uid, 'group_gid': gid, 'mode': mode,
                     'applied': False, 'requires_approved_bootstrap': True})
    callback = '/etc/xuanjun-owner-callback/'
    stage('owner-user-id', (owner+'\n').encode(), callback+'owner-user-id', 1004, 1006, 0o600)
    stage('owner-chat-id', (chat+'\n').encode(), callback+'owner-chat-id', 1004, 1006, 0o600)
    for name in ('owner-callback-auth', 'owner-callback-hmac', 'owner-dashboard-token'):
        stage(name, (secrets.token_urlsafe(48)+'\n').encode(), callback+name, 1004, 1006, 0o600)
    stage('github-intake-token', token, '/etc/xuanjun-development/github-intake-token', 1003, 1003, 0o600)
    unit = 'xuanjun-uk-openclaw.service'
    properties = subprocess.check_output(
        ['systemctl','show',unit,'--property=MainPID,ControlGroup,ActiveState'],
        stderr=subprocess.DEVNULL, timeout=8).decode()
    props = dict(line.split('=',1) for line in properties.splitlines() if '=' in line)
    assert props['ActiveState'] == 'active'
    pid = int(props['MainPID']); assert pid > 1
    cgroup = props['ControlGroup']; assert cgroup == '/system.slice/'+unit
    with open('/proc/'+str(pid)+'/status') as f:
        uidline = next(line for line in f if line.startswith('Uid:'))
    assert all(int(x)==1002 for x in uidline.split()[1:])
    exe = os.path.realpath('/proc/'+str(pid)+'/exe')
    expected = '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/bin/node'
    assert exe == expected
    fd = os.open(exe, os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as f:
        info=os.fstat(f.fileno());assert info.st_uid==1002 and not info.st_mode&0o022
        h=hashlib.sha256()
        for chunk in iter(lambda:f.read(65536),b''):h.update(chunk)
    bridge_source = package+'/stage1/native_ledger_bridge.py'
    with open(bridge_source,'rb') as f: bridge_sha=digest(f.read())
    client = b'{"socket_path":"/run/xuanjun-development/ledger.sock","server_uid":1003}\n'
    bridge = RELEASE+'/stage1/native_ledger_bridge.py'
    config = '/etc/xuanjun-development/p2-native-ledger-client.json'
    binding = {'ledger': {'python':'/usr/libexec/platform-python3.6',
                'pythonSha256':'ba19929d7038d0c2304f528213fa11e5f10c1ce65f0a891afa459bd167c7e5f6',
                'bridge':bridge,'config':config,'files':{bridge:bridge_sha,config:digest(client)}},
               'gatewayIdentity':{'user':'xuanjun_dev','exe':exe,'sha256':h.hexdigest(),'cgroup':cgroup}}
    stage('p2-native-binding.json', pack(binding), '/etc/xuanjun-development/p2-native-binding.json', 0, 0, 0o644)
    result = {'schema':1,'state':'PRIVATE_BOOTSTRAP_CANDIDATES_NOT_APPLIED',
              'artifact_id':11819078922,'files':rows,'planned_uid_gid_unreserved':True,
              'new_owner_secrets_require_protected_delivery':True,
              'github_write_permission':'NOT_TESTED','install':False,
              'writer_admission':False,'services_changed':False,'model_calls':0}
    receipt=pack(result)
    fd=os.open(output+'/protected-bootstrap-candidate-receipt.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(receipt);f.flush();os.fsync(f.fileno())
    print('PRIVATE_BOOTSTRAP_CANDIDATE_FILES='+str(len(rows)))
    print('PRIVATE_BOOTSTRAP_CANDIDATE_RECEIPT_SHA256='+digest(receipt))
    print('RUNTIME_TARGETS_WRITTEN=NO; INSTALL=NO; WRITER_ADMISSION=NO')

if __name__ == '__main__':
    assert len(sys.argv)==3
    prepare(sys.argv[1],sys.argv[2])
