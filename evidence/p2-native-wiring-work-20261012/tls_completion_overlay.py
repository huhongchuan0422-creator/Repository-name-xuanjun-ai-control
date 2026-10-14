"""Integrate reviewed lifecycle candidate; effects occur only in install."""
import hashlib,json,pathlib,sys
r=pathlib.Path(sys.argv[1]);here=pathlib.Path(__file__).resolve().parent;mp=r/'deploy/integration-manifest.json';m=json.loads(mp.read_text())
def load(p):
 b=(r/p).read_bytes()
 if hashlib.sha256(b).hexdigest()!=m['files'][p]:raise ValueError('TLS_OVERLAY_INPUT')
 return b.decode()
def rep(s,a,b):
 if s.count(a)!=1:raise ValueError('TLS_OVERLAY_ANCHOR_'+a[:60])
 return s.replace(a,b)
p='stage1/p2_fixed_host_runtime.py';s=load(p)
if s.count("self._command(['/usr/sbin/nginx', '-t'])")!=2:raise ValueError('NGINX_CHECK_CALLSITES')
s=rep(s,"self._command(['/usr/sbin/nginx', '-t'])","self._command(['/usr/sbin/nginx', '-t', '-c', '/etc/xuanjun-development/nginx-main.conf'])") if s.count("self._command(['/usr/sbin/nginx', '-t'])")==1 else s.replace("self._command(['/usr/sbin/nginx', '-t'])","self._command(['/usr/sbin/nginx', '-t', '-c', '/etc/xuanjun-development/nginx-main.conf'])")
s=rep(s,'import p2_auxiliary_isolation as Auxiliary','import p2_auxiliary_isolation as Auxiliary\nfrom p2_tls_lifecycle import TlsLifecycle,TIMER as TLS_TIMER,SERVICE as TLS_SERVICE')
s=rep(s,"        self.prerequisites.preflight(runtime['prerequisites'])","        if 'tls_renewal' in runtime:TlsLifecycle(self.directory).prepare(runtime['tls_renewal'])\n        self.prerequisites.preflight(runtime['prerequisites'])")
s=rep(s,"        if 'auxiliary_isolation' in runtime:receipt['auxiliary_isolation']=runtime['auxiliary_isolation']","        if 'auxiliary_isolation' in runtime:receipt['auxiliary_isolation']=runtime['auxiliary_isolation']\n        if 'tls_renewal' in runtime:receipt['tls_renewal']=runtime['tls_renewal']")
s=rep(s,"        create_dropin_parent=self._dropin_parent_state()", "        if 'tls_renewal' in runtime:\n            tls_value=TlsLifecycle(self.directory).prepare(runtime['tls_renewal'])\n            configs=[item for item in prepared if item['target']=='/etc/xuanjun-development/tls-renewal.json']\n            if len(configs)!=1 or json.loads(configs[0]['data'].decode())!=tls_value:raise ValueError('TLS_RENDERED_CONFIG_BINDING')\n            required={'/etc/systemd/system/'+TLS_TIMER,'/etc/systemd/system/'+TLS_SERVICE,'/etc/systemd/system/nginx.service','/etc/xuanjun-development/nginx-main.conf'}\n            if not required.issubset({item['target'] for item in prepared}):raise ValueError('TLS_TIMER_SERVICE_BINDING')\n        create_dropin_parent=self._dropin_parent_state()")
s=rep(s,"            PublisherBootstrap(self.directory).apply(runtime.get('publisher'))","            PublisherBootstrap(self.directory).apply(runtime.get('publisher'))\n            if 'tls_renewal' in runtime:TlsLifecycle(self.directory).apply(runtime['tls_renewal'])")
s=rep(s,"        return tuple(ALLOWED_SERVICES)+(GATEWAY_SERVICE,)+extra","        if any(t['target']=='/etc/systemd/system/'+TLS_TIMER for t in targets):extra+=(TLS_TIMER,)\n        return tuple(ALLOWED_SERVICES)+(GATEWAY_SERVICE,)+extra")
s=rep(s,"        return {'services_active': True}\n\n    def stop_new", "        if 'tls_renewal' in runtime:\n            self._command(['/usr/bin/systemctl','start',TLS_TIMER])\n            self._command(['/usr/bin/systemctl','is-active','--quiet',TLS_TIMER])\n        return {'services_active': True}\n\n    def stop_new")
s=rep(s,"    def stop_new(self, runtime):\n        self._authority()", "    def stop_new(self, runtime):\n        self._authority()\n        if 'tls_renewal' in runtime:\n            self._command(['/usr/bin/systemctl','stop',TLS_TIMER])\n            self._command(['/usr/bin/systemctl','stop',TLS_SERVICE])")
s=rep(s,"        BootstrapFiles(self.directory).rollback_rows()", "        if 'tls_renewal' in receipt:TlsLifecycle(self.directory).rollback_check()\n        BootstrapFiles(self.directory).rollback_rows()")
s=rep(s,"        RpmPrerequisites(self.directory).rollback()", "        if 'tls_renewal' in receipt:TlsLifecycle(self.directory).rollback()\n        RpmPrerequisites(self.directory).rollback()")
s=rep(s,'class FixedHostRuntime(object):','def _dropin_rollback_present(plugin_receipt, prepared):\n    """The legacy receipt records creation intent, not completed mkdir.\n\n    Missing owned directory is a no-effect state only when EVERY planned target\n    still has its authenticated original state. Never create a directory merely\n    to let rollback pass. Any installed/drifted target keeps the transaction HOLD.\n    """\n    if not plugin_receipt[\'dropin_parent_created\']:\n        return False\n    if not os.path.lexists(GATEWAY_DROPIN_DIR):\n        for item, unused in prepared:\n            path, previous = item[\'target\'], item[\'previous\']\n            if previous is None:\n                if os.path.lexists(path):\n                    raise ValueError(\'HOLD_MISSING_DROPIN_WITH_TARGET_EFFECT\')\n            elif previous.get(\'masked\') is True:\n                if not Auxiliary.is_mask(path):\n                    raise ValueError(\'HOLD_MISSING_DROPIN_WITH_MASK_EFFECT\')\n            else:\n                data, info = _read_regular(path)\n                if (_digest_bytes(data), stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid) != (\n                        previous[\'sha256\'], previous[\'mode\'], previous[\'uid\'], previous[\'gid\']):\n                    raise ValueError(\'HOLD_MISSING_DROPIN_WITH_TARGET_DRIFT\')\n        return False\n    info = os.lstat(GATEWAY_DROPIN_DIR)\n    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_gid != 0\n            or stat.S_IMODE(info.st_mode) != 0o755):\n        raise ValueError(\'HOLD_GATEWAY_DROPIN_DIRECTORY_CHANGED\')\n    return True\n\n\nclass FixedHostRuntime(object):')
s=rep(s,"        if plugin_receipt['dropin_parent_created']:\n            if not os.path.lexists(GATEWAY_DROPIN_DIR):\n                raise ValueError('HOLD_GATEWAY_DROPIN_DIRECTORY_MISSING')\n            dropin_parent=os.lstat(GATEWAY_DROPIN_DIR)\n            if (not stat.S_ISDIR(dropin_parent.st_mode) or dropin_parent.st_uid!=0\n                    or dropin_parent.st_gid!=0 or stat.S_IMODE(dropin_parent.st_mode)!=0o755):\n                raise ValueError('HOLD_GATEWAY_DROPIN_DIRECTORY_CHANGED')\n",'        dropin_present = _dropin_rollback_present(plugin_receipt, prepared)\n')
s=rep(s,"        if plugin_receipt['dropin_parent_created']:\n            self._remove_created_dropin_parent()",'        if dropin_present:\n            self._remove_created_dropin_parent()')
texts={p:s}
p='stage1/p2_install_entrypoint.py';s=load(p)
s=rep(s,"set(runtime)-{'legacy_cutover','auxiliary_isolation'}","set(runtime)-{'legacy_cutover','auxiliary_isolation','tls_renewal'}")
s=rep(s,"    if 'bootstrap' in runtime:","    if 'tls_renewal' in runtime:\n        ref=runtime['tls_renewal']\n        if not isinstance(ref,dict) or set(ref)!={'path','sha256'} or not _canonical(ref['path']) or not SHA256.fullmatch(ref['sha256']):raise ValueError('TLS_RENEWAL_REFERENCE')\n    if 'bootstrap' in runtime:")
texts[p]=s
texts.update({'deploy/p2-nginx-main.conf':'''user nginx;
worker_processes auto;
pid /run/nginx.pid;
error_log /var/log/nginx/error.log warn;
events { worker_connections 1024; }
http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    access_log /var/log/nginx/access.log;
    sendfile on;
    keepalive_timeout 65;
    include /etc/nginx/conf.d/xuanjun-p2-owner.conf;
}
''',
 'deploy/p2-nginx.service':'''[Unit]
Description=Xuanjun P2 HTTPS nginx with fixed reviewed configuration
After=network-online.target
Wants=network-online.target
[Service]
Type=forking
PIDFile=/run/nginx.pid
ExecStartPre=/usr/sbin/nginx -t -c /etc/xuanjun-development/nginx-main.conf
ExecStart=/usr/sbin/nginx -c /etc/xuanjun-development/nginx-main.conf
ExecReload=/bin/kill -s HUP $MAINPID
KillSignal=SIGQUIT
TimeoutStopSec=30
KillMode=mixed
PrivateTmp=true
[Install]
WantedBy=multi-user.target
'''})
texts.update({'stage1/p2_tls_lifecycle.py':(here/'p2_tls_lifecycle.py').read_text(),
 'scripts/uk-p2-tls-renew.py':"#!/usr/bin/env python3\nimport os,sys\nsys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'stage1'))\nfrom p2_tls_lifecycle import renew\nif __name__=='__main__':renew()\n",
 'deploy/p2-tls-renewal.json.template':'''{"schema":1,"domain":"uk.wenwenwenyiyiyi.work","root":"/var/lib/xuanjun-development/tls-acme","transaction_directory":"@@TRANSACTION_DIRECTORY@@","transaction_id":"@@TRANSACTION_ID@@","instance":"@@INSTANCE@@","generation":@@GENERATION@@,"ledger_uuid":"@@LEDGER_UUID@@","release_sha256":"@@PACKAGE_SHA256@@","accept_acme_terms":true}
''',
 'deploy/xuanjun-p2-tls-renew.service':'''[Unit]
Description=Xuanjun P2 fixed-domain ACME renewal with ACTIVE gate
After=network-online.target nginx.service
Wants=network-online.target
[Service]
Type=oneshot
User=root
UMask=0077
ExecStart=/usr/bin/python3 -I -B @@RELEASE@@/scripts/uk-p2-tls-renew.py
TimeoutStartSec=300
KillMode=control-group
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/xuanjun-development/tls-acme /var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5 /run/xuanjun-p2-install.lock
''',
 'deploy/xuanjun-p2-tls-renew.timer':'''[Unit]
Description=Xuanjun P2 certificate renewal schedule
[Timer]
OnActiveSec=5min
OnUnitActiveSec=12h
RandomizedDelaySec=900
Unit=xuanjun-p2-tls-renew.service
[Install]
WantedBy=timers.target
'''})
for p,text in texts.items():
 if p.endswith('.py'):compile(text,p,'exec')
 (r/p).write_text(text);m['files'][p]=hashlib.sha256(text.encode()).hexdigest()
mp.write_text(json.dumps(m,sort_keys=True,indent=2)+'\n')
print('TLS_ISSUANCE_DRYRUN_ACTIVE_TIMER_AND_ROLLBACK_CANDIDATE_WIRED_INSTALL_NOT_RUN')

