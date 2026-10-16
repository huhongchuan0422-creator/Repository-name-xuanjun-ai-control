"""Bounded domestic metadata/config-source preflight; never installs or starts."""
import base64
import glob
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import stat
import subprocess
import tempfile

APEX='wenwenwenyiyiyi.work'
PREFIX='/_preview/community-api/'
ZONE='xuanjun_community_preview'
EXPECTED_HOST='iZvt5t8tlrm8oiZ'
UNIT_BASE64='W1VuaXRdCkRlc2NyaXB0aW9uPVh1YW5qdW4gcGVyLXZpc2l0b3Igc3ludGhldGljIGNvbW11bml0eSBwcmV2aWV3CkFmdGVyPW5ldHdvcmsudGFyZ2V0CgpbU2VydmljZV0KVHlwZT1zaW1wbGUKRHluYW1pY1VzZXI9eWVzCldvcmtpbmdEaXJlY3Rvcnk9L3Zhci9saWIveHVhbmp1bi1zaXRlLWh1Yi1wcmV2aWV3L2N1cnJlbnQKRXhlY1N0YXJ0PS91c3IvYmluL3B5dGhvbjMgLUkgLUIgL3Zhci9saWIveHVhbmp1bi1zaXRlLWh1Yi1wcmV2aWV3L2N1cnJlbnQvc2NyaXB0cy9wcjEyMl9zaXRlX2h1Yl9wcmV2aWV3LnB5IC0tcG9ydCAxODc5MwpFbnZpcm9ubWVudD1QWVRIT05ET05UV1JJVEVCWVRFQ09ERT0xClJlc3RhcnQ9b24tZmFpbHVyZQpSZXN0YXJ0U2VjPTMKTm9OZXdQcml2aWxlZ2VzPXllcwpQcml2YXRlVG1wPXllcwpQcml2YXRlRGV2aWNlcz15ZXMKUHJvdGVjdFN5c3RlbT1zdHJpY3QKUHJvdGVjdEhvbWU9eWVzClByb3RlY3RLZXJuZWxUdW5hYmxlcz15ZXMKUHJvdGVjdEtlcm5lbE1vZHVsZXM9eWVzClByb3RlY3RDb250cm9sR3JvdXBzPXllcwpSZXN0cmljdEFkZHJlc3NGYW1pbGllcz1BRl9JTkVUCkNhcGFiaWxpdHlCb3VuZGluZ1NldD0KTWVtb3J5TWF4PTEyOE0KVGFza3NNYXg9MTYKSVBBZGRyZXNzRGVueT1hbnkKSVBBZGRyZXNzQWxsb3c9bG9jYWxob3N0CgpbSW5zdGFsbF0KV2FudGVkQnk9bXVsdGktdXNlci50YXJnZXQK'
PARSER_BASE64='ZGVmIG5naW54X3Rva2Vucyh0ZXh0KToKICAgIHRva2Vucywgd29yZCwgcXVvdGUsIGVzY2FwZWQsIGNvbW1lbnQgPSBbXSwgJycsIE5vbmUsIEZhbHNlLCBGYWxzZQogICAgZm9yIGNoYXIgaW4gdGV4dDoKICAgICAgICBpZiBjb21tZW50OgogICAgICAgICAgICBpZiBjaGFyID09ICdcbic6IGNvbW1lbnQgPSBGYWxzZQogICAgICAgICAgICBjb250aW51ZQogICAgICAgIGlmIGVzY2FwZWQ6CiAgICAgICAgICAgIHdvcmQgKz0gY2hhcjsgZXNjYXBlZCA9IEZhbHNlOyBjb250aW51ZQogICAgICAgIGlmIGNoYXIgPT0gJ1xcJzoKICAgICAgICAgICAgZXNjYXBlZCA9IFRydWU7IGNvbnRpbnVlCiAgICAgICAgaWYgcXVvdGU6CiAgICAgICAgICAgIGlmIGNoYXIgPT0gcXVvdGU6IHF1b3RlID0gTm9uZQogICAgICAgICAgICBlbHNlOiB3b3JkICs9IGNoYXIKICAgICAgICAgICAgY29udGludWUKICAgICAgICBpZiBjaGFyIGluICgnIicsICInIik6CiAgICAgICAgICAgIHF1b3RlID0gY2hhcjsgY29udGludWUKICAgICAgICBpZiBjaGFyID09ICcjJzoKICAgICAgICAgICAgaWYgd29yZDogdG9rZW5zLmFwcGVuZCh3b3JkKTsgd29yZCA9ICcnCiAgICAgICAgICAgIGNvbW1lbnQgPSBUcnVlOyBjb250aW51ZQogICAgICAgIGlmIGNoYXIuaXNzcGFjZSgpIG9yIGNoYXIgaW4gJ3t9Oyc6CiAgICAgICAgICAgIGlmIHdvcmQ6IHRva2Vucy5hcHBlbmQod29yZCk7IHdvcmQgPSAnJwogICAgICAgICAgICBpZiBjaGFyIGluICd7fTsnOiB0b2tlbnMuYXBwZW5kKGNoYXIpCiAgICAgICAgZWxzZTogd29yZCArPSBjaGFyCiAgICBpZiBxdW90ZSBvciBlc2NhcGVkOiByYWlzZSBWYWx1ZUVycm9yKCdOR0lOWF9MRVhJQ0FMX0hPTEQnKQogICAgaWYgd29yZDogdG9rZW5zLmFwcGVuZCh3b3JkKQogICAgcmV0dXJuIHRva2VucwoKZGVmIG5naW54X3BhcnNlKHRleHQpOgogICAgdG9rZW5zLCBpbmRleCA9IG5naW54X3Rva2Vucyh0ZXh0KSwgMAogICAgZGVmIHNjb3BlKG5lc3RlZD1GYWxzZSk6CiAgICAgICAgbm9ubG9jYWwgaW5kZXgKICAgICAgICBub2Rlcywgd29yZHMgPSBbXSwgW10KICAgICAgICB3aGlsZSBpbmRleCA8IGxlbih0b2tlbnMpOgogICAgICAgICAgICB0b2tlbiA9IHRva2Vuc1tpbmRleF07IGluZGV4ICs9IDEKICAgICAgICAgICAgaWYgdG9rZW4gPT0gJ30nOgogICAgICAgICAgICAgICAgaWYgd29yZHMgb3Igbm90IG5lc3RlZDogcmFpc2UgVmFsdWVFcnJvcignTkdJTlhfUEFSU0VfSE9MRCcpCiAgICAgICAgICAgICAgICByZXR1cm4gbm9kZXMKICAgICAgICAgICAgaWYgdG9rZW4gaW4gKCc7JywgJ3snKToKICAgICAgICAgICAgICAgIGlmIG5vdCB3b3JkczogcmFpc2UgVmFsdWVFcnJvcignTkdJTlhfUEFSU0VfSE9MRCcpCiAgICAgICAgICAgICAgICBub2Rlcy5hcHBlbmQoeyduYW1lJzp3b3Jkc1swXSwgJ2FyZ3MnOndvcmRzWzE6XSwKICAgICAgICAgICAgICAgICAgICAnY2hpbGRyZW4nOnNjb3BlKFRydWUpIGlmIHRva2VuID09ICd7JyBlbHNlIFtdfSkKICAgICAgICAgICAgICAgIHdvcmRzID0gW10KICAgICAgICAgICAgZWxzZTogd29yZHMuYXBwZW5kKHRva2VuKQogICAgICAgIGlmIG5lc3RlZCBvciB3b3JkczogcmFpc2UgVmFsdWVFcnJvcignTkdJTlhfUEFSU0VfSE9MRCcpCiAgICAgICAgcmV0dXJuIG5vZGVzCiAgICByZXR1cm4gc2NvcGUoKQ=='

def run(args):
    try:
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=15)
        return {'code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
    except Exception as e:return {'code':None,'error':type(e).__name__,'stdout':'','stderr':''}

def metadata(name,digest=False):
    path=Path(name)
    try:
        i=path.lstat()
        value={'status':'OBSERVED','path':str(path),'uid':i.st_uid,'gid':i.st_gid,'mode':oct(stat.S_IMODE(i.st_mode)),
               'type':'symlink' if stat.S_ISLNK(i.st_mode) else 'directory' if stat.S_ISDIR(i.st_mode) else 'file' if stat.S_ISREG(i.st_mode) else 'other',
               'runner_writable':os.access(str(path),os.W_OK)}
        if stat.S_ISLNK(i.st_mode):value['target']=os.readlink(str(path))
        if digest and stat.S_ISREG(i.st_mode) and i.st_size<=1000000:
            value['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        return value
    except FileNotFoundError:return {'path':str(path),'status':'ABSENT'}
    except PermissionError:return {'path':str(path),'status':'UNKNOWN_PERMISSION_DENIED'}
    except Exception as e:return {'path':str(path),'status':'UNKNOWN','error':type(e).__name__}

def nginx_source():
    # Reuse the exact existing tokenizer/parser, without its host-specific main.
    namespace={};exec(compile(base64.b64decode(PARSER_BASE64),'<existing-nginx-parser>','exec'),namespace)
    parse=namespace['nginx_parse']
    base=Path('/etc/nginx');files={};active=set();total=0
    def allowed(path):
        text=str(path)
        return any(text==root or text.startswith(root+'/') for root in ('/etc/nginx','/usr/share/nginx/modules','/usr/share/nginx/modules-enabled')) or text=='/etc/letsencrypt/options-ssl-nginx.conf' or (text.startswith('/var/www/wenwenwenyiyiyi.work/releases/') and text.endswith('/release-metadata/inline-csp.conf'))
    def expand(path,depth=0):
        nonlocal total
        path=Path(path).resolve(strict=True)
        if not allowed(path):raise ValueError('INCLUDE_OUTSIDE_PUBLIC_CONFIG_ROOT')
        if path in active or depth>12 or len(files)>256:raise ValueError('INCLUDE_CYCLE_OR_LIMIT')
        before=path.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_size>512000:raise ValueError('CONFIG_OBJECT_OR_SIZE_HOLD')
        raw=path.read_bytes();after=path.stat();total+=len(raw)
        if total>2000000:raise ValueError('CONFIG_TOTAL_LIMIT')
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):raise ValueError('CONFIG_CHANGED_DURING_READ')
        files[str(path)]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'uid':before.st_uid,'mode':oct(stat.S_IMODE(before.st_mode))}
        active.add(path)
        def descend(nodes):
            output=[]
            for node in nodes:
                if node['name']=='include':
                    if len(node['args'])!=1 or '$' in node['args'][0]:raise ValueError('DYNAMIC_INCLUDE_HOLD')
                    pattern=Path(node['args'][0]);pattern=pattern if pattern.is_absolute() else base/pattern
                    matches=sorted(glob.glob(str(pattern)))
                    if not matches and not glob.has_magic(str(pattern)):raise ValueError('MISSING_INCLUDE')
                    for match in matches:output.extend(expand(match,depth+1))
                else:
                    node['children']=descend(node['children']);output.append(node)
            return output
        result=descend(parse(raw.decode()));active.remove(path);return result
    tree=expand('/etc/nginx/nginx.conf')
    zones=[];servers=[]
    def all_nodes(nodes):
        for n in nodes:
            yield n
            for child in all_nodes(n['children']):yield child
    for node in all_nodes(tree):
        if node['name'] in ('limit_req_zone','limit_conn_zone'):
            for arg in node['args']:
                if arg.startswith('zone='):
                    name=arg[5:].split(':')[0]
                    zones.append({'directive':node['name'],'name':name if re.fullmatch(r'[A-Za-z0-9_-]{1,80}',name) else 'REDACTED'})
    for http in (n for n in tree if n['name']=='http'):
        for server in (n for n in http['children'] if n['name']=='server'):
            nodes=server['children']
            if not any(n['name']=='server_name' and APEX in n['args'] for n in nodes):continue
            record={'listen':[n['args'] for n in nodes if n['name']=='listen'],'roots':[n['args'] for n in nodes if n['name']=='root'],
                    'ssl_paths':{n['name']:n['args'] for n in nodes if n['name'] in ('ssl_certificate','ssl_certificate_key')},
                    'relevant_locations':[],'conflicting_locations':[],'server_auth_controls':[n['name'] for n in nodes if n['name'] in ('auth_request','auth_basic','allow','deny','satisfy')]}
            for location in (n for n in all_nodes(nodes) if n['name']=='location'):
                args=location['args'];match=' '.join(args)
                if args and ('?' in match or '/telegram-webhook/' in match):continue
                literal=args[-1] if args else ''
                relevant=literal=='/' or literal.startswith('/_preview') or 'community-api' in match
                if relevant:
                    safe=match if len(match)<240 else '[REDACTED]'
                    record['relevant_locations'].append({'match':safe,'directives':[c['name'] for c in location['children']]})
                    if literal!='/' and (literal.startswith('/_preview') or 'community-api' in match):record['conflicting_locations'].append(safe)
            servers.append(record)
    return {'status':'SOURCE_INVENTORY_COMPLETE','files':files,'apex_servers':servers,'limit_zones':zones,
            'new_zone_conflict':any(z['name']==ZONE for z in zones),'new_location_conflict':any(s['conflicting_locations'] for s in servers),
            'disk_config_trust':all(v['uid']==0 and not int(v['mode'],8)&0o022 for v in files.values()),
            'loaded_nginx_validation':'NOT_RUN_REQUIRES_PROTECTED_ROOT','raw_config_exported':False,'private_keys_read':False}

def main():
    signal.alarm(110)
    if os.uname().nodename!=EXPECTED_HOST or pwd.getpwuid(os.geteuid()).pw_name!='githubrunner':raise SystemExit('HOLD_WRONG_HOST_OR_IDENTITY')
    output={'source_head':'dd81041042ef3acca031d6b64684941c38ed72ef','audit_comment':6207779869,'host':os.uname().nodename,'uid':os.getuid(),
            'production_mutations':0,'services_started':0,'sudo_commands_executed':[],'state':'PREFLIGHT_PARTIAL_HOLD'}
    versions={}
    for binary in ('/usr/bin/python3',shutil.which('python3')):
        if not binary or binary in versions:continue
        r=run([binary,'-I','-B','-c','import sys,sqlite3,http.cookies,secrets,math; print(__import__("json").dumps({"version":list(sys.version_info[:3]),"executable":sys.executable,"sqlite":sqlite3.sqlite_version,"runtime_language_compatible":sys.version_info>=(3,9)}))'])
        try:versions[binary]=json.loads(r['stdout']) if r['code']==0 else {'status':'UNKNOWN','exit':r['code'],'error_type':r.get('error')}
        except ValueError:versions[binary]={'status':'UNKNOWN_INVALID_OUTPUT'}
    output['python']=versions
    ss=run(['ss','-H','-lnt'])
    output['port_18793']={'status':'LISTENING_CONFLICT' if re.search(r':18793\s',ss['stdout']) else 'NOT_LISTENING_OBSERVED' if ss['code']==0 else 'UNKNOWN','query_exit':ss['code']}
    version=run(['systemctl','--version']);output['systemd_version']=version['stdout'].splitlines()[:2]
    output['cgroup_filesystems']={name:Path(name).exists() for name in ('/sys/fs/cgroup/cgroup.controllers','/sys/fs/cgroup/memory','/sys/fs/cgroup/systemd')}
    fields=('LoadState','ActiveState','SubState','User','MainPID','FragmentPath')
    output['units']={}
    for unit in ('nginx.service','xuanjun-site-hub-preview.service'):
        r=run(['systemctl','show',unit]+['--property='+f for f in fields])
        output['units'][unit]={'query_exit':r['code'],**dict(line.split('=',1) for line in r['stdout'].splitlines() if '=' in line and line.split('=',1)[0] in fields)}
    raw=base64.b64decode(UNIT_BASE64)
    with tempfile.TemporaryDirectory(prefix='pr122-hub-unit-readonly-') as folder:
        path=Path(folder)/'xuanjun-site-hub-preview.service';path.write_bytes(raw)
        r=run(['systemd-analyze','verify',str(path)])
        output['unit_verify']={'unit_sha256':hashlib.sha256(raw).hexdigest(),'exit':r['code'],'diagnostics':(r['stderr']+r['stdout'])[:6000],
                               'runtime_sandbox_effectiveness':'NOT_RUN_NO_SERVICE_STARTED'}
    try:output['nginx']=nginx_source()
    except Exception as e:output['nginx']={'status':'UNKNOWN_CONFIG_SOURCE','error_type':type(e).__name__,'reason':str(e) if isinstance(e,ValueError) else 'CONFIG_NOT_READABLE_OR_UNAVAILABLE','private_keys_read':False,'raw_config_exported':False}
    output['paths']=[metadata(p,p.endswith('pr122_website_release.py')) for p in (
        '/var/www/wenwenwenyiyiyi.work','/var/www/wenwenwenyiyiyi.work/current','/var/www/wenwenwenyiyiyi.work/releases','/var/www/wenwenwenyiyiyi.work/transactions',
        '/etc/nginx','/etc/nginx/nginx.conf','/etc/systemd/system','/var/lib/xuanjun-site-hub-preview','/usr/local/libexec/pr122_website_release.py','/var/backups')]
    policy=run(['sudo','-n','-l'])
    output['sudo_policy']={'query_exit':policy['code'],'policy_visible':policy['code']==0,
        'general_nopasswd_all_reported':bool(re.search(r'NOPASSWD:\s*ALL(?:\s|$)',policy['stdout'])) if policy['code']==0 else None,
        'known_portal_log_helper_reported':'/usr/local/sbin/xuanjun-pr122-portal-logfix-v1' in policy['stdout'] if policy['code']==0 else None,
        'combined_hub_installer':'NOT_REGISTERED_OR_NOT_PROVEN','raw_policy_exported':False}
    disk=shutil.disk_usage('/var/www');output['disk']={'free_bytes':disk.free,'total_bytes':disk.total}
    output['remaining_gate']=['Protected combined execution and root-private backup/rollback admission','Loaded Nginx -t/source/include confirmation under protected root','Actual runtime identity and sandbox effects after explicit installation approval','Separate production release decision and real HTTPS acceptance']
    print('PR122_SITE_HUB_TARGET_PREFLIGHT='+json.dumps(output,sort_keys=True),flush=True)

if __name__=='__main__':main()
