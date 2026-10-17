"""Bounded read-only migration inventory; no raw unit, cron, env or key output."""
import ast
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess

HOSTS={'iZmj7a5kwr75qc1tul4kf9Z':'korea','iZvt5t8tlrm8oiZ':'domestic','iZ6wee8q9z4t03hvqumwfhZ':'tokyo'}
UNITS=('secure-secrets-portal.service','xuanjun-wecom-customer-contact.service',
 'xuanjun-wecom-customer-service.service','xuanjun-wecom-novel-ingress.service',
 'provider-neutral-tunnel.service','provider-neutral-tokyo-tunnel.service',
 'provider-neutral-domestic-bridge.service','domestic-model-rpc-tunnel.service',
 'korea-novel-model-rpc-tunnel.service','restricted-rpc-openai-shim.service',
 'tokyo-restricted-model-executor.service','xj-tokyo-vpn.service',
 'finance-collection-sync.timer','owner-commercial-ledger-sync.timer',
 'billing-operations-weekly-settlement.timer','billing-operations-weekly-final-invoice.timer')


def run(args):
    try:
        r=subprocess.run(args,capture_output=True,text=True,timeout=12)
        return r.returncode,r.stdout[:262144]
    except Exception:
        return -1,''


def read(path,limit=262144):
    p=Path(path)
    for parent in p.parents:
        if parent.is_symlink():raise RuntimeError('SYMLINK_PARENT')
    s=p.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_size>limit:raise RuntimeError('FILE_SHAPE')
    fd=os.open(str(p),os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        if (before.st_dev,before.st_ino)!=(s.st_dev,s.st_ino):raise RuntimeError('FILE_REPLACED')
        chunks=[];remaining=limit+1
        while remaining:
            chunk=os.read(fd,remaining)
            if not chunk:break
            chunks.append(chunk);remaining-=len(chunk)
        b=b''.join(chunks);after=os.fstat(fd)
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns) or len(b)!=after.st_size:raise RuntimeError('FILE_CHANGED')
        return b
    finally:os.close(fd)


def identity(path):
    try:
        p=Path(path);s=p.lstat()
        out={'path':str(p),'uid':s.st_uid,'gid':s.st_gid,'mode':oct(stat.S_IMODE(s.st_mode)),'regular':stat.S_ISREG(s.st_mode),'symlink':stat.S_ISLNK(s.st_mode)}
        if out['regular']:
            b=read(p);out.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
        return out
    except Exception as e:return {'path':str(path),'error':type(e).__name__}


def command_projection(value):
    try:tokens=shlex.split(value)
    except ValueError:return {'status':'PARSE_HOLD'}
    out={'token_count':len(tokens),'forwards':[]}
    if tokens:
        exe=tokens[0];out['executable']=exe if re.fullmatch(r'/[A-Za-z0-9_./-]{1,180}',exe) else 'WITHHELD'
    for i,t in enumerate(tokens):
        if t in ('-L','-R','-D') and i+1<len(tokens):
            v=tokens[i+1];out['forwards'].append({'flag':t,'binding':v if re.fullmatch(r'[A-Za-z0-9_.:\[\]-]{1,180}',v) else 'DYNAMIC_OR_WITHHELD'})
        elif t.startswith(('-L','-R','-D')) and len(t)>2:
            v=t[2:];out['forwards'].append({'flag':t[:2],'binding':v if re.fullmatch(r'[A-Za-z0-9_.:\[\]-]{1,180}',v) else 'DYNAMIC_OR_WITHHELD'})
        elif re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,39}@[A-Za-z0-9_.-]{1,100}',t):out['ssh_peer']=t
        elif t=='-m' and i+1<len(tokens) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]{1,140}',tokens[i+1]):out['module']=tokens[i+1]
        elif t.startswith('/opt/trading-system/') and re.fullmatch(r'/[A-Za-z0-9_./-]{1,240}',t) and t.endswith(('.py','.sh')):out.setdefault('entry_paths',[]).append(t)
    return out


def unit(name):
    props=('LoadState','ActiveState','SubState','MainPID','User','Group','WorkingDirectory','FragmentPath','DropInPaths','After','Wants','Requires')
    rc,text=run(['/usr/bin/systemctl','show',name,'--property='+','.join(props),'--no-pager'])
    data={}
    for line in text.splitlines():
        k,sep,v=line.partition('=')
        if sep and k in props:data[k]=v
    for key in ('After','Wants','Requires'):
        if key in data:data[key]=' '.join(v for v in data[key].split() if v in UNITS or v in ('docker.service','network-online.target','sshd.service') or v.startswith(('xuanjun','provider-neutral','tokyo-','korea-','domestic-','restricted-')))
    row={'unit':name,**data}
    f=data.get('FragmentPath')
    if f:
        row['fragment']=identity(f)
        try:
            b=read(f);commands=[];env_names=set()
            text=b.decode('utf-8','replace').replace('\\\n',' ')
            for line in text.splitlines():
                if line.startswith('ExecStart='):commands.append(command_projection(line.partition('=')[2]))
                if line.startswith('Environment='):
                    env_names.update(re.findall(r'(?:^|[\s\"\x27])([A-Z_][A-Z0-9_]*)=',line.partition('=')[2]))
            row['command_projection']=commands;row['environment_names']=sorted(env_names)
        except Exception as e:row['fragment_read_error']=type(e).__name__
    # Detailed dependency lists only matter for the selected runtime services.
    if name.endswith('.timer'):
        for p in ('After','Wants','Requires'):row.pop(p,None)
    return row


def cron():
    rows=[]
    paths=[Path('/etc/crontab')]
    paths+=list(Path('/etc/cron.d').glob('*'))[:40]
    for root in ('/var/spool/cron','/var/spool/cron/crontabs'):
        for user in ('root','admin'):
            p=Path(root)/user
            if p.exists():paths.append(p)
    for p in paths:
        if not p.is_file():continue
        row=identity(p)
        try:
            b=read(p);lines=[l for l in b.decode('utf-8','replace').splitlines() if l.strip() and not l.lstrip().startswith('#')]
            row['noncomment_lines']=len(lines)
            row['project_script_paths']=sorted(set(re.findall(r'/opt/trading-system/[A-Za-z0-9_./-]+\.(?:py|sh)',b.decode('utf-8','replace'))))[:20]
            row['command_values_disclosed']=False
        except Exception as e:row['read_error']=type(e).__name__
        rows.append(row)
    return rows


def nginx_routes():
    paths=[Path('/etc/nginx/nginx.conf')]
    paths+=list(Path('/etc/nginx/conf.d').glob('*.conf'))[:40]
    rows=[]
    for p in paths:
        if not p.is_file():continue
        row=identity(p);routes=[]
        try:
            for line in read(p).decode('utf-8','replace').splitlines():
                m=re.match(r'^\s*(listen|server_name|proxy_pass|root|include)\s+([^;]+);',line)
                if not m:continue
                key,value=m.groups()
                if key=='server_name' and re.fullmatch(r'[A-Za-z0-9_.* -]{1,250}',value):routes.append({'directive':key,'value':value})
                elif key=='listen' and re.fullmatch(r'[A-Za-z0-9_.:\[\] =-]{1,120}',value):routes.append({'directive':key,'value':value})
                elif key in ('root','include') and re.fullmatch(r'/[A-Za-z0-9_./*${}-]{1,240}',value):routes.append({'directive':key,'value':value})
                elif key=='proxy_pass':
                    from urllib.parse import urlsplit
                    try:
                        u=urlsplit(value)
                        if u.scheme in ('http','https') and u.hostname and not u.username and not u.password and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',u.hostname):routes.append({'directive':key,'host':u.hostname,'port':u.port or (443 if u.scheme=='https' else 80),'scheme':u.scheme})
                    except ValueError:pass
            row['routes']=routes[:24]
        except Exception as e:row['read_error']=type(e).__name__
        rows.append(row)
    return rows[:30]


def main():
    host=os.uname().nodename
    assert os.geteuid()==0 and host in HOSTS
    rows=[unit(n) for n in UNITS]
    rc,ports=run(['/usr/sbin/ss','-lntpH'])
    listeners=[]
    wanted={443,18080,18770,18780,18781,18761,18443,19443,19444}
    for line in ports.splitlines():
        parts=line.split()
        if len(parts)<4:continue
        local=parts[3]
        try:port=int(local.rsplit(':',1)[1])
        except ValueError:continue
        if port not in wanted:continue
        listeners.append({'local':local,'processes':[{'name':m[0],'pid':int(m[1])} for m in re.findall(r'\("([A-Za-z0-9_.-]+)",pid=(\d+)',line)]})
    rc,docker=run(['/usr/bin/docker','ps','--format','{{.Names}}\t{{.Image}}\t{{.Ports}}'])
    containers=[]
    if rc==0:
        for line in docker.splitlines()[:12]:
            parts=line.split('\t')
            if len(parts)==3 and all(re.fullmatch(r'[A-Za-z0-9_.:/<> ,=-]{0,300}',p) for p in parts):containers.append(dict(zip(('name','image','ports'),parts)))
    rc,active=run(['/usr/bin/systemctl','list-units','--type=service','--state=running','--no-legend','--plain','--no-pager'])
    running=[l.split()[0] for l in active.splitlines() if l.split() and re.fullmatch(r'[A-Za-z0-9_.@:-]+\.service',l.split()[0])][:100]
    client_refs=[]
    project=Path('/opt/trading-system') if HOSTS[host]=='tokyo' else Path('/var/lib/xuanjun-pr99-s07-isolated-start-v4/rootfs/opt/trading-system')
    if HOSTS[host]!='korea':
        for rel in ('ai_service/telegram_customer_service_canary.py','ai_service/wecom_customer_service.py'):
            try:
                b=read(project/rel);tree=ast.parse(b);addresses=set()
                for node in ast.walk(tree):
                    if isinstance(node,ast.Constant) and isinstance(node.value,str):
                        try:addresses.add(str(ipaddress.ip_address(node.value)))
                        except ValueError:pass
                client_refs.append({'source':rel,'sha256':hashlib.sha256(b).hexdigest(),'literal_ip_addresses':sorted(addresses)})
            except Exception as e:client_refs.append({'source':rel,'error':type(e).__name__})
    result={'attempt_nonce':globals().get('ATTEMPT_NONCE'),'status':'S08_ROOT_READONLY_RUNTIME_CLOSURE','host':HOSTS[host],'hostname':host,'units':rows,'listeners':listeners,'cron':cron(),'nginx':nginx_routes(),'containers':containers,'running_service_names':running,'client_refs':client_refs,'collected_at_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'uid':os.geteuid(),'service_actions':0,'database_opened':False,'business_api_requests':0,'secret_values_disclosed':False}
    encoded=json.dumps(result,sort_keys=True)
    if len(encoded.encode())>22000:raise RuntimeError('PUBLIC_RECEIPT_SIZE_LIMIT')
    print(encoded,flush=True)


if __name__=='__main__':
    try:main()
    except Exception as e:
        print(json.dumps({'status':'HOLD','exception':type(e).__name__,'code':str(e) if re.fullmatch(r'[A-Z0-9_]{1,160}',str(e)) else 'PRIVATE_DETAIL_WITHHELD'}),flush=True)
        raise SystemExit(2)
