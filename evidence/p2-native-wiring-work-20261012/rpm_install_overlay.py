"""Integrate signed RPM payloads and enforce quiescence before runtime provisioning."""
import hashlib,json,pathlib,sys
r=pathlib.Path(sys.argv[1]);here=pathlib.Path(__file__).resolve().parent;mp=r/'deploy/integration-manifest.json';m=json.loads(mp.read_text())
paths=('stage1/p2_fixed_host_runtime.py','stage1/p2_install_entrypoint.py','stage1/p2_prerequisites.py');texts={}
for rel in paths:
 raw=(r/rel).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=m['files'][rel]:raise ValueError('RPM_INPUT_MANIFEST_HASH')
 texts[rel]=raw.decode()
def replace(rel,old,new):
 if texts[rel].count(old)!=1:raise ValueError('RPM_OVERLAY_ANCHOR_'+rel)
 texts[rel]=texts[rel].replace(old,new)
a,b,c=paths
replace(a,'from p2_sandbox_profile import SandboxProfile','from p2_sandbox_profile import SandboxProfile\nfrom p2_rpm_prerequisites import RpmPrerequisites')
replace(a,'from p2_bootstrap_files import BootstrapFiles','from p2_bootstrap_files import BootstrapFiles,private_read')
anchor="        SandboxProfile(self.directory).prepare(runtime.get('sandbox_policy'))"
replace(a,anchor,anchor+"\n        RpmPrerequisites(self.directory).prepare(runtime.get('rpm'),runtime['prerequisites'])")
replace(a,'    def provision(self, release, runtime):',"    def prepare_prerequisites(self,runtime):\n        self._authority()\n        return self.prerequisites.apply(runtime['prerequisites'])\n\n    def restore_prerequisites(self,runtime):\n        if os.path.lexists(self.receipt_path):\n            receipt=json.loads(private_read(self.prerequisites.path).decode())\n            if receipt.get('restored') is not True:\n                raise ValueError('HOLD_PROVISION_RECONCILIATION_BEFORE_NSS_ROLLBACK')\n        return self.prerequisites.rollback(runtime['prerequisites'])\n\n    def provision(self, release, runtime):")
replace(a,"            self.prerequisites.apply(runtime['prerequisites'])", "            RpmPrerequisites(self.directory).apply(runtime.get('rpm'),runtime['prerequisites'])")
# Stop/enable/install the plugin offline while the old parent remains masked.
start=texts[a].index("            self._start_gateway()\n            inspected=",texts[a].index('    def _install_plugin'))
end=texts[a].index('        except Exception:',start)
block=texts[a][start:end]
inspect=block.replace('            self._start_gateway()\n','',1)
texts[a]=texts[a][:start]+texts[a][end:]
replace(a,"try:self._rollback_plugin(runtime,restart=True)","try:self._rollback_plugin(runtime,restart=False)")
method="    def _verify_plugin_runtime(self,runtime):\n"+'\n'.join(line[4:] for line in inspect.rstrip().split('\n'))+'\n\n'
replace(a,'    def _rollback_plugin(self,runtime,restart):',method+'    def _rollback_plugin(self,runtime,restart):')
replace(a,"        self._start_gateway()\n        for service in ALLOWED_SERVICES:", "        self._start_gateway()\n        self._verify_plugin_runtime(runtime)\n        for service in ALLOWED_SERVICES:")
replace(a,"            self._command(['/usr/bin/systemctl', 'reload', 'nginx.service'])\n            self._command(['/usr/bin/systemctl', 'is-active', '--quiet',", "            self._command(['/usr/bin/systemctl', 'start', 'nginx.service'])\n            self._command(['/usr/bin/systemctl', 'is-active', '--quiet',")
replace(a,"        for service in STOP_SERVICES:","        if any(item['target'].startswith('/etc/nginx/') for item in runtime.get('provisioning',[])):\n            self._command(['/usr/bin/systemctl','stop','nginx.service'])\n        for service in STOP_SERVICES:")
token='ALLOWED_SERVICES+(GATEWAY_SERVICE,)'
if texts[a].count(token)!=5:raise ValueError('NGINX_BOOT_SCOPE_ANCHORS')
texts[a]=texts[a].replace(token,'self._boot_units(binding)')
replace(a,"        value=self._boot_read(self._boot_binding())", "        binding=self._boot_binding();value=self._boot_read(binding)")
helper="    def _boot_units(self,binding):\n        raw,info=_read_regular(self.receipt_path)\n        if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600 or _digest_bytes(raw)!=binding:\n            raise ValueError('BOOT_PROVISION_CHANGED')\n        value=json.loads(raw.decode());targets=value.get('targets',[])\n        if not isinstance(targets,list) or any(not isinstance(t,dict) or not isinstance(t.get('target'),str) for t in targets):\n            raise ValueError('BOOT_TARGET_SCOPE')\n        extra=('nginx.service',) if any(t['target'].startswith('/etc/nginx/') for t in targets) else ()\n        return tuple(ALLOWED_SERVICES)+(GATEWAY_SERVICE,)+extra\n\n"
replace(a,'    def _boot_read(self, binding):',helper+'    def _boot_read(self, binding):')
replace(a,"        SandboxProfile(self.directory).rollback_check()\n        self._restore_boot()", "        SandboxProfile(self.directory).rollback_check()\n        RpmPrerequisites(self.directory).rollback_rows()\n        self._restore_boot()")
replace(a,"        self.prerequisites.rollback(receipt['prerequisites'])", "        RpmPrerequisites(self.directory).rollback()\n        self.prerequisites.rollback(receipt['prerequisites'])")
restore_start=texts[a].index('    def restore(')
tail=texts[a][restore_start:]
old="        if any(item['target'].startswith('/etc/nginx/')\n               for item in receipt['targets']):\n            self._command(['/usr/sbin/nginx', '-t'])\n            self._command(['/usr/bin/systemctl', 'reload', 'nginx.service'])\n        self._start_gateway()\n"
if tail.count(old)!=1:raise ValueError('RPM_RESTORE_NO_RESTART_ANCHOR')
texts[a]=texts[a][:restore_start]+tail.replace(old,'')
replace(b,"{'release_directory','provisioning','services','prerequisites','plugin','bootstrap','publisher','sandbox_policy'})", "{'release_directory','provisioning','services','prerequisites','plugin','bootstrap','publisher','sandbox_policy'},\n                                    {'release_directory','provisioning','services','prerequisites','plugin','bootstrap','publisher','sandbox_policy','rpm'})")
replace(b,"    plugin=runtime['plugin']", "    if 'rpm' in runtime:\n        value=runtime['rpm']\n        if (not isinstance(value,dict) or set(value)!={'path','sha256'}\n                or not isinstance(value['path'],str) or not value['path'].startswith('/var/lib/xuanjun-p2-preparation/')\n                or not isinstance(value['sha256'],str) or re.fullmatch(r'[0-9a-f]{64}',value['sha256']) is None):\n            raise ValueError('INVALID_RPM_REFERENCE')\n    plugin=runtime['plugin']")
# Minimal identity/directory bootstrap precedes ledger staging; runtime effects follow quiescence.
replace(b,"        prepared = None\n        try:", "        prepared = None\n        prerequisites_requested = False\n        try:")
begin=texts[b].index("            provision = self.runtime.provision(release, plan['runtime'])",texts[b].index('    def execute('))
end=texts[b].index("            value = plan['activation']",begin)
provision=texts[b][begin:end]
texts[b]=texts[b][:begin]+"            prerequisites_requested = True\n            self.runtime.prepare_prerequisites(plan['runtime'])\n\n"+texts[b][end:]
anchor="            # Services require ACTIVE; prove the staged DB is readable first."
replace(b,anchor,provision+anchor)
replace(b,"                    rollback.append('PROVISIONING_RESTORED')\n                if legacy_effect:", "                    rollback.append('PROVISIONING_RESTORED')\n                elif prerequisites_requested:\n                    self.runtime.restore_prerequisites(plan['runtime'])\n                    rollback.append('PREREQUISITES_RESTORED')\n                if legacy_effect:")
# Preserve the complete original prerequisite journal on duplicate requests.
replace(c,"        self.preflight(plan)\n        receipt={'schema':1", "        if os.path.lexists(self.path):raise ValueError('HOLD_EXISTING_PREREQUISITE_TRANSACTION')\n        self.preflight(plan)\n        receipt={'schema':1")
replace(c,"or not isinstance(plan['groups'],dict) or set(plan['groups'])!=GROUPS\n            or not isinstance(plan['users'],dict) or set(plan['users'])!=USERS", "or not isinstance(plan['groups'],dict) or set(plan['groups']) not in (GROUPS,GROUPS|{'nginx'})\n            or not isinstance(plan['users'],dict) or set(plan['users']) not in (USERS,USERS|{'nginx'})\n            or ('nginx' in plan['groups'])!=('nginx' in plan['users'])")
replace(c,"or item['groups']!= ([] if name=='xj_codex_worker' else ['xuanjun-control-db'])):", "or item['groups']!= ([] if name in ('xj_codex_worker','nginx') else ['xuanjun-control-db'])):")
replace(c,"        uids.append(item['uid'])", "        if name=='nginx' and (item['uid'],item['gid'],item['home'])!=(1008,1008,'/var/lib/xuanjun-development/nginx-home'):\n            raise ValueError('FIXED_NGINX_IDENTITY_REQUIRED')\n        uids.append(item['uid'])")
replace(c,"        if receipt.get('plan_sha256')!=digest(plan) or any", "        if receipt.get('plan_sha256')==digest(plan) and receipt.get('restored') is True:return {'restored':True,'effects':0}\n        if receipt.get('plan_sha256')!=digest(plan) or any")
replace(c,"            elif kind=='group':self.command(['/usr/sbin/groupdel',i['name']])", "            elif kind=='group':\n                try:g=grp.getgrnam(i['name'])\n                except KeyError:continue # userdel can already remove its matching private group.\n                if g.gr_gid!=i['gid']:raise ValueError('HOLD_CREATED_GROUP_CHANGED')\n                self.command(['/usr/sbin/groupdel',i['name']])")
replace(c,"        return {'restored':True,'effects':len(actions)}", "        receipt['restored']=True;_atomic_receipt(self.path,receipt)\n        return {'restored':True,'effects':len(actions)}")
rel='stage1/p2_rpm_prerequisites.py'
if (r/rel).exists():raise ValueError('RPM_MODULE_PRESENT')
texts[rel]=(here/'p2_rpm_prerequisites.py').read_text()
for rel,text in texts.items():(r/rel).write_text(text);m['files'][rel]=hashlib.sha256(text.encode()).hexdigest()
mp.write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');print('RPM_QUIESCENCE_ORDER_OFFLINE_PLUGIN_AND_RESTORE_HOOKS=PASS; INSTALL=NO')
