import hashlib,json,pathlib,sys
r=pathlib.Path(sys.argv[1]);here=pathlib.Path(__file__).resolve().parent
m_path=r/'deploy/integration-manifest.json';m=json.loads(m_path.read_text())
def load(rel):
 raw=(r/rel).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=m['files'][rel]:raise ValueError('ADOPTION_INPUT_MANIFEST')
 return raw.decode()
a='stage1/legacy_host_adapter.py';s=load(a)
old="    def preflight(self, plan):\n        self._authority()"
new=old+"\n        if 'legacy_isolation' in plan:\n            from p2_legacy_adoption import bind\n            return bind(self,plan)"
if s.count(old)!=1:raise ValueError('ADOPTION_PREFLIGHT_ANCHOR')
s=s.replace(old,new)
old="    def stop_and_inhibit(self, bindings):\n        self._authority()"
new=old+"\n        if hasattr(self,'_adoption_plan'):\n            if bindings!=self._adoption_plan['legacy_bindings']:raise ValueError('ADOPTION_STOP_BINDINGS_CHANGED')\n            from p2_legacy_adoption import bind\n            bind(self,self._adoption_plan)\n            return # Existing isolated transaction: zero repeated systemd effects."
if s.count(old)!=1:raise ValueError('ADOPTION_STOP_ANCHOR')
s=s.replace(old,new)
b='stage1/ledger_cutover_transaction.py';t=load(b)
old="if not isinstance(plan, dict) or set(plan) != required or plan['schema'] != 1:"
new="if not isinstance(plan, dict) or set(plan) not in (required,required|{'legacy_isolation'}) or plan['schema'] != 1:"
if t.count(old)!=1:raise ValueError('ADOPTION_CUTOVER_ANCHOR')
t=t.replace(old,new)
c='stage1/p2_fixed_host_runtime.py';u=load(c)
old="""        result=self.run(['/usr/bin/systemctl','is-active','--quiet',GATEWAY_SERVICE],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=False)
        if result.returncode!=0:raise ValueError('GATEWAY_MUST_BE_ACTIVE_BEFORE_P2')"""
if u.count(old)!=1:raise ValueError('ADOPTED_GATEWAY_GUARD_ANCHOR')
u=u.replace(old,"        self._verify_gateway_preflight(runtime)")
helper="""    def _verify_gateway_preflight(self,runtime):
        if 'legacy_cutover' in runtime:
            if not isinstance(runtime['legacy_cutover'],dict) or 'legacy_isolation' not in runtime['legacy_cutover']:
                raise ValueError('ADOPTED_GATEWAY_REFERENCE_REQUIRED')
            from legacy_host_adapter import LegacyHostAdapter
            if LegacyHostAdapter(self.directory).preflight(runtime['legacy_cutover']) is not True:
                raise ValueError('ADOPTED_GATEWAY_PREFLIGHT_FAILED')
            return
        result=self.run(['/usr/bin/systemctl','is-active','--quiet',GATEWAY_SERVICE],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=False)
        if result.returncode!=0:raise ValueError('GATEWAY_MUST_BE_ACTIVE_BEFORE_P2')

"""
u=u.replace('    def preflight(self, runtime, auth, tls):',helper+'    def preflight(self, runtime, auth, tls):')
e='stage1/p2_install_entrypoint.py';v=load(e)
old='or set(runtime) not in ('
if v.count(old)!=1:raise ValueError('ADOPTED_RUNTIME_SCHEMA_ANCHOR')
v=v.replace(old,"or set(runtime)-{'legacy_cutover'} not in (")
anchor="    if 'bootstrap' in runtime:"
addition="""    if 'legacy_cutover' in runtime:
        value=runtime['legacy_cutover']
        if not isinstance(value,dict) or value!=plan['cutover'] or 'legacy_isolation' not in value:
            raise ValueError('ADOPTED_RUNTIME_CUTOVER_BINDING')
"""
if v.count(anchor)!=1:raise ValueError('ADOPTED_RUNTIME_BINDING_ANCHOR')
v=v.replace(anchor,addition+anchor)
cli='scripts/uk-p2-install.py';w=load(cli)
old="            validate_plan(plan)\n            runtime.preflight"
new="            validate_plan(plan)\n            if 'legacy_isolation' in plan['cutover']:\n                if legacy.preflight(plan['cutover']) is not True:raise ValueError('CLI_ADOPTION_PREFLIGHT_FAILED')\n            runtime.preflight"
if w.count(old)!=1:raise ValueError('ADOPTED_CLI_PREFLIGHT_ANCHOR')
w=w.replace(old,new)

texts={a:s,b:t,c:u,e:v,cli:w,'stage1/p2_legacy_adoption.py':(here/'p2_legacy_adoption.py').read_text()}
for rel,text in texts.items():
 (r/rel).write_text(text);m['files'][rel]=hashlib.sha256(text.encode()).hexdigest()
m_path.write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
print('EXPLICIT_ISOLATION_ADOPTION_OVERLAY=PASS; INSTALL=NO')
