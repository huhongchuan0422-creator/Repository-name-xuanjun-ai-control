#!/usr/bin/env python3
"""Fixed UK Owner dashboard installer. Root/no arguments; no inference/deploys.

SOURCE_COMMIT is pinned by the reviewer before installation. This installs one
new read-only dashboard unit and one no-argument audit helper. It neither stops
nor modifies the existing Coordinator/OpenClaw/callback services. No token is
printed. Dry-run validation is available by importing build_plan in tests.
"""
import hashlib
import json
import os
import pwd
import re
import secrets
import socket
import stat
import subprocess
import tempfile

SOURCE_COMMIT = '8b4a67d9a75a63a880172becefd6d22851edd4c3'
MANIFEST = {
    'activation_control.py': 'c03e6b7516cbc8aa14b52d018dbfa8d06d0740154bf7110c94941b9d6e550bd8',
    'owner_dashboard.py': '138af6496f491ab4bf15c24020a6f66bb0899dadeae8eb66c6b583031c7f5f09',
    'owner_dashboard.html': '79cd5f314230e0e2862f26e73b48ef617090feba641b9dd8952eb224db2e368a',
}
HOST = 'iZd7oeikknn1z21sq6ji6zZ'
RELEASE = '/opt/xuanjun-uk-control/release'
TOKEN = '/home/xuanjun_dev/.config/xuanjun/owner-dashboard-token'
ACTIVATION_DESCRIPTOR = '/var/lib/xuanjun-development/activation/active.json'
ACTIVATION_EPOCH_JOURNAL = '/var/lib/xuanjun-development/activation/epochs.jsonl'
ACTIVATION_LOCK = '/var/lib/xuanjun-development/activation/activation.lock'
AUDIT = '/usr/local/sbin/xuanjun-uk-owner-audit'
UNIT_PATH = '/etc/systemd/system/xuanjun-uk-owner-dashboard.service'
SUDOERS = '/etc/sudoers.d/xuanjun-uk-owner-audit'

UNIT = '''[Unit]
Description=Xuanjun UK read-only Owner dashboard
After=network.target

[Service]
Type=simple
User=xuanjun_dev
Group=xuanjun_dev
WorkingDirectory=/opt/xuanjun-uk-control/release
ExecStart=/usr/bin/python3 /opt/xuanjun-uk-control/release/owner_dashboard.py --activation-descriptor /var/lib/xuanjun-development/activation/active.json --activation-epoch-journal /var/lib/xuanjun-development/activation/epochs.jsonl --activation-lock /var/lib/xuanjun-development/activation/activation.lock --token-file /home/xuanjun_dev/.config/xuanjun/owner-dashboard-token --port 18556
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
UMask=0077

[Install]
WantedBy=multi-user.target
'''

AUDIT_PROGRAM = r'''#!/usr/bin/python3
"""Fixed no-argument privileged read-only summaries; never emit credentials."""
import json,os,pwd,re,socket,stat,subprocess,sys,urllib.request,urllib.error
HOME='/home/xuanjun_dev'
TOKEN=HOME+'/.config/xuanjun/owner-dashboard-token'
ENV={'PATH':HOME+'/.openclaw/tools/node-v24.21.0/bin:/usr/local/bin:/usr/bin:/bin','HOME':HOME,'LANG':'C.UTF-8'}
if os.geteuid()!=0 or len(sys.argv)!=1 or socket.gethostname().split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ':
 raise SystemExit('STOP_FIXED_AUDIT_SCOPE')
def run(argv):
 try:
  p=subprocess.run(argv,env=ENV,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=15,check=False)
  return p.returncode,p.stdout[:262144].decode('utf-8','replace')
 except (OSError,subprocess.SubprocessError):return None,''
def mode(path):
 try:
  s=os.lstat(path)
  return {'present':True,'regular':stat.S_ISREG(s.st_mode),'mode':oct(stat.S_IMODE(s.st_mode)),'owner_uid':s.st_uid}
 except OSError:return {'present':False}
result={'runtime_acceptance':'UNKNOWN','auth_files':{p:mode(p) for p in [HOME+'/.codex/auth.json',HOME+'/.openclaw/agents/main/agent/auth-profiles.json',TOKEN]},'binaries':[],'units':{}}
for p in [HOME+'/.openclaw/bin/codex',HOME+'/.local/bin/codex','/usr/local/bin/codex','/usr/bin/codex',HOME+'/.openclaw/bin/openclaw']:
 if os.path.isfile(p):result['binaries'].append(p)
for unit in ['xuanjun-uk-openclaw.service','xuanjun-uk-stage1-minimal.service','xuanjun-uk-owner-callback.service','xuanjun-uk-owner-dashboard.service','xj-uk-domestic-customer-tunnel.service','xj-uk-owner-notify.timer','nginx.service']:
 code,out=run(['/usr/bin/systemctl','is-active',unit])
 value=out.strip()
 result['units'][unit]=value if value in ('active','inactive','failed','activating','deactivating','unknown') else 'UNKNOWN'
result['auth_profiles']=[]
for path in [HOME+'/.openclaw/agents/main/agent/auth-profiles.json','/root/.openclaw/agents/main/agent/auth-profiles.json']:
 summary={'path':path,'present':False,'profiles':[]}
 try:
  s=os.lstat(path)
  if not stat.S_ISREG(s.st_mode):raise ValueError('unsafe')
  with open(path) as stream:raw=stream.read(262145)
  if len(raw)>262144:raise ValueError('oversize')
  data=json.loads(raw)
  profiles=data.get('profiles',{}) if isinstance(data,dict) else {}
  if isinstance(profiles,dict):
   for profile in list(profiles.values())[:100]:
    if not isinstance(profile,dict):continue
    mode=profile.get('type',profile.get('mode'))
    provider=profile.get('provider')
    summary['profiles'].append({'mode':mode if mode in ('oauth','api_key','token','api-key') else 'UNKNOWN','provider':provider if provider in ('openai','openai-codex','anthropic','google','github-copilot','ollama') else 'UNKNOWN'})
  summary['present']=True
 except Exception:summary['status']='UNKNOWN'
 result['auth_profiles'].append(summary)
result['ssh_hosts']=[]
try:
 config=HOME+'/.ssh/config'
 if not stat.S_ISREG(os.lstat(config).st_mode):raise ValueError('unsafe')
 with open(config) as stream:raw=stream.read(65537)
 if len(raw)>65536:raise ValueError('oversize')
 entry=None
 for line in raw.splitlines():
  parts=line.strip().split(None,1)
  if len(parts)!=2 or parts[0].startswith('#'):continue
  key,value=parts[0].lower(),parts[1].strip()
  if key=='host':
   aliases=[p for p in value.split() if re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',p)]
   entry={'aliases':aliases}
   if aliases:result['ssh_hosts'].append(entry)
  elif entry is not None and key in ('hostname','user','port','identityfile'):
   value=os.path.basename(value) if key=='identityfile' else value
   if re.fullmatch(r'[A-Za-z0-9_.:-]{1,253}',value):entry[key]=value
except Exception:result['ssh_config_status']='UNKNOWN'
cli=HOME+'/.openclaw/bin/openclaw'
result['openclaw_help']={}
if os.path.isfile(cli):
 for name,args in [('root',['--help']),('models',['models','--help']),('agent',['agent','--help']),('auth',['models','auth','--help'])]:
  code,out=run(['/usr/sbin/runuser','-u','xuanjun_dev','--',cli]+args)
  # Only syntactic option flags survive; never emit raw help/diagnostics.
  result['openclaw_help'][name]={'exit_code':code,'flags':sorted(set(re.findall(r'(?<![A-Za-z0-9_])--[a-z][a-z0-9-]{0,63}',out)))[:120]}
result['dashboard_http']={}
for path in ['/','/api/state']:
 try:
  request=urllib.request.Request('http://127.0.0.1:18556'+path)
  if path=='/api/state':
   fd=os.open(TOKEN,os.O_RDONLY|os.O_NOFOLLOW)
   with os.fdopen(fd) as stream:
    s=os.fstat(stream.fileno())
    if not stat.S_ISREG(s.st_mode) or stat.S_IMODE(s.st_mode)!=0o600 or s.st_uid!=pwd.getpwnam('xuanjun_dev').pw_uid:raise ValueError('unsafe')
    token=stream.read(257).strip()
   if re.fullmatch(r'[A-Za-z0-9_-]{32,256}',token) is None:raise ValueError('unsafe')
   request.add_header('Authorization','Bearer '+token)
  with urllib.request.urlopen(request,timeout=5) as response:
   result['dashboard_http'][path]=response.status
 except urllib.error.HTTPError as error:result['dashboard_http'][path]=error.code
 except Exception:result['dashboard_http'][path]='UNKNOWN'
print(json.dumps(result,sort_keys=True))
'''


def secure_path(path, owners, allow_missing=False):
    if not os.path.isabs(path):
        raise ValueError('ABSOLUTE_PATH_REQUIRED')
    current = '/'
    for part in path.strip('/').split('/'):
        if part in ('.', '..'):
            raise ValueError('PATH_ESCAPE')
        current = os.path.join(current, part)
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            if allow_missing:
                continue
            raise
        if stat.S_ISLNK(info.st_mode) or info.st_uid not in owners:
            raise ValueError('UNTRUSTED_PATH')


def source_bytes(path, owners, expected):
    secure_path(path, owners)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in owners:
            raise ValueError('UNTRUSTED_SOURCE_FILE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(500001)
        if len(raw) > 500000 or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('SOURCE_HASH_MISMATCH')
        return raw
    finally:
        os.close(fd)


def build_plan(commit, owners):
    """Validate exact bytes before any install effect; dry-run returns payloads."""
    if re.fullmatch(r'[0-9a-f]{40}', commit) is None:
        raise ValueError('PINNED_SOURCE_COMMIT_REQUIRED')
    source = '/tmp/xuanjun-uk-integration-' + commit + '/stage1'
    files = {name: source_bytes(os.path.join(source, name), owners, digest)
             for name, digest in MANIFEST.items()}
    return {'release_files': files, 'unit': UNIT.encode('utf-8'),
            'audit': AUDIT_PROGRAM.encode('utf-8'),
            'sudoers': ('githubrunner ALL=(root) NOPASSWD: ' + AUDIT + ' ""\n').encode('ascii')}


def atomic(path, data, uid=0, gid=0, mode=0o644):
    secure_path(path, {0, uid}, allow_missing=True)
    parent = os.path.dirname(path)
    fd, temporary = tempfile.mkstemp(prefix='.xuanjun-install-', dir=parent)
    try:
        os.fchmod(fd, mode)
        os.fchown(fd, uid, gid)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def ensure_directory(path, uid, gid, mode):
    secure_path(path, {0, uid}, allow_missing=True)
    if not os.path.exists(path):
        os.mkdir(path, mode)
        os.chown(path, uid, gid)
    info = os.lstat(path)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid:
        raise ValueError('UNSAFE_DESTINATION_DIRECTORY')
    # Only our new dedicated directories have their modes tightened.
    os.chmod(path, mode)


def ensure_token(path, uid, gid):
    secure_path(path, {0, uid}, allow_missing=True)
    if os.path.exists(path):
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != uid or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('UNSAFE_EXISTING_TOKEN')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            token = stream.read(257).strip()
        if re.fullmatch(r'[A-Za-z0-9_-]{32,256}', token) is None:
            raise ValueError('INVALID_EXISTING_TOKEN')
        return
    atomic(path, (secrets.token_urlsafe(48) + '\n').encode('ascii'), uid, gid, 0o600)


def main():
    import sys
    if os.geteuid() != 0 or len(sys.argv) != 1 or socket.gethostname().split('.')[0] != HOST:
        raise SystemExit('STOP_FIXED_UK_INSTALL_SCOPE')
    user, runner = pwd.getpwnam('xuanjun_dev'), pwd.getpwnam('githubrunner')
    plan = build_plan(SOURCE_COMMIT, {0, user.pw_uid, runner.pw_uid})
    for path in (ACTIVATION_DESCRIPTOR, ACTIVATION_EPOCH_JOURNAL,
                 ACTIVATION_LOCK):
        secure_path(path, {0, user.pw_uid})
        if not stat.S_ISREG(os.lstat(path).st_mode):
            raise ValueError('CANONICAL_ACTIVATION_FILE_REQUIRED')
    for path in [RELEASE, TOKEN, UNIT_PATH, AUDIT, SUDOERS]:
        secure_path(path, {0, user.pw_uid}, allow_missing=True)
    # Fail before effects if another unrelated service is already listening.
    import socket as sockets
    probe = sockets.socket()
    try:
        probe.bind(('127.0.0.1', 18556))
    except OSError:
        status = subprocess.run(['/usr/bin/systemctl', 'is-active', '--quiet',
                                 'xuanjun-uk-owner-dashboard.service'], check=False)
        if status.returncode:
            raise ValueError('DASHBOARD_PORT_IN_USE')
    finally:
        probe.close()
    ensure_directory('/opt/xuanjun-uk-control', 0, 0, 0o755)
    ensure_directory(RELEASE, 0, 0, 0o755)
    config = '/home/xuanjun_dev/.config'
    if not os.path.exists(config):
        ensure_directory(config, user.pw_uid, user.pw_gid, 0o700)
    ensure_directory(config + '/xuanjun', user.pw_uid, user.pw_gid, 0o700)
    ensure_token(TOKEN, user.pw_uid, user.pw_gid)
    for name, data in plan['release_files'].items():
        atomic(RELEASE + '/' + name, data)
    atomic(AUDIT, plan['audit'], mode=0o755)
    atomic(UNIT_PATH, plan['unit'])
    # Validate a root-only temporary sudoers file before replacing live policy.
    fd, temporary = tempfile.mkstemp(prefix='.xuanjun-sudoers-', dir='/etc/sudoers.d')
    try:
        os.fchmod(fd, 0o440)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(plan['sudoers'])
        subprocess.run(['/usr/sbin/visudo', '-cf', temporary], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        atomic(SUDOERS, plan['sudoers'], mode=0o440)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    subprocess.run(['/usr/bin/systemctl', 'daemon-reload'], check=True)
    subprocess.run(['/usr/bin/systemctl', 'enable', 'xuanjun-uk-owner-dashboard.service'], check=True)
    subprocess.run(['/usr/bin/systemctl', 'restart', 'xuanjun-uk-owner-dashboard.service'], check=True)
    # Installation success is not a runtime/CI/production acceptance claim.
    print('OWNER_DASHBOARD_INSTALL=FILES_AND_UNIT_INSTALLED')
    print('OWNER_DASHBOARD_RUNTIME=UNKNOWN_UNTIL_AUDIT')
    print('OWNER_DASHBOARD_BIND=127.0.0.1:18556')
    print('OWNER_TOKEN_DISCLOSED=NO')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('INSTALL_FAILED_NO_RAW_DIAGNOSTICS')
